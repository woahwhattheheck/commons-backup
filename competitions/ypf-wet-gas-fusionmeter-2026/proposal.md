# FusionMeter — YPF wet-gas challenge proposal draft

> **Draft / not submitted.** This file is structured around the public 2026 YPF/Innocentive form. Claims that require field evidence, owner experience, IP review or legal acceptance remain explicitly gated.

## 1. Participation type

**OWNER INPUT REQUIRED.** Select Individual / Organization / Organization owning IP / Partnering only after reviewing the Challenge Agreement and actual IP posture.

## 2. Solution level

**Proposed integrated solution: TRL 3 concept/prototype.** The physical principle—wet-gas over-reading in differential-pressure meters and use of permanent pressure loss / PLR as a liquid-loading observable—has prior experimental and standards support. The specific FusionMeter integration, calibration and YPF performance target have not yet been validated and must not be represented as field-proven.

## 3. Problem & Opportunity (form draft; <500 words)

YPF reports that wet gas can drive existing measurement uncertainty to approximately ±10%, while the target is approximately ±3% repeatability and approaches near ±2% are preferred. The challenge explicitly allows a strong answer for one meter family, so FusionMeter focuses first on YPF's installed **Orifice Plate / AGA-3** points rather than weakening the proposal with three shallow meter-specific models.

An orifice meter calibrated for clean single-phase gas tends to over-read gas rate when entrained liquid increases differential pressure. Published wet-gas metrology also shows that the **permanent pressure loss ratio (PLR)** across a DP meter changes with liquid loading. A 2026 experimental orifice-meter study specifically investigated a third downstream pressure tap as a way to detect and quantify wetness. This creates a practical retrofit seam: preserve the existing primary element and dry-gas computation, measure one additional pressure state, and use the combined observables to infer/correct liquid-induced over-reading.

FusionMeter proposes that seam as an evidence-bounded correction layer, not a universal black-box predictor. Each deployed model is tied to a calibration certificate covering meter beta ratio, pressure, temperature, density ratio, gas Froude number and observed PLR excess. The flow computer publishes the raw AGA-3 result alongside the correction, model identity, health state and domain status. If sensors fail or conditions leave the validated envelope, the correction refuses to extrapolate and the raw measurement is retained with a quality flag.

The point of difference is therefore **low intervention plus explicit measurement authority**: no separator replacement, no radioactive phase-fraction sensor, no new inline restriction, and no silent ML extrapolation. The proposed PoC is designed to test whether PLR-assisted correction can reduce error sufficiently across YPF's representative envelope while preserving 24/7 operability and auditable fallback behavior.

## 4. Solution Overview (form draft; <500 words)

### Field architecture

1. **Existing primary measurement** — retain the installed AGA-3 orifice plate, upstream/static pressure, temperature, differential-pressure transmitter and current flow-computer gas calculation.
2. **Permanent-loss observation** — add a qualified downstream pressure tap/transmitter far enough downstream for the site-specific permanent-loss measurement, subject to YPF piping/instrument review. If an existing suitable pressure point exists, reuse is preferred.
3. **Dry baseline** — establish the meter's dry/single-phase PLR reference by geometry plus dry-gas commissioning data.
4. **Wetness observable** — continuously compute wet PLR and `PLR_excess = PLR_wet - PLR_dry`. PLR excess is treated as a liquid-loading indicator, not as a direct liquid-rate truth outside its calibration.
5. **Physics-constrained residual correction** — calibrate a compact model against reference gas-rate tests using PLR excess, density ratio, gas Froude number and beta ratio. The model predicts only a non-negative wet-gas over-reading factor. Corrected gas rate = indicated gas rate / over-reading factor.
6. **Evidence envelope** — certificate bounds define the exact pressure, temperature, beta, density-ratio, Froude and PLR-excess region validated for use. Leaving any bound disables correction.
7. **Online quality channel** — transmit corrected rate, raw rate, quality/health, envelope status, screening uncertainty, and certificate hash to the existing flow computer/historian.

### Requirement alignment

The sensing concept introduces no new inline obstruction; total point ΔP still requires site verification against the <=15 psi criterion. No moving parts or radiation source are introduced. The AGA-3 primary computation is preserved rather than replaced, and a formal standards review remains a PoC gate. The design is compatible with redundant transmitters and watchdog logic for continuous service. A later adapter could apply the same certificate/authority pattern to Coriolis or ultrasonic meters, but those families are intentionally out of the first PoC.

## 5. Solution Feasibility (form draft; <500 words)

The proposal is anchored to known wet-gas behavior rather than an unbounded AI model. ISO/TR 11583 documents wet-gas measurement with differential-pressure devices and recognizes additional information such as pressure loss as a route to gas-flow evaluation. Recent reviews describe PLR as an industry-recognized observable related to liquid loading. Most directly, a 2026 experimental paper on an industry-standard orifice meter investigated a **third pressure tap** to measure permanent loss and back-calculate liquid loading; the paper notes strong dependence on beta ratio and gas/liquid density ratio, exactly why FusionMeter includes those terms and refuses extrapolation.

