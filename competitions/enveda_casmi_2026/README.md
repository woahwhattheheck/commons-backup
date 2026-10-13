# Enveda CASMI 2026 internal workbench

This carrier starts useful competition research **without pretending we have accepted or retained competition-specific rules**.

Current public facts retained on 2026-09-16:

- Kaggle lists **Enveda CASMI 2026 - Molecule ID From Mass Spectra**, predicting 2D molecular structures from complex biological-extract mass spectra, with an advertised **$50,000** prize pool.
- Kaggle's official announcement says the task uses LC-MS/MS spectra to generate SMILES and advertises an **entry deadline of 2026-12-07**.
- Enveda's public announcement says the challenge is open through **2026-12-14**. This is retained as a host announcement, not promoted to competition-rules authority.
- Competition-specific evaluation metric, eligibility, team rules, data license, external-data policy, submission format/frequency, and code/notebook requirements are **UNKNOWN** in this generation.
- Kaggle's platform documentation says competition data access/submission can require rule acceptance. This carrier does not cross that owner/account boundary.

Therefore the machine state is intentionally:

`GO_RESEARCH_INTERNAL / HOLD_RULES_SOURCE`

## Executable baseline

`workbench.py` provides a deterministic, dependency-free spectral-library retrieval baseline: precursor-mass proximity plus fragment-spectrum cosine matching. The committed fixture is synthetic; its `top1_accuracy` and `mean_reciprocal_rank` are labeled **LOCAL_DIAGNOSTIC...NOT_KAGGLE_METRIC**. The baseline does not claim leaderboard relevance.

```bash
python competitions/enveda_casmi_2026/workbench.py baseline \
  competitions/enveda_casmi_2026/synthetic_fixture.json

python competitions/enveda_casmi_2026/workbench.py compile \
  competitions/enveda_casmi_2026/competition_sources.json \
  competitions/enveda_casmi_2026/synthetic_fixture.json \
  /tmp/casmi-report.json

python competitions/enveda_casmi_2026/workbench.py verify /tmp/casmi-report.json
```

The compiler embeds its source generation and experiment fixture in a deterministic receipt. `experiment_ledger.json` durably records the synthetic smoke test, while `submission_checklist.json` keeps every rule/account/submission prerequisite machine-readable and held. Verification reconstructs the report, so editing `submission_state` and recomputing a plain SHA-256 still fails.

## Next experiment sequence

1. Owner-access the competition page and accept rules only if Bryce chooses to participate.
2. Pin the competition-specific Rules/Data/Overview bytes and replace this source generation; do not paraphrase unknowns into facts.
3. Confirm evaluation metric, eligibility, team/merge rules, license, external-data policy, submission schema/frequency, and any notebook-only constraints.
4. Only then adapt the baseline parser to the real allowed data schema and choose a validation split that mirrors the competition objective.
5. Candidate technical upgrades after source unlock: precursor/formula constraints, neutral-loss features, spectral transformers/embeddings, retrieval from allowed reference libraries, structure-generation/re-ranking, and ensemble calibration. Each experiment must retain data provenance and keep local validation separate from Kaggle score.

## Authority ceiling

This code cannot sign in to Kaggle, join the competition, accept rules, change a team, download gated competition data, submit, contact organizers, assert eligibility, claim a prize, or recognize revenue. The $50,000 figure is an advertised pool, not expected value or earned revenue.
