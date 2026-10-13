# Competition report skeleton — Visual Evidence Gate

## Problem and users
Teams building visual agents need evidence that a perception result truly changed what the system did next, while failures and high-risk cases remain reviewable.

## Implemented prototype
A deterministic OpenCV perception pipeline measures a rights-clean synthetic red region and binds those measurements to an advisory policy. The visual class selects a different next inspection tool or requests human approval. Exact evidence and decisions are content-addressed in a trace receipt.

## Evaluation
The shipped synthetic suite covers clear, left, center and right visual states plus hostile malformed/stale/tampered evidence and unsafe requested action classes. Report synthetic results as evaluator/control-flow evidence only; do not describe them as natural-image accuracy or a live AWS benchmark.

## AWS architecture
Use the shipped Lambda-shaped handler as the OpenCV 5 inference boundary, with Step Functions for orchestration/human approval, S3/DynamoDB for retained evidence and CloudWatch for operational telemetry. The repository contains design/source only; deployment evidence is currently absent.

## Responsible operation
The prototype performs no identity inference and no physical actuation. It defaults to HOLD on untrusted/stale evidence and to human approval on unknown/physical action requests. A real deployment needs right-cleared task data, held-out evaluation, calibrated thresholds, privacy/retention controls, abuse analysis and documented human override.

## Current limitations / evidence gaps
- OpenCV 5 runtime execution: **not yet evidenced** in the retained local environment.
- AWS deployment and observability: **not yet evidenced**.
- Natural image/video performance: **not measured**.
- Devpost registration/submission: **not claimed**.
- Prize, payment, revenue: **not claimed**.

## Judge demo outline
1. Run clear synthetic scene → show `CAPTURE_NEXT_FRAME`.
2. Run left/right scenes → show different focused-inspection tool plan.
3. Run center scene → show human-approval path.
4. Tamper the evidence digest or make it stale → show `HOLD_EVIDENCE`.
5. Ask for a physical action class → show forced `HUMAN_APPROVAL_REQUIRED` and `physical_actuation_authorized=false`.
6. Show the Lambda handler and AWS target diagram, clearly separating source from deployed-runtime evidence.