The repository contains a working deterministic prototype that fits a compact log-over-reading residual model, binds it to an evidence certificate, rejects sensor faults and out-of-envelope conditions, and emits a tamper-evident receipt. The checked-in calibration data are synthetic and therefore prove only software behavior. Their low held-out error is not cited as performance evidence.

The PoC converts the research precedent into a YPF-specific validation campaign. It first maps dry PLR and instrumentation uncertainty, then tests representative wet conditions across the disclosed 60–85 kg/cm² and 30–60°C envelope, relevant beta ratios and flow regimes. Calibration and validation runs are separated by whole runs/regimes rather than random point splits. A pre-registered validation gate requires representative independent evidence before the software can label a certificate `REPRESENTATIVE_POC`.

The project succeeds only if the final reference-comparison data support the required error/repeatability level and the site design satisfies total ΔP, reliability, hazardous-area, online-data and standards constraints. If the test does not meet these gates, FusionMeter remains a diagnostic/wetness alarm or is rejected; the software is intentionally built to make that failure visible.

## 6. Experience (form draft)

**HUMAN AUTHORSHIP REQUIRED — DO NOT AUTO-FILL.** Describe Bryce / submitting entity's truthful engineering, instrumentation, software, oil/gas, metrology, deployment and support experience only if personally verified. The release gate blocks while this field is not human-authored and substantiated.

## 7. Solution Risks and mitigations

| Risk | Consequence | Mitigation / falsification test |
|---|---|---|
| PLR/liquid-loading relation changes with beta, density ratio or regime | Biased correction | Include those terms; span actual site beta/pressure/flow regimes; refuse outside certificate bounds |
| Third-tap location does not reproduce lab PLR behavior | Poor observability | CFD/engineering tap review followed by dry/wet flow-loop A/B; reject location if sensitivity is inadequate |
| Condensate/water properties differ from analog fluids | Calibration transfer error | Use representative fluid-property matrix or verified surrogates; include density/viscosity sensitivity; field validation mandatory |
| DP transmitter drift or plugged impulse lines | False wetness/correction | Redundancy/health diagnostics, zero checks, plausibility against dry PLR, fail back to raw measurement |
| Transients / slugging | Model leaves steady wet-gas assumptions | Change-point/regime detector; freeze correction and flag quality during unsupported transient state |
| Model fits laboratory points but not sites | Commercial/accounting error | Independent holdout by complete regimes + site pilot; no extrapolation; raw and corrected values archived together |
| Existing point already near 15 psi limit | Requirement violation | Verify total process pressure loss before PoC; sensing concept itself adds no inline restriction but deployment is blocked if total limit fails |
| Cyber/integration outage | Loss of corrected channel | Local deterministic flow-computer implementation; no cloud dependency for correction; watchdog and raw AGA-3 fallback |

## 8. Schedule & Cost — budgetary PoC planning estimate, not vendor quote

| Phase | Duration | Deliverable | Budgetary range (USD) |
|---|---:|---|---:|
| 0. Site + standards design | 2 weeks | P&ID/tap survey, AGA-3 and hazardous-area review, test matrix | $8k–$15k |
| 1. Flow-loop characterization | 4–6 weeks | Dry baseline + representative wet matrix + reference data | $25k–$60k |
| 2. Retrofit + edge implementation | 3–4 weeks (overlap possible) | transmitters/manifold, flow-computer correction, historian quality tags | $15k–$35k |
| 3. Field POC | 6–8 weeks | parallel raw/corrected/reference record, 24/7 reliability observation | $20k–$40k |
| 4. Independent analysis + scale decision | 2 weeks | blinded validation, uncertainty/error report, deployment decision | $8k–$15k |
| **Planning total** | **~17–22 elapsed weeks with overlap** | **POC decision package** | **$76k–$165k** |

These are transparent planning ranges, not supplier quotes. They exclude site shutdown, extraordinary piping modification, travel, taxes, hazardous-area recertification and any reference facility charges not yet known. Before submission/POC authorization, YPF-specific quantities and at least budgetary vendor/facility quotes should replace assumptions.

For ~40 eventual points, the proposal should not invent a per-site price. Scale cost is best expressed as `40 × site hardware/installation + central engineering/validation`, populated after the first point establishes actual tap reuse, transmitter class, cable/IO, commissioning time and certification needs.

## 9. Online references

See `source_ledger.md`. Primary sources include the current YPF/Innocentive challenge page, ISO/TR 11583:2012 (confirmed current in 2022), the 2026 experimental third-pressure-tap orifice study, and peer-reviewed wet-gas measurement reviews/correction studies.
