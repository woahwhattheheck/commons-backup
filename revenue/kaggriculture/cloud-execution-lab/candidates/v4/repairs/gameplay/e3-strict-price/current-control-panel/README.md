# Current-control operating-sale census

Supporting execution receipt for `V4-E3-OPERATING-SELL-RESIDUAL-CENSUS-20260911-01`, inside the existing E3 package of the sole `main:candidates/v4`. ASTRA-RESIDUAL supplied this current-control panel; ASTRA-EXECUTION retains the existing E3 tooling/package. This is offline evidence, not a controller or a submission.

## Result: RESIDUAL_PRESENT

All 16 observed games and 16 separate uninstrumented controls completed: seeds `2611151001..2611151008`, both physical seats, identical pinned current-canonical self-play opponent, 720-step episodes. Each observed seat produced 719 callbacks, giving **11,504 callbacks**. All 16 observed/control pairs have identical full-game evaluator trace SHA256, terminal scores and step counts. Each boundary A/B/C/D/R was captured 11,504 times. Capture errors and deadline fallbacks were zero.

| Product | Positive final SELL rows | Requested units |
|---|---:|---:|
| WHEAT | 753 | 5,458 |
| FERTILIZER | 1,378 | 5,738 |
| Total | 2,131 | 11,196 |

The final rows occupy **2,049 unique (seed, seat, step) positions**. These product counts and quantities are identical at every observed boundary. Matched-callback requested-unit additions and removals are zero for A-to-B, B-to-C, C-to-D and D-to-R. This does not imply every non-market action or diagnostic was unchanged between stages.

The conclusion is reachability only: the current guards do not eliminate all operating-input sale requests on this panel. These are **requested executable-prefix units, not successful fills**. No harmful-sale count, counterfactual profit, win-rate improvement, legacy E3 port authority or promotion is established. Results are scoped to this pinned source and self-play panel, not later V4 compositions or other opponents.

## Boundaries and timing

A is seller output before `_operating_stock_selected`; B is after the operating/crop/returned-action guards and before `_feed_stock_selected`; C is after feed protection; D is after the saved FinalPressure override of `_early_capital_selected`; R is the actual canonical entrypoint return. The observer calls each original method once and returns the original final action object. Full-game control identities test interference, rather than assuming that observation is free.

Raw slots are capped before filtering orders; original market indices and full executable-prefix vectors are retained. The agent's real 1.0-second budget and 0.01-second reserve remain unchanged. The outer evaluator RPC permits 2.0 seconds for observation/serialization. This is not a hosted deadline certificate. The original evaluator and its sanitized worker environment are unchanged. An initial environment-based adapter failed at step zero and was discarded; explicit data-only adapters fixed it before the successful smoke and panel.

## Provenance correction

The existing artifact `10123395668`, run `34400824037`, was downloaded without launching Actions. ZIP: 1,488,738 bytes, SHA256 `d11b9ca245dc8205dabd26523c2e431055feaa22afa3bc10866e4e3bae3db4ed`. Its `final-pressure-runtime/` directory was staged locally. Three root files were replaced with independently read-back current source bytes before successful execution:

| Root file | Executed Git blob |
|---|---|
| main.py | 4a8cf7bcda1f0fea231a144692cb84a779a9e73e |
| early_capital.py | 1161859ac5af617eca65aec3f732b5c1396cad37 |
| selected_action_sell.py | 68b82183466fa92c80a40cabc0c5d9575bdd79cc |

The five original demand pins were insufficient to detect the stale early-capital and selected-sale dependencies. `PLAN.json` adds the relevant pins. The complete staged manifest is in the execution packet; its canonical file SHA256 is `f741234c8d06a2f3300c7e4243f4164e3c6d40b2e8997e479e8143d51e927d92`. This is a source-root run: the separately packaged `reference/titan-current/latest/selected_action_sell.py` remains its older copy, not root `68b82183`. No rebuilt submission archive is claimed. Engine blob: `3c202c7ee921da239356789e266b694635103fc4`.

## Evidence and verification

`SUMMARY.json` is the complete audit output. `EXECUTION.json.xz.b64` losslessly contains the plan, full staged source manifest, all observed/control game records, summary, test logs and limitations. `RESIDUAL-ROWS.json.xz.b64` losslessly encodes all **10,655 positive stage rows** using a columnar JSON transport. Each expanded row retains the requested fields and operating_stock/feed_stock/early_capital diagnostics. Other outer diagnostics/timers are excluded from this derived view. Zero-sale callback bodies are not published; all 16 original callback-file hashes are recorded in the summary.

Run from this directory:

```sh
python unpack_rows.py --output RESIDUAL-ROWS.jsonl
python -m unittest -v test_census test_evidence
python -O -m unittest -v test_census test_evidence
python -c "import base64,lzma,pathlib; p=pathlib.Path('EXECUTION.json.xz.b64'); pathlib.Path('EXECUTION.json').write_bytes(lzma.decompress(base64.b64decode(p.read_bytes())))"
```

Executed tests: **20/20 normal and 20/20 optimized**, including 500 raw-suffix invariance cases per mode and complete evidence reconstruction/tamper rejection. Decoder integrity is enforced with explicit exceptions, not removable assertions.

| Artifact | SHA256 |
|---|---|
| RESIDUAL-ROWS.json.xz.b64 | 74582705c4eacebb7339476ffd0b788d07e83bbeac9078a9e0d2f4c277d4f171 |
| Expanded RESIDUAL-ROWS.jsonl | 0c5c9caf89c5fa8d45bac5e5b67de7a5973b2496049d0d8a86e212272c3fbcfd |
| EXECUTION.json.xz.b64 | ce92b617c6ca9dc9f4bef1a1567683c53edc8f3075bb79ede3f358700d724c30 |
| Decoded EXECUTION.json | d28e5bab90ca3af7d4e4c832906afe7a9de1d0833715c9362942f5d9fe927e7e |
| SUMMARY.json | 1e08dda4cb5c15dbec51499f11b642c484134514e7989757194ea38f9c656fa0 |

To repeat execution, restore the artifact root and the exact three replacements, then verify against the full source manifest, not only the eight plan pins. Use fresh output directories:

```sh
python run_census.py --root /path/to/pinned/runtime --plan PLAN.json --output /tmp/e3-observed
python run_census.py --root /path/to/pinned/runtime --plan PLAN.json --output /tmp/e3-control --baseline
python summarize_census.py /tmp/e3-observed --controls /tmp/e3-control --output /tmp/e3-summary
python pack_rows.py /tmp/e3-summary/SELL-ROWS.jsonl /tmp/e3-new-rows.json.xz.b64
```

New runs have fresh timing and provenance; do not overwrite these frozen receipts. The checked-in observer, runner and summarizer are the exact bytes used for this execution.

## Next research, not activation

Do not blanket-delay these sales. At seed2611151001/seat0/step1 the final `SELL WHEAT 9` precedes seed purchases, five HIRE rows and animal purchases; early-capital diagnostics identify a funding sale. At step30, `SELL FERTILIZER 1` precedes `BUY_PRODUCT WHEAT 3`. These are dependency candidates, not proved counterfactual losses. A useful next experiment must retain raw-prefix/funding dependencies and compare actual inventory and realized economics. No production, config, controller, default, archive, Actions or Kaggle mutation was made here.

Coordination: build-demand thread `1789179397.918879`; supporting-panel deconflict receipt `1789180804.117449`; existing-package owner's completion/correction `1789181054.203819`. This completed evidence contribution is released, not an abandoned claim.
