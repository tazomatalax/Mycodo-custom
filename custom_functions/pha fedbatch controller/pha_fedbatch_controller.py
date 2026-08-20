# coding=utf-8
#
#  pha_fedbatch_controller.py - Stoichiometric Fed-Batch & Dynamic C:N Controller
#
#  Supports:
#  - First-principles Stoichiometric Mass Balances (C, N, Biomass Yields Y_X/S, Y_X/N)
#  - Automatic Calculation of Initial Feed Rates (F0_A, F0_B) and Optimal Stoichiometric Ratio
#  - Live Feed Trimming & Foam Mitigation (+/- 10%, -25% backoff) with runtime multiplier
#  - Robust State Persistence (preserves elapsed stage time, stage number, totals across UI edits)
#  - Independent vs Coupled Ratio mode (maintains A:B volumetric/mass ratio)
#  - Profile modes: Exponential (F0 * e^(mu*t)), Linear ramp, or Constant rate
#  - Physiological Stage Transitions: Cumulative Nitrogen Delivered, DO Spike, or Timed
#  - Stage 3 Adaptive Sensor-Stat (pH-stat, DO-stat) with Volume-Scaled Pulse Dosing & Hourly Safety Cap
#  - Stage 3 Nitrogen Management: Full Starvation, Maintenance Trickle N, or Constant Ratio
#  - Dynamic Broth Volume V(t) and Biomass X(t) Tracking
#
import threading
import time
import math
from flask_babel import lazy_gettext

from mycodo.databases.models import CustomController
from mycodo.functions.base_function import AbstractFunction
from mycodo.mycodo_client import DaemonControl
from mycodo.utils.constraints_pass import constraints_pass_positive_value
from mycodo.utils.constraints_pass import constraints_pass_positive_or_zero_value
from mycodo.utils.database import db_retrieve_table_daemon

