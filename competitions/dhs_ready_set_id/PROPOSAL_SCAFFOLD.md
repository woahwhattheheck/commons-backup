# Proposal scaffold — NOT A SUBMISSION

Status: engineering scaffold only. Registration, entrant eligibility, exact rules, submission format, and portal state are UNKNOWN until verified against the complete DHS terms.

## One-sentence concept

A deterministic, explainable, provenance-bound anomaly triage layer that learns benign environmental background from numerical feature tables, flags material distribution shifts for follow-on analysis, and reports confidence plus the strongest contributing features.

## Public-objective mapping

| Public DHS objective | Demonstrated now | Evidence / remaining gate |
|---|---|---|
| Distinguish signal from benign background | YES, software mechanism on abstract synthetic vectors | `detector.py`, `synthetic_eval.py`; challenge/domain validation still required |
| Explainable output | YES | ranked feature deviations with value/center/scale/z-score/direction |
| Confidence-scored output | YES | bounded risk score, learned threshold, distance-to-threshold confidence |
| Rapid / computational | YES at small synthetic scale | stdlib-only deterministic kernel; benchmark on authorized challenge scale still required |
| Known/novel/unknown biological threat detection | **NOT DEMONSTRATED** | requires authorized domain dataset, labels/evaluation design, and expert review |
| Blinded final validation readiness | PARTIAL | deterministic manifests/hashes and side-effect-free scorer exist; official interface UNKNOWN |

## Proposed technical path once rules/data are verified

1. Convert authorized challenge inputs into a documented, immutable numerical feature table **without changing the official evaluation target**.
2. Partition benign reference/calibration data and preserve a blind evaluation split.
3. Fit robust background references and calibrate thresholds only on allowed training/calibration data.
4. Score held-out samples, retain confidence and explanation output, and measure official challenge metrics exactly as specified.
5. Add an ensemble/domain model only if the rules and safety review permit it; keep the deterministic triage kernel as an auditable baseline/fallback.
6. Package a reproducible entry with hashes, versions, fixed seeds, resource envelope, failure analysis, and no hidden network dependency.

## Evidence we can truthfully claim today

- deterministic, reproducible abstract anomaly-scoring software exists;
- malformed or schema-drifted inputs fail closed;
- output binds model + sample + result through SHA-256 receipts;
- explanations identify strongest numerical deviations;
- synthetic background-vs-shift tests exercise detection and false-positive behavior;
- no biological or challenge-dataset performance has been measured yet.

## Statements prohibited until independently evidenced

Do not claim: official registration; verified eligibility; submitted entry; finalist status; award; payment; cash; revenue; challenge accuracy; biological threat coverage; zero false negatives; real-time production performance; DHS approval/endorsement; or any exact rule requirement not present in the archived official terms.
