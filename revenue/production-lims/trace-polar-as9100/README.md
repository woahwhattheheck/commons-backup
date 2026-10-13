# TRACE-POLAR-AS9100 synthetic evidence rail

Demand: `trace-polar-as9100-lims-01`

A synthetic/read-only traveler and QMS evidence reconciliation package for the posted Polar Semiconductor AS9100 build demand. It binds each synthetic wafer traveler step to an approved revision identifier, calibration evidence, operator-signoff presence, measurement-evidence pointer, QMS reference, and immutable source hash. It stages an evidence pack for named-human disposition and never changes a traveler, QMS/NCR record, recipe, instrument, or production state.

## Frozen acceptance

The signed fixture expands deterministically to three synthetic wafers and 36 traveler steps:

- `W1 = REVIEW_READY`;
- `W2 = HOLD_REVISION` because one step uses `R3` where the fixture approves `R4`;
- `W3 = HOLD_CAL_AND_SIGNATURE` because one measurement cites expired calibration and another step has a blank operator signoff;
- exactly three exception rows and three evidence packs;
- every evidence pack carries all 12 source-step hashes and a deterministic trace-matrix/evidence-pack digest;
- full replay adds zero packs, exceptions, or events and leaves state/audit hashes unchanged;
- only a non-reserved two-token named human can disposition the review-ready pack, and that operation returns an unsent copy; held packs cannot be approved; automatic disposition is disabled.

Run:

```text
python -m unittest -v test_trace_polar_as9100.py
python -m py_compile trace_polar_as9100.py test_trace_polar_as9100.py
python trace_polar_as9100.py
```

## Boundary

Synthetic/mock read-only evidence only. The `R4` revision, calibration validity, signoffs, and all identifiers are fixture-only evidence assertions, not process specifications or fabrication guidance. No live QMS, NCR, traveler, recipe, equipment, material, customer, production, disposition, certification, or reporting action occurs. This package makes no AS9100/IATF/ISO compliance or accreditation determination; real acceptance requires buyer-owned schemas, controls, and named human review.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
