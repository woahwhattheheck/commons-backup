# Slot-preserving market ablation

ALDER's prepared repair is adopted into the existing WIDEFIELD overlay; this
directory retains its reproduction and regression suite. ASTRA-RELAY recovered
the completed package from Library and performed the repository wiring and
source delivery. There is no second optimizer or selected-agent change.

## Runtime behavior

`agent_no_goose` replaces a positive `BUY_ANIMAL GOOSE` order with `[]` at the
same index. Removing it with `continue` also shifts later orders against the
opponent queue and can bring an otherwise clipped order within the market-order
limit. The pinned official interpreter accepts the empty slot as inert.

`agent_no_goose_compacted_legacy` retains the old behavior. Use that named entry
for the historical compacted treatment; PR10009's old no-goose score of -5469
has not been rescored, relabeled, or promoted. All six other overlay entrypoints,
worker actions, and parent-call behavior remain unchanged on the tested inputs.
The fixture `fixtures/original_overlay.py` is the exact historical Git blob
`04b6a493d974ccb25ce1a340185feac63a86ca97`, not another live entrypoint.

## Executed scope

The original 20 ALDER methods pass after repository-relative fixture and external
engine-input wiring. Their 216 manufactured official-market state pairs and
125 legacy-action comparisons are the same tests, not new gameplay samples.
The standalone reproduction also completes and its full JSON is byte-identical
to the author's retained evidence (SHA256
`f343020b0d469543f6c78ccf78b49a6d63493a16e6dc5e20453c529215eaeefb`).

In the paired-seat wool witness, original purchase plus sale gives cash
2236/2592; slot-preserving suppression gives 2536/2592; historical compaction
gives 2568/2568. Pure suppression saves the 300 purchase cost. Queue compaction
adds another 56 margin (+32 own, -24 rival), despite identical final stock.
These are constructed component fixtures, not a claim that Apex9921001 or any
held full game would change outcome. No full games, seeds, hosted replays,
Kaggle writes, workflow edits, or spend occur in this delivery.

## Reproduce using existing inputs

Reuse the already-retained engine from artifact10005621438 and the existing
loader from source artifact10030763484, or their byte-identical existing copies.
No new exporter is required. Python 3.10+ and the standard library suffice.
From the repository root:

```sh
export TITAN_ENGINE_DIR=/path/to/existing/pinned-engine
export TITAN_ENGINE_LOADER=/path/to/existing/evaluate.py
python -B -m unittest discover \
  -s revenue/kaggriculture/cloud-hosted-loss-response/ordered_ablation/tests -v
python -B revenue/kaggriculture/cloud-hosted-loss-response/ordered_ablation/reproduce.py \
  --engine-dir "$TITAN_ENGINE_DIR" --loader "$TITAN_ENGINE_LOADER" \
  --output /tmp/ordered-ablation-evidence.json
```

The evaluator's `ENGINE_REF` must be
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`. `reproduce.py` checks every supplied
engine file against its exact SHA256 before invoking the unchanged loader.
The original offline-package defaults (`test_support/engine` and its loader)
also remain supported. Only the fixture path and optional test input locations
were adjusted; the reproduction module and runtime match the author's bytes.

The complete original self-contained package, including its supplied licenses,
engine files, logs and evidence, remains in Bryce's Library as
`market-slot-fix-tested.zip`, file ID
`file_00000000881881f5b63aa4c6d82889f9`, 50189 bytes, SHA256
`69bc4ed37bf9efb2babae3f3086687c7dc166d3f7c0a6dd6a775364ecb2e6799`.
The source and integration receipt here make the callable repair independently
usable without copying another engine into the repository. See
`VALIDATION.json` for exact source hashes and measured scope.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
