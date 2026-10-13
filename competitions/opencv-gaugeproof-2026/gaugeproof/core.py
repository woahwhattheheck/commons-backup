from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
import math
from typing import Iterable, Sequence

import cv2
import numpy as np


MAX_IMAGE_SIDE = 4096
MIN_IMAGE_SIDE = 160
MAX_PIXELS = 12_000_000


class InspectionDecision(str, Enum):
    ACCEPT_READING = "ACCEPT_READING"
    REINSPECT = "REINSPECT"
    ESCALATE_HUMAN = "ESCALATE_HUMAN"


@dataclass(frozen=True)
class Calibration:
    """Map a clockwise image angle to an engineering value.

    Angles are expressed clockwise from +x in image coordinates.  The maximum
    angle may exceed 360 degrees so a dial arc that crosses zero can be
    represented without ambiguity (for example 135 -> 405 degrees).
    """

    min_angle_deg: float
    max_angle_deg: float
    min_value: float
    max_value: float
    unit: str = ""

    def validate(self) -> None:
        vals = (
            self.min_angle_deg,
            self.max_angle_deg,
            self.min_value,
            self.max_value,
        )
        if any(not math.isfinite(float(v)) for v in vals):
            raise ValueError("calibration values must be finite")
        span = float(self.max_angle_deg) - float(self.min_angle_deg)
        if not 5.0 <= span <= 360.0:
            raise ValueError("calibration angle span must be in [5, 360] degrees")
        if float(self.max_value) <= float(self.min_value):
            raise ValueError("calibration value range must be strictly increasing")
        if not isinstance(self.unit, str) or len(self.unit) > 32 or any(ord(c) < 32 for c in self.unit):
            raise ValueError("unit must be a short printable string")

    @property
    def value_span(self) -> float:
        return float(self.max_value) - float(self.min_value)

    def unwrap_angle(self, angle_deg: float) -> float:
        self.validate()
        base = float(angle_deg) % 360.0
        lo = float(self.min_angle_deg)
        hi = float(self.max_angle_deg)
        candidates = [base + 360.0 * k for k in range(-2, 4)]
        return min(candidates, key=lambda x: 0.0 if lo <= x <= hi else min(abs(x - lo), abs(x - hi)))

    def angle_to_value(self, angle_deg: float) -> float:
        a = self.unwrap_angle(angle_deg)
        lo = float(self.min_angle_deg)
        hi = float(self.max_angle_deg)
        margin = max(1.5, (hi - lo) * 0.015)
        if a < lo - margin or a > hi + margin:
            raise ValueError("pointer angle falls outside calibrated dial arc")
        a = min(max(a, lo), hi)
        t = (a - lo) / (hi - lo)
        return float(self.min_value) + t * self.value_span

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FrameReading:
    accepted: bool
    reason: str
    value: float | None
    unit: str
    pointer_angle_deg: float | None
    center_x: float | None
    center_y: float | None
    radius: float | None
    blur_score: float
    glare_fraction: float
    ring_support: float
    pointer_score: float
    pointer_ambiguity_ratio: float

    def to_dict(self) -> dict:
        out = asdict(self)
        for key, value in tuple(out.items()):
            if isinstance(value, float):
                out[key] = round(value, 8)
        return out


@dataclass(frozen=True)
class SequenceInspection:
    decision: InspectionDecision
    reason: str
    value: float | None
    unit: str
    accepted_frames: int
    rejected_frames: int
    median_value: float | None
    mad_value: float | None
    range_value: float | None
    frames: tuple[FrameReading, ...]
    side_effects_authorized: bool = False

    def to_dict(self) -> dict:
        return {
            "decision": self.decision.value,
            "reason": self.reason,
            "value": None if self.value is None else round(self.value, 8),
            "unit": self.unit,
            "accepted_frames": self.accepted_frames,
            "rejected_frames": self.rejected_frames,
            "median_value": None if self.median_value is None else round(self.median_value, 8),
            "mad_value": None if self.mad_value is None else round(self.mad_value, 8),
            "range_value": None if self.range_value is None else round(self.range_value, 8),
            "side_effects_authorized": False,
            "frames": [f.to_dict() for f in self.frames],
        }


