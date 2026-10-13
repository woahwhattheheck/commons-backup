# Production-recovery retained-economics survivorship

This is a **single-V5 evidence arm** for the merged production-recovery candidate,
not a second candidate tree.

## Authority

The baseline is the exact reproducible production-recovery V2 archive:

`0aded66a2c393cc60f4f45d10f11c384a7e788182bf5430863829a02b66daf02`

It combines the submitted V3.1 R04 production closure with retained V4 economics.
Its `TITAN-CONFIG.json` is the exact V4 config
`ba18563683125fd89d5473ddb8a5c3e9431db1787a3046f618a9e03af2cb44af`.

Exact submitted-package archaeology established that V3.1 and V4 share sixteen
config keys with identical values. The only V4-only enabled config key is
`town_procurement=true`. Therefore the first candidate-level survivorship test is
only:

`town_procurement: true -> false`

The deterministic treatment config is
`70e849ebc9275250f474aa463b8f90862a7c224b10f9b2e91f8b78e04ad94463`.

This does **not** call the four-feature `all_four_off` arm a V3.1 reconstruction.
`idle_fertilizer`, `crop_release`, and `early_capital` were already true in the
submitted V3.1 package.

## Materialize

```bash
python -B materialize_town_off.py \
  --baseline /path/to/titan-v5-production-recovery-v2.tar.gz \
  --out /fresh/path/titan-v5-production-recovery-town-off.tar.gz \
  --receipt /fresh/path/titan-v5-production-recovery-town-off.json
```

The materializer authenticates the exact baseline archive before parsing, rejects
noncanonical tar members, changes only `TITAN-CONFIG.json`, preserves the exact
member set and every other member byte, emits a deterministic archive, and records
both complete member-hash maps in the receipt. Output paths are create-only.

Run the source contracts normally and under `-O`:

```bash
python -B -m unittest -v test_materialize_town_off.py
python -O -B -m unittest -v test_materialize_town_off.py
```

## Compute gate

No native game is authorized merely by this source landing. SPARK owns the current
native production-recovery V2 panel. Wait for that exact `0aded66a...` baseline to
finish and remain viable. Only then may the town-off archive become one additional
matched arm using the same official engine, opponents, seeds, seats, RNG, and
timeouts as the base panel. Reuse exact matching V3.1/V4 controls.

Stop after this one arm for review. Do not expand to a factorial or use the result
to mutate runtime defaults, `CURRENT`, a release pointer, or a Kaggle submission.
