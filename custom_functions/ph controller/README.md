#### Custom Function: pH Control using CO2 Mass Flow Controller

Version 1.0

#### About

This Function implements PID-based control for maintaining a pH setpoint by regulating CO2 flow through an Alicat Mass Flow Controller. The controller automatically adjusts CO2 dosing to keep pH stable in bioreactors, fermenters, or aquaculture systems.

CO2 lowers pH, so the controller uses **reverse** control logic: when pH is too high, it increases CO2 flow; when pH is at or below setpoint, it reduces flow.

#### Features

- **PID-based Control** - Smooth, precise pH regulation with configurable gains
- **Safety Limits** - Min/max flow limits prevent over-dosing
- **Measurement Timeout** - Stops CO2 flow if pH sensor fails or becomes stale
- **Real-time Logging** - Detailed debug output showing PID components
- **Integration Ready** - Works seamlessly with Hamilton pH probes and Alicat MFCs

#### Requirements

- Mycodo >= 8.0.0
- pH sensor configured as Mycodo Input (e.g., Hamilton pH Probe)
- Alicat MFC configured as Mycodo Output (for CO2)
- Python package: `simple-pid` (auto-installed on import)

#### Hardware Setup

1. **pH Sensor:**
   - Install and configure pH probe (e.g., Hamilton ARC pH)
   - Ensure probe is calibrated
   - Add as Input in Mycodo and verify readings

2. **CO2 Mass Flow Controller:**
   - Connect Alicat MFC to CO2 source
   - Configure as Output in Mycodo using `alicat_mfc_output.py`
   - Verify manual control works before enabling PID

3. **System Integration:**
   - Plumb CO2 line into bioreactor/fermenter
   - Ensure adequate mixing for CO2 dissolution
   - Consider using sparger or diffuser for efficiency

#### Software Setup

1. **Import Function:**
   - Navigate to `[Gear Icon] → Configure → Custom Functions`
   - Click "Import Custom Function"
   - Upload `ph_control_co2_mfc.py`

2. **Add Function:**
   - Go to `Setup → Function`
   - Select "pH Control (CO2 MFC)"
   - Configure (see Configuration section below)

3. **Activate:**
   - Click "Activate" to start PID control
   - Monitor in Dashboard and logs

#### Configuration Options

##### Measurement Settings
| Option | Description | Default |
|--------|-------------|---------|
| pH Measurement | Select pH sensor input | (required) |
| Max Age (seconds) | Stop if measurement older than this | 120 |

##### Output Settings
| Option | Description | Default |
|--------|-------------|---------|
| CO2 Mass Flow Controller | Select Alicat MFC output | (required) |

##### Control Settings
| Option | Description | Default |
|--------|-------------|---------|
| pH Setpoint | Target pH value to maintain | 7.0 |
| Period (seconds) | How often to update controller | 30.0 |

##### PID Gains
| Option | Description | Default |
|--------|-------------|---------|
| Kp (Proportional) | Immediate response to error | 1.0 |
| Ki (Integral) | Eliminates steady-state error | 0.1 |
| Kd (Derivative) | Dampens oscillations | 0.05 |

##### Flow Limits
| Option | Description | Default |
|--------|-------------|---------|
| Minimum CO2 Flow (mL/min) | Lower flow limit | 0.0 |
| Maximum CO2 Flow (mL/min) | Upper flow limit (safety) | 100.0 |

#### PID Tuning Guide

**Default values work for most applications**, but you may need to tune for your specific system:

**Understanding PID Gains:**
- **Kp (Proportional):** Immediate response to current error
  - Higher Kp = faster response but more oscillation
  - Lower Kp = slower response but more stable
  
- **Ki (Integral):** Eliminates steady-state error over time
  - Higher Ki = faster correction of persistent errors
  - Lower Ki = slower correction, more stable
  
- **Kd (Derivative):** Dampens oscillations and overshoots
  - Higher Kd = more damping, less overshoot
  - Lower Kd = less damping, more oscillation

**Tuning Process:**

1. **Start Conservative:**
   - Use defaults: Kp=1.0, Ki=0.1, Kd=0.05
   - Set max flow to safe value for your system

2. **Observe Response:**
   - Watch pH graph for 30-60 minutes
   - Check logs for PID output values

