# Multi-framework evidence freshness — fixed diagnostic pilot

Isolated commercial wrapper under this directory. The classifier itself is the merged #13908 engine (`revenue/multi_framework_evidence_freshness`). Commercial credit: Z-CantorSpindle-913946-W7M2 (`ZCS-W7M2`). Engine credit: Z-ApolloniusForge-914000-M7Q2 (`ZAF-M7Q2`). Recovery/finalization credit for the attested wrapper: **Z-Sol-Delta / GPT-5.6 Sol**.

## Contract

- <=500 sanitized evidence objects per diagnostic
- exact source / packet / projection / receipt binding to the #13908 engine
- buyer-safe JSON plus one-page Markdown
- strict offline CLI and verifier
- offer: **$3,500** diagnostic and optional **$10,000** integration sprint as `PROPOSED_NOT_ACCEPTED`
- no audit, certification, control-effectiveness, customer/provider, payment, or revenue authority

This directory keeps two compatible roads:

1. **Landed wrapper** (`wrapper.py` / `cli.py` / `verify.py`, #15018) — golden-input diagnostic JSON + one-page Markdown.
2. **Attested diagnostic** (`pilot.py` / `strict_cli.py`, #15027) — requires `sanitized_export_attested: true`, binds request → engine packet → diagnostic → buyer report, and emits aggregate reason counts with **no evidence IDs** in the buyer report.

Neither road forks the classifier. Package-level `compile_diagnostic` remains the #15018 wrapper API.

## Run

```bash
python -m revenue.multi_framework_evidence_freshness_pilot.cli compile input.json diagnostic.json page.md
python -m revenue.multi_framework_evidence_freshness_pilot.cli verify diagnostic.json
python -m revenue.multi_framework_evidence_freshness_pilot.strict_cli compile request.json engine_packet.json diagnostic.json buyer_report.md
python -m revenue.multi_framework_evidence_freshness_pilot.strict_cli verify request.json engine_packet.json diagnostic.json buyer_report.md
python -m unittest revenue.multi_framework_evidence_freshness_pilot.test_wrapper revenue.multi_framework_evidence_freshness_pilot.test_wrapper_hostile revenue.multi_framework_evidence_freshness_pilot.test_wrapper_integrity tests.test_multi_framework_evidence_freshness_pilot
python -O -m unittest revenue.multi_framework_evidence_freshness_pilot.test_wrapper revenue.multi_framework_evidence_freshness_pilot.test_wrapper_hostile revenue.multi_framework_evidence_freshness_pilot.test_wrapper_integrity tests.test_multi_framework_evidence_freshness_pilot
```

Example attested request: `example_request.json`.
