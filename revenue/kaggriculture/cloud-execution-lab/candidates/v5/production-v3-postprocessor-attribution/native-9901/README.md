# Native production-v3 stage screen: seed 1209129901

All 20 new games completed 719 callbacks without an evaluator failure: 12
stage-knockout games and eight matched consumer-boundary games. The stage
knockouts do not repair the remaining Apex own-score deficit. The parent
consumer bundle improves Apex own score but loses competitive margin to its
matched frozen control against both opponents. No policy or default changes
are selected by these results.

The unchanged generic evaluator ran exact production-v3 config-only treatments
against the original native-9901 Apex v7 and Arlene v14 adapters and the original
precompiled Apex binary. For the three-arm screen, all 319 input paths were
hashed before and after execution with no changes. Python 3.12.14, engine,
evaluator, loader, opponent
entries, RNG 20260912, both seats and limits 1.25/10/900 match the retained
control sample. Native policy timers remained enabled. Two treatment arms ran
concurrently at most; all completed control games were reused.

| Arm | Apex own / rival | Apex margin | Delta own / margin vs full | Arlene own / rival | Arlene margin | Delta own / margin vs full |
|---|---:|---:|---:|---:|---:|---:|
| Submitted V3.1 (reused) | 74143 / 64333 | 9810 | +237 / -258 | 74260 / 68660 | 5600 | -332 / -220 |
| Full production-v3 (reused) | 73906 / 63838 | 10068 | 0 / 0 | 74592 / 68772 | 5820 | 0 / 0 |
| seed_hire_off | 73906 / 63838 | 10068 | 0 / 0 | 74592 / 68772 | 5820 | 0 / 0 |
| inventory_spatial_off | 73907 / 63838 | 10069 | +1 / +1 | 74593 / 68772 | 5821 | +1 / +1 |
| late_market_off | 73832 / 63894 | 9938 | -74 / -130 | 74562 / 68798 | 5764 | -30 / -56 |

Both seats produce the same mirrored terminal scores. They are correlated
measurements on one seed, not independent replicates. The inventory/spatial
arm leaves an Apex own-score gap of 236. Removing late-market logic harms
both own score and competitive margin. These outcomes do not justify disabling
any group or claiming the restored V5 has passed the champion comparison.

`SUMMARY.json` pairs every new cell to the five existing control reports in
`selective-carrot/native-9901` and binds their raw hashes. `SCREEN.json` contains
the exact three-arm archive/member manifests: only `TITAN-CONFIG.json` changes
and all 91 other members are identical. `INPUT-CUSTODY.json` binds the actual
executed adapters and all inputs. `RUN.json` records native execution and the
successful final input readback. The three evaluator reports are unmodified.
Historical cloud paths and process-namespace PIDs are provenance, not current
process claims. Actor cleanup exit codes are not game failure: use the
evaluator's complete status, failure field and 719-step count.

The completed [matched consumer pair](consumer-boundary/README.md) uses
identical required-off leaves and changes only the consumer config value.

| Pair arm | Apex own / rival | Apex margin | Arlene own / rival | Arlene margin |
|---|---:|---:|---:|---:|
| Matched frozen control | 73905 / 63838 | 10067 | 74592 / 68772 | 5820 |
| Matched parent | 74211 / 64279 | 9932 | 74290 / 68634 | 5656 |
| Parent minus matched control | +306 / +441 | -135 | -302 / -138 | -164 |

This conditional comparison measures the consumer boundary bundle, including
its downstream runtime gates. It does not isolate FrozenSelected alone. Parent
exceeds V3.1 own score by 68 against Apex and 30 against Arlene in this sample,
but loses margin to full production-v3 by 136 and 164 respectively. The pair
subdirectory preserves its separate 226-input custody, unchanged raw reports,
all per-cell deltas, and the #13472 source-provenance clarification. The original
three-arm receipts above remain unchanged. No CURRENT, release pointer,
gameplay default or Kaggle submission changed.
