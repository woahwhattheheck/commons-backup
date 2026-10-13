# KAG-FRONTIER-POLICY

Selected Kaito-derived policy:16/16 development wins and16/16 reserved validation wins against Kaito v43 and Igor MultiRoute, both seats. Mean validation margins: +7,528.5 vs Kaito and +12,216.875 vs Igor. Full per-game cash, actions and runtime are in RESULTS.md and results/. This is a candidate for root's single submission sequence, not a measured current leaderboard rating.

Use **export/submission.tar.gz** (57,711 bytes) or the independently runnable **main.py** (73,418 bytes). The archive includes main.py, Apache LICENSE, attribution NOTICE.txt and PACK-MANIFEST.json. main.py is the frozen73,212-byte candidate.py plus one packaging-only final entrypoint. The separate candidate.py is the evaluator's named-agent source; use main.py for the official last-callable file loader.

| Artifact | SHA-256 |
|---|---|
| Frozen candidate.py | b3a6085e1e6674f0228fca4b31fe90950875c1ef93c8c8d926dbc586298c0b56 |
| Native main.py | 16d7f213e06c563487e5f613f8c94116a094b36ba46927329cbfc3b4195d461d |
| submission.tar.gz | 79b407d699b5fd39e7b396de8b6fc79b2bc2fb99f427f7e2e7ecd25fbc71fb0b |

The implementation calls Kaito's actual agent once. Parent worker actions, route selection, weed repair and persistent state remain intact. When the opponent's publicly visible farm signature has distance<=2 under Kaito's existing helper, the overlay advances sales of observed finished goods. It preserves every existing market slot for hires, land, feed and seed purchases. Otherwise it returns the parent action. It reads no environment seed, opponent private inventory or future episode state.

## Rebuild and reproduce

```sh
python revenue/kaggriculture/cloud-frontier-policy/build_selected.py
python revenue/kaggriculture/cloud-frontier-policy/test_sales.py
python revenue/kaggriculture/cloud-pack/pack.py build --spec revenue/kaggriculture/cloud-frontier-policy/export-profile.json --output /tmp/frontier-export
```

Existing engine/evaluator reproduction (the recorded games need not be repeated for orientation):

```sh
python revenue/kaggriculture/cloud-frontier-policy/measure.py --engine-dir /path/to/existing/engine --seeds 9400203,9400217,9400231,9400249 --output /tmp/frontier-validation.json
python revenue/kaggriculture/cloud-pack/pack.py check --bundle /tmp/frontier-export --spec revenue/kaggriculture/cloud-frontier-policy/export-profile.json --engine-dir /path/to/existing/engine --opponent revenue/kaggriculture/cloud-frontier-policy/vendor/kaito_v43.py --output /tmp/frontier-native --seed 9400109
```

The accepted exporter and pinned official file loader passed cold calls and four complete source/export games for this new candidate, matching scores and action-trace hashes in both seats. Cold lazy-loader/source calls:138–284 ms; process start through first response:230–565 ms. Native complete games include cold initialization and stay below143 ms maximum decision call. These are cloud Python measurements, not hosted sandbox certification.

measure.py invokes the existing process-isolated cloud-eval.play and official interpreter. Passive hooks record actual unit actions, unchanged non-PASS effects, successful market transaction units/proceeds, terminal farms/private inventories and resources. Wall time includes diagnostics; child decision timings are separate. No new simulator, repeated parent downloads, owner-PC or paid compute was used.

## Evidence and continuation

selection.json freezes the policy hash before reserved seeds. results/selected-summary.json combines the selection and runtime receipts. results/validation-games.csv is the compact per-game table. results/native-first-failed.json retains the first packaging failure; that archive is not delivered. The uniquely named final entrypoint fixes selection without retuning policy. All failed development variants and actual-parent/route-only/sales-only controls are retained; build.py/overlay.py are historical rejected experiments, not the selected build.

Development seeds9400109/9400123/9400137/9400151; reserved validation seeds9400203/9400217/9400231/9400249. Reserved outcomes were not used to retune this source. For any future change, treat these as consumed evidence and reserve new seeds. Root owns Claude/account/submission; ROWAN owns transport/readback. PUBLIC_CODE_SHARING.md provides the official-rule link, scoped findings and a ready-to-post public announcement. No duplicate submission or forum announcement was performed here.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
