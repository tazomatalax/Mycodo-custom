#### Custom Input: Alicat Mass Flow Controller (Modbus RTU)

Version 1.0

#### About

This Input module reads telemetry data from Alicat Mass Flow Controllers via Modbus RTU serial communication. It provides real-time monitoring of volumetric flow, mass flow, pressure, temperature, and current setpoint values.

The module uses the Modbus RTU protocol over RS-485 serial connection to communicate with Alicat devices. All measurements are read from the controller's primary data registers (1349-1364) which provide the most up-to-date process values.

#### Measurements

- **Volumetric Flow Rate** - Standard flow rate in mL/min
- **Mass Flow Rate** - Mass flow in standard mL/min (SCCM)
- **Pressure** - Absolute pressure in PSI
- **Temperature** - Gas temperature in °C
- **Setpoint** - Current active setpoint in standard mL/min

#### Requirements

- Mycodo >= 8.0.0
- Alicat Mass Flow Controller with Modbus RTU capability
- USB-RS485 adapter (e.g., FTDI-based)
- Python packages (pre-installed in Mycodo):
  - `minimalmodbus` - Modbus RTU communication
  - `pyserial` - Serial port handling

#### Hardware Setup

1. **Connect USB-RS485 Adapter:**
   - Connect the RS-485 adapter to a Raspberry Pi USB port
   - Identify the serial device (typically `/dev/ttyUSB0`)

2. **Wire RS-485 Connection:**
   - Connect adapter A/B terminals to controller's Modbus terminals
   - Ensure proper polarity (A to A, B to B)
   - Add 120Ω termination resistor if at end of bus

3. **Configure Controller:**
   - Set controller to Modbus RTU mode
   - Configure serial settings: 19200 baud, 8N2
   - Note the Slave ID (default is 1)

#### Software Setup

1. **Import Module:**
   - Navigate to `[Gear Icon] → Configure → Custom Inputs`
   - Click "Import Custom Input"
   - Upload `alicat_mfc_input.py`

2. **Add Input:**
   - Go to `Setup → Input`
   - Select "Mass Flow Controller (Telemetry)"
   - Configure:
     - **UART Device**: Serial port path (e.g., `/dev/ttyUSB0`)
     - **Slave ID**: Modbus address (1-247, typically 1)
     - **Period**: Measurement interval in seconds (recommended: 5-30s)

3. **Activate:**
   - Click "Activate" to start reading measurements
   - View data on Dashboard or Live Measurements page

#### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| UART Device | Serial port path for Modbus communication | `/dev/ttyUSB0` |
| Slave ID | Modbus slave address (1-247) | 1 |
| Period | Measurement interval in seconds | 5 |

#### Technical Details

**Serial Configuration:**
- Baud Rate: 19200
- Data Bits: 8
- Parity: None
- Stop Bits: 2
- Timeout: 1.0 second

**Modbus Register Map:**
- Base Address: 1349
- Register Count: 16 (8 float values)
- Function Code: 3 (Read Holding Registers)
- Data Format: IEEE 754 32-bit floats with swapped register order

**Register Layout:**
| Registers | Data | Unit |
|-----------|------|------|
| 1349-1350 | Setpoint | Device units |
| 1351-1352 | Valve Drive | % |
| 1353-1354 | Pressure | Device units |
| 1355-1356 | Secondary Pressure | Device units |
| 1357-1358 | Barometric Pressure | Device units |
| 1359-1360 | Temperature | °C |
| 1361-1362 | Volumetric Flow | Device units |
| 1363-1364 | Mass Flow | Device units |

#### Troubleshooting

**Module Won't Import:**
- Verify Python syntax: `python3 -m py_compile alicat_mfc_input.py`
- Check Mycodo logs: `tail -f /var/log/mycodo/mycodo.log`

**Serial Communication Errors:**
- Verify device exists: `ls -la /dev/ttyUSB*`
- Check permissions: `sudo usermod -a -G dialout mycodo`
- Test with standalone script: `python3 /opt/Mycodo/env/bin/python alicat_mfc_controller.py`

**No Measurements Recorded:**
- Confirm input is activated in Mycodo
- Check serial connection and wiring
- Verify Modbus slave ID matches controller
- Review logs for timeout or checksum errors

**Incorrect Values:**
- Ensure byte-order swapping is correct for your controller model
- Verify controller is in Modbus RTU mode (not ASCII)
- Check serial configuration matches controller settings

#### Integration Examples

**Dashboard Widget:**
Create a line graph showing flow rate over time:
1. Go to `Setup → Dashboard`
2. Add "Graph (Synchronous)" widget
3. Add measurement: "Volumetric Flow Rate"
4. Set time range (e.g., last 1 hour)

**PID Control:**
Use flow readings as input to a PID controller:
1. Go to `Setup → Function`
2. Add "PID Controller (Basic)"
3. Set Measurement to "Volumetric Flow Rate"
4. Configure setpoint and output actions

**Data Export:**
Export flow data for analysis:
1. Go to `More → Data Query`
2. Select "Volumetric Flow Rate" measurement
3. Set date range
4. Download CSV

#### Related Modules

- **Alicat MFC Output** - Control setpoint via Modbus
- **pH Control (CO2 MFC)** - PID controller for pH using CO2 MFC
- **DO Control (Air MFC)** - PID controller for dissolved oxygen

#### License

GPL v3 (consistent with Mycodo)

#### Support

For issues or questions:
- Review Mycodo logs: `/var/log/mycodo/mycodo.log`
- Check serial connection and Modbus configuration
- Consult Alicat controller manual for register details
- Post to Mycodo forums or GitHub issues
