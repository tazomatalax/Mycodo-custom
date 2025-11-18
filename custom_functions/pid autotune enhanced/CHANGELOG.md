# Changelog - PID Autotune v2

## [1.0.0] - 2025-11-18

### Added
- Initial release of enhanced PID autotune function
- Progress tracking with three measurement channels:
  - Progress percentage (0-100%)
  - Current state (0=off, 1=up, 2=down, 3=success, 4=fail)
  - Elapsed time in seconds
- Support for continuous outputs (MFC, PWM, valves)
- Support for on/off outputs (relays, pumps, heaters)
- Bidirectional control (raise and lower modes)
- Pre-flight testing to validate output affects measurement
- Configurable convergence tolerance
- Configurable maximum cycles
- Configurable lookback window
- Enhanced logging with cycle-by-cycle progress
- Detailed completion summary with all tuning rules
- Failure diagnostics with troubleshooting suggestions
- Seven tuning rule options:
  - Ziegler-Nichols (classic)
  - Tyreus-Luyben (less aggressive)
  - Ciancone-Marlin (balanced)
  - Pessen Integral (strong integral)
  - Some Overshoot (allows overshoot)
  - No Overshoot (conservative)
  - Brewing (slow systems)

### Features
- Works with DO control and mass flow controllers
- Real-time progress visible on dashboards
- Automatic output shutoff on completion or failure
- Thread-safe deactivation
- Respects output min/max limits
- Handles missing measurements gracefully

### Design
- Based on Åström-Hägglund relay feedback method
- Improved peak detection algorithm
- Adaptive progress estimation
- State machine architecture for reliability
- Clean separation between autotune logic and Mycodo integration

### Documentation
- Comprehensive README with examples
- Troubleshooting guide
- Configuration recommendations
- Integration guide for DO controller
