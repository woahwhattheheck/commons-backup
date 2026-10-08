# ChipTrace: evidence-first multimodal drift intelligence for organ-on-chip experiments

## Abstract

Organ-on-chip experiments can produce synchronized sensor traces, image-derived features, electrophysiology, device telemetry, and experimental metadata. Before those observations are interpreted biologically, researchers need to know whether a run is comparable to its baseline, whether replicates agree, whether sampling broke, and whether sensor relationships changed. ChipTrace is a lightweight, auditable quality-control layer for that problem. It consumes a strict non-sensitive research-data schema, learns robust baseline envelopes from explicit reference observations, computes seven interpretable drift and quality signals, and returns per-channel evidence states with uncertainty. Every report is bound to exact input bytes by SHA-256 and can be verified without rerunning the analysis. The implementation uses only the Python standard library so that reviewers can reproduce it without an environment build or model/API dependency.

ChipTrace is intentionally not a medical model. It does not infer diagnosis, clinical safety, treatment effect, or patient-specific outcomes. Its narrow claim is operational: it identifies evidence that a research experiment may need quality review before downstream interpretation.

## 1. Problem

OoC platforms are experimentally rich but operationally heterogeneous. A single run may include several replicates and multiple modalities sampled over time. Common failure modes can be mundane but consequential: a shifted sensor baseline, a transient state change, dropped samples, one divergent replicate, or a change in relationships between channels. If those defects are hidden inside an apparently plausible aggregate curve, downstream analysis can be confidently wrong.

A useful QC system should therefore satisfy five properties:

1. **Evidence before interpretation.** Quality findings must be connected to observable measurements, not a free-form model narrative.
2. **Multisignal detection.** No single statistic captures level drift, dynamics, timing loss, replicate disagreement, and cross-sensor structure.
3. **Fail-closed uncertainty.** Small samples should not be labelled healthy merely because no test has power.
4. **Replayability.** A reviewer should be able to identify the exact bytes and policy that produced a report.
5. **Privacy minimization.** A public competition demo should not normalize ingestion of clinical identity fields.

ChipTrace implements that layer as a transparent prototype.

## 2. Data contract and privacy boundary

Each CSV row has exactly eight fields:

`run_id, replicate_id, time_s, channel, value, unit, source, modality`.

Unknown columns are rejected. This blocks accidental addition of identity-bearing fields such as patient IDs, names, or medical-record numbers to the public pipeline. It also forces a candidate channel's unit and modality to match the baseline exactly. Duplicate observation keys, non-finite values, negative time, mixed baseline units, and candidate-only channels fail closed.

The included demo is fully synthetic. It uses dimensionless feature channels named `barrier_index`, `oxygen_index`, and `flow_index`; these are illustrative research features, not validated biological endpoints.

## 3. Robust baseline model

For channel values \(x_1,\ldots,x_n\), ChipTrace uses the median as center and scaled median absolute deviation as dispersion:

\[
\hat\mu = \operatorname{median}(x), \qquad
\hat\sigma = 1.4826\,\operatorname{median}|x-\hat\mu|.
\]

If MAD degenerates, the implementation falls back to population standard deviation, then a small magnitude-aware floor. The chosen scale method is emitted in the report so that a reviewer can see when a channel was nearly constant.

Sampling cadence is estimated from positive within-replicate timestamp differences. No timestamps are synthesized into the input data.

## 4. Evidence signals

For each candidate channel, seven signals are computed.

### 4.1 Level shift

The candidate median is compared with the baseline center in robust-scale units. This detects an experiment that is consistently displaced from its reference envelope.

### 4.2 Within-run change

For each replicate with at least four samples, ChipTrace compares the first-half and second-half medians. The largest normalized difference across replicates becomes the change-point evidence. This deliberately simple statistic is transparent and robust to isolated spikes.

### 4.3 Robust trend

A Theil–Sen slope is computed from pairwise slopes and normalized to one baseline cadence step. For very long traces, deterministic regular subsampling bounds work while preserving reproducibility.

### 4.4 Outlier fraction

The fraction of candidate observations at least three robust baseline scales from center captures repeated excursion rather than a single maximum.

### 4.5 Cadence-derived missingness

Within each replicate, gaps are compared with baseline cadence. Near-integer multiples of the cadence imply missing expected samples. The report exposes the inferred missing fraction rather than silently interpolating observations.

### 4.6 Replicate divergence

The spread of replicate medians, normalized by baseline scale, identifies disagreement hidden by pooled averaging.

### 4.7 Cross-sensor structural shift

Channels aligned by `(replicate_id, time_s)` receive pairwise Pearson correlations when enough points exist. ChipTrace compares candidate and baseline correlations, exposing the largest absolute structural change associated with each channel. This can identify a sensor relationship that changed even when marginal centers remain plausible.

## 5. Evidence states and uncertainty

