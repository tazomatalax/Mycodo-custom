#### Custom Input: Hamilton DO Probe (Modbus RTU)

Version 1.0

#### About

This Input module reads dissolved oxygen (DO) and temperature measurements from Hamilton ARC DO probes via Modbus RTU serial communication. Hamilton ARC (Adaptive Real-time Control) sensors provide high-accuracy measurements with digital Modbus RTU communication for industrial and laboratory applications.

The module uses a specialized byte-order conversion for Hamilton's Modbus implementation, reading from registers 2089 (DO) and 2409 (temperature).

#### Measurements

- **Dissolved Oxygen** - DO concentration in mg/L
- **Temperature** - Probe temperature in °C

#### Requirements

- Mycodo >= 8.0.0
- Hamilton DO probe with Modbus RTU capability (ARC series)
- USB-RS485 adapter (e.g., FTDI-based)
- Python packages (pre-installed in Mycodo):
  - `minimalmodbus` - Modbus RTU communication
  - `pyserial` - Serial port handling

#### Hardware Setup

1. **Connect USB-RS485 Adapter:**
   - Connect the RS-485 adapter to a Raspberry Pi USB port
   - Identify the serial device (typically `/dev/ttyUSB0`)

2. **Wire RS-485 Connection:**
   - Connect adapter A/B terminals to probe's Modbus terminals
   - Ensure proper polarity (A to A, B to B)
   - Add 120Ω termination resistor if at end of bus

3. **Configure Probe:**
   - Set probe to Modbus RTU mode
   - Configure serial settings: 19200 baud, 8N2
   - Note the Slave ID (typically 1)

#### Software Setup

1. **Import Module:**
   - Navigate to `[Gear Icon] → Configure → Custom Inputs`
   - Click "Import Custom Input"
   - Upload `hamilton_do_input.py`

2. **Add Input:**
   - Go to `Setup → Input`
   - Select "DO Probe (Telemetry)"
   - Configure:
     - **UART Device**: Serial port path (e.g., `/dev/ttyUSB0`)
     - **Baud Rate**: 19200 (default, change if probe configured differently)
     - **Period**: Measurement interval in seconds (recommended: 5-30s)

3. **Activate:**
   - Click "Activate" to start reading measurements
   - View data on Dashboard or Live Measurements page

#### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| UART Location | Serial port path for Modbus communication | `/dev/ttyUSB0` |
| Baud Rate | Modbus communication speed | 19200 |
| Period | Measurement interval in seconds | 5 |

#### Technical Details

**Serial Configuration:**
- Baud Rate: 19200 (configurable)
- Data Bits: 8
- Parity: None
- Stop Bits: 2
- Timeout: 1.0 second

**Modbus Register Map:**
- **DO Register**: 2089 (10 registers read)
- **Temperature Register**: 2409 (10 registers read)
- **Function Code**: 3 (Read Holding Registers)
- **Data Format**: 32-bit float with Hamilton-specific byte order

**Byte Order Conversion:**
Hamilton probes use a unique register layout:
```python
# Read 10 registers starting at base address
registers = instrument.read_registers(register_start, 10, functioncode=3)

# Combine registers 2 and 3 to form 32-bit value
int_value = (registers[3] << 16) | registers[2]

# Convert to little-endian bytes and interpret as float
bytes_value = int_value.to_bytes(4, 'little')
float_value = struct.unpack('f', bytes_value)[0]
```

#### Troubleshooting

**Module Won't Import:**
- Verify Python syntax: `python3 -m py_compile hamilton_do_input.py`
- Check Mycodo logs: `tail -f /var/log/mycodo/mycodo.log`

**Serial Communication Errors:**
- Verify device exists: `ls -la /dev/ttyUSB*`
- Check permissions: `sudo usermod -a -G dialout mycodo`
- Test serial connection with minimalmodbus directly

**No Measurements Recorded:**
- Confirm input is activated in Mycodo
- Check serial connection and wiring
- Verify Modbus slave ID (typically 1 for Hamilton probes)
- Review logs for timeout or checksum errors

**Incorrect DO Values:**
- Verify probe is calibrated
- Check barometric pressure compensation settings
- Ensure byte-order conversion matches your probe model
- Consult Hamilton documentation for your specific probe

**Temperature Reading Issues:**
- Ensure probe has integrated temperature sensor
- Verify register 2409 is supported on your probe model
- Check probe firmware version

#### Integration Examples

**Dashboard DO Monitoring:**
Create a gauge showing current DO:
1. Go to `Setup → Dashboard`
2. Add "Gauge" widget
3. Select "Dissolved Oxygen" measurement
4. Set min/max range (e.g., 0 to 10 mg/L)

**DO Control with Air:**
Use DO readings to control air/O2 flow:
1. Go to `Setup → Function`
2. Add "DO Control (Air MFC)" function
3. Select this DO probe as measurement input
4. Configure Air MFC as output
5. Set desired DO setpoint and PID gains

**DO Alert:**
Send notification if DO drops too low:
1. Go to `Setup → Conditional`
2. Add condition: Dissolved Oxygen < 5.0 mg/L
3. Add action: Send email notification or activate alarm

**Data Logging:**
Log DO data for compliance/analysis:
1. DO data automatically logged to InfluxDB
2. Export via `More → Data Query`
3. Or integrate with external systems via REST API

**Bioreactor Control:**
Combine with other sensors for full bioreactor control:
- DO probe → Air MFC control
- pH probe → CO2/base MFC control
- Temperature sensor → Heater/chiller control

#### Calibration

**Note:** This module reads values from the probe but does not perform calibration. Calibrate the probe using:
- Hamilton's proprietary software
- Probe's built-in calibration interface
- Third-party Modbus configuration tools

Typical calibration procedure:
1. Zero calibration (nitrogen or zero-oxygen solution)
2. Span calibration (air-saturated water at known temperature)
3. Verify readings in Mycodo match expected values

#### Specifications

**Typical Hamilton ARC DO Probe Specs:**
- DO Range: 0-20 mg/L (0-200% saturation)
- Accuracy: ±0.1 mg/L
- Temperature Range: 0-50°C
- Response Time: < 60 seconds (90% in water)
- Communication: Modbus RTU over RS-485

#### Related Modules

- **Hamilton pH Probe Input** - pH monitoring
- **DO Control (Air MFC)** - Automated DO control using air/O2
- **Alicat MFC Output** - Control air/O2 flow for DO regulation

#### License

GPL v3 (consistent with Mycodo)

#### Support

For issues or questions:
- Review Mycodo logs: `/var/log/mycodo/mycodo.log`
- Check serial connection and Modbus configuration
- Consult Hamilton probe manual for register details
- Verify probe firmware supports Modbus RTU
- Post to Mycodo forums or GitHub issues
