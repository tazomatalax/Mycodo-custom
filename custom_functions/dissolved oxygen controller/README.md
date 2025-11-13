#### Custom Function: DO Control using Air Mass Flow Controller

Version 1.0

#### About

This Function implements PID-based control for maintaining a dissolved oxygen (DO) setpoint by regulating air flow through an Alicat Mass Flow Controller. The controller automatically adjusts air/O2 dosing to keep DO stable in bioreactors, fermenters, or aquaculture systems.

Air increases DO, so the controller uses **direct** control logic: when DO is too low, it increases air flow; when DO is at or above setpoint, it reduces flow.

#### Features

- **PID-based Control** - Smooth, precise DO regulation with configurable gains
- **Safety Limits** - Min/max flow limits prevent over-aeration
- **Measurement Timeout** - Stops air flow if DO sensor fails or becomes stale
- **Real-time Logging** - Detailed debug output showing PID components
- **Integration Ready** - Works seamlessly with Hamilton DO probes and Alicat MFCs

#### Requirements

- Mycodo >= 8.0.0
- DO sensor configured as Mycodo Input (e.g., Hamilton DO Probe)
- Alicat MFC configured as Mycodo Output (for air/O2)
- Python package: `simple-pid` (auto-installed on import)

#### Hardware Setup

1. **DO Sensor:**
   - Install and configure DO probe (e.g., Hamilton ARC DO)
   - Ensure probe is calibrated
   - Add as Input in Mycodo and verify readings

2. **Air Mass Flow Controller:**
   - Connect Alicat MFC to air/O2 source
   - Configure as Output in Mycodo using `alicat_mfc_output.py`
   - Verify manual control works before enabling PID

3. **System Integration:**
   - Plumb air line into bioreactor/fermenter
   - Use sparger or diffuser for efficient gas transfer
   - Ensure adequate mixing for oxygen dissolution

#### Software Setup

1. **Import Function:**
   - Navigate to `[Gear Icon] → Configure → Custom Functions`
   - Click "Import Custom Function"
   - Upload `do_control_air_mfc.py`

2. **Add Function:**
   - Go to `Setup → Function`
   - Select "DO Control (Air MFC)"
   - Configure (see Configuration section below)

3. **Activate:**
   - Click "Activate" to start PID control
   - Monitor in Dashboard and logs

#### Configuration Options

##### Measurement Settings
| Option | Description | Default |
|--------|-------------|---------|
| DO Measurement | Select DO sensor input | (required) |
| Max Age (seconds) | Stop if measurement older than this | 120 |

##### Output Settings
| Option | Description | Default |
|--------|-------------|---------|
| Air Mass Flow Controller | Select Alicat MFC output | (required) |

##### Control Settings
| Option | Description | Default |
|--------|-------------|---------|
| DO Setpoint (mg/L) | Target DO value to maintain | 8.0 |
| Period (seconds) | How often to update controller | 30.0 |

##### PID Gains
| Option | Description | Default |
|--------|-------------|---------|
| Kp (Proportional) | Immediate response to error | 10.0 |
| Ki (Integral) | Eliminates steady-state error | 0.5 |
| Kd (Derivative) | Dampens oscillations | 0.1 |

##### Flow Limits
| Option | Description | Default |
|--------|-------------|---------|
| Minimum Air Flow (mL/min) | Lower flow limit | 0.0 |
| Maximum Air Flow (mL/min) | Upper flow limit (safety) | 500.0 |

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
   - Use defaults: Kp=10.0, Ki=0.5, Kd=0.1
   - Set max flow to safe value for your system

2. **Observe Response:**
   - Watch DO graph for 30-60 minutes
   - Check logs for PID output values

3. **Adjust Incrementally:**
   - Too slow? → Increase Kp by 20-50%
   - Oscillating? → Decrease Kp or increase Kd
   - Offset from setpoint? → Increase Ki
   - Overshoots badly? → Increase Kd

**Example Configurations:**

**Bioreactor (High Sensitivity):**
```
DO Setpoint: 8.5 mg/L
Kp: 15.0, Ki: 1.0, Kd: 0.2
Max Air: 1000 mL/min
Period: 15s
```

