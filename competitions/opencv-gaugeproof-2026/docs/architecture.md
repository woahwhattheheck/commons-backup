# Architecture and evidence contract

## Pipeline

`image bytes -> bounded decode/input checks -> OpenCV quality metrics -> dial geometry -> pointer angular signal -> declared calibration -> per-frame reading/refusal -> temporal reducer -> agentic disposition -> deterministic receipt + annotation hashes`

### Vision primitives

- `cv2.Laplacian(...).var()` supplies a blur/focus indicator.
- `cv2.HoughCircles` proposes dial geometry; candidate selection is constrained by in-frame geometry and sampled ring support.
- A dense radial projection samples only the inner dial, deliberately staying inside major tick marks. The strongest angular darkness peak is the pointer candidate; a separated second peak supplies an ambiguity ratio.
- Calibration is explicit and versionable data: clockwise image angles can cross zero by allowing the maximum calibration angle to exceed 360 degrees.

### Temporal evidence

One frame cannot silently dominate a sequence. The reducer records every frame disposition, requires a minimum number of accepted frames, limits rejected-frame fraction, and compares the range of accepted values against the calibrated instrument span. Large disagreement becomes `ESCALATE_HUMAN`, not an average that conceals disagreement.

### Receipt model

`gaugeproof.inspection/v1` binds:

- declared calibration;
- aggregate decision/reason/statistics;
- per-frame raw array-byte digest (including dtype/shape metadata);
- per-frame visual finding;
- deterministic PNG annotation digest;
- hard-false authority statements.

`receipt_sha256` is SHA-256 over canonical sorted compact JSON of the body. `verify_receipt()` is intentionally a **self-integrity verifier**, not a camera/site authenticity oracle. Source authenticity must come from a future trusted acquisition layer.

## Threat / failure model

Covered in source/tests:

- blur or excessive glare;
- incomplete/occluded dial ring;
- low-contrast or competing pointers;
- pointer outside declared calibrated sweep;
- frame-to-frame disagreement;
- non-finite/malformed calibration values;
- malformed/unbounded image shapes;
- receipt mutation;
- attempts to turn a receipt into equipment-control authority.

Not claimed solved:

- adversarial physical stickers or sophisticated spoofed video;
- instrument mechanical failure that still looks visually plausible;
- source camera authentication;
- camera intrinsic/extrinsic calibration in arbitrary perspective;
- digital instrument OCR;
- safe equipment control.

## AWS / Cloud Optimized OpenCV extension

The evidence contract is intentionally independent of runtime location. A competition deployment can fan frames out to AWS workers (and optionally benchmark Cloud Optimized OpenCV) and feed their deterministic per-frame findings into the same reducer. Cloud deployment must not grant new authority or relax refusal thresholds.
