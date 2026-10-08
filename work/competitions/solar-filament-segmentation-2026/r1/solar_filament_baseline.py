"""Public-safe baseline/evaluator for Solar Filament Segmentation Challenge 2026.

This module is intentionally dataset-agnostic: it operates on in-memory grayscale arrays.
An authenticated competition seat can connect MAGFiLO image/mask loading without changing
segmentation or metric semantics.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Iterable

import numpy as np

def robust_unit_scale(image: np.ndarray, low_q: float = 0.01, high_q: float = 0.99) -> np.ndarray:
    x = np.asarray(image, dtype=np.float32)
    if x.ndim != 2:
        raise ValueError("expected a 2D grayscale image")
    lo = float(np.quantile(x, low_q))
    hi = float(np.quantile(x, high_q))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return np.zeros_like(x, dtype=np.float32)
    return np.clip((x - lo) / (hi - lo), 0.0, 1.0)

def _neighbor_count(mask: np.ndarray, radius: int = 1) -> np.ndarray:
    m = np.asarray(mask, dtype=np.uint8)
    padded = np.pad(m, radius, mode="constant")
    out = np.zeros_like(m, dtype=np.uint16)
    h, w = m.shape
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx == 0 and dy == 0:
                continue
            out += padded[radius + dy:radius + dy + h, radius + dx:radius + dx + w]
    return out

def majority_cleanup(mask: np.ndarray, passes: int = 1) -> np.ndarray:
    """Remove isolated noise and bridge one-pixel gaps with deterministic local voting."""
    out = np.asarray(mask, dtype=bool).copy()
    for _ in range(passes):
        n = _neighbor_count(out)
        out = (out & (n >= 2)) | (~out & (n >= 5))
    return out

def connected_components(mask: np.ndarray, min_area: int = 8) -> np.ndarray:
    """8-connected component labels; 0 is background, instances are 1..N by scan order."""
    m = np.asarray(mask, dtype=bool)
    if m.ndim != 2:
        raise ValueError("expected a 2D mask")
    h, w = m.shape
    seen = np.zeros((h, w), dtype=bool)
    labels = np.zeros((h, w), dtype=np.int32)
    next_label = 1
    for y in range(h):
        for x in range(w):
            if not m[y, x] or seen[y, x]:
                continue
            q = deque([(y, x)])
            seen[y, x] = True
            pixels: list[tuple[int, int]] = []
            while q:
                cy, cx = q.popleft()
                pixels.append((cy, cx))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w and m[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            q.append((ny, nx))
            if len(pixels) >= min_area:
                for py, px in pixels:
                    labels[py, px] = next_label
                next_label += 1
    return labels

def segment_dark_filaments(
    image: np.ndarray,
    dark_quantile: float = 0.16,
    min_area: int = 12,
    cleanup_passes: int = 1,
) -> np.ndarray:
    """Model-free baseline: robust scale -> dark-tail mask -> local cleanup -> instances.

    Solar filaments are dark H-alpha structures. This baseline is deliberately simple so
    the first data-bearing receipt tells us whether morphology/normalization is worth
    keeping before spending inference budget on a learned model.
    """
    if not 0.0 < dark_quantile < 0.5:
        raise ValueError("dark_quantile must be in (0, 0.5)")
    scaled = robust_unit_scale(image)
    threshold = float(np.quantile(scaled, dark_quantile))
    mask = scaled <= threshold
    if cleanup_passes:
        mask = majority_cleanup(mask, cleanup_passes)
    return connected_components(mask, min_area=min_area)

def _ids(x: np.ndarray) -> list[int]:
    return [int(v) for v in np.unique(x) if int(v) != 0]

def _iou(pred: np.ndarray, truth: np.ndarray, pid: int, tid: int) -> float:
    p = pred == pid
    t = truth == tid
    inter = int(np.count_nonzero(p & t))
    if inter == 0:
        return 0.0
    union = int(np.count_nonzero(p | t))
    return inter / union if union else 0.0

@dataclass(frozen=True)
class PQResult:
    pq: float
    sq: float
    rq: float
    tp: int
    fp: int
    fn: int
    mean_matched_iou: float
    dice_foreground: float
    fragmentation_count: int
    overmerge_count: int

def panoptic_quality(pred: np.ndarray, truth: np.ndarray, match_iou: float = 0.5) -> PQResult:
    """Standard class-agnostic PQ for non-overlapping instance maps.

    Matching at IoU > 0.5 is unambiguous for non-overlapping panoptic segments, so no
    assignment solver is necessary. This local implementation MUST be cross-checked against
    the organizer self-evaluation notebook before any competition-performance claim.
    """
    pred = np.asarray(pred, dtype=np.int32)
    truth = np.asarray(truth, dtype=np.int32)
    if pred.shape != truth.shape or pred.ndim != 2:
        raise ValueError("pred and truth must be same-shape 2D instance maps")
    pids, tids = _ids(pred), _ids(truth)
    pair_iou: dict[tuple[int, int], float] = {}
    overlaps_by_pred: dict[int, int] = {p: 0 for p in pids}
    overlaps_by_truth: dict[int, int] = {t: 0 for t in tids}
    matches: list[tuple[int, int, float]] = []
    for p in pids:
        for t in tids:
            score = _iou(pred, truth, p, t)
            if score > 0.0:
                pair_iou[p, t] = score
                overlaps_by_pred[p] += 1
                overlaps_by_truth[t] += 1
            if score > match_iou:
                matches.append((p, t, score))

    matched_p = {p for p, _, _ in matches}
    matched_t = {t for _, t, _ in matches}
    tp = len(matches)
    fp = len(pids) - len(matched_p)
    fn = len(tids) - len(matched_t)
    sum_iou = float(sum(s for _, _, s in matches))
    denom = tp + 0.5 * fp + 0.5 * fn
    pq = sum_iou / denom if denom else 1.0
    sq = sum_iou / tp if tp else (1.0 if not pids and not tids else 0.0)
    rq = tp / denom if denom else 1.0

    pfg = pred > 0
    tfg = truth > 0
    inter = int(np.count_nonzero(pfg & tfg))
    dice_denom = int(np.count_nonzero(pfg)) + int(np.count_nonzero(tfg))
    dice = (2.0 * inter / dice_denom) if dice_denom else 1.0

    fragmentation = sum(max(0, n - 1) for n in overlaps_by_truth.values())
    overmerge = sum(max(0, n - 1) for n in overlaps_by_pred.values())
    return PQResult(
        pq=pq,
        sq=sq,
        rq=rq,
        tp=tp,
        fp=fp,
        fn=fn,
        mean_matched_iou=sq,
        dice_foreground=dice,
        fragmentation_count=int(fragmentation),
        overmerge_count=int(overmerge),
    )

def evaluate_cases(cases: Iterable[tuple[str, np.ndarray, np.ndarray]]) -> dict:
    """Evaluate named (image, truth-instance-map) cases and emit a deterministic receipt."""
    per_case = []
    latencies_ms = []
    for name, image, truth in cases:
        t0 = perf_counter()
        pred = segment_dark_filaments(image)
        latency_ms = (perf_counter() - t0) * 1000.0
        latencies_ms.append(latency_ms)
        metrics = panoptic_quality(pred, truth)
        per_case.append({"name": name, "latency_ms": round(latency_ms, 6), **asdict(metrics)})
    if not per_case:
        raise ValueError("at least one case required")
    return {
        "schema": "solar-filament-baseline-r1",
        "n_cases": len(per_case),
        "mean_pq": float(np.mean([x["pq"] for x in per_case])),
        "mean_dice": float(np.mean([x["dice_foreground"] for x in per_case])),
        "total_fragmentation": int(sum(x["fragmentation_count"] for x in per_case)),
        "total_overmerge": int(sum(x["overmerge_count"] for x in per_case)),
        "latency_ms_median": float(np.median(latencies_ms)),
        "latency_ms_p95": float(np.quantile(latencies_ms, 0.95)),
        "cases": per_case,
    }
