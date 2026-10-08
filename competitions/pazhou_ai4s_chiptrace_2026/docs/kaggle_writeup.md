# Kaggle Writeup draft — ChipTrace

**Category: Tool & Platform**

## Title

**ChipTrace: evidence-first multimodal drift intelligence for organ-on-chip experiments**

## One-sentence pitch

ChipTrace is a reproducible research-QC engine that tells an organ-on-chip team *why* a run may no longer be comparable to its baseline—across level, dynamics, sampling, replicates, and cross-sensor structure—and binds every finding to exact input bytes.

## Why this problem matters

AI for organ-on-chip should not begin with the most glamorous downstream prediction. It should begin by asking whether the experiment being interpreted is trustworthy enough to compare with its reference. OoC systems increasingly combine several time-varying modalities, and simple aggregation can hide sensor drift, missing samples, divergent replicates, or altered relationships between channels.

ChipTrace makes that precondition explicit. It is a narrow, inspectable layer that can sit before phenotype, dose-response, toxicity, digital-twin, or experiment-planning models.

## What we built

A dependency-free Python system with:

- strict non-sensitive experiment schema;
- robust median/MAD reference envelopes;
- seven independent quality signals: level shift, within-run change, trend, robust outliers, cadence missingness, replicate divergence, and cross-sensor correlation shift;
- transparent weighted risk plus hard evidence thresholds;
- `SUPPORTED`, `REVIEW`, and `INSUFFICIENT_EVIDENCE` states;
- explicit uncertainty;
- exact input hashes and a canonical SHA-256 replay receipt;
- a standalone HTML judge report;
- a deterministic synthetic demo and hostile tests.

The implementation uses only the Python standard library. A judge can clone the public repository and run the entire demo without network access, an API key, or package installation.

## Demo result

The synthetic candidate contains several deliberate experiment-quality faults. ChipTrace returns `REVIEW` with max quality-risk score `69.869`.

- `barrier_index`: level shift, within-run change, replicate divergence, elevated robust outliers.
- `oxygen_index`: within-run change, robust outliers, and changed cross-sensor structure.
- `flow_index`: replicate divergence, robust outliers, and changed cross-sensor structure.

The report receipt is:

`88233f2735ea76f7e90f68c05b0ee65ead47c97a221c268af02e8222ef06bb32`

That receipt verifies the complete canonical report, which includes SHA-256 hashes of the exact baseline and candidate inputs.

## Frozen benchmark evidence

The merged benchmark layer evaluates five frozen synthetic QC scenarios and repeats each scenario three times (15 internal scenario executions, not 15 independent experiments). On the accepted CPython 3.13.5 exact-byte run, 14/14 focused tests passed; QC and triage precision/recall/F1 were 1.0/1.0/1.0; false-flag rate was 0; sparse-case abstention accuracy and citation validity were 1.0; and decision churn was 0. The retained run measured 3.196900 ms median and 4.178909 ms P95/max, with deterministic receipt `bfbfbe949b15fa02e45dd5a6694d84709a3924d1e1cd5f9c6cc46e2c39cdb862`.

These are reproducible synthetic software-QC measurements, not independent biological experiments, wet-lab validation, an organizer score, or a prize claim.

## Technical novelty

ChipTrace's novelty is not a single exotic detector. It is the **evidence contract around multimodal experiment intelligence**:

1. separate quality evidence from biological interpretation;
2. fuse multiple interpretable drift modes instead of one opaque anomaly score;
3. fail closed when evidence is sparse;
4. protect the public pipeline from accidental identity/clinical-field ingestion;
5. make each result byte-replayable and tamper-evident.

This makes the system useful both as a standalone lab QC prototype and as a reliable upstream gate for more complex OoC AI.

## Trust, ethics, and limitations

ChipTrace is research QC only. It does not diagnose disease, recommend treatment, establish safety or efficacy, or make patient-specific decisions. The checked-in demo is synthetic and contains no sensitive data. Unknown input columns are rejected by design. Fixed thresholds are prototype policy that a real lab should calibrate against its assay and validated QC process.

## Reproduce

```bash
python competitions/pazhou_ai4s_chiptrace_2026/chiptrace.py demo --directory /tmp/chiptrace-demo
python competitions/pazhou_ai4s_chiptrace_2026/chiptrace.py verify /tmp/chiptrace-demo/report.json
```

## Public artifacts