def _validate_image(image: np.ndarray) -> np.ndarray:
    if not isinstance(image, np.ndarray):
        raise TypeError("image must be a numpy array")
    if image.dtype != np.uint8:
        raise ValueError("image dtype must be uint8")
    if image.ndim == 2:
        gray = image
    elif image.ndim == 3 and image.shape[2] in (3, 4):
        gray = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2GRAY)
    else:
        raise ValueError("image must be grayscale, BGR, or BGRA")
    h, w = gray.shape
    if min(h, w) < MIN_IMAGE_SIDE or max(h, w) > MAX_IMAGE_SIDE or h * w > MAX_PIXELS:
        raise ValueError("image dimensions outside bounded inspection range")
    return np.ascontiguousarray(gray)


def _circle_ring_support(gray: np.ndarray, cx: float, cy: float, radius: float) -> float:
    angles = np.linspace(0.0, 2.0 * np.pi, 180, endpoint=False)
    supports = []
    for a in angles:
        vals = []
        for dr in (-3.0, -1.5, 0.0, 1.5, 3.0):
            rr = radius + dr
            x = int(round(cx + rr * math.cos(a)))
            y = int(round(cy + rr * math.sin(a)))
            if 0 <= x < gray.shape[1] and 0 <= y < gray.shape[0]:
                vals.append(int(gray[y, x]))
        supports.append(bool(vals) and min(vals) < 120)
    return float(np.mean(supports))


def _detect_dial(gray: np.ndarray) -> tuple[float, float, float, float]:
    h, w = gray.shape
    blur = cv2.GaussianBlur(gray, (5, 5), 1.2)
    min_r = int(min(h, w) * 0.22)
    max_r = int(min(h, w) * 0.48)
    circles = cv2.HoughCircles(
        blur,
        cv2.HOUGH_GRADIENT,
        dp=1.1,
        minDist=min(h, w) * 0.25,
        param1=120,
        param2=42,
        minRadius=min_r,
        maxRadius=max_r,
    )
    if circles is None:
        raise ValueError("dial circle not found")
    candidates = []
    for cx, cy, r in circles[0][:12]:
        if r <= 0:
            continue
        # Reject circles whose fitted dial would materially leave the frame.
        if cx - r < 2 or cy - r < 2 or cx + r >= w - 2 or cy + r >= h - 2:
            continue
        support = _circle_ring_support(gray, float(cx), float(cy), float(r))
        center_penalty = math.hypot(cx - w / 2.0, cy - h / 2.0) / max(h, w)
        score = support - 0.12 * center_penalty
        candidates.append((score, support, float(cx), float(cy), float(r)))
    if not candidates:
        raise ValueError("dial circle candidates invalid")
    candidates.sort(reverse=True)
    _, support, cx, cy, r = candidates[0]
    return cx, cy, r, support


def _radial_darkness_scores(gray: np.ndarray, cx: float, cy: float, radius: float) -> tuple[np.ndarray, np.ndarray]:
    angles_deg = np.arange(0.0, 360.0, 0.5, dtype=np.float64)
    angles = np.deg2rad(angles_deg)
    radii = np.linspace(radius * 0.18, radius * 0.70, 80, dtype=np.float64)
    # Sample a narrow three-ray fan. This is robust to anti-aliasing and a few-pixel needle width.
    scores = np.zeros_like(angles_deg)
    for offset in (-0.012, 0.0, 0.012):
        aa = angles + offset
        xs = np.rint(cx + np.cos(aa)[:, None] * radii[None, :]).astype(np.int32)
        ys = np.rint(cy + np.sin(aa)[:, None] * radii[None, :]).astype(np.int32)
        xs = np.clip(xs, 0, gray.shape[1] - 1)
        ys = np.clip(ys, 0, gray.shape[0] - 1)
        sampled = gray[ys, xs].astype(np.float64)
        darkness = 255.0 - sampled
        # Weight the outer part of the needle slightly more than the hub.
        weights = np.linspace(0.35, 1.0, radii.size, dtype=np.float64)
        scores += (darkness * weights[None, :]).mean(axis=1)
    scores /= 3.0
    return angles_deg, scores


