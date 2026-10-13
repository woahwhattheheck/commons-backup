# GaugeProof — OpenCV AI Competition 2026

GaugeProof turns short image/video bursts of an analog industrial gauge into a **bounded evidence packet**, not an equipment-control command. It is a competition-isolated prototype for the OpenCV AI Competition 2026 powered by AWS.

## Why this product

Industrial and water operators still encounter analog pressure/flow/level gauges in inspections. A single OCR-like number is not enough: blur, glare, occlusion, a second dark radial feature, or frame-to-frame disagreement can turn a plausible-looking read into bad evidence. GaugeProof makes refusal a first-class product behavior.

The computer-vision path is the core:

1. OpenCV localizes a dial circle and measures ring completeness.
2. A radial darkness projection estimates the pointer angle while excluding tick marks.
3. A declared calibration maps the pointer angle into an engineering value.
4. Quality gates reject blur, glare, missing dial geometry, low pointer contrast, and ambiguous radial peaks.
5. Multiple frames are aggregated. Stable evidence may become `ACCEPT_READING`; poor capture becomes `REINSPECT`; materially conflicting valid reads become `ESCALATE_HUMAN`.
6. Every result is bound into deterministic SHA-256 evidence receipts with input and annotation identities.

The agentic layer is deliberately narrow: it selects a review disposition and explains why. It **cannot** operate a valve, pump, PLC, meter, provider API, or maintenance system.

## Judge path

```bash
cd competitions/opencv-gaugeproof-2026
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python -m unittest discover -s tests -v
PYTHONPATH=. python -m gaugeproof.cli demo --output gaugeproof-demo
PYTHONPATH=. python -m gaugeproof.cli verify gaugeproof-demo/receipt.json
```

The demo generates synthetic gauges in memory; no camera, customer image, cloud key, or network call is required. The output directory is create-new-only and contains the receipt plus annotated frames.

## Competition fit

Current organizer material describes a global OpenCV/AWS competition centered on real image/video applications. Organizer/Devpost prize surfaces have changed during the live event, so this repository intentionally records opportunity URLs and deadlines without hard-coding a guaranteed award amount. Submission/registration, AWS credits, and any special-prize requirements remain external account actions.

Potential judging story:

- **real-world impact:** low-friction inspection evidence for legacy analog instruments;
- **technical execution:** geometry detection, angular signal extraction, quality refusal, temporal consistency, deterministic evidence;
- **agentic vision:** the agent reasons over visual evidence quality and chooses accept/reinspect/human escalation, with no device authority;
- **cloud path:** frame-level analysis is embarrassingly parallel and can later benchmark standard OpenCV vs Cloud Optimized OpenCV on AWS without changing evidence semantics.

## Truth / authority boundary

The checked-in system proves only what its supplied image bytes and calibration support. It does not prove the camera/site identity, physical calibration validity, maintenance completion, operator identity, or that a real instrument is safe. All receipt authority flags remain false for external actions. Real deployment requires site-specific calibration, camera provenance, operational safety review, and human process integration.

See `docs/architecture.md` and `docs/submission.md`.
