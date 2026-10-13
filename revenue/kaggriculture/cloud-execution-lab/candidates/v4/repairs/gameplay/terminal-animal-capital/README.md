# H5 terminal animal-capital guard — V4 recovery

This package is the single V4 H5 terminal animal-capital authority. It is
**default off** and is not wired into the production runtime.

## Mechanism

The original V3.1 H5 theorem (PR #12471) and its first V4 recovery incorrectly
treated “first EGG/MILK/WOOL production is after terminal” as proof that a late
`BUY_ANIMAL` has no remaining value. The pinned official engine disproves that:
every surviving **placed** animal becomes `fertilizer_available=True` at EOD,
independent of species-product maturity. A maturity-only guard can therefore
erase a real BUY -> PICKUP -> PLACE -> EOD fertilizer -> collect/use/sell route.

H5 now uses a much narrower source theorem that does not depend on product
maturity at all:

1. unit actions execute before market orders;
2. `BUY_ANIMAL` therefore puts the purchased animal in the shed only after the
   current callback's unit phase;
3. a later unit action must `PICKUP` the animal into one actor's inventory;
4. a separate later unit action must `PLACE` it on a matching unoccupied
   structure.

Thus a purchased animal needs at least **two later unit callbacks** before it can
become a placed animal and enter *any* animal-refresh/product/fertilizer channel.
Under the standard 720-step contract with last executable action step 718, only
steps 717–718 satisfy that static proof. Step 716 remains parent-owned because
callbacks 717 and 718 can still realize PICKUP then PLACE. Earlier final-plan
steps also remain parent-owned unless some future route-aware proof is added.

The only permitted edit is replacing an eligible executable-prefix `BUY_ANIMAL`
market row with `[]`, preserving the raw market vector length. The component may
be called from the final-plan window (step 648), but every step without the
strict no-placement proof returns the parent action unchanged.

Saved cash can make later market orders newly executable. Therefore H5 edits
only the provably-dead animal-buy suffix after the last other non-SELL,
non-placeholder executable market row. Every worker command, SELL row and
quantity, HIRE, BUY_LAND, BUY_SEED, BUY_PRODUCT, unknown order, unknown animal,
and nonexecuted raw suffix row is parent-owned.

## Provenance and repaired boundary

Historical falsifier: PR #12471 review `5177174337` / retirement
`5632547232`. The same engine-level counterexample was rediscovered against
merged V4 #12949 and blocks any activation/economics claim from that predecessor.

Official-engine source identity at repair:
`reference/engine/kaggriculture.py` Git blob
`3c202c7ee921da239356789e266b694635103fc4`.

The component keeps strict fail-closed timing and market-prefix parsing:
missing, bool/float/string-poisoned, or nonstandard `turnsPerDay` /
`episodeSteps` fail closed. Missing `maxMarketOrdersPerTurn` uses the official
default 10; an explicitly supplied **plain int** follows the interpreter's
`max(1, value)` executable-prefix rule, so zero/negative ints still expose row 0.
Bool, float, string, `None`, and other non-int cap values remain outside H5's
source-safe contract and fail closed.

## Authority boundary

Source/mechanism only until a current-native route census proves natural
engagement of the **repaired** step-717/718 theorem. Zero engagement terminalizes
the lane without runtime wiring. If it engages, the next gate must prove both-seat
execution, unchanged unit/liquidation behavior, saved terminal cash, paired
own/rival money and margin, and no harmful externality across representative
opponents. No default/config/archive/Kaggle change is authorized here.