3. **Adjust Incrementally:**
   - Too slow? → Increase Kp by 20-50%
   - Oscillating? → Decrease Kp or increase Kd
   - Offset from setpoint? → Increase Ki
   - Overshoots badly? → Increase Kd

**Example Configurations:**

**Bioreactor (Aggressive):**
```
pH Setpoint: 7.0
Kp: 2.0, Ki: 0.3, Kd: 0.1
Max CO2: 50 mL/min
Period: 20s
```

**Aquaculture (Conservative):**
```
pH Setpoint: 7.5
Kp: 0.5, Ki: 0.05, Kd: 0.02
Max CO2: 30 mL/min
Period: 60s
```

#### Safety Features

1. **Measurement Timeout:**
   - If pH reading is older than "Max Age", flow stops
   - Prevents runaway dosing if sensor fails

2. **Flow Limits:**
   - Hard limits on min/max prevent over-dosing
   - PID output is clamped within bounds

3. **Graceful Shutdown:**
   - When deactivated, CO2 flow set to 0
   - No runaway dosing

4. **Error Handling:**
   - Missing measurements trigger flow shutdown
   - All errors logged for debugging

#### Monitoring

**View Controller Status:**
- Check `More → Daemon Log` for detailed output:
```
pH Control: Current=7.23, Setpoint=7.00, Error=0.23, CO2 Flow=15.3 mL/min
  PID Components: P=0.23, I=0.05, D=0.02
```

**Dashboard Widgets:**
Create graphs to visualize:
- pH measurement over time
- CO2 flow rate over time
- Both on same graph to see relationship

**Alerts:**
Create conditionals for:
- pH out of acceptable range
- CO2 flow at maximum (sustained)
- pH sensor inactive/stale

#### Troubleshooting

**Controller oscillates around setpoint:**
- Decrease Kp (e.g., 1.0 → 0.5)
- Increase Kd (e.g., 0.05 → 0.1)
- Increase update period (e.g., 30s → 45s)

**Slow to reach setpoint:**
- Increase Kp (e.g., 1.0 → 1.5)
- Increase Ki (e.g., 0.1 → 0.2)

**Persistent offset from setpoint:**
- Increase Ki (e.g., 0.1 → 0.3)
- Verify CO2 flow is sufficient (not at max limit)

**"No measurement available" errors:**
- Check pH sensor is active and reporting
- Verify max age setting is appropriate
- Review pH sensor logs for errors

**Flow stays at 0 or max:**
- Check PID gains aren't too extreme
- Verify setpoint is achievable with available CO2 flow
- Ensure min/max flow settings are appropriate

#### Technical Details

**Control Algorithm:**
Uses `simple-pid` library with reverse mode:
```
error = setpoint - current_pH
output = Kp * error + Ki * ∫error + Kd * (d/dt)error
flow_rate = clamp(output, min_flow, max_flow)
```

**Update Cycle:**
1. Wait for `period` seconds
2. Retrieve latest pH measurement
3. Calculate PID output
4. Clamp output to min/max flow limits
5. Send flow setpoint to MFC
6. Log status

**Thread Safety:**
- Runs in separate thread managed by Mycodo daemon
- Uses thread-safe database and output control methods

#### Integration Example

**Complete Bioreactor Setup:**

1. **Inputs:**
   - Hamilton pH Probe → pH readings
   - Hamilton DO Probe → DO readings
   - Temperature sensor → temp monitoring

2. **Outputs:**
   - Alicat MFC #1 → CO2 for pH control
   - Alicat MFC #2 → Air for DO control

3. **Functions:**
   - pH Control (CO2 MFC) → this function
   - DO Control (Air MFC) → companion function

4. **Dashboard:**
   - Line graph: pH + CO2 flow
   - Line graph: DO + Air flow
   - Gauges: Current pH, current DO

#### Related Modules

- **Hamilton pH Probe Input** - pH sensor readings
- **Alicat MFC Output** - CO2 flow control
- **DO Control (Air MFC)** - Companion function for DO
- **pH Control (Dual Output)** - Alternative using CO2 + base

#### License

GPL v3 (consistent with Mycodo)

#### Support

For issues or questions:
- Review Mycodo daemon logs for PID output
- Check pH sensor is working correctly
- Verify CO2 MFC responds to manual commands
- Start with conservative PID gains and tune gradually
- Post to Mycodo forums or GitHub issues
