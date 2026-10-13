# V218 current-router intake (LOCKGATE)

This package extends the already-landed V218 movement/shed parity repair with a **whole-file current-input custody gate**. It does not add another V218 implementation, key, controller, runtime entrypoint, archive, or production install.

## Why this exists

The original V218 repair proved the engine mechanics and pinned the relevant source components, but its manifest correctly left three gates open: whole-current-router input, current-ABI composition, and natural full-runtime engagement/economics.

Fresh `main` readback during this intake shows the canonical donor router at
`candidates/v4/donor/overlay/r04_full_router.py` is still Git blob
`a3e2fe87c717d128e43c9b65bae2265f40d1d76d`, and still contains both exact predecessor predicates:

- `_v218_path` rejects otherwise engine-legal transit when `tiles[y][x] == 'LOCKED'`;
- `_v218_plan` removes LOCKED central shed-access corners.

The existing repair tool remains exact Git blob
`88abf4fd6c44f3ff938cede8815aeb58085eaace` and pins that same current router.

## `compose_current_v218.py`

The binder refuses to operate unless the **entire input file** hashes to `a3e2…` and the sibling repair tool hashes to `88ab…`. ON delegates the semantic edit to the existing `v218_movement_parity.py`; it never carries a second transform body. It then independently audits the before/after files and requires:

1. identical line counts;
2. exactly two changed lines;
3. the changed pairs are exactly the LOCKED-transit and LOCKED-shed-corner predicates;
4. predecessor anchors disappear and replacement-anchor cardinalities increase exactly once;
5. every other source line remains byte-identical.

OFF requires the same exact current source and emits whole-file byte identity. Output and optional receipt paths are opened with exclusive creation, so the tool will not overwrite a donor or another candidate.

Example, from this directory:

```sh
python3 compose_current_v218.py \
  ../../../donor/overlay/r04_full_router.py \
  /tmp/r04_full_router.v218-current.py \
  --enable-current-v218 \
  --receipt /tmp/r04_full_router.v218-current.json
```

This command creates a candidate file only. It does **not** activate production or run the legacy `apply_v4.py` materializer.

## Executed validation

Exact authored binder/test bytes were executed locally with Python in normal and optimized mode:

- 11/11 focused tests PASS;
- 11/11 `python -O` tests PASS;
- `py_compile` PASS;
- the test suite authenticates and imports the exact existing sibling repair Git blob `88ab…`;
- fault controls reject source-blob drift, repair-tool drift, extra source edits, wrong semantic edits, accidental enabled no-op, line-count changes, and output overwrite;
- OFF identity and delegated-ON exact-two-line auditing both execute.

Source SHA-256: `160a67732e8928cf36cc2695529a2ed70e9edc1086533ce02bef5440b91474ad`.
Test SHA-256: `677904c672bed5d4a3087e3588ef5bb143086355842cd46854045ac51b6e06ba`.

## Current evidence and remaining gate

Fresh GitHub `main` readback independently verifies the current donor path is still blob `a3e2…`, with both predecessor anchors present, and the sibling repair is still blob `88ab…`. Those are source-custody facts, not a claim that a complete current-router candidate game was executed in this session.

The full `a3e2…` file was available through repository readback but not mounted into the local execution container, so this session did **not** claim a positive whole-file current composition run, natural V218 engagement, full-game economics, gauntlet strength, or production promotion. `CURRENT-INTAKE-VALIDATION.json` records that boundary explicitly.

The next executable gate is therefore narrow and deterministic: run the command above on the exact donor file, then run current `main.py::agent` baseline vs generated candidate in both seats and record actual V218 plan/collection counts plus margin. Do not infer activation from the constructed +1 engine fixtures in the original package.
