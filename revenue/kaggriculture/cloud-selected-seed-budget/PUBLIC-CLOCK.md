# Selected seed-budget public-clock compatibility

The existing `compile_demand` and `transform` functions now accept the redundant
`step` key omitted or null when public `day` and `hour` identify the decision.
The inferred value is `day * turnsPerDay + hour`; the configured period defaults
to 24. A supplied non-null step retains precedence, including zero. The original
strict integer contract is retained; booleans, numeric strings and fractional
clocks are not coerced. Inferred hours must be within their configured day.
`configuration=None` uses the ordinary defaults. Caller objects are not changed.

Both functions normalize before binding the context. Equivalent explicit,
omitted and null step representations therefore share a contract. Different
observation time, player, action or stock still invalidates that contract.
Missing or invalid public clock data is not guessed: compilation raises a
validation error; transformation of a complete contract returns the unchanged
selected action with `invalid_current_context`. Incomplete contracts retain the
existing unchanged-action path.

No additional controller, clock service, policy entrypoint or release is added.
The request-count calculation, per-branch maxima, standing reserves, market-slot
preservation and absence of assumed purchase fills are unchanged. A seed-saving
proposal still needs whole-queue economic evaluation; it is not cash dominance.
JUNIPER's supplied-actor wrapper and ALDER's input-budget work are separate.

## Reproduce

Use the existing pinned engine cache and existing offline loader, with no new
download or engine implementation:

```sh
D=revenue/kaggriculture/cloud-selected-seed-budget
export KAG_ENGINE_DIR=/path/to/existing/engine
export TITAN_ENGINE_LOADER="$PWD/revenue/kaggriculture/20260907-offline-agent/evaluate.py"
TITAN_CLOCK_REPORT=/tmp/seed-clock.json python -B "$D/test_public_clock.py"
```

The test harness checks all three cached engine file hashes before calling the
existing loader. Both environment variables omitted means only the 20 ordinary
methods run and native setup is explicitly skipped. A partially configured,
missing or hash-mismatched native input is an error, not a passing native result.
`TITAN_SEED_SOURCE` can select an exact retained source file for a negative control.
For example, extract the original runtime from PR9961's merge
`36ec529659f038725ce325a19c2079a2a5b898b7`, whose Git blob is
`78bd08b00a8b7fcf934dcf25c54ece51746a5f5e`, and run this same suite against it.

The application CLI is unchanged:

```sh
python "$D/selected_seed_budget.py" case.json --output proposal.json
```

The input can now have `observation.step` omitted or null and
`configuration: null`. All existing explicit continuation rows must still cover
the remaining executable decisions. Current PLANT requests remain excluded
because the caller provides post-unit seeds; the normalization does not invent
future routes, fills or private rival information.

## Executed scope

The final source passes 24 new methods, zero skips, including four native methods
in both positions: 14 official market calls and 10 official unit primitives.
These are constructed interface/transition fixtures, not full games. The same
suite on the original source records seven assertion failures and 40 error or
subtest records across 24 methods; these are not 47 distinct tests. The baseline
missing-step witness raises `KeyError('step')` before a contract is built.

An additional 256 deterministic explicit-input comparisons match the complete
old/new contracts, context hashes and proposal dictionaries exactly, with no
input mutations. The original integer/stock/rule/binding helpers, demand-contract
class and CLI function are AST-identical. Only the two public functions gain a
normalization call, supported by the new private helper and nullable annotations.

Native sparse-input checks preserve the prior two-plant saving of 70 game cash,
terminal unused-seed saving of 90, and the adverse liquidity example where a
later unchanged hire becomes funded and leaves 143 less cash. Those cases check
this input representation, not a new economic improvement or mitigation of the
known liquidity interaction. The earlier PR9961 validation remains its original
source-specific result and has not been relabeled as this execution.

Source and result identities are in `PUBLIC-CLOCK-VALIDATION.json`. Full original
logs, original runtime, explicit-input comparison records and the reproduction
script are retained in the companion delivery ZIP. No scored panel, hidden game
seed, canonical archive, live default, Kaggle submission or owner-PC execution
is changed by this repair. Hosted checks are recorded separately on its PR.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
