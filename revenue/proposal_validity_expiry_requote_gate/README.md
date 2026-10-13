# Proposal validity / expiry / requote gate

This is an **owner-review commercial-truth gate** for an offer that was already proposed. It does not send anything, accept terms, sign a contract, operate a checkout rail, authorize payment, or recognize revenue.

The compiler emits exactly one state:

- `CURRENT_FOR_OWNER_USE`
- `EXPIRED_REQUOTE_REQUIRED`
- `SUPERSEDED`
- `HOLD_NO_VALIDITY_BASIS`
- `HOLD_SOURCE_DRIFT`

`CURRENT_FOR_OWNER_USE` is deliberately narrow: the exact issued commercial snapshot is still current enough for owner review under its explicit validity terms. It is not outbound authority and it is not evidence of buyer acceptance, contract execution, payment, cash, or revenue.

## Hardened v2 evidence

Schema v2 is required to mint a fresh `CURRENT_FOR_OWNER_USE` result. The issued snapshot binds `offer_id`, source generation **and source digest**, pricing revision, currency, exact scope/economics JSON, issuance time, explicit validity semantics, buyer deadline when present, and optional non-authoritative payment-road identity.

The v2 current snapshot binds the same live commercial semantics plus exact controlling source generation + digest; `source_status` (`CURRENT`, `STALE`, or `WITHDRAWN`); timezone-aware `source_observed_at`; current payment-road identity/state when the issued offer carried one; and source-bound supersession events.

For a CURRENT result, source observation must be no earlier than issuance and no later than the trusted runtime clock. Source digest/generation/status drift or a stale/replaced/withdrawn payment road produces `HOLD_SOURCE_DRIFT`. Pricing, currency, scope, or economics drift remains `SUPERSEDED`.

Supersession kinds are `AMENDMENT`, `REDLINE`, `CHANGE_ORDER`, `REPRICE`, and `WITHDRAWAL`. Every row is schema/syntax validated and event IDs remain globally unique. **Current source-generation/digest/observation authority is applied only after the row is relevant to this exact offer and observed after the offer was issued.** Historical rows for another offer, and pre-issuance history for this offer, therefore cannot veto current truth merely because they correctly bind an older source generation. A relevant post-issuance superseder must still bind the exact current source generation/digest and cannot postdate the current source observation.

### V1 compatibility / migration

Legacy schema-v1 issued/current JSON is still accepted so callers receive a deterministic bounded result instead of a parser break. Because v1 lacks the source digest/status/observation and current payment-road evidence needed for current commercial truth, unchanged v1 snapshots are truth-narrowed to `HOLD_SOURCE_DRIFT` with `LEGACY_SOURCE_EVIDENCE_MISSING`; they cannot mint a new CURRENT receipt. Recompile with v2 evidence to regain a CURRENT determination. Pre-hardening v1 packets should likewise be recompiled rather than treated as current proof.

## Time and replay boundary

The production CLI obtains evaluation time from the process UTC clock and exposes **no `--as-of`** option. The canonical core still captures its standard-library `datetime.now` callable for private compatibility, while the supported facade owns a separate stdlib process-clock generation and captures that callable in the public `evaluate_offer()` / `verify_packet()` closure. Ordinary rebinding of `gate._dt.datetime`, public `gate._utc_now`, or reachable `gate._core._utc_now` therefore cannot select/freeze historical evaluation time; reloading the facade after rebinding the private-core clock still constructs the supported API from the facade-owned stdlib clock.

The private `_evaluate_at` helper defaults to `clock_basis=TEST_EXPLICIT`; those packets are intentionally not accepted by `verify_packet` as process-current evidence. Retained deterministic tests construct a separate private API generation with `_build_current_api_for_test`; the supported public API exposes no caller clock parameter.

Verification exact-rebuilds at the packet's bound evaluation instant and then performs a fresh captured process-UTC evaluation whose **semantic projection** must still match, not merely its coarse five-state string. This rejects both an old CURRENT packet after expiry and subtler same-state drift, such as an already-expired packet later crossing a buyer deadline and gaining a new requote reason.

## Implementation preservation

The canonical predecessor implementation reviewed at `9dee00d3021f45272c22b86493c75191ce596b16` remains structurally preserved as `_proposal_validity_core.py`. One later semantic seam is intentionally hardened there: packet authority is now emitted from source-literal values rather than the mutable compatibility descriptor `_AUTHORITY`. Public `gate.py` remains the small facade that patches the supersession-relevance and public-current-clock STOP seams before exporting the supported API/CLI. The predecessor test file is still retained byte-for-byte as `tests/_proposal_validity_predecessor_suite.py`; the discoverable successor test subclasses it, adapts deterministic clock setup to the private API-generation seam, and adds the later hostile predecessors.

## Strict input boundary

JSON is fail-closed and bounded. The parser rejects duplicate keys, floats, non-finite numbers, overlarge integer tokens before Python integer conversion, lone-surrogate Unicode keys/values, excessive nesting/collections, unknown contract fields, bool-as-int money/durations, and malformed or timezone-naive timestamps. Runtime JSON/Unicode/recursion/overflow failures are translated into bounded gate errors; the CLI returns status 2 without a traceback under normal Python and real `python -O`.

`requote_delta` remains `PROPOSED_NOT_ACCEPTED` and records exact commercial changes, applicable source-bound supersession events, source-currentness reasons, and time reasons. Every packet keeps buyer acceptance, contract signed, checkout/payment rail as acceptance, payment authorization, revenue recognition, and outbound authorization hard false. Those authority bits are emitted source-literally; mutating or rebinding either the public `gate._AUTHORITY` alias or reachable `gate._core._AUTHORITY` compatibility descriptor cannot widen compilation, and a packet with any widened bit fails exact verification even if its receipt is recomputed.

## Run

```bash
python revenue/proposal_validity_expiry_requote_gate/gate.py compile \
  --issued revenue/proposal_validity_expiry_requote_gate/example_issued.json \
  --current revenue/proposal_validity_expiry_requote_gate/example_current.json \
  --out /tmp/proposal-validity-packet.json

python revenue/proposal_validity_expiry_requote_gate/gate.py verify \
  --issued revenue/proposal_validity_expiry_requote_gate/example_issued.json \
  --current revenue/proposal_validity_expiry_requote_gate/example_current.json \
  --packet /tmp/proposal-validity-packet.json
```

Output creation is exclusive: an existing target is never overwritten.

## Tests

```bash
python -m py_compile \
  revenue/proposal_validity_expiry_requote_gate/_proposal_validity_core.py \
  revenue/proposal_validity_expiry_requote_gate/gate.py \
  tests/_proposal_validity_predecessor_suite.py \
  tests/test_proposal_validity_expiry_requote_gate.py
python -m unittest -v tests/test_proposal_validity_expiry_requote_gate.py
python -O -m unittest -v tests/test_proposal_validity_expiry_requote_gate.py
```

The retained hostile suite covers legacy truth narrowing; source generation/digest/status/chronology; commercial drift; all five supersession kinds; relevant post-issue source binding; irrelevant OTHER-offer and pre-issue old-generation history; payment-road drift; validity/deadline boundaries; explicit-test-clock rejection; stdlib-clock rebinding; direct public `_utc_now` rebinding; private-core `_utc_now` rebinding followed by facade reload; public/core authority mutation and rebinding plus self-consistent widened-packet rejection; duplicate/nonfinite/float/giant-int/surrogate/deep JSON hostiles; tampered receipts; historical CURRENT replay; same-state temporal semantic drift; create-exclusive output; no `--as-of`; and bounded CLI failures under normal and optimized Python.
