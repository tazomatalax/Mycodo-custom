# coding=utf-8
#
#  do_control_air_mfc.py - Dissolved Oxygen Control using Air Mass Flow Controller
#
#  This custom function implements PID control for maintaining DO setpoint
#  by regulating air flow through an Alicat Mass Flow Controller.
#
import time

from flask_babel import lazy_gettext

from mycodo.databases.models import CustomController
from mycodo.functions.base_function import AbstractFunction
from mycodo.mycodo_client import DaemonControl
from mycodo.utils.constraints_pass import constraints_pass_positive_value
from mycodo.utils.database import db_retrieve_table_daemon
from mycodo.utils.influx import write_influxdb_value
from mycodo.utils.pid_controller_default import PIDControl

# Measurement channels for InfluxDB logging
measurements_dict = {
    0: {
        'measurement': 'volume_flow_rate',
        'unit': 'ml_per_minute',
        'name': 'Air Flow Rate'
    },
    1: {
        'measurement': 'pid_p_value',
        'unit': 'unitless',
        'name': 'PID P Value'
    },
    2: {
        'measurement': 'pid_i_value',
        'unit': 'unitless',
        'name': 'PID I Value'
    },
    3: {
        'measurement': 'pid_d_value',
        'unit': 'unitless',
        'name': 'PID D Value'
    },
    4: {
        'measurement': 'setpoint',
        'unit': 'percent',
        'name': 'DO Setpoint'
    }
}

