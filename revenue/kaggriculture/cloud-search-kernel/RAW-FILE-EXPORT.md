# T06 file-loader export

This is an additive compatibility route for the frozen experimental T06 v2 runtime. It does not promote the SELL augmenter or alter any of the three runtime files, controllers, opponents or original measured panels.

## Cause and correction

The pinned Kaggle file loader executes Python in a namespace without `__file__`. The module-oriented `entrypoint.py` therefore fails when passed directly to that loader. The previous 48-game evidence used the documented offline evaluator; it did not establish raw-file loader compatibility.

`raw_entrypoint.py` defers asset discovery until its first call. At that point, Kaggle has provided `configuration['__raw_path__']`. The wrapper resolves the exported `cloud-search-kernel/entrypoint.py`, imports it normally with a real module location, and delegates to its unchanged callable. Normal source-module imports remain supported. The nested archive layout preserves the original sibling vendor paths.

`export-profile.json` is a 15-file profile for **LARK's existing `../cloud-pack/pack.py`**, not a new packager. It includes the exact T06 runtime and existing SELL dependencies, licenses and notices. The profile performs byte pinning; it is not a claim that a different current parent revision was tested. Missing assets produce explicit errors. This wrapper supports file-based loading, not arbitrary standalone source text without its assets.

## Executed checks

Eight additional regression tests passed. They cover the original `__file__` failure, actual pinned loader execution of the wrapper, persistent calls, unrelated working directories, normal source imports, missing assets, exact source pins and reproducible archive extraction.

The existing packager check then passed both-seat cold probes and **four complete 719-decision games**: source wrapper versus extracted wrapper, against unchanged Arlene, at regression seed `6100003`. Both seats had identical source/extracted actions, terminal scores and full action-trace hashes. Candidate cash was 83,680 and rival cash 83,168 in each case. This establishes packaging parity on that test, not improvement over another policy or an independent competitive holdout.

A prior invocation hit this tool session's execution timeout after two complete games. That partial report is retained in the companion archive. The receipt's four executions are from the subsequently completed check only; there was no agent failure in that completed check.

The check executed unchanged definitions from `Kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c` through the existing official-loader adapter. It is not the full Kaggle package or hosted resource enforcement. Configured limits were 1 second per action RPC, 10 seconds startup and 120 seconds per game, with zero configured overage. Timing is local evidence, not a worst-case guarantee.

`export-validation.json` records exact source, packager, loader, archive and report hashes. The 61,234-byte archive's SHA-256 is `abda29f695b5b20cd9b384dd8aa3025ab3a7a044dfc200ce23859e3f08599355`. No Kaggle upload or submission was performed. The earlier no-promotion decision remains unchanged.

## Reproduce in the isolated cloud workspace

Keep the existing repository layout. The tested parent and packager sources come from commit `7f92f6c0f4e3961be8109b2e3dc6da3e4e356d9f`, FLOW's existing 88-file artifact `10030763484`, SHA-256 `68f78694fa56976fa1476ffd1d1fb6b3bfd4935392dfd0023a170c7efcd35e62`. This route did not create another source-export workflow.

From this directory, with `ENGINE_DIR` pointing to the existing pinned engine files:

```sh
python -m unittest -v test_raw_entrypoint
OUT="$(mktemp -d)"
python ../cloud-pack/pack.py build --spec export-profile.json --output "$OUT/bundle"
python ../cloud-pack/pack.py check --bundle "$OUT/bundle" \
  --spec export-profile.json --engine-dir "$ENGINE_DIR" \
  --opponent ../cloud-frontier-policy/next-panel/vendor/arlene.py \
  --output "$OUT/check" --seed 6100003
```

Use the extracted `main.py` for file-loader execution, not the inner module file. Preserve all archive members. Existing LARK packaging/official-loader work, FLOW transport, SELL controller, SORREL economics and Arlene retain their ownership and licenses. T06's contribution here is only the wrapper, profile, regression and recorded compatibility result.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
