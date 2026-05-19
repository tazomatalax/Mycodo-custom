# coding=utf-8
#
# pump_gpio_variable_off.py - Peristaltic pump output with fixed ON pulses and variable OFF gap.
#
# Four modes:
#   1. Fastest Flow Rate  - 100% duty cycle, no pulsing
#   2. Specify Flow Rate  - set desired ml/min -> off time calculated
#   3. Simple Interval    - set on_s + off_s directly -> flow rate + dose projections calculated
#   4. Target Dose        - set total_ml + total_hours + on_pulse -> rate + cycle calculated
#
# On every save/restart a "Dosing Plan" summary is printed to the log at INFO level so the
# operator can immediately verify the settings are correct before any fluid is moved.
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

# One stop-Event per output unique_id.  When Mycodo re-initialises an output
# (after a settings save) it creates a NEW OutputModule while the old dispense
# thread is still alive.  Signalling the old event here is the only reliable
# way to stop that orphaned thread and return the pin to single ownership.
_DISPENSE_STOP: dict = {}

measurements_dict = {
    0: {'measurement': 'duration_time', 'unit': 's',  'name': 'Pump On'},
    1: {'measurement': 'volume',        'unit': 'ml', 'name': 'Dispense Volume'},
    2: {'measurement': 'duration_time', 'unit': 's',  'name': 'Dispense Duration'},
}

channels_dict = {
    0: {'types': ['volume', 'on_off'], 'measurements': [0, 1, 2]}
}

