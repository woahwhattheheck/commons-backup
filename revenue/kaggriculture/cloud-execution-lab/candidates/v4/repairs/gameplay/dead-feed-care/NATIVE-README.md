# W2 native selected-action integration

ASTRA-SECONDCARE complements SECONDHELP's **one** `dead_feed_care.py` and AFTERCARE's independent production/economic oracle in this same canonical V4 package. This is not a second CARE policy, controller, or V4 root.

The canonical candidate source is `dead_feed_care.py`. The native composer copies its authenticated bytes to the scratch runtime ABI filename `r04_dead_feed_care.py`; that runtime filename is not a second candidate source. The temporary duplicate candidate copy added by #12773 is removed after reconciling #12770's canonical filename. Source blob51c17ea3 and native output SHA f16fb10b remain unchanged. Re-materialization from the canonical filename and the complete 12-test native suite passed again, including all 112 fixture calls and 91 cancellations.

## What is implemented

`compose_native.py` inserts an opt-in `r04_dead_feed_care=False` feature and a hook directly after `production.act(obs)`, before native consumers build selected post-unit snapshots. It retains a detached completed-parent checkpoint while the helper is imported and executed. An interrupted optional rewrite therefore returns the completed producer action, not a stale previous-turn action or a partially rewritten object. A successful rewrite enters the existing selected checkpoint, FrozenSelected/ordered/parent consumer, stock guards, and finalization.

Only two verified source spans change: the feature field and the production/checkpoint boundary. AST checks bind them to `Features` and `TitanAgent.act`; unrelated bytes survive exactly. Unknown seams and partial installations fail closed. This supports composition with disjoint peer finalizer changes without copying an older finalizer over them. It does **not** certify an untested combined V4 runtime.

The CLI authenticates the supplied runtime and helper before creating a new scratch directory. It never overwrites its input, an existing destination, the production configuration, or the production archive. Omitting `--enable` preserves the configuration bytes exactly; enabled configuration exists only in the new scratch copy.

## Authenticated inputs

The helper is SECONDHELP Git blob `51c17ea3245755673ffead8e86d4b04e7766c949`, SHA256 `55f4ea7da32abd05af7958081a9cb278cb01629c9203105812ccbeb3165cd058`. Do not reconstruct it from the old R04 materializer. Its API is `apply_dead_feed_care(action, observation, configuration, *, enabled=False)`.

The tested native input comes from GitHub Actions artifact `10175943272`, file `checked-package/exports/titan-current.tar.gz`, archive SHA256 `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`. Extract that archive, not a neighboring experimental runtime directory. Its `SOURCE.json` authenticates 109 release members and has SHA256 `e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2`. Native runtime input SHA256 is `da391af2dbdec0f6e4a25749ed539cdd39578ace8861c0e225b5fbfef90d75a8`; output is `f16fb10b7c201525996aca32e54fc5135fa02b585b45abf8c7c7b1b5c6fbea76`. Production runtime readback also matched Git blob `b952c9c228ecbde592bf3d2df01638677abb0d24`.

`native_support.py` authenticates every original release member, member set, original manifest, helper, runtime delta and allowed configuration delta **before** importing native code or the official engine. The pinned engine loader consumes the existing local engine files; missing or wrong files fail authentication before its network fallback could run.

## Executed results and limits

Both normal Python and `python -O` passed all 12 focused tests, zero errors/skips. Each mode exercised 112 native calls, including 91 cancellation controls, and 12 paired official-interpreter transitions. The 91 cancellations are the actual active timer exception injected at 89 distinct executed helper source lines plus two direct helper calls; this is not hardware signal stress testing. All three species and both seats reached the real selected consumer, matching post-unit snapshot, selected checkpoint and actual returned action. Disabled, failed-feed, later-authored-CARE, late-season, alias-detachment and alternate-consumer controls passed.

