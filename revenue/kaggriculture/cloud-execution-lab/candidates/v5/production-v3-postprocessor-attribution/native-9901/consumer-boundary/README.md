# Matched consumer boundary: native seed 1209129901

All eight games completed 719 callbacks without evaluator failures. Relative to
the matched frozen control, the parent bundle gains 306 own score against Apex
but gives the rival 441 more, reducing margin by 135. Against Arlene, own score
falls 302 and margin falls 164. These results select no promotion or default
change.

| Arm | Apex own / rival | Apex margin | Arlene own / rival | Arlene margin |
|---|---:|---:|---:|---:|
| Matched frozen control | 73905 / 63838 | 10067 | 74592 / 68772 | 5820 |
| Matched parent | 74211 / 64279 | 9932 | 74290 / 68634 | 5656 |

| Parent minus comparison | Apex delta own / rival / margin | Arlene delta own / rival / margin | Interpretation |
|---|---:|---:|---|
| Matched frozen control | +306 / +441 / -135 | -302 / -138 / -164 | Conditional consumer boundary bundle |
| Full production-v3 (reused) | +305 / +441 / -136 | -302 / -138 / -164 | Descriptive strength comparison |
| Submitted V3.1 (reused) | +68 / -54 / +122 | +30 / -26 / +56 | Descriptive strength comparison |

Both seats give identical mirrored terminal scores. They are correlated
measurements of one seed. The parent's improvements over V3.1 in this sample
do not establish a champion result or remove its margin loss against full V5.

The archives differ only in `TITAN-CONFIG.json`, and their configs differ only
in `consumer=frozen` versus `consumer=parent`. Both set `redundant_hire`,
`idle_fertilizer`, `crop_release` and `town_procurement` false. Each archive has
92 members, with the other 91 identical to full production-v3. Parent bypasses
`FrozenSelected.transform` while retaining controller construction, and also
gates spatial, operating-stock, feed-stock and early-capital stages. The matched
delta therefore measures this consumer boundary bundle; it cannot isolate
FrozenSelected alone. Comparisons with other controls are descriptive because
the required-off leaves differ.

The unchanged official-interpreter driver used Python 3.12.14, RNG 20260912,
native policy timers, both seats, and action/startup/game limits 1.25/10/900.
Engine, evaluator, loader, opponent entries and other report authority fields
match all five retained native-9901 control reports exactly. Execution hashed
all 226 input paths before and after with no changes; evidence preparation
also verified their current hashes. Control games were reused.

`RUN.json` is the byte-identical completed execution record; it binds both raw
reports and `INPUT-CUSTODY.json`. `SCREEN.json` is the unchanged pre-run
materialization receipt, so its pending-economics field is historical.
`SUMMARY.json` derives every new cell's own/rival/margin and deltas to both pair
arms and all five retained controls, including their raw report commitments.
Historical cloud paths and process-namespace PIDs describe the recorded run.
Actor cleanup exit codes are separate from complete game status and failure.

`SOURCE-PROVENANCE.json` clarifies the immutable input receipt's `source_main`:
`1f3daa2f93b7be8c52a0aa81c488402bd93adb1e` is the local checkout commit, not
canonical GitHub main. The consumed materializer came from #13472, merged at
`d898babbaed187a951e11de57eadca7b32440774`; its SHA-256 is
`171a09116b0aa4f111677163285bad20088903ac7d1f1b9a522b6c841c3be016`, verified
identical at both commits. The raw receipt remains unchanged.

No CURRENT, release pointer, gameplay default or Kaggle submission changed.
