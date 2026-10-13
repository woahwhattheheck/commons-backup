# 90-Second Demo â€” Hyperagent Transcript Carrier

Prospect-safe walkthrough of the merged offline carrier. Runs entirely
against the checked-in synthetic fixture; no network, no credentials, no
customer data, no outbound send authority.

## Run

```bash
python -m revenue.hyperagent_slack_transcript.demo_90s
```

## What it shows (~seconds, three scenes)

1. **Projection** â€” 30 synthetic events across three heterogeneous backend
   schemas (`stream`, `trace`, `envelope`) normalize into 6 deterministic
   transcript artifacts. Per-artifact SHA-256 printed for byte-exactness.
2. **Idempotent replay** â€” full re-ingest emits 0 duplicate logical
   messages; state hash identical across passes.
3. **Approval boundary** â€” a `MUTATING_ACTION` event is held without
   approval (`APPROVAL_NOT_CURRENT_FOR_EXACT_EVENT_GENERATION`), an
   approval signed with a forged key is rejected, and the exact
   HMAC-authenticated approval emits one candidate message carrying
   `approval_id` and a bound `approval_receipt_sha256`.

Every emitted artifact carries `external_send_authorized=False`. The demo
key is generated at runtime (`secrets.token_bytes`) and never committed.

## Provenance

- Package: `revenue/hyperagent_slack_transcript/` (merged on `main`,
  PRs #15057 and #15082).
- Contract: `revenue/hyperagent_slack_transcript/README.md`.
- Tests (38): `test_adapter.py`, `test_stateful.py`,
  `test_public_surface.py` â€” run with
  `python -m unittest -v revenue.hyperagent_slack_transcript.test_adapter revenue.hyperagent_slack_transcript.test_stateful revenue.hyperagent_slack_transcript.test_public_surface`.

Synthetic fixture only â€” this demonstrates fulfillment readiness, not a
deployed customer integration.
