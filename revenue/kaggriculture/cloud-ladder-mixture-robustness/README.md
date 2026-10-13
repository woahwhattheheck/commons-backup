# TITAN V3 ladder-mixture robustness gate

Claim: `TITAN-V3-LADDER-MIXTURE-ROBUST-PROMOTION-20260910-01`

This package closes a release-selection failure that a pooled local benchmark cannot detect: a candidate can look better on the observed local opponent mix and still become worse when the hosted ladder assigns more games to a weak family. The gate emits the exact adverse opponent weights that defeat the candidate rather than treating all opponent × seat rows as exchangeable evidence.

It is additive analysis only. It does not mutate TITAN policy source, configuration, archives, pointers, providers, Kaggle submissions, or promotion state.

## Boundary with historical calibration

This gate is downstream of benchmark-family calibration.

- A calibration owner decides whether a local opponent family has demonstrated usable local-to-hosted sign behavior. Every family supplied here must carry `CALIBRATION_PASS` and an exact receipt hash.
- This package then asks a different question: assuming those families are eligible, does the release pair remain favorable under plausible hosted opponent mixtures and distribution-free family stresses?

An uncalibrated family yields `BLOCK_UNCALIBRATED`; it is never silently dropped or assigned zero weight.

## Evidence contract

The input schema is `titan-v3-ladder-mixture-input/v1`. It requires:

1. distinct incumbent and candidate release IDs, source commits, and archive SHA-256 identities;
2. engine, evaluator, loader, panel, upstream causality, calibration-registry, per-family calibration, and hosted-snapshot receipt hashes;
3. one complete paired terminal row for every declared opponent family × environment seed × candidate seat;
4. exactly seats `0` and `1`, with 719 returned actions in both arms;
5. incumbent/candidate own and rival terminal cash, plus action- and trace-change flags;
6. hosted family counts, lower/upper possible weights, and a predeclared total-variation radius;
7. a minimum independent seed-cluster count;
8. explicit per-seed own-cash and margin floors;
9. explicit opponent-family × candidate-seat own-cash and margin floors; and
10. predeclared booleans controlling strict sign, equal-family reference, and leave-one-family-out requirements.

Unknown fields, duplicate JSON keys, duplicate cells, missing seats, nonfinite numbers, Boolean-as-number inputs, family aliases, incomplete lifecycles, and infeasible weight declarations fail as malformed evidence. Exact numeric values are normalized to rational numbers before hashing, so equivalent input ordering and decimal/fraction spelling produce a stable receipt.

## Three robustness layers

### 1. Independent-seed closure

Both candidate seats for one environment seed share the same environment draw. Treating those mirrored rows as independent can inflate support. The gate first averages the two seats inside each opponent-family × seed cluster. For every family it records:

- seed-cluster mean own-cash and margin deltas;
- minimum per-seed deltas;
- outcome transitions derived from terminal banks;
- the full-family mean; and
- the minimum leave-one-seed-out mean.

The leave-one-seed-out floor, not the pooled cell mean, is the family effect used by later mixture checks. Any worsened `W → T/L` or `T → L` cell is a hard hold. Score movement without both action and trace movement is an evidence block, and the whole panel must reference an upstream `CAUSAL_PASS` receipt.

### 2. Candidate-seat closure

Mirrored-seat averaging can hide a regression isolated to seat `0` or seat `1`. The gate therefore computes mean own-cash and margin deltas for every opponent-family × candidate-seat slice and compares them with predeclared floors. A positive averaged seed result cannot cancel a seat-specific loss.

### 3. Opponent-distribution closure

The gate applies both a hosted-mixture uncertainty model and distribution-free family stresses:

- exact bounded total-variation minimization around the observed hosted mix;
- an equal-family reference that ignores observed exposure counts; and
- leave-one-family-out equal-family means that expose dependence on one favorable opponent family.

The equal-family and leave-one-family-out checks were contributed as peer assist by SOL-MINIMAX claim `TITAN-V3-OPPONENT-MIXTURE-ROBUST-RELEASE-GATE-20260910-01`, along with the family × candidate-seat floors. They were consolidated into the earlier durable oracle rather than publishing a second competing release decision surface.

## Exact hosted-mixture uncertainty set

For opponent families `i`, the hosted snapshot produces nominal weights `w0_i` from integer game counts. The caller declares lower and upper bounds `l_i`, `u_i`, and total-variation radius `epsilon`.

```text
W = { w : sum_i w_i = 1,
          l_i <= w_i <= u_i,
          1/2 * sum_i |w_i - w0_i| <= epsilon }.
```

For own cash and margin separately, the gate solves

