# Paid Pilot → Rollout Desk

`paid-pilot-rollout-desk` is an offline commercial-boundary product for the exact moment after a bounded pilot has run and before anyone quietly turns “one more thing” into free work.

It does **not** contact a buyer, accept a contract, charge a payment method, mutate a provider, or recognize revenue. Its output is an owner-review candidate.

## Why it exists

A paid pilot can prove enough value to justify a larger rollout and still fail commercially if the handoff is fuzzy:

- the original acceptance criteria are not tied back to exact evidence;
- a failed criterion is waved through as “close enough”;
- the buyer asks for adjacent work and it gets absorbed for free;
- phase 2 has no measurable acceptance criteria;
- an internal proposal is accidentally described as buyer-approved, paid, or booked revenue.

This desk makes those failure modes explicit and machine-checkable.

## Decision model

The desk compiles one of four outcomes:

- `HOLD_FOR_PAYMENT_EVIDENCE`: the pilot is not backed by an externally supplied paid-pilot evidence reference.
- `NO_GO`: at least one original pilot acceptance criterion is explicitly `NOT_MET`.
- `HOLD_FOR_PILOT_EVIDENCE`: a criterion is missing evidence or explicitly `HOLD`.
- `HOLD_FOR_COMMERCIAL_SCOPE`: an adjacent follow-on request exists but lacks separate commercial terms.
- `READY_FOR_OWNER_ROLLOUT_REVIEW`: the paid-pilot evidence reference is present, all original criteria are `MET`, and every new-scope request either stays excluded or has explicit proposed change-order terms.

The system never promotes any of those states into buyer acceptance, signature, charge authority, payment receipt, or revenue recognition.

## Scope classes

Every follow-on request names the exact scope IDs it depends on.

- `INCLUDED`: every requested scope ID was explicitly included in the pilot. This is the only class that may be fulfilled without a new commercial delta.
- `OUT_OF_SCOPE`: at least one requested scope ID was explicitly excluded. It stays outside the rollout candidate.
- `CHANGE_ORDER_REQUIRED`: the request introduces scope not present in the pilot. The rollout is held until proposed price, duration, dependencies, and acceptance criteria are attached. Even after terms are attached, a separate buyer agreement is still required.

Different wording does not make unknown scope “included”; classification is ID-based.

## Truth boundary

The pilot spec contains an opaque commercial evidence reference and digest. `PAID_EXTERNAL_EVIDENCE` means an authorized operator supplied an external payment-evidence pointer. The desk does **not** independently verify a Stripe event, bank transaction, contract, or cash receipt.

Every compiled rollout candidate hard-codes:

- `buyer_acceptance = false`
- `contract_signed = false`
- `charge_authorized = false`
- `payment_received = false`
- `revenue_recognized = false`

The persisted state additionally refuses any attempt to elevate its authority flags.

## Files

- `rollout_desk.py` — dependency-free engine + CLI.
- `test_rollout_desk.py` — hostile/state tests.
- `example_pilot.json` — fictional paid-pilot closeout input.
- `example_evidence_accuracy.json`, `example_evidence_handoff.json` — fictional evidence bindings.
- `example_followon_change_order.json` — fictional adjacent request with explicit separate terms.

All example buyer/evidence references are synthetic opaque identifiers.

## Reproduce the example

```bash
python3 rollout_desk.py init \
  --pilot-spec example_pilot.json \
  --state demo-state.json

python3 rollout_desk.py evidence \
  --state demo-state.json \
  --evidence example_evidence_accuracy.json

python3 rollout_desk.py evidence \
  --state demo-state.json \
  --evidence example_evidence_handoff.json

python3 rollout_desk.py followon \
  --state demo-state.json \
  --request example_followon_change_order.json

python3 rollout_desk.py compile \
  --state demo-state.json \
  --out-json rollout.json \
  --out-md rollout.md

python3 rollout_desk.py verify --state demo-state.json
```

Expected decision: `READY_FOR_OWNER_ROLLOUT_REVIEW`. That phrase is intentionally not “accepted,” “sold,” “paid,” or “revenue.”

## Validation

Focused local acceptance on the authored bytes:

```bash
python3 -m unittest -v test_rollout_desk.py
python3 -O -m unittest -q test_rollout_desk.py
python3 -m py_compile rollout_desk.py test_rollout_desk.py
```

The suite covers normal and optimized mode, strict JSON duplicate-key rejection, bool/int traps, opaque refs, scope overlap, payment-evidence hold, `NO_GO`, evidence hold/missing, evidence history, scope classification, free-extension prevention, change-order terms, duplicate requests, state tamper detection, authority escalation denial, export hashing, symlink rejection, create-exclusive output, and reopen integrity.

## Commercial use

Attach this desk to any bounded paid pilot whose phase-2 opportunity is materially larger than the pilot itself. The operator can close the pilot with evidence, hand the buyer an exact success/hold/no-go narrative, and prepare a phase-2 package without silently donating integration work.

A practical internal rule is: **no unpriced new scope crosses the pilot boundary.**
