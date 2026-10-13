# TITAN V3 intersection gate

Operation: `titan-v3-paired-game-intersection-closure-20260910-01`

This is an additive, fail-closed companion to the existing native paired-game gate. It does not reinterpret or overwrite a historical gate decision. A new contract binds the exact parent-report bytes by SHA-256, independently recomputes every cell from the two terminal score vectors, verifies the complete opponent × seed × seat grid, and then evaluates evidence dimensions that opponent-only and seat-only marginals cannot prove.

## Defect closed

A balanced aggregate can still conceal a losing intersection. For example, opponent means and seat means can all be nonnegative while one `(opponent, candidate_seat)` stratum is negative. Likewise, global mean margin can be positive while one two-seat `(opponent, seed)` pair has negative margin.

Those are release-evidence defects, not gameplay factors. They matter whenever own cash and rival cash move in opposite directions, or when a seat-specific regression is offset by another opponent/seat cell.

## Hard contract

Before policy evaluation, the adapter requires:

- one regular, bounded parent report read through a single file descriptor;
- exact SHA-256 equality to the immutable intersection contract;
- strict UTF-8 JSON with duplicate-key and non-finite-number rejection;
- an exact Cartesian grid of declared opponents × seeds × seats `[0, 1]`;
- no missing, extra, or duplicate cells;
- exactly two finite terminal scores per baseline/candidate cell;
- exact recomputation of own, rival, and margin deltas from the candidate seat;
- exact recomputation of W/T/L results; and
- a coherent parent `PROMOTE`; this requirement is literal and cannot be disabled.

It then reports and gates:

- two-seat pair mean own cash and margin;
- positive-margin pair fraction and worst pair margin;
- opponent × candidate-seat own-cash summaries;
- opponent × candidate-seat margin summaries; and
- the count and worst mean of negative intersection strata.

Exit codes are `0 PROMOTE`, `2 INVALID`, and `3 REJECT`.

## Usage

```bash
python3 intersection_gate.py \
  --contract INTERSECTION-CONTRACT.json \
  --parent-report GATE.json \
  --output INTERSECTION-GATE.json
```

The parent report must remain the output of the existing paired-game gate. This adapter is not a replacement for row-level candidate-byte custody, source/archive provenance, official-engine execution, action-trace causality, holdout separation, or hosted leaderboard calibration.

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 \
  python3 -m unittest -v test_intersection_gate.py
python3 -m py_compile intersection_gate.py test_intersection_gate.py
```

Twenty-two contracts cover Simpson-masked own cash, Simpson-masked margin, negative pair margin hidden by positive intersection means, parent-verdict escalation, malformed/invalid parent reports, digest drift, duplicate/missing cells, contradictory deltas, non-finite/boolean/overflowing arithmetic, duplicate/unknown contract keys, missing and symlinked inputs, evidence-path output aliasing, deterministic output, and stable CLI exits.

## Scope

No TITAN policy, scheduler, runtime, configuration, archive, export, release pointer, provider state, Kaggle state, or game execution is changed. The reviewed parent metric source is Git blob `288f35aa15b137c9bea67df5d3492abae1ce92f8`; `PREDECESSOR-WITNESSES.json` binds the arithmetic counterexamples to that review.
