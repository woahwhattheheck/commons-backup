# Exact terminal receipt objectives

A dependency-free receipt-to-objective adapter for existing complete-plan
consumers. It does not construct a controller, rival model, population trainer,
engine, or scenario distribution. It does not alter selected TITAN.

## Interface

`terminal_utility.build_table(document)` accepts ordered `plan_ids`, ordered
`scenario_ids`, a `baseline` plan, and one receipt for each plan/scenario pair.
Each receipt supplies `plan`, `scenario`, absolute `own_cash`, absolute
`rival_cash`, and a boolean `done`. The example JSON is an actual constructed
terminal fixture executed through the pinned official interpreter, not a scored
full game.

The output retains both cash ledgers, cash-margin changes, exact terminal points
(win=1, tie=1/2, loss=0), absolute centered utility `2U-1`, and baseline-relative
centered-utility changes. Fractions are serialized as exact strings. Source and
extra receipt fields are preserved without modifying the caller's document.
Missing cells or cash remain explicit. Any incomplete or nonterminal receipt
leaves the table as a **cash-margin proxy** with no terminal points. No
continuation distribution or terminal probability is inferred.

Optional `plan_sha256`, `scenario_sha256`, and `public_state_sha256` bindings are
compared when provided. A complete own plan cannot silently change across rival
columns; the same rival column cannot change across own plans. Missing bindings
are reported, not invented. Matching supplied hashes are a data-consistency
check, not a proof that an arbitrary caller's rollout is correct or causal.

`solve_terminal(table, existing_t15_solver, objective="absolute")` consumes the
unchanged T15 `solve_table` callable. The default objective is absolute terminal
win points. T15's zero-baseline solver can implement that objective by constant
translation **only when the baseline utility is constant across the columns**.
With a varying baseline, the helper returns `absolute_matrix_solver_needed`
and the complete absolute utility table; it does not silently optimize a
different objective. A general absolute-matrix consumer can use that table.

Explicit `objective="baseline_relative"` instead optimizes the worst expected
change against the scenario-matched baseline. This is a different objective and
is labeled accordingly. Expectations are over the chosen complete own plans,
not an invented probability distribution over rival worlds. The output reports
expected win points, not a calibrated probability of winning. Ties matter.

The existing T15 solver supports baseline plus at most two alternatives and at
most 32 supplied correlated scenarios. This adapter does not expand that solver
or assert feasibility of proposed plans. Every complete action sequence and its
physical/funding/slot feasibility remain the caller's responsibility.

## Executable usage

From the repository root:

```sh
D=revenue/kaggriculture/cloud-terminal-utility
S=revenue/kaggriculture/cloud-market-game-theory/solver.py
python "$D/terminal_utility.py" --input "$D/example-terminal-receipts.json" \
  --solver-file "$S" --output /tmp/terminal-objective.json
python -m unittest discover -s "$D" -p 'test_*.py' -v
```

The CLI reads only supplied local files. `--objective baseline_relative` is an
explicit opt-in to the relative guarantee rather than absolute win points.

Rebuild the actual interpreter cases using an existing local engine cache and
an existing evaluator loader. Engine bytes are checked before the loader is
called, so the fixture command does not fetch missing source:

```sh
python "$D/engine_cases.py" --engine-dir /path/to/existing/engine \
  --engine-loader /path/to/existing/evaluate.py --solver-file "$S" \
  --output /tmp/terminal-engine-cases.json
```

`engine-cases.json.xz` retains all 66 final action transitions, ten cases, both
player positions, exact source hashes, complete own/rival queues, initial/final
cash, rewards, remaining sheds, and paired bindings. There are 66 separate
fixture initializations; these are not counted as action transitions. The
initializer uses seed0 only to construct a fixed manufactured state. No full
game, held seed, public episode, agent, or provider call is used.

The optional test-only SciPy comparison is separate from production:

```sh
python "$D/oracle_check.py" --solver-file "$S" --output /tmp/terminal-oracle.json
```

## Retained results and limits

Thirty focused regressions pass, including actual unchanged-T15 consumption,
CLI round trips, missing/nonterminal data, exact rational ties, paired bindings,
and reconstruction of the retained engine tables. An independent linear
program agrees on all 243 enumerated constant-baseline 3-plan/2-scenario
absolute-utility problems (largest floating difference 1.12e-16). All 486
varying-baseline combinations take the explicit absolute-interface branch.
Those checks execute no additional engine steps.

The principal terminal fixture has initial public cash lead30, own WHEAT2 and
MILK2, and two possible complete rival scenarios. Relative terminal cash is:

| Complete own plan | Rival WHEAT17 | Rival MILK2 then WHEAT3 |
| --- | ---: | ---: |
| Delayed baseline | -4 | -2 |
| WHEAT first | +1 | -1 |
| MILK first | -4 | +6 |

The unchanged cash-margin solver chooses weights2/3 and1/3, yielding worst
expected win points1/3. Terminal win points choose1/2 and1/2, yielding1/2.
This is a constructed finite-scenario decision, not observed game-strength
improvement. A legal extra rival WHEAT20 scenario makes every plan lose and
removes the positive bound; the helper retains baseline. Lead35 already wins
all included scenarios and keeps baseline for the terminal objective.

Lead33 supplies an important interface negative: the baseline loses one
scenario and wins the other, while WHEAT-first wins both. A zero-baseline
**relative** maximin table has optimum zero and T15's tie preference retains
baseline. That must not be described as solving the **absolute** win objective.
The default helper exposes the absolute table for the appropriate consumer
instead. At action717 the same current cash values are not terminal, so no win
labels or solver invocation are produced. The pinned interpreter's final
executable action is718 for episodeSteps720; its DONE rewards equal final cash.

Development used manufactured one-market enumeration to locate this
illustration, not held-game selection. The retained validation receipt separates
that discovery work and its early non-discriminating trial from the final 66
verified transitions. There is no claim that the two rival scenarios span all
feasible behavior, that expected protection holds in each realized outcome, or
that this table is a whole-game equilibrium. Default SELL and every existing
policy, source path, panel, and seed allocation are unchanged.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
