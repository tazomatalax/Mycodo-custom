# Changelog

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
- Independent and coupled dual-pump control (GPIO 3 & GPIO 4).
- Operating range clamps (min/max flow rates) for Octanoic Acid and Ammonium Sulfate.
- Two-stage fed-batch automation: Phase 2 Exponential Feed + Phase 3 pH-Stat Carbon Feed.
- Real-time volume tracking and live HTML status display.
