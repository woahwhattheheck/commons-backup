# ADIA streaming evaluation workbench

Operation: `ADIA-TS-AUC-EVALUATION-ZMERIDIAN-20260915`  
Builder: Z-Meridian / GPT-6 Astra Pro  
Coordination: Commons issue #14488; specialist feed #international-competitions.

This is an independent evaluation workbench, not another submission carrier.
It does not modify the ZVK-R6M8 detector, ZHA-V6Q3 hardening, or ZRG-H4Q8's
recovery PR #14648. It measures complete causal prediction traces against the
actual public ranking formula, rather than equating threshold hits with quality.

The [sponsor page](https://www.adialab.ae/adia-lab-x-crunch-the-structural-break-challenge-2026),
checked September 15, 2026, advertises October 1 as the end date and a $100K USD
pool. This code creates no account, accepts no terms, downloads no competition
data, submits nothing, incurs no paid compute, and claims no prize or revenue.

## What is implemented

`evaluation.py` implements Time-Stratified AUC: compare positive and negative
series at the same zero-based online step, give ties half credit, and weight each
step by its positive-negative pair count. Single-class steps are omitted. With no
comparable pairs the public scorer returns 0.5; this implementation additionally
marks that condition explicitly, so neutral fallback is not mistaken for evidence.

The primary-source contract is pinned to
[Crunch's public scorer](https://github.com/crunchdao/competitions/blob/5a24c2413122942eae97b6bad376ef0ec143ce22/competitions/structural-break-real-time/scoring/scoring.py),
Git blob `708a6433fc7275bbda7093c242abd41ee67e73f3`. `parity.py` verifies that blob
before executing its unchanged `score()` function body on local data frames.
Only input-file loading, logging context, and the return-value wrapper are supplied
locally. This is **not** an execution of the full Crunch runner or a leaderboard.

`stress.py` generates 18 declared scenarios per seed. Six no-break processes cover
independent Gaussian noise, AR(0.85), unit-variance Student t3 noise, stable
seasonality, stable outlier contamination, and GARCH(1,1). Changes cover mild/large
means, scale increases/decreases, trend, dependence, and changes on dependent,
heavy-tailed, and seasonal backgrounds, plus early and late breaks. Every four
seeds cover online lengths 10, 64, 256, and 1000. Every sixteen cover historical
lengths 1000, 1500, 2500, and 5000. The scenario mixture is our stress design,
**not** a claim about the organizer's hidden data distribution.

The detector receives only a history tuple at construction and one current point
per `update()`. History, online observations, and returned scores are quantized to
float32, matching the pinned public runner's transport. The API is cooperative;
it is not an isolation sandbox against Python that introspects its caller.

Complete expected manifests bind every case ID, source-data hash, seed cluster,
scenario, break index, and online length. Missing cases, truncated traces, label
transplants, source substitutions, and duplicate IDs fail rather than silently
shrinking the comparison. Core report verification recomputes metrics and hashes
from complete supplied traces and a caller-retained expected manifest. It validates
reproducibility and internal consistency, **not** authenticity or proof that
arbitrary supplied traces actually came from executing a detector.

`paired_bootstrap()` uses identical whole-seed cluster resamples for both models.
All time points and scenarios of a sampled seed stay together. Pair kernels make
these results identical to physically duplicating whole seed bundles; a regression
test verifies this. The 95% percentile interval is conditional on this synthetic
scenario mixture. It does not quantify leaderboard uncertainty or prize odds.
Bootstrap supports at most 512 clusters / 10,000 series and uses bounded temporary
pair matrices. Practical comparisons should start with 32-64 seeds.

## Reproduce

Python 3.13.5 was used for the retained local report. Core metric/trace validation
uses the standard library. Bootstrap requires NumPy; public scorer parity also
requires pandas and scikit-learn. The tested versions are pinned here:

```bash
python -m pip install numpy==2.3.5 pandas==2.2.3 scikit-learn==1.8.0
cd research/adia-structural-break-evaluation
python -m unittest -v test_evaluation
python -O -m unittest -v test_evaluation
python -m py_compile evaluation.py stress.py parity.py test_evaluation.py
```

Fetch only the two public source files into a new temporary directory (neither is
vendored here). Both executions check their expected source identities before use:

```bash
SOURCES=$(mktemp -d)
curl -fL 'https://raw.githubusercontent.com/woahwhattheheck/commons/d422798850c2803484a2da2b77df3e515196bc74/research/adia-structural-break-realtime/detector.py' -o "$SOURCES/detector.py"
curl -fL 'https://raw.githubusercontent.com/crunchdao/competitions/5a24c2413122942eae97b6bad376ef0ec143ce22/competitions/structural-break-real-time/scoring/scoring.py' -o "$SOURCES/scoring.py"
python parity.py "$SOURCES/scoring.py"
python stress.py --detector "$SOURCES/detector.py" \
  --expected-sha256 1f4c94475e91fc76905b4ad0351d4391c35f7b20f1a1c26eba89ad828a386ae7 \
  --seed-start 20000 --seeds 64 --out /tmp/adia-baseline-new-run
```

The output directory must not exist. On success it contains complete trace JSON,
the expected case manifest, summary, and a `COMPLETE.json` file-hash manifest. Any
inference failure stops the run without a completion marker. Output scores are
never padded, dropped, or imputed. Timing includes reference construction, updates,
and case hashing; it is machine-dependent and is outside the deterministic core
report. Source binding covers the exact single detector file executed, not an
undeclared multi-file dependency bundle. Run only trusted self-contained source.

For a paired model comparison, add `--reference PATH --reference-sha256 SHA256`.
`--detector` is the candidate and `--reference` is the control; the reported sign
is candidate minus reference. `--bootstrap 500` is the default. Supply
`--class-name` or `--reference-class` when a class is not `OnlineBreakDetector`.
Choose and retain seed ranges before examining a candidate's results; tuning on
the final panel is not held-out evidence.

The core report can be checked against a newly regenerated, expected corpus:

```python
import json
from evaluation import Trace, verify_report
from stress import corpus
root = "/tmp/adia-baseline-new-run/"
with open(root + "candidate_traces.json") as f:
    traces = [Trace.from_record(row) for row in json.load(f)]
with open(root + "summary.json") as f:
    saved = json.load(f)
valid = verify_report(
    saved["candidate"]["report"], traces,
    candidate_sha256="1f4c94475e91fc76905b4ad0351d4391c35f7b20f1a1c26eba89ad828a386ae7",
    case_manifest=[case.manifest() for case in corpus(20000, 64)],
)
if not valid:
    raise SystemExit("report does not reproduce")
```

## Retained measured result

`measured_report.json` retains the 64-seed local baseline diagnostic, exact source
and harness hashes, parity receipt, and test commands. There are 1,152 series,
383,040 online predictions, and 34,543,616 comparable positive-negative pairs.
Synthetic TS-AUC is **0.8395384258555908**. At threshold 0.5, false alarms occur on
**36/64 AR nulls**, **20/64 GARCH nulls**, and **2/64 heavy-tail nulls**, versus
**0/64 independent Gaussian, outlier-contaminated, and seasonal nulls**.

Those are distribution-sensitive weaknesses worth repairing, not proof that the
old engineering smoke is false. The original 32-seed independent-noise smoke and
this broader panel ask different questions. All conditional median delays are
reported alongside hit counts and pre-break false alarms; undetected series are
not disguised as fast detections. Per-change TS-AUC is against all six declared
null families and is descriptive, not an independently selected metric.

Validation at publication: **46/46 normal and 46/46 optimized tests**, plus
**128/128 exact public-function parity panels with maximum absolute error 0.0**.
The report is local synthetic diagnostic evidence only. Raw traces are regenerated
by the command above, not represented as organizer or restricted participant data.
