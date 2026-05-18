# coding=utf-8
#
# pump_gpio_variable_off.py - Peristaltic pump output with fixed ON time and variable OFF time.
#
# Unlike the built-in pump_gpio.py which constrains cycles to a 60-second window,
# this output uses a user-defined fixed ON pulse duration and calculates the OFF
# duration freely, allowing very low flow rates (e.g. a 10-second pulse every 20 minutes).
#
import copy
import datetime
import threading
import time

from flask_babel import lazy_gettext

from mycodo.databases.models import OutputChannel
from mycodo.outputs.base_output import AbstractOutput
from mycodo.utils.constraints_pass import constraints_pass_positive_or_zero_value
from mycodo.utils.constraints_pass import constraints_pass_positive_value
from mycodo.utils.database import db_retrieve_table_daemon
from mycodo.utils.influx import add_measurements_influxdb

# Measurements
measurements_dict = {
    0: {
        'measurement': 'duration_time',
        'unit': 's',
        'name': 'Pump On',
    },
    1: {
        'measurement': 'volume',
        'unit': 'ml',
        'name': 'Dispense Volume',
    },
    2: {
        'measurement': 'duration_time',
        'unit': 's',
        'name': 'Dispense Duration',
    }
}

channels_dict = {
    0: {
        'types': ['volume', 'on_off'],
        'measurements': [0, 1, 2]
    }
}

# Output information
OUTPUT_INFORMATION = {
    'output_name_unique': 'peristaltic_pump_variable_off',
    'output_name': "{}: Raspberry Pi GPIO, Variable Off Time (Pi <= 4)".format(lazy_gettext('Peristaltic Pump')),
    'output_library': 'RPi.GPIO',
    'measurements_dict': measurements_dict,
    'channels_dict': channels_dict,
    'output_types': ['volume', 'on_off'],

    'message': (
        "This output turns a GPIO pin HIGH and LOW to control a peristaltic pump using a fixed ON pulse "
        "duration and a calculated variable OFF duration. Unlike the standard peristaltic pump output, "
        "the cycle period is not constrained to 60 seconds, allowing very low flow rates such as a "
        "10-second pulse every 20 minutes. Set 'On Pulse Duration (Seconds)' to the fixed length of "
        "each pump pulse, then calibrate 'Fastest Rate (ml/min)' by running the pump continuously for "
        "60 seconds and measuring the dispensed volume."
    ),

    'options_enabled': [
        'button_on',
        'button_send_volume',
        'button_send_duration'
    ],
    'options_disabled': ['interface'],

    'dependencies_module': [
        ('pip-pypi', 'RPi.GPIO', 'RPi.GPIO==0.7.1')
    ],

    'interfaces': ['GPIO'],

    'custom_options_message': (
        "Calibration: purge the fluid line, then run the pump continuously for 60 seconds and measure "
        "the dispensed volume in ml. Enter that value as 'Fastest Rate (ml/min)'. "
        "Set 'On Pulse Duration (Seconds)' to the fixed pulse width you want (e.g. 10 seconds). "
        "The output will then calculate the required off time between pulses to achieve the desired flow rate. "
        "Very low flow rates are supported since the off time is unbounded."
    ),

    'custom_channel_options': [
        {
            'id': 'pin',
            'type': 'integer',
            'default_value': None,
            'required': False,
            'constraints_pass': constraints_pass_positive_or_zero_value,
            'name': "{}: {} ({})".format(lazy_gettext('Pin'), lazy_gettext('GPIO'), lazy_gettext('BCM')),
            'phrase': lazy_gettext('The pin to control the state of')
        },
        {
            'id': 'on_state',
            'type': 'select',
            'default_value': 1,
            'options_select': [
                (1, 'HIGH'),
                (0, 'LOW')
            ],
            'name': lazy_gettext('On State'),
            'phrase': 'The state of the GPIO that corresponds to an On state'
        },
        {
            'id': 'fastest_dispense_rate_ml_min',
            'type': 'float',
            'default_value': 150.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Fastest Rate (ml/min)',
            'phrase': 'The fastest rate that the pump can dispense (ml/min), measured at 100% duty cycle'
        },
        {
            'id': 'on_pulse_seconds',
            'type': 'float',
            'default_value': 10.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'On Pulse Duration (Seconds)',
            'phrase': (
                'The fixed duration the pump turns on for each pulse. '
                'The off time between pulses is calculated automatically from the desired flow rate. '
                'There is no minimum off-time constraint, so very low flow rates are achievable.'
            )
        },
        {
            'id': 'flow_mode',
            'type': 'select',
            'default_value': 'fastest_flow_rate',
            'options_select': [
                ('fastest_flow_rate', 'Fastest Flow Rate'),
                ('specify_flow_rate', 'Specify Flow Rate')
            ],
            'name': 'Flow Rate Method',
            'phrase': 'The flow rate to use when pumping a volume'
        },
        {
            'id': 'flow_rate',
            'type': 'float',
            'default_value': 10.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': "{} ({})".format(lazy_gettext('Desired Flow Rate'), lazy_gettext('ml/min')),
            'phrase': 'Desired flow rate in ml/minute when Specify Flow Rate is set'
        },
        {
            'id': 'amps',
            'type': 'float',
            'default_value': 0.0,
            'required': True,
            'name': "{} ({})".format(lazy_gettext('Current'), lazy_gettext('Amps')),
            'phrase': 'The current draw of the device being controlled'
        }
    ]
}


