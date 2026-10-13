# DHS Ready, Set...ID — defensive competition carrier

Owner/finalizer: `Z-OrbitMason-914015-K8J3 (ZOM-K8J3) / GPT-5.6 Sol`  
Claim: `DHS-READY-SET-ID-BIOTHREAT-ZOMK8J3-20260913`  
Tracking: Commons issue #13934

## Why this exists

DHS S&T opened **Ready, Set...ID the Biothreat**, an AI-assisted algorithmic biodetection prize challenge. The public USAGov listing says the challenge opened 2026-09-08, closes **2026-10-14 12:00 PM ET**, runs in three stages, and has **$999,990 total cash prizes**. DHS public press material describes the objective as computational AI/ML that identifies potential biological threat signals in complex environmental metagenomic data, separates suspicious signal from benign environmental background, and returns explainable confidence-scored output for follow-on analysis.

This directory is a **pursuit and software-readiness carrier**, not a submission and not a claim of biological performance.

## Public-source truth ledger

| Field | Status | Public evidence |
|---|---|---|
| Sponsor | VERIFIED | U.S. Department of Homeland Security, Science & Technology Directorate |
| Challenge | VERIFIED | Ready, Set...ID the Biothreat |
| Start | VERIFIED | 2026-09-08 09:30 ET |
| Submission deadline | VERIFIED | 2026-10-14 12:00 ET |
| Total cash prizes | VERIFIED | $999,990 |
| Stages | VERIFIED | Three stages; DHS press describes proposal evaluation, prototype development/testing, final blinded validation |
| Individual eligibility | PUBLIC-PRESS-VERIFIED | U.S. citizen or legal permanent resident, age 18+ at submission |
| Entity eligibility | PUBLIC-PRESS-VERIFIED | U.S.-incorporated legal entity with primary place of business in the U.S. |
| Existing core IP | PUBLIC-PRESS-VERIFIED | Participants retain existing core IP, subject to full rules |
| Exact stage prize allocation | **UNKNOWN** | Full rules required |
| Required submission fields/files | **UNKNOWN** | Full rules required |
| Registration account / portal status | **UNKNOWN / NOT CLAIMED** | No portal action performed by this carrier |
| User/team eligibility | **UNKNOWN / NOT CLAIMED** | Must be verified against full rules before submission |
| Any submission/finalist/award/payment/revenue | **NO / NOT CLAIMED** | No such action or event has occurred in this carrier |

Public sources accessed 2026-09-13:

- USAGov active challenge listing: `https://www.usa.gov/challenges/ready-set-id-biothreat`
- DHS S&T public news release (2026-09-09): `https://www.dhs.gov/science-and-technology/news/2026/09/09/st-launches-prize-challenge-advance-ai-assisted-biodetection`
- DHS challenge landing page named by USAGov: `https://www.dhs.gov/science-and-technology/ready-set-id-bio-threat` (research fetch path returned HTTP 403; do **not** infer missing rules)

## Safety and authority boundary

The code here is defensive anomaly triage over **abstract numerical feature vectors**. It contains no organisms, sequences, pathogen targets, culture conditions, synthesis instructions, threat construction, or wet-lab procedures. It does not fetch data, access networks, execute subprocesses, or contact DHS.

The carrier may support a future eligible competition submission only after the full rules, dataset terms, evaluation metric, portal requirements, and entrant eligibility are independently verified. Nothing here authorizes registration, contact, signature, submission, award acceptance, accounting, cash, or revenue claims.

## Implemented software

`detector.py` provides a deterministic stdlib-only robust background model:

- strict finite-number and exact-feature validation;
- median/MAD reference estimation with a deterministic zero-variance floor;
- bounded anomaly risk score based on the strongest standardized deviations;
- confidence, threshold, per-feature explanations, and SHA-256 provenance bindings;
- fail-closed dataset-manifest validation;
- zero network and zero process side effects.

`synthetic_eval.py` supplies a deterministic **abstract** distribution-shift fixture for software testing. Its metrics are never challenge metrics and must not be represented as biodetection performance.

## Run

```bash
cd competitions/dhs_ready_set_id
python -m unittest -v test_detector.py
python synthetic_eval.py
```

## Next-gate checklist before a real submission

1. Acquire and archive the complete DHS rules/terms through an authorized browser/session.
2. Verify entrant/team eligibility and registration mechanics.
3. Record exact Phase 1 deliverables, page/word limits, scoring rubric, required forms, IP/data terms, and stage-by-stage prize allocation.
4. Obtain the authorized challenge dataset or data specification; bind immutable hashes/manifests.
5. Replace the abstract fixture with a rules-compliant evaluation pipeline while preserving a blind holdout and deterministic provenance.
6. Add domain-expert review for biological validity and safety. The current kernel is intentionally domain-agnostic.
7. Report actual benchmark results with confidence intervals and failure cases. Never transplant synthetic fixture numbers into a proposal.
8. Only then prepare portal-ready submission material, subject to explicit owner authority for any external action.
