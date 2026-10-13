# ARC-AGI-2 / 2026 deterministic baseline

A dependency-free symbolic baseline for the 2026 ARC-AGI-2 paid competition lane. It learns one task-local hypothesis from the supplied training pairs and applies it to each test input.

## What it does

- validates ARC grids (rectangular, 1–30 cells per side, colors 0–9);
- tries a fixed deterministic library of dihedral, crop, scale, repeat, tile, symmetry, and completion primitives;
- searches background color as a verified hypothesis parameter for background-sensitive rules instead of assuming the modal color is background;
- extracts tight foreground regions and largest/smallest 4-connected components for any verified background color;
- includes separator-delimited two-panel intersection and self-mask/fractal expansion hypotheses;
- includes conservative Latin-square zero completion and two-axis quadrant mirroring;
- infers one global color remapping that must be consistent across every training pair;
- emits two distinct predictions when available and deterministic fallbacks otherwise;
- writes the required Kaggle `submission.json` shape: every task ID, every test output in order, and both `attempt_1` + `attempt_2`.

Every candidate rule must reproduce every supplied training output exactly before it is allowed to predict a test output. The library is intentionally small and symbolic. This is a measured baseline and packaging scaffold, not a claim of competitive ARC-AGI-2 performance.

## Measured public-training regression set

Development measurements use the official **training** split only. Public evaluation tasks are reserved from iterative tuning.

The accumulated five-task training regression set is `68b16354`, `67e8384a`, `4cd1b7b2`, `0520fde7`, and `007bbfb7`. The first depth increment moved the first three from 1/3 to 3/3 pass@2. The current relation/component increment preserves those three and adds:

- `0520fde7`: separator-delimited panel intersection (`panel_overlap_vertical_bg0`);
- `007bbfb7`: self-mask/fractal expansion (`self_mask_expand_bg0`).

Against the same five tasks, the immediately previous baseline is 3/5 pass@2 and the current baseline is 5/5 pass@2. This is a bounded regression set, **not** an estimate of training-set, public-evaluation, semi-private, private, or leaderboard accuracy. Public task files remain in the official `arcprize/ARC-AGI-2` repository and are not copied into Commons.

### 2026-10-05 targeted post-benchmark increment

The complete public-training leave-one-demonstration-out receipt on the immediately preceding solver measured **134 / 3,232 folds (4.1460%)** at pass@2. The two transforms added after that run were selected from tasks that the receipt showed at zero passed folds:

- `00d62c1b`: fill 4-connected zero regions that do not reach the grid border with color 4 — candidate replay is 5/5 LODO folds, and the task's held-back public-training test example is exact.
- `00576224`: repeat the input as a 3×3 tile field while horizontally reflecting the middle tile-row band — candidate replay is 2/2 LODO folds, and the held-back public-training test example is exact.

The complete 1,000-task / 3,232-fold public-training LODO rerun has now finished on exact solver head `80faa19347d365cca73619544e8121951cb2edc1` against `arcprize/ARC-AGI-2@f3283f727488ad98fe575ea6a5ac981e4a188e49`:

- **151 / 3,232 exact held-out folds pass@2 (4.6720%)**;
- **38 / 1,000 tasks pass every held-out fold (3.8%)**;
- prior complete baseline: 134 / 3,232 folds and 33 / 1,000 tasks;
- net delta: **+17 folds and +5 all-fold tasks**, with zero per-task regressions.

The complete result is recorded in Commons PR #31852. Runner wall time was 14.635 seconds with 15,592 KiB peak RSS; solver SHA-256 is `56ac575f1648ea36c9f0da0f800dd7e31f4fd7f32fcb6e18c33504a1058bd80e` and raw result JSON SHA-256 is `56df95ed95258bf2e4a7f468727c5577ebb0a791c89c75a5129e4b021d70ccb1`. These figures remain public-training cross-validation evidence, not a Kaggle score or private-test estimate.

## Run

```bash
python research/arc-agi-2-2026/arc2_baseline.py \
  /kaggle/input/competitions/arc-prize-2026-arc-agi-2/arc-agi_test_challenges.json \
  --output submission.json
```

Focused tests:

```bash
cd research/arc-agi-2-2026
python -m unittest -v test_arc2_baseline.py
python arc2_baseline.py synthetic_challenges.json --output /tmp/arc2-submission.json
```

## Competition contract pinned 2026-09-08

The Kaggle competition page requires `submission.json`; every task ID from the challenges file must be present; each test output has exactly two predictions named `attempt_1` and `attempt_2`; multiple test outputs stay in input order. Evaluation notebooks run without internet and must stay within the competition runtime limit. See the official ARC Prize 2026 ARC-AGI-2 competition page for current binding details.

## Development discipline

- use public **training** tasks for iterative rule development and regression measurement;
- keep public evaluation tasks out of the optimization loop;
- require exact reproduction of all demonstrations before a hypothesis can emit a test prediction;
- report only explicitly measured bounded sets until a full allowed benchmark run exists;
- do not claim a Kaggle submission, rank, score, award, or payment without an actual external receipt.

## Next high-value solver work

1. add periodic-pattern completion and object-relation transforms grounded in training tasks;
2. add counting, separator, and symmetry-repair hypotheses;
3. score hypotheses by training simplicity and ambiguity rather than fixed order;
4. keep the complete **training-only** LODO benchmark as the regression gate for each solver increment;
5. reserve public evaluation for a final held-out check, then use Kaggle/private scoring only through the competition's permitted path.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