- [Public source and reproduction instructions](https://github.com/woahwhattheheck/commons/tree/a3d2b0b6e80ee4200682e2509abf2f3051316305/competitions/pazhou_ai4s_chiptrace_2026).
- [Original merged implementation and retained validation record](https://github.com/woahwhattheheck/commons/pull/14412).
- [Standalone technical report](https://github.com/woahwhattheheck/commons/blob/a3d2b0b6e80ee4200682e2509abf2f3051316305/competitions/pazhou_ai4s_chiptrace_2026/docs/technical_report.md). Its complete text is included below so that the final Kaggle Writeup can carry the report directly.
- Demo video: an existing 2:56 H.264 recording has been retained by the publication operator. Its public attachment or hosting URL is still pending; this draft is not complete for submission until that accessible reference is inserted. Do not substitute the report receipt hash for a video checksum.
- Judge report: the reproduction command above generates `/tmp/chiptrace-demo/report.html`; open that file locally. It is generated output, not a checked-in public webpage.

## Source, data, and license

The linked repository carries an [Apache-2.0 license](https://github.com/woahwhattheheck/commons/blob/a3d2b0b6e80ee4200682e2509abf2f3051316305/LICENSE). Implementation provenance remains in the original merged pull request. The runtime uses the Python standard library, with no hosted model, API key, third-party package, or external dataset required for the included synthetic demonstration. The synthetic channels are illustrative research features and do not establish biological validation.

## Technical report

### Abstract

Organ-on-chip experiments can produce synchronized sensor traces, image-derived features, electrophysiology, device telemetry, and experimental metadata. Before those observations are interpreted biologically, researchers need to know whether a run is comparable to its baseline, whether replicates agree, whether sampling broke, and whether sensor relationships changed. ChipTrace is a lightweight, auditable quality-control layer for that problem. It consumes a strict non-sensitive research-data schema, learns robust baseline envelopes from explicit reference observations, computes seven interpretable drift and quality signals, and returns per-channel evidence states with uncertainty. Every report is bound to exact input bytes by SHA-256 and can be verified without rerunning the analysis. The implementation uses only the Python standard library so that reviewers can reproduce it without an environment build or model/API dependency.

ChipTrace is intentionally not a medical model. It does not infer diagnosis, clinical safety, treatment effect, or patient-specific outcomes. Its narrow claim is operational: it identifies evidence that a research experiment may need quality review before downstream interpretation.

### 1. Problem

OoC platforms are experimentally rich but operationally heterogeneous. A single run may include several replicates and multiple modalities sampled over time. Common failure modes can be mundane but consequential: a shifted sensor baseline, a transient state change, dropped samples, one divergent replicate, or a change in relationships between channels. If those defects are hidden inside an apparently plausible aggregate curve, downstream analysis can be confidently wrong.

A useful QC system should therefore satisfy five properties:

1. **Evidence before interpretation.** Quality findings must be connected to observable measurements, not a free-form model narrative.
2. **Multisignal detection.** No single statistic captures level drift, dynamics, timing loss, replicate disagreement, and cross-sensor structure.
3. **Fail-closed uncertainty.** Small samples should not be labelled healthy merely because no test has power.
4. **Replayability.** A reviewer should be able to identify the exact bytes and policy that produced a report.
5. **Privacy minimization.** A public competition demo should not normalize ingestion of clinical identity fields.

ChipTrace implements that layer as a transparent prototype.

### 2. Data contract and privacy boundary

Each CSV row has exactly eight fields:

`run_id, replicate_id, time_s, channel, value, unit, source, modality`.

Unknown columns are rejected. This blocks accidental addition of identity-bearing fields such as patient IDs, names, or medical-record numbers to the public pipeline. It also forces a candidate channel's unit and modality to match the baseline exactly. Duplicate observation keys, non-finite values, negative time, mixed baseline units, and candidate-only channels fail closed.

The included demo is fully synthetic. It uses dimensionless feature channels named `barrier_index`, `oxygen_index`, and `flow_index`; these are illustrative research features, not validated biological endpoints.

### 3. Robust baseline model

For channel values \(x_1,\ldots,x_n\), ChipTrace uses the median as center and scaled median absolute deviation as dispersion:

\[
\hat\mu = \operatorname{median}(x), \qquad
\hat\sigma = 1.4826\,\operatorname{median}|x-\hat\mu|.
\]

If MAD degenerates, the implementation falls back to population standard deviation, then a small magnitude-aware floor. The chosen scale method is emitted in the report so that a reviewer can see when a channel was nearly constant.

Sampling cadence is estimated from positive within-replicate timestamp differences. No timestamps are synthesized into the input data.

### 4. Evidence signals

For each candidate channel, seven signals are computed.

#### 4.1 Level shift

The candidate median is compared with the baseline center in robust-scale units. This detects an experiment that is consistently displaced from its reference envelope.

#### 4.2 Within-run change

For each replicate with at least four samples, ChipTrace compares the first-half and second-half medians. The largest normalized difference across replicates becomes the change-point evidence. This deliberately simple statistic is transparent and robust to isolated spikes.

#### 4.3 Robust trend

A Theil–Sen slope is computed from pairwise slopes and normalized to one baseline cadence step. For very long traces, deterministic regular subsampling bounds work while preserving reproducibility.

#### 4.4 Outlier fraction

The fraction of candidate observations at least three robust baseline scales from center captures repeated excursion rather than a single maximum.

#### 4.5 Cadence-derived missingness

Within each replicate, gaps are compared with baseline cadence. Near-integer multiples of the cadence imply missing expected samples. The report exposes the inferred missing fraction rather than silently interpolating observations.

#### 4.6 Replicate divergence

The spread of replicate medians, normalized by baseline scale, identifies disagreement hidden by pooled averaging.

#### 4.7 Cross-sensor structural shift

Channels aligned by `(replicate_id, time_s)` receive pairwise Pearson correlations when enough points exist. ChipTrace compares candidate and baseline correlations, exposing the largest absolute structural change associated with each channel. This can identify a sensor relationship that changed even when marginal centers remain plausible.

### 5. Evidence states and uncertainty

Signal severities are mapped to [0,1] and combined with fixed documented weights into a 0–100 quality-risk score. A channel returns `REVIEW` if the score is at least 25 or if any configured hard threshold is exceeded. A channel returns `INSUFFICIENT_EVIDENCE` when candidate or baseline sample counts are below configured minima. Otherwise it returns `SUPPORTED`.

`SUPPORTED` is deliberately defined as *no configured QC review threshold exceeded*. It does not imply biological efficacy, assay validity, clinical safety, or treatment suitability.

The report also carries a bounded uncertainty indicator driven by candidate count, baseline count, missingness, and degenerate baseline scale. The uncertainty is an audit signal, not a frequentist confidence interval.

### 6. Provenance and deterministic replay

The report records SHA-256 digests of the exact baseline and candidate files. The complete JSON payload is serialized canonically with sorted keys and compact separators; its SHA-256 becomes `receipt_sha256`. `chiptrace.py verify report.json` removes that field, canonicalizes the rest, and verifies the digest.

This creates a simple evidence chain:

`exact input bytes -> deterministic analysis -> canonical report -> receipt`.

A modified report fails verification. A modified input produces a different input digest and therefore a different receipt on re-analysis.

### 7. Synthetic demonstration

The deterministic demo creates three baseline replicates and three candidate replicates with three synchronized feature channels sampled every 300 seconds. The candidate deliberately introduces:

- a second-half downward shift in `barrier_index`;
- progressive drift in `oxygen_index`;
- a single cadence gap;
- one elevated `flow_index` replicate;
- changed cross-sensor correlation structure.

The current deterministic output returns overall `REVIEW`, max quality-risk score `69.869`, and receipt `88233f2735ea76f7e90f68c05b0ee65ead47c97a221c268af02e8222ef06bb32`. In the current report, all three channels warrant review for different observable reasons. This is useful for a judge demo because one run exercises all major evidence paths without hidden data or a remote service.

### 8. Validation

The test suite covers deterministic fixture generation, repeat analysis equality, receipt tamper detection, HTML scope disclosure, strict unknown-column rejection, duplicate-key rejection, unit mismatch rejection, insufficient-evidence behavior, non-finite-value rejection, cadence-gap observability, and JSON round-trip receipt verification.

The historical multi-Python path-scoped workflow is not present on current main. Current execution evidence is the focused merged-byte CPython 3.13.5 benchmark and test receipt above; no broader hosted matrix is claimed.

### 9. Scientific value and next experimental steps

ChipTrace's practical role is upstream of biological interpretation. A lab could use it as a reproducible gate before more specialized models: first establish that an experiment is sufficiently comparable and internally coherent, then pass the run to phenotype, toxicity, dose-response, or mechanistic models appropriate to the assay.

The most valuable next work would use legitimately licensed OoC data to calibrate thresholds and compare ChipTrace against known device/sampling failure annotations. A second extension would replace the fixed weighted score with a training-only calibration learned from labelled QC outcomes while retaining the same interpretable component evidence. A third would add image/video feature extractors behind the same contract, keeping raw images outside the core evidence engine.

### 10. Limitations

- Fixed thresholds are prototype policy and are not universal lab standards.
- Pearson structural checks measure association, not causality.
- Theil–Sen and median-split change evidence favor auditability over maximum statistical power.
- The synthetic demo demonstrates behavior, not biological validity.
- The tool does not model assay-specific mechanisms.
- The tool must not be used for clinical diagnosis, treatment, or patient-specific decisions.

### 11. Reproduction

```bash
python competitions/pazhou_ai4s_chiptrace_2026/chiptrace.py demo --directory /tmp/chiptrace-demo
python competitions/pazhou_ai4s_chiptrace_2026/chiptrace.py verify /tmp/chiptrace-demo/report.json
python -m unittest competitions.pazhou_ai4s_chiptrace_2026.tests.test_chiptrace -v
```

No third-party package, API key, network access, or private data is required.

## Competition-action note

This is a prepared draft, not a successfully submitted Kaggle Writeup. The source and report are public; the retained video still needs an accessible publication reference. Existing organizer registration, entrant eligibility, accepted terms and publication rights must be established through the original account custodian before any formal submission. The provider observation on October 4, 2026 is signed out, with no submission ID or non-draft acceptance receipt established. No account creation or agreement acceptance is represented by this document.
