# EvidenceAAR — NIWC Digital Scribe source carrier

EvidenceAAR is a deterministic, evidence-bound **offline prototype** for the 2026 NIWC Atlantic / OUSD(R&E) AI Digital Scribe Prize Challenge. It converts a bounded normalized multimodal event packet into a timestamp-corrected timeline, episodes, evidence-linked observations/decisions/actions/outcomes, an unresolved contradiction ledger, a modality-coverage ledger, and deterministic JSON/Markdown/HTML After-Action Review artifacts.

The public challenge schedule currently lists Phase 1 submissions due **September 25, 2026**, virtual Phase 2 on **October 20–22, 2026**, and awards of **$50,000 / $30,000 / $20,000**. Those are sponsor-advertised challenge terms, not an award or payment claim by this repository. Submission is a separate authenticated Vulcan-account action and is intentionally not implemented here.

## What this carrier proves

* **Evidence lineage.** Every AAR claim binds an event ID, source ID, source SHA-256, observed timestamp, and corrected timestamp. The normalized source manifest is transitively bound into the receipt digests.
* **Clock correction.** Each source carries a bounded signed millisecond correction. Timeline order and segmentation use the corrected UTC timestamps, never machine-local time.
* **Episode segmentation.** A fixed caller-declared gap threshold partitions the corrected timeline deterministically.
* **Contradiction conservation.** Distinct assertions are marked `UNRESOLVED` only when they share the same episode, subject, and claim kind. A normal observation → decision → action → outcome narrative does not manufacture a contradiction.
* **Coverage visibility.** Every episode reports present and missing required modalities instead of pretending incomplete evidence is complete.
* **Strict ingress.** Duplicate JSON keys, floating/non-finite numbers, over-deep values, unsafe huge integers, unknown fields, type confusion (`true` as an integer), unbounded counts, and timezone-free timestamps fail closed.
* **Safe publication.** Markdown metacharacters and HTML text are escaped. Render outputs are create-exclusive and a partial render is cleaned up on failure.
* **Independent verification.** A bundle is accepted only when recomputing from the original input yields the exact canonical bundle bytes.
* **Authority ceiling.** The checked-in carrier accepts only `synthetic: true` and always records external authority as false: no operational exercise-data claim, sponsor-submission authority, win/award claim, or payment/revenue claim.

This carrier starts **after multimodal extraction**: audio/video/image/text/sensor preprocessing produces normalized events plus immutable source digests. It does not pretend that a deterministic stdlib prototype performs speech recognition, computer vision, or restricted-data ingestion.

## Run the synthetic demo

```bash
python3 competitions/niwc-digital-scribe-2026/workbench.py \
  compile competitions/niwc-digital-scribe-2026/fixtures/synthetic_exercise.json \
  -o /tmp/evidenceaar-bundle.json

python3 competitions/niwc-digital-scribe-2026/workbench.py \
  verify competitions/niwc-digital-scribe-2026/fixtures/synthetic_exercise.json \
  /tmp/evidenceaar-bundle.json

python3 competitions/niwc-digital-scribe-2026/workbench.py \
  render competitions/niwc-digital-scribe-2026/fixtures/synthetic_exercise.json \
  /tmp/evidenceaar-rendered
```

`verify` prints `VERIFIED` only after exact recomputation. `render` creates `aar.json`, `aar.md`, `aar.html`, `receipt.json`, and `bundle.json` in a new directory.

## Test contract

The repository-root regression file is deliberately named `test_niwc_digital_scribe_evidenceaar.py` so Commons' existing test battery discovers it without adding another workflow surface.

```bash
python3 -m unittest -v test_niwc_digital_scribe_evidenceaar.py
python3 -O -m unittest -v test_niwc_digital_scribe_evidenceaar.py
```

The suite covers deterministic compilation, clock correction, segmentation, contradiction semantics, source-digest lineage, coverage gaps, Markdown/HTML escaping, exact-type checks, duplicate keys, floats/non-finite values, Python's huge-integer JSON parser resource guard, deep nesting, schema/type attacks, bundle tamper, raw-input mismatch, create-exclusive rendering, and real subprocess compile/verify behavior in normal and optimized Python.

## Phase 1 handoff

See [`PHASE1.md`](PHASE1.md). External registration, terms acceptance, real challenge data, sponsor submission, and any award/payment assertion remain deliberately outside source authority.
