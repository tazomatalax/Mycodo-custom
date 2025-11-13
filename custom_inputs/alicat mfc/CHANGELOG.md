## Changelog - Alicat Mass Flow Controller Input

### Version 1.0 (2025-01-14)

**Initial Release**

**Features:**
- Read volumetric flow rate from Alicat MFC via Modbus RTU
- Read mass flow rate in standard conditions
- Monitor absolute pressure
- Monitor gas temperature
- Read current active setpoint
- Configurable serial port and slave ID
- Automatic byte-order handling for IEEE 754 floats
- 8 float values from registers 1349-1364

**Technical Details:**
- Serial configuration: 19200 baud, 8N2
- Modbus function code 3 (Read Holding Registers)
- Swapped register order conversion for float values
- 1-second timeout with automatic buffer clearing

**Dependencies:**
- minimalmodbus (Modbus RTU communication)
- pyserial (serial port handling)

**Compatibility:**
- Tested with Alicat MC-Series and MQ-Series controllers
- Compatible with any Alicat device supporting Modbus RTU
- Mycodo >= 8.0.0

**Notes:**
- Units configured for mL/min (milliliters per minute)
- Registers read provide real-time process values
- Lock file used to prevent concurrent serial access
