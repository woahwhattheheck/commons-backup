# Native production recovery diagnostic

This finite Linux sample uses the unchanged existing generic evaluator and
pinned raw-file loader. Seed 1209129901 was unused in the visible Slack queue;
it does not replace SPARK's original three-seed assignment or any top30 shard.
Both Apex_v7 and Arlene_v14 run in both seats, with RNG 20260912 and
action/startup/game limits 1.25/10/900 seconds. Native policy timers stay enabled.

The original production v2 `0aded66a…` fails all four cells on the first
decision with `ModuleNotFoundError: full_production_context`. The context file
is present, but its lazy import occurs after the raw loader restores sys.path
and before baseline.agent can install the payload directory. The v3 repair
loads that module at entry-file execution. No policy or config changes occur.

All subsequent games finish 719 decisions with no external failure: four cells
each for V3.1, V4, production v3 and the two existing survivorship treatments.
The eight completed controls are reused; they were not rerun for treatments.

| Arm | Apex own/rival | Apex margin | Arlene own/rival | Arlene margin |
|---|---:|---:|---:|---:|
| Submitted V3.1 | 74143/64333 | 9810 | 74260/68660 | 5600 |
| Submitted V4 | 70385/62323 | 8062 | 69847/68401 | 1446 |
| Production v3 | 73906/63838 | 10068 | 74592/68772 | 5820 |
| Town-off | 73904/63838 | 10066 | 74591/68772 | 5819 |
| Aggregate bypass | 74143/64333 | 9810 | 74260/68660 | 5600 |

Both seats produce the same mirrored terminal scores. These are correlated
measurements on one seed, not four independent replications. Production v3
improves margins over both submitted controls. Against V3.1 on Apex it gives
up 237 own-score and reduces the rival by 495; on Arlene it gains 332 own-score
while the rival gains 112. Keep the full composition for wider development;
neither blanket removal improves it. The Apex own-score gap prevents claiming
the strict champion condition. No release or submission is authorized by this
sample. V3 max callback 0.252s and zero external failures supply a native timing
observation for this sample, not a hosted-runtime guarantee.

`SUMMARY.json` derives paired deltas from the complete unchanged evaluator
reports and records their SHA256 values. `INPUTS.json` retains the original
archive/member manifests; `IMPORT-REPAIR.json` binds v3's one-member change.
The opponent manifests retain source and compiler identities. `RUN.json`,
`COMPLETED.json` and `TREATMENTS.json` are historical execution records with
cloud-local paths and process-namespace PIDs, not live process claims.
No per-action trace was emitted by the existing evaluator; its daily bank
series and trace digests are retained. They do not establish a first-action
causal diagnosis.

## Reproduce the exact candidate inputs

Build v3 with the parent directory's `build_production_recovery.py`; it must
emit SHA256 `20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239`.
The two configs here are byte-identical to the outputs of merged #13462 and
#13464. Applying each to v3 changes only `TITAN-CONFIG.json`; the eager context
import is identical in all three candidate arms. From the parent directory:

```python
from pathlib import Path
from build_delivery import archive_bytes, digest, members

base = members(Path('/path/to/production-v3.tar.gz'),
    '20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239')
for arm, expected in (
    ('town-off', '535ac1bbae3f68bad78dd7904c1a225ad791c87fb1bf79f981df2493848a661d'),
    ('post-bypass', '8ffe4e594d2325fe095bb8d38db0e3e7eb2cb4f485fa144a111ba9b2c51ee144'),
):
    files = dict(base)
    files['TITAN-CONFIG.json'] = Path(f'native-9901/{arm}-config.json').read_bytes()
    packed = archive_bytes(files)
    if digest(packed) != expected:
        raise ValueError('Treatment differs from the tested archive')
    with Path(f'/new/output/{arm}.tar.gz').open('xb') as out:
        out.write(packed)
```

Use the existing generic evaluator command in `PRODUCTION-RECOVERY.md` with
the corresponding adapter and seed 1209129901 to reproduce this experiment
only when explicitly needed. Preserve the completed reports for ordinary
analysis; the sample's conclusion does not require more copies of these games.
