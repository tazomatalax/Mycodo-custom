# coding=utf-8
"""
Mycodo custom input module for Alicat Mass Flow Controllers.

Reads volumetric flow, pressure, temperature, and current setpoint so
the values can be graphed or fed into PID loops.
"""

from __future__ import annotations

import copy
import logging
import struct
from typing import Dict, Optional

import minimalmodbus
import serial

from mycodo.inputs.base_input import AbstractInput


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


# Register constants
DATA_START = 1349
DATA_COUNT = 16


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


# ===== End Alicat Common Functions =====


LOCK_NAME = "/var/lock/alicat_mfc"

measurements_dict = {
    0: {"measurement": "volume_flow_rate", "unit": "ml_min"},
    1: {"measurement": "mass_flow_rate", "unit": "sml_min"},
    2: {"measurement": "pressure", "unit": "psi"},
    3: {"measurement": "temperature", "unit": "C"},
    4: {"measurement": "setpoint", "unit": "sml_min"},
}

INPUT_INFORMATION = {
    "input_name_unique": "alicat_mfc_input",
    "input_manufacturer": "Alicat",
    "input_name": "Mass Flow Controller (Telemetry)",
    "measurements_name": "Flow/Pressure/Temperature",
    "measurements_dict": measurements_dict,
    "options_enabled": [
        "uart_location",
        "uart_baud_rate",
        "period",
        "measurements_select",
    ],
    "interfaces": ["UART"],
    "uart_location": "/dev/ttyUSB0",
    "uart_baud_rate": 19200,
    # Dependencies are already installed in the Mycodo environment
    # Uncomment below if Mycodo's dependency checker is needed
    # "dependencies_module": [
    #     ("pip-pypi", "minimalmodbus", "minimalmodbus"),
    #     ("pip-pypi", "pyserial", "serial"),
    # ],
    "custom_options": [
        {
            "id": "modbus_address",
            "type": "integer",
            "default_value": 1,
            "required": True,
            "name": "Modbus Address",
            "phrase": "RTU slave ID configured on the Alicat.",
        }
    ],
}


class InputModule(AbstractInput):
    """Expose Alicat telemetry as a Mycodo input."""

    def __init__(self, input_dev, testing: bool = False):
        super().__init__(input_dev, testing=testing, name=__name__)
        self.instrument = None
        self.logger = logging.getLogger(__name__)
        self.modbus_address = 1

        if not testing:
            self.setup_custom_options(INPUT_INFORMATION["custom_options"], input_dev)
            self.initialize_input()

    def initialize_input(self):
        """Establish the Modbus connection."""
        address = self._get_option_value("modbus_address", default=self.modbus_address)
        if address is not None:
            self.modbus_address = int(address)

        port = getattr(self.input_dev, "uart_location", "/dev/ttyUSB0")
        baudrate = getattr(self.input_dev, "baud_rate", 19200)
        timeout = getattr(self.input_dev, "uart_timeout", 1.0)

        self.instrument = setup_instrument(port, self.modbus_address, baudrate, timeout)

    def _get_option_value(self, option_id: str, default: Optional[int] = None):
        """Utility to fetch a custom option value if it exists."""
        option = getattr(self, "options_custom", {}).get(option_id)
        if option is None:
            return default
        return option.get("value", default)

    def get_measurement(self):
        """Poll the Alicat and populate measurement channels."""
        if self.instrument is None:
            self.initialize_input()

        self.return_dict = copy.deepcopy(measurements_dict)

        try:
            snapshot = read_mfc_snapshot(self.instrument)
        except Exception as exc:  # pragma: no cover - requires hardware
            self.logger.exception("Failed to read Alicat registers: %s", exc)
            return self.return_dict

        if self.is_enabled(0):
            self.value_set(0, snapshot["volumetric_flow"])
        if self.is_enabled(1):
            self.value_set(1, snapshot["mass_flow"])
        if self.is_enabled(2):
            self.value_set(2, snapshot["pressure"])
        if self.is_enabled(3):
            self.value_set(3, snapshot["temperature"])
        if self.is_enabled(4):
            self.value_set(4, snapshot["setpoint"])

        return self.return_dict
