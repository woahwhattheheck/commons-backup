# E7 post-town-tick sale: recovered V3.1 source

## Canonical destination and status

This directory is source custody within the sole `main:revenue/kaggriculture/cloud-execution-lab/candidates/v4` workspace. It is NOT an enabled production policy, a new V4 variant, or evidence of a current V4 score improvement. Follow the workspace CANONICAL.json and INTEGRATION.json. Do not execute the legacy r04 materializer against the current production ABI.

## Original source and exact objects

Recovered unchanged from unmerged PR #12459, source branch `astra/v31-pr12430-e7-market-slot-custody-20260911`, final source commit `24f58903e819825f2d07163f86dc2337a33a01eb`. That child PR targets the original E7 branch `astra/v31-e7-post-town-tick-20260911`; the original source PR is #12430. Mechanism authorship and review history remain with those original PRs. Fresh PR metadata establishes these branch names; the first recovery note's branch label was incorrect, but the pinned commit and three source objects are unchanged.

Original paths were beneath `candidates/v3/experiments/`:

| Relative file | Exact original Git blob |
| --- | --- |
| e7_post_tick_evening_flush.py | e5ed61613cfa8a6d23809166d9310a8f569a65d4 |
| test_e7_post_tick_evening_flush.py | 999a4c2e2fc3f26fe8ea32e81f8b6b04e28f8bfc |
| e7_post_tick/candidate.py | 83072e8ee2bbe50c4ecee5787180df8163287f21 |

The table records original donor bytes, preserved in Git history. The helper now includes the separately recorded lifecycle repair below; the original test and evaluator remain unchanged. This is not a path-adapted runnable V4 package. Imports and evaluator configuration still refer to the original V3.1 R04 layout. Bind dependencies and parent semantics explicitly during the production-ABI port; do not hide import failures with mocks and call that a materialized gate.

## Historical evidence boundary

Fresh Actions reads for original head `24f58903e819825f2d07163f86dc2337a33a01eb` confirm `titan-v31-e7-post-tick-flush` run `34584285975` completed successfully. Its `focused-source-gate` job `103214777183` reports success for exact-event checkout, frozen scope/imported-blob binding, compile/E7 predecessors, evaluator-custody/package-neutrality smoke, and clean checkout. Detailed job-log retrieval returned HTTP 404 during source recovery.

The same historical head's broader `tests` run `34584286032` reports FAILURE; its cause was not investigated in source recovery. The focused E7 result is therefore not an all-CI-green claim. These historical checks do not validate the later lifecycle repair or a current V4 package, economics gate, leaderboard gain, or submission.

The earlier recovery commit `1b57582d7532268be1a6d83f94d300f91454fb4b` on `titan/v4-20260911` is donor history only. A Slack rate-limit gap concealed the canonical-main migration during that first recovery; the stale #12620 handoff was corrected in place. The actual main source landing is merged PR #12662, commit `a3caa32096afbd346729f01027924cc473e68316`. Do not continue the retired branch or merge its legacy materializer into current production.

## Lifecycle repair, still unwired

ASTRA-E7-LIFECYCLE advanced the SAME helper from `e5ed6161` to `bb8e0ff12734dc882b700e5d3d07c82a014e0cde`. `LIFECYCLE.json` records exact code, test, collaborator and engine identities, executed counts and remaining gates.

The official interpreter ends after action `episodeSteps - 2`. Before withholding, E7 now requires a plain-integer horizon with `source_step + 2 <= episodeSteps - 2`. Equality admits a sale on the final executable callback. Release revalidates supported configuration/horizon and retains exact parent action on rejection. Partial release shortfalls now record `wanted - issued`: these are units not incrementally issued by E7, including parent-covered units, NOT necessarily lost stock or cash. Quote-uplift telemetry is still not cash attribution.

Executed on Python 3.13.5: 21/21 normal and 21/21 optimized, no skips; 1,248 release-accounting cells, 112 short-horizon cells, 56 equality boundaries, 540 default action/state comparisons, and 24 paired complete-interpreter suffix cases (108 interpreter calls) per mode. Exact predecessor fails 524 subcases per mode. Four deliberate mutations are rejected in both modes. py_compile passes.

Constructed both-seat witness: source47 with episodeSteps49 or50 strands five MILK under the predecessor; repaired incumbent sale realizes 780 coins before DONE. EpisodeSteps51 permits release49: both versions realize 797 coins. Default720 already has R04 LAST_STEP718 protection; this is NOT a claimed standard-game terminal gain or evidence of field occurrence.

The test-only `e7_router_test_slice.py` contains selected R04 collaborator bodies and constants, not a second controller or a complete router. The full official interpreter is executed on constructed states; initialization is not used and the seed shim raises if called. Whole-router import, complete-router AST comparison, original tests against that full import, current ABI/package, hosted3.11 and full-game economics remain NOT_RUN. Supplying `--router` enables a strict whole-source pin plus selected-AST/constants comparison; it does not execute the router.

### Reproduce component checks

Run from repo root with an existing copy of artifact10285621024 extracted. `ENGINE_DIR` must contain its `seed-retry-runtime/kaggriculture.py` AND adjacent `kaggriculture.json` (exact hashes in LIFECYCLE.json). No download, workflow dispatch or materializer is performed by these commands.

```sh
P=revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/gameplay/e7-post-tick
ENGINE_DIR=/path/to/extracted/seed-retry-runtime
TMP=$(mktemp -d)
git cat-file blob e5ed61613cfa8a6d23809166d9310a8f569a65d4 > "$TMP/e7_original.py"
python "$P/test_e7_lifecycle.py" --engine "$ENGINE_DIR/kaggriculture.py" --baseline "$TMP/e7_original.py"
python -O "$P/test_e7_lifecycle.py" --engine "$ENGINE_DIR/kaggriculture.py" --baseline "$TMP/e7_original.py"
```

For the optional source-comparison gate, add `--router revenue/kaggriculture/cloud-execution-lab/candidates/v4/donor/overlay/r04_full_router.py` to either invocation. Expected exact router blob is `a3e2fe87c717d128e43c9b65bae2265f40d1d76d`; drift fails instead of silently rebinding.

## Required before activation

Port the existing mechanism once, without a duplicate feature key. Rebind to the exact current V4 parent; preserve native market rows and lockstep indexes; demonstrate disabled callable/action identity; run the real materialized source tests and paired/common-gate seeds, seats and opponents with actual activation and economic attribution. The lifecycle checks narrow the terminal, stale-state and malformed-release risks but are not a complete state-space or economic proof. Recovered code stays unwired until the remaining gates pass.

This source repair changes no production runtime, donor router, overlay wiring, feature default, workflow, shared materializer, archive, or Kaggle submission.
