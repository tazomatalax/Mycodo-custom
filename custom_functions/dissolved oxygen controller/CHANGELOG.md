## Changelog - DO Control (Air MFC)

### Version 1.0 (2025-01-14)

**Initial Release**

**Features:**
- PID-based dissolved oxygen control using air mass flow controller
- Direct control logic (air raises DO)
- Configurable Kp, Ki, Kd gains for tuning
- Min/max flow rate limits for safety
- Measurement timeout protection (stops flow if sensor fails)
- Real-time logging of PID components and control variables
- Compatible with any Mycodo Input providing DO measurements
- Compatible with Alicat MFC outputs

**Default Settings:**
- DO Setpoint: 8.0 mg/L
- Kp: 10.0 (proportional gain)
- Ki: 0.5 (integral gain)
- Kd: 0.1 (derivative gain)
- Min Flow: 0.0 mL/min
- Max Flow: 500.0 mL/min
- Update Period: 30 seconds
- Max Measurement Age: 120 seconds

**Control Logic:**
```python
# Direct mode: lower DO → more air
error = current_DO - setpoint
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
- Tested with Hamilton ARC DO probes
- Tested with Alicat MC/MQ series MFCs
- Mycodo >= 8.0.0

**Logging Output Example:**
```
INFO - DO Control: Current=7.85 mg/L, Setpoint=8.00 mg/L, Error=-0.15, Air Flow=45.2 mL/min
DEBUG - PID Components: P=-1.50, I=-0.08, D=-0.02
```

**Use Cases:**
- Bioreactor DO control
- Fermenter oxygen management
- Aquaculture DO regulation
- Any application requiring air/O2-based DO control

**Notes:**
- Air/O2 addition raises DO
- Gas transfer is slower than pH response
- Requires adequate sparging/mixing for efficiency
- Can use pure O2 for faster response and higher concentrations
- Start with default gains and tune based on system response
- Monitor initially to ensure stable control