**Fermenter (Moderate):**
```
DO Setpoint: 6.0 mg/L
Kp: 8.0, Ki: 0.3, Kd: 0.05
Max Air: 500 mL/min
Period: 30s
```

**Aquaculture (Conservative):**
```
DO Setpoint: 7.0 mg/L
Kp: 5.0, Ki: 0.2, Kd: 0.05
Max Air: 200 mL/min
Period: 60s
```

#### Safety Features

1. **Measurement Timeout:**
   - If DO reading is older than "Max Age", flow stops
   - Prevents runaway aeration if sensor fails

2. **Flow Limits:**
   - Hard limits on min/max prevent over-aeration
   - PID output is clamped within bounds

3. **Graceful Shutdown:**
   - When deactivated, air flow set to 0
   - No runaway aeration

4. **Error Handling:**
   - Missing measurements trigger flow shutdown
   - All errors logged for debugging

#### Monitoring

**View Controller Status:**
- Check `More → Daemon Log` for detailed output:
```
DO Control: Current=7.85 mg/L, Setpoint=8.00 mg/L, Error=-0.15, Air Flow=45.2 mL/min
  PID Components: P=-1.50, I=-0.08, D=-0.02
```

**Dashboard Widgets:**
Create graphs to visualize:
- DO measurement over time
- Air flow rate over time
- Both on same graph to see relationship

**Alerts:**
Create conditionals for:
- DO out of acceptable range
- Air flow at maximum (sustained)
- DO sensor inactive/stale

#### Troubleshooting

**Controller oscillates around setpoint:**
- Decrease Kp (e.g., 10.0 → 5.0)
- Increase Kd (e.g., 0.1 → 0.2)
- Increase update period (e.g., 30s → 45s)

**Slow to reach setpoint:**
- Increase Kp (e.g., 10.0 → 15.0)
- Increase Ki (e.g., 0.5 → 1.0)

**Persistent offset from setpoint:**
- Increase Ki (e.g., 0.5 → 1.0)
- Verify air flow is sufficient (not at max limit)

**"No measurement available" errors:**
- Check DO sensor is active and reporting
- Verify max age setting is appropriate
- Review DO sensor logs for errors

**Flow stays at 0 or max:**
- Check PID gains aren't too extreme
- Verify setpoint is achievable with available air flow
- Ensure min/max flow settings are appropriate

**DO Response Too Slow:**
- DO transfer is slower than pH (gas transfer limited)
- Increase Kp for faster response
- Consider using pure O2 instead of air for faster response
- Ensure adequate mixing/sparging

#### Technical Details

**Control Algorithm:**
Uses `simple-pid` library with direct mode:
```
error = current_DO - setpoint
output = Kp * error + Ki * ∫error + Kd * (d/dt)error
flow_rate = clamp(output, min_flow, max_flow)
```

**Update Cycle:**
1. Wait for `period` seconds
2. Retrieve latest DO measurement
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
   - pH Control (CO2 MFC) → companion function
   - DO Control (Air MFC) → this function

4. **Dashboard:**
   - Line graph: pH + CO2 flow
   - Line graph: DO + Air flow
   - Gauges: Current pH, current DO

#### Physical Considerations

**Gas Transfer Efficiency:**
- Use fine bubble spargers for maximum transfer
- Higher pressure increases dissolution rate
- Temperature affects O2 solubility
- Consider pure O2 for high-demand applications

**System Design:**
- Air flow rate depends on vessel volume and O2 consumption
- Typical ranges: 0.1-2.0 VVM (volumes per volume per minute)
- Ensure adequate headspace pressure relief
- Monitor for excessive foaming

#### Related Modules

- **Hamilton DO Probe Input** - DO sensor readings
- **Alicat MFC Output** - Air/O2 flow control
- **pH Control (CO2 MFC)** - Companion function for pH
- **Temperature Control** - Complete bioreactor control

#### License

GPL v3 (consistent with Mycodo)

#### Support

For issues or questions:
- Review Mycodo daemon logs for PID output
- Check DO sensor is working correctly
- Verify Air MFC responds to manual commands
- Start with conservative PID gains and tune gradually
- Consider gas transfer limitations in tuning
- Post to Mycodo forums or GitHub issues
