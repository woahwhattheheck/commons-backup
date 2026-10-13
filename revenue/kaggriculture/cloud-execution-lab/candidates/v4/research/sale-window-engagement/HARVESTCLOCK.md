# HARVESTCLOCK: actual-fill sale-window acceptance

One canonical integration home: `main:revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/sale-window-engagement`.

This is independently authored, executable acceptance tooling and recorded native evidence. It is **not** the historical `r04_sellby15` policy, which has not been recovered, and it does not activate a sale policy. SELLWINDOW owns complementary native activation/receipt wiring in this same directory and has consumed the exact `sale_window.py` blob `20e623722fbb3f8a9cdb71add009a9f68756819d`. There is no second controller or V4. KEEL retains runtime composition; WEAVE retains optimizer composition.

## What the oracle measures

`sale_window.py` authenticates four official reference inputs, then calls the entire interpreter. Temporary observers around parsing, successful unit transactions, and market entry restore in `finally`. They do not implement replacement market arithmetic. Execution is sequential and **not thread-safe**.

`shift_sale` moves one positive literal SELL between different turns, replaces its original raw slot with PASS, and uses only a destination PASS or appended slot. It neither compacts invalid rows nor assumes a requested quantity will fill. Other own actions and the opponent's recorded actions remain unchanged. Each action is copied independently so cross-turn input aliases cannot change an unrelated turn.

`compare` replays both arms from independent copies of one snapshot. It distinguishes changed returned commands from changes in successful sales. It reports actual post-unit shed contents, exposed raw rows, successful quantities, sale cash, final state/environment hashes, both players' cash, and terminal margin only when both arms are DONE. Ignored raw commands may change the full-state hash because actions are retained; a separate outcome hash excludes those action fields.

This is an **open-loop counterfactual**: future actions remain recorded, rather than being recomputed by either agent after intervention. It is not an adaptive policy gate, forecast, competitive strength estimate, or promotion decision.

## Executed results

Python 3.13.5 in the session container; no owner-PC or paid compute.

| Gate | Result |
|---|---|
| Focused suite | 23/23 normal and 23/23 `-O`; no skips |
| Independent observer/pristine corpus inside suite | 48 complete state+environment pairs per mode |
| Deliberately broken source variants | 10/10 assertion-rejected per mode; no infrastructure-error rejections |
| Actual archived-native entrypoint | Two serial seed-17 games, both seats; 719 completed callbacks each, zero fallback |
| Stored evidence replay | 15,818 complete interpreter turns in normal mode and again in `-O`, exact recorded results |
| Whole-game timing interventions | 10 paired cells total, five per seat; not ten independent competitive seeds |

Native captures authenticated all 109 runtime members. Scores were 105846/3741 as seat 0 and 3741/105846 as seat 1. In each capture, 222 exposed SELL rows included 221 filled rows and 1492 successfully sold units. Instrumented replay reproduced the uninstrumented native capture's full final state, environment, action-tape hashes, and rewards.

The predeclared residual panel selected the first actually filled sale per product during days 14–16 inclusive and attempted shifts of exactly one turn. Both seats gave the following results:

| Product / shift | Terminal margin delta | Realized interpretation |
|---|---:|---|
| MILK earlier | +1262 | **Suppressed sale, not an earlier fill** |
| MILK later | 0 | Fully filled retiming |
| WOOL earlier | -2 | Fully filled retiming |
| WOOL later | 0 | Fully filled retiming |
| STRAWBERRY earlier | Not executed | No free exposed destination slot |
| STRAWBERRY later | 0 | Fully filled retiming |
| MELON | Not executed | No filled source in the declared window |

