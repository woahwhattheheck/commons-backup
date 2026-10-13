# Selected SELL joint receipt consumer

A Python 3.10+ standard-library CLI and callable for consuming an **existing** `titan-selected-projection` validation artifact. It reads the ZIP without extracting or executing its contents, checks reported suite results against the one source snapshot, and returns structured JSON. It does not download files, rerun tests, dispatch jobs, invoke an agent, or change policy selection.

ATLAS owns the projection implementation and existing hosted workflow; WREN owns the market consumer and seller repairs; INTEGRATION supplied the loader handoff. This directory adds the offline downstream reader only. Their original source and results remain unchanged.

## Use the completed combined checkpoint

Obtain existing GitHub Actions artifact **10033795374** from run **34164813999**, attempt **1**, using the normal artifact download road. Do not create a new source export or rerun that workflow to inspect its result.

```sh
python3 revenue/kaggriculture/cloud-selected-joint-checks/check_joint_receipt.py \
  /path/to/titan-combined-existing-51.zip \
  --expected-sha256 d1984cf6b25abbb1c0dfbc5be61e238f970995d69b98ec45fe6a0b1de4a9d3b7 \
  --expected-checkout e5d4e8541895a17ee165663c0ede88af9e743746 \
  --expected-run-id 34164813999 --expected-attempt 1 \
  --json-output /tmp/joint-receipt.json
```

Actual output: `COMPLETE_PASS`, 51 reported methods (16 original, 21 projection, 14 market), with zero problems. The archive retains 144 projection cases / 378 interpreter transitions and 28 market executions. These are the original hosted results, not new executions by this reader.

The seller in that checkpoint is SHA-256 `a3ca92cb7fabfb65bb660931fb6fa2623067809ac01ef44b55edd6ca3f5b422a`. It combines ordered-transfer and terminal-stock repairs. This checkpoint **does not cover later empty-lot repairs, future source revisions, gameplay strength, or whole-repository CI**. The consumer does not transfer an old receipt to a changed seller.

The earlier artifact **10033736596**, run **34164624483**, remains valid for its original 37 methods. Reading it yields `INCOMPLETE` for the three-suite contract, identifying the absent market source row, log and JSON. Its original 37 passing results are retained rather than relabeled as failures or combined evidence.

## Interface and statuses

```python
from pathlib import Path
from check_joint_receipt import inspect_archive

receipt = inspect_archive(
    Path("validation.zip"),
    expected_sha256="<provider artifact digest>",
    expected_checkout="<tested checkout>",
    expected_run_id="<run id>",
    expected_attempt="<attempt>",
)
```

Exit 0 means `COMPLETE_PASS` for the named three-suite receipt contract; 1 means `FAIL` due to inconsistent/failed evidence; 2 means `INCOMPLETE`; 3 means an I/O or invocation error. Without the expected provider digest the archive can still be inspected, but is reported incomplete rather than provider-verified. Optional expected checkout/run/attempt values are checked when supplied. Supplying a digest is a data-integrity check, not an independent execution attestation.

Default members are `SOURCE-SNAPSHOT.json`, `original-seller-tests.log`, `projection-tests.log`, `projection-results.json`, `market-tests.log`, and `market-results.json`. A single directory prefix is supported. Use `--market-log` and `--market-report` for alternate market filenames. Unknown additional files are not interpreted as additional suite coverage. Duplicate/ambiguous member basenames or JSON keys, incomplete unittest completion, skipped cases, source/engine drift, differing method counts and failed suite summaries cannot produce `COMPLETE_PASS`.

The declared pre-execution snapshot is the source binding for the original unittest log; projection and market JSON also report their own implementation/engine hashes. This reader checks alignment of those declarations in one digest-matched artifact. It does not independently attest which instructions executed. Archive contents are never executed; no archive paths are extracted. ZIP members are limited to 8 MiB each and 32 MiB total uncompressed.

## Reader validation

```sh
cd revenue/kaggriculture/cloud-selected-joint-checks
python3 -m unittest test_joint_receipt -v
```

Twenty self-contained reader regressions pass. Their generated ZIP fixtures are explicitly synthetic receipt-parser tests, not game results. The real 37-method and 51-method artifacts were separately processed by the published reader; exact source pins and outcomes are in `VALIDATION.json`.

Source contracts and existing execution: [projection PR9951](https://github.com/woahwhattheheck/commons/pull/9951), [terminal-stock PR9949](https://github.com/woahwhattheheck/commons/pull/9949), and [combined workflow PR9954](https://github.com/woahwhattheheck/commons/pull/9954). New files are Apache-2.0, as indicated by their SPDX headers.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
