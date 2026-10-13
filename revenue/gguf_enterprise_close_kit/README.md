# GGUF $12k enterprise close + delivery kit

This is the buyer-neutral fulfillment spine for the existing public `gguf-diagnostic-10d-12k` offer. It **does not change or remint** the commercial rail.

Canonical terms: **$12,000 fixed / 10 calendar days**; M1 **$6,000 after NDA + SOW and before customer file exchange**; M2 **$6,000 on AT1–AT6 acceptance**. Acceptance is **rollback evidence, not metric lift**.

## What ships

- `close_kit.py` — deterministic secret-free intake + digest-only AT1–AT6 compiler/verifier and buyer-readable Markdown renderer.
- `sample_intake.json` / `sample_evidence.json` — explicitly synthetic, unpaid, non-customer example. No model bytes, private identity, secrets, or payment data.
- `SOW_ORDER_FORM.md` — order-form/SOW content with exact scope, exclusions, acceptance, and responsibility split.
- `DELIVERY_RUNBOOK.md` — 10-day operating plan, stop/HOLD/refund-escalation semantics, evidence custody, and final packet contents.
- `intake.schema.json` — machine-readable public contract for secret-free intake metadata.
- `SAMPLE_REPORT.md` — expected report surface generated from the synthetic fixture.

## Reproduce

```bash
python revenue/gguf_enterprise_close_kit/close_kit.py compile \
  revenue/gguf_enterprise_close_kit/sample_intake.json \
  revenue/gguf_enterprise_close_kit/sample_evidence.json \
  --json-out /tmp/gguf-packet.json --markdown-out /tmp/gguf-report.md
python revenue/gguf_enterprise_close_kit/close_kit.py verify /tmp/gguf-packet.json
python -m unittest tests.test_gguf_enterprise_close_kit
python -O -m unittest tests.test_gguf_enterprise_close_kit
```

## Hard boundaries

Public Commons holds only sanitized metadata and SHA-256 evidence references. Customer GGUF bytes, harness payloads/logs, private contacts, signatures, tax/payment details, and secrets stay outside Commons. Every retained free-text scope field is checked by the canonical `host/revenue_recovery.py::contains_sensitive_value` DLP and rejects URLs outright; caller privacy booleans are additional fail-closed assertions, not the privacy enforcement mechanism. This kit never authorizes a send, file transfer, legal acceptance, payment capture/refund, or revenue recognition. A synthetic PASS is not a buyer case.
