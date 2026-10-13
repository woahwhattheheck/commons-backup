# E-Jet Batch Provenance Gate

A buyer-neutral, deterministic evidence gate for one E-Jet batch. It turns a small JSON evidence packet into a machine-readable decision and a one-page PDF dossier without plant credentials, network access, or third-party packages.

This is a pilot artifact for the AirPlant-scale handoff problem: connect feedstock/electricity evidence, production accounting, assay/spec results, sustainability method/CI, and custody handoffs into one reproducible PASS/HOLD decision.

## What it checks

- positive feedstock input, non-negative electricity and output volumes;
- mass conservation within `max(0.5 L, 0.5% of feedstock)`;
- source protocol, assay spec/sample, and a `PASS` assay result;
- non-negative carbon intensity plus named sustainability method;
- required `production_release -> carrier_pickup -> buyer_receipt` stages;
- named owner and offset-aware RFC3339 timestamp for every required handoff;
- chronological handoff ordering and duplicate stage detection.

Any failed check yields `HOLD` plus stable reason codes. A clean packet yields `PASS`. Identical evidence produces identical JSON/PDF bytes and an evidence SHA-256, so a buyer, producer, or auditor can reproduce the decision independently.

## Run

```bash
python3 gate.py fixtures/pass_batch.json --out out
python3 gate.py fixtures/hold_missing_owner.json --out out || test $? -eq 2
python3 -m unittest discover -s tests -v
```

Exit code is `0` for PASS and `2` for HOLD. Output is `<batch>.decision.json` plus `<batch>.dossier.pdf`.

## Paid pilot boundary

A practical pilot uses **three real, redacted batches** and maps only evidence already produced by plant, carrier, buyer, lab, and sustainability workflows. Deliverables: three reproducible dossiers, source-to-handoff mapping, unresolved evidence gaps with owners, and an integration estimate. No live control-system or plant credential access is required to scope the pilot.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)
