# DELVE: the remaining integrated-versus-frozen SELL cash gap

This is an attribution and targeted-experiment delivery, not a change to a
selected policy. It consumes the complete saved development evidence from
[PR10060](https://github.com/woahwhattheheck/commons/pull/10060), final source
`17e149e75092c905e4ef96ce0dca8806e521ea5e`. The funded integration, certificate,
producer, frozen scheduler and opponent are not edited.

## Result

Across the four previously completed development cells, the repaired funded
integration remains behind frozen SELL in relative cash by 53, 63, 49 and 49
coins. The new interpreter instrumentation exactly reproduces all **5,752 full
post-transition states** in the eight source streams and closes both cash
ledgers with zero residuals. These are executions of recorded actions, not new
agent games or new evidence about the earlier test panel's performance.

For seed **9965019**, both recorded positions mirror. All 719 worker actions
match across funded integration and frozen SELL. Both sell 261 MILK and 262
STRAWBERRY units. The complete cash difference is therefore not extra production
or sale volume:

| Product | Own cash difference | Rival cash difference | Relative difference |
|---|---:|---:|---:|
| MILK | -23 | +21 | -44 |
| STRAWBERRY | -210 | -205 | -5 |
| All other cash causes | 0 | 0 | 0 |
| **Total** | **-233** | **-184** | **-49** |

Funded integration ends at **77,678 / 77,208**; frozen SELL at
**77,911 / 77,392**. The positive seed savings on the other seed do not transfer
into a stronger-than-SELL claim: on 9965001/position0, own +625 is accompanied
by rival +678, giving -53 relative. Position1 differs only by ten fewer coins of
seed savings, giving -63. `FINDINGS.json` retains the exact cause breakdown.

### Two reached decisions distinguish the mechanisms

At decision **360**, the integrated seller emits MILK3 before seed purchases and
hires; frozen SELL leaves that first market slot empty. The current integrated
projection ends immediately at360 because the next continuation needs an
unprovided product-purchase cash bound. Its pre-purchase sell minimum is3. This
is a conservative continuation/funding difference, not just a missing timer.

At **375**, the generic seller chooses MILK13 now and2 at381. At **381**, it builds
a fresh reference with no milk sale; it does not carry the earlier planned2
into that reference. The frozen scheduler retains future sales in its persistent
`planned` map. This is an observable source/action difference, but does not by
itself establish which change improves the complete game.

## Fixed commands and responsive policies answer different questions

First, six offline suffixes were executed from the saved funded state at360:
three treatments in both mirrored positions. They preserve all subsequent own
and rival commands, except the explicitly named edits. Complete altered states,
cash events, terminal stock and source/input hashes are retained.

Then three **new responsive development games**, position0 only, exercised the
same treatments through the original process-isolated evaluator. Each uses a
fresh funded actor and a fresh intact-Arlene rival. Later decisions come from
these policies on the altered observations, not from the saved tape. The exact
source-bound original funded game is the reused control.

| Treatment | Fixed-command margin delta | Responsive own delta | Responsive rival delta | Responsive margin delta |
|---|---:|---:|---:|---:|
| Withhold MILK3 at360 | -186 | +4 | -8 | +12 |
| Request MILK2 at381 | -6 | -2 | -8 | +6 |
| Both | +5 | +2 | -16 | +18 |

The fixed-command first treatment strands3 milk; the combined treatment strands1.
Neither is a valid forecast of how the unchanged live agent later sells stock.
The responsive treatments have **no changed worker actions, productive tiles or
terminal physical inventory** against the original funded control. The rival's
requested actions also remain identical; its receipts change through the shared
market. Own market actions differ on four, three and seven decisions respectively.
Their first post-state differences are at361,382 and361 as expected.

All three responsive games complete 719 decisions without a deadline failure.
Their verdict remains **W**, as does the original control. The combined treatment
ends at **77,680 / 77,192**, margin488: an improvement of18 over funded integration,
but still **31 behind frozen SELL's519**. This is one already-used development
regime, not three independent samples or untouched validation. The interventions
are deliberately timed ablations, not a proposed generic production policy.

**Consumer implication:** a future generic SELL revision needs a coherent,
feasible complete sale continuation and evaluation against a responsive policy.
Simply replaying a diagnostic future tranche, or suppressing a sale without its
continuation, is not justified by these results. T08/ASH retain implementation
and selection ownership; no new persistence wrapper is added here.

## Reproduce

The input is the existing private Library artifact
`TITAN-DELVE-funded-seed-evidence.zip`, SHA-256
`aaa2d811a919b6b1c2219082753cfe476a0a0fac7567d3ad1d72c9f373a912f9`.
Its `MANIFEST.json` SHA-256 is
`809b73067e4b5f3d58d5aa4dd3bccae664e73470ed3b8f0a478728f04a074873`.
It contains all source, official-engine files, unchanged evaluator, complete
observations and source identities. Reuse it rather than export another source
pack. The separate attribution evidence ZIP retains the exact new results,
source versions, full responsive traces and complete fixed-command suffix states.

```sh
BASE=/path/to/extracted/TITAN-DELVE-funded-seed-evidence
D=revenue/kaggriculture/cloud-integration-differentials/delve-evaluation/attribution
python "$BASE/verify.py"
DELVE_ATTR_TEST_PACKAGE="$BASE" python -B -m unittest discover -s "$D" -p 'test_attribution.py' -v
python -B "$D/attribute.py" --package "$BASE" --output /new/path/recorded
python -B "$D/interventions.py" --package "$BASE" --output /new/path/fixed-suffixes
```

The following commands **start new deliberate development games**. They are not
needed to read the shipped receipts and must not be counted as fresh holdouts:

```sh
python -B "$D/responsive.py" --package "$BASE" --arms suppress360 --output /new/path/live-suppress
python -B "$D/responsive.py" --package "$BASE" --arms due381 --output /new/path/live-due
python -B "$D/responsive.py" --package "$BASE" --arms joint --output /new/path/live-joint
```

The live driver verifies every archived input and all original source hashes.
It copies the ablation actor and explicit path/telemetry descriptor into a new
output directory, retains actor failure records, and keeps the original1s action,
10s startup and120s game budgets. Full fresh-process timing and inner policy
time are different measurements. `max_inner_seconds` does not include import,
construction, telemetry serialization or the process protocol.

## Validation and provenance

**20 new regression methods pass.** They cover exact official suffix state/cash,
both positions, independent private state, complete traces, input nonmutation,
edit bounds, exact market slots, hook restoration after failure, full-state
recording and conditional treatment activation. No original policy regression
suite or held panel is represented as rerun.

One first actor attempt failed before gameplay because this evaluator removes
ambient environment variables. The runner now uses its explicit per-run file
configuration. That attempt's result and executed source are retained alongside
the three complete games: **4 actor attempts, 3 complete, 1 instrumentation
failure**. No score was invented for the failure. Earlier exploratory fixed
suffix receipts and source versions are retained, separately from the six
canonical fixed suffixes.

The final serial attribution CLI adds input checks and complete-state recording;
its original execution-source version is preserved with the responsive receipts.
No responsive game was rerun merely for a formatting or artifact change. Timing
and absolute local source paths can vary on reproduction; cash, actions and
source identities are the comparison targets.

Official interpreter pin: `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.
Repository source is Apache-2.0; retain the original component and engine notices
from the input package. No rival-private state is used by the live actor; full
paired private states are used only by the offline evidence replay. No Kaggle
write, new spend, owner-PC work or selected-default change is part of this work.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
