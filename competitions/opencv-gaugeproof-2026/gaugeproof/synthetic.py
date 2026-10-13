from __future__ import annotations

import math
from typing import Iterable

import cv2
import numpy as np

from .core import Calibration


def value_to_angle(value: float, calibration: Calibration) -> float:
    calibration.validate()
    if not math.isfinite(float(value)):
        raise ValueError("value must be finite")
    t = (float(value) - calibration.min_value) / calibration.value_span
    if not 0.0 <= t <= 1.0:
        raise ValueError("value outside calibration range")
    return calibration.min_angle_deg + t * (calibration.max_angle_deg - calibration.min_angle_deg)


def render_gauge(
    value: float,
    calibration: Calibration,
    *,
    size: int = 512,
    center: tuple[int, int] | None = None,
    radius: int | None = None,
    blur_sigma: float = 0.0,
    glare: bool = False,
    occlusion_fraction: float = 0.0,
    second_pointer_value: float | None = None,
) -> np.ndarray:
    calibration.validate()
    if not isinstance(size, int) or isinstance(size, bool) or not 240 <= size <= 1600:
        raise ValueError("size must be an integer in [240, 1600]")
    if not 0.0 <= float(occlusion_fraction) <= 0.8:
        raise ValueError("occlusion_fraction must be in [0, 0.8]")
    if not math.isfinite(float(blur_sigma)) or blur_sigma < 0 or blur_sigma > 20:
        raise ValueError("blur_sigma outside supported range")
    cx, cy = center or (size // 2, size // 2)
    r = radius or int(size * 0.39)
    if r < 70 or cx - r < 8 or cy - r < 8 or cx + r >= size - 8 or cy + r >= size - 8:
        raise ValueError("gauge geometry must fit inside image")

    img = np.full((size, size, 3), 238, dtype=np.uint8)
    # A light dial face against a slightly darker background helps ring localization.
    cv2.circle(img, (cx, cy), r, (252, 252, 252), -1, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), r, (24, 24, 24), 5, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), int(r * 0.97), (120, 120, 120), 1, cv2.LINE_AA)

    # Major ticks stay outside the pointer-scoring annulus.
    for i in range(11):
        a = calibration.min_angle_deg + i / 10.0 * (calibration.max_angle_deg - calibration.min_angle_deg)
        ar = math.radians(a % 360.0)
        p1 = (int(round(cx + r * 0.79 * math.cos(ar))), int(round(cy + r * 0.79 * math.sin(ar))))
        p2 = (int(round(cx + r * 0.91 * math.cos(ar))), int(round(cy + r * 0.91 * math.sin(ar))))
        cv2.line(img, p1, p2, (35, 35, 35), 3, cv2.LINE_AA)

    def draw_pointer(v: float, thickness: int = 7) -> None:
        a = math.radians(value_to_angle(v, calibration) % 360.0)
        tip = (int(round(cx + r * 0.70 * math.cos(a))), int(round(cy + r * 0.70 * math.sin(a))))
        tail = (int(round(cx - r * 0.10 * math.cos(a))), int(round(cy - r * 0.10 * math.sin(a))))
        cv2.line(img, tail, tip, (10, 10, 10), thickness, cv2.LINE_AA)

    draw_pointer(value)
    if second_pointer_value is not None:
        draw_pointer(second_pointer_value, 7)
    cv2.circle(img, (cx, cy), int(r * 0.055), (18, 18, 18), -1, cv2.LINE_AA)

    if occlusion_fraction > 0:
        width = max(1, int(round(2 * r * occlusion_fraction)))
        x0 = max(0, cx + r // 3)
        cv2.rectangle(img, (x0, max(0, cy - r - 10)), (min(size - 1, x0 + width), min(size - 1, cy + r + 10)), (238, 238, 238), -1)
    if glare:
        cv2.ellipse(img, (cx - r // 3, cy - r // 3), (int(r * 0.43), int(r * 0.30)), -25, 0, 360, (255, 255, 255), -1, cv2.LINE_AA)
    if blur_sigma > 0:
        k = int(max(3, 2 * round(blur_sigma * 3) + 1))
        img = cv2.GaussianBlur(img, (k, k), blur_sigma)
    return img


def render_sequence(values: Iterable[float], calibration: Calibration, **kwargs) -> list[np.ndarray]:
    return [render_gauge(v, calibration, **kwargs) for v in values]
