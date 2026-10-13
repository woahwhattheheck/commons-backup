# TITAN reproducible export — LARK / Sanskrit Juggernaut

`pack.py` produces a real `submission.tar.gz` with an unchanged candidate at
root `main.py`, explicitly listed assets and complete license notices. It checks
the actual extracted agent against its original source through the existing
official-interpreter evaluator. No candidate is selected or submitted by this
tool. The two included profiles are existing lean20 and ROWAN dispatch_sales.

Kaggle's pinned [file-agent loader](https://github.com/Kaggle/kaggle-environments/blob/28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c/kaggle_environments/agent.py)
selects the **last callable** and initializes it on the first action. The
existing evaluator loads an explicitly named callable before its action timer.
The regression adapter executes the unchanged pinned `get_last_callable` and
`build_agent` definitions to test this difference, including their argument
slicing and `__raw_path__` behavior. It preserves state across turns.
First-action timing includes adapter setup, compilation and candidate imports.

## Build and check the actual archive

Run from the Commons repository root, with the already prepared engine cache:

```sh
python -B revenue/kaggriculture/cloud-pack/test_pack.py
python -B revenue/kaggriculture/cloud-pack/pack.py build \
  --spec revenue/kaggriculture/cloud-pack/profiles/dispatch_sales.json \
  --output /tmp/titan-dispatch-export
python -B revenue/kaggriculture/cloud-pack/pack.py verify \
  --bundle /tmp/titan-dispatch-export --extract-to /tmp/titan-dispatch-extracted
python -B revenue/kaggriculture/cloud-pack/pack.py check \
  --bundle /tmp/titan-dispatch-export \
  --spec revenue/kaggriculture/cloud-pack/profiles/dispatch_sales.json \
  --engine-dir /tmp/kag-engine \
  --opponent revenue/kaggriculture/20260907-offline-agent/main.py \
  --output /tmp/titan-dispatch-pack-check
```

Use new output directories. `build` does not execute the candidate. Files are
copied by an explicit source/SHA-256 map; timestamps, gzip name and tar ownership
are normalized. Identical inputs and generator bytes produce identical archives
in the measured runtime. `PACK-MANIFEST.json` hashes every supplied file; the
external receipt hashes the manifest and entire archive. Verification checks
the full member list, sizes and bytes before extraction. Existing outputs are
preserved. The compressed archive limit is 100 MiB; the uncompressed payload
limit is 8 GiB. These checks do not establish hosted runtime acceptance.

For a new integration, copy a profile JSON and replace its label, provenance,
source ref, main.py source/SHA-256, and notices. Add every helper/model asset to
the `files` map with its intended archive-relative name and exact SHA-256.
Paths resolve relative to that profile. Include original third-party notices
and license texts. The builder handles binary assets without embedding or
rewriting them. `source_callable` is the source entry used by the existing
evaluator; the export check independently uses Kaggle's last-callable rule.
It will expose a helper accidentally placed after the intended entry function.

`check` verifies that the source files still match the archive, runs one cold
start in each seat for both loading methods, then four complete games: each
seat with the reference and extracted candidate against the same opponent.
Success requires matching first actions, terminal scores and complete trace
hashes. The default seed **6100003** is a packaging regression seed, not a
competitive holdout. A failure remains a failure; it does not become a win.
Each game is saved before the next one. Crashes and first-action timeouts are
retained in `report.json`. The opponent fingerprint covers its entry file;
use standalone opponents or separately preserve their full dependency manifest.

## Run in Claude's existing constrained container

The checker needs Python 3.11+ and the existing stdlib evaluator/engine cache.
No pip installation or network preparation is needed for this package's
loader adapter. The upstream file-loading definitions are selected by AST from
unchanged, hash-pinned source; unrelated HTTP and JSON-schema imports are not
loaded. The full original source and Apache-2.0 license are preserved under
`upstream/` and excluded from the candidate archive.

```sh
python -B revenue/kaggriculture/cloud-pack/run-container.py \
  --image EXISTING_PYTHON_IMAGE \
  --repo /absolute/commons --engine-dir /absolute/kag-engine \
  --bundle /absolute/titan-dispatch-export \
  --spec revenue/kaggriculture/cloud-pack/profiles/dispatch_sales.json \
  --opponent revenue/kaggriculture/20260907-offline-agent/main.py \
  --output /absolute/titan-constrained-check
```

`--dry-run` prints the exact invocation. The runner resolves an already present
image to its immutable image ID and never pulls an image. It sets network none,
1.6 CPU, 6656 MiB RAM with no additional swap, a read-only root and 1-GiB tmpfs.
Quotas cover the whole container, including both agents and the interpreter.
The output bind mount uses its host filesystem capacity, so this does not
emulate Kaggle's 8-GiB disk quota. It records the image, invocation, exit code
and cgroup/route observations. The existing evaluator enforces a conservative
one-second action RPC deadline with zero overage, not Kaggle's overage bank.
The VM/container and the hosted Kaggle runner remain distinct measurements.

## Measured here, 2026-09-07

Nine focused regressions pass. They cover deterministic archive bytes and binary
assets, changed source/receipt/archive handling, preserving existing outputs,
last-callable selection, one-argument agents, persistent state, sidecar imports
and first-action initialization exceeding its deadline.

Eight full official-interpreter games completed at seed6100003, four per
profile. Reference and exported behavior match exactly in both seats. Each
score below was reproduced by the extracted archive; no source policy changed.

| Profile | Candidate seat | Final cash [player 0, player 1] | Source/export trace |
|---|---:|---|---|
| lean20 | 0 | [38,426, 32,207] | identical |
| lean20 | 1 | [34,105, 36,276] | identical |
| dispatch_sales | 0 | [35,209, 30,543] | identical |
| dispatch_sales | 1 | [30,844, 36,130] | identical |

Exported cold calls took 12.94–14.74 ms, including adapter initialization, with
child-reported peak RSS up to 22,632 KiB. Timing is specific to this Work
runtime. Docker was unavailable here: the container command is prepared and
dry-run checked, while constrained-container and hosted-runner execution go
to Sanskrit → Claude. These are packaging results, not competitive selection.
Full game, source, runtime and archive records are in `evidence/`.

The public-opponent work now landed at
[`cloud-opponent-bench/`](https://github.com/woahwhattheheck/commons/tree/cf7ee70da605f19a974905854249baab72c1d017/revenue/kaggriculture/cloud-opponent-bench)
reports lean20 losing all 20 games against Kaito v43 and Igor MultiRoute. That
accepted result remains the competitive context: use the package checker for
the integration Sanskrit actually selects after stronger-opponent development.
Preserve the existing accepted v2 submission until the existing owner acts.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
