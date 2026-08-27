# Changelog

## [1.2.0] - 2026-08-20

### Added
- **Live Feed Rate Trimming & Foam Mitigation**: Real-time multiplier (`feed_rate_scale`) and quick UI commands (`Trim -10%`, `Trim +10%`, `Quick Foam Backoff (-25%)`, `Reset Trim`) allowing dynamic feed adjustment during foaming or non-standard growth without controller restart.
- **Stage 3 Overfeed / Runaway Safety Clamp**: Added `stage3_max_rate_clamp_ml_h` enforcing a strict maximum on cumulative Pump A feed dosed within any rolling 1-hour window, preventing toxicity and foam flares caused by sensor drift.
- **Persistent Runtime State Management**: Full DB persistence for `stage_start_time`, `is_paused`, `feed_rate_scale`, and `stage3_pulses`, ensuring stage elapsed time and feeding profiles are preserved when users edit settings in the Mycodo web UI during an active run.
- **7 L Bench-Scale Parameter Mapping**: Pre-configured defaults for 7 L scale ($V_0 = 5.0\text{ L}$, $500\text{ g/L}$ nitrogen stock, concentrated carbon stock, $\mu = 0.268\text{ h}^{-1}$, $F_{0,A} = 8.08\text{ mL/h}$, $F_{0,B} = 3.01\text{ mL/h}$, $T = 6.13\text{ h}$, Stage 3 N cutoff).

## [1.1.0] - 2026-08-20

### Added
- **Stoichiometric Mass Balance Engine**: Derived initial feed rates ($F_{0,A}, F_{0,B}$), dynamic feeding ratio ($R_{A:B}$), and target nitrogen mass from first principles ($V_0, X_0, X_{\text{target}}, Y_{X/S}, Y_{X/N}, S_{i,A}, N_{i,B}, \mu, m_S$).
- **Physiological Stage Transitions**: Automated Stage 2 $\rightarrow$ Stage 3 transition based on cumulative nitrogen delivered reaching target cell mass demand, online DO spike, or elapsed time.
- **Dynamic C:N & Trickle Nitrogen Support**: Added `trickle_nitrogen` policy in Stage 3 to supply low maintenance nitrogen, preventing cellular metabolic arrest and sustaining carbon assimilation.
- **Volume-Adaptive Feedback Dosing**: Pulse volume in Stage 3 scales dynamically with working liquid volume $V(t)/V_0$.
- **Broth Volume and Biomass Tracking**: Live state tracking of $V(t)$, estimated $X(t)$, and cumulative delivered elemental masses ($M_C, M_N$).

## [1.0.0] - 2026-08-20

### Added
- Initial release of `pha_fedbatch_controller.py` for Mycodo.
- Independent and coupled dual-pump control.
- Operating range clamps (min/max flow rates) for primary substrate and co-feed.
- Two-stage fed-batch automation: Phase 2 Exponential Feed + Phase 3 Feedback Dosing.
- Real-time volume tracking and live HTML status display.

