# PID Autotune v2 - Quick Reference

## Quick Start for DO Control

1. **Install Function**
   - Copy `pid_autotune_v2` folder to Mycodo custom_functions
   - Restart Mycodo daemon

2. **Configure**
   ```
   Measurement:        Hamilton DO Probe
   Output:             Alicat Air MFC  
   Output Type:        Continuous
   Direction:          Raise
   
   Setpoint:           8.0 mg/L
   Sample Period:      30 seconds
   Noise Band:         0.3 mg/L
   Output Step:        250.0 mL/min
   Output Min:         0.0
   Output Max:         500.0
   ```

3. **Monitor**
   - Add graph with DO measurement, Progress %, State, and MFC output
   - Watch for oscillations around setpoint
   - Wait for State=3 (success) or State=4 (failed)

4. **Get Results**
   - Check Daemon Log for PID parameters
   - Look for "PID AUTOTUNE COMPLETE" section
   - Copy gains from preferred tuning rule

5. **Apply to DO Controller**
   - Use Tyreus-Luyben or No-Overshoot for stable control
   - Use Ziegler-Nichols for faster response
   - Fine-tune ±20% based on performance

## Parameter Guidelines

| System Speed | Sample Period | Lookback | Noise Band |
|--------------|---------------|----------|------------|
| Fast (seconds) | 5-15s | 30-60s | Small |
| Medium (minutes) | 15-60s | 60-180s | Medium |
| Slow (hours) | 60-300s | 180-600s | Large |

## Output Step Guidelines

**On/Off Outputs**: 
- Start with 33-50% duty cycle
- Temperature: 10-20s out of 30s period
- Pumps: 3-10s out of 30s period

**Continuous Outputs**:
- MFC: 30-50% of max flow
- PWM: 30-50% of full power  
- Valve: 30-50% open

## Common Issues

| Symptom | Solution |
|---------|----------|
| "Small change detected" | Increase output step by 50% |
| Takes > 1 hour | Increase max_cycles to 40-50 |
| Fails immediately | Check output type, direction, connections |
| Oscillations too large | Decrease output step |
| Never converges | Increase convergence tolerance to 0.15 |
| Measurement noisy | Increase noise band by 2x |

## States

- 0: Off (initializing)
- 1: Stepping Up (heating/aerating/alkalizing)
- 2: Stepping Down (cooling/reducing/acidifying)  
- 3: Succeeded (gains calculated)
- 4: Failed (see daemon log)

## Expected Duration

- Fast systems: 10-20 minutes (6-12 peaks)
- Medium systems: 20-40 minutes (8-16 peaks)
- Slow systems: 40-90 minutes (10-20 peaks)

## Safety

- Runs pre-flight test by default (disable with caution)
- Automatically stops output on completion
- Respects output min/max limits
- Handles missing measurements (stops output)
- Thread-safe deactivation

## Files

- `pid_autotune_v2.py` - Main function code
- `README.md` - Full documentation
- `CHANGELOG.md` - Version history
- `QUICK_REFERENCE.md` - This file
