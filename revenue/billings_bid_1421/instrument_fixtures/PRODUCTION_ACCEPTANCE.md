# Bid 1421 instrument integration — production acceptance

Measured decision: **NOT_READY**.

The landed 30-event mock pack remains the deterministic starting corpus. This extension adds a real, fail-closed production evidence gate; it does not relabel mock fixtures as live adapters.

## Evidence incorporated

- Official RFP/Attachment F: SHA-256 `667d3d260f28877ad41ca6313d03eaddf3e45ae278a995ebf72d78d144339882`.
- Addendum 1: exact City response labels `Metrohm Eco IC`, `Seivers M5310C`, `Seal Analytical AQ300`, and `Perkin Elmer PinAAcle 900Z`; Big Bang, two labs/shared instance, no migration, 5,000 samples/year, 6 named / 2–3 concurrent, iOS+Android, PowerBI.
- Addendum 2: cloud, six field samplers, one subcontract lab, and QA targets for control charts, batch QC, thermometer/pipet verification, maintenance, and temperature.
- Addendum 4: static workbook inspection found sheet `Permit= `, range `A1:AI1`, exactly 35 header fields, and no example rows.
- Addendum 5: CMDP 5–10 unique uploads/week; one plant and one NetDMR/month.
- Addendum 3: macro-enabled CMDP workbook. The connector marks it unsupported; it was not opened and no macros were executed.

Attachment hashes, exact targets, the 35-field NetDMR header, and known gaps are in `production_source_evidence.json`.

## Executable gate

`production_acceptance_requirements.json` defines 24 required gates:

- device identity, transport contract, de-identified payloads, schema/unit/method mapping;
- QC/calibration/error behavior, idempotency, order/replay, timeout-after-commit, amendment/quarantine;
- AquaTrace product RBAC/release separation, audit integrity, secret handling/encryption, authorized security assessment;
- cloud reproducibility, monitoring/SLOs, backup/restore, DR, mobile offline reconciliation;
- CMDP/NetDMR validation, capacity/concurrency, and release evidence.

These are AquaTrace product acceptance requirements only. They do not alter or gate the Commons Action Pad or any Commons write road.

`production_gate.py` requires every `SATISFIED` gate to carry immutable evidence references, SHA-256, verification method, exact passed assertions, verifier, and time. It rejects malformed evidence, secret-bearing evidence keys, assertion drift, and a false `PRODUCTION_READY` decision.

The checked-in `production_candidate_evidence.json` truthfully satisfies only official-source traceability:

```text
NOT_READY required=24 satisfied=1 unsatisfied=23
```

Exit codes: `0` ready, `2` valid but not ready, `1` invalid or inflated evidence.

## Run

```bash
python3 revenue/billings_bid_1421/instrument_fixtures/runner.py
python3 revenue/billings_bid_1421/instrument_fixtures/production_gate.py --json
python3 -m unittest -v \
  test_billings_bid_1421_instrument_fixtures.py \
  test_billings_bid_1421_instrument_production_gate.py
```

## Production blockers

No source supplies pH-meter/balance models, any firmware/software versions, vendor transport schemas, representative device payloads, source IDs, sequence/retry semantics, QC/error mappings, or device acceptance thresholds. No product build, production environment, or verified evidence exists for the remaining 23 gates. Addendum 3 remains safely unread, and Addendum 4 is a header-only template.

No new City/prospect contact, submission, form, price, spend, secret, production claim, certification/reference claim, policy change, or external-model use occurred in this lane.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
