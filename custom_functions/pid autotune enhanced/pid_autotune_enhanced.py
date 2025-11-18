# coding=utf-8
#
#  pid_autotune_v2.py - Enhanced PID Controller Autotune
#
#  Improved version with:
#  - Progress tracking via measurements
#  - Support for continuous outputs (MFC, PWM, etc.)
#  - Better convergence detection
#  - Pre-flight validation
#  - Configurable parameters
#
import math
import threading
import time
from collections import deque

from flask_babel import lazy_gettext

from mycodo.config import MYCODO_DB_PATH
from mycodo.databases.models import CustomController
from mycodo.databases.utils import session_scope
from mycodo.functions.base_function import AbstractFunction
from mycodo.mycodo_client import DaemonControl
from mycodo.utils.constraints_pass import constraints_pass_positive_value
from mycodo.utils.database import db_retrieve_table_daemon
from mycodo.utils.influx import write_influxdb_value

FUNCTION_INFORMATION = {
    'function_name_unique': 'pid_autotune_enhanced',
    'function_name': 'PID Autotune Enhanced',

    'message': 'Enhanced PID autotune with progress tracking and continuous output support. Uses relay feedback '
               'method to determine optimal PID gains. Supports both on/off outputs (heaters, pumps) and continuous '
               'outputs (mass flow controllers, PWM, valves). Tracks progress via measurements that can be graphed. '
               'Works for both raising (heating, aeration) and lowering (cooling) control scenarios. '
               'The autotune will cycle the output and measure system response to calculate Kp, Ki, and Kd gains '
               'using multiple tuning rules (Ziegler-Nichols, Tyreus-Luyben, etc.).',

    'options_disabled': [
        'measurements_select'
    ],

    'measurements_dict': {
        0: {
            'measurement': 'setpoint',
            'unit': 'none',
            'name': 'Progress'
        },
        1: {
            'measurement': 'setpoint',
            'unit': 'none', 
            'name': 'State'
        },
        2: {
            'measurement': 'duration_time',
            'unit': 's',
            'name': 'Elapsed Time'
        }
    },

    'channels_dict': {
        0: {
            'name': 'Progress (%)',
            'measurements': [0]
        },
        1: {
            'name': 'State (0=off,1=up,2=down,3=done,4=fail)',
            'measurements': [1]
        },
        2: {
            'name': 'Elapsed Time',
            'measurements': [2]
        }
    },

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
            'name': lazy_gettext('Measurement'),
            'phrase': 'Select the process variable that the output will affect (e.g., temperature, DO, pH)'
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
            'name': lazy_gettext('Output'),
            'phrase': 'Select the output that will modulate to affect the measurement'
        },
        {
            'id': 'output_type',
            'type': 'select',
            'default_value': 'on_off',
            'required': True,
            'options_select': [
                ('on_off', 'On/Off (heater, pump, relay)'),
                ('continuous', 'Continuous (MFC, PWM, valve)')
            ],
            'name': lazy_gettext('Output Type'),
            'phrase': 'Type of output control'
        },
        {
            'type': 'new_line'
        },
        {
            'type': 'message',
            'default_value': '<strong>Control Direction</strong>'
        },
        {
            'id': 'direction',
            'type': 'select',
            'default_value': 'raise',
            'required': True,
            'options_select': [
                ('raise', 'Raise (heat, aerate, alkalize)'),
                ('lower', 'Lower (cool, de-aerate, acidify)')
            ],
            'name': lazy_gettext('Direction'),
            'phrase': 'Direction the output pushes the measurement'
        },
        {
            'type': 'new_line'
        },
        {
            'type': 'message',
            'default_value': '<strong>Autotune Parameters</strong>'
        },
        {
            'id': 'setpoint',
            'type': 'float',
            'default_value': 50.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Setpoint'),
            'phrase': 'Target value the system should oscillate around (must be reachable by the output)'
        },
        {
            'id': 'period',
            'type': 'integer',
            'default_value': 30,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Sample Period (seconds)'),
            'phrase': 'How often to read measurement and update output (match your intended PID period)'
        },
        {
            'id': 'noiseband',
            'type': 'float',
            'default_value': 0.5,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Noise Band'),
            'phrase': 'Measurement deadband around setpoint - larger values = more tolerance for noise'
        },
        {
            'type': 'new_line'
        },
        {
            'type': 'message',
            'default_value': '<strong>Output Step Settings</strong><br>'
                             'For On/Off outputs: duration output stays on each cycle<br>'
                             'For Continuous outputs: the value to write (e.g., 250 mL/min for MFC)'
        },
        {
            'id': 'outstep',
            'type': 'float',
            'default_value': 10.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Output Step'),
            'phrase': 'For on/off: seconds on per period. For continuous: output value (e.g., flow rate)'
        },
        {
            'id': 'output_min',
            'type': 'float',
            'default_value': 0.0,
            'required': True,
            'name': lazy_gettext('Output Minimum'),
            'phrase': 'Minimum output value (for continuous) or 0 for on/off'
        },
        {
            'id': 'output_max',
            'type': 'float',
            'default_value': 100.0,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Output Maximum'),
            'phrase': 'Maximum output value (for continuous) or period duration for on/off'
        },
        {
            'type': 'new_line'
        },
        {
            'type': 'message',
            'default_value': '<strong>Advanced Settings</strong>'
        },
        {
            'id': 'lookback',
            'type': 'integer',
            'default_value': 60,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Lookback Window (seconds)'),
            'phrase': 'Time window for detecting peaks - should be longer than expected oscillation period'
        },
        {
            'id': 'convergence_tolerance',
            'type': 'float',
            'default_value': 0.10,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Convergence Tolerance'),
            'phrase': 'Amplitude deviation threshold for convergence (0.05-0.15 typical, lower = stricter)'
        },
        {
            'id': 'max_cycles',
            'type': 'integer',
            'default_value': 30,
            'required': True,
            'constraints_pass': constraints_pass_positive_value,
            'name': lazy_gettext('Maximum Cycles'),
            'phrase': 'Maximum peaks to collect before giving up (20-50 typical)'
        },
        {
            'id': 'preflight_test',
            'type': 'bool',
            'default_value': True,
            'required': True,
            'name': lazy_gettext('Pre-flight Test'),
            'phrase': 'Test that output affects measurement before starting autotune'
        }
    ]
}


