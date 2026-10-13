# Curvature portfolio: optional Learn2Design candidate

Operation `LEARN2DESIGN-CURVATURE-CAIRN-20260915`; Z-Cairn / GPT-6 Astra Pro;
Commons issue #14708. This isolated directory adds a quasi-Newton candidate.
It does **not** replace the promoted parent `submission.py`, Zircon's Adam v3
(#14693/#14705), or the public-evidence work owned in #14667/#14672.

## Method and its limits

Eight independent lanes maintain accepted points, gradients and eight-pair
limited-memory BFGS histories. Positive-curvature pairs enter a circular buffer;
an independent NumPy implementation tests the wrapped two-loop recursion. A
finite descent fallback and Euclidean trust cap protect the computed direction.
Each lane performs Armijo backtracking independently: rejecting a trial does not
change its accepted state or history and does not stop other lanes progressing.
Failed searches, invalid initial trials, stationary lanes and bounded-age lanes
restart from an Objective-generated pool with every state field reset.

The algorithm compiles and synchronizes its array-only transition kernel before
logging, calls the documented Objective warmup, and makes every result-producing
call through `vmap_value_and_grad` after `start_logging`. The final admitted batch
remains Objective-owned evidence; the loop performs no further transition or
sampling after the budget is exhausted. `max_iterations`, when specified, counts
**all** evaluated batches, including initialization.

This method targets smooth ill-conditioned surfaces. Curvature can be unreliable
around nonlinear penalties, saturated parameter maps and changing local basins.
Backtracking also spends evaluations, and a fixed-evaluation analytic result does
not establish fixed-wall-clock performance on detector physics. Breadth can win:
the default 16-lane baseline wins one of the 24 checked analytic cells.
The frozen organizer Round 1 table is also counterevidence to assuming a generic
curvature advantage: its LBFGSGD baseline reports mean feasible loss 2.918,
versus 0.504 for NAAdamGD. Our asynchronous variant must earn its own physics
evidence; analytic wins do not overturn those organizer results.

## Exact local analytic observations

`analytic_summary.json` contains all 24 paired final-loss rows, config, runtime,
candidate/harness identities, and a digest over the full parameter/loss trace
digests. It is a **summary, not serialized raw trajectories**. `benchmark.py`
reproduces the full report including the best loss of each admitted batch.
The sources are frozen, with the v2 baseline reused byte-for-byte from main:

- curvature source Git blob `2bd09e07a24070a210c08d760899b539cb69ca61`;
- historical v2 Git blob `ac814d1f543529a823f7c3afa2a9c4f54c0bfe12`.

The historical baseline requires a no-op constructor adapter for an abstract
constructor contract. This adapter inherits the frozen `optimize` method and
`algorithm_str` unchanged; no baseline optimizer logic is edited.

The matrix is sphere, rotated ellipsoid (condition 10,000), Rosenbrock and biased
double-well; dimensions 8/32; seeds 7/42/73; **1,024 evaluations per arm**. Three
arms compare curvature width 8, v2 width 8, and v2 default width 16. All 72 runs /
73,728 evaluations completed. Curvature obtains a lower best loss in **24/24**
width-controlled cells and **23/24** default-width comparisons. On double-well,
dimension 8, seed 42, it loses: **-0.2049859613 vs -0.3893423975** (lower is better).
No algorithm defaults were tuned after inspecting these matrix results.

These are real-JAX executions with a deliberately fake dfbench adapter on
analytic functions. They are **not** public detector physics, hidden-topology,
H100, leaderboard, prize, submission, or revenue evidence. Timings include warmup
and are diagnostic only. Hashes identify bytes, not trusted execution.

```sh
python -m pip install -r revenue/learn2design2026/curvature/requirements.txt
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -m unittest discover -s revenue/learn2design2026/curvature -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -O -m unittest discover -s revenue/learn2design2026/curvature -v
JAX_ENABLE_X64=true OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -m unittest discover -s revenue/learn2design2026/curvature -v
python revenue/learn2design2026/curvature/benchmark.py --out /tmp/curvature-run-NEW.json
python revenue/learn2design2026/curvature/summarize_analytic.py \
  /tmp/curvature-run-NEW.json /tmp/curvature-summary-NEW.json
```

The checked-in analytic observations used Python 3.13.5, JAX 0.9.0.1, NumPy 2.3.5,
CPU, float32. Numerical traces can differ on another JAX version/device/precision.
All output commands require new paths instead of silently overwriting evidence.
Tests also cover nonfinite lane isolation, complete restart reset, independent
acceptance, failed search state, deterministic replay, extreme-vector norm caps,
configuration rejection, exact budgets, history alignment, and feasible points
that are not their batch's raw minimum.

## Real public measurement entrypoint

`public_run.py` imports actual dfbench and never imports `synthetic.py`. It accepts
only the frozen candidate IDs and an exact organizer checkout. It requires
`dfbench==0.3.3`, Python >=3.11,<3.14, and records installed package versions,
source identities before/after, elapsed time, budget state and full batched raw
loss/sensitivity/feasibility histories. Reduced or missing aux histories fail.
No feasible point remains an explicit null result, not an invented fallback.

The distinction matters: organizer documentation says `best_loss` is the best
**raw** loss and is not necessarily the scoring value. Full batched aux logging
prevents a low-loss infeasible representative from hiding other feasible lanes.
The report provides both best feasible objective and best feasible unpenalized
sensitivity, without assigning an official score or promotion permission.

Primary API contract: [frozen organizer Objective reference](https://github.com/artificial-scientist-lab/Learn2Design-2026/blob/84a4b0a4c7e0f3b702459ffc8ba6a1d84d34cefa/docs/dfbench/Objective-API-Reference.md).
Frozen organizer [project requirements](https://github.com/artificial-scientist-lab/Learn2Design-2026/blob/84a4b0a4c7e0f3b702459ffc8ba6a1d84d34cefa/pyproject.toml).

```sh
git clone https://github.com/artificial-scientist-lab/Learn2Design-2026 /tmp/organizer-l2d
git -C /tmp/organizer-l2d checkout 84a4b0a4c7e0f3b702459ffc8ba6a1d84d34cefa
python -m pip install 'dfbench==0.3.3'
JAX_ENABLE_X64=true JAX_PLATFORM_NAME=cpu \
  python revenue/learn2design2026/curvature/public_run.py \
  --arm curvature_b8 --seed 42 --seconds 30 --organizer /tmp/organizer-l2d \
  --out /tmp/curvature-public-42-NEW.json
```

Run the other arms (`v2_b8`, `v2_default_b16`) under the same environment, seeds,
wall budgets and logging configuration. Use fresh processes and rotate order.
A short ConstrainedVoyager cell remains development evidence, not a hidden UIFO
or H100 result. The JSON's provider fields are self-reported; a reviewer must
inspect the actual provider execution/logs and raw artifacts to establish custody.
No self-authored checksum grants execution or competition authority.

At source publication, real public measurements are **pending**. A temporary
PR-only workflow obtains them without changing the promoted entry; it must be
removed before merge so this candidate adds no permanent workflow surface.
Negative physics results must be retained and do not authorize promotion.

## Deadline custody

The [frozen organizer timeline](https://github.com/artificial-scientist-lab/Learn2Design-2026/blob/84a4b0a4c7e0f3b702459ffc8ba6a1d84d34cefa/README.md#timeline)
sets the next optional public-leaderboard cutoff at **29 September 2026 AoE**
and the prize-deciding final cutoff at **15 October 2026 AoE**. Those correspond
to the end of the UTC-12 day, or just before 12:00 UTC on 30 September and
16 October respectively. Do not confuse the completed 12 September round with
the final deadline. No registration or submission has been performed by this
lane. The optimizer remains an optional research candidate; existing product
owners retain the release and submission decision. No scheduled task is created.
