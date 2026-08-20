# coding=utf-8
#
#  pha_fedbatch_controller.py - Generalized Dual-Pump Ratio & Fed-Batch Controller
#
#  Supports:
#  - Generic Pump A & Pump B (GPIO / PWM / Flow outputs)
#  - Independent vs Coupled Ratio mode (maintains A:B volumetric/mass ratio)
#  - Profile modes: Exponential (F0 * e^(mu*t)), Linear ramp, or Constant rate
#  - Min/Max flow rate clamps for each pump
#  - Automated Stage transition (Timed/Volume) -> Sensor-Stat demand dosing (pH/DO stat)
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
    'function_name': 'Dual-Pump Fed-Batch & Ratio Controller',
    'function_name_short': 'Dual-Pump Ratio',

    'message': 'Generalized dual-pump controller for fed-batch bioreactors. '
               'Executes coupled or independent feeding profiles (exponential, linear, constant) '
               'with min/max safety clamps, and supports automated transition to sensor-stat '
               'feedback dosing (pH-stat, DO-stat).',

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
            'name': 'Switch to Sensor-Stat (Stage 3)'
        },
        {
            'id': 'cmd_pause_feed',
            'type': 'button',
            'wait_for_return': True,
            'name': 'Pause / Resume'
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

        # Mode & Kinetics
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
            'id': 'ratio_a_to_b',
            'type': 'float',
            'default_value': 2.687,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Target Ratio (Pump A : Pump B)',
            'phrase': 'Volumetric feed ratio of Pump A to Pump B'
        },
        {
            'id': 'growth_rate_mu',
            'type': 'float',
            'default_value': 0.268,
            'required': True,
            'name': 'Ramp Rate / Specific Growth Rate mu (1/h)',
            'phrase': 'Used for exponential or linear slope calculation'
        },
        {
            'id': 'stage2_duration_hours',
            'type': 'float',
            'default_value': 6.13,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Stage 2 Duration (Hours)',
            'phrase': 'Duration before automatic transition to Stage 3'
        },
        {
            'type': 'new_line'
        },

        # Pump A Configuration (e.g. Carbon / GPIO 3)
        {
            'id': 'output_pump_a',
            'type': 'select_channel',
            'default_value': '',
            'required': True,
            'options_select': ['Output_Channels'],
            'name': 'Pump A Output Channel (e.g. GPIO 3)'
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
            'id': 'f0_pump_a_ml_h',
            'type': 'float',
            'default_value': 8.08,
            'required': True,
            'constraints_pass': constraints_pass_positive_or_zero_value,
            'name': 'Pump A Initial Rate F0 (mL/h)'
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

        # Pump B Configuration (e.g. Nitrogen / GPIO 4)
        {
            'id': 'output_pump_b',
            'type': 'select_channel',
            'default_value': '',
            'required': True,
            'options_select': ['Output_Channels'],
            'name': 'Pump B Output Channel (e.g. GPIO 4)'
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
            'id': 'f0_pump_b_ml_h',
            'type': 'float',
            'default_value': 3.01,
            'required': True,
            'constraints_pass': constraints_pass_positive_or_zero_value,
            'name': 'Pump B Initial Rate F0 (mL/h)'
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

        # Stage 3 Feedback / Sensor-Stat (e.g. pH-stat or DO-stat)
        {
            'id': 'stage3_pump_b_action',
            'type': 'select',
            'default_value': 'stop',
            'required': True,
            'options_select': [
                ('stop', 'Stop Pump B (0 mL/h)'),
                ('maintain', 'Maintain Final Flow Rate'),
                ('continue_profile', 'Continue Profile')
            ],
            'name': 'Stage 3 Pump B Action'
        },
        {
            'id': 'select_feedback_sensor',
            'type': 'select_measurement',
            'default_value': '',
            'required': False,
            'options_select': ['Input', 'Function'],
            'name': 'Feedback Sensor Measurement (e.g. pH / DO)'
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
                ('above_threshold', 'Dose Pump A when Sensor > Threshold (e.g. pH-stat)'),
                ('below_threshold', 'Dose Pump A when Sensor < Threshold (e.g. DO-stat)')
            ],
            'name': 'Feedback Trigger Direction'
        },
        {
            'id': 'feedback_threshold_val',
            'type': 'float',
            'default_value': 6.52,
            'required': True,
            'name': 'Sensor Trigger Threshold'
        },
        {
            'id': 'feedback_dose_vol_ml',
            'type': 'float',
            'default_value': 0.08,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Pump A Pulse Dose Volume (mL)'
        },
        {
            'id': 'feedback_cooldown_sec',
            'type': 'float',
            'default_value': 90.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Feedback Dose Cooldown (seconds)'
        }
    ]
}


