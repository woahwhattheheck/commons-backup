#!/usr/bin/env python3
"""Deterministic, advisory visual-evidence gate for the OpenCV 2026 Agentic Vision path.

Synthetic or right-cleared frames are measured with OpenCV. Visual evidence changes the
next advisory tool plan, but this module never actuates hardware or contacts a provider.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

SCHEMA = "visual-evidence-gate/v1"
DETECTOR = "red-region-v1"
MAX_FRAME_PIXELS = 4_194_304
MAX_AGE_MS = 2_000
MIN_HAZARD_PPM = 7_500  # 0.75% of frame
CENTER_LOW = 400
CENTER_HIGH = 600
ALLOWED_REQUEST_CLASSES = {"ADVISORY", "OBSERVATION_ONLY"}
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class GateError(ValueError):
    pass


@dataclass(frozen=True)
class Detection:
    scene_sha256: str
    width: int
    height: int
    observed_ms: int
    hazard_pixels: int
    hazard_ppm: int
    centroid_x_permille: int | None
    visual_class: str
    opencv_version: str


def canonical_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()


def digest_obj(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def opencv_major() -> int:
    token = cv2.__version__.split(".", 1)[0]
    return int(token) if token.isdigit() else 0


def opencv5_runtime_evidenced() -> bool:
    return opencv_major() >= 5


def synthetic_scene(*, width: int = 320, height: int = 192, hazard: str = "none") -> np.ndarray:
    """Create a deterministic rights-clean scene; no external media is used."""
    if not (64 <= width <= 1920 and 64 <= height <= 1080):
        raise GateError("synthetic dimensions out of bounds")
    if width * height > MAX_FRAME_PIXELS:
        raise GateError("synthetic frame too large")
    if hazard not in {"none", "left", "center", "right"}:
        raise GateError("unknown synthetic hazard")
    frame = np.full((height, width, 3), 32, dtype=np.uint8)
    # Neutral structure makes the scene non-uniform while remaining deterministic.
    cv2.line(frame, (0, height // 2), (width - 1, height // 2), (96, 96, 96), 2)
    cv2.circle(frame, (width // 2, height // 3), max(4, min(width, height) // 18), (180, 120, 20), -1)
    if hazard != "none":
        centers = {"left": width // 5, "center": width // 2, "right": 4 * width // 5}
        cx = centers[hazard]
        half_w = max(8, width // 12)
        half_h = max(8, height // 8)
        cv2.rectangle(
            frame,
            (max(0, cx - half_w), max(0, height // 2 - half_h)),
            (min(width - 1, cx + half_w), min(height - 1, height // 2 + half_h)),
            (0, 0, 255),
            -1,
        )
    return frame


def _validate_frame(frame: np.ndarray) -> tuple[int, int]:
    if not isinstance(frame, np.ndarray):
        raise GateError("frame must be ndarray")
    if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
        raise GateError("frame must be uint8 HxWx3 BGR")
    height, width = int(frame.shape[0]), int(frame.shape[1])
    if height <= 0 or width <= 0 or height * width > MAX_FRAME_PIXELS:
        raise GateError("frame dimensions invalid")
    return width, height


def detect(frame: np.ndarray, *, observed_ms: int) -> Detection:
    width, height = _validate_frame(frame)
    if not isinstance(observed_ms, int) or isinstance(observed_ms, bool) or observed_ms < 0:
        raise GateError("observed_ms must be nonnegative integer")
    # The frame digest binds exact BGR bytes plus dimensions to the downstream decision.
    scene_sha = hashlib.sha256(
        width.to_bytes(4, "big") + height.to_bytes(4, "big") + frame.tobytes(order="C")
    ).hexdigest()
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower_a = cv2.inRange(hsv, np.array([0, 160, 120], np.uint8), np.array([10, 255, 255], np.uint8))
    lower_b = cv2.inRange(hsv, np.array([170, 160, 120], np.uint8), np.array([179, 255, 255], np.uint8))
    mask = cv2.bitwise_or(lower_a, lower_b)
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hazard_pixels = int(cv2.countNonZero(mask))
    hazard_ppm = (hazard_pixels * 1_000_000) // (width * height)
    centroid_x = None
    if contours and hazard_ppm >= MIN_HAZARD_PPM:
        moments = cv2.moments(max(contours, key=cv2.contourArea))
        if moments["m00"] > 0:
            x = moments["m10"] / moments["m00"]
            centroid_x = max(0, min(1000, int(round(x * 1000 / width))))
    if hazard_ppm < MIN_HAZARD_PPM or centroid_x is None:
        visual_class = "CLEAR"
        centroid_x = None
    elif centroid_x < CENTER_LOW:
        visual_class = "HAZARD_LEFT"
    elif centroid_x > CENTER_HIGH:
        visual_class = "HAZARD_RIGHT"
    else:
        visual_class = "HAZARD_CENTER"
    return Detection(
        scene_sha256=scene_sha,
        width=width,
        height=height,
        observed_ms=observed_ms,
        hazard_pixels=hazard_pixels,
        hazard_ppm=hazard_ppm,
        centroid_x_permille=centroid_x,
        visual_class=visual_class,
        opencv_version=cv2.__version__,
    )


def evidence(det: Detection) -> dict[str, Any]:
    obj = {
        "detector": DETECTOR,
        "scene_sha256": det.scene_sha256,
        "width": det.width,
        "height": det.height,
        "observed_ms": det.observed_ms,
        "hazard_pixels": det.hazard_pixels,
        "hazard_ppm": det.hazard_ppm,
        "centroid_x_permille": det.centroid_x_permille,
        "visual_class": det.visual_class,
        "opencv_version": det.opencv_version,
    }
    obj["evidence_sha256"] = digest_obj(obj)
    return obj


EVIDENCE_KEYS = {
    "detector", "scene_sha256", "width", "height", "observed_ms", "hazard_pixels",
    "hazard_ppm", "centroid_x_permille", "visual_class", "opencv_version", "evidence_sha256",
}


def validate_evidence(ev: Any, *, now_ms: int) -> dict[str, Any]:
    if not isinstance(now_ms, int) or isinstance(now_ms, bool) or now_ms < 0:
        raise GateError("now_ms must be nonnegative integer")
    if not isinstance(ev, dict) or set(ev) != EVIDENCE_KEYS:
        raise GateError("evidence exact keys required")
    if ev["detector"] != DETECTOR:
        raise GateError("wrong detector generation")
    if not isinstance(ev["scene_sha256"], str) or not SHA_RE.fullmatch(ev["scene_sha256"]):
        raise GateError("scene digest invalid")
    if not isinstance(ev["opencv_version"], str) or not ev["opencv_version"]:
        raise GateError("OpenCV version missing")
    for key in ("width", "height", "observed_ms", "hazard_pixels", "hazard_ppm"):
        if not isinstance(ev[key], int) or isinstance(ev[key], bool) or ev[key] < 0:
            raise GateError(f"{key} invalid")
    if ev["width"] <= 0 or ev["height"] <= 0 or ev["width"] * ev["height"] > MAX_FRAME_PIXELS:
        raise GateError("evidence dimensions invalid")
    if ev["hazard_pixels"] > ev["width"] * ev["height"] or ev["hazard_ppm"] > 1_000_000:
        raise GateError("hazard measurement impossible")
    if ev["visual_class"] not in {"CLEAR", "HAZARD_LEFT", "HAZARD_CENTER", "HAZARD_RIGHT"}:
        raise GateError("visual class invalid")
    cx = ev["centroid_x_permille"]
    if ev["visual_class"] == "CLEAR":
        if cx is not None:
            raise GateError("clear evidence cannot have hazard centroid")
    else:
        if not isinstance(cx, int) or isinstance(cx, bool) or not 0 <= cx <= 1000:
            raise GateError("hazard centroid invalid")
    if now_ms < ev["observed_ms"]:
        raise GateError("future evidence")
    if now_ms - ev["observed_ms"] > MAX_AGE_MS:
        raise GateError("stale evidence")
    claimed = ev["evidence_sha256"]
    if not isinstance(claimed, str) or not SHA_RE.fullmatch(claimed):
        raise GateError("evidence digest invalid")
    unsigned = {k: ev[k] for k in ev if k != "evidence_sha256"}
    if digest_obj(unsigned) != claimed:
        raise GateError("evidence digest mismatch")
    return dict(ev)


def decide(ev: Any, *, now_ms: int, requested_action_class: str = "ADVISORY") -> dict[str, Any]:
    if requested_action_class not in ALLOWED_REQUEST_CLASSES:
        # Unknown or physical action requests are never auto-authorized.
        return {
            "decision": "HUMAN_APPROVAL_REQUIRED",
            "tool_plan": "NO_ACTION",
            "reason": "UNSAFE_OR_UNKNOWN_ACTION_CLASS",
            "requested_action_class": str(requested_action_class),
            "evidence_sha256": ev.get("evidence_sha256") if isinstance(ev, dict) else None,
            "physical_actuation_authorized": False,
        }
    try:
        good = validate_evidence(ev, now_ms=now_ms)
    except (GateError, TypeError, ValueError):
        return {
            "decision": "HOLD_EVIDENCE",
            "tool_plan": "NO_ACTION",
            "reason": "EVIDENCE_INVALID_OR_STALE",
            "requested_action_class": requested_action_class,
            "evidence_sha256": ev.get("evidence_sha256") if isinstance(ev, dict) else None,
            "physical_actuation_authorized": False,
        }
    mapping = {
        "CLEAR": ("CONTINUE_OBSERVATION", "CAPTURE_NEXT_FRAME", "CLEAR_FRAME"),
        "HAZARD_LEFT": ("PLAN_FOCUSED_INSPECTION", "INSPECT_LEFT_ZONE", "VISUAL_HAZARD_LEFT"),
        "HAZARD_RIGHT": ("PLAN_FOCUSED_INSPECTION", "INSPECT_RIGHT_ZONE", "VISUAL_HAZARD_RIGHT"),
        "HAZARD_CENTER": ("HUMAN_APPROVAL_REQUIRED", "NO_ACTION", "VISUAL_HAZARD_CENTER"),
    }
    decision, tool_plan, reason = mapping[good["visual_class"]]
    return {
        "decision": decision,
        "tool_plan": tool_plan,
        "reason": reason,
        "requested_action_class": requested_action_class,
        "evidence_sha256": good["evidence_sha256"],
        "physical_actuation_authorized": False,
    }


def compile_trace(frame: np.ndarray, *, observed_ms: int, now_ms: int, requested_action_class: str = "ADVISORY") -> dict[str, Any]:
    det = detect(frame, observed_ms=observed_ms)
    ev = evidence(det)
    outcome = decide(ev, now_ms=now_ms, requested_action_class=requested_action_class)
    packet = {
        "schema": SCHEMA,
        "perception": ev,
        "decision": outcome,
        "authority": {
            "physical_actuation_authorized": False,
            "camera_capture_authorized": False,
            "aws_deployment_authorized": False,
            "external_submission_authorized": False,
            "payment_or_revenue_claim_authorized": False,
        },
        "runtime_truth": {
            "opencv5_execution_evidenced": opencv5_runtime_evidenced(),
            "aws_deployment_evidenced": False,
            "synthetic_fixture": True,
        },
    }
    packet["trace_sha256"] = digest_obj(packet)
    return packet


def verify_trace(packet: Any) -> bool:
    if not isinstance(packet, dict) or set(packet) != {"schema", "perception", "decision", "authority", "runtime_truth", "trace_sha256"}:
        return False
    claimed = packet.get("trace_sha256")
    if not isinstance(claimed, str) or not SHA_RE.fullmatch(claimed):
        return False
    unsigned = {k: packet[k] for k in packet if k != "trace_sha256"}
    if digest_obj(unsigned) != claimed:
        return False
    auth = packet.get("authority")
    if not isinstance(auth, dict) or any(auth.values()):
        return False
    if packet["decision"].get("physical_actuation_authorized") is not False:
        return False
    return True