The apparent +1262 improvement must not be reported as an earlier milk-sale benefit. The source at step 338, raw row 0, sells 6 MILK for 588. Its proposed earlier destination at step 337, row 3, has zero MILK after unit actions and fills zero. Withholding the original sale changes later market prices and retained cargo, including later wheat/strawberry fills. `timing_witness` therefore labels it `SUPPRESSED_SALE_NOT_RETIMED` and preserves source/destination fill evidence. The eight genuine retiming cells are six zeroes and two -2 outcomes. These small fixed-tape results do not dispose of an unrecovered or differently wired policy.

A development bug initially inspected parsed `op` instead of the official `type` field and produced a false zero census. It was corrected without changing the recorded native action tapes. A focused regression and deliberately broken variant now catch that exact mistake. A second regression catches the false earlier-fill interpretation above. Both corrections and raw execution logs remain in the evidence.

Other covered boundaries include successful $1 floor sales without market inventory growth, no-stock and capped-out orders, minimum-one live cap, partial/duplicate sales, raw-slot atomic funding, unit DROP before market versus EOD delivery after market, rival supply reversing a waiting advantage, terminal rival-cash effects, source/step validation, numeric exceptions, and alias preservation.

## Reproduce the delivered results

Run from this directory. `REF` must be the extracted reference directory containing `engine/` and `evaluator/`; all four inputs are authenticated before execution.

```sh
export TITAN_REFERENCE="$REF"
python -m unittest -v test_sale_window
python -O -m unittest -v test_sale_window
python run_negative_controls.py
python replay_evidence.py --reference "$REF"
python -O replay_evidence.py --reference "$REF"
```

`HARVESTCLOCK-EVIDENCE.json` is a manifest for four adjacent `.part0`–`.part3` files. The reader joins the parts, verifies the packed length and SHA256, decompresses the payload, verifies its length and hash, and verifies both recorded action tapes before replaying. The payload retains both native results and timings, all ten executed counterfactual results and fill witnesses, focused test logs, and all twenty negative-control logs. It is not a placeholder or a link to unavailable session files.

The second independently captured tape was verified to be the exact seat swap of the first; it is encoded losslessly that way, and its original full-tape hash is checked after expansion. Symmetry is not assumed for other games. The replay command calls no native agent and reproduces stored results deterministically with the pinned engine.

Optional new captures require the complete native package and its original `CURRENT-SOURCE.json` manifest. Run seats serially in fresh processes:

```sh
python run_native.py --native "$NATIVE" --manifest "$MANIFEST" --reference "$REF" --seed 17 --seat 0 --output seat0.json
python run_native.py --native "$NATIVE" --manifest "$MANIFEST" --reference "$REF" --seed 17 --seat 1 --output seat1.json
```

The native agent uses wall-clock budgets, and the official starter constructs an unseeded random generator internally. Therefore a new capture is not promised to reproduce a previous action tape from the seed alone. The delivered recorded tapes remove that ambiguity for the reported counterfactuals.

## Source identity and limits

Native archive recovered from artifact `10175943272`:
`b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.
Original 109-member manifest SHA256:
`e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2`.
Reference Git blob pins:

```
engine/kaggriculture.py    3c202c7ee921da239356789e266b694635103fc4
engine/kaggriculture.json  b354d06b742fe48402513792253f1a5c29366b20
engine/utils.py            91c8822ee6201ba4a5a8416c7dbe34f95dd61c87
evaluator/loader.py        23948e10cfc3d32f46c9abb1321b0d8fc8db21d5
```

Historical `r04_sellby15` source and the original -86 raw gate remain a source-custody gap requested from Riot/Muse in Slack thread `1789182925.344409`. Never-fired/wrong-setup evidence is not a kill. This package does not close that gap or substitute a reconstructed donor. The executable oracle/evidence delivery is complete; native wiring is the complementary SELLWINDOW contribution in the same home, not a new builder demand.

No current composed-V4 certification, strong-opponent/held-out gate, adaptive economic benefit, Python 3.11 execution, or hosted CI-green result is claimed. No production, default, configuration, archive, workflow, or Kaggle mutation is part of this delivery.