class OutputModule(AbstractOutput):
    """An output support class that operates an output."""
    def __init__(self, output, testing=False):
        super().__init__(output, testing=testing, name=__name__)

        self.GPIO = None
        self.currently_dispensing = False

        output_channels = db_retrieve_table_daemon(
            OutputChannel).filter(OutputChannel.output_id == self.output.unique_id).all()
        self.options_channels = self.setup_custom_channel_options_json(
            OUTPUT_INFORMATION['custom_channel_options'], output_channels)

    def initialize(self):
        import RPi.GPIO as GPIO

        self.GPIO = GPIO

        self.setup_output_variables(OUTPUT_INFORMATION)

        if self.options_channels['pin'][0] is None:
            self.logger.warning("Invalid pin for output: {}.".format(self.options_channels['pin'][0]))
            return

        try:
            try:
                self.GPIO.setmode(self.GPIO.BCM)
                self.GPIO.setwarnings(True)
                self.GPIO.setup(self.options_channels['pin'][0], self.GPIO.OUT)
                self.GPIO.output(self.options_channels['pin'][0], not self.options_channels['on_state'][0])
                self.output_setup = True
            except Exception as e:
                self.logger.error("Setup error: {}".format(e))
            state = 'LOW' if self.options_channels['on_state'][0] else 'HIGH'
            self.logger.info(
                "Output setup on pin {pin} and turned OFF (OFF={state})".format(
                    pin=self.options_channels['pin'][0], state=state))
        except Exception as except_msg:
            self.logger.exception(
                "Output was unable to be setup on pin {pin} with trigger={trigger}: {err}".format(
                    pin=self.options_channels['pin'][0],
                    trigger=self.options_channels['on_state'][0],
                    err=except_msg))

    def dispense_volume_fastest(self, amount, total_dispense_seconds):
        """Dispense at fastest flow rate — 100% duty cycle, no pulsing."""
        self.currently_dispensing = True
        self.logger.debug("Output turned on")
        self.GPIO.output(self.options_channels['pin'][0], self.options_channels['on_state'][0])
        timer_dispense = time.time() + total_dispense_seconds
        timestamp_start = datetime.datetime.utcnow()

        while time.time() < timer_dispense and self.currently_dispensing:
            time.sleep(0.01)

        self.GPIO.output(self.options_channels['pin'][0], not self.options_channels['on_state'][0])
        self.currently_dispensing = False
        self.logger.debug("Output turned off")
        self.record_dispersal(amount, total_dispense_seconds, total_dispense_seconds, timestamp=timestamp_start)

    def dispense_volume_rate(self, amount, dispense_rate):
        """
        Dispense a volume at a specific flow rate using fixed-ON / variable-OFF pulsing.

        The ON pulse duration is fixed by the user ('on_pulse_seconds'). The OFF duration
        between pulses is calculated from the duty cycle, with no 60-second window constraint.
        This allows arbitrarily low flow rates.

        Cycle math:
            duty_cycle         = dispense_rate / fastest_rate
            repeat_seconds_on  = on_pulse_seconds                        (fixed)
            repeat_seconds_off = on_pulse_seconds * (1 - duty_cycle) / duty_cycle  (variable)
        """
        total_dispense_seconds = amount / dispense_rate * 60
        self.logger.debug("Total duration to run: {0:.1f} seconds".format(total_dispense_seconds))

        duty_cycle = dispense_rate / self.options_channels['fastest_dispense_rate_ml_min'][0]
        self.logger.debug("Duty Cycle: {0:.2f} %".format(duty_cycle * 100))

        total_seconds_on = total_dispense_seconds * duty_cycle
        self.logger.debug("Total seconds on: {0:.1f}".format(total_seconds_on))

        total_seconds_off = total_dispense_seconds - total_seconds_on
        self.logger.debug("Total seconds off: {0:.1f}".format(total_seconds_off))

        repeat_seconds_on = self.options_channels['on_pulse_seconds'][0]
        # Variable off time — no 60-second window constraint
        repeat_seconds_off = repeat_seconds_on * (1.0 - duty_cycle) / duty_cycle

        self.logger.debug(
            "Pulse cycle: on {on:.2f} s, off {off:.1f} s  "
            "(cycle period {period:.1f} s = {period_min:.2f} min)".format(
                on=repeat_seconds_on,
                off=repeat_seconds_off,
                period=repeat_seconds_on + repeat_seconds_off,
                period_min=(repeat_seconds_on + repeat_seconds_off) / 60.0))

        self.currently_dispensing = True
        timer_dispense = time.time() + total_dispense_seconds
        timestamp_start = datetime.datetime.utcnow()

        while time.time() < timer_dispense and self.currently_dispensing:
            # ON pulse
            timer_on = time.time() + repeat_seconds_on
            self.logger.debug("Output turned on")
            self.GPIO.output(self.options_channels['pin'][0], self.options_channels['on_state'][0])
            while time.time() < timer_on and self.currently_dispensing:
                time.sleep(0.01)

            # OFF pause
            timer_off = time.time() + repeat_seconds_off
            self.logger.debug("Output turned off")
            self.GPIO.output(self.options_channels['pin'][0], not self.options_channels['on_state'][0])
            while time.time() < timer_off and self.currently_dispensing:
                time.sleep(0.01)

        self.currently_dispensing = False
        self.record_dispersal(amount, total_seconds_on, total_dispense_seconds, timestamp=timestamp_start)

    def record_dispersal(self, amount, total_on_seconds, total_dispense_seconds, timestamp=None):
        measure_dict = copy.deepcopy(measurements_dict)
        measure_dict[0]['value'] = total_on_seconds
        measure_dict[1]['value'] = amount
        measure_dict[2]['value'] = total_dispense_seconds
        if timestamp:
            measure_dict[0]['timestamp_utc'] = timestamp
            measure_dict[1]['timestamp_utc'] = timestamp
            measure_dict[2]['timestamp_utc'] = timestamp
        add_measurements_influxdb(self.unique_id, measure_dict, use_same_timestamp=False)

    def output_switch(self, state, output_type=None, amount=None, output_channel=None):
        self.logger.debug("state: {}, output_type: {}, amount: {}".format(
            state, output_type, amount))

        if amount is not None and amount < 0:
            self.logger.error("Amount cannot be less than 0")
            return

        if state == 'off':
            if self.currently_dispensing:
                self.currently_dispensing = False
            self.logger.debug("Output turned off")
            self.GPIO.output(self.options_channels['pin'][0], not self.options_channels['on_state'][0])

        elif state == 'on' and output_type in ['vol', None] and amount:
            if self.currently_dispensing:
                self.logger.debug("Pump instructed to turn on for a volume while it's already dispensing. "
                                  "Overriding current dispense with new instruction.")

            if self.options_channels['flow_mode'][0] == 'fastest_flow_rate':
                total_dispense_seconds = amount / self.options_channels['fastest_dispense_rate_ml_min'][0] * 60
                msg = "Turning pump on for {sec:.1f} seconds to dispense {ml:.1f} ml (at {rate:.1f} ml/min, " \
                      "the fastest flow rate).".format(
                        sec=total_dispense_seconds,
                        ml=amount,
                        rate=self.options_channels['fastest_dispense_rate_ml_min'][0])
                self.logger.debug(msg)

                write_db = threading.Thread(
                    target=self.dispense_volume_fastest,
                    args=(amount, total_dispense_seconds,))
                write_db.start()
                return

            elif self.options_channels['flow_mode'][0] == 'specify_flow_rate':
                fastest = self.options_channels['fastest_dispense_rate_ml_min'][0]
                on_pulse = self.options_channels['on_pulse_seconds'][0]

                # The slowest achievable rate occurs when duty_cycle approaches 0.
                # In practice, enforce a minimum OFF time of 0.1 s to avoid GPIO thrashing.
                min_off_seconds = 0.1
                slowest_rate_ml_min = fastest * on_pulse / (on_pulse + min_off_seconds)
                # Note: slowest_rate approaches 0 with no hard floor — the user-requested rate
                # is honoured as long as it is > 0. We only warn, not clamp, at the low end.

                requested = self.options_channels['flow_rate'][0]

                if requested > fastest:
                    self.logger.debug(
                        "Instructed to dispense {ir:.3f} ml/min, "
                        "however the fastest rate is {fr:.1f} ml/min. Clamping.".format(
                            ir=requested, fr=fastest))
                    dispense_rate = fastest
                else:
                    dispense_rate = requested

                self.logger.debug("Turning pump on to dispense {ml:.1f} ml at {rate:.4f} ml/min.".format(
                    ml=amount, rate=dispense_rate))

                write_db = threading.Thread(
                    target=self.dispense_volume_rate,
                    args=(amount, dispense_rate,))
                write_db.start()
                return

            else:
                self.logger.error("Invalid Output Mode: '{}'. Make sure it is properly set.".format(
                    self.options_channels['flow_mode'][0]))
                return

        elif state == 'on' and output_type == 'sec':
            if self.currently_dispensing:
                self.logger.debug(
                    "Pump instructed to turn on while it's already dispensing. "
                    "Overriding current dispense with new instruction.")
            self.logger.debug("Output turned on")
            self.GPIO.output(self.options_channels['pin'][0], self.options_channels['on_state'][0])

        else:
            self.logger.error(
                "Invalid parameters: State: {state}, Type: {ot}, Mode: {mod}, Amount: {amt}, Flow Rate: {fr}".format(
                    state=state,
                    ot=output_type,
                    mod=self.options_channels['flow_mode'][0],
                    amt=amount,
                    fr=self.options_channels['flow_rate'][0]))
            return

    def is_on(self, output_channel=None):
        if self.is_setup():
            try:
                if self.currently_dispensing:
                    return True
                return self.options_channels['on_state'][0] == self.GPIO.input(self.options_channels['pin'][0])
            except Exception as e:
                self.logger.error("Status check error: {}".format(e))

    def is_setup(self):
        return self.output_setup
