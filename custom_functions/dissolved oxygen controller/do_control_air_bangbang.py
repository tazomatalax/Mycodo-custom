# coding=utf-8
#
#  do_control_air_bangbang.py - Simple Bang-Bang DO Control using Air MFC
#
#  This custom function implements simple hysteretic (bang-bang) control for DO
#  by regulating air flow through an Alicat Mass Flow Controller.
#  Simpler than PID - easier to understand and tune.
#
import time

from flask_babel import lazy_gettext

from mycodo.databases.models import CustomController
from mycodo.functions.base_function import AbstractFunction
from mycodo.mycodo_client import DaemonControl
from mycodo.utils.constraints_pass import constraints_pass_positive_value
from mycodo.utils.constraints_pass import constraints_pass_positive_or_zero_value
from mycodo.utils.database import db_retrieve_table_daemon

FUNCTION_INFORMATION = {
    'function_name_unique': 'do_control_air_bangbang',
    'function_name': 'DO Control Bang-Bang (Air MFC)',
    'function_name_short': 'DO Bang-Bang Air',

    'message': 'Simple bang-bang (hysteretic) controller for dissolved oxygen using air mass flow controller. '
               'Much simpler than PID - uses high/low flow rates based on DO thresholds. '
               'When DO drops below (setpoint - hysteresis), air flow increases to high rate. '
               'When DO rises above (setpoint + hysteresis), air flow reduces to low rate. '
               'Easy to understand and tune, excellent for systems that don\'t need precise control.',

    'options_enabled': [
        'custom_options'
    ],
    'options_disabled': [
        'measurements_select',
        'measurements_configure'
    ],

    'custom_options': [
        {
            'type': 'message',
            'default_value': '<strong>Measurement Settings</strong>'
        },
        {
            'id': 'measurement',
            'type': 'select_measurement',
            'default_value': '',
            'required': True,
            'options_select': [
                'Input',
                'Function'
            ],
            'name': lazy_gettext('DO Measurement'),
            'phrase': 'Select the dissolved oxygen sensor input'
        },
        {
            'id': 'measurement_max_age',
            'type': 'integer',
            'default_value': 120,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Max Age (seconds)'),
            'phrase': 'Maximum age of DO measurement before controller stops'
        },
        {
            'type': 'new_line'
        },
        {
            'type': 'message',
            'default_value': '<strong>Output Settings</strong>'
        },
        {
            'id': 'output',
            'type': 'select_measurement_channel',
            'default_value': '',
            'required': True,
            'options_select': [
                'Output_Channels_Measurements',
            ],
            'name': lazy_gettext('Air Mass Flow Controller'),
            'phrase': 'Select the Alicat MFC output for air'
        },
        {
            'type': 'new_line'
        },
        {
            'type': 'message',
            'default_value': '<strong>Control Settings</strong>'
        },
        {
            'id': 'setpoint',
            'type': 'float',
            'default_value': 8.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('DO Setpoint (mg/L)'),
            'phrase': 'Target dissolved oxygen value to maintain'
        },
        {
            'id': 'hysteresis',
            'type': 'float',
            'default_value': 0.5,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Hysteresis (mg/L)'),
            'phrase': 'Control band (+/- around setpoint). Larger = less frequent switching'
        },
        {
            'id': 'period',
            'type': 'float',
            'default_value': 15.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Period (seconds)'),
            'phrase': 'How often to check and update the controller'
        },
        {
            'type': 'new_line'
        },
        {
            'type': 'message',
            'default_value': '<strong>Flow Rate Settings (mL/min)</strong>'
        },
        {
            'id': 'flow_high',
            'type': 'float',
            'default_value': 300.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('High Flow Rate'),
            'phrase': 'Air flow when DO is too low (actively raising)'
        },
        {
            'id': 'flow_maintain',
            'type': 'float',
            'default_value': 50.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_or_zero_value,
            'name': lazy_gettext('Maintain Flow Rate'),
            'phrase': 'Air flow when DO is within range (maintaining)'
        },
        {
            'id': 'flow_low',
            'type': 'float',
            'default_value': 0.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_or_zero_value,
            'name': lazy_gettext('Low Flow Rate'),
            'phrase': 'Air flow when DO is too high (typically 0)'
        },
        {
            'type': 'new_line'
        },
        {
            'type': 'message',
            'default_value': '<strong>Advanced Settings</strong>'
        },
        {
            'id': 'start_offset',
            'type': 'integer',
            'default_value': 10,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Start Offset (seconds)'),
            'phrase': 'Wait time before starting control loop'
        }
    ]
}


