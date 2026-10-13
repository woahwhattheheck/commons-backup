# Procurement win/loss evidence loop

`tools.procurement_win_loss` turns **redacted, source-digest-bound procurement outcome evidence** into one deterministic state:

- `WON`
- `LOST`
- `NO_DECISION`
- `UNKNOWN`

It exists to close the learning loop after real bids without inventing a postmortem. A notice that only says *not selected* proves `LOST`; it does **not** prove why. The receipt therefore separates observed decision facts from source-stated rationale and explicit unknowns.

## Authority boundary

This package is offline and side-effect free. It does not authorize or perform buyer contact, debrief requests, outbound messages, payment actions, contract changes, revenue recognition, or causal inference. Every emitted authority bit is false and the independent verifier checks that boundary.

Do not place raw buyer email bodies, addresses, phone numbers, URLs, or other private contact data in these records. Each evidence row must carry `redacted: true`, and stated rationale rejects obvious email/URL/phone-like strings. Keep the owner-retained raw source elsewhere and bind the redacted row to it with `source_digest_sha256`.

## Input contract

```json
{
  "schema": "procurement-outcome-evidence/v1",
  "opportunity_id": "SYNTH-RFP-002",
  "compiled_at": "2026-09-17T03:00:00Z",
  "evidence": [
    {
      "evidence_id": "notice-002",
      "bound_opportunity_id": "SYNTH-RFP-002",
      "source_kind": "BUYER_NOTICE",
      "source_digest_sha256": "2222222222222222222222222222222222222222222222222222222222222222",
      "observed_at": "2026-09-17T01:55:05Z",
      "captured_at": "2026-09-17T02:01:00Z",
      "evidence_status": "CURRENT",
      "redacted": true,
      "decision_signal": "NOT_SELECTED",
      "rationale": {"status": "UNKNOWN"}
    }
  ]
}
```

Signals map directly: `SELECTED`/`AWARDED` → `WON`; `NOT_SELECTED` → `LOST`; `NO_AWARD`/`CANCELLED` → `NO_DECISION`; `PENDING`/`UNKNOWN` → `UNKNOWN`. The compiler never maps free text to an outcome.

Each evidence row is bound to the root `opportunity_id`. Duplicate evidence ids and duplicate source digests are rejected as replay. Evidence marked `STALE` or `WITHDRAWN` cannot independently produce a terminal result. Conflicting current terminal evidence, conflicting non-current terminal evidence, and a later `PENDING` after a terminal signal fail closed to `UNKNOWN` with an explicit `hold_reasons` entry.

## Compile and verify

```bash
python3 -m tools.procurement_win_loss compile evidence.json receipt.json
python3 -m tools.procurement_win_loss verify evidence.json receipt.json
```

Compilation canonicalizes evidence order and timestamps, hashes the normalized input, and hashes the complete receipt. Verification is a separate semantic path that recomputes outcome, holds, facts, rationale, unknowns, hashes, and the all-false authority boundary.

## Seller/operator use

Use this receipt to update targeting from **facts only**:

1. Preserve the terminal outcome as evidence-backed history.
2. Preserve any buyer-stated reason exactly as a redacted statement; do not broaden it into a causal theory.
3. Keep absent reason detail `UNKNOWN`.
4. Aggregate only source-bound fields across bids. A loss without rationale may change the denominator, not the story.
5. If evidence conflicts, is transplanted, replayed, future-dated, stale-only, or otherwise malformed, stop at `UNKNOWN` or reject the input. Repair evidence before drawing conclusions.

The included `fixtures.json` is synthetic and intentionally contains no real buyer identity or contact material. It covers win, loss, no-decision, unknown, conflict, chronology, stale evidence, transplant rejection, replay rejection, malformed/unredacted evidence, and missing reason detail.

## CI

`test_procurement_win_loss.py` is a root `test_*.py` file, so the retained Commons `tests.yml` battery discovers it automatically. The workflow is already path-triggered on root tests; no additional active workflow is required. Run both normal and optimized modes locally:

```bash
python3 -m unittest -v test_procurement_win_loss.py
python3 -O -m unittest -v test_procurement_win_loss.py
```
