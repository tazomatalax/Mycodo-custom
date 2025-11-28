# coding=utf-8
#
#  ph_control_dual_output.py - pH Control using CO2 MFC and Base Pump
#
#  This custom function implements bang-bang control for pH regulation
#  using a CO2 mass flow controller to lower pH and a base pump to raise pH.
#  Based on Mycodo's regulate_ph_ec.py but simplified for gas/liquid control.
#
import threading
import time

from flask_babel import lazy_gettext

from mycodo.databases.models import CustomController
from mycodo.functions.base_function import AbstractFunction
from mycodo.mycodo_client import DaemonControl
from mycodo.utils.constraints_pass import constraints_pass_positive_value
from mycodo.utils.database import db_retrieve_table_daemon
from mycodo.utils.influx import write_influxdb_value

# Measurement channels for InfluxDB logging
measurements_dict = {
    0: {
        'measurement': 'volume_flow_rate',
        'unit': 'ml_per_minute',
        'name': 'CO2 Flow Rate'
    },
    1: {
        'measurement': 'volume',
        'unit': 'ml',
        'name': 'Base Volume Dosed'
    },
    2: {
        'measurement': 'duration',
        'unit': 's',
        'name': 'Base Duration Dosed'
    },
    3: {
        'measurement': 'volume',
        'unit': 'ml',
        'name': 'Cumulative Base Volume'
    },
    4: {
        'measurement': 'duration',
        'unit': 's',
        'name': 'Cumulative CO2 Flow Time'
    }
}

FUNCTION_INFORMATION = {
    'function_name_unique': 'ph_control_dual_output',
    'function_name': 'pH Control (CO2 MFC + Base Pump)',
    'function_name_short': 'pH Control Dual',
    'measurements_dict': measurements_dict,

    'message': 'Regulate pH using a CO2 mass flow controller to lower pH and a base pump to raise pH. '
               'When pH is above setpoint + hysteresis, CO2 flow increases. When pH is below setpoint - hysteresis, '
               'base solution is dosed. Includes tracking of total CO2 flow and base volume dispensed. '
               'Logs CO2 flow rate and base dosing events to InfluxDB for graphing.',

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
            'type': 'message',
            'default_value': 'Reset tracking totals for CO2 flow and base volume dispensed.'
        },
        {
            'id': 'reset_all_totals',
            'type': 'button',
            'wait_for_return': True,
            'name': 'Reset All Totals'
        },
        {
            'id': 'reset_co2_total',
            'type': 'button',
            'wait_for_return': True,
            'name': 'Reset CO2 Flow Total'
        },
        {
            'id': 'reset_base_total',
            'type': 'button',
            'wait_for_return': True,
            'name': 'Reset Base Volume Total'
        }
    ],

    'custom_options': [
        {
            'type': 'message',
            'default_value': '<strong>Timing Settings</strong>'
        },
        {
            'id': 'period',
            'type': 'float',
            'default_value': 60,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Period (seconds)'),
            'phrase': 'How often to check pH and adjust outputs'
        },
        {
            'id': 'start_offset',
            'type': 'integer',
            'default_value': 10,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Start Offset (seconds)'),
            'phrase': 'Wait time before starting control loop'
        },
        {
            'type': 'new_line'
        },
        {
            'type': 'message',
            'default_value': '<strong>pH Measurement</strong>'
        },
        {
            'id': 'select_measurement_ph',
            'type': 'select_measurement',
            'default_value': '',
            'required': True,
            'options_select': [
                'Input',
                'Function'
            ],
            'name': 'pH Measurement',
            'phrase': 'Select the pH sensor input'
        },
        {
            'id': 'measurement_max_age_ph',
            'type': 'integer',
            'default_value': 120,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Max Age (seconds)'),
            'phrase': 'Maximum age of pH measurement before stopping'
        },
        {
            'type': 'new_line'
        },
        {
            'type': 'message',
            'default_value': '<strong>Output: CO2 for Lowering pH</strong>'
        },
        {
            'id': 'output_co2_lower',
            'type': 'select_measurement_channel',
            'default_value': '',
            'required': True,
            'options_select': [
                'Output_Channels_Measurements',
            ],
            'name': 'CO2 Mass Flow Controller',
            'phrase': 'Select the Alicat MFC output for CO2 (lowers pH)'
        },
        {
            'id': 'co2_flow_high',
            'type': 'float',
            'default_value': 50.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'CO2 High Flow Rate (mL/min)',
            'phrase': 'CO2 flow when actively lowering pH'
        },
        {
            'id': 'co2_flow_maintain',
            'type': 'float',
            'default_value': 10.0,
            'required': True,
            'name': 'CO2 Maintain Flow Rate (mL/min)',
            'phrase': 'CO2 flow when maintaining pH (can be 0)'
        },
        {
            'type': 'new_line'
        },
        {
            'type': 'message',
            'default_value': '<strong>Output: Base for Raising pH</strong>'
        },
        {
            'id': 'output_base_raise',
            'type': 'select_channel',
            'default_value': '',
            'required': True,
            'options_select': [
                'Output_Channels'
            ],
            'name': 'Base Pump Output',
            'phrase': 'Select pump output for base solution (raises pH)'
        },
        {
            'id': 'output_base_type',
            'type': 'select',
            'default_value': 'volume_ml',
            'required': True,
            'options_select': [
                ('duration_sec', 'Duration (seconds)'),
                ('volume_ml', 'Volume (ml)')
            ],
            'name': 'Base Output Type',
            'phrase': 'Duration or volume for base pump'
        },
        {
            'id': 'base_dose_amount',
            'type': 'float',
            'default_value': 1.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Base Dose Amount',
            'phrase': 'Amount to dose when raising pH (seconds or ml)'
        },
        {
            'type': 'new_line'
        },
        {
            'type': 'message',
            'default_value': '<strong>pH Control Range</strong>'
        },
        {
            'id': 'setpoint_ph',
            'type': 'float',
            'default_value': 7.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'pH Setpoint',
            'phrase': 'Target pH value'
        },
        {
            'id': 'hysteresis_ph',
            'type': 'float',
            'default_value': 0.2,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'pH Hysteresis',
            'phrase': 'Control band (+/-) around setpoint'
        }
    ]
}