class CustomModule(AbstractFunction):
    """
    Simple Bang-Bang DO Control using Air Mass Flow Controller
    """
    def __init__(self, function, testing=False):
        super().__init__(function, testing=testing, name=__name__)

        self.timer_loop = time.time()
        self.control = DaemonControl()
        self.current_state = None  # Track: 'high', 'maintain', 'low'

        # Initialize custom options
        self.measurement_device_id = None
        self.measurement_measurement_id = None
        self.measurement_max_age = None
        self.output_device_id = None
        self.output_measurement_id = None
        self.output_channel_id = None
        self.output_channel = None
        self.setpoint = None
        self.hysteresis = None
        self.period = None
        self.flow_high = None
        self.flow_maintain = None
        self.flow_low = None
        self.start_offset = None

        # Calculated thresholds
        self.do_upper = None
        self.do_lower = None

        # Set custom options
        custom_function = db_retrieve_table_daemon(
            CustomController, unique_id=self.unique_id)
        self.setup_custom_options(
            FUNCTION_INFORMATION['custom_options'], custom_function)

        if not testing:
            self.try_initialize()

    def initialize(self):
        """Initialize the controller"""
        self.output_channel = self.get_output_channel_from_channel_id(
            self.output_channel_id)

        # Calculate control thresholds
        self.do_upper = self.setpoint + self.hysteresis
        self.do_lower = self.setpoint - self.hysteresis

        self.timer_loop = time.time() + self.start_offset
        self.current_state = None

        self.logger.info(
            "DO Bang-Bang Control (Air) started: DO Setpoint={:.2f} mg/L, Hysteresis={:.2f}, "
            "Control Range: {:.2f}-{:.2f} mg/L, Flow Rates: High={} mL/min, Maintain={} mL/min, "
            "Low={} mL/min, Period={}s".format(
                self.setpoint, self.hysteresis, self.do_lower, self.do_upper,
                self.flow_high, self.flow_maintain, self.flow_low, self.period))

    def loop(self):
        """Main control loop"""
        if self.timer_loop > time.time():
            return

        while self.timer_loop < time.time():
            self.timer_loop += self.period

        if self.output_channel is None:
            self.logger.error("Cannot run DO controller: Output channel not configured")
            return

        # Get latest DO measurement
        last_measurement = self.get_last_measurement(
            self.measurement_device_id,
            self.measurement_measurement_id,
            max_age=self.measurement_max_age)

        if not last_measurement or last_measurement[1] is None:
            self.logger.error("No DO measurement available. Stopping air flow for safety.")
            self.set_flow(0.0, "SAFETY_STOP")
            return

        current_do = last_measurement[1]
        
        # Determine desired flow based on DO thresholds
        new_state = None
        desired_flow = None

        if current_do < self.do_lower:
            # DO too low - need high air flow to raise it
            new_state = 'high'
            desired_flow = self.flow_high
        elif current_do > self.do_upper:
            # DO too high - reduce/stop air flow
            new_state = 'low'
            desired_flow = self.flow_low
        else:
            # DO within range - maintain with moderate flow
            new_state = 'maintain'
            desired_flow = self.flow_maintain

        # Only log state changes
        if new_state != self.current_state:
            self.logger.info(
                f"DO Control state change: {self.current_state} → {new_state} "
                f"(DO={current_do:.3f} mg/L, Setpoint={self.setpoint:.2f} mg/L, "
                f"Range={self.do_lower:.2f}-{self.do_upper:.2f} mg/L, "
                f"Setting flow to {desired_flow} mL/min)")
            self.current_state = new_state
        else:
            # Log current status at debug level
            self.logger.debug(
                f"DO Control: State={new_state}, DO={current_do:.3f} mg/L, "
                f"Setpoint={self.setpoint:.2f} mg/L, Flow={desired_flow} mL/min")

        # Set the flow rate
        self.set_flow(desired_flow, new_state)

    def set_flow(self, flow_rate, state):
        """Helper function to set MFC flow rate"""
        self.control.output_on(
            self.output_device_id,
            output_type='value',
            amount=flow_rate,
            output_channel=self.output_channel)

    def stop_function(self):
        """Called when function is deactivated - stop air flow"""
        self.logger.info("DO Bang-Bang Control stopping - setting air flow to 0")
        if self.output_channel is not None:
            self.set_flow(0.0, "STOPPED")