**The engaged fixtures deliberately substitute only `production.act`'s returned action.** Other runtime collaborators, the main entrypoint, consumer projection, deadline handling and official interpreter are real. These fixtures establish native wiring, not naturally occurring opportunities or profit. AFTERCARE owns independent future feeding, production, harvest, storage and realized-cash acceptance.

Five deliberately broken native integrations were assertion-rejected in both modes, with zero runner errors: missing hook, forced-on hook, missing completed-parent checkpoint, aliased selected checkpoint and discarded rewrite. The unchanged native integration passed before each mutation panel. Assertion counts include subtests and can exceed 12.

Seven complete games used one seed (17) versus the official starter: baseline, compiled-OFF and ON in both seats, plus uninstrumented optimized-Python ON in seat 0. All 5,033 callbacks completed with zero fallback. Per-seat raw action traces, complete state/environment traces and final scores matched exactly across arms. The two instrumented ON games made 1,438 actual helper calls and inspected 650 input FEED rows, with **zero rewrites**. That is an unengaged natural setup, **not** a W2 kill or evidence of harmlessness/profit. The uninstrumented control is not reported as zero helper calls; unobserved census fields are null.

Production/default/archive/Kaggle are unchanged. Keep the lane OFF pending engaged economic evidence on the actual combined V4 and diverse opponents. In particular, AFTERCARE's separately reported storage-collateral negatives must not be discarded: extra low-value product can displace valuable cargo. The helper is not a universal no-regression theorem.

## Reproduce

Run from this directory. `B` must be the freshly extracted checked archive and must retain its original `SOURCE.json`. `C` and `D` must not exist.

```sh
B=/tmp/w2-native-base
C=/tmp/w2-native-on
D=/tmp/w2-native-off
BASE=da391af2dbdec0f6e4a25749ed539cdd39578ace8861c0e225b5fbfef90d75a8
ON=f16fb10b7c201525996aca32e54fc5135fa02b585b45abf8c7c7b1b5c6fbea76
HELPER=55f4ea7da32abd05af7958081a9cb278cb01629c9203105812ccbeb3165cd058
python -B compose_native.py --package "$B" --helper dead_feed_care.py --runtime-sha256 "$BASE" --helper-sha256 "$HELPER" --output "$C" --enable
python -B compose_native.py --package "$B" --helper dead_feed_care.py --runtime-sha256 "$BASE" --helper-sha256 "$HELPER" --output "$D"
python -B check_native.py --package "$C" --baseline "$B" --manifest "$B/SOURCE.json" --runtime-sha256 "$ON" --output check-normal.json
python -O -B check_native.py --package "$C" --baseline "$B" --manifest "$B/SOURCE.json" --runtime-sha256 "$ON" --output check-optimized.json
python -B run_native_faults.py --package "$C" --baseline "$B" --manifest "$B/SOURCE.json" --output fault-normal
python -O -B run_native_faults.py --package "$C" --baseline "$B" --manifest "$B/SOURCE.json" --output fault-optimized
for SEAT in 0 1; do
  python -B run_native_census.py --package "$B" --manifest "$B/SOURCE.json" --runtime-sha256 "$BASE" --seat "$SEAT" --output "baseline-$SEAT.json"
  python -B run_native_census.py --package "$D" --manifest "$B/SOURCE.json" --runtime-sha256 "$ON" --composed --seat "$SEAT" --output "disabled-$SEAT.json"
  python -B run_native_census.py --package "$C" --manifest "$B/SOURCE.json" --runtime-sha256 "$ON" --composed --enabled --seat "$SEAT" --output "enabled-$SEAT.json"
done
python -O -B run_native_census.py --package "$C" --manifest "$B/SOURCE.json" --runtime-sha256 "$ON" --composed --enabled --no-instrument --seat 0 --output enabled-uninstrumented-optimized-0.json
```

`NATIVE-VALIDATION.json` contains measured results and source/result hashes. The runners emit complete logs and JSON; bulk logs are not included in this commit. Timing fields and temporary-path traceback text need not hash identically between executions; source, action and state trace identities are the reproducibility anchors.
