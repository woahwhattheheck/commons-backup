# Provider Cost Truth Gate

`tools/provider_cost_truth` is a side-effect-free fleet preflight for one question: **is a requested provider/product/model/session actually evidenced as zero-cost at the scope being delegated?**

A product or model can be described as “free” while the connected provider account still has billable activity. The gate refuses both scope errors: an account-level paid receipt does **not** become a model/session price claim, and marketing/owner/worker prose saying “free” does **not** become provider-authenticated zero-cost authority.

## States

- `ZERO_COST_VERIFIED` — current **source-manifest-trusted** provider-authenticated zero-cost evidence exists at the exact requested scope.
- `BILLABLE_VERIFIED` — current **source-manifest-trusted** provider-authenticated nonzero billing evidence exists at the exact requested scope.
- `FREE_UNPROVEN_ACCOUNT_BILLING_PRESENT` — trusted account billing exists but the requested lower-scope price is unproven.
- `COST_UNKNOWN` — insufficient current trusted provider authority.
- `CONTRADICTORY` — latest exact-scope trusted provider generation contains incompatible zero/nonzero evidence.

For `free_only=true`, only `ZERO_COST_VERIFIED` sets `free_only_satisfied=true`. Every receipt permanently keeps `provider_session_authorized=false`, `spend_authorized=false`, and `external_side_effects_authorized=false`.

## Trust root: raw snapshots never self-authorize

`authority="PROVIDER_AUTHENTICATED"` inside a JSON snapshot is **not authority by itself**. The caller also controls that JSON, so treating the string as proof would let anyone self-mint `ZERO_COST_VERIFIED`.

Authorizing rows must additionally match an immutable fingerprint in `trusted_sources.py`. A fingerprint binds the complete normalized evidence row: event id; provider/account; ACCOUNT/PRODUCT/MODEL/SESSION identity; kind; amount/currency; event, observation, and validity times; source reference; source SHA-256; and authority label. Any source-digest drift, source-reference transplant, identity transplant, amount/kind change, time change, or event-id substitution changes the fingerprint and fails closed.

The v1 manifest intentionally ships **empty**. Therefore the supported `compile_current(snapshot)` cannot presently emit `ZERO_COST_VERIFIED` or `BILLABLE_VERIFIED` from caller JSON alone, even if a row says `PROVIDER_AUTHENTICATED`. Such rows are ignored with `IGNORED_UNTRUSTED_PROVIDER_EVIDENCE:<event_id>` and `free_only=true` remains held.

Adding a fingerprint to `TRUSTED_PROVIDER_EVIDENCE_FINGERPRINTS` is an explicit source-code authority change. It must be backed by independently authenticated provider material and reviewed as such; do not add a fingerprint merely because a caller supplied matching fields. This package does not fetch providers, hold credentials, or authenticate provider bytes itself.

Every evaluation and current receipt also binds `trusted_provider_evidence_manifest_sha256`, a deterministic digest of the trust-manifest schema and sorted fingerprint generation. Historical verification replays using the captured program generation and requires exact receipt equality. Changing that manifest digest and merely recomputing the outer receipt SHA does not manufacture a valid receipt: semantic replay reconstructs the actual captured generation and rejects the forged one.

Private explicit-time semantic tests may inject a test-only fingerprint generation plus its matching manifest digest into the non-authorizing evaluator to prove scope/precedence logic. That seam emits no current receipt fields and is not the supported current compiler.

## Scope and currentness

Evidence is `ACCOUNT`, `PRODUCT`, `MODEL`, or `SESSION`; the requested target is the deepest supplied identity. Positive trusted account billing may HOLD an unproven zero-cost assumption but cannot be transplanted into “this model costs $X”. A zero-cost receipt for one session cannot be replayed to another session.

Trusted `ZERO_COST_CONFIRMED` and `PRICE_QUOTE` rows require explicit `valid_until_utc`. v1 also applies a seven-day observation-age ceiling; future, stale, or expired trusted rows are ignored fail-closed and named in receipt reasons.

`compile_current(snapshot)` owns process UTC. Its clock plus evaluator/parser/schema/hash generation are captured when the supported API initializes, so ordinary reassignment of those module helper names cannot retarget an already-created current compiler/verifier pair. The evaluator’s trusted-manifest generation is an immutable `frozenset` captured when the evaluator initializes; ordinary rebinding of the exported manifest name afterward cannot grant authority to the already-created API.

The explicit-time evaluator is deliberately non-authorizing: it emits no `evaluation_mode`, `evaluated_at_utc`, or `receipt_sha256`. The compatibility facade exposes no caller-time receipt builder. `verify_receipt(snapshot, receipt)` is historical integrity verification only; it replays the embedded instant inside a captured closure, returns only a boolean, and never remints current authority. A current decision requires `compile_current()` again now.

This is an ordinary-caller integrity boundary, not a security claim against a trusted process owner mutating dependency modules before import/reload, replacing closure/default objects through Python introspection, or rewriting interpreter memory. The source-controlled manifest is trusted because its bytes are part of the reviewed program generation, not because Python can defend itself from a hostile process owner.

## Strict text boundary

Duplicate JSON keys and NaN/Infinity are rejected. Schema-bearing text must encode as strict UTF-8 scalar text: escaped lone surrogates are rejected as `GateError` before digesting or diagnostic output; duplicate-key errors do not echo attacker-authored key text; canonicalization translates encoding failure into the same domain error. Normal and real `python -O` CLI predecessors require rc=2 with no traceback for surrogate input.

## CLI

```bash
python -m tools.provider_cost_truth.cli compile snapshot.json > receipt.json
python -m tools.provider_cost_truth.cli verify snapshot.json receipt.json
```

With the v1 empty manifest, `compile` is intentionally fail-closed for raw provider claims. `verify` emits an explicit all-false current/provider/spend authority envelope even when historical integrity is valid.

## Evidence hygiene and authority ceiling

Fixtures/examples use synthetic or redacted opaque identities only. Do not commit invoice bodies, email addresses, payment credentials, API keys, session tokens, or private account identifiers. Provider evidence must be authenticated outside this package before a reviewed source-manifest fingerprint is added.

This package does not create/cancel provider sessions, alter plans, authorize or make payments, mutate credentials, send Slack/Gmail messages, contact customers, or establish accounting/revenue truth. It is a conservative evidence compiler only.
