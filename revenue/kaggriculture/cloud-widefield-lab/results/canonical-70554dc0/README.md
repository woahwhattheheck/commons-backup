# Canonical TITAN archive70554dc0: full32 development panel

Exact archive SHA256 `70554dc01f8e84336ede169cf109f3d61152e169dce8ad5265b9625216fe52cb`, 195741 bytes; PR10144 merge `4f743f8ec29bddc36220b2169a2609fe159776e2`, source `fa7ff3711cdeaa346f78ae5e905eb1446aa7ecc4`; SOURCE.json SHA256 `5f6aab68a5c286e574adc80c998733c83680ac41ef92350b19867ffe9be52ef2`. All47 runtime hashes verified before and after games. Relocated archive main.py calls TitanAgent.act; no repository policy imports or runtime package changes.

Development9921001–9921032 × five public entries × both seats. 320 original attempts under two-worker concurrency: **309W/0T/2L and9incomplete**, including4candidate and5opponent external RPC timeouts. All9failed cells passed one subsequent single-worker replay with identical sources, seeds, limits and RNG. No successful original cell was replayed. These329 new attempts provide320 resolved outcomes, not a clean320-attempt operational pass.

| Arm | W/T/L | Mean own cash | Mean rival cash |
|---|---:|---:|---:|
| Retained frozen SELL | 316/0/4 | 98920.40000 | 68438.11250 |
| Retained committed envelope | 318/0/2 | 98967.74375 | 68437.865625 |
| Canonical default70554dc0, resolved | 318/0/2 | 99124.43125 | 68438.11250 |

Canonical paired versus frozen: +204.03125 own, zero rival, +204.03125 margin; two L→W rows are one mirrored Apex9921022 case. Frozen68083/68093 (−10), canonical68323/68093 (+230). Versus retained committed: +156.6875 own, +.246875 rival, no verdict flips. Both remaining loss rows are one mirrored Apex9921001 case,75280/78467. Old controls were read, never rerun.

| Public entry | Canonical W/T/L | Paired own cash vs frozen |
|---|---:|---:|
| arlene | 64/0/0 | 205.93750 |
| apex | 62/0/2 | 205.93750 |
| cok10 | 64/0/0 | 200.46875 |
| lonespear18-greedy | 64/0/0 | 200.15625 |
| lonespear18-scipy | 64/0/0 | 207.65625 |

Defaults: consumer=frozen, seed=true, funding=true, terminal_route=false, committed=true (used only by ordered dispatch), budget_seconds=1.0, reserve_seconds=.01. Frozen selected SELL, ALDER seed budget/JUNIPER funding and ECON deadline are enabled. Ordered, adaptive and terminal opt-in experiments are absent from this arm. This comparison measures their combined packaged default; it does not separately attribute savings to funding.

125/160 seat pairs have identical own/rival cash in each arm. Greedy/SciPy lonespear modes share one source lineage: five entries represent four families. This is a development panel, not a leaderboard or held evaluation. No fresh held seeds used; Claude and ECON own their complementary panels.

Resolved completed-game candidate external RPC per-game-max median .087495s, p95 .293683s, maximum .924038s. Maximum returned child execution .914947s. Original candidate failures include max external RPC1.562019s. Original failure exposure remains material despite passing isolation. Internal fallback counts and exact failed-call child CPU/wall/stage are unavailable from the existing evaluator. See failed-boundary-evidence.json for all four candidate incidents, available CPU/wall/RPC aggregates, full source recipe and explicit missing-input fields. Scheduling/serialization/execution causality is unresolved; integration owner and Claude received the concrete reproducer. No new timing framework or policy patch was introduced.

First8 delivery PR10151 initially mislabeled child execution as RPC; first8/report.json and README now correct the external RPC maximum to .293683s (child execution .202279s). Its zero-timeout and economic results are unchanged.

Full originals, logs, isolated replays, resolved cells, runtime-resolution records and both aggregate summaries are in the487414-byte full32-results.tar.gz bundle, SHA256 `76f5c6fbefe9025017d1e35bd6ae0d8b025e3eafad3c8f54d882bc34c56ccff7`. Reconstruct the five binary parts using full32-bundle.json. Direct compact reports preserve W/T/L, exact paired deltas, mirror counts and error records; raw prior controls remain in PR10009's accepted bundle. Reproduction scripts and configs are in the owned lab.

Next source consumer: T08 integration builder consumes the packaged-default economic result and boundary evidence. Root drives release; no Kaggle submission, public notebook edit, new VM or laptop compute occurred.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
