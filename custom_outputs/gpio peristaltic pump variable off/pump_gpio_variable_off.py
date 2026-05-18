# coding=utf-8
#
# pump_gpio_variable_off.py - Peristaltic pump output with fixed ON time and variable OFF time.
#
# Three flow rate modes:
#   1. Fastest Flow Rate   - runs pump continuously at 100% duty cycle
#   2. Specify Flow Rate   - user sets desired ml/min; off time is calculated automatically
#   3. Simple Interval     - user sets on_seconds and off_seconds directly;
#                            effective flow rate is calculated and logged automatically
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
        "Controls a peristaltic pump via GPIO using fixed ON pulses with a variable OFF gap. "
        "Three modes: (1) Fastest Flow Rate — runs continuously; "
        "(2) Specify Flow Rate — enter a desired ml/min and the off time is calculated; "
        "(3) Simple Interval — directly set the ON and OFF durations and the effective flow rate "
        "is calculated and logged for you. "
        "Calibrate by running the pump continuously for 60 seconds and entering the dispensed volume "
        "as 'Fastest Rate (ml/min)'."
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
        "CALIBRATION: Purge the fluid line, run the pump continuously for 60 seconds, measure the "
        "dispensed volume in ml, and enter that value as 'Fastest Rate (ml/min)'. "
        "\n\n"
        "MODE — Specify Flow Rate: Set 'On Pulse Duration' (e.g. 10 s) and 'Desired Flow Rate'. "
        "The off time is calculated automatically. "
        "Effective flow rate = Fastest Rate × (on / (on + off)). "
        "\n\n"
        "MODE — Simple Interval: Set 'On Pulse Duration' and 'Off Interval Duration' directly. "
        "The effective flow rate and cycle period will be calculated and logged each time the pump runs. "
        "Formula: Flow Rate (ml/min) = Fastest Rate × on_s / (on_s + off_s)."
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
                'How long the pump runs for each pulse. '
                'Used in all modes. '
                'In Specify Flow Rate mode the off time is calculated from this and the desired flow rate. '
                'In Simple Interval mode both on and off times are set directly.'
            )
        },
        {
            'id': 'flow_mode',
            'type': 'select',
            'default_value': 'fastest_flow_rate',
            'options_select': [
                ('fastest_flow_rate', 'Fastest Flow Rate'),
                ('specify_flow_rate', 'Specify Flow Rate'),
                ('simple_interval', 'Simple Interval (set on + off directly)')
            ],
            'name': 'Flow Rate Method',
            'phrase': (
                'Fastest Flow Rate: runs continuously at 100% duty cycle. '
                'Specify Flow Rate: enter ml/min and off time is calculated. '
                'Simple Interval: set on and off durations directly; effective flow rate is calculated for you.'
            )
        },
        {
            'id': 'flow_rate',
            'type': 'float',
            'default_value': 10.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': "{} ({}) — Specify Flow Rate mode".format(lazy_gettext('Desired Flow Rate'), lazy_gettext('ml/min')),
            'phrase': 'Desired flow rate in ml/min. Used only in Specify Flow Rate mode. Off time is calculated automatically.'
        },
        {
            'id': 'off_interval_seconds',
            'type': 'float',
            'default_value': 1200.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Off Interval Duration (Seconds) — Simple Interval mode',
            'phrase': (
                'How long the pump stays off between pulses. Used only in Simple Interval mode. '
                'Effective flow rate = Fastest Rate × on_s / (on_s + off_s). '
                'Example: on=10 s, off=1200 s, fastest=20.7 ml/min → 0.171 ml/min, cycle every 20.2 min.'
            )
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

    def dispense_volume_rate(self, amount, dispense_rate, repeat_seconds_on, repeat_seconds_off):
        """
        Dispense a volume at a specific flow rate using fixed-ON / variable-OFF pulsing.

        repeat_seconds_on and repeat_seconds_off are pre-calculated by the caller so this
        method works for both 'Specify Flow Rate' and 'Simple Interval' modes.
        """
        total_dispense_seconds = amount / dispense_rate * 60
        self.logger.debug("Total duration to run: {0:.1f} seconds".format(total_dispense_seconds))

        duty_cycle = repeat_seconds_on / (repeat_seconds_on + repeat_seconds_off)
        total_seconds_on = total_dispense_seconds * duty_cycle
        total_seconds_off = total_dispense_seconds - total_seconds_on

        self.logger.debug("Duty Cycle: {0:.2f} %".format(duty_cycle * 100))
        self.logger.debug("Total seconds on: {0:.1f}".format(total_seconds_on))
        self.logger.debug("Total seconds off: {0:.1f}".format(total_seconds_off))
        self.logger.debug(
            "Pulse cycle: on {on:.2f} s, off {off:.1f} s  "
            "(period {period:.1f} s = {period_min:.2f} min)  "
            "Effective flow rate: {rate:.4f} ml/min".format(
                on=repeat_seconds_on,
                off=repeat_seconds_off,
                period=repeat_seconds_on + repeat_seconds_off,
                period_min=(repeat_seconds_on + repeat_seconds_off) / 60.0,
                rate=dispense_rate))

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

                requested = self.options_channels['flow_rate'][0]
                if requested > fastest:
                    self.logger.debug(
                        "Instructed to dispense {ir:.3f} ml/min, "
                        "however the fastest rate is {fr:.1f} ml/min. Clamping.".format(
                            ir=requested, fr=fastest))
                    dispense_rate = fastest
                else:
                    dispense_rate = requested

                # Calculate off time from duty cycle (no 60-second window constraint)
                duty_cycle = dispense_rate / fastest
                on_s = self.options_channels['on_pulse_seconds'][0]
                off_s = on_s * (1.0 - duty_cycle) / duty_cycle

                self.logger.debug(
                    "Specify Flow Rate mode: {rate:.4f} ml/min → on {on:.2f} s / off {off:.1f} s "
                    "(period {period:.1f} s = {period_min:.2f} min)".format(
                        rate=dispense_rate, on=on_s, off=off_s,
                        period=on_s + off_s, period_min=(on_s + off_s) / 60.0))
                self.logger.debug("Turning pump on to dispense {ml:.1f} ml at {rate:.4f} ml/min.".format(
                    ml=amount, rate=dispense_rate))

                write_db = threading.Thread(
                    target=self.dispense_volume_rate,
                    args=(amount, dispense_rate, on_s, off_s))
                write_db.start()
                return

            elif self.options_channels['flow_mode'][0] == 'simple_interval':
                fastest = self.options_channels['fastest_dispense_rate_ml_min'][0]
                on_s = self.options_channels['on_pulse_seconds'][0]
                off_s = self.options_channels['off_interval_seconds'][0]

                # Calculate effective flow rate from the intervals
                effective_rate = fastest * on_s / (on_s + off_s)

                self.logger.info(
                    "Simple Interval mode: on {on:.2f} s / off {off:.1f} s "
                    "(period {period:.1f} s = {period_min:.2f} min) → "
                    "Effective flow rate: {rate:.4f} ml/min".format(
                        on=on_s, off=off_s,
                        period=on_s + off_s, period_min=(on_s + off_s) / 60.0,
                        rate=effective_rate))
                self.logger.debug("Turning pump on to dispense {ml:.1f} ml at {rate:.4f} ml/min.".format(
                    ml=amount, rate=effective_rate))

                write_db = threading.Thread(
                    target=self.dispense_volume_rate,
                    args=(amount, effective_rate, on_s, off_s))
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
