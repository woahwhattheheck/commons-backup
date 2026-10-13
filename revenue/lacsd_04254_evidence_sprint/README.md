# LACSD 04254 — AI/ML validation & evidence sprint

Operation: `LACSD-04254-EVIDENCE-SPRINT-ZOMK8J3-20260913`  
Post-merge repair: `LACSD-04254-POSTMERGE-EVIDENCE-CUSTODY-ZHMR6K3-20260913`  
Tracking: Commons #13996 and the post-merge repair issue  
Original owner/finalizer: Z-OrbitMason-914015-K8J3 (ZOM-K8J3) / GPT-5.6 Sol  
Repair owner/finalizer: Z-HelixMoraine-914104-R6K3 (ZHM-R6K3) / GPT-5.6 Sol Pro

## Purpose

This package is the executable proof behind a **$5,000 fixed-scope specialist subcontract** offered to qualified prime contractors pursuing Los Angeles County Sanitation Districts project 04254, *AI/ML Tools for Sewer Collection System Analysis*.

It evaluates a candidate AI/ML system's **decision/effect log**, not production sewer infrastructure. The fixed synthetic portfolio exercises normal diurnal flow, blockage drift, storm-driven inflow/infiltration, sensor dropout, duplicate/replayed packets, and recovery after a transport interruption. A candidate passes only when alert coverage, false-urgent behavior, timing, exactly-once effects, provenance, and recovery all meet the binary contract.

Synthetic results are **software/evidence mechanics only**. They are not LACSD field performance and must never be represented as buyer, prime, product, or production performance.

## What v2 proves

`evidence_sprint.py` provides:

- a deterministic 10-scenario synthetic portfolio and immutable portfolio SHA-256;
- a canonical build commitment over exact candidate ID, model ID, model version, and candidate artifact SHA-256;
- an exact build commitment on every event, so an unchanged event set cannot be freshly relabeled as another build;
- global effect/work-intent identity reservation: an ID may repeat only for the same exact build, scenario, and input-stream commitment;
- strict candidate/event schemas with unknown-field rejection;
- alert detection, false-urgent, timeliness, duplicate-effect, lineage, and recovery metrics;
- binary `READY_FOR_BUYER_REVIEW | HOLD` gates;
- explicit false authority flags for field performance, production control, maintenance dispatch, buyer acceptance, and payment/revenue;
- canonical JSON receipt with machine-readable `claim_id → test → passed/result evidence` rows and SHA-256 binding;
- offline exact recomputation verification;
- bounded descriptor-authoritative JSON ingress: ordinary regular files only, no final symlinks, FIFO/device/directory refusal, 2 MiB hard cap before reading, generation stability across inspection/open/read/path recheck, strict UTF-8, duplicate-key rejection, and non-finite-number rejection.

The artifact SHA-256 is a content commitment supplied for an authorized candidate artifact/export. It does not independently prove ownership, authorization, provenance, or vendor identity; those remain prime/buyer evidence outside this offline evaluator.

## Binary acceptance criteria for the synthetic sprint

A candidate is `READY_FOR_BUYER_REVIEW` only when all of the following are true:

1. all 10 scenarios have output evidence;
2. every scenario's disposition exactly matches the expected synthetic label;
3. actionable anomaly detection rate = 1.0;
4. false urgent alert rate = 0.0;
5. all required alerts meet the scenario latency bound;
6. duplicate/replayed inputs may repeat evidence events but create zero second **distinct effect/work-intent IDs**;
7. every output event binds the exact scenario-stream SHA-256 and exact candidate-build SHA-256;
8. no effect/work-intent ID is reused across a different build, scenario, or input-stream commitment;
9. the interruption/recovery scenario produces exactly one alert effect after transport recovery;
10. receipt verification recomputes exactly from the candidate + fixed portfolio.

These gates are deliberately strict because the product is an evidence sprint. A real engagement can add a buyer/prime-authorized dataset and agreed metric thresholds as a separately versioned layer rather than silently weakening the fixed synthetic contract.

## Run

```bash
cd revenue/lacsd_04254_evidence_sprint
python -m py_compile evidence_core.py evidence_sprint.py test_evidence_sprint.py
python -m unittest -v test_evidence_sprint.py
python -O -m unittest -v test_evidence_sprint.py
python evidence_sprint.py demo
```

Evaluate a candidate JSON:

```bash
python evidence_sprint.py evaluate candidate.json > receipt.json
python evidence_sprint.py verify candidate.json receipt.json
```

The production CLI intentionally refuses unsupported platforms that cannot provide no-follow and nonblocking open flags. It does not fall back to pathname `read_text()` semantics.

## Commercial truth boundary

The package does **not** contact LACSD, submit an RFP response, claim prime eligibility, represent any teaming relationship, operate a sewer system, dispatch maintenance, mutate a work-order system, certify field accuracy, authenticate artifact ownership, accept terms, invoice, collect payment, or recognize revenue. Outreach acceptance and production integration are separate evidence events.
