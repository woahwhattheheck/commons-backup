# L3 public-supply pressure gate — experiment only

This directory is a **default-off, package-neutral diagnostic arm** stacked on the exact current-base L3 carrier (#12377). It does not change `overlay/**`, `V3-MANIFEST.json`, `FILES.json`, deterministic V3 defaults, the official evaluator, an opponent, or any Kaggle artifact.

## Why this exists

L3's source seam is correct but its unconditional `step >= 648` policy is not opponent-robust. The same late reservation suppression that is strongly positive against Arlene-like controls was reproduced as strongly negative against exact V3.1 self-play. The official engine semantics explain the sign flip: waiting can win when rival supply is absent, while rival supply can make selling now strictly better.

This arm therefore asks a narrower question: **can L3 suppress only when public state does not prove recent rival net supply?**

## Exact public-state discriminator

Between consecutive observations, for each product:

```
rival_net_supply_lower_bound =
    current_public_market_inventory
  - previous_public_market_inventory
  + deterministic_town_consumption
  - our_previous_requested_SELL_quantity
```

The engine transition is `delta_inventory = own_sell + rival_sell - own_buy - rival_buy - town_consume`. Executed own SELL cannot exceed our requested SELL quantity, and omitting our own BUY contribution only makes the estimate smaller. A floor-price `$1` SELL also remains conservative here because the official engine pays it without increasing public market inventory. Therefore a **positive** lower bound proves positive rival net supply without reading private rival inventory or guessing opponent identity.

The gate keeps an 8-transition lookback, matching the shipped E184 sale horizon. If any product has a positive rival-supply lower bound in that window, normal E184 reservation remains enabled. L3 suppression requires a **complete eight-transition clean window**; first observation, incomplete warmup, gaps/rewinds, malformed public scalar types, malformed own SELL quantities, invalid town intervals, or unknown shops all fail closed to baseline E184 behavior. Public inventory/step/player/config interval scalars are exact non-bool integers rather than Python-coerced aliases.

## Focused source predecessors

The hardened predecessor suite is **13/13 PASS** under both normal Python and `python -O`. It covers full-window warmup, pressure expiry, gap warmup, rewind fail-close, exact duplicate-shop/center demand, conservative unfillable own SELL subtraction, unknown shops, missing inventory, string/float/bool public inventory, string/float/bool step/player, malformed SELL quantities, and strict positive town intervals.

The dedicated workflow checks out the literal PR head SHA, proves the exact #12377 parent is its merge base, and rejects any diff outside the four additive experiment/workflow paths before executing those predecessors and live-R04 source pins.

## Small diagnostic receipt — not promotion evidence

Using retained ready-to-submit V3.1 artifact `F0C18AXAL04` with its pinned official evaluator/interpreter, the unconditional L3 factor first reproduced the war-room counterexample exactly:

- seed 101 vs exact V3.1: **-314** competitive margin in both seats;
- seed 102 vs exact V3.1: **-315** in both seats.

With the public-supply lower-bound gate:

- exact V3.1 self-play, seeds 101-102, both seats: **4/4 exact baseline ties** (`94543` on seed101; `97408` on seed102), zero failures;
- official starter seed101: baseline own `181100`, unconditional L3 `181252`, gated `181159` — gated retains **+59** of the +152 L3 upside;
- official starter seed102: baseline own `178346`, unconditional L3 `178436`, gated `178424` — gated retains **+78** of the +90 L3 upside.

Those executions were run before the parser/warmup hardening; the normal full-episode path already has a mature eight-transition history long before step648, so the repair is intended to preserve that signal while closing malformed/reset fail-opens. They remain tiny diagnostic evidence only, not a post-repair exact-package promotion gate.

This 2-seed diagnostic only establishes a plausible Pareto direction. It is **not** a default-on, merge, package, leaderboard, or Kaggle claim.

## Required next gate

Before any integration proposal, materialize the exact repaired candidate under the fleet's 1:1 fidelity standard and run the frozen official panel plus widened self-play/strong-opponent panels. Bind exact interpreter blobs, canonical/package identity, live `TITAN-CONFIG`, paired seeds/seats, and exact opponent fingerprints. Report per-cell paired Delta-M, L3 suppressions, guard decisions, positive lower-bound products/units, avoided reservation quantities/debts, and every negative transition. Reject on new-loss pathology or if the rescue disappears under exact-package execution.
