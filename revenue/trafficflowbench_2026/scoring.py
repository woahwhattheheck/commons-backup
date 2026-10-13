from __future__ import annotations

import math
from typing import Iterable, Sequence


def _vector(values: Iterable[float], *, name: str, nonnegative: bool = False) -> list[float]:
    out = [float(v) for v in values]
    if not out:
        raise ValueError(f"{name} must be non-empty")
    if any(not math.isfinite(v) for v in out):
        raise ValueError(f"{name} contains non-finite values")
    if nonnegative and any(v < 0 for v in out):
        raise ValueError(f"{name} contains negative values")
    return out


def _same_length(*items: Sequence[object]) -> None:
    lengths = {len(item) for item in items}
    if len(lengths) != 1:
        raise ValueError(f"length mismatch: {sorted(lengths)}")


def _rmse(truth: Sequence[float], pred: Sequence[float]) -> float:
    _same_length(truth, pred)
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(truth, pred)) / len(truth))


def state_regime_score(
    true_speed_kmh: Iterable[float],
    true_flow_vph: Iterable[float],
    pred_speed_kmh: Iterable[float],
    pred_flow_vph: Iterable[float],
    lanes: Iterable[int | float],
) -> dict[str, float]:
    """Mirror the published Task 1 score for one regime/corridor slice."""
    ts = _vector(true_speed_kmh, name="true_speed_kmh", nonnegative=True)
    tf = _vector(true_flow_vph, name="true_flow_vph", nonnegative=True)
    ps = _vector(pred_speed_kmh, name="pred_speed_kmh", nonnegative=True)
    pf = _vector(pred_flow_vph, name="pred_flow_vph", nonnegative=True)
    ln = _vector(lanes, name="lanes")
    _same_length(ts, tf, ps, pf, ln)
    if any(v <= 0 or int(v) != v for v in ln):
        raise ValueError("lanes must be positive integers")
    true_lane = [f / l for f, l in zip(tf, ln)]
    pred_lane = [f / l for f, l in zip(pf, ln)]
    rmse_speed = _rmse(ts, ps)
    rmse_flow_per_lane = _rmse(true_lane, pred_lane)
    s_speed = max(0.0, 1.0 - rmse_speed / 25.0)
    s_flow = max(0.0, 1.0 - rmse_flow_per_lane / 600.0)
    return {
        "rmse_speed": rmse_speed,
        "rmse_flow_per_lane": rmse_flow_per_lane,
        "S_speed": s_speed,
        "S_flow": s_flow,
        "S_state": 0.54 * s_speed + 0.46 * s_flow,
    }


def queue_iou(true_queue: Iterable[int | bool], pred_queue: Iterable[int | bool]) -> float:
    truth = [int(v) for v in true_queue]
    pred = [int(v) for v in pred_queue]
    if not truth:
        raise ValueError("queue window must be non-empty")
    _same_length(truth, pred)
    if any(v not in (0, 1) for v in truth + pred):
        raise ValueError("queue values must be binary")
    inter = sum(a & b for a, b in zip(truth, pred))
    union = sum(a | b for a, b in zip(truth, pred))
    return 1.0 if union == 0 else inter / union


def physics_score(fd_score: float, lwr_score: float) -> float:
    """Published Task 3 aggregation, for already-derived local diagnostic terms."""
    fd = float(fd_score)
    lwr = float(lwr_score)
    if not (math.isfinite(fd) and math.isfinite(lwr) and 0 <= fd <= 1 and 0 <= lwr <= 1):
        raise ValueError("physics components must be finite values in [0, 1]")
    return (fd / 3.0) + (2.0 * lwr / 3.0)


def _matvec(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> list[float]:
    if any(len(row) != len(vector) for row in matrix):
        raise ValueError("matrix/vector dimension mismatch")
    return [sum(float(a) * float(v) for a, v in zip(row, vector)) for row in matrix]


def _l1_ratio(error: float, denom: float, eps: float = 1e-12) -> float:
    return max(0.0, 1.0 - error / max(denom, eps))


def odme_score(
    truth_path_flow: Iterable[float],
    pred_path_flow: Iterable[float],
    incidence: Sequence[Sequence[float]],
    link_counts: Iterable[float],
    weak_prior: Iterable[float],
    destination_ids: Sequence[str],
) -> dict[str, float]:
    """Mirror Task 4 on local synthetic/public-train truth only.

    The official hidden reference is never fabricated by this package.
    """
    truth = _vector(truth_path_flow, name="truth_path_flow", nonnegative=True)
    pred = _vector(pred_path_flow, name="pred_path_flow", nonnegative=True)
    prior = _vector(weak_prior, name="weak_prior", nonnegative=True)
    counts = _vector(link_counts, name="link_counts", nonnegative=True)
    _same_length(truth, pred, prior, destination_ids)
    if len(incidence) != len(counts):
        raise ValueError("incidence rows must match link_counts")
    link_pred = _matvec(incidence, pred)
    s_od = _l1_ratio(sum(abs(a - b) for a, b in zip(pred, truth)), sum(truth))
    s_link = _l1_ratio(sum(abs(a - b) for a, b in zip(link_pred, counts)), sum(counts))
    d_hat = sum(abs(a - b) for a, b in zip(pred, prior))
    d_star = sum(abs(a - b) for a, b in zip(truth, prior))
    if d_star <= 1e-12:
        s_dev = 1.0 if d_hat <= 1e-12 else 0.0
    else:
        s_dev = math.exp(-abs(d_hat / d_star - 1.0))
    dests = sorted(set(destination_ids))
    total_truth = sum(truth)
    total_pred = sum(pred)
    if total_truth <= 0 or total_pred <= 0:
        s_attr = 1.0 if total_truth == total_pred == 0 else 0.0
    else:
        truth_attr = {d: 0.0 for d in dests}
        pred_attr = {d: 0.0 for d in dests}
        for d, t, p in zip(destination_ids, truth, pred):
            truth_attr[d] += t / total_truth
            pred_attr[d] += p / total_pred
        l1 = sum(abs(truth_attr[d] - pred_attr[d]) for d in dests)
        s_attr = max(0.0, 1.0 - 0.5 * l1)
    score = 0.45 * s_od + 0.25 * s_link + 0.15 * s_dev + 0.15 * s_attr
    return {"S_od": s_od, "S_link": s_link, "S_dev": s_dev, "S_attr": s_attr, "S_ODME": score}


def total_score(state: float, queue: float, physics: float, odme: float) -> float:
    parts = [float(state), float(queue), float(physics), float(odme)]
    if any(not math.isfinite(v) or v < 0 or v > 1 for v in parts):
        raise ValueError("task scores must be finite values in [0, 1]")
    return 0.35 * parts[0] + 0.30 * parts[1] + 0.15 * parts[2] + 0.20 * parts[3]
