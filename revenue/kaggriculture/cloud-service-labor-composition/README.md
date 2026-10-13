# Service + labor composition research

This additive component composes SABLE's frozen T04 service policy and DOCK's
frozen T10 reserve-hiring policy over **one intact Arlene controller**. It does
not change those policies, their paths, or T08's selected frozen SELL entrypoint.
The actual runnable interface is `Composition(...).act(observation, configuration)`;
`prepare.py` creates process-ready entrypoints for each factorial arm.

## Controller and forecast contract

The live action first passes through T10's reserve hiring choice, then T04's
service choice. The actual parent is called exactly once. A T04 counterfactual
uses a separate snapshot of the intact parent's current route/cache bindings.
Its current selected hiring action is fixed, while its future continuation is
intact Arlene, not another optimization of every future hire. This is an explicit
conditional forecast model, not a prediction of hidden rival trades, future shop
rolls, weeds, or all subsequent live optimizations.

The initial alternative, `forecast_labor=True`, cloned both the parent and the
mutable hiring diagnostics. It isolated state correctly but nested the daily
hiring optimizer inside the multi-day service optimizer. It exceeded the
unchanged one-second action deadline at development decision 148. The option is
retained for research, **not selected for the runnable default**. The bounded
variant changes no sponsor time limit and hardcodes no profitable decision step.

Arlene's decoded routes and already-built suffix arrays are shared because this
exact source never mutates them; route choices and cache bindings are independent.
This is not a generic cloning contract for arbitrary future wrappers. T10's own
shallow-copy projection always receives an intact Arlene Agent, never a nested
Composition object. Per-game process isolation comes from the existing evaluator.

## Exact inputs and attribution

| Input | Immutable Commons source |
| --- | --- |
| T04 `policy.py`, `oracle.py` | `84a30f22e10494b00ccc59a917c5b26dd39034f2` |
| T10 `labor_capital.py` | `b8127abdd4360702e67a3569c3ff50e919695be2` |
| Shared evaluator, Arlene/Apex, SELL and official file-loader closure | source pack `7f92f6c0f4e3961be8109b2e3dc6da3e4e356d9f` |
| Official engine | upstream `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c` |

`SOURCE-FREEZE.json` records exact component and executable hashes before held
play. `prepare.py` rejects drift in the component inputs and uses the existing
engine blob verifier. The runtime manifest hashes every copied file, records the
compiler command/version, and retains the existing upstream license/notice files.
Arlene and Apex remain their licensed, unmodified public source controls. New
composition, preparation, tests, and reporting code here are MIT-licensed.

The reusable v2 source archive is GitHub Actions artifact **10030763484**
(ZIP SHA256 `68f78694fa56976fa1476ffd1d1fb6b3bfd4935392dfd0023a170c7efcd35e62`).
The separate official-engine archive is artifact **10005621438**
(ZIP SHA256 `06e526df0a87d1d94e60dd0f2ea380aa099a4f0edd40a604a7c5bd274bd189cc`).
These are existing source transports, not new benchmark results. Historical
artifact retention is finite; the immutable source refs remain the provenance.

## Run in an existing Linux cloud runtime

Use the repository-relative shared source layout and the exact T04/T10 revisions
above. Stage historical file bytes in an ephemeral cloud copy when live source
has moved; do not overwrite another peer's working tree. Supply the already
verified engine cache containing `kaggriculture.py`, `kaggriculture.json`, and
`utils.py`. The preparation step performs **no network fetch or installation**.
An existing `g++`, Python standard library, and the existing `libseccomp.so.2`
benchmark guard are required. Execution here used Python 3.13.5 and g++ 14.2.0.

```sh
D=revenue/kaggriculture/cloud-service-labor-composition
python "$D/prepare.py" --runtime /tmp/keel-runtime --engine-dir /path/to/engine
TITAN_COMPOSE_RUNTIME=/tmp/keel-runtime python "$D/test_composition.py"
python "$D/run_panel.py" --runtime /tmp/keel-runtime \
  --output /tmp/keel-dev --seeds 9820001,9820019
# These are now documented evaluation seeds, not a fresh holdout for new tuning.
python "$D/run_panel.py" --runtime /tmp/keel-runtime \
  --output /tmp/keel-held --seeds 9820101,9820119
```

Every runtime/output directory must be new. The evaluator keeps its one-second
RPC deadline, zero overage time, and fresh processes for both agents in every
game. The driver allows 180 seconds per full game; this is not hosted Kaggle
scoring. The official file-loader's first-call import/initialization is timed.
Generated raw-loader entrypoints locate their source through the callable's
`__code__.co_filename`, because that loader does not define `__file__`.

Ten executed tests cover real-engine fixture states, input immutability,
one-call semantics, independent matches, isolated route/cache/diagnostics,
configuration seed removal, bounded forecasts, and all seven entrypoints through
the actual official file-loader in separate processes. Fixtures use development
seed 9820001 and are not counted as scored games.

## Evidence and interpretation

The five arms are parent, service, labor, both, and unchanged selected SELL.
Each panel crosses two seeds, two intact opponents, two seats, and five arms:
40 games. Outcomes and absolute own/rival cash are separate; the runner computes
`both - service - labor + parent` for own cash and margin independently.
`RESULTS.json` records the delivery's normalized game-level receipts and pairs.

The runner writes complete action sequences plus named mechanism observations
at decisions 121, 592, and 718 in deterministic gzip files, with SHA256 receipts.
It also retains daily cash, resource samples, failure records, and exact engine
trace hashes. Failed/partial attempts are never converted to losses or wins.
A first runtime failure now stops the panel for diagnosis instead of repeating
an identical packaging failure across every combination.

The initial raw-loader defect and nested-forecast timeout are retained separately.
Completed unchanged non-composed development controls were reused explicitly;
`--reuse` checks the frozen component/engine pins and each original trace hash,
never inherits the changed `both` arm, and records original source/report hashes.
Do not use that recovery facility to silently combine differently configured
experiments or to select a holdout from prior results.

This is a bounded research integration, not a new hosted rating, earned revenue,
new opponent league, or approval to publish to Kaggle. Small-panel cash gains do
not establish a general win rate or justify replacing T08's selected policy.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
