# UIOWA-102 — specialist outputs to common evidence register

Status: SYNTHETIC INTEGRATION ASSET / NOT A UNIVERSITY FINDING

This adapter consumes three sources that are actually merged on current Commons main and maps them into the existing UIOWA-023 evidence-register contract.

## Common target

Target register:
revenue/uiowa_rfq_18649_workshare/methodology/23-synthetic-evidence-register.csv

Target structural validator:
revenue/uiowa_rfq_18649_workshare/methodology/validate_23_evidence_register.py

The common schema has 22 required columns. The validator permits additional columns, so this adapter preserves source-specific data in five explicit extension fields instead of discarding it:

- source_component
- native_id
- synthetic
- source_sha256
- extensions_json

extensions_json contains the entire original native record plus component, native identifier, synthetic flag, and source SHA-256.

## Real merged source contracts

### Delivery

Source:
revenue/uiowa_rfq_18649_delivery_metrics/fixtures/synthetic_deployments.csv

Verified source blob on main when this adapter was authored:
8fac02fb9d947deed7df99d563ab05d949127793

Eight synthetic deployment records are mapped to ESS / DEP evidence items. The adapter does not turn single events into DORA population metrics or maturity claims.

### Security

Source:
revenue/uiowa_rfq_18649_security_event_review/fixtures/synthetic_events.json

Verified source blob:
3d988e919f9c395eeb08f8171f04cafaea3df143

Five synthetic event records are mapped to SEC evidence. Monitoring-only records remain monitoring-only. Missing review evidence becomes NO_EVIDENCE_OBSERVED / NOT_EVIDENCED rather than a fabricated security failure. Open actions remain open in extensions_json.

### AI

Current merged source:
revenue/uiowa_rfq_18649_synthetic_collection/facts.json

Verified source blob:
d715a392b92b4738070552f7cecb8f32a4ddc765

This is the AI-readiness slice of the merged UIOWA-091 synthetic evidence corpus. It is used because the dedicated AI specialist kits were still being built when UIOWA-102 was implemented. The adapter does not pretend otherwise.

Six ai_readiness facts are mapped to AI evidence. UIOWA-091 strength/gap labels remain visible in extensions_json, but the adapter does not promote the curated fact ledger to direct high-confidence evidence. Known strength/gap facts enter as NEAR_DIRECT / LOW support pending underlying-artifact review; unknown facts remain NO_EVIDENCE_OBSERVED / NOT_EVIDENCED.

A later dedicated AI component can receive a new adapter without changing these historical source bindings.

## Deterministic identifiers

New evidence rows use high synthetic sequence ranges to avoid the existing UIOWA-023 demonstration rows:

- delivery: 810–817
- security: 840–844
- AI: 870–875

Original source IDs are never replaced: native_id and source_ref preserve them, while extensions_json retains the full record.

## Run

From this directory:

    python3 adapter.py --component delivery --out examples
    python3 adapter.py --component security --out examples
    python3 adapter.py --component ai --out examples
    python3 adapter.py --component all --out examples
    python3 -m unittest -v tests/test_adapter.py

Each CSV can be passed directly to the common UIOWA-023 structural validator. The regression suite also requires checked-in example CSV/JSON bytes to equal fresh adapter output.

## Interpretation boundary

Passing the common validator proves schema coherence only. It does not prove a University fact, security condition, delivery maturity, AI adoption level, compliance result, or recommendation. All sources and outputs in this lane are synthetic.
