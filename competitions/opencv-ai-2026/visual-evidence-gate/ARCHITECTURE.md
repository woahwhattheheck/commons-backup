# Architecture and AWS deployment boundary

## Offline reference flow

1. **Synthetic/right-cleared image** — exact BGR bytes are SHA-256 bound with dimensions.
2. **OpenCV perception** — HSV conversion, red masks, morphology, contours, moments, pixel counts.
3. **Evidence object** — detector generation, scene digest, dimensions, observation time, measurements, visual class, runtime OpenCV version, canonical evidence digest.
4. **Policy** — validates exact evidence shape, generation, digest and freshness before selecting a later advisory tool plan.
5. **Human control** — center hazards and unsafe/unknown action classes force `HUMAN_APPROVAL_REQUIRED`; malformed/missing/stale evidence forces `HOLD_EVIDENCE`.
6. **Trace receipt** — binds perception, decision, authority ceiling, runtime truth and final trace digest.

## Meaningful AWS target (not deployed by this source)

`S3 / judge upload → Lambda (aws_lambda.handler + OpenCV 5) → Step Functions decision state → optional callback-token human approval → S3/DynamoDB receipt retention → CloudWatch observability`

Suggested controls for an authorized deployment:

- immutable input-object version/digest binding;
- least-privilege Lambda execution role;
- bounded payload size and timeouts;
- structured CloudWatch logs keyed by trace digest, without raw private imagery by default;
- Step Functions callback-token path for human approval rather than direct actuation;
- explicit retention/deletion policy for images and receipts;
- alarms for decode failures, stale evidence, HOLD rate and error rate;
- pinned OpenCV 5 dependency/container digest and reproducible deployment manifest.

`aws_lambda.py` supplies the pure handler boundary but does not create AWS resources, credentials, costs, deployment evidence, or a public endpoint.
