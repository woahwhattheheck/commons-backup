"""OpenCV 5 perception adapter for ProofLens.

The adapter intentionally detects visual *change*, not people, objects, intent, or
hazard severity. A caller supplies two exact image byte strings and a source
reference. The result is a strict evidence packet consumed by prooflens.py.
"""
from __future__ import annotations

import hashlib
from typing import Any

import cv2
import numpy as np

from prooflens import ALGORITHM, sha256_json, validate_evidence

MAX_IMAGE_BYTES = 16 * 1024 * 1024
MIN_SIDE = 32
DEFAULT_MAX_SIDE = 1024


def _require_opencv5() -> None:
    try:
        major = int(cv2.__version__.split(".", 1)[0])
    except (ValueError, IndexError) as exc:
        raise RuntimeError("unable to parse OpenCV version") from exc
    if major < 5:
        raise RuntimeError(f"ProofLens requires OpenCV 5+, found {cv2.__version__}")


def _decode(data: bytes, label: str) -> np.ndarray:
    if type(data) is not bytes or not data:
        raise ValueError(f"{label} image must be non-empty bytes")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"{label} image exceeds {MAX_IMAGE_BYTES} bytes")
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"{label} is not a decodable 3-channel image")
    height, width = image.shape[:2]
    if min(height, width) < MIN_SIDE:
        raise ValueError(f"{label} dimensions are too small")
    return image


def _working_size(width: int, height: int, max_side: int) -> tuple[int, int]:
    if type(max_side) is not int or not MIN_SIDE <= max_side <= 4096:
        raise ValueError("max_side must be an integer in [32,4096]")
    scale = min(1.0, max_side / float(max(width, height)))
    return max(MIN_SIDE, int(round(width * scale))), max(MIN_SIDE, int(round(height * scale)))


def _frame_quality(gray: np.ndarray) -> float:
    clipped = np.logical_or(gray <= 5, gray >= 250)
    exposure = 1.0 - float(np.mean(clipped))
    laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    sharpness = min(1.0, max(0.0, laplacian_var / 150.0))
    return max(0.0, min(1.0, 0.55 * exposure + 0.45 * sharpness))


def _align_current(baseline_gray: np.ndarray, current_gray: np.ndarray, current_bgr: np.ndarray) -> tuple[np.ndarray, float, bool]:
    """Attempt ORB/RANSAC alignment. Failure stays explicit via confidence=0."""
    orb = cv2.ORB_create(nfeatures=1000, fastThreshold=10)
    key_a, desc_a = orb.detectAndCompute(baseline_gray, None)
    key_b, desc_b = orb.detectAndCompute(current_gray, None)
    if desc_a is None or desc_b is None or len(key_a) < 12 or len(key_b) < 12:
        return current_bgr, 0.0, False

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    pairs = matcher.knnMatch(desc_b, desc_a, k=2)
    good = []
    for pair in pairs:
        if len(pair) != 2:
            continue
        first, second = pair
        if first.distance < 0.75 * second.distance:
            good.append(first)
    if len(good) < 12:
        return current_bgr, 0.0, False

    good.sort(key=lambda match: (match.distance, match.queryIdx, match.trainIdx))
    good = good[:120]
    src = np.float32([key_b[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([key_a[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    matrix, mask = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
    if matrix is None or mask is None:
        return current_bgr, 0.0, False
    confidence = float(mask.ravel().mean())
    if not np.isfinite(confidence) or confidence < 0.25:
        return current_bgr, max(0.0, min(1.0, confidence if np.isfinite(confidence) else 0.0)), False

    height, width = baseline_gray.shape
    aligned = cv2.warpPerspective(
        current_bgr,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT101,
    )
    return aligned, max(0.0, min(1.0, confidence)), True


def analyze_pair(
    baseline_bytes: bytes,
    current_bytes: bytes,
    *,
    source_ref: str,
    max_side: int = DEFAULT_MAX_SIDE,
) -> dict[str, Any]:
    _require_opencv5()
    if type(source_ref) is not str or not source_ref.strip():
        raise ValueError("source_ref must be a non-empty string")

    baseline = _decode(baseline_bytes, "baseline")
    current = _decode(current_bytes, "current")
    base_h, base_w = baseline.shape[:2]
    cur_h, cur_w = current.shape[:2]
    base_aspect = base_w / float(base_h)
    cur_aspect = cur_w / float(cur_h)
    if abs(base_aspect - cur_aspect) / max(base_aspect, cur_aspect) > 0.01:
        raise ValueError("baseline/current aspect ratios differ by more than 1%")

    work_w, work_h = _working_size(base_w, base_h, max_side)
    baseline_work = cv2.resize(baseline, (work_w, work_h), interpolation=cv2.INTER_AREA)
    current_work = cv2.resize(current, (work_w, work_h), interpolation=cv2.INTER_AREA)
    baseline_gray = cv2.cvtColor(baseline_work, cv2.COLOR_BGR2GRAY)
    current_gray = cv2.cvtColor(current_work, cv2.COLOR_BGR2GRAY)

    aligned_bgr, alignment_confidence, aligned = _align_current(baseline_gray, current_gray, current_work)
    aligned_gray = cv2.cvtColor(aligned_bgr, cv2.COLOR_BGR2GRAY)

    baseline_blur = cv2.GaussianBlur(baseline_gray, (5, 5), 0)
    current_blur = cv2.GaussianBlur(aligned_gray, (5, 5), 0)
    diff = cv2.absdiff(baseline_blur, current_blur)
    _, mask = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
    kernel = np.ones((3, 3), dtype=np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    edges_a = cv2.Canny(baseline_gray, 80, 160)
    edges_b = cv2.Canny(aligned_gray, 80, 160)
    edge_xor = cv2.bitwise_xor(edges_a, edges_b)

    changed_fraction = float(np.count_nonzero(mask)) / float(mask.size)
    edge_delta = float(np.count_nonzero(edge_xor)) / float(edge_xor.size)
    mean_delta = float(np.mean(diff))

    quality = min(_frame_quality(baseline_gray), _frame_quality(aligned_gray))
    alignment_factor = 0.75 + (0.25 * alignment_confidence if aligned else 0.0)
    quality_score = max(0.0, min(1.0, quality * alignment_factor))

    semantic: dict[str, Any] = {
        "algorithm": ALGORITHM,
        "source_ref": source_ref,
        "baseline_sha256": hashlib.sha256(baseline_bytes).hexdigest(),
        "current_sha256": hashlib.sha256(current_bytes).hexdigest(),
        "width": int(base_w),
        "height": int(base_h),
        "changed_fraction": round(changed_fraction, 9),
        "edge_delta": round(edge_delta, 9),
        "mean_delta": round(mean_delta, 6),
        "quality_score": round(quality_score, 9),
        "alignment_confidence": round(alignment_confidence, 9),
        "opencv_version": str(cv2.__version__),
    }
    packet = dict(semantic)
    packet["event_id"] = sha256_json({k: semantic[k] for k in sorted(semantic)})
    return validate_evidence(packet)
