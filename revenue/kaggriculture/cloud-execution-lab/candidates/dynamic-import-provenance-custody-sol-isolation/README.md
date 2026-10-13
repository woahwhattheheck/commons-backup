# TITAN dynamic import provenance custody

The `audit_import_provenance.py` wrapper and its `_titan_custody_*` isolated-worker modules close a release-custody gap that static checks cannot see: a candidate can compile and hash cleanly while Python satisfies a plain import from an already-populated `sys.modules` entry belonging to another candidate tree.

The gate launches an isolated, bytecode-disabled Python child; imports the frozen `main.py` by absolute path; resolves the declared callable; optionally reads the frozen `TITAN-CONFIG.json` and runs the canonical `_new_instance` activation seam (while retaining legacy `_load_feature_config` support); and records the module closure Python actually used. Any candidate-local module fails closed when its source:

- is outside the candidate root, including an identically hashed clone;
- crosses or contains a symlink;
- is source-less, cached bytecode, namespaced, zipped, or loaded by a non-source loader;
- is absent from `FILES.json` or differs from its frozen SHA-256;
- disagrees between `__file__`, `__spec__.origin`, callable source, and the declared entrypoint.

The JSON receipt is deterministic: it excludes timestamps, PIDs, hostnames, and absolute paths. It binds the raw and canonical manifest hashes, Python isolation flags, entrypoint/callable, requested local imports, resolved module origins and hashes, activation result type, captured-output digests, violations, and verdict.

## Clean-tree gate

```bash
python audit_import_provenance.py \
  --candidate-root /path/to/extracted-candidate \
  --manifest /path/to/FILES.json \
  --entrypoint main.py \
  --callable agent \
  --activate titan-new-instance \
  --receipt import-provenance.json
```

Exit `0` means every manifest member matched its frozen hash and every dynamically loaded candidate-local source file stayed inside the tree. Exit `1` always emits a complete fail receipt.

## Adversarial stale-cache predecessor

Copy the candidate to another directory and preload its `titan_runtime` before the real entrypoint:

```bash
python audit_import_provenance.py \
  --candidate-root /path/to/real-candidate \
  --manifest /path/to/FILES.json \
  --preload-root titan_runtime=/path/to/identical-foreign-copy \
  --receipt hostile-cache.json
```

This run **must** exit `1` with `MODULE_OUTSIDE_ROOT`. Matching bytes are intentionally insufficient: provenance is part of the executable identity.

## Local validation

```bash
python -m unittest -v test_audit_import_provenance.py
python -m compileall -q audit_import_provenance.py _titan_custody_common.py _titan_custody_worker.py test_audit_import_provenance.py
```

The seven-test suite covers a clean candidate, an identical foreign `sys.modules` predecessor, source mutation after manifest freeze, missing callable, symlink escape, a hung entrypoint killed by the parent timeout, and receipt determinism. The accompanying workflow repeats both the clean and hostile-cache checks against the extracted canonical `exports/titan-current.tar.gz`.

## Scope

This contribution is additive release infrastructure. It does not change gameplay policy, V3 mechanisms, canonical archives, source pointers, provider configuration, evaluator games, or Kaggle submission state.