class CustomModule(AbstractFunction):
    """
    pH Control using CO2 MFC and Base Pump
    """
    def __init__(self, function, testing=False):
        super().__init__(function, testing=testing, name=__name__)

        self.control = DaemonControl()
        self.timer_loop = time.time()
        
        # Timing
        self.period = None
        self.start_offset = None

        # Measurement
        self.select_measurement_ph_device_id = None
        self.select_measurement_ph_measurement_id = None
        self.measurement_max_age_ph = None

        # Outputs
        self.output_co2_lower_device_id = None
        self.output_co2_lower_measurement_id = None
        self.output_co2_lower_channel_id = None
        self.output_co2_lower_channel = None
        self.co2_flow_high = None
        self.co2_flow_maintain = None

        self.output_base_raise_device_id = None
        self.output_base_raise_channel_id = None
        self.output_base_raise_channel = None
        self.output_base_type = None
        self.base_dose_amount = None

        # Setpoints
        self.setpoint_ph = None
        self.hysteresis_ph = None
        self.range_ph = None

        # Totals tracking
        self.total_co2_flow_time = None
        self.total_base_sec = None
        self.total_base_ml = None

        # Current state
        self.current_state = None

        # Set custom options
        custom_function = db_retrieve_table_daemon(
            CustomController, unique_id=self.unique_id)
        self.setup_custom_options(
            FUNCTION_INFORMATION['custom_options'], custom_function)

        if not testing:
            self.try_initialize()

    def initialize(self):
        """Initialize the controller"""
        self.timer_loop = time.time() + self.start_offset
        
        # Calculate pH range
        self.range_ph = (
            self.setpoint_ph - self.hysteresis_ph,
            self.setpoint_ph + self.hysteresis_ph
        )

        # Get output channels
        self.output_co2_lower_channel = self.get_output_channel_from_channel_id(
            self.output_co2_lower_channel_id)
        self.output_base_raise_channel = self.get_output_channel_from_channel_id(
            self.output_base_raise_channel_id)

        # Initialize totals if not set
        if self.get_custom_option("total_co2_flow_time") is None:
            self.total_co2_flow_time = self.set_custom_option("total_co2_flow_time", 0)
        else:
            self.total_co2_flow_time = self.get_custom_option("total_co2_flow_time")

        if self.get_custom_option("total_base_sec") is None:
            self.total_base_sec = self.set_custom_option("total_base_sec", 0)
        else:
            self.total_base_sec = self.get_custom_option("total_base_sec")

        if self.get_custom_option("total_base_ml") is None:
            self.total_base_ml = self.set_custom_option("total_base_ml", 0)
        else:
            self.total_base_ml = self.get_custom_option("total_base_ml")

        self.logger.info(
            f"pH Dual Control started: Setpoint={self.setpoint_ph:.2f}, "
            f"Range={self.range_ph[0]:.2f}-{self.range_ph[1]:.2f}, "
            f"CO2 Flow: High={self.co2_flow_high} mL/min, Maintain={self.co2_flow_maintain} mL/min, "
            f"Base Dose={self.base_dose_amount} {self.output_base_type}")

    def loop(self):
        """Main control loop"""
        if self.timer_loop > time.time():
            return

        while self.timer_loop < time.time():
            self.timer_loop += self.period

        # Get latest pH measurement
        last_measurement_ph = self.get_last_measurement(
            self.select_measurement_ph_device_id,
            self.select_measurement_ph_measurement_id,
            max_age=self.measurement_max_age_ph)

        if not last_measurement_ph or last_measurement_ph[1] is None:
            self.logger.error("No pH measurement available. Stopping CO2 flow for safety.")
            self.set_co2_flow(0, "SAFETY_STOP")
            return

        current_ph = last_measurement_ph[1]

        # Control logic based on pH range
        if current_ph < self.range_ph[0]:
            # pH too low - dose base to raise it, stop CO2
            self.logger.info(
                f"pH {current_ph:.2f} < {self.range_ph[0]:.2f}. "
                f"Dosing {self.base_dose_amount} {self.output_base_type} base.")
            self.dose_base()
            self.set_co2_flow(0, "DOSING_BASE")

        elif current_ph > self.range_ph[1]:
            # pH too high - increase CO2 flow to lower it
            self.logger.info(
                f"pH {current_ph:.2f} > {self.range_ph[1]:.2f}. "
                f"Setting CO2 to {self.co2_flow_high} mL/min.")
            self.set_co2_flow(self.co2_flow_high, "LOWERING_pH")

        else:
            # pH in range - maintain with low CO2 flow
            self.logger.debug(
                f"pH {current_ph:.2f} in range {self.range_ph[0]:.2f}-{self.range_ph[1]:.2f}. "
                f"Maintaining with {self.co2_flow_maintain} mL/min CO2.")
            self.set_co2_flow(self.co2_flow_maintain, "IN_RANGE")

    def set_co2_flow(self, flow_rate, state):
        """Set CO2 MFC flow rate"""
        self.control.output_on(
            self.output_co2_lower_device_id,
            output_type='value',
            amount=flow_rate,
            output_channel=self.output_co2_lower_channel)
        
        # Track total CO2 flow time
        self.total_co2_flow_time = self.set_custom_option(
            "total_co2_flow_time",
            self.get_custom_option("total_co2_flow_time") + self.period)
        
        # Log CO2 flow rate to InfluxDB
        write_influxdb_value(
            self.unique_id,
            'ml_per_minute',
            value=flow_rate,
            measure='volume_flow_rate',
            channel=0)
        
        # Log cumulative CO2 flow time
        write_influxdb_value(
            self.unique_id,
            's',
            value=self.total_co2_flow_time,
            measure='duration',
            channel=4)
        
        if state != self.current_state:
            self.current_state = state

    def dose_base(self):
        """Dose base solution to raise pH"""
        base_type = 'vol' if self.output_base_type == 'volume_ml' else 'sec'
        
        output_on_off = threading.Thread(
            target=self.control.output_on_off,
            args=(self.output_base_raise_device_id, "on",),
            kwargs={'output_type': base_type,
                    'amount': self.base_dose_amount,
                    'output_channel': self.output_base_raise_channel})
        output_on_off.start()

        # Track totals and log to InfluxDB
        if base_type == 'sec':
            self.total_base_sec = self.set_custom_option(
                "total_base_sec",
                self.get_custom_option("total_base_sec") + self.base_dose_amount)
            
            # Log base duration dosed
            write_influxdb_value(
                self.unique_id,
                's',
                value=self.base_dose_amount,
                measure='duration',
                channel=2)
        else:
            self.total_base_ml = self.set_custom_option(
                "total_base_ml",
                self.get_custom_option("total_base_ml") + self.base_dose_amount)
            
            # Log base volume dosed
            write_influxdb_value(
                self.unique_id,
                'ml',
                value=self.base_dose_amount,
                measure='volume',
                channel=1)
            
            # Log cumulative base volume
            write_influxdb_value(
                self.unique_id,
                'ml',
                value=self.total_base_ml,
                measure='volume',
                channel=3)

    def stop_function(self):
        """Called when function is deactivated"""
        self.logger.info("pH Dual Control stopping - setting CO2 flow to 0")
        if self.output_co2_lower_channel is not None:
            self.set_co2_flow(0, "STOPPED")

    # Custom command functions
    def reset_all_totals(self, args_dict):
        """Reset all tracking totals"""
        self.total_co2_flow_time = self.set_custom_option("total_co2_flow_time", 0)
        self.total_base_sec = self.set_custom_option("total_base_sec", 0)
        self.total_base_ml = self.set_custom_option("total_base_ml", 0)
        return "All totals reset successfully"

    def reset_co2_total(self, args_dict):
        """Reset CO2 flow time total"""
        self.total_co2_flow_time = self.set_custom_option("total_co2_flow_time", 0)
        return "CO2 flow total reset successfully"

    def reset_base_total(self, args_dict):
        """Reset base dose totals"""
        self.total_base_sec = self.set_custom_option("total_base_sec", 0)
        self.total_base_ml = self.set_custom_option("total_base_ml", 0)
        return "Base dose totals reset successfully"

    def function_status(self):
        """Return status information for UI"""
        return_str = {
            'string_status': 
                f"<strong>pH Control</strong>"
                f"<br>Setpoint: {self.setpoint_ph:.2f} ± {self.hysteresis_ph:.2f}"
                f"<br>Range: {self.range_ph[0]:.2f} - {self.range_ph[1]:.2f}"
                f"<br>State: {self.current_state if self.current_state else 'Initializing'}"
                f"<br>"
                f"<br><strong>CO2 MFC (Lower pH)</strong>"
                f"<br>High Flow: {self.co2_flow_high} mL/min"
                f"<br>Maintain Flow: {self.co2_flow_maintain} mL/min"
                f"<br>Total Flow Time: {self.total_co2_flow_time:.0f} sec ({self.total_co2_flow_time/3600:.1f} hrs)"
                f"<br>"
                f"<br><strong>Base Pump (Raise pH)</strong>"
                f"<br>Dose Amount: {self.base_dose_amount} {self.output_base_type.replace('_', ' ')}"
                f"<br>Total Dispensed: {self.total_base_ml:.1f} ml / {self.total_base_sec:.1f} sec",
            'error': []
        }
        return return_str
