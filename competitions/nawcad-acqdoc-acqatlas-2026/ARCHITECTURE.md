# Architecture and challenge-criteria mapping

## Pipeline

1. **Ingest extracted text** from a controlled IL4-side ETL adapter. The public baseline accepts JSONL/JSON/CSV only.
2. **Normalize + featurize** deterministic unigrams and adjacent phrase bigrams.
3. **Weight** features with corpus-local sublinear TF-IDF.
4. **Score similarity** with 82% sparse cosine + 18% weighted token Jaccard.
5. **Cluster** requirements via thresholded similarity graph and canonical union-find roots.
6. **Calibrate threshold** on authorized training data; the synthetic fixture uses 0.18, with strongest cross-domain edge ~0.091. This threshold is not a sponsor-data claim.
7. **Recommend vehicles** from labeled neighbors, aggregating squared similarity with diminishing returns so near-duplicate documents cannot completely dominate one vehicle.
8. **Validate** with leave-one-out top-1/top-5 metrics and sponsor-provided acceptable-label sets when available.
9. **Visualize** clusters and ranked candidates in a self-contained HTML report.
10. **Bind evidence** with canonical SHA-256 JSON receipts and repeated-run hashes.

## Published challenge criteria

- **Repeatability:** all ordering/tie breaks are explicit; repeated runs on identical bytes must yield the same analysis hash.
- **Replication:** core analysis is stateless. Sharding can be added by feature/partition with deterministic merge; do not claim replication points until container-scale tests prove identical output and improved wall time.
- **Compute:** standard-library sparse structures and no model inference are intended to fit the challenge's lowest compute tier on realistic document counts, but only measured GFI/container evidence can claim that score.
- **LLM cost:** core uses no LLM and makes no network calls. Optional summarization should remain downstream and non-authoritative.
- **Validation:** top-k metrics are first-class and accept multiple valid vehicles per requirement.
- **30-minute runtime:** benchmark tooling reports wall time/RSS. Sponsor-scale evidence must be captured on the final container/hardware.

## IL4 deployment envelope

The core requires Python only at runtime. For a government cloud deployment:

- immutable container digest;
- read-only source/input mounts where practical;
- no outbound network route;
- approved document-extraction adapter writes normalized records to a content-addressed staging area;
- analysis emits content-addressed JSON/HTML artifacts plus execution receipt;
- no GFI, embeddings, or derived sensitive corpus statistics are committed to public source control.

## High-value next experiments

1. section-aware weighting for SOW/PWS headings and CDRLs;
2. deterministic BM25 vs TF-IDF ablation;
3. latent semantic projection using a vetted offline linear algebra package, if allowed, with fixed seed/solver;
4. vehicle catalog priors and ceiling/scope metadata;
5. cluster stability under bootstrap/document perturbation;
6. calibration of score-to-confidence on GFI train/validation splits;
7. MinHash candidate generation for scale while preserving exact reranking;
8. deterministic process-parallel pair scoring with canonical reduce.
