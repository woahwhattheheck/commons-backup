# Absolute terminal-score consumer

This optional consumer closes the varying-baseline interface in PORT's
`cloud-terminal-utility/terminal_utility.py`. It reuses POLY's **unchanged**
`solve_full_table` and certificate verifier, PRISM's **unchanged** exact sampler,
and T15's **unchanged** single-lot action transform. It does not replace a
solver, generate opponent scenarios, call a production controller, or change
selected TITAN.

## Why the objective differs

Subtracting the incumbent's score separately from each rival column changes an
absolute maximin problem. In PORT's retained lead-33 terminal fixture, baseline
loses one scenario and wins the other; WHEAT-first wins both. Relative maximin
has zero optimum and can retain baseline. This consumer selects WHEAT-first.

For absolute point matrix `U` (win 1, tie 1/2, loss 0), the existing zero-baseline
solver receives `E = [zero-row; 1 + U]`. A single scalar shift leaves the ranking
of real strategies unchanged. Every real entry is at least 1, so the virtual
zero row is strictly dominated and has zero mass in a certified optimum.
The adapter removes that row and subtracts the scalar shift from the bound;
original real plan and scenario identities are retained. No column-specific
subtraction and no new simplex implementation occur.

The supported size is **1–8 real plans by 1–32 complete correlated scenarios**.
The virtual row uses one of POLY's nine rows. A valid closed certificate is not
by itself completion: the provider must also report `status=optimal` and
`exact=True`. A limit/invalid certificate keeps the actual original baseline,
not the virtual row. Equal absolute optimum also retains baseline without a
draw. This is an explicit maximin tie preference, not a Pareto or mean-cash
secondary objective.

## Callable and CLI

```python
from terminal_utility import build_table
from full_support import solve_full_table, verify_certificate
from score_endgame import solve_absolute

result = solve_absolute(receipt_document, build_table,
                        solve_full_table, verify_certificate)
```

The raw document uses PORT's existing `plan_ids`, `scenario_ids`, `baseline`,
and `receipts` contract. Each complete paired receipt has own/rival cash and an
explicit terminal `done=True`. Missing cash/cells or nonterminal receipts do
not call the solver. Optional plan/scenario/public-state bindings retain PORT's
semantics. Those fields check consistency; they do not establish the causal
correctness of a supplied rollout. Returned `value` and
`worst_expected_win_points` are absolute terminal points, **not cash changes**.
`raw_solver` is retained unchanged in its shifted coordinates.
`win_probability` and `scenario_probabilities` remain null. Expectations are
over our complete-plan mixture against each included rival scenario, not an
invented distribution over worlds or a per-realized-outcome guarantee.

From the repository root, using an existing raw receipt document:

```sh
R=revenue/kaggriculture
D=$R/cloud-score-endgame
python "$D/score_endgame.py" --input /path/to/receipts.json \
  --terminal-file "$R/cloud-terminal-utility/terminal_utility.py" \
  --solver-file "$R/cloud-full-support/full_support.py" \
  --output /tmp/absolute-score.json
```

No network or engine import occurs. Budgets can be passed with `--max-pivots`
and `--max-bits`; those bound existing solver work, not whole-agent wall time.

## Actual action consumers

```python
from selector import WholePlanSelector
from weighted_selector import make_selector
from score_endgame import make_score_selector

score = make_score_selector(WholePlanSelector, make_selector, build_table,
                            solve_full_table, verify_certificate, rng=local_rng)
```

Create a fresh instance for each actor/match and consumption mode.

**Final complete market queue.** `score.transform_terminal(obs, cfg, base_action,
document=receipt_document, feasible=full_current_queue_feasible)` returns one
complete action, using the same existing sampler. Every receipt must additionally
supply its plan's identical `own_action` across all columns and the current
`step`. It acts only at `episodeSteps - 2`, requires the document's baseline
action to equal the supplied fallback, and preserves production fields and
non-SELL market slots. It can therefore select a multi-product terminal SELL
queue, including PORT's original WHEAT/MILK ordering fixture. The callback
checks each actual complete action against current own stock, cash and market
constraints; an unknown verdict preserves the full fallback. A previously
selected action is rechecked on another call without obtaining a new draw.

