# TITAN W0 archive promotion gate

This directory is an additive, non-custodial acceptance layer for the independent
`weed_continuation` capability split. It does **not** modify the canonical runtime,
archive pointer, release state, gameplay selection, provider, Kaggle, or submission.

The source repair is necessary but not sufficient: the V2 regression existed in the
shipped artifact even though the visible feature toggles appeared off. This gate
therefore evaluates the archive that would actually be promoted.

## Contract

`verify_archive.py` fails closed unless all of the following hold:

1. the base archive matches an exact SHA-256, byte count, and member count;
2. no path, link, device, duplicate, case collision, oversized member, or undeclared
   archive delta escapes the contract;
3. `TITAN-CONFIG.json` contains explicit JSON `"weed_continuation": false`;
4. `SOURCE.json.default` exactly equals the packaged config and its runtime entries
   bind every declared changed source/test member by bytes and SHA-256;
5. the **actual extracted package** passes all 32 P/T/I/C/W construction masks;
6. all-off leaves `self.spatial is None` and does not install a spatial wrapper;
7. I-only, C-only, and W-only each still construct the shared service object;
8. P/T with W0 cannot reach `_continue_weed`, while W1 can;
9. a retained impossible W1 plan is scrubbed during W0 producer reconstruction
   without erasing unrelated idle-fertilizer state; and
10. the package configuration constructs W0, even when I/C keep SpatialTempo alive.

The runtime probe executes in a separate isolated Python process with deterministic
environment settings and a timeout. It is code execution, not a security sandbox;
archive path/type validation and subprocess isolation prevent filesystem extraction
escapes, while ordinary repository review remains the trust boundary for source.

## Pinned current contracts

`contract-current-base-hold.json` binds the exact canonical predecessor and must
classify it as `HOLD` with `config.weed_continuation_missing`.
`contract-current.json` binds the same predecessor while requiring the four
production members (`TITAN-CONFIG.json`, `SOURCE.json`, `titan_runtime.py`, and
`spatial_tempo.py`) to change and allowing no added or deleted members. CI runs the
negative control directly against the packaged archive in the repository.

The unit suite also mutation-tests the coupled P/T construction gate, an unguarded
weed call, stale W1 state, a true feature default, and unconditional all-off
installation. See `EVIDENCE.md` for receipt identities and evidence boundaries.

## Run

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m py_compile verify_archive.py runtime_probe.py tests/test_verify_archive.py

python verify_archive.py \
  --base /path/to/base.tar.gz \
  --candidate /path/to/candidate.tar.gz \
  --contract contract-current.json \
  --receipt /tmp/titan-w0-archive-receipt.json
```

Exit status is `0` only for `PASS`, `2` for a policy `HOLD`, and `3` for an internal
error. Every outcome writes a deterministic receipt when `--receipt` is supplied.
