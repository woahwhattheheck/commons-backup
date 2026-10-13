# V3.1 → V4 package-first regression coverage

This lane treats the **exact submitted archives** as execution authority. Raw Git refs, nearby commits, and `SOURCE.json` are provenance only unless their bytes match an authenticated archive member.

Authoritative submissions:

- V3.1 / submission `56172377`: `titan-v3.1-56172377-5db3921f.tar.gz`, SHA256 `5db3921f85efbc7596e5a1e7e198fc5f4644ceea43d8e8323c74ded7b4ba4361`, 148 files.
- V4 / submission `56182437`: `titan-v4-56182437-4d960155.tar.gz`, SHA256 `4d9601552b5e25d02d8a33961c0bed54ed92d032dbcd4a72f6ab8e03515ed21b`, 75 files.

CI downloads the public release assets, verifies the exact whole-archive digest/size, rejects unsafe or non-regular members, recomputes every member digest/size, and checks an immutable canonical inventory-root digest plus the expected cross-version closure. The whole-archive SHA256 is the root authority, so no raw source checkout is trusted as a substitute for submission bytes.

The package delta is much smaller and materially different from the earlier raw-source story:

- 74 common paths; 63 byte-identical; 11 changed common paths.
- 74 V3.1-only paths.
- exactly one V4-only path: `town_procurement.py`.
- the 11 changed common paths are pinned in `COVERAGE.json`.
- Python AST symbol deltas are recomputed from the authenticated tar members, not from raw source refs.

## Active topology

The exact V3.1 package config has `r04_sale_window=true`. Its package `TitanAgent.act()` returns through `_v3_r03_act()` before canonical controller initialization; that delegate imports `r04_full_router.install()`, whose factory returns standalone `v3_agent`. V4 removes that package/config surface and runs the canonical runtime.

That makes **route topology** the causal center. Canonical helper definitions that happen to differ between archived files are not automatically executed V3.1 semantics. They may still be useful as V4 self-ablations, but they do not satisfy V3.1 rollback coverage without separate reachability evidence.

The exact config delta is also authoritative: all 16 common keys have identical values; V3.1 has its V3/R04-only keys; V4 adds exactly `town_procurement=true`. V3.1 already has `crop_release`, `idle_fertilizer`, and `early_capital` enabled, so a four-off V4 factorial is a V4 self-ablation, not an exact V3.1 config restore.

## Verify

```bash
python -B -m py_compile coverage.py test_coverage.py
python -B -m unittest -v test_coverage.py
python -O -B -m unittest -v test_coverage.py
python -B coverage.py \
  --v31-archive /path/to/titan-v3.1-56172377-5db3921f.tar.gz \
  --v4-archive /path/to/titan-v4-56182437-4d960155.tar.gz
python -O -B coverage.py \
  --v31-archive /path/to/titan-v3.1-56172377-5db3921f.tar.gz \
  --v4-archive /path/to/titan-v4-56182437-4d960155.tar.gz
```

This is evidence/control-plane code only. It does not mutate gameplay, defaults, config, CURRENT, archives, release state, or Kaggle state.