class PIDAutotuneV2:
    """
    Enhanced PID Autotune using Relay Feedback Method
    Based on Åström-Hägglund relay method with improvements
    """
    
    STATE_OFF = 0
    STATE_RELAY_STEP_UP = 1
    STATE_RELAY_STEP_DOWN = 2
    STATE_SUCCEEDED = 3
    STATE_FAILED = 4
    
    TUNING_RULES = {
        "ziegler-nichols": [34, 40, 160],
        "tyreus-luyben": [44, 9, 126],
        "ciancone-marlin": [66, 88, 162],
        "pessen-integral": [28, 50, 133],
        "some-overshoot": [60, 40, 60],
        "no-overshoot": [100, 40, 60],
        "brewing": [2.5, 6, 380]
    }
    
    def __init__(self, setpoint, out_step, sampletime, lookback=60,
                 out_min=0, out_max=100, noiseband=0.5, 
                 convergence_tolerance=0.10, direction='raise'):
        """
        Initialize autotune
        
        Args:
            setpoint: Target value to oscillate around
            out_step: Output step magnitude
            sampletime: Sampling period in seconds
            lookback: Window for peak detection
            out_min: Minimum output value
            out_max: Maximum output value
            noiseband: Deadband around setpoint
            convergence_tolerance: Amplitude convergence threshold
            direction: 'raise' or 'lower'
        """
        self.setpoint = setpoint
        self.outputstep = out_step
        self.sampletime = sampletime
        self.noiseband = noiseband
        self.out_min = out_min
        self.out_max = out_max
        self.convergence_tolerance = convergence_tolerance
        self.direction = direction
        
        # History buffers
        maxlen = max(1, round(lookback / sampletime))
        self.inputs = deque(maxlen=maxlen)
        self.peaks = deque(maxlen=5)
        self.peak_timestamps = deque(maxlen=5)
        
        # State
        self.state = self.STATE_OFF
        self.output = 0
        self.peak_type = 0  # -1: min, +1: max
        self.peak_count = 0
        self.cycle_count = 0
        self.initial_output = 0
        
        # Results
        self.Ku = 0  # Ultimate gain
        self.Pu = 0  # Ultimate period
        self.induced_amplitude = 0
        
        # Timing
        self.start_time = time.time()
        self.last_run_timestamp = 0
        
    def run(self, input_val):
        """
        Process one measurement sample
        
        Returns:
            True if autotune complete (success or failure), False otherwise
        """
        now = time.time()
        
        # Initialize on first run
        if self.state == self.STATE_OFF:
            self._init_tuner(input_val, now)
            return False
        
        # Check if we've already finished
        if self.state in [self.STATE_SUCCEEDED, self.STATE_FAILED]:
            return True
        
        # Enforce sample time
        if (now - self.last_run_timestamp) < self.sampletime:
            return False
        
        self.last_run_timestamp = now
        self.cycle_count += 1
        
        # Check input and switch relay state if needed
        if self.direction == 'raise':
            # For raising: switch to down when above setpoint+noiseband
            if (self.state == self.STATE_RELAY_STEP_UP and 
                input_val > self.setpoint + self.noiseband):
                self.state = self.STATE_RELAY_STEP_DOWN
            # Switch to up when below setpoint-noiseband
            elif (self.state == self.STATE_RELAY_STEP_DOWN and 
                  input_val < self.setpoint - self.noiseband):
                self.state = self.STATE_RELAY_STEP_UP
        else:
            # For lowering: reversed logic
            if (self.state == self.STATE_RELAY_STEP_UP and 
                input_val < self.setpoint - self.noiseband):
                self.state = self.STATE_RELAY_STEP_DOWN
            elif (self.state == self.STATE_RELAY_STEP_DOWN and 
                  input_val > self.setpoint + self.noiseband):
                self.state = self.STATE_RELAY_STEP_UP
        
        # Set output based on state
        if self.state == self.STATE_RELAY_STEP_UP:
            self.output = self.initial_output + self.outputstep
        elif self.state == self.STATE_RELAY_STEP_DOWN:
            self.output = self.initial_output - self.outputstep
        
        # Respect output limits
        self.output = min(self.output, self.out_max)
        self.output = max(self.output, self.out_min)
        
        # Detect peaks
        is_max = True
        is_min = True
        
        for val in self.inputs:
            is_max = is_max and (input_val >= val)
            is_min = is_min and (input_val <= val)
        
        self.inputs.append(input_val)
        
        # Wait for input buffer to fill
        if len(self.inputs) < self.inputs.maxlen:
            return False
        
        # Check for inflection (peak)
        inflection = False
        if is_max:
            if self.peak_type == -1:
                inflection = True
            self.peak_type = 1
        elif is_min:
            if self.peak_type == 1:
                inflection = True
            self.peak_type = -1
        
        # Record peak
        if inflection:
            self.peak_count += 1
            self.peaks.append(input_val)
            self.peak_timestamps.append(now)
        
        # Check for convergence after collecting enough peaks
        if inflection and self.peak_count > 4:
            # Calculate induced amplitude from last 6 transitions (3 cycles)
            abs_max = max(list(self.peaks)[:-1])
            abs_min = min(list(self.peaks)[:-1])
            
            amplitude_sum = 0
            for i in range(len(self.peaks) - 2):
                amplitude_sum += abs(self.peaks[i] - self.peaks[i+1])
            
            self.induced_amplitude = amplitude_sum / (len(self.peaks) - 1)
            
            # Check convergence
            peak_range = abs_max - abs_min
            amplitude_dev = abs((0.5 * peak_range - self.induced_amplitude) / 
                              (self.induced_amplitude + 1e-9))
            
            if amplitude_dev < self.convergence_tolerance:
                # Success! Calculate gains
                self.state = self.STATE_SUCCEEDED
                self._calculate_gains()
                return True
        
        # Check for failure conditions
        if self.peak_count >= 20:  # Fallback max peaks
            self.state = self.STATE_FAILED
            self.output = 0
            return True
        
        return False
    
    def _init_tuner(self, input_val, timestamp):
        """Initialize tuner state"""
        self.peak_type = 0
        self.peak_count = 0
        self.output = 0
        self.initial_output = 0
        self.Ku = 0
        self.Pu = 0
        self.inputs.clear()
        self.peaks.clear()
        self.peak_timestamps.clear()
        self.peak_timestamps.append(timestamp)
        self.state = self.STATE_RELAY_STEP_UP
        self.last_run_timestamp = timestamp
    
    def _calculate_gains(self):
        """Calculate ultimate gain and period"""
        # Ultimate gain (Ku)
        self.Ku = 4.0 * self.outputstep / (self.induced_amplitude * math.pi)
        
        # Ultimate period (Pu) in seconds
        period1 = self.peak_timestamps[3] - self.peak_timestamps[1]
        period2 = self.peak_timestamps[4] - self.peak_timestamps[2]
        self.Pu = 0.5 * (period1 + period2)
    
    def get_pid_parameters(self, tuning_rule='ziegler-nichols'):
        """
        Calculate PID parameters using specified tuning rule
        
        Returns:
            dict with Kp, Ki, Kd
        """
        if tuning_rule not in self.TUNING_RULES:
            tuning_rule = 'ziegler-nichols'
        
        divisors = self.TUNING_RULES[tuning_rule]
        kp = self.Ku / divisors[0]
        ki = kp / (self.Pu / divisors[1])
        kd = kp * (self.Pu / divisors[2])
        
        return {'Kp': kp, 'Ki': ki, 'Kd': kd}
    
    def get_progress(self):
        """
        Calculate progress percentage
        
        Returns:
            float: 0-100 progress percentage
        """
        if self.state == self.STATE_OFF:
            return 0
        elif self.state == self.STATE_SUCCEEDED:
            return 100
        elif self.state == self.STATE_FAILED:
            return 0
        else:
            # Estimate based on peak count (need at least 5 peaks)
            return min(95, (self.peak_count / 5.0) * 100)


