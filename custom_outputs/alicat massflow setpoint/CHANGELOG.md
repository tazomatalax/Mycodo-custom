## Changelog - Alicat Mass Flow Controller Output

### Version 1.0 (2025-01-14)

**Initial Release**

**Features:**
- Write flow setpoint to Alicat MFC via Modbus RTU
- Value-type output accepting numeric setpoints
- Automatic verification by reading back setpoint status
- On/off control (off sets setpoint to 0)
- Compatible with Mycodo PID controllers
- Status reporting based on actual setpoint value

**Technical Details:**
- Serial configuration: 19200 baud, 8N2
- Write to register 1009 (Register Numbers 1010-1011)
- Read confirmation from register 1349 (setpoint status)
- Modbus function codes: 16 (write) and 3 (read)
- Swapped register order conversion for float values
- 1-second timeout with automatic buffer clearing

**Control Logic:**
- `output_switch(state='on', amount=X)` → writes X mL/min
- `output_switch(state='off')` → writes 0 mL/min
- `is_on()` → returns True if setpoint > 0.1 mL/min
- `is_setup()` → returns True if initialized

**Dependencies:**
- minimalmodbus (Modbus RTU communication)
- pyserial (serial port handling)

**Compatibility:**
- Tested with Alicat MC-Series and MQ-Series controllers
- Compatible with any Alicat device supporting Modbus RTU register 1009
- Mycodo >= 8.0.0

**Bug Fixes from Development:**
- Fixed incorrect setpoint register (1349 is read-only, 1009 is write command)
- Added output_channel parameter to output_switch()
- Implemented all required abstract methods
- Added channels_dict definition for value output type
- Renamed initialize_output() to initialize()

**Notes:**
- Units configured for mL/min (milliliters per minute)
- Setpoint writes confirmed by reading back register 1349
- Lock file used to prevent concurrent serial access
- Off button functionality sets flow to 0 for safety
