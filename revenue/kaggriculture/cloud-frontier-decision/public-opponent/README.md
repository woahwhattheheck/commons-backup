# Breaking the Tie v12: exact public opponent fixture

Unchanged Apache-2.0 agent by Andrey Naymushin (andrewsokolovsky), acquired from the [version 12 notebook](https://www.kaggle.com/code/andrewsokolovsky/kaggriculture-breaking-the-tie/notebook?scriptVersionId=341994976). The versioned page displayed 2883.0 and version 12 of 43; this is historical page evidence, not a current rating claim. This fixture does not substitute a later version.

`submission.py` is exactly 26,585 bytes, SHA256 `df4e899ad535754cf2ddbd3c16e48085916b0cd2baa5182a1a2cfc6a856abae5`, matching the notebook's build output. The original downloaded notebook, license, and attribution are retained. Extraction removed only the first cell's `%%writefile submission.py` directive. The notebook was not executed. The encoded constant was decoded statically into 720 JSON action dictionaries; the surrounding controller was read in full. Dependencies are Python standard library `base64`, `copy`, `json`, and `zlib`. No external dataset, model, network access, or hidden opponent state/seed is required by this source. The author describes its embedded baseline as C165; independent ancestry has not been established.

## Observed mechanism

* A public farm signature compares tile counts, hand count, unlocked quadrants, and positions with its own historical trace. Scheduled observations increase or decrease bounded mirror confidence.
* With confidence at least one, the four-turn front-run scans upcoming trace sales for MELON, STRAWBERRY, MILK, or WOOL and appends one sale bounded by observed shed stock and existing requests.
* With confidence at least three, consecutive public market observations infer rival supply after estimated own sales and known town consumption. One matching event can latch the four-turn-counter detector. The latch has no expiry until an episode reset.
* Once latched, the five-turn counter considers one premium product with a trace sale five turns ahead, excluding a product consumed by town on the current turn, and prepends its sale.
* Terminal liquidation supplements the trace after step 680. Despite its final-eight-turn docstring, the custom terminal action branch actually starts at step 717.

These are source behaviors, not demonstrated causes of the benchmark result. Own-supply inference uses pre-action shed stock and does not reconstruct ordered DROP/PICKUP/PLACE effects. Town intervals are default constants. Falling mirror confidence does not clear the counter latch. The original source is intentionally preserved with these limitations. Prepending a sale is not priority over the other seat: the official market quotes both seats from the same pre-commit inventory in each unit round. Floor-price sales pay cash but add market supply only when their quote exceeds one.

## Completed cloud benchmark

Existing `cloud-eval/evaluate.py` and the official engine at `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`; 719 action rounds, two fresh seeds (9600107, 9600121), both seats, no game failures. LARK confirmed these seeds did not overlap its panel. Candidate below means unchanged Breaking the Tie v12. Margin means candidate terminal cash minus opponent terminal cash.

| Opponent | Candidate W/T/L | Mean margin |
| --- | ---: | ---: |
| Arlene `1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4` | 0/0/4 | -16,111.25 |
| Apex, exact vendor source/native build pinned in results | 0/0/4 | -12,392.00 |
| Deployed archive `79b407d699b5fd39e7b396de8b6fc79b2bc2fb99f427f7e2e7ecd25fbc71fb0b` | 3/0/1 | -38.00 |

The two seeds are a bounded comparison, not a ranking estimate or evidence that the counter alone improves performance. Against deployed TITAN the first seed produces +45 in both seats; the second produces -6512 and +6270. The fixture remains useful for exposing timing interactions, but these results do not justify promoting it over Arlene or Apex. No controller ablation was run and no internal detector-activation count is claimed.

`results-summary.json` contains every game's cash, seat, status, timing, trace digest, and all recorded source/build pins. `results.json.gz` preserves the full evaluator result, including passive market commit diagnostics, daily observations/actions, terminal state, and unchanged-action events. Runtime measurements belong to this cloud run; the existing actor cumulative CPU accounting is retained verbatim and should not be interpreted as isolated per-call latency. Candidate per-call timing is separately recorded.

## Reproduction

From a checkout containing this directory and the existing parent fixtures:

```sh
python -B revenue/kaggriculture/cloud-frontier-decision/public-opponent/prepare.py --runtime /tmp/breaking-tie-runtime
python -B revenue/kaggriculture/cloud-frontier-decision/public-opponent/benchmark.py --engine-dir /path/to/pinned/engine --runtime /tmp/breaking-tie-runtime --candidate /tmp/breaking-tie-runtime/breaking-tie-adapter.py --seeds 9600107,9600121 --output /tmp/breaking-tie-results.json
```

The preparation wrapper packages the existing next-panel preparation and existing pack adapter calls. Those constituent operations were executed in this run; the wrapper itself was not separately rerun. Adapters use the existing isolated loader and offline restriction. `benchmark.py` derives from LARK's existing Apache-2.0 next-panel measurement harness, adding the frozen opponent and exact fixture metadata. It does not implement alternate game transitions. Source inspection, download, compilation, and all games occurred in the cloud. No Kaggle upload or new paid compute was performed. FLORA's production integration and the separate forecast economics lane are unchanged.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
