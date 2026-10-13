# Joint rival stock and cash feasibility

Optional, standard-library-only analysis of caller-supplied ordered rival paths.
`rival_feasibility.py` and `linear_bounds.py` are the complete runtime. Python 3.10+.
No controller, price model, game package, network call, private rival observation,
or probability estimate is imported. Existing policies and evaluation panels are
unchanged.

## Callable

```python
from rival_feasibility import Interval, RivalLedger, check_extension, check_column

base = RivalLedger(["WHEAT", "EGG"], 100, as_of_step=5,
                   cash=Interval(100, 100))
# A complete conditional path with no intervening stock additions:
path = [dict(kind="sale", step=5, product="WHEAT", quantity=60, cash=None),
        dict(kind="sale", step=5, product="EGG", quantity=60, cash=None)]
result = check_extension(base, path, complete=True)
assert not result.keep  # The two products cannot share a 100-unit initial shed.
assert result.result.reason == "certified_contradiction"
```

`keep=True` means possible or unknown in a real-valued linear relaxation, NOT a
physically executable plan or an estimate of hidden stock. Fractional witnesses
are intentionally retained. `keep=False` requires an independently verified
nonnegative combination of the original inequalities proving a contradiction.
The certificate is in `result.result.certificate`; check it with
`linear_bounds.verify_certificate(candidate.constraints, certificate)` after
rebuilding that exact candidate with `base.fork().event(...)`.

Initial per-product shed bounds default to `[0, capacity]`, with ONE shared total
capacity constraint. Carry defaults to `[0, infinity)` and is separate from shed.
Cash defaults to `[0, infinity)`. Omitted products loosen capacity constraints;
they do not establish free space. Supply only justified bounds. `as_of_step`
is the latest observed time, not a future evaluation time.

`event(kind, step=..., product=..., quantity=..., cash=...)` appends an event.
Kinds: `sale`, `buy`, `deposit`, `pickup`, `harvest`, `consume`, `discard`,
`income`, `expense`, `cash_checkpoint`. Events must arrive in actual execution
order; equal-step events are checked separately, never netted. `quantity` means
actual realized fill or accepted transfer, not an order request. A partial DROP
is its accepted deposit followed by a separate discard of the remaining carry.
A `buy` adds to shed; `pickup` moves shed to carry; `consume` removes carry.

For sales and buys, `cash` is the total receipt or expense computed from the
COMPLETE ordered own/rival stream, including paired unit quotes. Supply an
integer, `Fraction`, rational string, or conservative `Interval`. Floats are
not accepted. `cash=None` means unknown nonnegative money, never zero. Extra
nonmarket effects use `income`/`expense`, with an unbounded interval when their
amount is unknown. Historical public net cash is not gross sale revenue.
`cash_checkpoint` binds actual public cash only at or before `as_of_step`.
Never pass a future replay balance as an observation.

`complete=True` is a modeling assertion: every possibly relevant transition in
the path is represented, exactly or by a conservative interval in the correct
order. It does not assert perfect knowledge. Include uncertain harvests,
deposits, purchases and costs instead of silently setting them to zero. An
interval transfer uses one variable in both locations and conserves stock.
Default `complete=False` retains the path as unknown. Inconsistent base facts,
malformed candidate events, and exhausted budgets also retain it as unknown.

`check_column(base, events_for_each_own_plan, complete=..., limits=...)` uses a
single shared budget. A whole table column is removed only when EVERY supplied
own-plan pricing path is contradicted. Mixed applicability is returned as
`conditional=True`; do not turn that result into a rectangular zero-sum table
or replace an individual cell without modeling the conditional rival response.
The original source labels, streams, and own-plan identities remain the caller's.

`linear_bounds.Limits` defaults to 2,048 rows, 8,192 pair combinations, 2,048-bit
rational coefficients, and 25 ms of cooperative time budget. The budget includes
base validation and candidate work. It is not a hard real-time limit or a
whole-agent timing claim. Larger systems can return unknown without pruning.

## Existing stream interface

`t12_sale_events(product, stream, receipts=callback)` accepts the existing T12
`(label, ((step, quantity), ...), alignment)` tuple. The callback receives that
ENTIRE original stream and an event index; use the exact scorer for the specific
own plan. Labels are not filtered or reinterpreted. This adapter alone does not
supply missing production, stock transfers or nonmarket costs. Multiple product
streams need a caller-supplied correlated ordering; do not concatenate independent
product scenarios and claim a feasible joint rival strategy.

Interface inspected at Commons commit
`4d7fd6d4d4e1f71941f7fe76b8e10274f1bfc1a6`,
`cloud-market-response/flow.py`, Git blob
`7b3c1c383e98ce1eb5bf539caddf0ab4351f8633`. The source remains unchanged.

## Reproduction and retained results

```sh
python -m unittest -v test_feasibility
python read_results.py --output /tmp/rill-results.json
python verify_engine.py --engine-root /path/to/existing/engine --output /tmp/engine.json
# Optional independent development check; SciPy is NOT needed by the runtime:
python verify_solver.py --output /tmp/solver.json
```

The existing Commons Actions artifact `10005621438` supplies the engine files;
no new export job is needed. Place `kaggriculture.py`, `kaggriculture.json`, and
`utils.py` together in the supplied engine directory. Engine source is
[Kaggle/kaggle-environments at 28b6d8af](https://github.com/Kaggle/kaggle-environments/tree/28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c/kaggle_environments/envs/kaggriculture),
Apache-2.0, and is NOT redistributed in this component. The verifier checks the
engine's exact SHA-256 and Git blob before executing its unchanged market stage.
Its import-only seed helper raises if called; no episode initialization is
performed. A recording wrapper delegates every actual commit to the original
engine function.

Recorded execution: 18 unit tests pass; 18 official market stages yield 36
per-seat paths, all retained. All 36 altered-receipt controls are rejected with
verified certificates, and all 36 are retained after the missing expense is
left unknown. Products, floor regimes, order permutations, and both seats are
retained in the evidence. Maximum measured warm call was 2.418 ms, including
base validation, on these small cases only. No full games or policy-strength
measurements were run.

An independent SciPy 1.17.0 HiGHS comparison matches 160/160 deterministic
algebraic systems: 75 possible, 85 infeasible with exact certificates. These
are linear-system fixtures, not game seeds. The four `evidence/*.b64` pieces
retain the complete engine paths, LP systems/certificates, and unit output. `read_results.py`
checks both archive and decoded hashes from `VALIDATION.json` before returning
results. The manifest binds all published source bytes used by these checks.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