OUTPUT_INFORMATION = {
    'output_name_unique': 'peristaltic_pump_variable_off',
    'output_name': "{}: Raspberry Pi GPIO, Variable Off Time (Pi <= 4)".format(lazy_gettext('Peristaltic Pump')),
    'output_library': 'RPi.GPIO',
    'measurements_dict': measurements_dict,
    'channels_dict': channels_dict,
    'output_types': ['volume', 'on_off'],

    'message': (
        "Peristaltic pump controller using fixed ON pulses with a variable OFF gap. "
        "Four modes: run at full speed; specify a flow rate in ml/min; "
        "set on/off intervals directly; or enter a total volume and timeframe to dose. "
        "After saving, check the Mycodo log for a full Dosing Plan summary — "
        "flow rate, cycle period, projected volumes — before any fluid is moved."
    ),

    'options_enabled': ['button_on', 'button_send_volume', 'button_send_duration'],
    'options_disabled': ['interface'],

    'dependencies_module': [('pip-pypi', 'RPi.GPIO', 'RPi.GPIO==0.7.1')],
    'interfaces': ['GPIO'],

    'custom_options_message': (
        "CALIBRATION (do this first):\n"
        "  Purge the fluid line. Run the pump continuously for exactly 60 seconds and "
        "collect the dispensed liquid. Measure the volume in ml -- that value equals ml/min. "
        "Enter it as 'Fastest Rate (ml/min)' below.\n\n"

        "MODES:\n"
        "  Fastest Flow Rate -- pump runs solid at 100%% duty cycle.\n"
        "  Specify Flow Rate -- enter target ml/min; off gap derived: off = on x (fastest/rate - 1)\n"
        "  Simple Interval   -- set on + off seconds directly; rate derived: rate = fastest x on/(on+off)\n"
        "  Target Dose       -- enter total ml + total hours; rate and cycle derived automatically.\n\n"

        "TIP: After saving, open the Mycodo log. A 'DOSING PLAN' block is printed at INFO level "
        "showing the derived cycle, flow rate, and projected dose over 8/16/24 h. "
        "Verify this before starting a long run."
    ),

    'custom_channel_options': [
        # Hardware
        {
            'id': 'pin',
            'type': 'integer',
            'default_value': None,
            'required': False,
            'constraints_pass': constraints_pass_positive_or_zero_value,
            'name': 'GPIO Pin (BCM)',
            'phrase': 'BCM-numbered GPIO pin connected to the pump relay or driver'
        },
        {
            'id': 'on_state',
            'type': 'select',
            'default_value': 1,
            'options_select': [(1, 'HIGH'), (0, 'LOW')],
            'name': 'On State',
            'phrase': 'GPIO level that activates the pump. Most relay boards = LOW; most MOSFETs = HIGH.'
        },
        {
            'id': 'amps',
            'type': 'float',
            'default_value': 0.0,
            'required': True,
            'name': 'Current Draw (Amps)',
            'phrase': 'Pump current draw for power tracking. Set 0 to ignore.'
        },
        # Calibration
        {
            'id': 'fastest_dispense_rate_ml_min',
            'type': 'float',
            'default_value': 150.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Fastest Rate (ml/min)',
            'phrase': (
                'CALIBRATE: run pump 60 s, measure dispensed ml -- that value is ml/min. '
                'Example: 20.7 ml dispensed in 60 s -> enter 20.7'
            )
        },
        # Mode
        {
            'id': 'flow_mode',
            'type': 'select',
            'default_value': 'simple_interval',
            'options_select': [
                ('fastest_flow_rate', 'Fastest Flow Rate  (100% duty cycle, runs solid)'),
                ('specify_flow_rate', 'Specify Flow Rate  (enter ml/min -> off time derived)'),
                ('simple_interval',   'Simple Interval    (enter on + off seconds -> rate derived)'),
                ('target_dose',       'Target Dose        (enter total ml + total hours -> cycle derived)'),
            ],
            'name': 'Mode',
            'phrase': (
                'Choose how to define pump behaviour. All pulsed modes use fixed ON + variable OFF. '
                'After saving, check the log for the DOSING PLAN block to verify your settings.'
            )
        },
        # On pulse (all pulsed modes)
        {
            'id': 'on_pulse_seconds',
            'type': 'float',
            'default_value': 10.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'On Pulse Duration (s)',
            'phrase': (
                'How long the pump runs per pulse (all pulsed modes). '
                '10 s is a good default. Shorter = finer control but more relay wear.'
            )
        },
        # Specify Flow Rate
        {
            'id': 'flow_rate',
            'type': 'float',
            'default_value': 1.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Desired Flow Rate (ml/min)  [Specify Flow Rate mode]',
            'phrase': (
                'Target flow rate. Off gap is calculated: off = on x (fastest/rate - 1). '
                'Example: fastest=20.7, on=10 s, rate=0.171 ml/min -> off=1200 s (20-min cycle).'
            )
        },
        # Simple Interval
        {
            'id': 'off_interval_seconds',
            'type': 'float',
            'default_value': 1200.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Off Interval (s)  [Simple Interval mode]',
            'phrase': (
                'Rest time between pulses. Rate is calculated: rate = fastest x on/(on+off). '
                'Example: on=10 s, off=1200 s, fastest=20.7 -> 0.171 ml/min, 20.2-min cycle.'
            )
        },
        # Target Dose
        {
            'id': 'target_volume_ml',
            'type': 'float',
            'default_value': 500.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Target Volume (ml)  [Target Dose mode]',
            'phrase': (
                'Total volume to dose over the target duration. '
                'Example: 2000 ml over 23 h -> 1.449 ml/min -> on=10 s, off=404 s (~206 pulses).'
            )
        },
        {
            'id': 'target_duration_hours',
            'type': 'float',
            'default_value': 24.0,
            'constraints_pass': constraints_pass_positive_value,
            'name': 'Target Duration (hours)  [Target Dose mode]',
            'phrase': (
                'Timeframe to spread the dose over. '
                'rate = target_ml / (hours x 60). '
                'Trigger with the Volume SEND button set to the target volume.'
            )
        },
    ]
}


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _cycle_from_rate(rate_ml_min, fastest_ml_min, on_s):
    """Return (off_s, period_s, duty_pct) for a desired flow rate."""
    if rate_ml_min >= fastest_ml_min:
        return 0.0, on_s, 100.0
    duty  = rate_ml_min / fastest_ml_min
    off_s = on_s * (1.0 - duty) / duty
    return off_s, on_s + off_s, duty * 100.0


def _fmt(seconds):
    """Human-readable duration: seconds / minutes / hours."""
    if seconds < 120:
        return "{:.1f} s".format(seconds)
    elif seconds < 7200:
        return "{:.1f} min".format(seconds / 60.0)
    else:
        return "{:.2f} h".format(seconds / 3600.0)


# ---------------------------------------------------------------------------
# Output class
# ---------------------------------------------------------------------------