def _pointer_angle(gray: np.ndarray, cx: float, cy: float, radius: float) -> tuple[float, float, float]:
    angles, scores = _radial_darkness_scores(gray, cx, cy, radius)
    best_idx = int(np.argmax(scores))
    best_score = float(scores[best_idx])
    best_angle = float(angles[best_idx])

    exclusion = 8.0
    delta = np.abs(((angles - best_angle + 180.0) % 360.0) - 180.0)
    outside = scores[delta >= exclusion]
    second_score = float(np.max(outside)) if outside.size else 0.0
    ambiguity = second_score / max(best_score, 1e-9)
    median = float(np.median(scores))
    contrast = max(0.0, (best_score - median) / max(best_score, 1e-9))
    return best_angle, contrast, ambiguity


def analyze_frame(
    image: np.ndarray,
    calibration: Calibration,
    *,
    min_blur_score: float = 45.0,
    max_glare_fraction: float = 0.04,
    min_ring_support: float = 0.72,
    min_pointer_score: float = 0.32,
    max_pointer_ambiguity: float = 0.88,
) -> FrameReading:
    calibration.validate()
    gray = _validate_image(image)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    glare_fraction = float(np.mean(gray >= 255))

    def reject(reason: str, *, ring_support: float = 0.0, pointer_score: float = 0.0,
               ambiguity: float = 1.0, cx: float | None = None, cy: float | None = None,
               radius: float | None = None, angle: float | None = None) -> FrameReading:
        return FrameReading(
            accepted=False,
            reason=reason,
            value=None,
            unit=calibration.unit,
            pointer_angle_deg=angle,
            center_x=cx,
            center_y=cy,
            radius=radius,
            blur_score=blur_score,
            glare_fraction=glare_fraction,
            ring_support=ring_support,
            pointer_score=pointer_score,
            pointer_ambiguity_ratio=ambiguity,
        )

    if blur_score < min_blur_score:
        return reject("image_blurred")
    if glare_fraction > max_glare_fraction:
        return reject("excessive_glare")

    try:
        cx, cy, radius, ring_support = _detect_dial(gray)
    except ValueError:
        return reject("dial_not_found")
    if ring_support < min_ring_support:
        return reject("dial_occluded_or_incomplete", ring_support=ring_support, cx=cx, cy=cy, radius=radius)

    angle, pointer_score, ambiguity = _pointer_angle(gray, cx, cy, radius)
    if pointer_score < min_pointer_score:
        return reject("pointer_low_contrast", ring_support=ring_support, pointer_score=pointer_score,
                      ambiguity=ambiguity, cx=cx, cy=cy, radius=radius, angle=angle)
    if ambiguity > max_pointer_ambiguity:
        return reject("pointer_ambiguous", ring_support=ring_support, pointer_score=pointer_score,
                      ambiguity=ambiguity, cx=cx, cy=cy, radius=radius, angle=angle)
    try:
        value = calibration.angle_to_value(angle)
    except ValueError:
        return reject("pointer_outside_calibration", ring_support=ring_support, pointer_score=pointer_score,
                      ambiguity=ambiguity, cx=cx, cy=cy, radius=radius, angle=angle)

    return FrameReading(
        accepted=True,
        reason="accepted",
        value=value,
        unit=calibration.unit,
        pointer_angle_deg=angle,
        center_x=cx,
        center_y=cy,
        radius=radius,
        blur_score=blur_score,
        glare_fraction=glare_fraction,
        ring_support=ring_support,
        pointer_score=pointer_score,
        pointer_ambiguity_ratio=ambiguity,
    )


