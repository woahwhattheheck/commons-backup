# Early-capital full-agent paired execution

ASTRA-CONVERGE execution support for the existing ASTRA-CAPITAL recovery, PR #12713. This is part of `main:candidates/v4/repairs/gameplay/early-capital`, not another controller, feature, release or integration branch.

## What actually ran

The final development panel executed **16 complete games forming eight paired cells**, plus **two uninstrumented observer-parity replays**. Every game completed 719 interpreter steps through terminal step 718. There were no game failures or observed deadline fallbacks. The normal and `python -O` runner-test invocations each passed all 15 tests; the games themselves ran under normal Python 3.13.5, not both modes.

The only variant source difference was `early_capital.py`: control `1161859ac5af617eca65aec3f732b5c1396cad37`, candidate `c87f1d1c9d7b416c5316837634f7e721c85811fa`. The candidate is the existing recovered source in this directory, not a new implementation. Native `main.agent`, `FinalPressureAgent`, producer search, `act`, enabled stock/seed/capital transforms and final pressure all ran. The existing pinned evaluator owns the official interpreter serially and isolates both agents in separate processes. No action is rewritten by the observer.

The pre-outcome plan used seeds **17 and 101**, both seats, and two opponents: the pinned official starter and the complete native control agent. This is a small, disclosed development cohort, not a hidden test set or a strong-opponent gauntlet.

| Opponent | Seed | Own score, both versions | Rival score, both versions | Seats executed | Different returned actions per pair |
| --- | ---: | ---: | ---: | --- | ---: |
| Official starter | 17 | 105846 | 3741 | 0 and 1 | 3 |
| Official starter | 101 | 180745 | 3816 | 0 and 1 | 2 |
| Native control | 17 | 120576 | 120576 | 0 and 1 | 3 |
| Native control | 101 | 87313 | 87313 | 0 and 1 | 3 |

**All eight pairs had delta own = delta rival = delta margin = 0.** Each variant finished 4 wins / 4 ties / 0 losses. There were zero new losses or lost wins relative to control. This does not establish improved field strength.

The change was **not action-inert**. There were **22 differing final returned actions**, at steps 150, 195 and, in six pairs, 226. Control reordered on 24 callbacks; candidate reordered on two callbacks. Each variant had 5752 observed capital callbacks. The candidate's conservative `unproved_capital_sequence` decision preserved earlier WHEAT purchases instead of moving capital ahead of them. Farmer/hands matched in all 22 retained difference witnesses. The differing action sequences happened to yield equal terminal scores on this cohort; do not call the two variants trace-identical.

Separately, the observer and uninstrumented replay had identical complete evaluator trace hashes and scores **within each variant** on starter/17/seat0. This is a two-game instrumentation parity check, not two additional independent economic comparisons. Maximum observed RPC time across the 16 panel games was 0.109496 seconds; that is local execution evidence, not hosted deadline certification. The evaluator's actor exit code -9 is its deliberate cleanup after completed episodes, not a reported gameplay crash.

## Exact scope and custody

This is an explicitly historical **native fixture**, not current-full-main. The source artifact is **10169538667**; its `checked-package/exports/titan-current.tar.gz` is SHA256 `5f6a4153e502713b9467776eafe7464af650584149173ce7507a31a1b2af60f1`. The fixture adds the same artifact's `final-pressure-runtime/checks/reference/` files for the existing evaluator and engine. Its original capital module was `9bb3a0da`; both variant copies replace it with their respective exact control/candidate bytes. Matching five selected runtime pins alone would not establish complete agent identity.

The runner inventories all **110 fixture files** and both complete variant trees, requires the sole capital source delta, and confirms all source trees remain unchanged after execution. Important pins are checked before agent execution:

- Native runtime `b952c9c228ecbde592bf3d2df01638677abb0d24`; main `4a8cf7bcda1f0fea231a144692cb84a779a9e73e`.
- Scheduler `a483b24dd72b580d7d8811636b54d2d44f391575`; stock `781aa90da0d85d0ba23c665e29d6087d182c085e`; config `3a3bef83899d3010fad623b628d9e95d9978111b`.
- Mechanics `044a4f9c0a4a44dde10ada57563238bcaf82075d`; official engine `3c202c7ee921da239356789e266b694635103fc4`.
- Existing evaluator `1fb6b655bb4ca1e1684be165a8ef513e2e6c2325`; loader `23948e10cfc3d32f46c9abb1321b0d8fc8db21d5`.
- Executed runner `cfa2d3fe65bfda415df353faba13f864f766ec36`; tests `ef40688a7d5aadb58e07d391b80289f3d4805cea`.