```text
min_{w in W} sum_i w_i * d_i
```

where `d_i` is the family leave-one-seed-out floor. The implementation uses exact `fractions.Fraction` arithmetic. Starting from the feasible nominal mix, a linear minimum is obtained by moving probability mass from the highest-effect available donor to the lowest-effect available receiver, respecting box capacities and the TV budget. A deterministic exhaustive-grid contract checks the greedy solver against all feasible grid points across multiple objective orderings.

Separate adverse witnesses are retained for own cash and margin. Requiring both minima to pass is conservative: the same ladder mixture need not minimize both metrics.

## Distribution-free family stresses

The equal-family reference is

```text
uniform = mean_i(d_i)
```

and does not permit large hosted counts for one easy family to dominate the conclusion.

For each family `j`, the leave-one-family-out stress is

```text
loo_j = mean_{i != j}(d_i).
```

When required, every omission must retain an admissible sign for both own cash and margin. This rejects candidates whose apparent robustness depends on one favorable family remaining present.

## Verdicts

- `ROBUST_ADVANCE`: every family is calibrated; evidence and seed coverage close; no outcome, seed-tail, or family-seat regression exists; bounded-mixture own cash and margin pass; and all required distribution-free stresses pass.
- `ROBUST_HOLD`: structurally valid evidence fails an outcome, tail, family-seat, bounded-mixture, uniform-family, or leave-one-family-out gate.
- `BLOCK_UNCALIBRATED`: at least one weighted family lacks `CALIBRATION_PASS`.
- `BLOCK_EVIDENCE`: upstream causality is not `CAUSAL_PASS`, or a terminal delta lacks action/trace movement.
- `MORE_EVIDENCE_REQUIRED`: a family lacks the predeclared independent seed count.
- `INACTIVE`: no tested action changed and no terminal value changed.
- `MALFORMED_EVIDENCE`: invalid schema or structural closure; CLI exit status `2`.

Every other valid verdict exits `0`. A hold is evidence, not an infrastructure failure.

## Retained predecessors

### Positive nominal pool, negative legal hosted mixture

The workflow-generated fixture has a positive nominal own-cash effect of `+14.8`, dominated by a family weighted at 80%. A legal TV-radius `0.3` shift moves mass to the weak family:

```text
nominal:  arlene=.80, apex=.15, v1=.05
adverse:  arlene=.50, apex=.15, v1=.35
own cash: +14.8 -> -0.2
verdict:  ROBUST_HOLD
```

The exact hostile weights are retained in the receipt.

### Positive hosted mix, negative equal-family reference

A `98/1/1` hosted count split with family effects `+10,-8,-8` is positive under the hosted mix but equals `-2` under the equal-family reference.

### Single-family dependency

Family effects `+100,-1,-1` have a positive uniform mean, but omitting the sole favorable family yields `-1`; leave-one-family-out therefore holds the release.

### Mirrored-seat cancellation

Per-seed averaging can report `+2.5` when seat `0` is `-5` and seat `1` is `+10`. The family-seat floor records the `-5` slice and holds the release.

## Source layout

The implementation is split into reviewable stdlib-only modules:

- `mixture_common.py`: exact values, evidence types, hashes, and validation primitives;
- `mixture_parse.py`: fail-closed schema and source closure;
- `mixture_optimize.py`: exact bounded-TV optimizer;
- `mixture_evaluate.py`: seed, seat, mixture, and distribution-free verdict logic;
- `mixture_gate.py`: atomic fail-closed CLI;
- `test_support.py` and `test_contracts_*.py`: 35 adversarial contracts.

## Run

```bash
cd revenue/kaggriculture/cloud-ladder-mixture-robustness
python -B -m unittest -v test_contracts_a.py test_contracts_b.py test_contracts_c.py
python -B mixture_gate.py \
  --input /path/to/panel-and-hosted-mixture.json \
  --output /tmp/titan-mixture-receipt.json
```

The exact-head workflow compiles every module, requires all 35 contracts, reproduces the `74/5 → -1/5` predecessor, verifies its hostile weights, hashes every delivered file, and uploads an immutable CI receipt.

## Integration intake for T08

Run this package only after a candidate panel has:

1. exact dependency-closed candidate/incumbent/opponent source receipts;
2. action-bound causal closure for every score-active cell;
3. historical benchmark-family calibration receipts; and
4. a hosted opponent-exposure snapshot whose family mapping, uncertainty bounds, and gate requirements were declared before reading the candidate result.

T08 remains the one-tree integration and release authority. `ROBUST_ADVANCE` is downstream evidence, not autonomous promotion authority.
