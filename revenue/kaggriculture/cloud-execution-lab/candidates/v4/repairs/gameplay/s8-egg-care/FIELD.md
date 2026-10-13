# S8 independent native engagement and reachable-service field evidence

Owner: ASTRA-HENHOUSE. This is support for **GOSLING's one S8 implementation**,
not a second care policy, native composer, or alternative V4. It lives alongside
`compose_reopened_s8.py` and GOOSE's `ENGINE-LIFECYCLE.md` in the existing package.

## Result and disposition

All **120 planned full games completed**, with 719 own callbacks each (86,280
callbacks; 86,400 official interpreter calls including initialization). The six
seeds were 1, 17, 101, 2027, 6607, and 104729, each in both seats against the
**official starter**. These are named development seeds, not a global holdout.
The result is recorded in `FIELD-RESULTS.json` with every scheduled cell represented
by verified-equivalent groups and exact action/player-state hashes.

| Regime and candidate versus OFF | Completed pairs | Activated pairs | Mean cash-margin change |
| --- | ---: | ---: | ---: |
| Original native, shadow proposal only | 12 | 0 | 0 |
| Legal ordinary grower, donor | 12 | 0 | 0 |
| Legal ordinary grower, reopened combined | 12 | 0 | 0 |
| Legal disposal fixture, donor | 12 | 0 | 0 |
| Legal disposal fixture, spread only | 12 | 0 | 0 |
| Legal disposal fixture, discard only | 12 | 12 | +616.67 |
| Legal disposal fixture, combined | 12 | 12 | +616.67 |

The disposal fixture uses **startingMoney=10000 for both players and both arms**;
ordinary/native games use the default 3000. It purchases its goose and feed,
builds/places legally, and buys real WHEAT to fill its shed from day six. It also
sells WHEAT before subsequent egg drops, preserving real admission space. There
is no mature-animal injection, direct state mutation, hidden observation, or seed
exposure. The parent is a deterministic **test fixture**, not a recommended
production purchasing strategy.

For each disposal ON game, 11 actual care substitutions produced, harvested,
and sold 11 extra eggs: 26 -> 37. Useful EOD fertilizer admission stayed at 5;
collected fertilizer changed 28 -> 17 and genuinely discarded fertilizer changed
23 -> 12. Extra egg clipping and egg EOD discard were zero. Care first activated
at step 167 (day six) and last at 647. Both discard-only and combined modes had
identical action and player-state traces on this panel. Each seat's realized
cash-margin gains, by seed, were **665, 511, 668, 693, 554, 609**. Rival cash change
was zero throughout. Mean 616.67 and minimum 511 summarize **six seed blocks**,
not twelve independent observations.

This establishes a useful **reachable-regime mechanism**, not current-native
strength. Every native reference pair had zero helper proposals and identical
complete action/player-state traces. The unchanged reference already cares for
geese and supplies no qualifying S8 collection opportunity in these games.
Changing the price threshold alone did not activate the ordinary legal grower
either. These cases remain **unexercised**, not kills. Do not enable production
S8, change defaults, or submit an archive from this receipt. The existing native
assembler still owns receipt-safe placement after harvest rescue and before
final returned-action recording. All later main components were not assembled
into the reference archive used here.

## Executable files

- `reachable_goose.py`: legal-from-initializer ordinary and disposal fixtures.
- `run_s8_field.py`: pinned official-engine, process-isolated full-game runner;
  passive opportunity/effect observers; failed-cell retention; cash and full
  action/player-state hashes. It records actual effects, not requested quantities.
- `materialize_s8_field.py`: **test-only** materializer. Consumes the sole source
  owner's pinned donor/composer; preserves all 110 original archive members.
  Native shadow always returns the original native action, even when a helper
  proposes a change. Active modes use only the legal test fixture.
- `run_s8_panel.py`: freezes the complete cell plan before execution, checks
  package hashes before imports, rejects noncomparable or incomplete receipts,
  and computes own/rival/margin changes separately. No replacement for the
  project's broader cohort/gauntlet auditor is claimed.
- `test_s8_field.py`: independent observer, reachable-state, pair-accounting,
  source-drift and complete-interpreter null controls.

## Input identity

GitHub Actions artifact **10175943272**, member
`checked-package/exports/titan-current.tar.gz`, SHA256:
`b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.
Original engine `kaggriculture.py` Git blob:
`3c202c7ee921da239356789e266b694635103fc4`.

Source owner donor `s8_egg_care.py`:
`30a0e05c0cd7a435a59316d9d070da59eb2bb865`.
Composer `compose_reopened_s8.py`:
`7cc261b907e377961e204c47d594cf3cfc85663c`.
Generated helper SHA256:
`86be29534c8cfedef7d0b13043ec86586632b40eac2b16084dd1a9b6ac06d213`.
The helper is generated, not committed as a duplicate controller.

## Reproduce

Use Python 3.13.5 (the executed version), the pinned artifact, and this directory from main.
Set `ARTIFACT` to its unpacked directory and `S8` to this directory. Output paths
must be new; the materializer refuses to overwrite an existing package. No
network, owner computer, cloud deployment, or Actions dispatch is required.

```sh
ARCHIVE="$ARTIFACT/checked-package/exports/titan-current.tar.gz"
mkdir /tmp/s8-reference
# Verify the archive hash above before unpacking a trusted copy.
tar -xzf "$ARCHIVE" -C /tmp/s8-reference
python -B "$S8/test_s8_field.py" --runtime /tmp/s8-reference -v
python -B -O "$S8/test_s8_field.py" --runtime /tmp/s8-reference -v
python -B "$S8/run_s8_panel.py" --archive "$ARCHIVE" --sources "$S8" \
  --output /tmp/s8-field-panel --seeds 1,17,101,2027,6607,104729
```

The panel writes `plan.json`, per-package identities, all detailed `game.json`
and step `rows.json` files, and the final `panel.json`. Raw diagnostic game
receipts alone are about 33 MB; this commit records grouped completed-cell
values and trace identities, not those large raw dumps. Groups are formed only
after exact comparisons, not by assuming feature labels mean equivalent behavior.
Package hashes include each harness's absolute external telemetry path, so a
new output directory changes package/harness hashes; original input pins and
complete deterministic action/player-state traces remain the relevant controls.

## Validation and honest boundaries

**19/19 tests pass normally and 19/19 under -O**, zero errors or skips. Each suite
executes 3,600 official interpreter calls including initialization across five
complete legal-fixture trajectories versus PASS. The optimized claim concerns
this in-process suite; the panel's isolated agent subprocesses are not started
with -O. Tests cover actual overflow, preserved egg admission, full-state observer
identity, source mismatch before import, failed-cell retention, nonfinite cash,
seed/seat/config/engine mismatch, stale helper telemetry, and rival-cash dominance.

Two additional fresh-process controls completed all 719 callbacks: pristine
native seed101/seat0 without observers exactly matches the OFF native harness;
a repeated discard fixture exactly matches its prior action and full player-state
hashes and final cash 13136/10536. These two games are separate from the planned120.

A prior pilot batch was interrupted by the outer execution driver after five
complete games. It emitted no final panel; none of its cells enter the120-game
result. The final plan was restarted and completed in full. Persistent actor
processes are deliberately closed after a game; recorded exit code -9 during
cleanup is not evidence of an in-game crash. Internal native fallback counters
were not instrumented: only actual completion, driver/RPC errors, actions, states,
and elapsed call times are claimed. World hashes cover both player-state objects
at every callback, not `env.info`. No hosted rating, adversarial-gauntlet result,
production activation, or general competitive advantage is claimed.