FUNCTION_INFORMATION = {
    'function_name_unique': 'dual_pump_fedbatch_controller',
    'function_name': 'Stoichiometric Fed-Batch & C:N Controller',
    'function_name_short': 'Stoichiometric C:N',

    'message': 'Advanced dual-pump controller for microbial fed-batch fermentation. '
               'Implements first-principles stoichiometric balances (C:N, Y_XS, Y_XN), '
               'dynamic growth feeds with live trimming/foam backoff, physiological stage '
               'transitions (N-mass/DO-spike/timed), robust state persistence, and adaptive '
               'sensor-stat feedback with volume-scaled pulse dosing and safety clamping.',

    'options_enabled': [
        'custom_options',
        'function_status'
    ],
    'options_disabled': [
        'measurements_select',
        'measurements_configure'
    ],

    'custom_commands': [
        {
            'id': 'cmd_start_stage2',
            'type': 'button',
            'wait_for_return': True,
            'name': 'Start Active Feeding (Stage 2)'
        },
        {
            'id': 'cmd_start_stage3',
            'type': 'button',
            'wait_for_return': True,
            'name': 'Switch to Product Stage (Stage 3)'
        },
        {
            'id': 'cmd_pause_feed',
            'type': 'button',
            'wait_for_return': True,
            'name': 'Pause / Resume'
        },
        {
            'id': 'cmd_trim_minus_10',
            'type': 'button',
            'wait_for_return': True,
            'name': 'Trim Feed -10%'
        },
        {
            'id': 'cmd_trim_plus_10',
            'type': 'button',
            'wait_for_return': True,
            'name': 'Trim Feed +10%'
        },
        {
            'id': 'cmd_trim_foam_backoff',
            'type': 'button',
            'wait_for_return': True,
            'name': 'Foam Backoff (-25%)'
        },
        {
            'id': 'cmd_trim_reset',
            'type': 'button',
            'wait_for_return': True,
            'name': 'Reset Trim (100%)'
        },
        {
            'id': 'cmd_reset_totals',
            'type': 'button',
            'wait_for_return': True,
            'name': 'Reset Totals & Stage'
        }
    ],

    'custom_options': [
        # Timing
        {
            'id': 'period',
            'type': 'float',
            'default_value': 30.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Control Loop Period (seconds)'),
            'phrase': 'Cycle duration for updating flow rates and time-proportioned pulses'
        },
        {
            'id': 'start_offset',
            'type': 'integer',
            'default_value': 5,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Start Offset (seconds)')
        },
        {
            'type': 'new_line'
        },

        # Calculation Mode & Kinetics
        {
            'id': 'calc_mode',
            'type': 'select',
            'default_value': 'direct_rates',
            'required': True,
            'options_select': [
                ('direct_rates', 'Direct Manual Rates (Legacy F0 & Ratio)'),
                ('stoichiometric_balance', 'Stoichiometric Model (Auto F0, Ratio, & N-Target)')
            ],
            'name': 'Model & Parameterization Mode'
        },
        {
            'id': 'growth_rate_mu',
            'type': 'float',
            'default_value': 0.268,
            'required': True,
            'name': 'Specific Growth Rate mu (1/h)',
            'phrase': 'Target specific growth rate for exponential feed calculation'
        },
        {
            'id': 'feed_rate_scale',
            'type': 'float',
            'default_value': 1.0,
            'required': False,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Live Feed Rate Scale / Trim (Multiplier)',
            'phrase': 'Multiplier applied to calculated growth feed rates (e.g. 0.80 = 80%, 1.0 = 100%)'
        },
        {
            'id': 'feed_profile',
            'type': 'select',
            'default_value': 'exponential',
            'required': True,
            'options_select': [
                ('exponential', 'Exponential: F(t) = F0 * e^(mu * t)'),
                ('linear', 'Linear Ramp: F(t) = F0 + (slope * t)'),
                ('constant', 'Constant Rate: F(t) = F0')
            ],
            'name': 'Feed Profile'
        },
        {
            'id': 'control_mode',
            'type': 'select',
            'default_value': 'coupled_ratio',
            'required': True,
            'options_select': [
                ('coupled_ratio', 'Coupled Ratio (Pump B = Pump A / Ratio)'),
                ('independent', 'Independent Profiles (Individual Setpoints)')
            ],
            'name': 'Coupling Mode'
        },
        {
            'type': 'new_line'
        },

        # Stoichiometric Mass Balance Parameters
        {
            'id': 'initial_volume_l',
            'type': 'float',
            'default_value': 5.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Initial Working Volume V0 (L)',
            'phrase': 'Starting culture liquid volume in bioreactor'
        },
        {
            'id': 'initial_biomass_g_l',
            'type': 'float',
            'default_value': 0.40,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Initial Biomass X0 (g/L CDW)',
            'phrase': 'Biomass concentration at the start of fed-batch feeding'
        },
        {
            'id': 'target_biomass_g_l',
            'type': 'float',
            'default_value': 25.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Target Biomass X_target (g/L CDW)',
            'phrase': 'Desired biomass concentration at end of Stage 2 growth'
        },
        {
            'id': 'yield_yxs_g_g',
            'type': 'float',
            'default_value': 0.65,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Biomass Yield on Carbon Y_X/S (g CDW / g sub)',
            'phrase': 'Grams dry cell weight produced per gram of carbon substrate consumed'
        },
        {
            'id': 'yield_yxn_g_g',
            'type': 'float',
            'default_value': 4.20,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Biomass Yield on Nitrogen Y_X/N (g CDW / g N-salt)',
            'phrase': 'Grams dry cell weight produced per gram of nitrogen stock salt'
        },
        {
            'id': 'stock_c_conc_g_l',
            'type': 'float',
            'default_value': 910.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Carbon Stock Concentration S_i,A (g/L)',
            'phrase': 'Concentration of carbon substrate in Pump A feed bottle (neat octanoic acid = ~910 g/L)'
        },
        {
            'id': 'stock_n_conc_g_l',
            'type': 'float',
            'default_value': 500.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Nitrogen Stock Concentration N_i,B (g/L)',
            'phrase': 'Concentration of nitrogen salt in Pump B feed bottle (500 g/L (NH4)2SO4)'
        },
        {
            'id': 'maintenance_ms_g_g_h',
            'type': 'float',
            'default_value': 0.02,
            'required': True,
            'constraints_pass': constraints_pass_positive_or_zero_value,
            'name': 'Maintenance Coeff m_S (g sub / g CDW / h)',
            'phrase': 'Specific substrate consumption rate for cellular maintenance'
        },
        {
            'type': 'new_line'
        },

        # Manual / Direct Rate Parameters (Fallback / Override)
        {
            'id': 'ratio_a_to_b',
            'type': 'float',
            'default_value': 2.684,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Manual Ratio (Pump A : Pump B)',
            'phrase': 'Used when Mode is Direct Manual Rates'
        },
        {
            'id': 'f0_pump_a_ml_h',
            'type': 'float',
            'default_value': 8.08,
            'required': True,
            'constraints_pass': constraints_pass_positive_or_zero_value,
            'name': 'Manual Pump A Initial Rate F0 (mL/h)'
        },
        {
            'id': 'f0_pump_b_ml_h',
            'type': 'float',
            'default_value': 3.01,
            'required': True,
            'constraints_pass': constraints_pass_positive_or_zero_value,
            'name': 'Manual Pump B Initial Rate F0 (mL/h)'
        },
        {
            'type': 'new_line'
        },

        # Stage Transition Triggers
        {
            'id': 'transition_trigger',
            'type': 'select',
            'default_value': 'time_duration',
            'required': True,
            'options_select': [
                ('time_duration', 'Timed Elapsed Duration (Hours)'),
                ('nitrogen_delivered', 'Stoichiometric N-Mass Delivered (Target Biomass reached)'),
                ('sensor_trigger', 'Online Sensor Trigger (DO Spike / pH Shift)')
            ],
            'name': 'Stage 2 -> Stage 3 Transition Trigger'
        },
        {
            'id': 'stage2_duration_hours',
            'type': 'float',
            'default_value': 6.13,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Stage 2 Duration (Hours)',
            'phrase': 'Duration of exponential feeding phase before switching to Stage 3'
        },
        {
            'type': 'new_line'
        },

        # Pump A Configuration (Carbon / Octanoic Acid)
        {
            'id': 'output_pump_a',
            'type': 'select_channel',
            'default_value': '',
            'required': True,
            'options_select': ['Output_Channels'],
            'name': 'Pump A Output Channel (Carbon Feed)'
        },
        {
            'id': 'pump_a_cal_ml_min',
            'type': 'float',
            'default_value': 10.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Pump A Calibration (mL/min at 100%)'
        },
        {
            'id': 'pump_a_min_clamp_ml_h',
            'type': 'float',
            'default_value': 1.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_or_zero_value,
            'name': 'Pump A Min Rate Clamp (mL/h)'
        },
        {
            'id': 'pump_a_max_clamp_ml_h',
            'type': 'float',
            'default_value': 55.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Pump A Max Rate Clamp (mL/h)'
        },
        {
            'type': 'new_line'
        },

        # Pump B Configuration (Nitrogen / Nutrients)
        {
            'id': 'output_pump_b',
            'type': 'select_channel',
            'default_value': '',
            'required': True,
            'options_select': ['Output_Channels'],
            'name': 'Pump B Output Channel (Nitrogen Feed)'
        },
        {
            'id': 'pump_b_cal_ml_min',
            'type': 'float',
            'default_value': 10.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Pump B Calibration (mL/min at 100%)'
        },
        {
            'id': 'pump_b_min_clamp_ml_h',
            'type': 'float',
            'default_value': 0.5,
            'required': True,
            'constraints_pass': constraints_pass_positive_or_zero_value,
            'name': 'Pump B Min Rate Clamp (mL/h)'
        },
        {
            'id': 'pump_b_max_clamp_ml_h',
            'type': 'float',
            'default_value': 25.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Pump B Max Rate Clamp (mL/h)'
        },
        {
            'type': 'new_line'
        },

        # Stage 3 Policy & Sensor-Stat (Product / Accumulation Phase)
        {
            'id': 'stage3_pump_b_action',
            'type': 'select',
            'default_value': 'stop',
            'required': True,
            'options_select': [
                ('stop', 'Stop Pump B (0 mL/h - Full Starvation)'),
                ('trickle_nitrogen', 'Trickle Nitrogen (Constant Low Maintenance Feed)'),
                ('maintain', 'Maintain Final Flow Rate'),
                ('continue_profile', 'Continue Profile')
            ],
            'name': 'Stage 3 Nitrogen (Pump B) Policy'
        },
        {
            'id': 'stage3_trickle_n_rate_ml_h',
            'type': 'float',
            'default_value': 0.5,
            'required': True,
            'constraints_pass': constraints_pass_positive_or_zero_value,
            'name': 'Stage 3 Trickle N Flow Rate (mL/h)',
            'phrase': 'Maintains active metabolism and prevents metabolic arrest if trickle is selected'
        },
        {
            'id': 'select_feedback_sensor',
            'type': 'select_measurement',
            'default_value': '',
            'required': False,
            'options_select': ['Input', 'Function'],
            'name': 'Stage 3 Feedback Sensor (pH Measurement)'
        },
        {
            'id': 'feedback_max_age_sec',
            'type': 'integer',
            'default_value': 120,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Max Sensor Age (seconds)'
        },
        {
            'id': 'feedback_trigger_direction',
            'type': 'select',
            'default_value': 'above_threshold',
            'required': True,
            'options_select': [
                ('above_threshold', 'Dose Pump A when Sensor > Threshold (pH-stat or DO-spike)'),
                ('below_threshold', 'Dose Pump A when Sensor < Threshold (DO-stat)')
            ],
            'name': 'Feedback Trigger Direction'
        },
        {
            'id': 'feedback_threshold_val',
            'type': 'float',
            'default_value': 6.52,
            'required': True,
            'name': 'Sensor Trigger Threshold (e.g. pH 6.52)'
        },
        {
            'id': 'feedback_dose_vol_ml',
            'type': 'float',
            'default_value': 0.10,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Base Pulse Dose Volume (mL)'
        },
        {
            'id': 'volume_adaptive_dose',
            'type': 'bool',
            'default_value': True,
            'name': 'Scale Dose Volume with Broth Volume V(t)',
            'phrase': 'Multiplies base dose by V(t)/V0 to maintain uniform nutrient concentration'
        },
        {
            'id': 'feedback_cooldown_sec',
            'type': 'float',
            'default_value': 90.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Feedback Dose Cooldown (seconds)'
        },
        {
            'id': 'stage3_max_rate_clamp_ml_h',
            'type': 'float',
            'default_value': 15.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Stage 3 Max Acid Dosing Rate Clamp (mL/h)',
            'phrase': 'Safety limit on total acid dosed per rolling hour during pH-stat feeding to prevent toxicity/burn'
        }
    ]
}


