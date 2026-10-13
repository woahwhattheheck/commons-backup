# FASTTAPE × REBIND commutation receipt

**Status:** exact source/preimage rebase proved; default-OFF; not promoted.

The canonical composition graph still names the historical fast-tape runtime
edge `b952c9c2… -> 2b2bd80e…`, but REBIND #12788 changed the live canonical
`cloud-execution-lab/titan_runtime.py` to
`6d9720f4aa1e6b46e92ee5183897074d8e9ea5a0`.

This packet proves the existing fast-tape transform remains valid on that
repaired runtime without silently discarding the loader fix.

## Exact diamond

Using the authenticated b567 foundation artifact `10175943272`
(SHA-256 `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`):

- baseline runtime: `b952c9c228ecbde592bf3d2df01638677abb0d24`
- REBIND only: `6d9720f4aa1e6b46e92ee5183897074d8e9ea5a0`
- historical fast-tape only: `2b2bd80e3fa76c61139bdbfeaa58dc8a8987339a`
- REBIND then fast-tape: `6472260d9aa82f1d6e4008afb24a2645bfb1226c`
- fast-tape then REBIND: `6472260d9aa82f1d6e4008afb24a2645bfb1226c`

The two combined outputs are byte-identical, compile, are 34,354 bytes, and
have SHA-256
`1c409b5fdf7942f31b37580987b10074aa231984edbe67e0080edfc31b65b0c5`.
The REBIND-only postimage is byte-identical to live main, so the proof is not
using a merely similar loader repair.

## Reproduce

`verify_rebind_commutation.py` authenticates the already-landed transformer
source blobs before executing them. Against a repo checkout it proves the live
edge with no external fixture:

```bash
python -B verify_rebind_commutation.py --pretty
python -O -B -m unittest -v test_rebind_commutation.py
```

For the full commutation diamond, extract artifact `10175943272` and pass its
`seed-retry-runtime/titan_runtime.py`:

```bash
python -B verify_rebind_commutation.py \
  --baseline-runtime /path/to/seed-retry-runtime/titan_runtime.py \
  --pretty
```

The verifier refuses drift in the current runtime, foundation runtime, existing
fast-tape transformer, existing REBIND transformer, historical fast-tape
postimage, or new combined postimage.

## Authority boundary

This does **not** mutate `COMPOSITION.json`, enable `r04_fast_tape_clone`, write
production runtime bytes, materialize a release archive, run a game, or claim
speed/economic improvement. The live sole V4 graph/postimage owner retains graph
custody and may consume the exact rebased edge
`6d9720f4… -> 6472260d…` after its own ledger checks.
