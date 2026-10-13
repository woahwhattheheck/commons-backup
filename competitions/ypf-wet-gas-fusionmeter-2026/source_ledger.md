# FusionMeter source ledger

This ledger separates **public precedent** from **FusionMeter-specific evidence**. A cited paper may support a physical mechanism; it does not validate this implementation at YPF.

## S1 — YPF / Innocentive public challenge (primary opportunity authority)

URL: https://www.innocentive.com/challenges/improving-wet-gas-measurement-accuracy-across-industry-standard-flow-meters/

Checked: 2026-09-13.

Supports: $25,000 opportunity; deadline 2026-10-12 23:59 US Eastern; current YPF meter families (Orifice Plate/AGA 3, Coriolis/AGA 11, Ultrasonic/AGA 9); 60–85 kg/cm² and 30–60°C envelope; wet-gas measurement error discussion; target around ±3% with ~±2% preferred; <=15 psi ΔP; 24/7/reliability, standards, online transmission and POC-support requirements; one strong meter-family solution acceptable; TRL 3–6 invited; form fields; solely-generative-AI warning; non-exclusive IP rights for award.

Does **not** support: FusionMeter performance, FusionMeter TRL acceptance, safety approval, implementation cost, owner experience, award/payment.

## S2 — ISO/TR 11583:2012 (current technical report page)

URL: https://www.iso.org/standard/50609.html

ISO page states the report covers wet-gas measurement by differential-pressure devices, including Venturi/orifice, and was reviewed/confirmed in 2022. The abstract notes wet gas at ~95%+ gas volume fraction and that information such as pressure-loss measurement can be sufficient in some wet-gas evaluations.

Supports: DP-meter wet-gas correction is a recognized metrology problem; pressure loss is a legitimate auxiliary observable; applicability ranges matter.

Does **not** support: applying a universal ISO equation outside its stated ranges, or claiming FusionMeter meets YPF ±3%.

## S3 — Nasr et al., 2026, third pressure tap for liquid detection/quantification in an orifice meter

URL: https://www.sciencedirect.com/science/article/pii/S0955598626001688

Public abstract/indexed text describes an experimental study using an industry-standard orifice meter plus a third downstream pressure tap. It reports that liquid presence causes orifice over-reading, that PLR rises with liquid loading, and that beta ratio and gas/liquid density ratio materially affect the PLR-to-loading relation. The study discusses 120 tests for a fitted liquid-loading relation.

Supports: the specific FusionMeter architecture seam—permanent-pressure-loss/PLR observation added to an existing orifice point—and the need for beta/density-aware calibration.

Does **not** support: transplanting that paper's coefficients to YPF without checking applicability; FusionMeter accuracy at YPF.

## S4 — Devices and methods for wet gas flow metering: comprehensive review (2024 journal issue)

URL: https://www.sciencedirect.com/science/article/pii/S0955598623002145

Supports: wet-gas over-reading, meter-family differences, importance of PLR/liquid-loading observability and limited applicability ranges for individual correlations.

## S5 — Standard-orifice wet-gas correction study (Sensors, 2021; open PMC copy)

URL: https://pmc.ncbi.nlm.nih.gov/articles/PMC8036351/

Supports: liquid droplets increase DP and apparent gas flow for standard orifices; over-reading correction is experimentally studied; Lockhart–Martinelli liquid-loading concepts are commonly used.

## S6 — Orifice pressure-loss ratio theoretical work (Measurement, 2025)

URL: https://www.sciencedirect.com/science/article/abs/pii/S0263224125000466

Supports: dry-gas PLR prediction accuracy matters because wet-gas corrections use deviation from dry PLR; PLR is also an established diagnostic observable.

## Claim ceiling

Until a representative POC produces immutable, reviewable source data, these sources justify **why the design is worth testing**, not that it has already achieved the challenge target.
