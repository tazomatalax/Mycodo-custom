# coding=utf-8
"""
Mycodo custom output module for driving an Alicat Mass Flow Controller.

Provides a value-type output that writes a new flow setpoint (in the
units configured on the device) whenever Mycodo automations, PID, or
manual commands call it.
"""

from __future__ import annotations

import logging
import struct
from typing import Dict, Optional

import minimalmodbus
import serial

from mycodo.outputs.base_output import AbstractOutput
from mycodo.utils.lockfile import LockFile


# ===== Alicat Common Functions =====
def setup_instrument(port: str, slave_address: int, baudrate: int = 19200, timeout: float = 1.0) -> minimalmodbus.Instrument:
    """Create and configure a Modbus RTU instrument for the Alicat MFC."""
    instrument = minimalmodbus.Instrument(port, slaveaddress=slave_address, debug=False)
    instrument.serial.baudrate = baudrate
    instrument.serial.bytesize = 8
    instrument.serial.parity = serial.PARITY_NONE
    instrument.serial.stopbits = 2
    instrument.serial.timeout = timeout
    instrument.mode = minimalmodbus.MODE_RTU
    instrument.clear_buffers_before_each_transaction = True
    return instrument


def _swapped_registers_to_float(reg_low: int, reg_high: int) -> float:
    """Convert swapped uint16 registers to IEEE 754 float."""
    bytes_value = struct.pack('>HH', reg_low, reg_high)
    return struct.unpack('>f', bytes_value)[0]


def _float_to_swapped_registers(value: float) -> list[int]:
    """Convert float to swapped register order required by Alicat."""
    bytes_value = struct.pack('>f', value)
    reg_low, reg_high = struct.unpack('>HH', bytes_value)
    return [reg_low, reg_high]


# Register constants
DATA_START = 1349
DATA_COUNT = 16
SETPOINT_REG = 1009  # Write setpoint to register 1009-1010 (Register Numbers 1010-1011)


def read_mfc_snapshot(instrument: minimalmodbus.Instrument) -> Dict[str, float]:
    """Read the primary measurement block from the Alicat controller."""
    registers = instrument.read_registers(DATA_START, DATA_COUNT, functioncode=3)
    return {
        "setpoint": _swapped_registers_to_float(registers[0], registers[1]),
        "valve_drive": _swapped_registers_to_float(registers[2], registers[3]),
        "pressure": _swapped_registers_to_float(registers[4], registers[5]),
        "secondary_pressure": _swapped_registers_to_float(registers[6], registers[7]),
        "barometric_pressure": _swapped_registers_to_float(registers[8], registers[9]),
        "temperature": _swapped_registers_to_float(registers[10], registers[11]),
        "volumetric_flow": _swapped_registers_to_float(registers[12], registers[13]),
        "mass_flow": _swapped_registers_to_float(registers[14], registers[15]),
    }


def write_setpoint(instrument: minimalmodbus.Instrument, setpoint: float) -> float:
    """Write a new setpoint (in device units) and return the echoed value."""
    registers = _float_to_swapped_registers(setpoint)
    instrument.write_registers(SETPOINT_REG, registers)
    confirmation = read_mfc_snapshot(instrument)
    return confirmation["setpoint"]


# ===== End Alicat Common Functions =====


LOCK_NAME = "/var/lock/alicat_mfc"

measurements_dict = {
    0: {"measurement": "volume_flow_rate", "unit": "ml_min"},
}

channels_dict = {
    0: {
        'types': ['value'],
        'measurements': [0]
    }
}

OUTPUT_INFORMATION = {
    "output_name_unique": "alicat_mfc_output",
    "output_name": "Alicat MFC (Setpoint Control)",
    "measurements_dict": measurements_dict,
    "channels_dict": channels_dict,
    "output_types": ["value"],
    "interfaces": ["UART"],
    "options_enabled": [
        "button_send_value",
    ],
    # Dependencies are already installed in the Mycodo environment
    # Uncomment below if Mycodo's dependency checker is needed
    # "dependencies_module": [
    #     ("pip-pypi", "minimalmodbus", "minimalmodbus"),
    #     ("pip-pypi", "pyserial", "serial"),
    # ],
    "custom_options": [
        {
            "id": "uart_device",
            "type": "text",
            "default_value": "/dev/ttyUSB0",
            "required": True,
            "name": "UART Device",
            "phrase": "Serial device connected to the RS485 adapter.",
        },
        {
            "id": "baud_rate",
            "type": "integer",
            "default_value": 19200,
            "required": True,
            "name": "Baud Rate",
        },
        {
            "id": "modbus_address",
            "type": "integer",
            "default_value": 1,
            "required": True,
            "name": "Modbus Address",
        },
    ],
}


