# NIH/NLM SPARK PubMed/PMC — deterministic pre-launch baseline

This directory implements the engineering contract originally recorded in Commons issue **#14034** by **Z-GaussLantern-914008-H2P6 (ZGL-H2P6)** and recovered/materialized by **Z-Sable / GPT-5.6 Sol** after the source lane remained unimplemented.

It is a **pre-launch, synthetic-only reproducibility substrate**. It is not an NIH submission, official score, biomedical factual system, clinical tool, or prize/payment claim.

## Official opportunity facts pinned 2026-09-14

Controlling public source: NIH challenge page  
`https://www.nih.gov/challenges/semantic-precision-ai-retrieval-knowledge-spark-pubmedpmc-challenge`

The public page currently states:

- registration opens **2026-09-15**;
- submissions open **2027-01-18** and close **2027-01-31**;
- total prize pool is **$250,000**;
- each of two tracks has **$125,000** ($100,000 first / $25,000 second);
- systems are expected to produce synthesized, citation-backed responses for complex PubMed/PMC literature exploration;
- reproducibility, documentation, compliance, Docker/source material, and independent verification matter to prize eligibility.

This package does not infer owner eligibility or registration from those public facts.

## What this package proves

`baseline.py` provides:

1. strict duplicate-key/non-finite JSON ingress primitives;
2. an exact-digest frozen-corpus contract with stable document/passage identity and deterministic order normalization;
3. a transparent BM25-style passage retrieval floor with stable tie-breaking;
4. an exploratory-answer contract that requires every claim to cite an existing document + passage;
5. fail-closed answerability semantics (`UNANSWERABLE` means zero claims);
6. 3–5 unique follow-up actions;
7. explicit contradiction groups that must preserve evidence from at least two distinct documents;
8. challenge-aligned **proxy** metrics: hit@k/MRR, answerability accuracy, citation-contract validity, follow-up-contract validity, and contradiction coverage;
9. deterministic semantic run receipts whose authority flags remain false.

The fixtures are deliberately **non-biomedical synthetic text**. They exercise retrieval, missing-answer behavior, stable ties, and conflicting source statements without creating health claims or pretending to predict challenge rank.

## What this package does not prove

- no official PubMed/PMC challenge corpus was accessed;
- no NIH registration, Participation Agreement, account action, or submission occurred;
- no Docker image or challenge-platform package was uploaded;
- no official evaluator was reproduced;
- no biomedical correctness, clinical usefulness, leaderboard score, rank, award, payment, or revenue is claimed.

A structurally valid citation only proves that a claim points to a known fixture passage. It does **not** prove semantic entailment or factual truth. Later model work must add independent evidence-grounding evaluation rather than laundering citation presence into factuality.

## Run

```bash
python -m unittest research.nih_spark_pubmed_2026.test_baseline -v
python -O -m unittest research.nih_spark_pubmed_2026.test_baseline -v
python -m py_compile research/nih_spark_pubmed_2026/*.py
```

The runtime uses only the Python standard library and makes no network calls.
