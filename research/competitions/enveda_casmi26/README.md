# CASMI26 hybrid ranker R1

Performance-oriented baseline for **Enveda CASMI 2026**. This is not a submission and contains no competition data.

## Why this lane

The official task has ~2.5M training spectra but only ~400 test molecules. R1 avoids materializing a huge spectral index: compute the test molecules' neutral-mass windows first, then stream train once and immediately discard rows outside every query window. Only mass-plausible spectra proceed to spectral scoring.

Ranking is per molecule, not per spectrum. Multiple query spectra are aggregated and train hits are collapsed to unique `inchikey14` structures so optimization tracks MRR@25 rather than raw spectrum accuracy.

## R1 mechanics

- explicit neutral-mass conversion for all 10 official test adducts
- robust weighted-median mass across repeated spectra
- top-128/intensity-floor peak cleaning
- sparse fragment + neutral-loss cosine evidence
- exact-adduct preference without hard filtering
- Gaussian ppm consistency penalty
- best-spectrum + corroborating-spectrum structure score
- top-25 unique structure output
- query-conditioned single-pass train retention

The intended R2 extension is an offline public candidate database (COCONUT/PubChem) and learned spectrum→fingerprint ranker for the official class-2/3 novelty cases. R1 deliberately isolates the high-confidence library-retrieval path first.

## Local check

```bash
python casmi26_hybrid_ranker.py --selftest --benchmark
```

The synthetic benchmark is only a throughput/correctness smoke test; it is **not** a chemistry or leaderboard result.

## Kaggle integration shape

In the final notebook:

1. Load test rows and construct `Spectrum` objects grouped by `molecule_id`.
2. Call `group_queries()` to obtain robust neutral masses.
3. Stream `train.parquet` by Arrow record batches using only:
   `spectrum_id`, `precursor_mz`, `adduct`, `normalized_smiles`, `inchikey14`, `ms2_mzs`, `ms2_normalized_intensities`.
4. Yield each retained row into `retain_and_score_rows()` (or inline the batch loop for lower Python overhead).
5. Call `make_submission()` and write `submission.csv`.

For full-scale speed, the next implementation step should vectorize the neutral-mass window fence at the Arrow/Numpy batch level before converting the tiny retained subset to Python objects.

## R1 local throughput receipt

Current optimized core precomputes every query sparse vector and the sorted query-mass index once. On the authoring cloud seat's synthetic stress pass:

- 200,000 library spectra
- 400 query molecules, 3 spectra each
- 3,700 spectra retained by the 15 ppm query-conditioned mass fence (1.85%)
- 0.753 s scoring wall time
- ~265,700 input rows/s
- synthetic top-1 400/400

Again: this proves the retrieval/scoring plumbing and throughput shape only. It is not a CASMI validation or leaderboard score.

## Source

- Competition: https://www.kaggle.com/competitions/enveda-CASMI26-molecule-id-mass-spectra
- Data: https://www.kaggle.com/competitions/enveda-CASMI26-molecule-id-mass-spectra/data
