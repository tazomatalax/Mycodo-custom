## Changelog - pH Control (CO2 MFC)

### Version 1.0 (2025-01-14)

**Initial Release**

**Features:**
- PID-based pH control using CO2 mass flow controller
- Reverse control logic (CO2 lowers pH)
- Configurable Kp, Ki, Kd gains for tuning
- Min/max flow rate limits for safety
- Measurement timeout protection (stops flow if sensor fails)
- Real-time logging of PID components and control variables
- Compatible with any Mycodo Input providing pH measurements
- Compatible with Alicat MFC outputs

**Default Settings:**
- pH Setpoint: 7.0
- Kp: 1.0 (proportional gain)
- Ki: 0.1 (integral gain)
- Kd: 0.05 (derivative gain)
- Min Flow: 0.0 mL/min
- Max Flow: 100.0 mL/min
- Update Period: 30 seconds
- Max Measurement Age: 120 seconds

**Control Logic:**
```python
# Reverse mode: higher pH → more CO2
error = setpoint - current_pH
output = PID(error)
flow = clamp(output, min_flow, max_flow)
```

**Safety Features:**
- Automatic shutoff if measurement stale/missing
- Flow clamping to configured limits
- Graceful stop on deactivation (flow → 0)
- Exception handling with logging

**Dependencies:**
- simple-pid (auto-installed on import)

**Compatibility:**
- Tested with Hamilton ARC pH probes
- Tested with Alicat MC/MQ series MFCs
- Mycodo >= 8.0.0

**Logging Output Example:**
```
INFO - pH Control: Current=7.23, Setpoint=7.00, Error=0.23, CO2 Flow=15.3 mL/min
DEBUG - PID Components: P=0.23, I=0.05, D=0.02
```

**Use Cases:**
- Bioreactor pH control
- Fermenter pH regulation
- Aquaculture pH management
- Any application requiring CO2-based pH control

**Notes:**
- CO2 addition lowers pH (acid effect)
- Requires adequate mixing for CO2 dissolution
- Start with default gains and tune based on system response
- Monitor initially to ensure stable control