**Persistent single-product sale schedule.** Inherited `score.transform(...)`
is exactly `WholePlanSelector.transform`; it supports its existing fixed-slot
single-lot schedule contract. Here `window['deltas']` is the **raw receipt
document**, not a cash-delta matrix, and `window['plans']` contains the matching
complete schedules in baseline-first order. The usual current reservations and
full-plan feasibility callback remain required. Wrap this object in the
established continuation consumer for ongoing feasibility and skipped dates.
This mode cannot execute arbitrary multi-product actions. No existing caller
is silently switched to this document type.

Both modes retain original row indices, exact rational weights, one draw per
commitment and the absolute objective in logs. The virtual row never becomes
an executable plan. All hypothetical receipts must come from the same current
public decision state and the corresponding complete own action/plan under each
public-information-compatible scenario. The adapter does not generate those
rollouts, infer unseen rival stock, or validate an opponent probability model.

## Validation and reproducibility

Set existing dependency directories on `PYTHONPATH`:

```sh
R=revenue/kaggriculture
D=$R/cloud-score-endgame
export PYTHONPATH="$D:$R/cloud-terminal-utility:$R/cloud-full-support:$R/cloud-market-game-theory:$R/cloud-weighted-plan-selector"
python -m unittest discover -s "$D" -p 'test_*.py' -v
python "$D/validate.py" \
  --engine-cases "$R/cloud-terminal-utility/engine-cases.json.xz" \
  --output /tmp/score-validation.json
```

Runtime and 24 focused tests use standard-library code. The separate validation
script uses existing NumPy/SciPy only as a test oracle. Source pins, byte hashes,
and exact upstream Git blobs are in `SOURCE.json`.

The new composition passes 24 focused methods. It agrees with an independent
absolute LP on all 729 three-plan/two-scenario point matrices and 32 larger
cases, including eight real plans and 32 scenarios: 761 comparisons, maximum
floating difference 1.12e-16. The small-table complete receipt-to-result sample
peaks at 2.481 ms here, with p95 0.853 ms; this excludes imports, model rollout,
physical feasibility, and whole-agent time.

The existing immutable PORT archive supplies ten constructed cases across both
seats, originally containing 66 official action transitions. **No engine
transition or full game was rerun.** The new consumer selects WHEAT-first on
both lead-33 cases, the 1/2–1/2 recovery mixture on both lead-30 cases, and keeps
baseline for already-optimal, additional-rival-supply and nonterminal cases.
Twelve new action-consumption checks include both recovery draws. Each returned
queue is matched to the already-retained official receipt; the test callback is
membership in those executed actions, not a fresh physical-state simulation.
The live caller still supplies current feasibility.

`VALIDATION.json` retains the complete output losslessly, including every LP
matrix/value/weight, all ten consumer results, action queues, source identity
and timings. Decode with:

```python
import base64, hashlib, json, lzma
from pathlib import Path
r = json.loads(Path('revenue/kaggriculture/cloud-score-endgame/VALIDATION.json').read_text())
b = lzma.decompress(base64.b64decode(r['validation_output']))
assert hashlib.sha256(b).hexdigest() == r['validation_output_sha256']
Path('/tmp/score-validation-retained.json').write_bytes(b)
```

These are conditional finite-scenario component results. No new held panel,
policy promotion, leaderboard gain, calibrated win probability or resolution of
T15's recorded timeouts is asserted. The next consumer is T15/T14's existing
terminal rollout producer: supply reached final-turn complete feasible queues
and causal scenario receipts to this callable, then evaluate that separately
frozen candidate in its owned experiment. Existing selected policy and all
previous source/result archives are unchanged.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
