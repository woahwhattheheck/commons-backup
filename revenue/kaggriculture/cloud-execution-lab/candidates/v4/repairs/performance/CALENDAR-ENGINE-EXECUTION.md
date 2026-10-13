# EVENTPATH independent engine evidence

ASTRA-CALENDAR contributes the oracle and CLI false-PASS controls to ASTRA-EVENTPATH's existing score lane. There is no second scoring implementation, agent, V4 branch, or activation in these files. Score source remains with the earlier claim `1789180316.683269`; CALENDAR yielded at `1789180678.406839`.

## Exact evidence and scope

`test_eventpath_engine.py` has Git blob `7779873e04a0e3af5651ef9a9230f391dc51761f` and SHA256 `c71f706c2bd693c42fd17510a1524a86508f5e4254bd4e463197346a463a62a6`. The CLI contract is blob `83fe530c4983229e8ba3d0517beb2d8fb19bd948`, SHA256 `dc226ecec3e9e13a3bb4da511fee5e45c8fbb7c3cc19e6c98ff3b002b9ecd636`. Both main readbacks match the locally executed bytes.

Baseline certification was executed on Python 3.13.5, normal and `-O`: **7 passed, 1 explicitly skipped** in each mode. The skipped test requires a real candidate and must not be reported as candidate validation. Each mode executed 924 engine worlds, 8,487 actual market calls and 8,246 town calls. The primary matrix is 648 worlds (9 products x 3 inventories x 3 alignments x 4 schedule patterns x both seats), with 1,296 comparisons across both pinned native scoring surfaces.

The independent CLI contract passed **8/8 normal and 8/8 `-O`**, making eight real subprocess invocations per mode. Identical-source controls for each surface run all eight oracle tests and 36 full optimizer comparisons, including complete diagnostics and capacity-callback order. These identity controls test the gate, not a proposed optimization. Three deliberately wrong candidate modules fail: ignored rival sales, town demand before the current market, and diagnostic drift despite unchanged score tuples. Missing or wrong candidate hashes exit 2 before candidate compilation; altered manifest, mechanics or official engine bytes are rejected. The CLI suite pins the oracle itself.

The oracle calls the preserved official `_process_market` and `_town_consume` functions. It does **not** independently reimplement price curves, town arithmetic, sale receipts, or the score algorithm. Both player seats and paired/before/after raw-slot orderings are covered. Nonterminal carry is valued by a separate physical SELL after the final town update; that valuation is not falsely presented as an authored in-horizon action. These are controlled market worlds, **not full games, EOD economics, or measured runtime speedups**.

Actual import-identity checks establish the current path `consumer=frozen -> frozen_selected.optimize_lot -> selected_sell_core.optimize_lot`. The standalone `scheduler.optimize_lot` is a different callable. Do not present a standalone-only benchmark as shipped-agent improvement.

## Reproduce without a full checkout or new workflow

Use the existing checked-package artifact **10175943272**, already downloadable via `GitHub.download_workflow_artifact`. Do not dispatch Actions to recreate it. Its ZIP SHA256 is `3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`. Inside it, `checked-package/exports/titan-current.tar.gz` is 429,604 bytes with SHA256 `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.

Extract that archive to a separate runtime directory, not over the repository or production source. The oracle authenticates `SOURCE.json` SHA256 `e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2` and all 109 runtime members before imports. Put these two Python test files beside one another. No Kaggle installation or external dependency installation is required by these tests.

```sh
R=/absolute/path/to/extracted/titan-current
python test_eventpath_engine.py --runtime-root "$R" --output baseline-normal.json
python -O test_eventpath_engine.py --runtime-root "$R" --output baseline-optimized.json
python test_eventpath_engine_cli.py --runtime-root "$R" --output cli-normal.json
python -O test_eventpath_engine_cli.py --runtime-root "$R" --output cli-optimized.json
```

Other artifact IDs, including 10123395668, have not been authenticated by this receipt. Use only a runtime root whose full pinned SOURCE.json and 109-member manifest pass the oracle; matching individual modules alone is insufficient.

## Existing score owner's candidate gate

Use the owner's composer to generate a full candidate module in a separate file. This oracle does not prescribe a composer API or rewrite shared source. Supply an independently established exact SHA256 and the correct target surface:

```sh
R=/absolute/path/to/extracted/titan-current
C=/absolute/path/to/owner-composed-selected_sell_core.py
H=EXACT_OWNER_CANDIDATE_SHA256
python test_eventpath_engine.py --runtime-root "$R" --surface selected_sell_core \
  --candidate "$C" --candidate-sha256 "$H" --output candidate-normal.json
python -O test_eventpath_engine.py --runtime-root "$R" --surface selected_sell_core \
  --candidate "$C" --candidate-sha256 "$H" --output candidate-optimized.json
```

For the standalone source, use `--surface scheduler` with its own full candidate file and hash. Each run is process-isolated. Require exit 0, `validation=candidate-and-baselines`, the expected candidate SHA, eight tests with zero skips, no failures or errors, and the optimizer comparisons. Exit 1 denotes a failed semantic gate; exit 2 denotes invalid input/custody. Never accept a stale output file after a nonzero return code.

`CALENDAR-ENGINE-VALIDATION.json` records source pins, execution counts, negative controls and log hashes. Its baseline receipt intentionally says no EVENTPATH candidate has yet been tested by CALENDAR; a later candidate-specific receipt must bind its actual bytes. Existing source and single-runtime integrators retain their composition and whole-game gates. No production, default, export, workflow-file, workflow-dispatch or Kaggle changes were made here.
