# TITAN cloud wide-field lab

Bounded league executor over the existing official-interpreter evaluator. It does
not integrate or select a production controller and makes no Kaggle writes.

`run_panel.py` runs resumable arm/seed shards while preserving each evaluator JSON
and complete stdout log. `aggregate.py` requires the exact arm × seed × seat ×
opponent grid, retains errors, computes W/T/L and paired own/rival cash, and emits a
compact loss trace for every loss or failed game. Lonespear greedy and SciPy modes
remain one source lineage even though both runtime modes are measured.

The run-specific `panel-config.json` binds absolute cloud-VM inputs and is retained
with `source-freeze.json`, `capacity.json`, raw reports, logs and the aggregate.
Those absolute paths are execution receipts, not a portable release interface.

## Completed development panel

Seeds 9921001–9921032 produced 640 canonical full games (two arms, five public
entries, both seats). Frozen SELL scored 316W/0T/4L; committed envelope scored
318W/0T/2L. The latter's two row flips are one mirrored Apex case at seed
9921022. Across all 320 paired cells, committed minus SELL is +47.34375 own cash,
-0.246875 rival cash, and +47.590625 margin. This is development evidence, not a
leaderboard or held-set claim.

Three opponent-side lonespear18-SciPy imports crossed the one-second first-action
deadline under four-shard concurrency. Their original reports/logs remain in
`results/panel-original/attempts`; isolated same-seed replications replace only
the failed cells in `results/panel-resolved`, with exact hashes in
`runtime-resolution.json`.

## Apex 9921001 diagnosis

`trace_apex_loss.py` reproduces the evaluator digest while retaining every action,
timing, cash state, production state, private capacity and shared market state.
`analyze_apex_loss.py` shows the first realized production split at step 226 and
the cash crossover at step 406. The bottleneck is not shed overflow: candidate
end-of-day room bottoms at 2 units versus Apex's 1, with all carried inventory
dropped. It is an animal ROI/financing mismatch: the parent buys three geese while
wool already quotes at 189 versus eggs at 51; Apex funds three sheep and later
monetizes increasingly scarce wool. Five capital-bounded substitutions, a no-buy
ablation, and a product-consistency action repair all fail to flip the full game,
so `apex_sheep_overlay.py` is retained as a negative experimental record only.
The next actionable producer-owned experiment is a joint animal-lot, same-turn
budget, and product-route decision—not another SELL or integration overlay.

The complete local result bundle is
`results/full-results-9921001-9921032.tar.gz` (sha256
`2859491973c51d21a95ec80135ac7385ce889c335ff619012f9f86dabce55a11`).

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
