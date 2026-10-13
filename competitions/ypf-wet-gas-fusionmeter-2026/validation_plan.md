# FusionMeter representative POC validation plan

## Objective

Determine whether a PLR-assisted correction layer on existing AGA-3 orifice points can satisfy YPF's wet-gas measurement target **without extrapolation** and while meeting reliability, pressure-drop, integration and safety constraints.

A software demonstration is not a validation result. The checked-in synthetic certificate must never be relabeled `REPRESENTATIVE_POC`.

## Pre-register before collecting POC results

Freeze and hash:

- target site/meter identifiers and beta ratios;
- reference instrument/method and traceability/calibration evidence;
- pressure/temperature/flow/liquid-loading test matrix;
- dry PLR baseline method;
- training versus held-out validation allocation by complete run/regime;
- correction feature set and fitting algorithm version;
- success metrics and stopping rules;
- data-exclusion rules decided before outcomes are seen.

## Representative envelope

Public challenge bounds that must be covered before technical release:

- pressure: **60–85 kg/cm²**;
- temperature: **30–60°C**;
- actual YPF orifice beta ratio(s) intended for deployment;
- gas/liquid density ratios representative of target streams;
- gas flow/Froude regimes actually encountered;
- wetness/liquid-loading range observed or deliberately bracketed for the target locations.

The challenge's composition definition of wet gas and site fluid properties should be used to design representative hydrocarbon/water surrogate or real-fluid tests. No fixture in this repo claims to reproduce those fluids.

## Phase A — instrumentation / dry baseline

1. Verify primary and downstream pressure transmitter ranges, uncertainty, time synchronization and response.
2. Map dry/single-phase PLR across pressure, temperature and flow before wet testing.
3. Quantify dry-baseline drift and repeatability.
4. Confirm total measurement-point pressure loss against the <=15 psi requirement.
5. Confirm the candidate downstream tap location is mechanically/safely suitable and provides stable permanent-loss sensitivity.

Failure to establish a repeatable dry PLR baseline stops the correction concept before wet calibration.

## Phase B — wet calibration matrix

Use a flow-loop/reference method able to independently establish gas rate and characterize liquid loading. Suggested design factors:

- pressure: low / mid / high points spanning 60–85 kg/cm²;
- temperature: low / mid / high spanning 30–60°C;
- each target beta ratio;
- multiple gas rates / Froude regimes;
- multiple liquid-loading levels from near-dry through the site's upper representative wet range;
- water-dominant and condensate-relevant property cases where safe/available.

Repeat selected points after intervening conditions to expose hysteresis/drift rather than only immediate repeatability.

## Phase C — independent validation

Do not randomly split adjacent samples from the same run. Hold out **complete runs/regimes** so validation measures transfer across operating states rather than sample duplication.

Minimum release policy in code:

- at least 60 independent representative validation points;
- p95 absolute gas-rate error <=3% versus reference;
- full 60–85 kg/cm² and 30–60°C support in the certificate;
- no use outside observed domain.

Additional recommended report metrics:

- mean signed error / systematic bias;
- p50/p90/p95/max absolute relative error;
- repeated-condition spread;
- error versus PLR excess, beta, density ratio, Froude, pressure and temperature;
- false wetness detection near dry baseline;
- correction-disable rate and causes.

The numerical release gate is a project decision criterion, not a claim that it is identical to a formal metrology uncertainty statement. A qualified measurement/standards review must define the final uncertainty budget and interpretation of YPF's ±3% requirement.

## Phase D — 24/7 field POC

Run raw and corrected streams in parallel; do **not** replace fiscal/accounting authority during POC.

Record continuously:

- raw AGA-3 gas rate;
- corrected candidate rate;
- primary DP and permanent pressure loss;
- pressure, temperature, density/composition inputs used;
- model certificate hash + software version;
- sensor/impulse-line health;
- in-domain/out-of-domain state;
- any reference/spot-check measurements;
- outages, restarts and maintenance interventions.

Current internal readiness gate asks for at least 720 continuous test hours and >=99.5% engineering availability before `READY`. Those are project gates, not a sponsor-authored threshold.

## Fail / pivot criteria

Stop or demote FusionMeter to diagnostic-only if:

- representative validation p95 remains >3%;
- dry PLR is not repeatable enough for stable wetness inference;
- correction error is strongly site-specific without a practical calibration procedure;
- added/total pressure loss or installation constraints violate the site requirement;
- safety/hazardous-area review rejects the tapping/instrument design;
- online integration or reliability cannot meet 24/7 needs.

A negative PoC is a valid engineering result. The code is intentionally designed so it cannot be papered over by changing a README claim.
