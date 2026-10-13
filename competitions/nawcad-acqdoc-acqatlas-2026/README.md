# AcqAtlas — deterministic acquisition-document recommender baseline

Candidate carrier for the 2026 **Advanced Acquisition Documentation Analysis Prize Challenge**. This repository slice is a public-data/synthetic engineering baseline only; it is not a claim of challenge registration, eligibility, GFI access, selection, score, prize, or revenue.

## Design target

The challenge asks for a reproducible system that groups heterogeneous acquisition requirements and returns strategic contract-vehicle candidates. Its published criteria strongly reward repeatability, low compute, low/zero LLM usage, Docker reproducibility, visualization, and measured validation. AcqAtlas makes those constraints first-class:

- deterministic TF-IDF + phrase features with fixed token normalization;
- multi-view document similarity (sparse cosine + weighted token Jaccard);
- deterministic similarity-graph clustering with canonical roots and a fixture-calibrated `0.18` default edge threshold;
- top-5 strategic-vehicle ranking from diverse labeled evidence;
- leave-one-out top-1 / top-5 validation;
- self-contained HTML visualization with escaped content;
- canonical SHA-bound JSON analysis receipts and benchmark receipts bound to a canonical document manifest + exact engine source;
- repeatability benchmark that runs identical bytes multiple times;
- standard-library-only runtime, zero network calls, zero LLM tokens;
- Docker image with an unprivileged runtime user.

The current fixture is **synthetic** and exists to exercise engineering contracts. Its measured strongest cross-domain edge is ~0.091 while a 0.18 threshold still connects each intended domain; that calibration is fixture evidence only and must be re-tuned on sponsor-authorized training data. Government Furnished Information (GFI) must not be copied into this public repository.

## Run

```bash
python3 -m unittest discover -s tests -v
python3 -O -m unittest discover -s tests -v
python3 acqatlas.py validate fixtures/synthetic_procurements.jsonl
python3 acqatlas.py benchmark fixtures/synthetic_procurements.jsonl --repeats 5 --output benchmark-receipt.json
python3 acqatlas.py verify-benchmark benchmark-receipt.json

# reconstruct the checked-in 500-document scale fixture manifest
python3 tools/generate_scale_fixture.py fixtures/synthetic_procurements.jsonl /tmp/acqatlas-scale.jsonl --batches 25
python3 acqatlas.py analyze fixtures/synthetic_procurements.jsonl --output analysis.json --html analysis.html
python3 acqatlas.py verify-analysis analysis.json
```

Container:

```bash
docker build -t acqatlas .
docker run --rm -v "$PWD:/work:rw" acqatlas analyze /work/fixtures/synthetic_procurements.jsonl --output /work/analysis.json --html /work/analysis.html
```

## Input contract

JSONL/JSON/CSV rows use:

- `doc_id` — required unique identifier;
- `title` — optional title;
- `text` — required extracted/plain text;
- `vehicle` — optional known strategic vehicle label used as training evidence;
- `acceptable_vehicles` — optional list (or pipe-separated CSV value) for validation where multiple answers are correct.

Raw PDF/Office extraction is intentionally outside the core model so extraction can be replaced with an approved IL4 ingestion service without changing analytical results. Phase-specific adapters should bind extracted-text hashes to source-document hashes.

## Truth boundary / challenge gating

A submission still requires the sponsor's pre-screening/eligibility process, access to the official GFI, official evaluation, Docker/resource validation, and any required in-person/demo materials. AcqAtlas should be measured against the GFI only in an approved private environment. Synthetic accuracy is not sponsor accuracy.

## Checked-in synthetic evidence

The `evidence/` directory is public synthetic evidence only:

- `synthetic-20-validation.json` — leave-one-out metrics over the 20-document fixture;
- `synthetic-20-benchmark.json` — five-run repeatability receipt bound to the exact engine source and canonical input manifest;
- `synthetic-500-benchmark.json` — two-run scale receipt. `tools/generate_scale_fixture.py --batches 25` reconstructs the 500-document manifest exactly from the public 20-document fixture.

The 500-document receipt measured 6.705956s and 7.1148s per full analysis, with ~132.8 MB Linux-interpreted peak RSS in the measurement runtime. These are engineering receipts, not sponsor hardware measurements or challenge scores.
