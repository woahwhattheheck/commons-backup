from __future__ import annotations

import hashlib
import json
from typing import Sequence

import cv2
import numpy as np

from .core import Calibration, annotate_frame, inspect_sequence


SCHEMA = "gaugeproof.inspection/v1"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def _image_digest(image: np.ndarray) -> str:
    if not isinstance(image, np.ndarray):
        raise TypeError("image must be a numpy array")
    meta = f"{image.dtype.str}|{image.shape}".encode("ascii")
    return _sha256(meta + b"\0" + np.ascontiguousarray(image).tobytes())


def _png_bytes(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise ValueError("failed to encode annotation")
    return encoded.tobytes()


def compile_receipt(frames: Sequence[np.ndarray], calibration: Calibration) -> tuple[dict, list[bytes]]:
    calibration.validate()
    if not isinstance(frames, Sequence) or isinstance(frames, (str, bytes)) or not 1 <= len(frames) <= 100:
        raise ValueError("frames must be a sequence of 1..100 images")
    result = inspect_sequence(frames, calibration)
    annotations: list[bytes] = []
    frame_evidence: list[dict] = []
    for idx, (image, reading) in enumerate(zip(frames, result.frames)):
        annotated = annotate_frame(image, reading)
        png = _png_bytes(annotated)
        annotations.append(png)
        frame_evidence.append({
            "index": idx,
            "input_sha256": _image_digest(image),
            "annotation_png_sha256": _sha256(png),
            "reading": reading.to_dict(),
        })

    body = {
        "schema": SCHEMA,
        "calibration": calibration.to_dict(),
        "inspection": {k: v for k, v in result.to_dict().items() if k != "frames"},
        "frame_evidence": frame_evidence,
        "authority": {
            "equipment_control_authorized": False,
            "provider_send_authorized": False,
            "maintenance_completion_asserted": False,
            "human_review_required_for_escalation": True,
        },
    }
    receipt = dict(body)
    receipt["receipt_sha256"] = _sha256(_canonical_json(body))
    return receipt, annotations


def verify_receipt(receipt: dict) -> bool:
    if not isinstance(receipt, dict) or set(receipt) != {
        "schema", "calibration", "inspection", "frame_evidence", "authority", "receipt_sha256"
    }:
        return False
    claimed = receipt.get("receipt_sha256")
    if not isinstance(claimed, str) or len(claimed) != 64 or any(c not in "0123456789abcdef" for c in claimed):
        return False
    if receipt.get("schema") != SCHEMA:
        return False
    authority = receipt.get("authority")
    expected_authority = {
        "equipment_control_authorized": False,
        "provider_send_authorized": False,
        "maintenance_completion_asserted": False,
        "human_review_required_for_escalation": True,
    }
    if authority != expected_authority:
        return False
    body = {k: receipt[k] for k in ("schema", "calibration", "inspection", "frame_evidence", "authority")}
    try:
        actual = _sha256(_canonical_json(body))
    except (TypeError, ValueError):
        return False
    return actual == claimed
