# Starbucks Cold Cup 2026 — ClearFiber Shell

This directory is a **submission-development package**, not evidence that a finished material meets Starbucks' requirements and not a record of external submission.

## What is here

- `proposal.md` — form-ready technical draft, with the Experience field intentionally blocked for truthful human input.
- `requirements-matrix.md` — every Starbucks requirement mapped to current evidence and the test needed to close it.
- `evidence-ledger.md` — precise scientific/regulatory precedents and claim boundaries.
- `validation-plan.md` — staged falsification, forming, regulatory, compostability, scale and LCA work.
- `readiness.json` — deliberately `unverified` release state.
- `readiness_gate.py` — strict validator that refuses READY until every hard gate has a real evidence reference and external-submission/identity/eligibility authority is explicit.
- `test_readiness_gate.py` — hostile regressions.

## Concept in one sentence

**ClearFiber Shell** is a dense, plastic-free CNF/chitosan physical network with the minimum continuous purified-shellac surface barrier needed for wet service, processed without chlorine bleach and screened first against Starbucks' unusually strict `ASTM D1003 haze <= 5%` target.

## Evidence boundary

Published work supports:
- high wet strength and visible transparency in CNF/chitosan nanopaper;
- strong water-barrier improvement from shellac coatings on cellulose;
- a plausible FDA starting point for purified shellac;
- a BPI assessment path for eligible fiber-based packaging without thermoplastic lamination.

Published work **does not** establish that this final cup/lid meets Starbucks' full specification. In particular, haze <=5%, 24-hour leak performance, 1 m filled-drop survival, espresso heat deformation, organoleptics, BPI compostability, final food-contact authorization, scale and LCA remain unproven until tested on the frozen article.

## Local verification

```bash
python -m unittest -v test_readiness_gate.py
python readiness_gate.py readiness.json
```

Expected checked-in result: tests pass; `readiness.json` prints `BLOCKED` and exits 2.

## External-action boundary

No Innocentive account registration, Challenge Agreement acceptance, submission, IP assignment, award claim, or Starbucks contact is performed by this package. The challenge states that submissions produced solely with generative AI are not of interest; this gate therefore requires a documented substantive human contribution plus truthful experience before release.