Canonical JSON plan digest: `65f2b9c82256db186fb2d9b2309f8a35e82bba943c0644a4d5d8809c23a50aeb`.
Fixture inventory digest: `3a035eda332ab2c181fbf8d18252ebb010d217cf4168ff4a5f45c227d1d64f9d`.
Control inventory digest: `d26e77d53da5a34078832c7c23b5eb5e3f4dd76d9f9334fed12b157f4857fd70`.
Candidate inventory digest: `899772ad548443d09573d2f4f3575cb23b60173ced1e542a58b2ff84b31a1c40`.

## Read the durable results

`FIELD-RESULT-BUNDLE.json.xz.b64` is a text-safe evidence transport, **not a submission archive**. Decoded XZ SHA256 is `1fa65135d11e8e5d71fda8e411f0e7fa256a6bac1d10c4e6baba1e9edb82b56f`. The committed Base64 file has Git blob `211e56efb783f7a0235777eda950456bf1db6ccd`.

The bundle contains the complete pre-outcome PLAN and inventories, complete RESULTS, all **18 raw per-game result records**, all **22 differing-action witnesses** including both versions' capital diagnostics, and both raw 15-test logs. It intentionally omits the 16 complete action-stream files; their exact Git hashes remain in the raw game records. The runner emits those full streams on reproduction. Exploratory runs from an earlier observer revision are excluded, not pooled into the final evidence.

Decode from this directory into a fresh directory with standard Python:

```python
import base64, hashlib, json, lzma
from pathlib import Path
encoded = Path('FIELD-RESULT-BUNDLE.json.xz.b64').read_bytes()
compressed = base64.b64decode(encoded)
expected = '1fa65135d11e8e5d71fda8e411f0e7fa256a6bac1d10c4e6baba1e9edb82b56f'
if hashlib.sha256(compressed).hexdigest() != expected:
    raise ValueError('Evidence digest mismatch')
bundle = json.loads(lzma.decompress(compressed))
out = Path('decoded-field-evidence')
out.mkdir(exist_ok=False)
for name, text in bundle['files'].items():
    if Path(name).name != name:
        raise ValueError('Unexpected evidence path')
    (out / name).write_text(text)
```

## Reproduce

Prepare the above exact fixture from artifact 10169538667. Preserve its packaged files, then overlay only the `checks/reference/` subtree from `final-pressure-runtime`. The full expected file inventory is in the decoded PLAN. Do not substitute another artifact just because a subset of hashes matches. The control module is available at repository commit `2e65099756fe85dd5f52673afba029b5b972527f`, production path `revenue/kaggriculture/cloud-execution-lab/early_capital.py`; it was independently fetched and verified as `1161859a`.

From this package directory, with the fixture and control module outside the output directory:

```sh
python test_capital_pair_panel.py
python -O test_capital_pair_panel.py
python run_capital_pair_panel.py --fixture /path/to/native-fixture \
  --control /path/to/control116.py --candidate early_capital.py \
  --output /tmp/capital-field-new --seeds 17,101
```

Use `--max-cells 4` for bounded batches and the same command plus `--resume` for later batches. Exit 3 means an explicitly partial saved panel; it is not completion. Resume rejects plan/runner/source drift, verifies existing telemetry hashes and retains failures instead of silently retrying or dropping them. The results include correctly seat-oriented own, rival and margin deltas.

The old `loader.play` helper rejects canonical extra hand rows before the official interpreter processes them; this runner deliberately uses the existing process-isolated evaluator's `play` instead. It does not alter agent actions to appease that retired helper.

## Integration disposition

This adds actual full-agent lifecycle and natural-engagement evidence to the source component's existing constructed-turn checks. It does **not** authorize current V4 promotion: composed current-main dependency binding, one final package/source identity, joint newer prefix/lifecycle repairs, a broader and genuinely stronger opponent cohort, and paired economic benefit remain separate gates. R04 legacy materializer reachability is not established or needed by this native fixture.

No production source, config/default, workflow, release pointer, submission archive or Kaggle state was changed. Reuse this runner and existing capital component in the sole V4 workspace instead of creating another evaluator or capital patch.