Signal severities are mapped to [0,1] and combined with fixed documented weights into a 0–100 quality-risk score. A channel returns `REVIEW` if the score is at least 25 or if any configured hard threshold is exceeded. A channel returns `INSUFFICIENT_EVIDENCE` when candidate or baseline sample counts are below configured minima. Otherwise it returns `SUPPORTED`.

`SUPPORTED` is deliberately defined as *no configured QC review threshold exceeded*. It does not imply biological efficacy, assay validity, clinical safety, or treatment suitability.

The report also carries a bounded uncertainty indicator driven by candidate count, baseline count, missingness, and degenerate baseline scale. The uncertainty is an audit signal, not a frequentist confidence interval.

## 6. Provenance and deterministic replay

The report records SHA-256 digests of the exact baseline and candidate files. The complete JSON payload is serialized canonically with sorted keys and compact separators; its SHA-256 becomes `receipt_sha256`. `chiptrace.py verify report.json` removes that field, canonicalizes the rest, and verifies the digest.

This creates a simple evidence chain:

`exact input bytes -> deterministic analysis -> canonical report -> receipt`.

A modified report fails verification. A modified input produces a different input digest and therefore a different receipt on re-analysis.

## 7. Synthetic demonstration

The deterministic demo creates three baseline replicates and three candidate replicates with three synchronized feature channels sampled every 300 seconds. The candidate deliberately introduces:

- a second-half downward shift in `barrier_index`;
- progressive drift in `oxygen_index`;
- a single cadence gap;
- one elevated `flow_index` replicate;
- changed cross-sensor correlation structure.

The current deterministic output returns overall `REVIEW`, max quality-risk score `69.869`, and receipt `88233f2735ea76f7e90f68c05b0ee65ead47c97a221c268af02e8222ef06bb32`. In the current report, all three channels warrant review for different observable reasons. This is useful for a judge demo because one run exercises all major evidence paths without hidden data or a remote service.

## 8. Validation

The test suite covers deterministic fixture generation, repeat analysis equality, receipt tamper detection, HTML scope disclosure, strict unknown-column rejection, duplicate-key rejection, unit mismatch rejection, insufficient-evidence behavior, non-finite-value rejection, cadence-gap observability, and JSON round-trip receipt verification.

A path-scoped CI workflow repeats compile, all tests, demo generation, receipt verification, and byte-for-byte comparison between two independently regenerated demo artifact sets on Python 3.11, 3.12, and 3.13.

## 9. Frozen synthetic benchmark evidence

The merged benchmark layer evaluates five deterministic synthetic QC scenarios—clean, level shift, cadence gap, replicate divergence, and sparse evidence—and wraps ChipTrace outputs in evidence-bound triage decisions with JSON-pointer citations. The accepted exact-byte execution used three repeats per scenario (15 internal scenario executions, not 15 independent experiments) on CPython 3.13.5. It passed 14/14 focused tests; QC and triage precision/recall/F1 were 1.0/1.0/1.0; false-flag rate was 0; sparse-case abstention accuracy and citation validity were 1.0; and decision churn was 0. The retained run measured 3.196900 ms median and 4.178909 ms P95/max, with deterministic receipt `bfbfbe949b15fa02e45dd5a6694d84709a3924d1e1cd5f9c6cc46e2c39cdb862`.

This is a bounded synthetic software-QC benchmark floor. It is not biological validation, a wet-lab result, an organizer score, or evidence of competition acceptance.

## 10. Scientific value and next experimental steps

ChipTrace's practical role is upstream of biological interpretation. A lab could use it as a reproducible gate before more specialized models: first establish that an experiment is sufficiently comparable and internally coherent, then pass the run to phenotype, toxicity, dose-response, or mechanistic models appropriate to the assay.

The most valuable next work would use legitimately licensed OoC data to calibrate thresholds and compare ChipTrace against known device/sampling failure annotations. A second extension would replace the fixed weighted score with a training-only calibration learned from labelled QC outcomes while retaining the same interpretable component evidence. A third would add image/video feature extractors behind the same contract, keeping raw images outside the core evidence engine.

## 11. Limitations

- Fixed thresholds are prototype policy and are not universal lab standards.
- Pearson structural checks measure association, not causality.
- Theil–Sen and median-split change evidence favor auditability over maximum statistical power.
- The synthetic demo demonstrates behavior, not biological validity.
- The tool does not model assay-specific mechanisms.
- The tool must not be used for clinical diagnosis, treatment, or patient-specific decisions.

## 12. Reproduction

```bash
python competitions/pazhou_ai4s_chiptrace_2026/chiptrace.py demo --directory /tmp/chiptrace-demo
python competitions/pazhou_ai4s_chiptrace_2026/chiptrace.py verify /tmp/chiptrace-demo/report.json
python -m unittest competitions.pazhou_ai4s_chiptrace_2026.tests.test_chiptrace -v
```

No third-party package, API key, network access, or private data is required.
