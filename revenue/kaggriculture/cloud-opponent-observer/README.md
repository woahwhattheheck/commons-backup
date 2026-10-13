# COK V10 activation observer

An offline evaluation adapter for T07's existing COK opponent. It returns the
original action and records the actual persisted route selection after that
call. It does not replace the opponent, patch its functions, start an engine,
fetch sources, or choose a policy for TITAN.

## Use the existing artifacts

Extract public-source artifact **10032525998** from `woahwhattheheck/commons` to
`SOURCES`. Extract source-loader artifact **10030763484**, then extract its
`titan-reusable-sources.tar`, preserving repository paths; set `PACK` to its
`revenue/kaggriculture/cloud-pack` directory. Retain the source bank's LICENSE,
THIRD_PARTY_NOTICES.md and LICENSES directory beside COK's original source.
No new export or opponent retrieval is necessary.

The executed input is `COK-ZhangZiliang/Kaggriculture` commit
`7ef67eac458cd9ecd13786063e2e581fbe7403ec`, `main.py`, Git blob
`736577e3810f018f1844b8ac9824a4e69b4c37d3`, SHA-256
`56831f3c43c9727d90016b7a7a8d4eb51d1a4c08c1120d58f061d9176e8bc109`.
This identity comes from both the artifact's `SOURCES.json` and the actual
source bytes; the upstream contents API reports the same Git blob. The source
bank's README is not substituted for this byte identity.

```python
from observe import CokObserver

opponent = CokObserver("SOURCES/cok-v10/main.py", "PACK")
action = opponent.act(observation, configuration)
record = opponent.last_record
```

Keep one instance per actor per match, as for the original T07 bank. `act`
invokes the existing official loader's original controller exactly once. It
keeps that controller's state and retry behavior. The detached `last_record`
contains source identity, action digest, observed/controller step, public
routing inputs, actual gate before/after, selected route family, sticky expert,
and cached-retry status. It retains only the latest record; stream records in
the caller rather than growing a runtime history.

`predicate_matches_now` is a diagnostic pure read. It is **not** evidence that
the source opened its gate: only step 72 evaluates that gate, and an identical
cached retry does not evaluate it again. The V5 expert choice persists after
step 168. The telemetry reads original controller state; no second controller
or hypothetical counterfactual action is run.

Only public shops, both public cash balances and rival public opening asset
counts enter the feature record. Private shed/inventories are not exported.
A route label describes controller selection, not whether every returned
operation later succeeds. Malformed telemetry is identified separately and
does not change the original action.

## Replay existing observation JSONL

Each input line has `observation`, optional `configuration`, and a `match_id`
which identifies one original match. Optional `expected_action` checks exact
action correspondence. Match IDs are metadata and are never passed to the
policy. Use already-delivered observations in chronological order, including
both shared fields and the actor's own private state; do not substitute rival
private inventory or infer a missing historical prefix.

```sh
python observe.py --source "$SOURCES/cok-v10/main.py" --pack "$PACK" \
  --input existing-observations.jsonl --output activation.jsonl \
  --summary activation-summary.json
```

The CLI constructs a separate original controller for each match/seat and
returns exit 1 for recorded telemetry errors or expected-action mismatches.
Input/source files cannot be selected as its output files. Summary counts are
per call and include retry counts and observed gate/expert transitions. The
`has_every_step_0_through_718` field describes the observed step set, not proof
of an official complete game, a continuous state trajectory or a win. Input
coverage, game outcomes and activation are separate facts.

Raw seat-1 replay storage may omit the shared `step`. Hydrate shared fields in
the replay intake using the official delivery contract before calling an
observation-only policy. This adapter does not manufacture a day/hour step:
it records a missing step explicitly and preserves the original controller's
step-zero behavior. This is necessary for action correspondence.

## Validation and reproduction

Reuse engine artifact **10005621438**, its `engine/` directory, and the
`cloud-eval/evaluate.py` from the same source-loader archive. Run from this
directory with existing extracted paths:

```sh
T07_COK_SOURCE="$SOURCES/cok-v10/main.py" T07_PACK="$PACK" \
TITAN_ENGINE="$ENGINE" TITAN_EVALUATOR="$EVALUATOR" \
python -m unittest -v
```

Sixteen tests pass against the real pinned source and preserved official
loader. The suite includes 1,438 exact action comparisons over two chronological
719-observation **synthetic sequences**, one for each seat, with zero differences;
these are not full games. Positive/negative gates, same-step close-only behavior,
cached retries, missing shared step, source identity, detached records and the
step-168 sticky route are covered. An additional real official-engine
initialization and one transition checks both actor observations/actions.
`VALIDATION.json` records scope and source hashes. No new scored games, hidden
panels, historical smoke reruns, Kaggle uploads or selection changes occurred.

This component measures activation on supplied inputs. It supplies no new
opponent win rate and does not label T07's original 12-game smoke as activated.

## License and provenance

Observer/CLI and tests: Apache-2.0, under the Commons repository license.
Original COK source is not copied or relicensed here. Its complete T07-carried
third-party notice retains the distinction between independently written
controller code, attributed routes and public-behavior reconstruction. The
existing cloud-pack loader retains its original license and upstream manifest.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
