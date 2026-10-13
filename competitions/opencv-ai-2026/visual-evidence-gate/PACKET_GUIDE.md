# Multi-photo packet quality and custody

This extension checks whether an ordered collection of supplied image bytes is ready for **human review**. It measures focus and clipped exposure, finds missing required slots, and flags identical or visually similar images across slots. It preserves the original single-frame `visual_gate.py` behavior and its separate advisory trace.

The extension integrates Z-Vectorforge-1545's retained ProofCam donor from `c21c117cd6b80292a5836f7f77d454a81e2915b0`, following issue #15715 and canonical #15360 / merged #15448. The earlier parallel #15696 was closed without merging; its separate directory is not recreated. Original single-frame implementation credit remains Z-Sol / Z-SOL/17-0408. Canonical integration, bounded input repairs, commands and rehearsal: ZZ–Keystone-43CF, Codex / GPT family; exact model identifier unavailable.

## Run the complete worked example

From repository root, using a Python environment with `requirements-test.txt` installed:

```bash
python competitions/opencv-ai-2026/visual-evidence-gate/packet_rehearsal.py ./packet-demo
```

Use a **new** destination. Open `packet-demo/READOUT.md`; every case includes its packet, image map, actual generated images and either a receipt or an input-error record. `summary.json` contains the observed next steps. `INVENTORY.json` binds every other output by byte count and SHA-256. A completed command is required: exclusive creation protects existing paths, but interrupted writes can leave an incomplete new directory.

The nine executed cases cover distinct views, a missing side view, identical cross-slot bytes, the same image encoded as PNG and JPEG, blur, shadow clipping, highlight clipping, unreadable bytes, and a deliberately wrong payload digest. They exercise all five advisory actions plus input rejection. The separate S3-shaped fixture verifies a manifest and rejects an altered outer envelope using an in-memory loader; it does not contact AWS.

The images are deterministic generated patterns. Noise and patterns can satisfy quality thresholds; a successful result does not establish that an image depicts the requested view or object. The rehearsal measures contract behavior, not accuracy on natural inspection photographs.

## Inspect and verify local files

```bash
python competitions/opencv-ai-2026/visual-evidence-gate/packet_cli.py inspect \
  --packet packet-demo/distinct/packet.json \
  --image-map packet-demo/distinct/image-map.json \
  --output ./review-receipt.json

python competitions/opencv-ai-2026/visual-evidence-gate/packet_cli.py verify \
  --packet packet-demo/distinct/packet.json \
  --image-map packet-demo/distinct/image-map.json \
  --receipt ./review-receipt.json
```

`inspect` writes the complete receipt to standard output when `--output` is omitted. An output file is created exclusively; an existing file is never replaced. Successful execution exits 0. Input, verification or filesystem errors exit 2 and emit an error on standard error. A quality hold is a successfully computed advisory result and exits 0; callers must read `decision.trace.action`.

The image map is a JSON object from each packet image ID to a local path. Relative paths resolve against the image-map file's directory, including when the command runs from elsewhere. Its keys must match the packet's image IDs exactly. Each file is captured once during a command. `verify` decodes and measures each captured image once while performing its full deterministic recompile; it does not trust a receipt merely because its digest is well formed. No URL fetching is implemented.

## Packet contract

```json
{
  "schema": "proofcam-evidence-packet/v1",
  "packet_id": "inspection-001",
  "required_slots": [
    {"slot_id": "front", "label": "front-view"},
    {"slot_id": "side", "label": "side-view"}
  ],
  "images": [
    {"image_id": "img-front", "slot_id": "front", "payload_sha256": "<64 lowercase hexadecimal characters>"}
  ]
}
```

Replace the digest placeholder with the SHA-256 of the exact encoded image bytes. The example intentionally lacks the required side view. IDs/labels use lowercase ASCII letters, digits and `._:-`, start with a letter or digit, and contain at most 128 characters. Slots are nonempty, unique and sorted by `slot_id`; images are sorted by `(slot_id, image_id)`. At most one image may fill each declared slot. Unknown slots, duplicate IDs/keys and reordered arrays are rejected. Missing images are a review outcome; an empty list of required slots is an invalid packet.

The donor's `proofcam-*` schemas remain stable for compatibility. Public Python functions in `packet_quality.py` are `compile_triage(packet, image_loader)` and `verify_triage(packet, image_loader, artifact)`. The loader receives an image ID and returns bytes. `ProofCamError` identifies contract failures. The module imports no network client.

## Measurements and next steps

