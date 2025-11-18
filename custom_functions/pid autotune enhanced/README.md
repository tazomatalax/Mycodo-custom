# PID Autotune v2

Enhanced PID controller autotuning function with progress tracking and continuous output support.

## Features

### Improvements over Original Autotune

1. **Progress Tracking**: Real-time progress measurements that can be graphed on dashboards
   - Progress percentage (0-100%)
   - Current state indicator
   - Elapsed time tracking

2. **Continuous Output Support**: Works with both output types:
   - **On/Off Outputs**: Heaters, pumps, relays (time-based control)
   - **Continuous Outputs**: Mass flow controllers, PWM, valves (value-based control)

3. **Bidirectional Control**: Supports both raising and lowering
   - Raise: heating, aeration, alkalization
   - Lower: cooling, de-aeration, acidification

4. **Pre-flight Testing**: Optional validation that output affects measurement before starting

5. **Configurable Parameters**: 
   - Adjustable convergence tolerance
   - Configurable maximum cycles
   - Tunable lookback window

6. **Better Diagnostics**: Detailed logging with failure analysis and recommendations

## How It Works

Uses the **Relay Feedback Method** (Åström-Hägglund):

1. Oscillates the output around the setpoint
2. Detects peaks in the measurement response
3. Calculates ultimate gain (Ku) and period (Pu) from stable oscillations
4. Applies multiple tuning rules to generate PID parameters

### Tuning Rules Provided

- **ziegler-nichols**: Classic aggressive tuning
- **tyreus-luyben**: Less aggressive, better for lag-dominant systems
- **ciancone-marlin**: Balanced response
- **pessen-integral**: Strong integral action
- **some-overshoot**: Allows 10-20% overshoot
- **no-overshoot**: Conservative, minimal overshoot
- **brewing**: Specialized for brewing/fermentation (slow systems)

## Configuration

### Basic Setup

1. **Measurement**: Select the process variable (temperature, DO, pH, etc.)
2. **Output**: Select the actuator (heater, MFC, pump, etc.)
3. **Output Type**: Choose on/off or continuous
4. **Direction**: Raise or lower
5. **Setpoint**: Target value to oscillate around

### Critical Parameters

**Sample Period**: How often to read and update (match your intended PID period)
- Typical: 15-60 seconds
- Fast systems: 5-15 seconds  
- Slow systems: 30-120 seconds

**Noise Band**: Deadband around setpoint
- Start with measurement noise × 2-3
- Temperature: 0.3-1.0°C typical
- DO: 0.2-0.5 mg/L typical
- pH: 0.05-0.2 typical

**Output Step**:
- **On/Off**: Seconds on per period (e.g., 10s out of 30s = 33% duty cycle)
- **Continuous**: Output value (e.g., 250 mL/min for MFC, 50% for PWM)

### Advanced Parameters

**Lookback Window**: Time window for peak detection
- Should be > expected oscillation period
- Slow systems: 120-300 seconds
- Fast systems: 30-90 seconds

**Convergence Tolerance**: Stricter = takes longer but more accurate
- Default: 0.10 (10%)
- Strict: 0.05 (5%)
- Loose: 0.15 (15%)

**Maximum Cycles**: Safety limit
- Default: 30 peaks
- Increase for slow/noisy systems: 40-50

## Usage Examples

### Example 1: DO Control with Alicat MFC

```
Measurement: Hamilton DO Probe (dissolved oxygen)
Output: Alicat Air MFC
Output Type: Continuous
Direction: Raise (air increases DO)

Setpoint: 8.0 mg/L
Sample Period: 30 seconds
Noise Band: 0.3 mg/L
Output Step: 250.0 mL/min (test value for oscillations)
Output Min: 0.0
Output Max: 500.0
Lookback: 120 seconds
```

### Example 2: Temperature Control with Heater

```
Measurement: Temperature Sensor
Output: Heating Element
Output Type: On/Off
Direction: Raise

Setpoint: 37.0°C
Sample Period: 30 seconds
Noise Band: 0.5°C
Output Step: 15.0 seconds (on for 15s out of 30s period)
Output Min: 0
Output Max: 30 (max = period)
Lookback: 90 seconds
```

### Example 3: pH Control with Acid Pump

```
Measurement: pH Probe
Output: Acid Dosing Pump
Output Type: On/Off
Direction: Lower (acid lowers pH)

Setpoint: 7.0
Sample Period: 60 seconds
Noise Band: 0.1
Output Step: 3.0 seconds
Output Min: 0
Output Max: 60
Lookback: 180 seconds
```

## Monitoring Progress

Add a graph to your dashboard with the following:

1. **Your Process Variable** (temperature, DO, pH, etc.)
2. **PID Autotune v2 > Progress (%)** - shows 0-100% completion
3. **PID Autotune v2 > State** - shows current state:
   - 0 = Off
   - 1 = Stepping Up
   - 2 = Stepping Down
   - 3 = Succeeded
   - 4 = Failed
4. **Your Output** (to see oscillations)

## Troubleshooting

### "No measurement available"
- Check that input/sensor is working
- Verify measurement is recent (within max age)

### "Pre-flight: Small change detected"
- Increase output step
- Wait longer between cycles (increase sample period)
- Check output is connected and working

### Autotune Never Completes
- System too noisy: increase noise band or convergence tolerance
- System too slow: increase max cycles and lookback window
- External disturbances: isolate system during autotune

### "Autotune Failed"
Common causes:
- **Output too weak**: Can't reach setpoint - increase output step
- **Setpoint unreachable**: Choose a setpoint the system can actually reach
- **Too much noise**: Increase noise band
- **System unstable**: Too many external disturbances
- **Wrong direction**: Check that direction matches output behavior

### Results Look Wrong
- Verify output type is correct (on/off vs continuous)
- Check direction setting (raise vs lower)
- Ensure sample period matches what you'll use for PID
- Try different tuning rules (start with tyreus-luyben or no-overshoot)

## Integration with DO Controller

This autotune function is specifically designed to work with the DO Control (Air MFC) function:

1. **Run Autotune**:
   - Select same DO measurement
   - Select same MFC output
   - Set continuous output type
   - Use a reasonable test flow (e.g., 200-300 mL/min)
   - Set DO setpoint to target value

2. **Wait for Completion**: Monitor progress on dashboard (10-60 minutes typical)

3. **Apply Results**: Copy PID gains from daemon log to DO Control function
   - Try "tyreus-luyben" first (less aggressive)
   - Or "no-overshoot" for very stable control
   - Or "ziegler-nichols" for faster response

4. **Fine-tune**: Adjust gains ±20% based on actual performance

## Notes

- Autotune should run in a stable environment (minimal disturbances)
- Disconnect other controllers affecting the same measurement
- Takes 15-60 minutes typically (3-6 oscillations needed)
- Pre-flight test recommended to catch configuration errors early
- Results are starting points - fine-tuning may be needed
- Different tuning rules optimize for different objectives (speed vs stability)

## Version History

See CHANGELOG.md
