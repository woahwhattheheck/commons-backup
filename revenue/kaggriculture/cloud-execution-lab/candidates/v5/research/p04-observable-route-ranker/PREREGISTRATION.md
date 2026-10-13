# TITAN V5 P04 — pre-registered route selector bridge

This is the **pre-declared consumer** of the merged #13478 route-matrix reducer. It is not a second route harness and it does not activate gameplay. The rule/fitting procedure was fixed before this lane consumed any R00–R12 terminal outcomes.

## Frozen authority

- production-v3 archive: `20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239`
- active R04 source: `41ea55c5f20c43cd58c5099fbadb212de62ec95a95dfc2e6e1e19c3d4d55b39a`
- #13478 reducer schema: `titan-v5-p04-route-ranker/v1`
- pre-registration rule-spec SHA256: `c0d57d3b20aba4ce8ecca7cc07ac3cf56bd7f7aeb9260efe1f6519d62aa8719e`
- pre-outcome discovery-universe SHA256: `3c393d57c4caae9c5ee3b4e6c1110220efbb556b48230ca209061b57a4119a66`
- discovery-universe source: #titan-kaggriculture `C0C0Z8AHGP2` message TS `1789253666.394169`, published before any R00–R12 terminal outcomes
- selection boundary: step 144; existing forced terminal plan2 at step 648 remains unchanged.

`p04_preregistered_selector.py --print-preregistration` emits the exact frozen fitting contract, the pre-outcome experiment-universe commitment, and the accepted evidence boundary. The rule SPEC and universe commitments remain unchanged by later custody hardening.

## Why this is a successor to #13501

#13501 merged at `cbe7a9d8098e4ef6e01cf0cb919a3141de45d233` before the later summary-authenticity review was closed. Its merged version has the predeclared selector, universe binding, and incumbent-control fail-close, but still accepts caller-authored reduced summaries. The post-merge branch commits were therefore **not** treated as if they had landed through #13501. This successor carries only the evidence-authority hardening onto live main.

## Evidence authority: canonical committed raw rows, never caller-authored summaries

Exact universe keys alone do not authenticate outcomes: a caller could preserve all eight legal `(seed, opponent, seat)` keys while forging feature values and plan deltas in a reduced report. The public fitting path now rejects reduced summaries outright.

Accepted fitting is deliberately narrow:

1. the public API derives the repository root from the checked-in module; callers cannot supply an arbitrary `repo_root`;
2. the checkout's `origin` URL must identify `woahwhattheheck/commons`;
3. `refs/remotes/origin/main` must exist — local `main` is **not** an authority fallback;
4. the evidence commit must be one exact lowercase 40-hex commit that is an ancestor of `origin/main`;
5. every evidence path must live under `revenue/kaggriculture/cloud-execution-lab/candidates/v5/selective-carrot/route-matrix-native/` and end in `.jsonl`;
6. bytes are loaded with `git show <commit>:<path>`, never from the mutable working tree;
7. each committed file's byte SHA256 and row count are recorded in the output receipt; and
8. merged #13478 `reduce_matrix()` recomputes the report from those exact raw rows before the selector sees any feature or delta.

The old `fit_selector(reduced_report)` entry point always raises. The test-only `_fit_selector_from_repo()` seam exists only to exercise custody hostiles; production API/CLI do not expose repository-root injection.

This is a local Git trust boundary, not a claim that Git manufactures native truth. Native executors still own capture quality. The selector trusts only P04 raw evidence already admitted to canonical Commons `origin/main`, then recomputes the reducer output itself. A dirty working tree cannot alter consumed bytes; a side-branch-only commit cannot become authority; a repository with a noncanonical origin is rejected; and deleting `origin/main` does not silently fall back to local `main`.

## Pre-outcome universe binding

After #13478 reduction, the report must contain the exact pre-outcome route board:

- seeds `1209131101` and `1209131102`;
- opponents `apex_v7` and `arlene_v14`;
- seats `0` and `1`;
- exact Cartesian product = eight `(seed, opponent, seat)` groups.

Missing groups, extra groups, substitutions, or duplicates fail before rule enumeration or scoring.

## Rule class

Fallback is always the source-recomputed incumbent `SHOP_PLANS` decision. The fitter may nominate only:

1. one global natural step-144 plan override; or
2. one equality predicate over one already-merged #13478 public feature, then one natural-plan override, otherwise incumbent.

Natural plans are `0,1,3..12`; diagnostic plan2 is excluded. Allowed predicates are exactly #13478's `shop_pair`, `first_two_yarn_count`, three public market comparisons, and rival visible-tile crop/livestock leaders. Seed, opponent, seat, snapshot hash, private inventory/shed state, future town state, RNG, and future fields cannot be predicates.

## Discovery gate

Every engaged comparison must have both candidate and incumbent-control rows free of evaluator failures, `delta_margin_vs_incumbent >= 0`, and `delta_own_vs_incumbent >= 0`. Failure accounting records candidate, incumbent-control, and combined invalid-comparison groups separately.

A rule also needs positive total margin delta plus cross-seed, cross-opponent, and both-seat coverage. Selection remains deterministic and worst-cell-first. Discovery may only nominate: output is always `policy_ready=false` and `composer_ready=false`.

## Held-out / convergence contract

Any nomination remains default-OFF. A separate native owner must run fresh held-out cells using the exact nominated rule bytes/spec hash/universe hash plus the committed-evidence receipt. Only a held-out winner may become a staging component on the single production-v3/V5 composer line. No CURRENT/default/release/Kaggle mutation is authorized here.

## Source gate

From this directory:

```bash
python -B -m py_compile p04_preregistered_selector.py test_p04_preregistered_selector.py
python -B -m unittest -v test_p04_preregistered_selector.py
python -O -B -m unittest -v test_p04_preregistered_selector.py
python -B p04_preregistered_selector.py --print-preregistration
```

The focused suite contains 29 methods. Hostiles cover subset/extra-group rejection, candidate and incumbent failure handling, forged reduced-summary rejection, committed-row reduction, dirty-working-tree irrelevance, side-branch rejection, namespace confinement, public repository-root derivation, noncanonical-origin rejection, removal of the local-main fallback, fake-local-origin/main rejection, ambient Git environment (`GIT_*`) redirection neutralization, Git replace-ref tampering prevention (`--no-replace-objects`), and fail-closed authenticated remote tip verification (`ls-remote`). Exact-head mounted execution plus independent source red-team are the drain gates.
