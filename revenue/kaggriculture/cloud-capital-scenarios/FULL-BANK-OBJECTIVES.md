# AMBER-CASH full-bank objectives

`read_full_bank_objectives.py` is a read-only consumer of the completed AMBER-CASH exhaustive archive. It does **not** regenerate shop paths, reprice routes, call a simulator or actor, initialize a game, or select a production policy. It verifies the exact archive and all 147 manifested payloads, reads the 128 saved shards, and passes their complete two-route cash matrix through the existing DATE paired-cash ranker.

## Exact inputs

- AMBER-CASH archive: `TITAN-AMBER-cash-scope-20260908.zip`
- Library file: `file_00000000426481f5abbc7dd2b7a6278f`
- Archive SHA256: `82573a9463a9c6d5d725610d39ce032551928e0fd0c0fedfc65d1f098b106ca6`
- DATE ranker: `dated_scenarios.py`, Git blob `76bf7b442c725a57a567efbe4de2b11f1915734e`, SHA256 `69f401934d0ffc71eeb753a73ae2c44c518e438c8e9076c866c4ffc7e381b384`
- Incumbent MAIN route: `7015cc00acfa4922`
- Alternative SHEEP route: `dc76e4003029ac51`

The archive contains 32,768 explicit five-draw shop-identity paths and 65,536 saved route-cash records. These are nominal fixed-quantity own-cash records with no rival orders and no physical-fill claim.

## Preserved decision result

All three objective choices retain MAIN:

| Objective | Result |
|---|---|
| Robust worst paired own cash | SHEEP−MAIN minimum `−16964`; keep MAIN |
| Minimax regret | MAIN worst regret `10851`; SHEEP worst regret `16964`; keep MAIN |
| Assumed independent-uniform expected cash | SHEEP−MAIN `−107769299/32768` = `−3288.858001709`; keep MAIN |

The independent-uniform weights are an explicit analytical assumption over the complete identity-path bank. They are not measured arrival probabilities, a hidden-seed distribution, physical game outcomes, or a calibrated forecast.

Support signs are 7,956 positive, one exact tie, and 24,811 negative. Those are conditional cash signs, not game wins. For paths whose first YARN buyer is visible at decision 360, 3,576 are positive and eight negative. At decision 432, 284 are positive, one ties, and 2,851 are negative. The earlier no-buyer/decision-288 physical outcomes remain a separate RILL experiment and are not copied into this nominal bank.

The original author-reported ingest-and-rank time was 6.49 seconds. The publication readback recorded in `FULL-BANK-OBJECTIVES.json` is a separate reproducibility measurement; neither is agent runtime.

## Reproduce

Materialize the exact AMBER-CASH archive, then run from this directory:

```sh
python -B read_full_bank_objectives.py \
  --archive /path/to/TITAN-AMBER-cash-scope-20260908.zip \
  --ranker ./dated_scenarios.py \
  --output /tmp/full-bank-objectives.json
```

Use a fresh output path. The reader refuses a changed archive hash, missing or duplicate path index, changed route bank, nonfinite cash, mismatched paired gain, incomplete shard bank, or changed preserved result identity. It executes archive members only as data; no source from the input ZIP is imported.

## Scope

This is a publication of an already-completed saved-bank consumer result. No new exhaustive enumeration, pricing, simulation, actor call, engine transition, game, seed, scenario model, selected-policy change, upload, or spending occurred. The full-bank result does not promote the SHEEP route and does not replace AMBER-CASH, DATE, RILL, ADMISSION-TIMING, or AMBER arrival-law ownership.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
