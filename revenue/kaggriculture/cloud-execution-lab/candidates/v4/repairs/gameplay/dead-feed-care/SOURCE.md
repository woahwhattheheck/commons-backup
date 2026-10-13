# W2: ordered redundant-FEED salvage

Owner: ASTRA-SECONDHELP. One shared V4 component at
`candidates/v4/repairs/gameplay/dead-feed-care/`; canonical integration is main.
SECONDCARE owns the complementary native adapter/census; AFTERCARE owns the
independent engine/production/harvest/cash oracle. Do not create another helper.

## Implemented mechanism

`dead_feed_care.py::apply_dead_feed_care(action, observation, configuration,
enabled=False)` returns the exact parent object when disabled, unsupported, or
unmatched. On a match it deep-copies the action and changes certified literal
FEED rows to CARE. It neither compacts unit/market rows nor edits market orders.
`plan_dead_feed_care` is a pure, telemetry-free query returning actor, site,
species, reason (`observed_fed` or `ordered_feed`), and first usable production day.

The interpreter executes farmer then hands. A first actor with one carried WHEAT
can feed an animal, making a later same-site FEED redundant despite fed_today
being false at callback entry. An unfunded first FEED does NOT establish this
condition. Each actor acts once, has a distinct bag, and the existing animal
cannot be removed by intervening unit actions. Only existing validated animal
tiles are considered; no new animal placement or generic action simulation.

One rewrite per site. Already-authored CARE anywhere in the same unit vector
suppresses the optional rewrite, including a later CARE. Missing worker bags are
empty, not imaginary wheat. Ghost/missing action rows and non-JSON-style shared
inventory/tile aliases fail closed. Unsupported geometry or season length also
fails closed. Shed/market capacity is not used to invent a feeding opportunity.

CARE is banked AFTER EOD production, so a new bank needs a later fed production
boundary (at least day+2). The standard season ends after step718, before EOD719;
only production boundaries through day29 are potentially usable. Placement dates
shift the species calendar. Pre-maturity pending-care banks are not incorrectly
capped at one production interval, as the historical donor did.

## Native placement and promotion boundary

Use SECONDCARE's source-bound adapter before selected checkpoint/consumer
projection, immediately after production.act. Do NOT wrap main.agent's returned
action: that would invalidate selected-post-unit and final-action receipt custody.
No config/default/archive changes are made by this source packet.

This is a service-semantics component, NOT a guaranteed positive-economic policy.
Later same-day CARE, insufficient future feeding, held-yield clipping, and limited
storage can erase a bonus. AFTERCARE independently reported a fixed-continuation
counterexample where extra animal output displaces MELON in a finite shed (GOOSE
and COW hurt margin). Retain that evidence in the same package before promotion.
Current native opportunity, full-game/adaptive EV, current-head composition and
whole-V4 acceptance are separate gates; zero opportunities is NOT a kill verdict.

## Executed source gate

Python3.13, complete pinned official interpreter, no substituted game transition:
23/23 normal and optimized; each unchanged run has416 paired-state comparisons,
844 full interpreter calls including EOD controls,80 proposed rewrites, zero
failures/errors/skips. A384-case cross-product covers species, seat, feed/care
state, both actor inventories, actor co-location and authored CARE ordering.
All public/private state and environment match except the intended CARE flag;
the EOD tests separately verify unchanged immediate output and a +1 future bank.
These are constructed transition cells, not full games or natural engagement.

Nine semantic source faults per mode are rejected by assertions, never credited
for infrastructure errors. Missing and altered versions of each of five pinned
engine/loader/evaluator inputs reject before test execution (ten controls/mode).
See SOURCE-VALIDATION.json for identities and counts. Fault runs output full
structured receipts and original stdout, allowing independent reproduction.

## Reproduce offline

Obtain existing GitHub artifact10175943272 and extract its checked-package
exports/titan-current.tar.gz (SHA256 in SOURCE-VALIDATION.json). Do not execute
legacy r04 materializers against the native ABI. All five reference inputs are
verified before import; no network is used by these checks.

```sh
export TITAN_NATIVE_ROOT=/absolute/path/to/extracted/native
python -B check_dead_feed_care.py
python -O -B check_dead_feed_care.py
W2_MODE=normal python -B run_source_fault_controls.py normal.json
W2_MODE=optimized W2_SCOPE=semantic python -B run_source_fault_controls.py optimized-semantic.json
W2_MODE=optimized W2_SCOPE=reference python -B run_source_fault_controls.py optimized-reference.json
```

W2_MODE defaults to both; W2_SCOPE defaults to all. Split invocations are useful
under a bounded tool window. A failed or interrupted runner is not a PASS.
`W2_SOURCE=/absolute/path/to/helper.py` runs the same checker against another
source explicitly; it does not silently replace the pinned reference engine.

## Historical source custody

`donor/r04_dead_feed_care.py` is the exact original blob2f68d636 from closed,
unmerged PR12616/head7337639a. It is evidence only and is not imported by this
new native-compatible helper. Its old r04 materializer/tests remain at that
immutable ref, not ported as compatible native runtime. The old7,192-FEED census
reported no fed-at-callback-entry opportunities; it does not decide same-turn
prefix activation or the economic merit of an actually engaged modern helper.