FUNCTION_INFORMATION = {
    'function_name_unique': 'do_control_air_mfc',
    'function_name': 'DO Control (Air MFC)',
    'function_name_short': 'DO Control Air',
    'measurements_dict': measurements_dict,

    'message': 'PID controller for maintaining dissolved oxygen (DO) setpoint by regulating air flow through a '
               'mass flow controller. The controller raises DO by increasing air flow. Includes configurable '
               'min/max flow limits to prevent over-aeration and ensure safe operation. Select a DO input, '
               'a mass flow controller output, and configure PID gains and flow limits. '
               'Logs air flow rate and PID values to InfluxDB for graphing.',

    'options_enabled': [
        'custom_options',
        'function_status'
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
            'name': lazy_gettext('DO Setpoint (%)'),
            'phrase': 'Target dissolved oxygen value to maintain'
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
            'default_value': 10.0,
            'required': True,
            'name': lazy_gettext('Kp (Proportional Gain)'),
            'phrase': 'Proportional gain - higher values = stronger response to error'
        },
        {
            'id': 'ki',
            'type': 'float',
            'default_value': 0.5,
            'required': True,
            'name': lazy_gettext('Ki (Integral Gain)'),
            'phrase': 'Integral gain - eliminates steady-state error over time'
        },
        {
            'id': 'kd',
            'type': 'float',
            'default_value': 0.1,
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
            'name': lazy_gettext('Minimum Air Flow'),
            'phrase': 'Minimum flow rate in mL/min (typically 0)'
        },
        {
            'id': 'max_flow',
            'type': 'float',
            'default_value': 500.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Maximum Air Flow'),
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
            'default_value': 'raise',
            'required': True,
            'options_select': [
                ('raise', 'Raise (Air increases DO)'),
                ('lower', 'Lower (unlikely for air)')
            ],
            'name': lazy_gettext('Direction'),
            'phrase': 'Direction of control - air normally raises DO'
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
    Dissolved Oxygen Control using Air Mass Flow Controller
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
        # For raising DO with air, we want PID to output positive values when DO < setpoint
        if self.direction == 'raise':
            # Direct mode: output increases when measurement is below setpoint
            self.pid_controller = PIDControl(
                self.logger, self.setpoint, self.kp, self.ki, self.kd,
                direction='raise',
                band=0,
                integrator_min=self.min_flow,
                integrator_max=self.max_flow
            )
        else:
            # Reverse mode: negate gains so output increases when measurement is above setpoint
            self.pid_controller = PIDControl(
                self.logger, self.setpoint, -self.kp, -self.ki, -self.kd,
                direction='lower',
                band=0,
                integrator_min=self.min_flow,
                integrator_max=self.max_flow
            )

        self.timer_loop = time.time() + self.start_offset

        self.logger.info(
            "DO Control (Air) started: DO Setpoint={:.2f} %, Kp={}, Ki={}, Kd={}, "
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
            self.logger.error("Cannot run DO controller: Output channel not configured")
            return

        # Get latest DO measurement
        last_measurement = self.get_last_measurement(
            self.measurement_device_id,
            self.measurement_measurement_id,
            max_age=self.measurement_max_age)

        if not last_measurement or last_measurement[1] is None:
            self.logger.error("No DO measurement available. Stopping air flow for safety.")
            self.control.output_on(
                self.output_device_id,
                output_type='value',
                amount=0.0,
                output_channel=self.output_channel)
            return

        current_do = last_measurement[1]
        
        # Calculate PID output
        self.pid_controller.update_pid_output(current_do)
        air_flow = self.pid_controller.control_variable

        # Ensure flow is within bounds
        air_flow = max(self.min_flow, min(self.max_flow, air_flow))

        # Send flow setpoint to MFC
        self.control.output_on(
            self.output_device_id,
            output_type='value',
            amount=air_flow,
            output_channel=self.output_channel)

        # Get PID components for logging
        p = self.pid_controller.P_value if self.pid_controller.P_value else 0
        i = self.pid_controller.I_value if self.pid_controller.I_value else 0
        d = self.pid_controller.D_value if self.pid_controller.D_value else 0

        # Store current values for status display
        self.current_do = current_do
        self.current_flow = air_flow
        self.current_p = p
        self.current_i = i
        self.current_d = d

        # Log to InfluxDB for graphing
        write_influxdb_value(
            self.unique_id,
            'ml_per_minute',
            value=air_flow,
            measure='volume_flow_rate',
            channel=0)
        
        write_influxdb_value(
            self.unique_id,
            'unitless',
            value=p,
            measure='pid_p_value',
            channel=1)
        
        write_influxdb_value(
            self.unique_id,
            'unitless',
            value=i,
            measure='pid_i_value',
            channel=2)
        
        write_influxdb_value(
            self.unique_id,
            'unitless',
            value=d,
            measure='pid_d_value',
            channel=3)
        
        write_influxdb_value(
            self.unique_id,
            'percent',
            value=self.setpoint,
            measure='setpoint',
            channel=4)

        self.logger.debug(
            f"DO Control: Current={current_do:.3f} %, Setpoint={self.setpoint:.3f} %, "
            f"Error={current_do - self.setpoint:.3f}, Air Flow={air_flow:.2f} mL/min, "
            f"PID(P={p:.2f}, I={i:.2f}, D={d:.2f})")

    def stop_function(self):
        """Called when function is deactivated - stop air flow"""
        self.logger.info("DO Control stopping - setting air flow to 0")
        if self.output_channel is not None:
            self.control.output_on(
                self.output_device_id,
                output_type='value',
                amount=0.0,
                output_channel=self.output_channel)

    def function_status(self):
        """Return status information for the UI"""
        current_do = getattr(self, 'current_do', None)
        current_flow = getattr(self, 'current_flow', None)
        current_p = getattr(self, 'current_p', 0)
        current_i = getattr(self, 'current_i', 0)
        current_d = getattr(self, 'current_d', 0)
        
        if current_do is not None and current_flow is not None:
            status_str = (
                f"<strong>DO Control Status</strong>"
                f"<br>Current DO: {current_do:.2f} %"
                f"<br>Setpoint: {self.setpoint:.2f} %"
                f"<br>Error: {current_do - self.setpoint:.3f}"
                f"<br>"
                f"<br><strong>Air Flow</strong>"
                f"<br>Current: {current_flow:.1f} mL/min"
                f"<br>Limits: {self.min_flow:.1f} - {self.max_flow:.1f} mL/min"
                f"<br>"
                f"<br><strong>PID Values</strong>"
                f"<br>P: {current_p:.3f}"
                f"<br>I: {current_i:.3f}"
                f"<br>D: {current_d:.3f}"
                f"<br>Gains: Kp={self.kp}, Ki={self.ki}, Kd={self.kd}"
            )
        else:
            status_str = "<strong>DO Control Status</strong><br>Initializing..."
        
        return {'string_status': status_str, 'error': []}
