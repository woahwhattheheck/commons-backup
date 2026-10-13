# F3 nightly feed frontier — built locally, not merged

This additive packet belongs to the existing sole V4 package:
`revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/gameplay/f3-v217-eod-tail/`.
It does not create another V4, controller, runtime feature key, submission, or default.
The existing legacy helper and R04 materializer are neither edited nor executed.

## Result

The legacy F3 selector allows only a single farmer target whose outbound FEED
ends exactly at reset. This research variant lets an idle farmer **or existing
hand** use already-carried wheat on up to three endangered animals, then wait
through the genuine nightly reset. It searches at most six reachable targets
per actor. All displaced incumbent commands must be literal PASS; represented
future feeding by another actor blocks the target. Unknown future-hand feeding
fails conservatively. The last season day cannot borrow a nonexistent reset.
The objective is rescue count within the declared bounded pool, **not money**.
`enabled=False` is the API default. No production caller invokes this code.

On the recovered b567 native release, seed 17 gives one real cow-rescue opportunity
at (6,3): actor 5 moves/feeds at steps 622–623, or actor 4 feeds at step 623.
Independent full-engine replays of the original actual action tapes to terminal
step 718 produce **+65 own game cash, +0 rival cash**, in both seats and both
Python modes. These two timings are alternatives for the SAME animal, not +130.
The other six seed/seat cells (seeds 1,101,9922999) have zero offers for this rule.
This is not an estimated field-wide gain.

A tempting earlier seed-17 offer at step 546 is rejected: the incumbent farmer
already feeds that target at step 548. A separate pair of constructed full-season
controls makes the opportunity cost explicit: rescue plus later HARVEST/DROP/SELL
is +463; rescue with no subsequent monetization is **−24**, both seats. Constructed
animals and starting states are injected fixtures, not claimed naturally reached
setups. Animal survival alone is not sufficient economic admission.

## Executed evidence

26/26 tests normal and 26/26 under `python -O`, zero errors/skips; 6,381 full
interpreter invocations including initializations per baseline suite. Eight
purposefully defective source variants each fail a named behavioral assertion
in each mode, not merely import errors. Missing and altered engine dependencies
are rejected before the loader can download or import them. Coverage includes
80 deterministic randomized multi-target interpreter cases per mode, both seats,
farmer/hand identity, real reset, wheat consumption, occupied work, future feed,
unknown future hands, malformed inputs, final season boundary, immutable outputs,
actual returned-action drift, and positive/negative terminal economics.

Eight seed/seat baseline cells are repeated in normal and optimized Python:
16 complete unchanged-native games, 11,504 native entrypoint calls, **zero
fallbacks**, eight fixed-action candidate suffixes and eight matched controls.
All eight matched control replays reproduce the baseline full-state hashes;
normal and optimized baseline action/full-state hashes also match for all eight
seed/seat cells. The native matrix invokes the full interpreter 13,064 times,
including initializations and suffix replays. It is not 16 candidate games.

All 110 input archive files are byte-authenticated before and after each native
game. Engine Git objects are checked before import. No reference mechanics are
replaced. The proposal API sees only the own-player observation and own route;
full two-player simulation state remains oracle-side. Compressed JSON receipts
retain actual joint tapes, source identities, proposal snapshots and all terminal
counterfactuals. Tests retain their complete logs and semantic-control failures.

## Reproduce offline

The distribution ZIP includes the checked input archive separately from the
repository patch. From the ZIP's top-level directory:

```bash
mkdir native-base
tar -xzf inputs/titan-current.tar.gz -C native-base
export TITAN_NATIVE_ROOT="$PWD/native-base"
export TITAN_ARCHIVE="$PWD/inputs/titan-current.tar.gz"
cd revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/gameplay/f3-v217-eod-tail
python check_night_feed_frontier.py --native-root "$TITAN_NATIVE_ROOT" --output /tmp/f3-normal.json
python -O check_night_feed_frontier.py --native-root "$TITAN_NATIVE_ROOT" --output /tmp/f3-optimized.json
python run_night_feed_frontier.py --native-root "$TITAN_NATIVE_ROOT" --archive "$TITAN_ARCHIVE" --seed 17 --seat 0 --output /tmp/f3-native-17-0.json
```

For the recorded matrix repeat the last command for seeds 1,17,101,9922999 and
seats 0,1, once normally and once with `python -O`. Run serially. Native code has
wall-clock deadlines; do not interpret concurrent-load timing as policy quality.
The test was executed on Python 3.13.5. Python 3.11 remains NOT_RUN.

## Integration boundary and limitations

This is source and executable evidence, **not an activated native port**. The
existing single native composer owns the integration boundary. An actual port
must run before the selected-action snapshots and commit its returned units
through the existing lifecycle; adding a post-return override would not establish
correct history/stock/snapshot custody. Multi-step cancellation after displacement
needs its own lifecycle proof. The oracle deliberately validates the complete
ACTUAL incumbent tail before it begins a fixed-tape replay and rejects drift.
That is not a live future guarantee. Resolve economics (including planned animal
retirement) and adaptive opponents before activating any variant.

The checked b567 artifact is not silently relabeled current main. Latest source
readback was cb70fb5c, with the existing F3 donor package unchanged. Current-stack
composition, adaptive candidate games, stronger opponents, hosted Kaggle behavior,
and whole-V4 promotion are NOT_RUN. No paid or owner-PC compute was used.

## Publication status

**LOCAL_BUILT_TESTED_UNMERGED_UNACTIVATED.** GitHub and Slack were discovered and
read, including #titan-kaggriculture, #build-demand and #delegations. This session
exposes no Slack posting or GitHub write/merge action, and no authenticated CLI
write route was available. No claim, handoff, push, or merge was published. The
accompanying patch adds only these files to the existing F3 directory. Its local
application check is not a remote merge certificate.
