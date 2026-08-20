# Changelog

## [1.2.0] - 2026-08-20

### Added
- **Live Feed Rate Trimming & Foam Mitigation**: Added `feed_rate_scale` multiplier and dedicated web UI action buttons (`Trim Feed -10%`, `Trim Feed +10%`, `Foam Backoff (-25%)`, and `Reset Trim (100%)`) to instantly throttle or boost feeding in real time without pausing or recalculating.
- **Robust State Persistence**: Preserved `stage_start_time`, `is_paused`, `stage3_pulses`, and `feed_rate_scale` across Mycodo daemon restarts and web UI option edits, preventing reset of elapsed feed time ($t=0$).
- **Stage 3 Hourly Acid Safety Clamp**: Added `stage3_max_rate_clamp_ml_h` rolling 1-hour dosage limit to protect cultures from toxic acid accumulation or foam runaway if pH sensor drifts.
- **7 L Bench-Scale Parameter Mapping**: Updated default option parameters to match the 7 L ($V_0 = 5.0\text{ L}$) bench-scale bioprocess ($500\text{ g/L } (\text{NH}_4)_2\text{SO}_4$, neat octanoic acid, $\mu = 0.268\text{ h}^{-1}$, $F_{0,A}=8.08\text{ mL/h}$, $F_{0,B}=3.01\text{ mL/h}$, Stage 3 N cutoff).
- **Enhanced Status Card**: Real-time display of feed trim percentage, rolling 1-hour acid consumption, stage elapsed times, and safety clamp status.

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
- Operating range clamps (min/max flow rates) for Octanoic Acid and Ammonium Sulfate.
- Two-stage fed-batch automation: Phase 2 Exponential Feed + Phase 3 pH-Stat Carbon Feed.
- Real-time volume tracking and live HTML status display.
