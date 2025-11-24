# coding=utf-8
"""
Mycodo custom input module for Hamilton DO Probe.

Reads dissolved oxygen and temperature from a Hamilton DO probe via Modbus RTU.
"""

from __future__ import annotations

import copy
import logging
import struct
from typing import Dict, Optional

import minimalmodbus
import serial

from mycodo.inputs.base_input import AbstractInput
from mycodo.utils.lockfile import LockFile


# ===== Hamilton Common Functions =====
def setup_instrument(port: str, slave_address: int, baudrate: int = 19200, timeout: float = 2.0) -> minimalmodbus.Instrument:
    """Create and configure a Modbus RTU instrument for Hamilton probes."""
    instrument = minimalmodbus.Instrument(port, slaveaddress=slave_address, debug=False)
    instrument.serial.baudrate = baudrate
    instrument.serial.bytesize = 8
    instrument.serial.parity = serial.PARITY_NONE
    instrument.serial.stopbits = 2
    instrument.serial.timeout = timeout
    instrument.mode = minimalmodbus.MODE_RTU
    instrument.clear_buffers_before_each_transaction = True
    instrument.close_port_after_each_call = True
    return instrument


def read_float_value(instrument: minimalmodbus.Instrument, register_start: int, max_retries: int = 3, retry_delay: float = 0.1) -> float:
    """Read a floating point value from registers using Hamilton's byte order with retry logic."""
    import time
    
    last_exception = None
    for attempt in range(max_retries):
        try:
            values = instrument.read_registers(register_start, 10, functioncode=3)
            
            # Combine the register values to form 32-bit integer (Hamilton format)
            int_value = (values[3] << 16) | values[2]
            
            # Convert the 32-bit integer to bytes (little-endian)
            bytes_value = int_value.to_bytes(4, 'little')
            
            # Interpret the bytes as 32-bit float
            float_value = struct.unpack('f', bytes_value)[0]
            
            return float_value
        except (minimalmodbus.NoResponseError, minimalmodbus.InvalidResponseError, serial.SerialException) as e:
            last_exception = e
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            continue
    
    # If all retries failed, raise the last exception
    raise last_exception


# Register constants for Hamilton probes
DO_REGISTER = 2089
TEMP_REGISTER = 2409

# ===== End Hamilton Common Functions =====


measurements_dict = {
    0: {"measurement": "dissolved_oxygen", "unit": "mg_L"},
    1: {"measurement": "temperature", "unit": "C"},
}

INPUT_INFORMATION = {
    "input_name_unique": "hamilton_do_input",
    "input_manufacturer": "Hamilton",
    "input_name": "DO Probe (Telemetry)",
    "measurements_name": "Dissolved Oxygen/Temperature",
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
            "default_value": 5,
            "required": True,
            "name": "Modbus Address",
            "phrase": "RTU slave ID configured on the Hamilton DO probe.",
        }
    ],
}


class InputModule(AbstractInput):
    """Expose Hamilton DO probe telemetry as a Mycodo input."""

    def __init__(self, input_dev, testing: bool = False):
        super().__init__(input_dev, testing=testing, name=__name__)
        self.instrument = None
        self.logger = logging.getLogger(__name__)
        self.modbus_address = 5

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
        """Poll the Hamilton DO probe and populate measurement channels."""
        if self.instrument is None:
            self.initialize_input()

        self.return_dict = copy.deepcopy(measurements_dict)

        port = getattr(self.input_dev, "uart_location", "/dev/ttyUSB0")
        lock_file = f"/var/lock/mycodo_serial_{port.replace('/', '_')}.lock"
        lf = LockFile()
        if lf.lock_acquire(lock_file, timeout=5.0):
            try:
                import time
                
                if self.is_enabled(0):
                    do_value = read_float_value(self.instrument, DO_REGISTER)
                    self.value_set(0, do_value)
                
                # Small delay between readings to reduce bus contention
                if self.is_enabled(0) and self.is_enabled(1):
                    time.sleep(0.05)
                
                if self.is_enabled(1):
                    temp_value = read_float_value(self.instrument, TEMP_REGISTER)
                    self.value_set(1, temp_value)
            except Exception as exc:
                self.logger.error("Failed to read Hamilton DO probe after retries: %s", exc)
                self.instrument = None
            finally:
                lf.lock_release(lock_file)

        return self.return_dict
