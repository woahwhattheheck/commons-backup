# Visual Evidence Gate — OpenCV AI Competition 2026 carrier

An offline-first Agentic Vision reference implementation: synthetic, rights-clean frames are measured with OpenCV; those measurements are bound into evidence; and the evidence changes a later advisory tool plan or forces human approval.

This is **not** a submission, registration, AWS deployment, camera integration, production actuator, surveillance product, benchmark on natural imagery, prize claim, or revenue claim.

## Agentic loop

`frame → OpenCV red-region perception → content-bound evidence → policy → next tool plan / HUMAN_APPROVAL → canonical trace receipt`

Synthetic cases intentionally produce different next steps:

- clear → `CAPTURE_NEXT_FRAME`
- left hazard → `INSPECT_LEFT_ZONE`
- right hazard → `INSPECT_RIGHT_ZONE`
- center hazard → `HUMAN_APPROVAL_REQUIRED / NO_ACTION`
- stale/malformed evidence → `HOLD_EVIDENCE / NO_ACTION`
- any unknown/physical requested action class → `HUMAN_APPROVAL_REQUIRED / NO_ACTION`

No branch ever authorizes physical actuation.

## OpenCV / competition truth

`visual_gate.py` executes OpenCV color conversion, thresholding, morphology, contour extraction, moments, and exact-pixel measurement. The retained build environment currently reports OpenCV 4.x, so `opencv5_execution_evidenced` remains false. A future competition runtime must execute and retain proof on OpenCV 5; this source does not promote a 4.x test into OpenCV-5 evidence.

The current public competition requires substantive OpenCV 5 image/video analysis and a meaningful AWS component. `aws_lambda.py` is a Lambda-shaped adapter for the same deterministic gate. It performs no provider calls itself and records `deployment_evidenced=false`; deployment, CloudWatch, and orchestration evidence must come from a real authorized AWS run.

## Quickstart

The additive [multi-photo packet extension](PACKET_GUIDE.md) checks required
views, image quality, duplicates and content custody before human review. Run
its complete synthetic image-packet rehearsal from repository root:

```bash
python competitions/opencv-ai-2026/visual-evidence-gate/packet_rehearsal.py ./packet-demo
```

Open the generated `packet-demo/READOUT.md`; the guide includes local inspection,
exact receipt verification, the read-only S3 contract and interpretation limits.
The single-frame gate below retains its original behavior. Run these original
commands from `competitions/opencv-ai-2026/visual-evidence-gate/`:

```bash
python evaluate.py
python -m unittest discover -s tests -v
python -O -m unittest discover -s tests -v
```

From repository root, the retained `test_opencv_visual_evidence_gate.py` bridge runs the hostile suite normally and also spawns the nested suite under `python -O`.

## Safety / privacy boundary

The detector only measures a synthetic red region. It does not identify people, faces, objects, intent, or safety-critical anomalies. No external media is bundled. Production or safety use would require lawful/right-cleared data, calibrated task-specific detection, held-out evaluation, threat modeling, and explicit human-control design.
