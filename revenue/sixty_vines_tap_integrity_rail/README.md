# Tap-to-Table Integrity Rail — internal delivery core

`sixty-vines-tap-integrity-rail/v1` is an offline, buyer-neutral acceptance core for a 60-tap wine service environment. It reconciles synthetic evidence from wine/SKU and keg/lot identity through tap/line state to pour, table/check, waste, void, and refund records.

This package is **delivery-core evidence only**. It does not connect to Sixty Vines systems, process guest data, decide alcohol service or age eligibility, change pricing/discounts/comps/refunds, mutate a POS, move money, buy or route inventory, clean a line, release a tap, or claim production acceptance/revenue.

## What the rail proves

The core gives every applied pour or waste event an attributable chain:

`wine/SKU -> keg/lot -> tap/line -> effect -> table/check (for pours)`

Before a committed pour/waste may affect the synthetic inventory ledger, the rail requires the event to match the current tap assignment, current keg/lot/wine/SKU identity, available + temperature-OK tap state, an unexpired line-cleaning window, and sufficient remaining volume. Operational mismatches are fail-closed `holds`; malformed/contradictory input is rejected.

Effect IDs are at-most-once. A retry carrying the same business effect under a new event ID is suppressed without a second inventory or monetary reconciliation effect. Reuse of an effect ID with different business content is rejected. An `UNKNOWN_EFFECT` is surfaced and never guessed as committed.

Voids/refunds reconcile only against a known committed pour on the same check and cannot reverse more cents than the original recorded amount. This is arithmetic/evidence reconciliation only; it grants no payment/refund authority.

The schema rejects unexpected fields and a fixed set of guest/customer/payment-identifier field names. Inputs use exact integers for milliliters and cents; JSON floats are not accepted as money.

## Deterministic acceptance corpus

Run:

```bash
python revenue/sixty_vines_tap_integrity_rail/rail.py acceptance --events 20000 --taps 60 --require-pass
```

The deterministic corpus has exactly 20,000 input rows and exercises all 60 taps. It includes a keg/SKU substitution, exact input replay, a distinct-event duplicate effect, normal pours, partial pours, waste/spill, void, refund, a timeout ambiguity, and four deliberate operational holds:

- SKU misroute
- unavailable tap
- temperature hold
- overdue line cleaning

The acceptance run passes only when the injected hold classes are visible, retry suppression is visible, the unknown effect remains explicit, every tap has a committed attributed effect, reconciliation invariants hold, and the offline SHA-256 receipt verifies.

Current locally executed acceptance receipt:

- manifest SHA-256: `476ef0b429c0c4b6b1e8751fc3b1f2f85322d695f8c8e9bcd1c8a0a0a431b5c1`
- result SHA-256: `bff13f79e8397032fbc0cc6b7371e2d46ece26212f81ec8d325c08c48e6cff0d`
- 20,000 input rows
- 60/60 taps with committed attributed effects
- 19,742 committed synthetic pours
- 175 partial pours
- 1 committed waste, 1 void, 1 refund
- 4 deliberate held pours
- 1 explicit unknown effect
- 1 distinct-event duplicate effect suppressed
- 1 exact input retry suppressed

The cents and milliliters in this fixture are synthetic test arithmetic, not customer economics, inventory, pricing, sales, or recognized revenue.

## Tests

```bash
python revenue/sixty_vines_tap_integrity_rail/test_rail.py
python -O revenue/sixty_vines_tap_integrity_rail/test_rail.py
python -m py_compile   revenue/sixty_vines_tap_integrity_rail/rail.py   revenue/sixty_vines_tap_integrity_rail/test_rail.py
```

Local execution for this carrier:

- normal Python: **21/21 PASS**
- `python -O`: **21/21 PASS**
- `py_compile`: **PASS**
- 20,000-row acceptance CLI with `--require-pass`: **PASS**
- offline receipt verification: **VALID**

The hostile suite covers event-ID collision, sequence collision, effect-ID collision, retry suppression, PII/unexpected-field rejection, non-integer money rejection, unknown-effect visibility, misroute, unavailable/temperature/cleaning holds, inventory overage, line assignment collision, duplicate keg custody, reversal overage/check mismatch, order-invariant replay, exact fixture sizing, CLI acceptance, and receipt tamper detection.

## Receipt model

`reconcile()` emits a canonical manifest and `manifest_sha256`. `make_receipt()` separately binds the complete result to `result_sha256`; `verify_receipt()` checks both digests using constant-time digest comparison. The receipt is an offline integrity receipt, not a digital signature or external attestation.

## Integration boundary

A future production adapter would still need buyer-approved schemas and identifiers, system-of-record ownership, authenticated read paths, timeout-after-commit reconciliation against authoritative provider state, retention/privacy policy, operator UX, real deployment/security evidence, and signed acceptance criteria. None of those are inferred here.

Source SHA-256 before publication:

- `rail.py`: `e51d05e4eb87158b0d04caa2ba48489a46a3117e9a8f322b3c5f572ef032e2fd`
- `test_rail.py`: `eacbf29343a62b96b98f613291c839065ad87039b4fe12f109479339c26cd640`
