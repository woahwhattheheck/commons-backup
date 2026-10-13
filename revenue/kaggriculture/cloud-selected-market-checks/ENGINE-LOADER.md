# Explicit offline engine-loader binding

`check_market_contracts.py` accepts an optional `--engine-loader PATH`. The path is forwarded to the existing evaluator's `get_engine(..., loader=PATH, prepare=False)`. Omitting it preserves the evaluator's original default. The checker does not remap paths, download missing sources, replace the evaluator, or change the selected policy.

This supports the bundled `cloud-execution-lab/reference/evaluator/evaluate.py` with its adjacent `loader.py`. The evaluator's historical default instead points to `../20260907-offline-agent/evaluate.py`, which is not present in that sparse layout.

## Use an existing bundled checkout

```sh
LAB=revenue/kaggriculture/cloud-execution-lab
python3 revenue/kaggriculture/cloud-selected-market-checks/check_market_contracts.py \
  --lab "$LAB" \
  --evaluator "$LAB/reference/evaluator/evaluate.py" \
  --engine-loader "$LAB/reference/evaluator/loader.py" \
  --engine-cache "$LAB/reference/engine" \
  --json-output /tmp/market-results.json

python3 revenue/kaggriculture/cloud-selected-market-checks/test_engine_binding.py \
  --json-output /tmp/loader-results.json
```

The second command defaults to the same bundled evaluator, loader and engine directory. Its three path options also accept an existing source pack. No new export or game panel is required. Sparse consumers must include this directory plus the evaluator, loader, engine and original seller dependencies.

## Executed validation: September 7, 2026

The exact published checker and new test source passed **7 methods, 0 failures, 0 errors** in the cloud. Tests execute the real evaluator and pinned official engine, including **4 actual market calls** (both seats under the legacy and explicit relocated bindings). Additional cases cover a missing default loader, a missing explicitly requested loader, unchanged engine-blob mismatch detection, CLI help and argument forwarding. The CLI-forwarding negative case intentionally reaches an absent seller only after the actual engine loads; it is not a complete seller-suite execution.

The original checker was also exercised against the sparse evaluator layout and raised `FileNotFoundError` at `reference/20260907-offline-agent/evaluate.py`. Supplying the explicit adjacent loader now succeeds. All 14 original market-test method syntax trees remain unchanged. Python compilation passed. No policy panels or seeds were used.

Exact local input identities:

| Input | Git blob | SHA-256 |
| --- | --- | --- |
| Published checker | `ae9d7474c30eb9059b034f24974ad202f646bcca` | `06ba8b22c3526038e2e027001fc44c9accaaaefcb992258e002ec11595851ac9` |
| New binding tests | `95f6507341581dc284988d9b7bb4d46a6a9fa73a` | `c88ac9f905f085013be1ccab36bb02f6a832c928edfed5d0742659dc349fb663` |
| Reused source-pack evaluator | `6bcde5b7dc1abc33eb3cd7ec42833affc2d28b53` | `bb5553a746989f3e854d4639c9d50839b1633b77faffcf49d3e9a748603711e6` |
| Reused offline loader | `23948e10cfc3d32f46c9abb1321b0d8fc8db21d5` | `cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e` |

The local evaluator came from existing artifact `10030763484`, source `7f92f6c0f4e3961be8109b2e3dc6da3e4e356d9f`; it is not byte-identical to the newer bundled evaluator `1fb6b655bb4ca1e1684be165a8ef513e2e6c2325`. Their inspected `get_engine` implementations have the same loader argument and default-path behavior. The loader body is identical to the bundled loader. Existing artifact `10005621438` supplied the three official engine files, each verified before loading against engine commit `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`:

- `kaggriculture.py`: `3c202c7ee921da239356789e266b694635103fc4`
- `kaggriculture.json`: `b354d06b742fe48402513792253f1a5c29366b20`
- `utils.py`: `91c8822ee6201ba4a5a8416c7dbe34f95dd61c87`

These binding results are separate from the previously completed [51-method combined seller run](https://github.com/woahwhattheheck/commons/actions/runs/34164813999), which tested its own pinned checkout before this loader option. That accepted result and its original/projection/market outputs are retained in the [projection validation receipt](../cloud-selected-projection/HOSTED-VALIDATION.json). Neither result establishes gameplay improvement, hosted rating, or whole-repository CI success.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
