# KESTREL lockstep hardening — existing V4 early-capital authority

This is an additive proof layer **inside** `candidates/v4/repairs/gameplay/early-capital/`. It does not create another capital policy, controller, feature key, V4 tree, default, archive or Kaggle path. The existing recovered v6 source (`early_capital.py`, Git blob `c87f1d1c9d7b416c5316837634f7e721c85811fa`) remains byte-unchanged and keeps policy authority.

## Why v6 still needs the historical KESTREL theorem

The v6 candidate correctly certifies that promoted funding, required operating rows and promoted LAND/ANIMAL capital can execute. But its rank order is FUNDING → OPERATING → CAPITAL → REST. `BUY_PRODUCT` is supported by the parser yet is neither required operating stock nor capital, so it is REST. A queue such as `BUY_PRODUCT WHEAT ; BUY_LAND` can therefore become `BUY_LAND ; BUY_PRODUCT`: the purchase remains syntactically present but can lose execution after capital spends the cash. Full capital execution is not the same theorem as preservation of every original own execution under the rival's hidden lockstep market queue.

PR #11705 already reviewed the rival-independent non-regression theorem. This carrier recovers only that admission proof and composes it *after* the existing v6 candidate.

## Admission

A changed v6 proposal is accepted only if the base report itself proves the canonical v6 path (`revision=v6-commit-real-capital`, `reason=ordered`, `capital_certificate_reason=certified`) **and** KESTREL proves all of the following over the executable prefix:

- active-order multiset and capped inactive tail are exact-parent; no non-market mutation;
- exactly one unchanged `BUY_LAND` or `BUY_ANIMAL` is present;
- every other effectful row is a SELL of a product the rival cannot buy in the market stage; WHEAT/FERTILIZER sales are rejected;
- requested sale units for every product never move later at any prefix;
- the sole capital row is the last effectful candidate row;
- public quotes match the official price function and every relevant sale curve is non-increasing across a complete two-shed supply bound.

Anything else returns the **exact parent action object**. This deliberately rejects the known BUY_PRODUCT-sacrifice class, HIRE/seed mixtures, multiple-capital tapes, buyable-product sales, malformed state and unproved price curves.

## Source graph

The checkout verifier pins the canonical v6 candidate `c87f1d1c...`, current production early-capital `1161859a...`, current runtime `6d9720f4...`, current production tests `89b451c4...`, config `3a3bef83...`, and official engine `3c202c7e...`. The historical donor theorem is `4999efe1...`. A source drift is a failed binding, not permission to weaken the proof.

## Promotion boundary

This source carrier is default-OFF and unwired. It makes no strength claim. A repository-mounted execution seat must first run the exact checkout binding/current-candidate witness, then measure natural v6 changes versus KESTREL-admitted changes on current-native traces. Zero admitted natural changes closes the lane COLD. Nonzero admissions require paired both-seat economics before any composition/runtime consideration.