class CustomModule(AbstractFunction):
    def __init__(self, function, testing=False):
        super().__init__(function, testing=testing, name=__name__)

        self.control = DaemonControl()
        self.timer_loop = time.time()

        # Config fields
        self.period = None
        self.start_offset = None
        self.control_mode = None
        self.feed_profile = None
        self.ratio_a_to_b = None
        self.growth_rate_mu = None
        self.stage2_duration_hours = None

        # Pump A
        self.output_pump_a_device_id = None
        self.output_pump_a_channel_id = None
        self.output_pump_a_channel = None
        self.pump_a_cal_ml_min = None
        self.f0_pump_a_ml_h = None
        self.pump_a_min_clamp_ml_h = None
        self.pump_a_max_clamp_ml_h = None

        # Pump B
        self.output_pump_b_device_id = None
        self.output_pump_b_channel_id = None
        self.output_pump_b_channel = None
        self.pump_b_cal_ml_min = None
        self.f0_pump_b_ml_h = None
        self.pump_b_min_clamp_ml_h = None
        self.pump_b_max_clamp_ml_h = None

        # Feedback
        self.stage3_pump_b_action = None
        self.select_feedback_sensor_device_id = None
        self.select_feedback_sensor_measurement_id = None
        self.feedback_max_age_sec = None
        self.feedback_trigger_direction = None
        self.feedback_threshold_val = None
        self.feedback_dose_vol_ml = None
        self.feedback_cooldown_sec = None

        # Runtime states
        self.current_stage = 1      # 1: Hold/Idle, 2: Active Profile, 3: Sensor-Stat
        self.is_paused = False
        self.stage_start_time = None
        self.last_feedback_pulse = 0.0
        self.rate_a_ml_h = 0.0
        self.rate_b_ml_h = 0.0
        self.operating_ratio = 0.0
        self.total_a_ml = 0.0
        self.total_b_ml = 0.0
        self.stage3_pulses = 0

        custom_function = db_retrieve_table_daemon(CustomController, unique_id=self.unique_id)
        self.setup_custom_options(FUNCTION_INFORMATION['custom_options'], custom_function)

        if not testing:
            self.try_initialize()

    def initialize(self):
        self.timer_loop = time.time() + self.start_offset
        self.output_pump_a_channel = self.get_output_channel_from_channel_id(self.output_pump_a_channel_id)
        self.output_pump_b_channel = self.get_output_channel_from_channel_id(self.output_pump_b_channel_id)

        # Restore totals from DB
        self.total_a_ml = float(self.get_custom_option("total_a_ml") or 0.0)
        self.total_b_ml = float(self.get_custom_option("total_b_ml") or 0.0)
        self.current_stage = int(self.get_custom_option("current_stage") or 1)

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

    def process_stage2(self):
        if not self.stage_start_time:
            self.stage_start_time = time.time()

        elapsed_h = (time.time() - self.stage_start_time) / 3600.0

        if elapsed_h >= self.stage2_duration_hours:
            self.logger.info(f"Stage 2 complete ({elapsed_h:.2f} h). Switching to Stage 3.")
            self.current_stage = 3
            self.set_custom_option("current_stage", 3)
            self.stage_start_time = time.time()
            return

        # Calculate Pump A rate
        if self.feed_profile == 'exponential':
            calc_a = self.f0_pump_a_ml_h * math.exp(self.growth_rate_mu * elapsed_h)
        elif self.feed_profile == 'linear':
            calc_a = self.f0_pump_a_ml_h + (self.growth_rate_mu * elapsed_h)
        else:
            calc_a = self.f0_pump_a_ml_h

        # Calculate Pump B rate
        if self.control_mode == 'coupled_ratio':
            calc_b = calc_a / max(self.ratio_a_to_b, 0.001)
        else:
            if self.feed_profile == 'exponential':
                calc_b = self.f0_pump_b_ml_h * math.exp(self.growth_rate_mu * elapsed_h)
            elif self.feed_profile == 'linear':
                calc_b = self.f0_pump_b_ml_h + (self.growth_rate_mu * elapsed_h)
            else:
                calc_b = self.f0_pump_b_ml_h

        # Apply Clamps
        self.rate_a_ml_h = max(self.pump_a_min_clamp_ml_h, min(calc_a, self.pump_a_max_clamp_ml_h))
        self.rate_b_ml_h = max(self.pump_b_min_clamp_ml_h, min(calc_b, self.pump_b_max_clamp_ml_h))
        self.operating_ratio = (self.rate_a_ml_h / self.rate_b_ml_h) if self.rate_b_ml_h > 0 else 0.0

        # Deliver pulses
        self.deliver_flow(self.output_pump_a_device_id, self.output_pump_a_channel, self.rate_a_ml_h, self.pump_a_cal_ml_min, True)
        self.deliver_flow(self.output_pump_b_device_id, self.output_pump_b_channel, self.rate_b_ml_h, self.pump_b_cal_ml_min, False)

    def process_stage3(self):
        # Pump B handling in Stage 3
        if self.stage3_pump_b_action == 'stop':
            self.rate_b_ml_h = 0.0
        elif self.stage3_pump_b_action == 'maintain':
            self.deliver_flow(self.output_pump_b_device_id, self.output_pump_b_channel, self.rate_b_ml_h, self.pump_b_cal_ml_min, False)

        self.rate_a_ml_h = 0.0
        now = time.time()
        if (now - self.last_feedback_pulse) < self.feedback_cooldown_sec:
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
            on_sec = self.feedback_dose_vol_ml / (self.pump_a_cal_ml_min / 60.0)
            self.trigger_pulse(self.output_pump_a_device_id, self.output_pump_a_channel, on_sec)
            self.last_feedback_pulse = now
            self.stage3_pulses += 1
            self.total_a_ml += self.feedback_dose_vol_ml
            self.set_custom_option("total_a_ml", self.total_a_ml)

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
        if not device_id or channel is None:
            return
        threading.Thread(
            target=self.control.output_on_off,
            args=(device_id, "on",),
            kwargs={'output_type': 'sec', 'amount': sec, 'output_channel': channel}
        ).start()

    def stop_function(self):
        self.logger.info("Dual-Pump Controller stopped.")

    # UI Commands
    def cmd_start_stage2(self, args_dict):
        self.current_stage = 2
        self.stage_start_time = time.time()
        self.is_paused = False
        self.set_custom_option("current_stage", 2)
        return "Stage 2 active feeding started."

    def cmd_start_stage3(self, args_dict):
        self.current_stage = 3
        self.stage_start_time = time.time()
        self.is_paused = False
        self.set_custom_option("current_stage", 3)
        return "Stage 3 feedback dosing started."

    def cmd_pause_feed(self, args_dict):
        self.is_paused = not self.is_paused
        return f"Feeding {'PAUSED' if self.is_paused else 'RESUMED'}."

    def cmd_reset_totals(self, args_dict):
        self.total_a_ml = self.set_custom_option("total_a_ml", 0.0)
        self.total_b_ml = self.set_custom_option("total_b_ml", 0.0)
        self.stage3_pulses = 0
        self.current_stage = 1
        self.stage_start_time = None
        self.set_custom_option("current_stage", 1)
        return "Totals & stage reset."

    def function_status(self):
        stages = {1: "Stage 1 (Hold/Idle)", 2: "Stage 2 (Active Profile)", 3: "Stage 3 (Sensor-Stat)"}
        elapsed = f"{(time.time() - self.stage_start_time)/3600.0:.2f} h" if self.stage_start_time and self.current_stage > 1 else "0.00 h"
        html = (
            f"<b>Stage:</b> {stages.get(self.current_stage, 'Unknown')} | <b>Elapsed:</b> {elapsed} | <b>State:</b> {'PAUSED' if self.is_paused else 'RUNNING'}<br>"
            f"<b>Pump A:</b> {self.rate_a_ml_h:.2f} mL/h | Total: {self.total_a_ml:.2f} mL | Clamps: [{self.pump_a_min_clamp_ml_h:.1f}-{self.pump_a_max_clamp_ml_h:.1f}]<br>"
            f"<b>Pump B:</b> {self.rate_b_ml_h:.2f} mL/h | Total: {self.total_b_ml:.2f} mL | Clamps: [{self.pump_b_min_clamp_ml_h:.1f}-{self.pump_b_max_clamp_ml_h:.1f}]<br>"
            f"<b>Operating Ratio (A:B):</b> {self.operating_ratio:.2f} : 1"
        )
        return {'string_status': html, 'error': []}