class OutputModule(AbstractOutput):
    """Expose Alicat setpoint control as a Mycodo output."""

    def __init__(self, output, testing: bool = False):
        super().__init__(output, testing=testing, name=__name__)
        self.instrument = None
        self.logger = logging.getLogger(__name__)
        self.uart_device = "/dev/ttyUSB0"
        self.baud_rate = 19200
        self.modbus_address = 1
        self.timeout = 1.0

        if not testing:
            self.setup_custom_options(OUTPUT_INFORMATION["custom_options"], output)

    def initialize(self):
        """Open the Modbus serial connection."""
        self.setup_output_variables(OUTPUT_INFORMATION)
        
        self.uart_device = self._get_option_value("uart_device", self.uart_device)
        baud = self._get_option_value("baud_rate", self.baud_rate)
        if baud is not None:
            self.baud_rate = int(baud)
        address = self._get_option_value("modbus_address", self.modbus_address)
        if address is not None:
            self.modbus_address = int(address)
        timeout = getattr(self.output, "uart_timeout", self.timeout)
        self.timeout = timeout if timeout else self.timeout

        self.instrument = setup_instrument(
            self.uart_device, self.modbus_address, self.baud_rate, self.timeout
        )

    def _get_option_value(self, option_id: str, default: Optional[str] = None):
        option = getattr(self, "options_custom", {}).get(option_id)
        if option is None:
            return default
        return option.get("value", default)

    def output_switch(self, state, output_type=None, amount=None, output_channel=None):
        """
        Handle value writes from Mycodo.

        Args:
            state: String describing new state ("on"/"off")
            output_type: Output category (unused)
            amount: Desired flow setpoint in device units (float)
            output_channel: Channel number (unused, single channel device)
        """
        if self.instrument is None:
            self.initialize()

        # Handle "off" state by setting setpoint to 0
        if state == 'off':
            amount = 0.0
        
        if amount is None:
            self.logger.error("Alicat setpoint write skipped: no amount provided")
            return False

        lock_file = f"/var/lock/mycodo_serial_{self.uart_device.replace('/', '_')}.lock"
        lf = LockFile()
        if lf.lock_acquire(lock_file, timeout=5.0):
            try:
                echoed = write_setpoint(self.instrument, float(amount))
                self.logger.info(
                    "Set Alicat flow setpoint to %.3f (device echoed %.3f)", amount, echoed
                )
                
                # Store the setpoint value in output_states so is_on() returns it
                # This makes the output display show "Active, X.X" in the UI
                self.output_states[0] = echoed
                
                return True
            except Exception as exc:  # pragma: no cover - requires hardware
                self.logger.exception("Failed to write Alicat setpoint: %s", exc)
                return False
            finally:
                lf.lock_release(lock_file)
        return False

    def is_on(self, channel=None):
        """
        Return the current setpoint value, or False if off.
        
        This is what Mycodo calls to determine output state. When this returns
        a numeric value > 0, the UI shows "Active, X.X". When it returns False
        or 0, the UI shows "Inactive".
        """
        if self.instrument is None:
            self.logger.debug("is_on() called but instrument is None")
            return False
        
        lock_file = f"/var/lock/mycodo_serial_{self.uart_device.replace('/', '_')}.lock"
        lf = LockFile()
        if lf.lock_acquire(lock_file, timeout=5.0):
            try:
                # Read the current setpoint from the device
                snapshot = read_mfc_snapshot(self.instrument)
                setpoint = snapshot["setpoint"]
                self.output_states[0] = setpoint
                
                self.logger.debug(f"is_on() read setpoint: {setpoint}")
                
                # Return the setpoint value if > 0, otherwise False
                # This makes the UI display show the actual setpoint value
                if setpoint > 0.01:  # Small threshold for floating point comparison
                    return setpoint
                else:
                    return False
            except Exception as e:
                self.logger.error(f"Failed to read setpoint in is_on(): {e}")
                # Fall back to cached value in output_states
                if 0 in self.output_states and self.output_states[0]:
                    cached = self.output_states[0]
                    self.logger.debug(f"is_on() returning cached value: {cached}")
                    return cached
                return False
            finally:
                lf.lock_release(lock_file)
        return False

    def is_setup(self):
        """Required method. Return if output is properly initialized."""
        return self.instrument is not None

    def stop_output(self):
        """Clean up resources when output is stopped."""
        self.instrument = None

    def get_current_flow(self) -> Optional[float]:
        """Optional helper to view latest flow value from the output page."""
        if self.instrument is None:
            return None

        try:
            snapshot = read_mfc_snapshot(self.instrument)
            return snapshot["volumetric_flow"]
        except Exception:
            return None
