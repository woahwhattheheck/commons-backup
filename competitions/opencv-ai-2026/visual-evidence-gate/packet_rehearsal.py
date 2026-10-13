#!/usr/bin/env python3
"""Write a reproducible, rights-clean image-packet rehearsal to a new directory."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import sys
from typing import Any

import cv2
import numpy as np

from packet_quality import ProofCamError, canonical_bytes, compile_triage, sha256, verify_triage
from packet_s3 import compile_s3_manifest_event, verify_s3_manifest_event


def encode(image: np.ndarray, suffix: str = ".png") -> bytes:
    ok, encoded = cv2.imencode(suffix, image, [cv2.IMWRITE_JPEG_QUALITY, 95] if suffix == ".jpg" else [])
    if not ok:
        raise RuntimeError("synthetic image encoding failed")
    return encoded.tobytes()


def texture(seed: int) -> np.ndarray:
    # Deliberately synthetic texture: exercises measurements, never view semantics.
    image = np.random.default_rng(seed).integers(20, 236, size=(160, 160, 3), dtype=np.uint8)
    cv2.rectangle(image, (15, 15), (80, 70), (255, 255, 255), 3)
    cv2.circle(image, (110, 105), 24, (5, 5, 5), 3)
    return image


def make_packet(case_id: str, payloads: dict[str, bytes], slots: tuple[str, ...]) -> dict[str, Any]:
    return {
        "schema": "proofcam-evidence-packet/v1",
        "packet_id": "synthetic-" + case_id,
        "required_slots": [{"slot_id": slot, "label": slot + "-view"} for slot in sorted(slots)],
        "images": [
            {"image_id": "img-" + slot, "slot_id": slot, "payload_sha256": sha256(payloads[slot])}
            for slot in sorted(payloads)
        ],
    }


def cases():
    front, side, duplicate = encode(texture(1)), encode(texture(2)), encode(texture(3))
    near = texture(19)
    shadow = np.zeros((160, 160, 3), dtype=np.uint8)
    cv2.line(shadow, (0, 0), (159, 159), (255, 255, 255), 2)
    highlight = 255 - shadow
    specifications = [
        ("distinct", {"front": front, "side": side}, ("front", "side"), "ACCEPT_FOR_HUMAN_REVIEW"),
        ("missing", {"front": front}, ("front", "side"), "REQUEST_MISSING_VIEW"),
        ("exact-duplicate", {"front": duplicate, "side": duplicate}, ("front", "side"), "HOLD_DUPLICATE_EVIDENCE"),
        ("near-duplicate", {"front": encode(near), "side": encode(near, ".jpg")}, ("front", "side"), "HOLD_DUPLICATE_EVIDENCE"),
        ("blur", {"front": encode(cv2.GaussianBlur(texture(4), (31, 31), 0))}, ("front",), "REQUEST_RECAPTURE"),
        ("shadow", {"front": encode(shadow)}, ("front",), "REQUEST_RECAPTURE"),
        ("highlight", {"front": encode(highlight)}, ("front",), "REQUEST_RECAPTURE"),
        ("corrupt", {"front": b"deliberately unreadable synthetic image"}, ("front",), "HOLD_UNSAFE_OR_UNREADABLE"),
        ("digest-mismatch", {"front": front}, ("front",), "INPUT_REJECTED"),
    ]
    for case_id, payloads, slots, expected in specifications:
        packet = make_packet(case_id, payloads, slots)
        if case_id == "digest-mismatch":
            packet["images"][0]["payload_sha256"] = "0" * 64
        yield case_id, packet, payloads, expected


def _report(case_id: str, result: dict[str, Any]) -> str:
    if "input_error" in result:
        return f"# Synthetic case: {case_id}\n\nInput rejected before a measurement receipt was issued.\n\n{result['input_error']}\n"
    decision = result["decision"]
    trace = decision["trace"]
    lines = [
        f"# Synthetic case: {case_id}", "", f"Next review step: **{trace['action']}**", "",
        "These generated patterns exercise image measurements. They do not demonstrate a real inspection, correct camera view or authentic capture.", "",
        "| View | Decode | Focus variance | Shadow fraction | Highlight fraction |",
        "|---|---|---:|---:|---:|",
    ]
    for m in decision["measurements"]:
        lines.append(f"| {m['slot_id']} | {m['status']} | {m.get('focus_variance', '—')} | {m.get('low_clip_fraction', '—')} | {m.get('high_clip_fraction', '—')} |")
    lines.extend(["", "Reasons: " + "; ".join(r["code"] + " (" + r["slot_id"] + ")" for r in trace["reasons"]) if trace["reasons"] else "", "No automatic business approval. A human must review the underlying evidence.", "", f"Receipt: `{result['receipt_sha256']}`", ""])
    return "\n".join(lines)


def build_artifacts() -> tuple[dict[str, bytes], dict[str, Any]]:
    artifacts: dict[str, bytes] = {}
    summary: list[dict[str, Any]] = []
    for case_id, packet, payloads, expected in cases():
        by_id = {"img-" + slot: data for slot, data in payloads.items()}
        image_map: dict[str, str] = {}
        for image_id, data in by_id.items():
            suffix = ".jpg" if data.startswith(b"\xff\xd8") else ".png" if data.startswith(b"\x89PNG") else ".bin"
            relative = "images/" + image_id + suffix
            image_map[image_id] = relative
            artifacts[case_id + "/" + relative] = data
        artifacts[case_id + "/packet.json"] = canonical_bytes(packet) + b"\n"
        artifacts[case_id + "/image-map.json"] = canonical_bytes(image_map) + b"\n"
        try:
            result = compile_triage(packet, by_id.__getitem__)
            verify_triage(packet, by_id.__getitem__, result)
            action = result["decision"]["trace"]["action"]
            if any(value is not False for value in result["decision"]["authority"].values()):
                raise RuntimeError("rehearsal received an unexpected authority value")
            artifacts[case_id + "/receipt.json"] = canonical_bytes(result) + b"\n"
        except ProofCamError as exc:
            if expected != "INPUT_REJECTED":
                raise
            action = "INPUT_REJECTED"
            result = {"input_error": str(exc), "receipt_issued": False}
            artifacts[case_id + "/input-error.json"] = canonical_bytes(result) + b"\n"
        if action != expected:
            raise RuntimeError(f"{case_id}: expected {expected}, observed {action}")
        artifacts[case_id + "/READOUT.md"] = _report(case_id, result).encode("utf-8")
        summary.append({"case": case_id, "action": action, "expected": expected, "receipt_sha256": result.get("receipt_sha256")})

    # The adapter is exercised against a fixed in-memory store. No boto3 import,
    # provider credential, network read or AWS runtime claim is involved.
    payload = encode(texture(14))
    packet = make_packet("s3-fixture", {"front": payload}, ("front",))
    manifest = {"packet": packet, "objects": [{"image_id": "img-front", "key": "evidence/front.png", "etag": "a" * 32, "payload_sha256": sha256(payload)}]}
    manifest_bytes = canonical_bytes(manifest)
    event = {"bucket": "synthetic-evidence", "manifest_key": "manifests/example.json", "manifest_etag": "b" * 32}
    store = {
        (event["bucket"], event["manifest_key"], event["manifest_etag"]): manifest_bytes,
        (event["bucket"], "evidence/front.png", "a" * 32): payload,
    }
    def get(bucket, key, etag):
        return store[(bucket, key, etag)]
    envelope = compile_s3_manifest_event(event, get)
    verify_s3_manifest_event(event, get, envelope)
    changed = copy.deepcopy(envelope)
    changed["runtime_envelope"]["bucket"] = "changed-fixture-bucket"
    try:
        verify_s3_manifest_event(event, get, changed)
    except ProofCamError:
        mutation_rejected = True
    else:
        raise RuntimeError("adapter accepted an altered outer envelope")
    artifacts["s3-fixture/event.json"] = canonical_bytes(event) + b"\n"
    artifacts["s3-fixture/manifest.json"] = manifest_bytes
    artifacts["s3-fixture/front.png"] = payload
    artifacts["s3-fixture/adapter-receipt.json"] = canonical_bytes(envelope) + b"\n"
    result = {
        "schema": "visual-evidence-packet-rehearsal/v1",
        "synthetic": True,
        "opencv_runtime_observed": str(cv2.__version__),
        "cases": summary,
        "s3_fixture": {"verified": True, "outer_mutation_rejected": mutation_rejected, "aws_execution_proven": False},
        "natural_image_accuracy_measured": False,
        "business_approval_created": False,
    }
    artifacts["summary.json"] = canonical_bytes(result) + b"\n"
    rows = ["# Multi-photo evidence packet: executed synthetic rehearsal", "", "Nine deterministic image-packet cases and one local S3-shaped fixture. Every image is generated here; no real inspection or person appears.", "", "| Case | Observed next step |", "|---|---|"]
    rows.extend(f"| [{row['case']}]({row['case']}/READOUT.md) | {row['action']} |" for row in summary)
    rows.extend(["", "The S3-shaped fixture verifies its manifest, object bytes and outer receipt. An altered envelope fails fixture verification. Objects are supplied by an in-process dictionary; no AWS deployment or execution is evidenced.", "", "A passing packet reaches human review only. The quality measures do not establish correct viewpoint, identity, authenticity, fraud, compliance or business approval. Thresholds are illustrative and require calibration on the intended imagery.", "", f"Observed runtime: OpenCV {cv2.__version__}. Competition eligibility or submission is not evaluated by this rehearsal.", ""])
    artifacts["READOUT.md"] = "\n".join(rows).encode("utf-8")
    inventory = {name: {"bytes": len(data), "sha256": sha256(data)} for name, data in sorted(artifacts.items())}
    artifacts["INVENTORY.json"] = canonical_bytes({"files": inventory}) + b"\n"
    return artifacts, result


def rehearse(destination: Path) -> dict[str, Any]:
    # Compute and check all cases before creating any output. mkdir is exclusive;
    # an existing directory is never used as a destination or silently replaced.
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"output directory already exists: {destination}")
    artifacts, summary = build_artifacts()
    destination.mkdir()
    for relative, data in sorted(artifacts.items()):
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    try:
        result = rehearse(args.destination)
    except (ProofCamError, OSError, RuntimeError, ValueError) as exc:
        print(f"rehearsal error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical_bytes(result) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
