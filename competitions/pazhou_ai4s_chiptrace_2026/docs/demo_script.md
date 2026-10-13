# ChipTrace demo script — target 4 minutes

## 0:00–0:30 — Problem

“Organ-on-chip AI can only be as trustworthy as the experiment it interprets. A run can look plausible while a sensor shifted, samples went missing, one replicate diverged, or cross-sensor structure changed. ChipTrace is a research-QC layer that makes those failure modes explicit before downstream biological interpretation.”

Show the repository tree and the eight-column CSV contract.

## 0:30–1:05 — Reproducible one-command demo

Run:

```bash
python competitions/pazhou_ai4s_chiptrace_2026/chiptrace.py demo --directory /tmp/chiptrace-demo
```

Point out that no package install, model download, API key, network access, or private data is required. Open `/tmp/chiptrace-demo/report.html`.

## 1:05–2:05 — Explain the evidence

Show the three channel rows.

- `barrier_index`: second-half level shift and replicate divergence.
- `oxygen_index`: progressive drift and structural change.
- `flow_index`: a deliberately elevated replicate and cross-sensor correlation change.

Explain that ChipTrace also measures cadence-derived missingness and robust outlier fraction. Emphasize that every reason is surfaced; there is no opaque “AI says bad” label.

## 2:05–2:45 — Trust and uncertainty

Show the report disclaimer and state semantics.

“SUPPORTED means only that configured QC thresholds were not exceeded. It does not mean a drug works, an assay is clinically valid, or a treatment is safe. Sparse evidence returns INSUFFICIENT_EVIDENCE instead of a false pass.”

Mention that unknown input columns are rejected so the public carrier does not casually ingest patient identity fields.

## 2:45–3:25 — Replay receipt

Copy the report receipt:

`88233f2735ea76f7e90f68c05b0ee65ead47c97a221c268af02e8222ef06bb32`

Run:

```bash
python competitions/pazhou_ai4s_chiptrace_2026/chiptrace.py verify /tmp/chiptrace-demo/report.json
```

Show `PASS`. Explain that the report contains exact SHA-256 hashes of baseline and candidate files, so data/report changes create different evidence.

## 3:25–4:00 — Value and extension path

“ChipTrace is an upstream gate. A lab can first establish that a run is comparable and internally coherent, then hand it to assay-specific phenotype, toxicity, dose-response, or digital-twin models. The next scientific step is threshold calibration on legitimately licensed OoC QC annotations, followed by optional image/video feature adapters that preserve the same evidence contract.”

End on the public source, technical report, and static HTML demo.