class OutputModule(AbstractOutput):

    def __init__(self, output, testing=False):
        super().__init__(output, testing=testing, name=__name__)
        self.GPIO = None
        self.currently_dispensing = False
        output_channels = db_retrieve_table_daemon(
            OutputChannel).filter(OutputChannel.output_id == self.output.unique_id).all()
        self.options_channels = self.setup_custom_channel_options_json(
            OUTPUT_INFORMATION['custom_channel_options'], output_channels)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def initialize(self):
        import RPi.GPIO as GPIO
        self.GPIO = GPIO
        self.setup_output_variables(OUTPUT_INFORMATION)

        # Cancel any dispense thread left behind by a previous instance of
        # this output (e.g. after a settings save that re-creates the module).
        uid = self.output.unique_id
        old_ev = _DISPENSE_STOP.pop(uid, None)
        if old_ev is not None:
            old_ev.set()
        self._stop_event = threading.Event()
        _DISPENSE_STOP[uid] = self._stop_event

        if self.options_channels['pin'][0] is None:
            self.logger.warning("No GPIO pin configured — output will not function.")
            return

        try:
            self.GPIO.setmode(self.GPIO.BCM)
            self.GPIO.setwarnings(True)
            self.GPIO.setup(self.options_channels['pin'][0], self.GPIO.OUT)
            self.GPIO.output(self.options_channels['pin'][0], not self.options_channels['on_state'][0])
            self.output_setup = True
            self.logger.info("Output setup on pin {} and turned OFF (OFF={})".format(
                self.options_channels['pin'][0],
                'LOW' if self.options_channels['on_state'][0] else 'HIGH'))
        except Exception as e:
            self.logger.exception("Setup failed on pin {}: {}".format(
                self.options_channels['pin'][0], e))
            return

        self._log_dosing_plan()

    def _log_dosing_plan(self):
        """Log a full dosing plan at INFO level after every save/restart."""
        try:
            fastest = self.options_channels['fastest_dispense_rate_ml_min'][0]
            on_s    = self.options_channels['on_pulse_seconds'][0]
            mode    = self.options_channels['flow_mode'][0]
            sep     = "=" * 52

            if mode == 'fastest_flow_rate':
                self.logger.info(sep)
                self.logger.info("DOSING PLAN  [Fastest Flow Rate]")
                self.logger.info("  Pump runs solid at 100%% duty cycle")
                self.logger.info("  Flow rate   : {:.2f} ml/min".format(fastest))
                self.logger.info("  Per hour    : {:.1f} ml".format(fastest * 60))
                self.logger.info(sep)

            elif mode == 'specify_flow_rate':
                rate = min(self.options_channels['flow_rate'][0], fastest)
                off_s, period_s, duty_pct = _cycle_from_rate(rate, fastest, on_s)
                self.logger.info(sep)
                self.logger.info("DOSING PLAN  [Specify Flow Rate]")
                self.logger.info("  Flow rate   : {:.4f} ml/min".format(rate))
                self.logger.info("  On pulse    : {:.2f} s".format(on_s))
                self.logger.info("  Off gap     : {}".format(_fmt(off_s)))
                self.logger.info("  Cycle period: {} ({:.2f} min)".format(_fmt(period_s), period_s / 60))
                self.logger.info("  Duty cycle  : {:.2f} %".format(duty_pct))
                self.logger.info("  Per  8 h    : {:.1f} ml".format(rate * 60 * 8))
                self.logger.info("  Per 16 h    : {:.1f} ml".format(rate * 60 * 16))
                self.logger.info("  Per 24 h    : {:.1f} ml".format(rate * 60 * 24))
                self.logger.info(sep)

            elif mode == 'simple_interval':
                off_s    = self.options_channels['off_interval_seconds'][0]
                rate     = fastest * on_s / (on_s + off_s)
                period_s = on_s + off_s
                pph      = 3600.0 / period_s
                self.logger.info(sep)
                self.logger.info("DOSING PLAN  [Simple Interval]")
                self.logger.info("  On pulse    : {:.2f} s".format(on_s))
                self.logger.info("  Off gap     : {}".format(_fmt(off_s)))
                self.logger.info("  Cycle period: {} ({:.2f} min)".format(_fmt(period_s), period_s / 60))
                self.logger.info("  Duty cycle  : {:.2f} %".format(on_s / period_s * 100))
                self.logger.info("  Flow rate   : {:.4f} ml/min".format(rate))
                self.logger.info("  Pulses/hour : {:.1f}".format(pph))
                self.logger.info("  Per  8 h    : {:.1f} ml  ({:.0f} pulses)".format(rate * 60 * 8,  pph * 8))
                self.logger.info("  Per 16 h    : {:.1f} ml  ({:.0f} pulses)".format(rate * 60 * 16, pph * 16))
                self.logger.info("  Per 24 h    : {:.1f} ml  ({:.0f} pulses)".format(rate * 60 * 24, pph * 24))
                self.logger.info(sep)

            elif mode == 'target_dose':
                total_ml    = self.options_channels['target_volume_ml'][0]
                total_hours = self.options_channels['target_duration_hours'][0]
                rate        = min(total_ml / (total_hours * 60.0), fastest)
                off_s, period_s, duty_pct = _cycle_from_rate(rate, fastest, on_s)
                total_run_s = total_ml / rate * 60.0
                n_pulses    = total_run_s / period_s
                self.logger.info(sep)
                self.logger.info("DOSING PLAN  [Target Dose]")
                self.logger.info("  Target      : {:.1f} ml over {:.2f} h".format(total_ml, total_hours))
                self.logger.info("  Required rate: {:.4f} ml/min".format(rate))
                self.logger.info("  On pulse    : {:.2f} s".format(on_s))
                self.logger.info("  Off gap     : {}".format(_fmt(off_s)))
                self.logger.info("  Cycle period: {} ({:.2f} min)".format(_fmt(period_s), period_s / 60))
                self.logger.info("  Duty cycle  : {:.2f} %".format(duty_pct))
                self.logger.info("  Total run   : {:.2f} h  (~{:.0f} pulses)".format(
                    total_run_s / 3600.0, n_pulses))
                self.logger.info("  >> To start: Volume SEND = {:.1f} ml".format(total_ml))
                self.logger.info(sep)

        except Exception as e:
            self.logger.warning("Could not generate Dosing Plan: {}".format(e))

    # ------------------------------------------------------------------
    # Dispense methods
    # ------------------------------------------------------------------

    def dispense_volume_fastest(self, amount, total_dispense_seconds, stop_event):
        self.currently_dispensing = True
        self.logger.debug("Output turned on")
        self.GPIO.output(self.options_channels['pin'][0], self.options_channels['on_state'][0])
        timer_dispense = time.time() + total_dispense_seconds
        timestamp_start = datetime.datetime.utcnow()

        while time.time() < timer_dispense and not stop_event.is_set():
            time.sleep(0.01)

        self.GPIO.output(self.options_channels['pin'][0], not self.options_channels['on_state'][0])
        self.currently_dispensing = False
        self.logger.debug("Output turned off")
        self.record_dispersal(amount, total_dispense_seconds, total_dispense_seconds,
                              timestamp=timestamp_start)

    def dispense_volume_rate(self, amount, dispense_rate, repeat_seconds_on, repeat_seconds_off, stop_event):
        total_s   = amount / dispense_rate * 60
        duty      = repeat_seconds_on / (repeat_seconds_on + repeat_seconds_off)
        on_total  = total_s * duty
        off_total = total_s - on_total
        n_pulses  = total_s / (repeat_seconds_on + repeat_seconds_off)

        self.logger.info("Dispensing {:.1f} ml at {:.4f} ml/min".format(amount, dispense_rate))
        self.logger.info("  Pulse: on {:.2f} s / off {}  |  cycle {} ({:.2f} min)".format(
            repeat_seconds_on, _fmt(repeat_seconds_off),
            _fmt(repeat_seconds_on + repeat_seconds_off),
            (repeat_seconds_on + repeat_seconds_off) / 60.0))
        self.logger.info("  Run: {:.1f} s on + {:.1f} s off = {:.2f} h total  (~{:.0f} pulses)".format(
            on_total, off_total, total_s / 3600.0, n_pulses))

        self.currently_dispensing = True
        timer_dispense = time.time() + total_s
        timestamp_start = datetime.datetime.utcnow()

        while time.time() < timer_dispense and not stop_event.is_set():
            timer_on = time.time() + repeat_seconds_on
            self.logger.debug("Output turned on")
            self.GPIO.output(self.options_channels['pin'][0], self.options_channels['on_state'][0])
            while time.time() < timer_on and not stop_event.is_set():
                time.sleep(0.01)

            timer_off = time.time() + repeat_seconds_off
            self.logger.debug("Output turned off")
            self.GPIO.output(self.options_channels['pin'][0], not self.options_channels['on_state'][0])
            while time.time() < timer_off and not stop_event.is_set():
                time.sleep(0.01)

        self.currently_dispensing = False
        self.record_dispersal(amount, on_total, total_s, timestamp=timestamp_start)

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

    # ------------------------------------------------------------------
    # Switch
    # ------------------------------------------------------------------

    def output_switch(self, state, output_type=None, amount=None, output_channel=None):
        self.logger.debug("state={}, output_type={}, amount={}".format(state, output_type, amount))

        if amount is not None and amount < 0:
            self.logger.error("Amount cannot be less than 0")
            return

        fastest = self.options_channels['fastest_dispense_rate_ml_min'][0]
        on_s    = self.options_channels['on_pulse_seconds'][0]
        mode    = self.options_channels['flow_mode'][0]

        if state == 'off':
            # Signal whichever thread currently owns the pin (current or orphaned).
            self._stop_event.set()
            self._stop_event = threading.Event()
            _DISPENSE_STOP[self.output.unique_id] = self._stop_event
            self.currently_dispensing = False
            self.logger.debug("Output turned off")
            self.GPIO.output(self.options_channels['pin'][0], not self.options_channels['on_state'][0])

        elif state == 'on' and output_type in ['vol', None] and amount:
            # Stop any running dispense — both on THIS instance and any orphaned
            # thread left by a previous instance after a settings save/restart.
            if self.currently_dispensing:
                self.logger.debug("Overriding current dispense with new instruction.")
            self._stop_event.set()
            self._stop_event = threading.Event()
            _DISPENSE_STOP[self.output.unique_id] = self._stop_event
            stop_ev = self._stop_event  # captured by the new thread

            if mode == 'fastest_flow_rate':
                total_s = amount / fastest * 60
                self.logger.info("Fastest mode: {:.1f} ml in {:.1f} s".format(amount, total_s))
                threading.Thread(target=self.dispense_volume_fastest,
                                 args=(amount, total_s, stop_ev),
                                 daemon=True).start()

            elif mode == 'specify_flow_rate':
                rate = min(self.options_channels['flow_rate'][0], fastest)
                off_s, _, _ = _cycle_from_rate(rate, fastest, on_s)
                threading.Thread(target=self.dispense_volume_rate,
                                 args=(amount, rate, on_s, off_s, stop_ev),
                                 daemon=True).start()

            elif mode == 'simple_interval':
                off_s = self.options_channels['off_interval_seconds'][0]
                rate  = fastest * on_s / (on_s + off_s)
                threading.Thread(target=self.dispense_volume_rate,
                                 args=(amount, rate, on_s, off_s, stop_ev),
                                 daemon=True).start()

            elif mode == 'target_dose':
                total_ml    = self.options_channels['target_volume_ml'][0]
                total_hours = self.options_channels['target_duration_hours'][0]
                rate        = min(total_ml / (total_hours * 60.0), fastest)
                off_s, _, _ = _cycle_from_rate(rate, fastest, on_s)
                if abs(amount - total_ml) > 0.5:
                    self.logger.warning(
                        "Requested {:.1f} ml but target_volume is {:.1f} ml — "
                        "using requested amount at configured rate.".format(amount, total_ml))
                threading.Thread(target=self.dispense_volume_rate,
                                 args=(amount, rate, on_s, off_s, stop_ev),
                                 daemon=True).start()

            else:
                self.logger.error("Unknown mode: '{}'".format(mode))

        elif state == 'on' and output_type == 'sec':
            if self.currently_dispensing:
                self.logger.debug("Overriding current dispense.")
                self._stop_event.set()
                self._stop_event = threading.Event()
                _DISPENSE_STOP[self.output.unique_id] = self._stop_event
                self.currently_dispensing = False
            self.logger.debug("Output turned on (duration mode)")
            self.GPIO.output(self.options_channels['pin'][0], self.options_channels['on_state'][0])

        else:
            self.logger.error("Invalid parameters: state={}, type={}, mode={}, amount={}".format(
                state, output_type, mode, amount))

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_on(self, output_channel=None):
        if self.is_setup():
            try:
                if self.currently_dispensing:
                    return True
                return self.options_channels['on_state'][0] == self.GPIO.input(
                    self.options_channels['pin'][0])
            except Exception as e:
                self.logger.error("Status check error: {}".format(e))

    def is_setup(self):
        return self.output_setup
