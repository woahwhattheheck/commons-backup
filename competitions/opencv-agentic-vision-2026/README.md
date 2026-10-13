# ProofLens — evidence-first agentic vision

Competition carrier for the **OpenCV AI Competition 2026, powered by AWS**.

ProofLens is a narrow visual-inspection agent: OpenCV 5 compares a retained baseline frame with a current frame, emits a deterministic evidence packet, and a policy engine chooses one of four bounded outcomes: `NO_ACTION`, `HOLD_LOW_QUALITY`, `REQUEST_HUMAN_REVIEW`, or `REPLAY_IGNORED`. Visual evidence may create a review request, but this source never authorizes a purchase, shutdown, safety declaration, disciplinary action, or other high-authority external action.

Official references:
- https://opencv26.devpost.com/
- https://opencv26.devpost.com/rules
- https://opencv.org/opencv-launches-ai-competition-powered-by-amazon-web-services/

The published competition requires substantive OpenCV 5 image/video analysis plus a meaningful AWS component. The final project deadline is October 26, 2026. The organizer currently lists overall cash awards of $5,000 / $3,000 / $2,000 and separate $1,000 Agentic Vision and $1,000 COOL awards. Those are competitive prizes, **not revenue received**.

## Why this is agentic instead of “vision + chatbot”

The perception result changes the next system action:

1. `opencv_perception.py` decodes and validates two images with OpenCV 5.
2. ORB feature matching + RANSAC homography attempt to normalize ordinary camera movement.
3. The aligned frames produce bounded change metrics: changed-pixel fraction, mean absolute delta, edge-map delta, and quality/alignment confidence.
4. `prooflens.py` validates the evidence identity and applies a versioned policy.
5. `aws_agent.py` records the exact evidence/decision receipt. Only `REQUEST_HUMAN_REVIEW` creates an SQS review message. Raw images are not placed on the queue.
6. A replayed event is recovered from DynamoDB instead of creating a second review request.

The system does **not** identify people or objects and does not infer intent, blame, hazard severity, compliance, or safety. A threshold crossing means only “this pair deserves human inspection under this declared policy.”

## Source layout

- `prooflens.py` — strict evidence schema, canonical hashing, replay-aware decision state machine.
- `opencv_perception.py` — OpenCV 5 pair analysis and deterministic image-derived evidence.
- `aws_agent.py` — AWS Lambda orchestration using S3, DynamoDB, and FIFO SQS.
- `template.yaml` — SAM deployment scaffold with least-purpose resources.
- `tests/test_prooflens.py` — pure-Python authority/replay/tamper tests.
- `tests/test_opencv_perception.py` — synthetic OpenCV tests for deterministic change evidence.
- `submission_readiness.json` / `validate_readiness.py` — fail-closed release gate for external competition claims/actions.

## Local contract

```bash
cd competitions/opencv-agentic-vision-2026
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m py_compile prooflens.py opencv_perception.py aws_agent.py validate_readiness.py
python validate_readiness.py submission_readiness.json
```

`validate_readiness.py` is expected to exit non-zero in the checked-in state. That is deliberate: this repository does not contain proof of an AWS deployment, measured held-out evaluation, a final demo video, accepted Devpost terms, a verified team bio, or final submission authorization.

## Perception contract

The adapter rejects malformed/non-image bytes, very small frames, incompatible aspect ratios, and non-OpenCV-5 runtimes. It scales each pair to a bounded working size and computes frame-quality evidence before decisioning. ORB/RANSAC alignment is attempted when enough stable features exist; lack of a trustworthy alignment reduces quality instead of being hidden.

The evidence packet binds:
- baseline and current SHA-256;
- source reference supplied by the AWS/object layer;
- original dimensions;
- changed fraction, edge delta, mean delta;
- frame-quality and alignment confidence;
- OpenCV version and algorithm version;
- deterministic `event_id` over the exact semantic payload.

`prooflens.py` rejects unknown evidence keys, booleans masquerading as numbers, NaN/Inf, out-of-range fractions, impossible dimensions, unsupported algorithm versions, and any mismatched event ID.

## AWS contract

`template.yaml` provisions a private encrypted versioned S3 image bucket, DynamoDB evidence table, FIFO human-review queue, and Lambda triggered only by `current/` object creation. There is no public HTTP ingestion endpoint in this carrier.

Each S3 event must name the exact current object `versionId`. That current object must carry `baseline-version-id` metadata naming the exact retained `baseline/<same-suffix>` object generation. The Lambda reads both exact versions, analyzes the pair, records a canonical evidence/decision receipt, and queues only review metadata when the policy returns `REQUEST_HUMAN_REVIEW`.

DynamoDB is the durable replay and delivery-state fence. An existing event returns its retained receipt; if a prior review event reached durable `RECORDED` state but queue delivery was interrupted, a retry repairs that delivery rather than creating a new semantic event. Queue messages use the deterministic event ID as FIFO deduplication identity; consumers should preserve event ID as their own durable idempotency key because SQS FIFO deduplication has a finite time window.

This scaffold has **not** been deployed from this lane and no AWS spend is claimed.

## Evaluation plan

Before a final entry, use a right-cleared held-out set with at least these slices:
- no meaningful scene change with ordinary camera jitter;
- illumination/exposure changes;
- blur/occlusion/underexposure that must HOLD;
- localized structural changes of several sizes;
- adversarial near-threshold cases;
- replayed events and repeated identical image pairs.

Report precision/recall for the *review-request decision*, abstention/HOLD rate, false-review rate under camera motion, event replay rate, Lambda cold/warm latency, and per-request AWS cost. Do not convert those measurements into a “safety accuracy” claim.

## Current truth boundary

Source implementation and tests can establish software behavior. They cannot establish deployment uptime, cloud cost, held-out accuracy, user impact, OpenCV/AWS organizer approval, competition eligibility, submission, ranking, prize, or payment. Those remain external evidence gates.
