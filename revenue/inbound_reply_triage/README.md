# Inbound reply triage

`revenue/inbound_reply_triage` turns retained commercial-contact events into a deterministic **owner-review queue**. It exists to protect warm replies from getting buried while preserving the single-writer/Muse collision discipline.

## Contract

Input binds every lane to an exact `org_key × route_key × domain × purpose_key × thread_key`. `org_key` and `route_key` are collision-sensitive text: the caller-authored spelling must already be exact NFKC; Unicode category-C code points, Unicode Default_Ignorable_Code_Point members that are not category-C (including variation selectors, combining grapheme joiner, Hangul fillers, and related retained ranges), line/paragraph separators, and every non-ASCII Unicode space separator are forbidden. Only ordinary ASCII SPACE (`U+0020`) may be trimmed at the outer boundary, and the result must remain non-empty. This prevents invisible, compatibility, or trim-erased spellings from splitting one commercial-contact custody lane into multiple bindings.

Events are chronological and evidence-referenced. `SENT` requires a fresh prior `MUSE_SELECTED` whose timestamp is **strictly earlier** than that `SENT`; same-second list order is never send authority. A repeat send in history additionally requires an intervening `HUMAN_REPLY` strictly after the previous send and strictly before the current send. `RESPONSE_DRAFT_READY` likewise requires a `HUMAN_REPLY` with a **strictly earlier** timestamp, so same-second list order cannot mint reply-readiness authority. Unsolicited genuine inbound can be represented without a prior send.

The compiler distinguishes:

- `NEW_HUMAN_INBOUND`
- `RESPONSE_READY_OWNER_REVIEW`
- `AUTO_REPLY`
- `BOUNCE`
- `REJECTION`
- `WAITING_EXTERNAL`
- `DNR`
- `COLLISION_HOLD`
- `MUSE_REQUIRED`

A drafted response becomes `RESPONSE_READY_OWNER_REVIEW` only with an active, evidence-bound one-writer lease and a draft strictly later than the retained human reply. An expired/missing lease fails closed to `COLLISION_HOLD`. DNR/collision/bounce/rejection evidence is never converted into a human reply. Same-second mutually exclusive status evidence fails closed instead of using list position as authority.

`evaluation_at` and `stale_after_minutes` produce deterministic reply age/staleness. The owner-review queue prioritizes human inbound first, with older human replies first within a state.

## Evidence boundary

Event and lease `evidence_refs` are retained caller evidence identifiers. They are bound into deterministic source/receipt bytes, but they are **not** external-provider authentication by themselves. `NEW_HUMAN_INBOUND`, active-lease, and `RESPONSE_READY_OWNER_REVIEW` therefore remain retained-evidence states until a separately reviewed provider/source binding proves the referenced event or lease. This package never upgrades those references into provider truth on its own.

## Authority ceiling

This package **does not send anything**. It cannot select Muse, contact a buyer/partner, assert acceptance, create a contract or invoice, move money, establish a receivable, or recognize revenue. Every such authority bit is hard false in compiled output. For any state that may eventually need an external response, `next_gate` remains `MUSE_REQUIRED_BEFORE_ANY_SEND`.

The receipt is not an external-provider attestation. It binds exact source and compiled packet bytes; `verify_triage()` recompiles and rejects tampering.

## Test

```bash
python -m unittest test_revenue_inbound_reply_triage.py test_revenue_inbound_reply_triage_15431_recovery.py -v
python -O -m unittest test_revenue_inbound_reply_triage.py test_revenue_inbound_reply_triage_15431_recovery.py -v
python -m py_compile revenue/inbound_reply_triage/core.py test_revenue_inbound_reply_triage.py test_revenue_inbound_reply_triage_15431_recovery.py
```
