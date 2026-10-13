# TITAN V3 internal SOURCE manifest closure

This additive repair/evidence carrier is bound to Slack one-tree packet
`F0C0JPCAAQP` (27,500 bytes; SHA-256
`f68792bf7f0fb269864ef4ab25967292e2d4cd03439dbc5c52b98dfcebd1b728`)
and its exact `build_v3.py` SHA-256
`cfcb383e6cba811e17d687cb080fea1f55723c8aa734edbe9c37ec3743f923d0`.
The packet is separately held as a stale repin; this directory does not publish,
rebase, enable, or promote it.

## Defect

The predecessor extracts the canonical root `SOURCE.json`, copies overlay files,
rewrites canonical runtime/config/release files, and returns the result without
reading or regenerating `SOURCE.json`. Thus the built archive's own `runtime`
map still names predecessor hashes and omits new members. The external
`FILES.json` is useful but does not repair the embedded manifest consumed by
archive carriers and source-closure checks.

`prove_predecessor.py` executes that behavior with the exact packet builder in a
synthetic two-file canonical archive. The old builder changes `main.py` and adds
`lane.py` while preserving stale SOURCE bytes. The bounded successor updates the
manifest after every package mutation and verifies exact closure before tar
serialization.

## Repair contract

`source_manifest_closure.py`:

- excludes root `SOURCE.json` to avoid a self-hash cycle;
- requires canonical relative POSIX member names and bytes;
- preserves every non-runtime manifest field and surviving `source_path` label;
- records every final non-manifest member exactly once by byte length and SHA-256;
- deterministically labels new members by package path unless explicitly mapped;
- rejects duplicate JSON keys, malformed entries, self-inclusion, missing/extra
  members, hash/length drift, and unsafe names;
- is idempotent.

`patch_packet.py` accepts only the exact predecessor builder and reviewed helper bytes, inserts one
refresh+verify boundary after all edits, and adds `build_v3.py` plus the helper
to the V3 source-receipt map. Publication owners must rebuild `FILES.json` and
`V3-MANIFEST.json` from their reconciled current-base packet; old archive hashes
must not be relabeled.

## Local verification

```text
python -m py_compile source_manifest_closure.py patch_packet.py prove_predecessor.py test_source_manifest_closure.py
python -m unittest -v test_source_manifest_closure.py  # 8/8 PASS
python prove_predecessor.py --check PREDECESSOR.json
```

No canonical runtime/config/archive/pointer, feature default or semantics,
gameplay, provider, Kaggle, or submission state is changed here.