class CustomModule(AbstractFunction):
    def __init__(self, function, testing=False):
        super().__init__(function, testing=testing, name=__name__)

        self.control = DaemonControl()
        self.timer_loop = time.time()

        # Timing
        self.period = None
        self.start_offset = None

        # Mode & Kinetics
        self.calc_mode = None
        self.growth_rate_mu = None
        self.feed_rate_scale = 1.0
        self.feed_profile = None
        self.control_mode = None

        # Stoichiometry
        self.initial_volume_l = None
        self.initial_biomass_g_l = None
        self.target_biomass_g_l = None
        self.yield_yxs_g_g = None
        self.yield_yxn_g_g = None
        self.stock_c_conc_g_l = None
        self.stock_n_conc_g_l = None
        self.maintenance_ms_g_g_h = None

        # Manual overrides
        self.ratio_a_to_b = None
        self.f0_pump_a_ml_h = None
        self.f0_pump_b_ml_h = None

        # Stage Transition
        self.transition_trigger = None
        self.stage2_duration_hours = None

        # Pump A
        self.output_pump_a_device_id = None
        self.output_pump_a_channel_id = None
        self.output_pump_a_channel = None
        self.pump_a_cal_ml_min = None
        self.pump_a_min_clamp_ml_h = None
        self.pump_a_max_clamp_ml_h = None

        # Pump B
        self.output_pump_b_device_id = None
        self.output_pump_b_channel_id = None
        self.output_pump_b_channel = None
        self.pump_b_cal_ml_min = None
        self.pump_b_min_clamp_ml_h = None
        self.pump_b_max_clamp_ml_h = None

        # Stage 3 Policy & Sensor-Stat
        self.stage3_pump_b_action = None
        self.stage3_trickle_n_rate_ml_h = None
        self.select_feedback_sensor_device_id = None
        self.select_feedback_sensor_measurement_id = None
        self.feedback_max_age_sec = None
        self.feedback_trigger_direction = None
        self.feedback_threshold_val = None
        self.feedback_dose_vol_ml = None
        self.volume_adaptive_dose = None
        self.feedback_cooldown_sec = None
        self.stage3_max_rate_clamp_ml_h = None

        # Runtime calculated stoichiometric values
        self.computed_f0_a_ml_h = 0.0
        self.computed_f0_b_ml_h = 0.0
        self.computed_ratio_a_to_b = 0.0
        self.target_n_mass_g = 0.0
        self.target_n_volume_ml = 0.0
        self.est_stage2_duration_h = 0.0

        # Runtime states
        self.current_stage = 1      # 1: Hold/Idle, 2: Active Profile, 3: Sensor-Stat/Product
        self.is_paused = False
        self.stage_start_time = None
        self.last_feedback_pulse = 0.0
        self.rate_a_ml_h = 0.0
        self.rate_b_ml_h = 0.0
        self.operating_ratio = 0.0
        self.total_a_ml = 0.0
        self.total_b_ml = 0.0
        self.cumulative_n_delivered_g = 0.0
        self.cumulative_c_delivered_g = 0.0
        self.current_volume_l = 5.0
        self.current_biomass_g_l = 0.0
        self.stage3_pulses = 0
        self.stage3_recent_pulses = []  # List of {'time': ts, 'vol_ml': vol} for rolling 1h clamp

        custom_function = db_retrieve_table_daemon(CustomController, unique_id=self.unique_id)
        self.setup_custom_options(FUNCTION_INFORMATION['custom_options'], custom_function)

        if not testing:
            self.try_initialize()

    def initialize(self):
        self.timer_loop = time.time() + self.start_offset
        self.output_pump_a_channel = self.get_output_channel_from_channel_id(self.output_pump_a_channel_id)
        self.output_pump_b_channel = self.get_output_channel_from_channel_id(self.output_pump_b_channel_id)

        # Restore totals and persistent runtime state from DB
        self.total_a_ml = float(self.get_custom_option("total_a_ml") or 0.0)
        self.total_b_ml = float(self.get_custom_option("total_b_ml") or 0.0)
        self.current_stage = int(self.get_custom_option("current_stage") or 1)

        saved_start_time = float(self.get_custom_option("stage_start_time") or 0.0)
        self.stage_start_time = saved_start_time if saved_start_time > 0 else None

        self.is_paused = bool(self.get_custom_option("is_paused") or False)
        self.stage3_pulses = int(self.get_custom_option("stage3_pulses") or 0)

        saved_scale = self.get_custom_option("feed_rate_scale")
        if saved_scale is not None:
            self.feed_rate_scale = float(saved_scale)
        else:
            self.feed_rate_scale = 1.0

        # Calculate stoichiometry
        self.calculate_stoichiometry()
        self.update_mass_and_volume_estimates()

    def calculate_stoichiometry(self):
        """Compute initial feed rates, stoichiometric ratios, and required nitrogen from first principles."""
        v0 = max(float(self.initial_volume_l or 5.0), 0.01)
        x0 = max(float(self.initial_biomass_g_l or 0.40), 0.01)
        x_target = max(float(self.target_biomass_g_l or 25.0), x0)
        yxs = max(float(self.yield_yxs_g_g or 0.65), 0.001)
        yxn = max(float(self.yield_yxn_g_g or 4.20), 0.001)
        c_stock = max(float(self.stock_c_conc_g_l or 910.0), 0.1)
        n_stock = max(float(self.stock_n_conc_g_l or 500.0), 0.1)
        mu = max(float(self.growth_rate_mu or 0.268), 0.0)
        ms = max(float(self.maintenance_ms_g_g_h or 0.02), 0.0)

        # Total initial cell mass (g)
        m_x0 = x0 * v0

        # Substrate specific uptake rate q_S = mu/Y_XS + m_S (g/g/h)
        qs_0 = (mu / yxs) + ms
        # Nitrogen specific uptake rate q_N = mu/Y_XN (g/g/h)
        qn_0 = mu / yxn

        # Initial mass flow rates required (g/h)
        m_dot_c0 = qs_0 * m_x0
        m_dot_n0 = qn_0 * m_x0

        # Initial volumetric flow rates (mL/h)
        self.computed_f0_a_ml_h = (m_dot_c0 / c_stock) * 1000.0
        self.computed_f0_b_ml_h = (m_dot_n0 / n_stock) * 1000.0

        # Stoichiometric Volumetric Ratio (Pump A : Pump B)
        if self.computed_f0_b_ml_h > 0:
            self.computed_ratio_a_to_b = self.computed_f0_a_ml_h / self.computed_f0_b_ml_h
        else:
            self.computed_ratio_a_to_b = 1.0

        # Total Nitrogen salt mass required to build target biomass (g)
        delta_biomass_g = (x_target - x0) * v0
        self.target_n_mass_g = delta_biomass_g / yxn
        self.target_n_volume_ml = (self.target_n_mass_g / n_stock) * 1000.0

        # Estimated Stage 2 duration
        if mu > 0:
            self.est_stage2_duration_h = math.log(x_target / x0) / mu
        else:
            self.est_stage2_duration_h = float(self.stage2_duration_hours or 6.13)

    def update_mass_and_volume_estimates(self):
        """Update current broth volume, delivered elemental masses, and cell dry weight."""
        v0 = max(float(self.initial_volume_l or 5.0), 0.01)
        x0 = max(float(self.initial_biomass_g_l or 0.40), 0.01)
        yxn = max(float(self.yield_yxn_g_g or 4.20), 0.001)
        c_stock = max(float(self.stock_c_conc_g_l or 910.0), 0.1)
        n_stock = max(float(self.stock_n_conc_g_l or 500.0), 0.1)

        self.current_volume_l = v0 + ((self.total_a_ml + self.total_b_ml) / 1000.0)
        self.cumulative_c_delivered_g = (self.total_a_ml / 1000.0) * c_stock
        self.cumulative_n_delivered_g = (self.total_b_ml / 1000.0) * n_stock

        total_biomass_g = (x0 * v0) + (self.cumulative_n_delivered_g * yxn)
        self.current_biomass_g_l = total_biomass_g / max(self.current_volume_l, 0.01)

    def loop(self):
        if self.timer_loop > time.time():
            return
        while self.timer_loop < time.time():
            self.timer_loop += self.period

        if self.is_paused or self.current_stage == 1:
            self.rate_a_ml_h, self.rate_b_ml_h = 0.0, 0.0
            return

        if self.current_stage == 2:
            self.process_stage2()
        elif self.current_stage == 3:
            self.process_stage3()

        self.update_mass_and_volume_estimates()

    def process_stage2(self):
        if not self.stage_start_time:
            self.stage_start_time = time.time()
            self.set_custom_option("stage_start_time", self.stage_start_time)

        elapsed_h = (time.time() - self.stage_start_time) / 3600.0

        # Evaluate Stage Transition Triggers
        should_transition = False
        reason = ""

        if self.transition_trigger == 'nitrogen_delivered':
            if self.cumulative_n_delivered_g >= self.target_n_mass_g and self.target_n_mass_g > 0:
                should_transition = True
                reason = f"Target Nitrogen Delivered ({self.cumulative_n_delivered_g:.2f}g / {self.target_n_mass_g:.2f}g)"
            elif elapsed_h >= (self.stage2_duration_hours * 1.5):  # Safety timeout fallback
                should_transition = True
                reason = f"Safety timeout reached ({elapsed_h:.2f} h)"
        elif self.transition_trigger == 'sensor_trigger':
            # Check sensor trigger (e.g. DO spike indicating N-exhaustion)
            if elapsed_h >= 1.0:  # Minimum growth duration before checking DO spike
                sensor_data = self.get_last_measurement(
                    self.select_feedback_sensor_device_id,
                    self.select_feedback_sensor_measurement_id,
                    max_age=self.feedback_max_age_sec
                )
                if sensor_data and sensor_data[1] is not None:
                    val = sensor_data[1]
                    trig = (val > self.feedback_threshold_val) if self.feedback_trigger_direction == 'above_threshold' else (val < self.feedback_threshold_val)
                    if trig:
                        should_transition = True
                        reason = f"Online Sensor Trigger ({val:.2f})"
        else:  # time_duration
            if elapsed_h >= self.stage2_duration_hours:
                should_transition = True
                reason = f"Elapsed Time ({elapsed_h:.2f} h / {self.stage2_duration_hours:.2f} h)"

        if should_transition:
            self.logger.info(f"Stage 2 complete [{reason}]. Switching to Stage 3 (Product Phase).")
            self.current_stage = 3
            self.stage_start_time = time.time()
            self.set_custom_option("current_stage", 3)
            self.set_custom_option("stage_start_time", self.stage_start_time)
            return

        # Determine baseline F0 and Ratio based on calculation mode
        if self.calc_mode == 'stoichiometric_balance':
            f0_a = self.computed_f0_a_ml_h
            f0_b = self.computed_f0_b_ml_h
            target_ratio = self.computed_ratio_a_to_b
        else:
            f0_a = self.f0_pump_a_ml_h or 8.08
            f0_b = self.f0_pump_b_ml_h or 3.01
            target_ratio = self.ratio_a_to_b or 2.684

        # Calculate Pump A rate
        if self.feed_profile == 'exponential':
            calc_a = f0_a * math.exp(self.growth_rate_mu * elapsed_h)
        elif self.feed_profile == 'linear':
            calc_a = f0_a + (self.growth_rate_mu * elapsed_h)
        else:
            calc_a = f0_a

        # Calculate Pump B rate
        if self.control_mode == 'coupled_ratio':
            calc_b = calc_a / max(target_ratio, 0.001)
        else:
            if self.feed_profile == 'exponential':
                calc_b = f0_b * math.exp(self.growth_rate_mu * elapsed_h)
            elif self.feed_profile == 'linear':
                calc_b = f0_b + (self.growth_rate_mu * elapsed_h)
            else:
                calc_b = f0_b

        # Apply Live Feed Rate Scale / Trim (Foaming or organism responsiveness)
        trim_multiplier = max(float(self.feed_rate_scale or 1.0), 0.05)
        calc_a *= trim_multiplier
        calc_b *= trim_multiplier

        # Apply Safety Clamps
        self.rate_a_ml_h = max(self.pump_a_min_clamp_ml_h, min(calc_a, self.pump_a_max_clamp_ml_h))
        self.rate_b_ml_h = max(self.pump_b_min_clamp_ml_h, min(calc_b, self.pump_b_max_clamp_ml_h))
        self.operating_ratio = (self.rate_a_ml_h / self.rate_b_ml_h) if self.rate_b_ml_h > 0 else 0.0

        # Deliver pulses
        self.deliver_flow(self.output_pump_a_device_id, self.output_pump_a_channel, self.rate_a_ml_h, self.pump_a_cal_ml_min, True)
        self.deliver_flow(self.output_pump_b_device_id, self.output_pump_b_channel, self.rate_b_ml_h, self.pump_b_cal_ml_min, False)

    def process_stage3(self):
        # Pump B (Nitrogen) handling in Stage 3
        if self.stage3_pump_b_action == 'stop':
            self.rate_b_ml_h = 0.0
        elif self.stage3_pump_b_action == 'trickle_nitrogen':
            self.rate_b_ml_h = float(self.stage3_trickle_n_rate_ml_h or 0.5)
            self.deliver_flow(self.output_pump_b_device_id, self.output_pump_b_channel, self.rate_b_ml_h, self.pump_b_cal_ml_min, False)
        elif self.stage3_pump_b_action == 'maintain':
            self.deliver_flow(self.output_pump_b_device_id, self.output_pump_b_channel, self.rate_b_ml_h, self.pump_b_cal_ml_min, False)
        elif self.stage3_pump_b_action == 'continue_profile':
            if not self.stage_start_time:
                self.stage_start_time = time.time()
                self.set_custom_option("stage_start_time", self.stage_start_time)
            elapsed_h = (time.time() - self.stage_start_time) / 3600.0
            calc_b = (self.computed_f0_b_ml_h or 3.01) * math.exp(self.growth_rate_mu * elapsed_h)
            self.rate_b_ml_h = max(self.pump_b_min_clamp_ml_h, min(calc_b, self.pump_b_max_clamp_ml_h))
            self.deliver_flow(self.output_pump_b_device_id, self.output_pump_b_channel, self.rate_b_ml_h, self.pump_b_cal_ml_min, False)

        self.rate_a_ml_h = 0.0
        now = time.time()
        if (now - self.last_feedback_pulse) < self.feedback_cooldown_sec:
            return

        # Check rolling 1-hour acid dosage to prevent runaway acid dumping
        self.stage3_recent_pulses = [p for p in self.stage3_recent_pulses if now - p['time'] < 3600.0]
        recent_hour_dose_ml = sum(p['vol_ml'] for p in self.stage3_recent_pulses)
        max_hourly_clamp = float(self.stage3_max_rate_clamp_ml_h or 15.0)

        if recent_hour_dose_ml >= max_hourly_clamp:
            return

        sensor_data = self.get_last_measurement(
            self.select_feedback_sensor_device_id,
            self.select_feedback_sensor_measurement_id,
            max_age=self.feedback_max_age_sec
        )
        if not sensor_data or sensor_data[1] is None:
            return

        val = sensor_data[1]
        triggered = (val > self.feedback_threshold_val) if self.feedback_trigger_direction == 'above_threshold' else (val < self.feedback_threshold_val)

        if triggered:
            # Volume-Adaptive Pulse Sizing
            v0 = max(float(self.initial_volume_l or 5.0), 0.01)
            vol_scale = max(self.current_volume_l / v0, 1.0) if self.volume_adaptive_dose else 1.0
            effective_dose_ml = self.feedback_dose_vol_ml * vol_scale

            on_sec = effective_dose_ml / (self.pump_a_cal_ml_min / 60.0)
            self.trigger_pulse(self.output_pump_a_device_id, self.output_pump_a_channel, on_sec)
            self.last_feedback_pulse = now
            self.stage3_pulses += 1
            self.stage3_recent_pulses.append({'time': now, 'vol_ml': effective_dose_ml})
            self.total_a_ml += effective_dose_ml
            self.set_custom_option("total_a_ml", self.total_a_ml)
            self.set_custom_option("stage3_pulses", self.stage3_pulses)

    def deliver_flow(self, device_id, channel, rate_ml_h, cal_ml_min, is_pump_a):
        if not device_id or channel is None or rate_ml_h <= 0 or cal_ml_min <= 0:
            return
        vol_ml = (rate_ml_h / 3600.0) * self.period
        on_sec = min(vol_ml / (cal_ml_min / 60.0), self.period)
        if on_sec > 0.05:
            self.trigger_pulse(device_id, channel, on_sec)
            if is_pump_a:
                self.total_a_ml += vol_ml
                self.set_custom_option("total_a_ml", self.total_a_ml)
            else:
                self.total_b_ml += vol_ml
                self.set_custom_option("total_b_ml", self.total_b_ml)

    def trigger_pulse(self, device_id, channel, sec):
        if not device_id or channel is None or sec <= 0:
            return
        threading.Thread(
            target=self.control.output_on_off,
            args=(device_id, "on",),
            kwargs={'output_type': 'sec', 'amount': sec, 'output_channel': channel}
        ).start()

    def stop_function(self):
        self.logger.info("Stoichiometric Dual-Pump Controller stopped.")

    # UI Commands
    def cmd_start_stage2(self, args_dict):
        self.current_stage = 2
        self.stage_start_time = time.time()
        self.is_paused = False
        self.set_custom_option("current_stage", 2)
        self.set_custom_option("stage_start_time", self.stage_start_time)
        self.set_custom_option("is_paused", False)
        self.calculate_stoichiometry()
        return f"Stage 2 active feeding started (F0_A: {self.computed_f0_a_ml_h:.2f} mL/h, F0_B: {self.computed_f0_b_ml_h:.2f} mL/h)."

    def cmd_start_stage3(self, args_dict):
        self.current_stage = 3
        self.stage_start_time = time.time()
        self.is_paused = False
        self.set_custom_option("current_stage", 3)
        self.set_custom_option("stage_start_time", self.stage_start_time)
        self.set_custom_option("is_paused", False)
        return "Stage 3 product / feedback dosing started."

    def cmd_pause_feed(self, args_dict):
        self.is_paused = not self.is_paused
        self.set_custom_option("is_paused", self.is_paused)
        return f"Feeding {'PAUSED' if self.is_paused else 'RESUMED'}."

    def cmd_trim_minus_10(self, args_dict):
        self.feed_rate_scale = max(0.10, round(self.feed_rate_scale - 0.10, 2))
        self.set_custom_option("feed_rate_scale", self.feed_rate_scale)
        return f"Feed rate scaled to {int(self.feed_rate_scale * 100)}%."

    def cmd_trim_plus_10(self, args_dict):
        self.feed_rate_scale = min(2.00, round(self.feed_rate_scale + 0.10, 2))
        self.set_custom_option("feed_rate_scale", self.feed_rate_scale)
        return f"Feed rate scaled to {int(self.feed_rate_scale * 100)}%."

    def cmd_trim_foam_backoff(self, args_dict):
        self.feed_rate_scale = max(0.10, round(self.feed_rate_scale - 0.25, 2))
        self.set_custom_option("feed_rate_scale", self.feed_rate_scale)
        return f"Foam backoff applied: Feed rate scaled to {int(self.feed_rate_scale * 100)}%."

    def cmd_trim_reset(self, args_dict):
        self.feed_rate_scale = 1.0
        self.set_custom_option("feed_rate_scale", 1.0)
        return "Feed rate trim reset to 100%."

    def cmd_reset_totals(self, args_dict):
        self.total_a_ml = 0.0
        self.total_b_ml = 0.0
        self.stage3_pulses = 0
        self.feed_rate_scale = 1.0
        self.stage3_recent_pulses = []
        self.set_custom_option("total_a_ml", 0.0)
        self.set_custom_option("total_b_ml", 0.0)
        self.set_custom_option("stage3_pulses", 0)
        self.set_custom_option("feed_rate_scale", 1.0)
        self.current_stage = 1
        self.stage_start_time = None
        self.set_custom_option("current_stage", 1)
        self.set_custom_option("stage_start_time", 0.0)
        self.calculate_stoichiometry()
        self.update_mass_and_volume_estimates()
        return "Totals & stage reset to Stage 1 (Standby)."

    def function_status(self):
        stages = {1: "Stage 1 (Hold/Idle)", 2: "Stage 2 (Active Growth)", 3: "Stage 3 (Product/PHA Phase)"}
        elapsed = f"{(time.time() - self.stage_start_time)/3600.0:.2f} h" if self.stage_start_time and self.current_stage > 1 else "0.00 h"

        mode_str = "Stoichiometric Model" if self.calc_mode == 'stoichiometric_balance' else "Direct Rates"
        f0_a_disp = self.computed_f0_a_ml_h if self.calc_mode == 'stoichiometric_balance' else (self.f0_pump_a_ml_h or 8.08)
        f0_b_disp = self.computed_f0_b_ml_h if self.calc_mode == 'stoichiometric_balance' else (self.f0_pump_b_ml_h or 3.01)
        ratio_disp = self.computed_ratio_a_to_b if self.calc_mode == 'stoichiometric_balance' else (self.ratio_a_to_b or 2.684)

        n_progress = f"{self.cumulative_n_delivered_g:.2f}g / {self.target_n_mass_g:.2f}g ({min(100.0, (self.cumulative_n_delivered_g/max(self.target_n_mass_g, 1e-3))*100.0):.1f}%)" if self.target_n_mass_g > 0 else "N/A"

        scale_pct = int(self.feed_rate_scale * 100) if self.feed_rate_scale is not None else 100
        trim_str = f"<span style='color: {'#28a745' if scale_pct == 100 else '#ffc107' if scale_pct < 100 else '#17a2b8'}; font-weight:bold;'>{scale_pct}%</span>"

        now = time.time()
        recent_1h_acid = sum(p['vol_ml'] for p in self.stage3_recent_pulses if now - p['time'] < 3600.0) if hasattr(self, 'stage3_recent_pulses') else 0.0

        html = (
            f"<div style='line-height:1.5; font-size:13px;'>"
            f"<b>Stage:</b> <span style='color:#007bff; font-weight:bold;'>{stages.get(self.current_stage, 'Unknown')}</span> | "
            f"<b>State:</b> <span style='color:{'#dc3545' if self.is_paused else '#28a745'}; font-weight:bold;'>{'PAUSED' if self.is_paused else 'RUNNING'}</span> | "
            f"<b>Elapsed:</b> {elapsed} | <b>Feed Trim:</b> {trim_str}<br>"
            f"<b>Mode:</b> {mode_str} | <b>Target Ratio (A:B):</b> {ratio_disp:.2f}:1 | <b>&mu;:</b> {self.growth_rate_mu:.3f} h⁻¹<br>"
            f"<b>Volume V(t):</b> {self.current_volume_l:.2f} L | <b>Est. Biomass X(t):</b> {self.current_biomass_g_l:.2f} g/L<br>"
            f"<b>Pump A (Octanoic):</b> {self.rate_a_ml_h:.2f} mL/h (F0: {f0_a_disp:.2f}) | Total: {self.total_a_ml:.2f} mL ({self.cumulative_c_delivered_g:.2f} g C)<br>"
            f"<b>Pump B ((NH4)2SO4):</b> {self.rate_b_ml_h:.2f} mL/h (F0: {f0_b_disp:.2f}) | Total: {self.total_b_ml:.2f} mL ({self.cumulative_n_delivered_g:.2f} g N-salt)<br>"
            f"<b>N-Target Progress:</b> {n_progress}<br>"
            f"<b>Stage 3 pH-Stat:</b> {self.stage3_pulses} pulses | Rolling 1h Acid: {recent_1h_acid:.2f} / {float(self.stage3_max_rate_clamp_ml_h or 15.0):.1f} mL | N-Policy: {self.stage3_pump_b_action}"
            f"</div>"
        )
        return {'string_status': html, 'error': []}
