# TITAN V5 D2 WHEAT carry census — post-auth source result

Operation: `TITAN-V5-LEAN-FEED-CARRY-ECONOMICS-20260917-SWARMZ`

Issue: `woahwhattheheck/commons#14337`

This additive research carrier consumes the retained post-#15592 state
`D2_SOURCE_AUTHENTICATED` and narrows the lean-feed hypothesis without changing
runtime policy, `CURRENT`, `CANONICAL`, archive/default pointers, Kaggle state,
provider state, account state, spend, prize, payment, or revenue.

## What source now proves

The authenticated D2 `operating_stock.protect_feed_stock` seam is not a fixed
two-unit feed buffer and it does not buy WHEAT. For a route/window the helper has
already certified, it:

1. computes source-proven `required_wheat`,
2. credits observed shed WHEAT plus only the certified EOD returned WHEAT,
3. starts from the selected action's offered `SELL WHEAT` quantity,
4. reduces that sale only enough to preserve the proven requirement, and
5. refuses the window when the required withholding would exceed two units.

`wheat_feed_carry_oracle.py` independently derives the minimum withholding from
the stock-balance equation and compares it with the exact retained helper
equation. On every supported certified window the two equations coincide.
Therefore the final helper itself contributes **zero discretionary WHEAT
buffer** and relaxing it to `MIN_PROVABLE` liberates **zero units / zero cash**.

`PLUS_ONE` remains a research stress comparator only; it can add retained WHEAT,
but it is not a candidate and has no promotion authority.

## What this does *not* prove

The theorem is scoped to the authenticated final `protect_feed_stock` WHEAT
sale-reservation seam. It does **not** assume the upstream D2 selected action
offers every otherwise-saleable WHEAT unit. The exact D2 runtime member is
authenticated on the operator host, but its archive bytes are not retained on
the GitHub-accessible cloud surface. A public-state/operator-harness census is
still required to determine whether discretionary carry exists *upstream* by
simply failing to offer WHEAT for sale.

Accordingly:

- `candidate_build_authorized = false`
- `promotion_authorized = false`
- no dev/holdout candidate run is justified by this source theorem
- an observed runtime/helper disagreement is source/runtime drift, not instant
  candidate authority

The correct next empirical action is now much smaller: record authenticated D2
windows with observed shed WHEAT, certified EOD credit, source-proven
`required_wheat`, selected offered WHEAT sale, and the helper report. The
included `analyze_certified_window()` rejects mismatches and returns
`NO_DISCRETIONARY_EXCESS_AT_CERTIFIED_WHEAT_SEAM` for source-consistent cells.

## Retained authority bindings

- D2 archive SHA-256: `3d250d7bd32bf51f26ec1f69c2c10bc3c914e7d0cf64a078ae5bac5832465bd8`
- archive authentication receipt: `df11fce3b91bcf36ad280942ed38e1faed743ce3b23fbb6f8b8e8a5ada65fb46`
- safe member manifest: `d0c150d5be46a6f5e5b3275197c0f3279f4f7345b61e0ff917196db5a1eca84c`
- runtime member: `titan_runtime.py`
- runtime Git-blob identity: `e0cdcf5a5dbe350d442d3b492795d37507449853`
- operating-stock Git-blob identity: `80b372bfd34d04a2c9e2376fa02917f21f659c41`
- official engine SHA-256: `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`
- harness SHA-256: `853850d8673cff0b21fdfe783e2dfcd539b8b2707bfe2d36c2e60d8ec2e43ea4`

## Validation

Root bridge `test_titan_v5_wheat_feed_carry_oracle.py` is enrolled by the
existing Commons test battery. It exercises status binding, bool/int rejection,
duplicate-key and huge-integer ingress, source-helper mismatch rejection,
uncertified-window fail-closed behavior, source helper ceiling behavior, and an
exhaustive representative state grid under both normal Python and real
`python -O`.

The test suite is pure/stdlib-only and performs no network or provider mutation.
