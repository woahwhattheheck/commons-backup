# ChipTrace — evidence-first organ-on-chip experiment intelligence

ChipTrace is a dependency-free research quality-control system for organ-on-chip (OoC) experiment streams. It compares a candidate run with an explicitly supplied baseline, detects multiple classes of quality drift, produces an uncertainty-aware `SUPPORTED | REVIEW | INSUFFICIENT_EVIDENCE` state for each channel, and binds the result to exact input bytes with a SHA-256 replay receipt.

**Important scope:** ChipTrace is experiment QC and research decision support. It does **not** diagnose disease, recommend treatment, establish drug efficacy or safety, or make patient-specific decisions. `SUPPORTED` means only that the configured QC review thresholds were not exceeded.

This carrier targets the 2026 Fifth Pazhou Algorithm Competition **AI + Organ-on-a-Chip: Open-ended Innovation Challenge for AI + Life Science**. The live organizer page describes an open innovation task accepting models, tools, agents, simulations, data-analysis pipelines, and experiment-assistance systems, with a Kaggle Writeup collecting public code, a demo video, and a technical report. Competition source: https://www.aicompetition-pz.com/topic_detail/26

## What is implemented

ChipTrace is deliberately small enough to audit and complete enough to demo:

- exact CSV contract for run / replicate / time / channel / value / unit / provenance / modality;
- fail-closed rejection of unknown columns, which prevents accidental ingestion of identity or clinical fields;
- robust baseline center and dispersion using median + MAD, with deterministic fallbacks;
- level-shift, within-run change-point, robust trend, outlier-fraction, cadence/missingness, replicate-divergence, and cross-sensor-correlation-shift evidence;
- explicit evidence-state semantics and uncertainty;
- unit and modality consistency gates;
- immutable hashes for baseline and candidate bytes;
- canonical JSON replay receipt and standalone receipt verification;
- deterministic synthetic OoC-style fixture with three sensor-feature channels and three replicates;
- self-contained judge-facing HTML report;
- technical report, Kaggle Writeup draft, and sub-five-minute demo script;
- hostile tests for tamper, identity-column ingestion, duplicate rows, unit mismatch, non-finite values, small samples, replay determinism, and report scope.

No network, model API, database, scientific Python package, or paid service is required.

## Quick start

From the Commons repository root:

```bash
python competitions/pazhou_ai4s_chiptrace_2026/chiptrace.py demo \
  --directory /tmp/chiptrace-demo

python competitions/pazhou_ai4s_chiptrace_2026/chiptrace.py verify \
  /tmp/chiptrace-demo/report.json
```

Expected demo state: `REVIEW`. The synthetic candidate deliberately contains a barrier-feature shift, oxygen drift, one cadence gap, replicate divergence, and changed cross-sensor structure.

Analyze your own **non-sensitive research** data:

```bash
python competitions/pazhou_ai4s_chiptrace_2026/chiptrace.py analyze \
  --baseline baseline.csv \
  --run candidate.csv \
  --out report.json \
  --html report.html
```

## Exact input contract

The header is intentionally exact:

```text
run_id,replicate_id,time_s,channel,value,unit,source,modality
```

Unknown columns are rejected. This is a feature, not an inconvenience: the competition allows public, owned, or synthetic research data, and this public carrier should not become an accidental route for patient names, MRNs, dates of birth, or other sensitive clinical identifiers.

Each observation key `(run_id, replicate_id, time_s, channel)` must be unique. Time and value must be finite numbers. A candidate channel must already exist in the baseline, and its unit and modality must match exactly.

## Evidence model

For each channel, ChipTrace builds a baseline envelope and computes:

1. **Level shift** — candidate median relative to robust baseline scale.
2. **Within-run change** — maximum first-half vs second-half median shift across replicates.
3. **Trend** — Theil–Sen slope normalized to one baseline sampling step.
4. **Outliers** — fraction of observations at least three robust scales from baseline center.
5. **Missingness** — missing expected cadence steps inferred from baseline timing.
6. **Replicate divergence** — spread of replicate medians relative to baseline scale.
7. **Cross-sensor shift** — change in aligned Pearson correlation structure versus baseline.

The composite `quality_risk_score` is deterministic and transparent. Hard review thresholds can trigger `REVIEW` even when the weighted score is below 25. Sparse data returns `INSUFFICIENT_EVIDENCE`, never a falsely reassuring pass.

The current thresholds are an auditable prototype policy, not universal biological constants. A real lab should calibrate them against its assay, device, sensor, sampling plan, and validated QC process.

## Demo receipt

The deterministic fixture currently yields:

- overall state: `REVIEW`;
- max quality-risk score: `69.869`;
- replay receipt: `88233f2735ea76f7e90f68c05b0ee65ead47c97a221c268af02e8222ef06bb32`.

The receipt binds the complete canonical report, which in turn includes hashes of the exact baseline and candidate input bytes. Editing either data or report content invalidates the evidence chain.

## Tests

```bash
python -m py_compile \
  competitions/pazhou_ai4s_chiptrace_2026/chiptrace.py \
  competitions/pazhou_ai4s_chiptrace_2026/tests/test_chiptrace.py

python -m unittest \
  competitions.pazhou_ai4s_chiptrace_2026.tests.test_chiptrace -v
```

The competition-scoped GitHub Actions workflow runs the same compile, hostile tests, deterministic demo, receipt verification, and independent twin-demo byte comparison on Python 3.11–3.13.


## Frozen benchmark and evidence-bound triage

`benchmark.py` evaluates the existing deterministic ChipTrace QC core on five frozen synthetic cases: clean, level shift, cadence gap, replicate divergence, and sparse evidence. The triage wrapper emits `SUPPORTED_QC`, `REVIEW`, or `ABSTAIN` and attaches JSON-pointer citations back to the exact report fields supporting the decision.

The benchmark reports precision, recall, F1, false-flag rate, sparse-case abstention accuracy, citation validity, repeat decision churn, and median/P95 execution latency. Its deterministic receipt excludes wall-clock timing so runner load does not change the evidence hash.

Accepted execution evidence on the merged exact bytes used CPython 3.13.5 and five frozen scenarios repeated three times (15 internal scenario executions, not 15 independent experiments): 14/14 focused tests passed; QC and triage precision/recall/F1 were 1.0/1.0/1.0; false-flag rate was 0; sparse abstention accuracy and citation validity were 1.0; decision churn was 0. The retained run measured 3.196900 ms median and 4.178909 ms P95/max, with deterministic receipt `bfbfbe949b15fa02e45dd5a6694d84709a3924d1e1cd5f9c6cc46e2c39cdb862`. These timings are runner-specific software measurements, not wet-lab, biological, or organizer scoring evidence.

This is a synthetic research-software QC benchmark floor, not biological or competition validation.

## Competition status and authority boundary

This repository carrier is source/test/demo/report readiness only. It does not assert Kaggle registration, terms acceptance, official submission, organizer validation, finalist status, score, ranking, prize, payment, or revenue. Any eventual competition action must preserve the event's current rules, data licenses, attribution requirements, and identity/entry requirements.

See `docs/technical_report.md`, `docs/kaggle_writeup.md`, and `docs/demo_script.md` for the judge-facing materials.
