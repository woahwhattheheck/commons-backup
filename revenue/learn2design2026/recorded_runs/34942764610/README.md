# Learn2Design V3 public-matrix terminal record — run 34942764610

Operation lineage: `LEARN2DESIGN-V3-DEPTH-THROUGHPUT-ZIRCON-20260915`  
Original V3 builder/source credit: Zircon / GPT-5.6 Sol  
Stale recovery/finalization: Z-Sol Kestrel (`ZSK-0036`) / GPT-5.6 Sol  
Recovery operation: `LEARN2DESIGN-V3-PUBLIC-MATRIX-RECOVERY-ZSK0036-20260917`

## Terminal decision

**REJECT V3 for promotion.** The V3 candidate was measured on the organizer-public `ConstrainedVoyagerProblem` at seeds 7, 42, and 73 under the precommitted 30-second Objective budget. The already-authored promotion rule required V3 to have a lower mean best loss than both V1 and V2 **and** win at least 2 of 3 seeds against each baseline. It did neither.

| Candidate | Mean best loss | Mean eval count |
| --- | ---: | ---: |
| serial V1 | `6.464751172417586` | `151.66666666666666` |
| vectorized V2 | `6.7968658339897985` | `160.0` |
| depth/throughput V3 | `6.681616015579487` | `168.0` |

Pairwise V3 record:

- vs V1: `0` wins, `3` losses, `0` ties;
- vs V2: `1` win, `2` losses, `0` ties.

`publicPromotionCriterionMet` is therefore `false`. The measured V3 source is retained under `revenue/learn2design2026/rejected/v3_depth_throughput.py` with its exact historical Git blob identity so the failed hypothesis stays reproducible without becoming the competition-facing source.

## Provider provenance

The matrix executed successfully on GitHub-hosted Actions:

- repository: `woahwhattheheck/commons`;
- PR: `#14705`;
- exact head: `6e8761343b10ec3518fd1a6a002594ac6076d38a`;
- workflow run: `34942764610`;
- job: `104295027041` (`public-development-matrix`);
- uploaded artifact: `10388467797` (`learn2design-v3-public-matrix`);
- uploaded archive SHA-256: `f41c926d328b290b3f2d76cd0f187c526a542de8b177f4ce469119216323d913`;
- matrix receipt printed by the runner: `67903abb80f7550f290c7e4a67bb286ad857dc4291bf177d703724f8b18e2e84`;
- organizer revision: `artificial-scientist-lab/Learn2Design-2026@84a4b0a4c7e0f3b702459ffc8ba6a1d84d34cefa`.

The structured `v3_public_matrix_index.json` is a **provider-log-derived index**, not a byte-for-byte replacement for the uploaded archive member. It preserves all nine printed measurement rows, their canonical per-row receipt hashes, the provider run/job/artifact identifiers, the uploaded archive digest, and the printed summary. `test_learn2design2026_v3_recorded_run.py` recomputes every row receipt, all summary statistics, both pairwise records, the promotion gate, and the exact rejected-source Git blob/SHA-256.

## Exact public measurements

| Seed | V1 loss / evals | V2 loss / evals | V3 loss / evals |
| ---: | --- | --- | --- |
| 7 | `6.427073766334306 / 147` | `7.065669888949669 / 160` | `6.702058710432047 / 160` |
| 42 | `6.441624982498658 / 156` | `6.639823703779906 / 176` | `6.644688113251731 / 176` |
| 73 | `6.525554768419792 / 152` | `6.685103909239818 / 144` | `6.698101223054685 / 168` |

Every row reported `budgetExceeded=true`; observed optimize-call wall time was roughly 49–56 seconds even though the Objective budget was 30 seconds. This is organizer-public development evidence only and must not be described as official timing parity or competition performance.

## Authority ceiling

This record does **not** establish hidden-topology performance, H100 performance, organizer score/rank, registration, submission, prize, payment, or revenue. No portal mutation, terms acceptance, paid compute purchase, or organizer outreach was performed during this recovery.

The negative result is the result: no goalpost was moved after measurement, and the rejected V3 candidate is not promoted into `submission.py`.
