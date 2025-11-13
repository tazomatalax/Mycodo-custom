## Changelog - Hamilton pH Probe Input

### Version 1.0 (2025-01-14)

**Initial Release**

**Features:**
- Read pH value from Hamilton ARC pH probe via Modbus RTU
- Read integrated temperature sensor value
- Hamilton-specific byte-order conversion for float values
- Configurable serial port and baud rate
- 10-register read pattern for robust data retrieval

**Technical Details:**
- Serial configuration: 19200 baud, 8N2
- Modbus function code 3 (Read Holding Registers)
- pH register: 2089
- Temperature register: 2409
- Custom byte-order: combines registers[3] and registers[2] as little-endian float
- 1-second timeout with automatic buffer clearing

**Byte Order Logic:**
```python
# Read 10 registers starting at base
registers = read_registers(start, 10)
# Extract 32-bit value from registers 2 and 3
int_value = (registers[3] << 16) | registers[2]
# Convert to little-endian float
float_value = struct.unpack('f', int_value.to_bytes(4, 'little'))[0]
```

**Dependencies:**
- minimalmodbus (Modbus RTU communication)
- pyserial (serial port handling)

**Compatibility:**
- Tested with Hamilton ARC pH sensors
- Compatible with Hamilton probes supporting Modbus RTU
- Mycodo >= 8.0.0

**Notes:**
- Units: pH (unitless), °C (Celsius)
- Calibration must be performed on the probe itself
- Module reads calibrated values from probe
- Slave ID typically 1 (configurable per probe)
