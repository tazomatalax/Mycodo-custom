# coding=utf-8
#
#  ph_control_co2_mfc.py - pH Control using CO2 Mass Flow Controller
#
#  This custom function implements PID control for maintaining pH setpoint
#  by regulating CO2 flow through an Alicat Mass Flow Controller.
#
import time

from flask_babel import lazy_gettext

from mycodo.databases.models import CustomController
from mycodo.functions.base_function import AbstractFunction
from mycodo.mycodo_client import DaemonControl
from mycodo.utils.constraints_pass import constraints_pass_positive_value
from mycodo.utils.database import db_retrieve_table_daemon
from mycodo.utils.pid_controller_default import PIDControl

FUNCTION_INFORMATION = {
    'function_name_unique': 'ph_control_co2_mfc',
    'function_name': 'pH Control (CO2 MFC)',
    'function_name_short': 'pH Control CO2',

    'message': 'PID controller for maintaining pH setpoint by regulating CO2 flow through a mass flow controller. '
               'The controller lowers pH by increasing CO2 flow. Includes configurable min/max flow limits to '
               'prevent over-dosing and ensure safe operation. Select a pH input, a mass flow controller output, '
               'and configure PID gains and flow limits.',

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
            'name': lazy_gettext('pH Measurement'),
            'phrase': 'Select the pH sensor input'
        },
        {
            'id': 'measurement_max_age',
            'type': 'integer',
            'default_value': 120,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Max Age (seconds)'),
            'phrase': 'Maximum age of pH measurement before controller stops'
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
            'name': lazy_gettext('CO2 Mass Flow Controller'),
            'phrase': 'Select the Alicat MFC output for CO2'
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
            'default_value': 7.0,
            'required': True,
            'name': lazy_gettext('pH Setpoint'),
            'phrase': 'Target pH value to maintain'
        },
        {
            'id': 'period',
            'type': 'float',
            'default_value': 30.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Period (seconds)'),
            'phrase': 'How often to update the controller'
        },
        {
            'type': 'new_line'
        },
        {
            'type': 'message',
            'default_value': '<strong>PID Gains</strong>'
        },
        {
            'id': 'kp',
            'type': 'float',
            'default_value': 1.0,
            'required': True,
            'name': lazy_gettext('Kp (Proportional Gain)'),
            'phrase': 'Proportional gain - higher values = stronger response to error'
        },
        {
            'id': 'ki',
            'type': 'float',
            'default_value': 0.1,
            'required': True,
            'name': lazy_gettext('Ki (Integral Gain)'),
            'phrase': 'Integral gain - eliminates steady-state error over time'
        },
        {
            'id': 'kd',
            'type': 'float',
            'default_value': 0.05,
            'required': True,
            'name': lazy_gettext('Kd (Derivative Gain)'),
            'phrase': 'Derivative gain - dampens oscillations and overshoots'
        },
        {
            'type': 'new_line'
        },
        {
            'type': 'message',
            'default_value': '<strong>Flow Limits (mL/min)</strong>'
        },
        {
            'id': 'min_flow',
            'type': 'float',
            'default_value': 0.0,
            'required': True,
            'name': lazy_gettext('Minimum CO2 Flow'),
            'phrase': 'Minimum flow rate in mL/min (typically 0)'
        },
        {
            'id': 'max_flow',
            'type': 'float',
            'default_value': 100.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Maximum CO2 Flow'),
            'phrase': 'Maximum safe flow rate in mL/min'
        },
        {
            'type': 'new_line'
        },
        {
            'type': 'message',
            'default_value': '<strong>Advanced Settings</strong>'
        },
        {
            'id': 'direction',
            'type': 'select',
            'default_value': 'lower',
            'required': True,
            'options_select': [
                ('lower', 'Lower (CO2 decreases pH)'),
                ('raise', 'Raise (unlikely for CO2)')
            ],
            'name': lazy_gettext('Direction'),
            'phrase': 'Direction of control - CO2 normally lowers pH'
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
    pH Control using CO2 Mass Flow Controller
    """
    def __init__(self, function, testing=False):
        super().__init__(function, testing=testing, name=__name__)

        self.timer_loop = time.time()
        self.control = DaemonControl()
        self.pid_controller = None

        # Initialize custom options
        self.measurement_device_id = None
        self.measurement_measurement_id = None
        self.measurement_max_age = None
        self.output_device_id = None
        self.output_measurement_id = None
        self.output_channel_id = None
        self.output_channel = None
        self.setpoint = None
        self.period = None
        self.kp = None
        self.ki = None
        self.kd = None
        self.min_flow = None
        self.max_flow = None
        self.direction = None
        self.start_offset = None

        # Set custom options
        custom_function = db_retrieve_table_daemon(
            CustomController, unique_id=self.unique_id)
        self.setup_custom_options(
            FUNCTION_INFORMATION['custom_options'], custom_function)

        if not testing:
            self.try_initialize()

    def initialize(self):
        """Initialize the PID controller"""
        self.output_channel = self.get_output_channel_from_channel_id(
            self.output_channel_id)

        # Initialize PID controller using Mycodo's built-in PIDControl
        # For lowering pH with CO2, we want PID to output positive values when pH > setpoint
        if self.direction == 'lower':
            # Reverse mode: negate gains so output increases when measurement is above setpoint
            self.pid_controller = PIDControl(
                self.logger, self.setpoint, -self.kp, -self.ki, -self.kd,
                direction='lower',
                band=0,
                integrator_min=self.min_flow,
                integrator_max=self.max_flow
            )
        else:
            # Direct mode: output increases when measurement is below setpoint
            self.pid_controller = PIDControl(
                self.logger, self.setpoint, self.kp, self.ki, self.kd,
                direction='raise',
                band=0,
                integrator_min=self.min_flow,
                integrator_max=self.max_flow
            )

        self.timer_loop = time.time() + self.start_offset

        self.logger.info(
            "pH Control (CO2) started: pH Setpoint={:.2f}, Kp={}, Ki={}, Kd={}, "
            "Flow Limits: {}-{} mL/min, Period={}s, Direction={}".format(
                self.setpoint, self.kp, self.ki, self.kd,
                self.min_flow, self.max_flow, self.period, self.direction))

    def loop(self):
        """Main control loop"""
        if self.timer_loop > time.time():
            return

        while self.timer_loop < time.time():
            self.timer_loop += self.period

        if self.output_channel is None:
            self.logger.error("Cannot run pH controller: Output channel not configured")
            return

        # Get latest pH measurement
        last_measurement = self.get_last_measurement(
            self.measurement_device_id,
            self.measurement_measurement_id,
            max_age=self.measurement_max_age)

        if not last_measurement or last_measurement[1] is None:
            self.logger.error("No pH measurement available. Stopping CO2 flow for safety.")
            self.control.output_on(
                self.output_device_id,
                output_type='value',
                amount=0.0,
                output_channel=self.output_channel)
            return

        current_ph = last_measurement[1]
        
        # Calculate PID output
        self.pid_controller.update_pid_output(current_ph)
        co2_flow = self.pid_controller.control_variable

        # Ensure flow is within bounds
        co2_flow = max(self.min_flow, min(self.max_flow, co2_flow))

        # Send flow setpoint to MFC
        self.control.output_on(
            self.output_device_id,
            output_type='value',
            amount=co2_flow,
            output_channel=self.output_channel)

        # Get PID components for logging
        p = self.pid_controller.P_value if self.pid_controller.P_value else 0
        i = self.pid_controller.I_value if self.pid_controller.I_value else 0
        d = self.pid_controller.D_value if self.pid_controller.D_value else 0

        self.logger.debug(
            f"pH Control: Current={current_ph:.3f}, Setpoint={self.setpoint:.3f}, "
            f"Error={current_ph - self.setpoint:.3f}, CO2 Flow={co2_flow:.2f} mL/min, "
            f"PID(P={p:.2f}, I={i:.2f}, D={d:.2f})")

    def stop_function(self):
        """Called when function is deactivated - stop CO2 flow"""
        self.logger.info("pH Control stopping - setting CO2 flow to 0")
        if self.output_channel is not None:
            self.control.output_on(
                self.output_device_id,
                output_type='value',
                amount=0.0,
                output_channel=self.output_channel)