| Priority | Condition | Advisory next step |
|---|---|---|
| 1 | Empty, oversized, undecodable or unsupported-dimension image | `HOLD_UNSAFE_OR_UNREADABLE` |
| 2 | Exact SHA-256 duplicate or dHash Hamming distance ≤ 3 across slots | `HOLD_DUPLICATE_EVIDENCE` |
| 3 | Required slot has no image | `REQUEST_MISSING_VIEW` |
| 4 | Focus variance < 60, shadow fraction > 0.35, or highlight fraction > 0.35 | `REQUEST_RECAPTURE` |
| 5 | No earlier condition applies | `ACCEPT_FOR_HUMAN_REVIEW` |

The action follows the donor's priority order; it is not an exhaustive simultaneous issue list. For example, an unreadable image takes precedence over a missing view. Within a quality result, low focus takes precedence over clipping. Full measured values remain in the receipt for readable images.

OpenCV decodes the original encoded bytes, converts BGR to gray, computes variance of the Laplacian, measures pixels at gray ≤ 5 and ≥ 250, and constructs dHash from a 9×8 area-resized image. See the official [image decoding documentation](https://docs.opencv.org/4.13.0/d4/da8/group__imgcodecs.html) and [Laplacian operator documentation](https://docs.opencv.org/4.13.0/d5/db5/tutorial_laplace_operator.html). The numerical thresholds are retained illustrative engineering choices, not values validated by those references or a calibrated inspection standard. dHash can collide and can miss modified duplicates; it is a review signal, not identity or fraud proof.

The measurement receipt binds the packet digest, measurements and thresholds. The outer receipt binds the decision, actual OpenCV version, packet and image payload digests, advisory trace and fixed false authority fields. Exact recompilation checks every field. These are deterministic content receipts, not signatures, capture-time evidence or proof of physical custody. Different OpenCV runtimes may produce different measurements or receipts; retain the observed runtime with the source and image bytes.

## Read-only S3 manifest adapter

`packet_s3.compile_s3_manifest_event(event, s3_get)` accepts exactly `bucket`, `manifest_key`, and `manifest_etag`. The injected read function receives `(bucket, key, normalized_etag)` and returns bytes. The manifest contains `packet` and `objects`; each object contains `image_id`, `key`, `etag`, and `payload_sha256`.

The object-ID set must equal the packet's image-ID set, and both digest declarations must agree before image reads. Actual object bytes must match that digest. The adapter receipt binds the exact manifest bytes, bucket/key/ETag envelope and complete inner artifact. `verify_s3_manifest_event` performs exact recompilation of the outer and inner result.

ETags are treated as conditional-read validators in the retained hexadecimal or multipart form, never as assumed content MD5 hashes. They are not S3 VersionId values or unique object-version identities. SHA-256 binds the payload. This version has a deliberately narrower key/ETag grammar than all possible S3 names. Dot-dot path components and noncanonical separators are rejected. No adapter write operation is present.

The optional `lambda_handler` retains the donor's OpenCV 5 and AWS-environment preconditions, uses `GetObject` with `IfMatch`, reads bounded chunks through EOF, validates declared length and closes the body. An environment variable does not prove AWS execution: the artifact still reports `aws_execution_proven=false`. This integration tests an injected store and fake provider streams; it does not deploy Lambda, exercise credentials, prove AWS runtime or establish competition eligibility.

## Bounds and interpretation

JSON is limited to 1 MiB, 64 nesting levels and 32,768 values/keys; required views are limited to 64. Each encoded image is limited to 32 MiB and aggregate encoded packet bytes to 128 MiB. Supported decoded dimensions are 32–8192 pixels per edge with at most 50 million pixels. The local command rejects an oversized file before issuing a receipt. Core decoding returns an unreadable measurement for its supported oversize case; aggregate overflow is an input error.

Dimension checks happen after native decoding; Laplacian measurement also allocates working data. These are input bounds, not a hard native-process memory sandbox. The shipped implementation is offline source-development tooling, not a validated arbitrary-media service.

No result approves a claim, payment, external action, compliance finding, fraud finding, competition submission, prize or revenue. Fixed authority values are literally false. The original single-frame gate remains separate: packet quality acceptance does not authorize camera capture or physical action.

## Replay the retained checks

```bash
python -m unittest discover -s competitions/opencv-ai-2026/visual-evidence-gate/tests -v
python -O -m unittest discover -s competitions/opencv-ai-2026/visual-evidence-gate/tests -v
python test_opencv_visual_evidence_gate.py
python -O test_opencv_visual_evidence_gate.py
```

The existing root bridge discovers original single-frame, packet and command suites and runs real optimized subprocesses. The original workflow and pinned test requirements remain unchanged; no second workflow or product tree is added. Local execution receipts and hosted/current-main integration evidence are recorded separately.
