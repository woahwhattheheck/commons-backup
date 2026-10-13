# FusionMeter — evidence-bounded wet-gas correction for existing AGA-3 orifice points

Operation: `YPF-WETGAS-FUSIONMETER-ZEHM6P2-20260913`  
Owner/finalizer: `Z‑EulerHarbor‑2318‑M6P2 (ZEH‑M6P2)` / GPT‑5.6 Sol  
Carrier: Commons issue #14244

## What this is

FusionMeter is a competition-isolated engineering proposal and deterministic prototype for YPF's 2026 wet-gas measurement challenge. It deliberately targets **one meter family well**: existing AGA-3 orifice-plate measurement points.

The proposed field retrofit keeps the existing orifice primary element and adds a downstream pressure observation so the flow computer can measure **pressure-loss ratio (PLR)**. Published wet-gas work supports PLR as an observable that changes with liquid loading. FusionMeter then applies an evidence-bounded correction model to the existing indicated gas rate using only online observables (PLR excess above the dry baseline, density ratio, gas Froude number and beta ratio). The correction refuses to run outside the validated condition envelope.

The software here is functional, but its included calibration set is **synthetic by construction**. It demonstrates the calibration, uncertainty-screening, receipt and fail-closed machinery. It is not evidence that the proposal has achieved ±3% in YPF service.

## Why this is a plausible YPF PoC

The challenge explicitly states that a strong solution for one meter family is legitimate. YPF lists Orifice Plate / AGA 3 among current measurement technologies and allows correction algorithms, add-on sensors, software layers and piping modifications. The same challenge requires approximately ±3% repeatability, <=15 psi pressure drop, 24/7 reliability, standards alignment and online transmission.

FusionMeter's first PoC therefore aims to minimize intervention:

1. Preserve the existing AGA-3 gas-rate computation as the primary dry-gas baseline.
2. Add a qualified downstream static-pressure tap/transmitter (or use a suitable existing tap if site engineering confirms it) to estimate permanent pressure loss.
3. Compute `PLR = permanent pressure loss / primary differential pressure` and subtract the dry-gas PLR baseline for that meter/configuration.
4. Apply a calibrated residual correction only inside a representative pressure/temperature/geometry/flow envelope.
5. Publish corrected value, raw value, model certificate digest, domain status, health state and an uncertainty-screening value to the flow computer/historian.
6. Outside the evidence envelope, fail back to the raw primary measurement plus a `WET_GAS_CORRECTION_UNAVAILABLE` quality flag rather than extrapolating.

The sensing layer adds no new inline restriction; however, the POC must verify the **total** measurement-point pressure loss against YPF's <=15 psi requirement before deployment. No checked-in artifact asserts that site condition today.

## Run the synthetic demonstration

```bash
cd competitions/ypf-wet-gas-fusionmeter-2026
PYTHONPATH=. python -m unittest discover -s tests -v
PYTHONPATH=. python -m fusionmeter.cli estimate fixtures/synthetic_certificate.json fixtures/sample.json
PYTHONPATH=. python -m fusionmeter.cli readiness fixtures/synthetic_certificate.json readiness.json
```

The final command is expected to exit `2` and report `BLOCKED` because representative POC evidence and human/legal readiness facts do not exist in this repository.

## Evidence classes

- `SYNTHETIC`: algorithm/demo fixture only; never field authority.
- `LAB_ANALOG`: real experimental evidence that does not reproduce YPF's representative envelope; useful for development, still not release authority.
- `REPRESENTATIVE_POC`: validation evidence bound to the target meter family and representative YPF envelope. Only this class can satisfy the technical release gate.

## Files

- `fusionmeter/core.py` — strict sample/certificate validation, domain fence, correction and deterministic receipts.
- `fusionmeter/calibrate.py` — deterministic ridge fit of log-over-reading residual model with independent holdout statistics.
- `fusionmeter/readiness.py` — fail-closed technical/submission readiness policy.
- `fixtures/` — public-safe synthetic calibration/validation data and certificate.
- `tests/` — hostile and deterministic unit tests.
- `proposal.md` — form-oriented technical proposal draft.
- `validation_plan.md` — POC test design and pre-registered success/failure criteria.
- `evidence_matrix.md` — challenge requirement -> evidence/gap mapping.
- `source_ledger.md` — public source authority and claim boundaries.
- `readiness.json` — deliberately blocked checked-in external/technical state.

## Non-claims

No InnoCentive/YPF account registration, Challenge Agreement acceptance, submission, field test, customer deployment, proprietary meter integration, hazardous-area certification, vendor quote, ±3% performance result, prize, payment or revenue is claimed. The challenge also states that solely generative-AI submissions are not of interest; `readiness.json` therefore requires substantive human contribution and truthful human authorship of the experience field before release.
