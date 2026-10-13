# FRUITPROOF: independent B5 production and economic acceptance

This is executable verification inside the single `main:candidates/v4/repairs/gameplay/b5-tomato-redirect` component, not another B5 policy, V4 branch, or production switch. SOLANUM-2863 owns `discarded_fertilizer_tomato.py` and its native binding. ORCHARD owns reachable grower/field controls in `research/tomato-window`. FRUITPROOF owns these independent constructed-state tests.

## Exact scope and custody

The historical Muse-local `b5_tomato_redirect.py` was not recovered and is not reconstructed here. The source actually accepted is SOLANUM's NEW companion, Git blob `31cddc7674d1b5a6cea33258881e7dfa25e47c38`, with `apply_discarded_fertilizer(observation, action, configuration=None, *, enabled=False) -> (action, report)`.

Five reference inputs are authenticated before import: the complete official interpreter, its specification and utility file, and both existing evaluator/loader files. They come from existing GitHub Actions artifact `10175943272`, ZIP SHA256 `3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`; unpack its `final-pressure-runtime` directory. The engine Git blob is `3c202c7ee921da239356789e266b694635103fc4`. No network preparation, mock engine, local owner PC, paid runner, or legacy R04 materializer is used. This artifact is NOT a claim of current-main native source equality.

## Reproduce

From this component directory, with `RUNTIME` pointing at that extracted runtime and `OWNER` pointing at the exact source above:

```sh
python run_fruitproof.py --runtime "$RUNTIME" --candidate "$OWNER" \
  --candidate-blob 31cddc7674d1b5a6cea33258881e7dfa25e47c38 \
  --output /tmp/fruitproof-normal
python -O run_fruitproof.py --runtime "$RUNTIME" --candidate "$OWNER" \
  --candidate-blob 31cddc7674d1b5a6cea33258881e7dfa25e47c38 \
  --output /tmp/fruitproof-optimized
```

The CLI writes `receipt.json`, complete `economics.json`, normal-suite logs, engine-control logs, and per-owner-mutant logs. Missing/drifted references or owner identities fail before import. A candidate cannot be supplied without a full blob pin. Without `--candidate` and `--candidate-blob`, only the independent engine/economic phase runs and owner acceptance is explicitly `NOT_RUN`. Test assertions remain active under `-O`. Deliberately moving the first-yield rule emits an expected engine warning in the negative-control phase; the unmodified engine has no such failure.

## Executed results

Both normal and optimized Python passed 26 engine tests plus 8 exact-owner acceptance tests. Per mode:

- 1,920 pulse counterfactual pairs span both seats, service ages6..11, held yields0..4, watered/dry states, coverage offsets and carried-input presence. Together with21 multi-day counterfactual pairs and focused state/action controls, the engine suite executes8,239 complete interpreter transitions.
- 16 separately recorded economic pairs execute3,328 transitions. Their full serialized economics output is byte-identical across modes (SHA256 in the validation receipt).
- 500 owner callbacks cover480 simple eligibility cells plus ownership/identity controls. Exactly24 cells activate;48 complete interpreter calls independently prove their one-transition certificate: retained inventories, cash and market equal; the selected tile gains exactly1 TOMATO at dawn.
- Eight broken ENGINE variants and nine broken OWNER variants are rejected by assertion failures, not import errors or skips. Including these controls, the final run executes15,983 complete interpreter transitions per mode.

The owner-source mutants exercise ignored disablement, spending a retained input, already-covered tiles, a false held3 cap certificate, missing WATER, wrong service night, collocated double spending, mutating caller data, and reporting a proposal without actually changing the returned command.

## Findings the composer must preserve

An actual TOMATO's four production pulses arrive at ages8..11; supplying service nights are ages7..10. Fertilizer coverage includes the service day, but a zero drought streak does not substitute for WATER that day. Carrying three tomatoes is already too full for an additional next-dawn unit: baseline grows3->4 and fertilized also grows3->4. The new helper's `held <= 2` condition is therefore essential for its exact +1 certificate.

A constructed age7 plant with identical subsequent daily WATER/HARVEST commands gives4->7 harvested tomatoes from one fertilizer. With unused fertilizer actually sold by the control, measured cash deltas at initial TOMATO market inventories10000/9800/9400/10500 are +66/+152/+2564/-91. Holding harvest until the final pulse instead gives4->4 and -100 in all four price setups. These are actual multi-day full-engine counterfactuals, not estimates and not native field wins. The economic fixtures spend retained fertilizer deliberately to expose opportunity-cost mistakes; they are NOT claims that the discarded-input helper takes those actions.

For the accepted new helper, a full shed and no room-releasing returned actions establish that the selected carried input would otherwise disappear at EOD. That establishes a physical next-dawn improvement, not that later harvest, storage, sales or final margin improve. Empty opportunity sets are untested setup, not a KILL. Original donor configuration wiring, the native finalizer integration, naturally reached activation, full-game competitive economics, and any default promotion remain separate source-owner/ORCHARD gates. No production config, archive, Kaggle submission, or runtime policy is changed by these files.
