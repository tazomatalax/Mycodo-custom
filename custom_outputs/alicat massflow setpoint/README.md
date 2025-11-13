#### Custom Output: Alicat Mass Flow Controller Setpoint Control (Modbus RTU)

Version 1.0

#### About

This Output module controls the setpoint of Alicat Mass Flow Controllers via Modbus RTU serial communication. It provides a value-type output that allows Mycodo automations, PID controllers, or manual commands to dynamically adjust the flow rate.

The module writes setpoint commands to register 1009 (Register Numbers 1010-1011) which is the designated read/write setpoint command register for Alicat controllers. It then reads back the confirmation from register 1349 to verify the setpoint was accepted.

#### Features

- **Dynamic Setpoint Control** - Write flow setpoints in real-time
- **Value Output Type** - Accepts numeric setpoint values
- **Verification** - Reads back actual setpoint after writing
- **On/Off Control** - Off state sets setpoint to 0
- **PID Integration** - Compatible with Mycodo PID controllers
- **Status Monitoring** - Reports on/off state based on actual flow setpoint

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
   - Note the maximum flow range for your device

#### Software Setup

1. **Import Module:**
   - Navigate to `[Gear Icon] → Configure → Custom Outputs`
   - Click "Import Custom Output"
   - Upload `alicat_mfc_output.py`

2. **Add Output:**
   - Go to `Setup → Output`
   - Select "Mass Flow Controller (Setpoint Control)"
   - Configure:
     - **UART Device**: Serial port path (e.g., `/dev/ttyUSB0`)
     - **Slave ID**: Modbus address (1-247, typically 1)
     - **Output Name**: Descriptive name (e.g., "CO2 Flow Controller")

3. **Activate:**
   - Click "Add" to create the output
   - Output is now ready for manual or automated control

#### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| UART Device | Serial port path for Modbus communication | `/dev/ttyUSB0` |
| Slave ID | Modbus slave address (1-247) | 1 |

#### Using the Output

**Manual Control:**
1. Go to `Data → Output`
2. Find your MFC output
3. Enter setpoint value in mL/min
4. Click "Turn On" to send the setpoint

**PID Control:**
1. Go to `Setup → Function`
2. Add a PID controller
3. Select your MFC as the "Output"
4. Configure PID gains and setpoint

**Conditional/Function Control:**
1. Create a conditional or function
2. Add action "Execute Output"
3. Select your MFC and enter desired value

**API Control:**
```python
import requests

url = f'https://{pi_ip}/api/outputs/{output_id}'
headers = {'X-API-KEY': 'your-api-key'}
data = {'state': True, 'amount': 50.0}  # 50 mL/min
response = requests.post(url, json=data, headers=headers, verify=False)
```

#### Technical Details

**Serial Configuration:**
- Baud Rate: 19200
- Data Bits: 8
- Parity: None
- Stop Bits: 2
- Timeout: 1.0 second

**Modbus Register Map:**
- **Write Register**: 1009-1010 (Register Numbers 1010-1011)
- **Read Register**: 1349-1350 (setpoint status readback)
- **Function Code**: 16 (Write Multiple Registers) and 3 (Read Holding Registers)
- **Data Format**: IEEE 754 32-bit floats with swapped register order

**Control Behavior:**
- `state='on', amount=X` → Sets setpoint to X mL/min
- `state='off'` → Sets setpoint to 0 mL/min
- `is_on()` → Returns True if setpoint > 0.1 mL/min

**Register Details:**
According to Alicat Modbus documentation:
- Register Numbers 1010-1011 (addresses 1009-1010): Read/Write setpoint command
- Register Numbers 1350-1351 (addresses 1349-1350): Current setpoint status (read-only)

The module writes the desired setpoint to register 1009, then reads back register 1349 to confirm the controller accepted the command.

#### Troubleshooting

**Module Won't Import:**
- Verify Python syntax: `python3 -m py_compile alicat_mfc_output.py`
- Check Mycodo logs: `tail -f /var/log/mycodo/mycodo.log`

**Output Not Responding:**
- Verify output is added (not just activated)
- Check serial connection and wiring
- Verify Modbus slave ID matches controller
- Test with direct Modbus command

**Setpoint Not Applied:**
- Ensure controller is not in local control mode
- Verify register 1009 is writable on your controller model
- Check for Modbus timeout or checksum errors in logs
- Confirm value is within controller's rated range (0 to max flow)

**"Unconfigured" Status:**
- For value outputs, this just means setpoint is 0
- Use the "On" button with a value to set a non-zero setpoint
- Or use the "Off" button to explicitly set to 0

#### Integration Examples

**pH Control with CO2:**
Use the pH Control (CO2 MFC) function:
1. Go to `Setup → Function`
2. Add "pH Control (CO2 MFC)"
3. Select pH sensor as input
4. Select this MFC output for CO2
5. Configure PID gains and max flow limit

**DO Control with Air:**
Use the DO Control (Air MFC) function:
1. Go to `Setup → Function`
2. Add "DO Control (Air MFC)"
3. Select DO sensor as input
4. Select this MFC output for Air
5. Configure PID gains and max flow limit

**Flow Ramp Control:**
Create a custom function to gradually ramp flow:
```python
# Gradually increase from 0 to 100 mL/min over 10 minutes
for i in range(0, 101, 10):
    self.control.output_on(output_id, amount=i)
    time.sleep(60)  # Wait 1 minute between steps
```

**Safety Shutoff:**
Create a conditional to stop flow if sensor fails:
1. Go to `Setup → Conditional`
2. Condition: pH sensor inactive for > 5 minutes
3. Action: Set MFC output to 0 (off)

#### Safety Considerations

1. **Set Appropriate Limits:**
   - When using with PID controllers, always set max flow limits
   - Ensure limits match your process safety requirements

2. **Monitor Sensor Health:**
   - Use conditionals to stop flow if sensors fail
   - Set measurement timeout in controller functions

3. **Test Before Deployment:**
   - Verify setpoint range matches your application
   - Test emergency stop procedures
   - Confirm flow measurements match setpoints

4. **Startup/Shutdown Behavior:**
   - Configure startup state (typically "Off")
   - Configure shutdown state (typically "Off" for safety)

#### Related Modules

- **Alicat MFC Input** - Monitor flow, pressure, and temperature
- **pH Control (CO2 MFC)** - Automated pH control using this output
- **DO Control (Air MFC)** - Automated DO control using this output

#### License

GPL v3 (consistent with Mycodo)

#### Support

For issues or questions:
- Review Mycodo logs: `/var/log/mycodo/mycodo.log`
- Check serial connection and Modbus configuration
- Verify register 1009 is writable (consult Alicat manual)
- Post to Mycodo forums or GitHub issues
