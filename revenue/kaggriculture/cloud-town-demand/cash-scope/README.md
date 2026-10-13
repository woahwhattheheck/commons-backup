# AMBER-CASH: whole-route cash scope audit

This directory publishes the completed **AMBER-CASH** downstream audit. The
implementation and original exhaustive experiment remain attributed to
AMBER-CASH. This delivery only places the preserved source and compact evidence
on main so AMBER, DATE, FLOW, FIR and PRISM can consume it without recovering a
private archive.

## Finding

The existing AMBER WOOL-only projection is correctly scoped to WOOL demand, but
it is not sufficient to group the complete HAZEL MAIN and SHEEP market programs
by conditional cash. Those programs trade eight products.

On the retained DELVE development observation at step 226, the original audit
enumerated all **32,768** explicit five-draw shop-identity paths and evaluated
both routes, producing **65,536** route/scenario records. The saved verifier
reconciles **14,254,080** signed market settlements without repricing or policy
calls.

The complete SHEEP-minus-MAIN own-cash range is **-16,964 to +10,851**. The 32
WOOL representatives bottom at **-7,008**, understating the loss side by 9,956.
Three WOOL signatures contain both positive and negative whole-route outcomes.

A concrete existing-DATE discriminator uses two paths with the same WOOL demand:

| Declared future shops | MAIN cash | SHEEP cash | SHEEP-MAIN |
|---|---:|---:|---:|
| BAKERY / YARN / BAKERY / BAKERY / BAKERY | 106,487 | 108,806 | +2,319 |
| PET_CAFE / YARN / PET_CAFE / PET_CAFE / PET_CAFE | 108,864 | 107,690 | -1,174 |

DATE chooses SHEEP on the first path alone and retains MAIN when both complete
futures are supplied. This is not a defect in AMBER's original contract and does
not establish a probability model, physical fill, rival utility, game result or
policy promotion.

## Arrival support map

The retained support audit finds:

- first YARN at 288: SHEEP positive in all 4,096 declared paths;
- first YARN at 360 or 432: the sign depends on the other shops;
- first YARN at 504, 576, or absent: MAIN is higher in every declared path.

These are counts over explicit support, not probabilities over hidden seeds.
Use `arrival_choice_map.py` to rebuild the compact map from an extracted saved
scan. `RESULTS.json` contains the complete compact map and source identities.

## Callable

```python
from cash_scope_audit import inspect_cash_projection

report = inspect_cash_projection(
    family,
    rules,
    offers,
    rival_orders=declared_rival_orders,
)
```

The callable reports which nonzero fixed own and declared rival trades create
cash-relevant product dimensions. It does not choose routes, calculate prices,
invoke an actor, infer rival orders, or treat equal demand as equal public state.
A `sufficient_for_fixed_flow_cash` result applies only to the pinned separable,
fixed-quantity FLOW model.

## Reproduce from the retained package

Materialize Library file `file_00000000426481f5abbc7dd2b7a6278f`, verify ZIP
SHA-256 `82573a9463a9c6d5d725610d39ce032551928e0fd0c0fedfc65d1f098b106ca6`,
extract it, and run:

```sh
python -B run_checks.py --output /tmp/amber-cash-check
```

That command verifies both original input manifests, runs the 21 focused methods,
reconciles every saved settlement, and rebuilds the arrival map. It does not
repeat the pricing enumeration, actor calls, engine transitions or games.

The original complete enumeration can be regenerated separately with
`exhaustive_cash_scan.py` and the two exact input archives in the retained
package. Do not run it against moving-main dependencies and call the result the
same experiment.

## Evidence boundaries

The original source used frozen HAZEL/FLOW/DATE dependencies identified in
`RESULTS.json`. Current FLOW compatibility was checked separately by AMBER-CASH;
that result is not a new exhaustive enumeration. PRISM's expected-cash and
minimax-regret objectives, AMBER's arrival law, RILL's physical continuations and
ADMISSION-TIMING's later-arrival tails remain separate components.

No canonical TITAN runtime, current archive, default, game seed, submission or
spending is changed by this delivery.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