def inspect_sequence(
    frames: Iterable[np.ndarray],
    calibration: Calibration,
    *,
    min_accepted_frames: int = 3,
    max_rejected_fraction: float = 0.40,
    max_range_fraction: float = 0.04,
) -> SequenceInspection:
    calibration.validate()
    if not isinstance(min_accepted_frames, int) or isinstance(min_accepted_frames, bool) or not 1 <= min_accepted_frames <= 100:
        raise ValueError("min_accepted_frames must be an integer in [1, 100]")
    if not 0.0 <= max_rejected_fraction < 1.0:
        raise ValueError("max_rejected_fraction must be in [0, 1)")
    if not 0.0 < max_range_fraction <= 0.5:
        raise ValueError("max_range_fraction must be in (0, 0.5]")

    readings: list[FrameReading] = []
    for idx, frame in enumerate(frames):
        if idx >= 100:
            raise ValueError("sequence exceeds 100-frame bounded inspection window")
        readings.append(analyze_frame(frame, calibration))
    if not readings:
        raise ValueError("at least one frame is required")

    good = [r for r in readings if r.accepted and r.value is not None]
    rejected = len(readings) - len(good)
    if len(good) < min_accepted_frames:
        return SequenceInspection(
            decision=InspectionDecision.REINSPECT,
            reason="insufficient_accepted_frames",
            value=None,
            unit=calibration.unit,
            accepted_frames=len(good),
            rejected_frames=rejected,
            median_value=None,
            mad_value=None,
            range_value=None,
            frames=tuple(readings),
        )
    rejected_fraction = rejected / len(readings)
    vals = np.asarray([float(r.value) for r in good], dtype=np.float64)
    median = float(np.median(vals))
    mad = float(np.median(np.abs(vals - median)))
    spread = float(np.max(vals) - np.min(vals))
    max_spread = calibration.value_span * max_range_fraction

    if spread > max_spread:
        decision = InspectionDecision.ESCALATE_HUMAN
        reason = "temporal_disagreement"
        value = None
    elif rejected_fraction > max_rejected_fraction:
        decision = InspectionDecision.REINSPECT
        reason = "too_many_rejected_frames"
        value = None
    else:
        decision = InspectionDecision.ACCEPT_READING
        reason = "stable_visual_evidence"
        value = median

    return SequenceInspection(
        decision=decision,
        reason=reason,
        value=value,
        unit=calibration.unit,
        accepted_frames=len(good),
        rejected_frames=rejected,
        median_value=median,
        mad_value=mad,
        range_value=spread,
        frames=tuple(readings),
    )


def annotate_frame(image: np.ndarray, reading: FrameReading) -> np.ndarray:
    _validate_image(image)
    if image.ndim == 2:
        canvas = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    else:
        canvas = image[:, :, :3].copy()
    if reading.center_x is not None and reading.center_y is not None and reading.radius is not None:
        center = (int(round(reading.center_x)), int(round(reading.center_y)))
        cv2.circle(canvas, center, int(round(reading.radius)), (255, 255, 255), 2, cv2.LINE_AA)
        if reading.pointer_angle_deg is not None:
            a = math.radians(reading.pointer_angle_deg)
            tip = (
                int(round(center[0] + reading.radius * 0.72 * math.cos(a))),
                int(round(center[1] + reading.radius * 0.72 * math.sin(a))),
            )
            cv2.line(canvas, center, tip, (255, 255, 255), 2, cv2.LINE_AA)
    label = reading.reason
    if reading.accepted and reading.value is not None:
        label = f"{reading.value:.3f} {reading.unit}".strip()
    cv2.putText(canvas, label, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2, cv2.LINE_AA)
    return canvas