class CustomModule(AbstractFunction):
    """
    Enhanced PID Autotune Function
    """
    def __init__(self, function, testing=False):
        super().__init__(function, testing=testing, name=__name__)

        self.autotune = None
        self.control = DaemonControl()
        self.timer_loop = None

        # Initialize custom options
        self.measurement_device_id = None
        self.measurement_measurement_id = None
        self.output_device_id = None
        self.output_measurement_id = None
        self.output_channel_id = None
        self.output_type = None
        self.direction = None
        self.setpoint = None
        self.period = None
        self.noiseband = None
        self.outstep = None
        self.output_min = None
        self.output_max = None
        self.lookback = None
        self.convergence_tolerance = None
        self.max_cycles = None
        self.preflight_test = None

        self.output_channel = None
        self.start_time = None
        self.last_progress = 0

        # Set custom options
        custom_function = db_retrieve_table_daemon(
            CustomController, unique_id=self.unique_id)
        self.setup_custom_options(
            FUNCTION_INFORMATION['custom_options'], custom_function)

        self.output_channel = self.get_output_channel_from_channel_id(
            self.output_channel_id)

        if not testing:
            self.try_initialize()

    def initialize(self):
        """Initialize autotune"""
        self.start_time = time.time()
        
        # Create autotune instance
        self.autotune = PIDAutotuneV2(
            setpoint=self.setpoint,
            out_step=self.outstep,
            sampletime=self.period,
            lookback=self.lookback,
            out_min=self.output_min,
            out_max=self.output_max,
            noiseband=self.noiseband,
            convergence_tolerance=self.convergence_tolerance,
            direction=self.direction
        )
        
        self.timer_loop = time.time()
        self.running = True
        
        self.logger.info(
            "PID Autotune v2 started: Measurement={}, Output={} ({}), Setpoint={}, "
            "Period={}s, Noiseband={}, Outstep={}, Direction={}, Convergence={}".format(
                self.measurement_device_id,
                self.output_device_id,
                self.output_type,
                self.setpoint,
                self.period,
                self.noiseband,
                self.outstep,
                self.direction,
                self.convergence_tolerance))
        
        # Optionally run pre-flight test
        if self.preflight_test:
            self._run_preflight_test()

    def _run_preflight_test(self):
        """Test that output affects measurement"""
        self.logger.info("Running pre-flight test...")
        
        # Get baseline measurement
        baseline = self.get_last_measurement(
            self.measurement_device_id,
            self.measurement_measurement_id)
        
        if not baseline or baseline[1] is None:
            self.logger.warning("Pre-flight: No baseline measurement available")
            return
        
        baseline_val = baseline[1]
        
        # Apply output briefly
        test_duration = min(self.period * 2, 60)  # 2 periods or 60s max
        self.logger.info(
            f"Pre-flight: Baseline={baseline_val:.2f}, testing output for {test_duration}s")
        
        self._apply_output(self.outstep)
        time.sleep(test_duration)
        
        # Check if measurement changed
        test_measurement = self.get_last_measurement(
            self.measurement_device_id,
            self.measurement_measurement_id)
        
        self._apply_output(0)  # Turn off
        
        if test_measurement and test_measurement[1] is not None:
            change = test_measurement[1] - baseline_val
            self.logger.info(
                f"Pre-flight: After test={test_measurement[1]:.2f}, "
                f"Change={change:.2f}")
            
            expected_direction = change > 0 if self.direction == 'raise' else change < 0
            if abs(change) < self.noiseband * 0.5:
                self.logger.warning(
                    "Pre-flight: Small change detected. Output may be weak or "
                    "measurement unresponsive. Consider increasing outstep.")
            elif not expected_direction:
                self.logger.warning(
                    f"Pre-flight: Change direction unexpected! Direction={self.direction}, "
                    f"but measurement {'increased' if change > 0 else 'decreased'}")

    def loop(self):
        """Main autotune loop"""
        if self.timer_loop > time.time():
            return

        while time.time() > self.timer_loop:
            self.timer_loop += self.period

        if self.output_channel is None:
            self.logger.error("Cannot run autotune: Output channel not found")
            self.deactivate_self()
            return

        # Get current measurement
        last_measurement = self.get_last_measurement(
            self.measurement_device_id,
            self.measurement_measurement_id)

        if not last_measurement or last_measurement[1] is None:
            self.logger.error("No measurement available")
            return

        current_value = last_measurement[1]
        
        # Run autotune step
        is_complete = self.autotune.run(current_value)
        
        # Apply output
        self._apply_output(self.autotune.output)
        
        # Update progress measurements
        self._update_progress()
        
        # Log status
        if self.autotune.cycle_count % 5 == 0:  # Log every 5 cycles
            self.logger.info(
                f"Cycle {self.autotune.cycle_count}: Value={current_value:.3f}, "
                f"State={self.autotune.state}, Peaks={self.autotune.peak_count}, "
                f"Output={self.autotune.output:.2f}, Progress={self.autotune.get_progress():.1f}%")
        
        # Handle completion
        if is_complete:
            self._handle_completion()

    def _apply_output(self, value):
        """Apply output value based on output type"""
        if self.output_type == 'on_off':
            # On/Off output: value is duration in seconds
            if value > 0:
                self.control.output_on(
                    self.output_device_id,
                    output_type='sec',
                    amount=value,
                    output_channel=self.output_channel)
            else:
                self.control.output_off(
                    self.output_device_id,
                    output_channel=self.output_channel)
        else:
            # Continuous output: value is the setpoint
            self.control.output_on(
                self.output_device_id,
                output_type='value',
                amount=value,
                output_channel=self.output_channel)

    def _update_progress(self):
        """Write progress measurements to database"""
        elapsed = time.time() - self.start_time
        progress = self.autotune.get_progress()
        state = self.autotune.state
        
        # Only update if progress changed significantly
        if abs(progress - self.last_progress) >= 5 or state >= self.autotune.STATE_SUCCEEDED:
            # Progress percentage (channel 0)
            write_influxdb_value(
                self.unique_id,
                'setpoint',
                progress,
                channel=0)
            
            # State (channel 1)
            write_influxdb_value(
                self.unique_id,
                'setpoint',
                state,
                channel=1)
            
            # Elapsed time (channel 2)
            write_influxdb_value(
                self.unique_id,
                'duration_time',
                elapsed,
                channel=2)
            
            self.last_progress = progress

    def _handle_completion(self):
        """Handle autotune completion"""
        elapsed = time.time() - self.start_time
        
        self.logger.info("")
        self.logger.info("=" * 60)
        self.logger.info("PID AUTOTUNE COMPLETE")
        self.logger.info("=" * 60)
        self.logger.info(f"Duration: {elapsed/60:.1f} minutes ({self.autotune.cycle_count} cycles)")
        self.logger.info(f"Peaks detected: {self.autotune.peak_count}")
        self.logger.info(f"State: {self.autotune.state}")
        
        if self.autotune.state == PIDAutotuneV2.STATE_SUCCEEDED:
            self.logger.info("")
            self.logger.info("SUCCESS! Calculated PID Parameters:")
            self.logger.info("-" * 60)
            self.logger.info(f"Ultimate Gain (Ku): {self.autotune.Ku:.4f}")
            self.logger.info(f"Ultimate Period (Pu): {self.autotune.Pu:.2f} seconds")
            self.logger.info(f"Induced Amplitude: {self.autotune.induced_amplitude:.4f}")
            self.logger.info("")
            
            # Log all tuning rules
            for rule_name in PIDAutotuneV2.TUNING_RULES.keys():
                params = self.autotune.get_pid_parameters(rule_name)
                self.logger.info(f"{rule_name:20s} -> Kp={params['Kp']:8.4f}  "
                               f"Ki={params['Ki']:8.4f}  Kd={params['Kd']:8.4f}")
            
            self.logger.info("-" * 60)
            self.logger.info("RECOMMENDED: Start with 'ziegler-nichols' or 'tyreus-luyben'")
            self.logger.info("For less overshoot, try 'no-overshoot' or 'some-overshoot'")
        else:
            self.logger.error("")
            self.logger.error("AUTOTUNE FAILED")
            self.logger.error("Possible reasons:")
            self.logger.error("  - Output too weak to reach setpoint")
            self.logger.error("  - Too much noise or external disturbances")
            self.logger.error("  - Setpoint unreachable with current output")
            self.logger.error("  - System too slow (increase max_cycles or lookback)")
            self.logger.error("  - Noiseband too small for system noise level")
        
        self.logger.info("=" * 60)
        
        # Turn off output
        self._apply_output(0)
        
        # Update final progress
        self._update_progress()
        
        # Deactivate
        self.deactivate_self()

    def deactivate_self(self):
        """Deactivate this function"""
        self.logger.info("Deactivating PID Autotune v2")
        
        # Ensure output is off
        if self.output_channel is not None:
            self._apply_output(0)
        
        # Update database
        with session_scope(MYCODO_DB_PATH) as new_session:
            mod_cont = new_session.query(CustomController).filter(
                CustomController.unique_id == self.unique_id).first()
            if mod_cont:
                mod_cont.is_activated = False
                new_session.commit()

        # Deactivate in separate thread
        deactivate_controller = threading.Thread(
            target=self.control.controller_deactivate,
            args=(self.unique_id,))
        deactivate_controller.start()

    def stop_function(self):
        """Called when function is stopped"""
        self.logger.info("PID Autotune v2 stopped")
        if self.output_channel is not None:
            self._apply_output(0)
        self.running = False
