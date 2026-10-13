"""Shot grouping, organizer errata repairs, and bounded resampling."""
from __future__ import annotations
from hashlib import sha256
from typing import Mapping, Sequence
import numpy as np
try:
    from .contract import BREAKDOWN_WINDOW_MS, ContractError, Fold
except ImportError:
    from contract import BREAKDOWN_WINDOW_MS, ContractError, Fold

def _stable_u64(text: str, seed: int = 0) -> int:
    h = sha256(f"{seed}\0{text}".encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big", signed=False)


def shot_group_folds(shot_ids: Sequence[str], n_splits: int = 5, seed: int = 42) -> list[Fold]:
    """Deterministically assign *whole shots* to folds.

    Repeated frame-level IDs are allowed in ``shot_ids``; they are collapsed
    before assignment.  A shot can therefore never straddle train/validation.
    """
    unique = sorted({str(s) for s in shot_ids})
    if n_splits < 2:
        raise ValueError("n_splits must be >= 2")
    if len(unique) < n_splits:
        raise ValueError("need at least n_splits distinct shots")
    ordered = sorted(unique, key=lambda s: (_stable_u64(s, seed), s))
    buckets: list[list[str]] = [[] for _ in range(n_splits)]
    for i, shot in enumerate(ordered):
        buckets[i % n_splits].append(shot)
    all_set = set(unique)
    folds: list[Fold] = []
    for valid in buckets:
        v = tuple(sorted(valid))
        t = tuple(sorted(all_set.difference(valid)))
        if set(t).intersection(v):
            raise AssertionError("shot leakage in fold planner")
        folds.append(Fold(t, v))
    return folds


def repair_d3d_ip_times(row: Mapping[str, object]) -> np.ndarray:
    """Organizer-compatible v1.1.0 DIII-D plasma-current time-axis repair.

    This intentionally mirrors the starter's ``fix_d3d_ip_times`` decision.
    It does *not* blanket-shift every DIII-D shot.
    """
    ipt = np.asarray(row["magnetics_plasma_current_times"], dtype=np.float64)
    ip = np.abs(np.asarray(row["magnetics_plasma_current"], dtype=np.float64))
    shared = np.asarray(row["magnetics_time"], dtype=np.float64)
    if ipt.ndim != 1 or ip.ndim != 1 or ipt.size != ip.size or ipt.size == 0:
        raise ContractError("invalid DIII-D Ip arrays")
    finite = np.isfinite(ip)
    if not finite.any():
        raise ContractError("DIII-D Ip contains no finite values")
    threshold = 0.10 * float(np.nanpercentile(ip, 99.5))
    crossing = np.flatnonzero(ip > threshold)
    if crossing.size == 0:
        raise ContractError("cannot locate DIII-D plasma breakdown")
    breakdown = float(ipt[int(crossing[0])])
    lo, hi = BREAKDOWN_WINDOW_MS
    if lo <= breakdown <= hi:
        return ipt.copy()
    if shared.ndim != 1 or shared.size == 0 or not np.isfinite(shared[0]):
        raise ContractError("invalid shared magnetics axis")
    return float(shared[0]) + (ipt - ipt[0])


def align_mast_thomson_core(row: Mapping[str, object]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Drop MAST's known uncalibrated Thomson channel zero when present."""
    r = np.asarray(row["thomson_core_R"], dtype=np.float64)
    te = np.asarray(row["thomson_core_Te"], dtype=np.float64)
    ne = np.asarray(row["thomson_core_ne"], dtype=np.float64)
    if te.ndim != 2 or ne.ndim != 2 or te.shape != ne.shape:
        raise ContractError("unexpected Thomson core profile shape")
    if te.shape[1] == r.size:
        return r, te, ne
    if te.shape[1] != r.size + 1:
        raise ContractError(
            f"unexpected Thomson core layout: {r.size} coordinates vs {te.shape[1]} channels"
        )
    return r, te[:, 1:], ne[:, 1:]


def _unique_finite_xy(times: object, values: object) -> tuple[np.ndarray, np.ndarray]:
    t = np.asarray(times, dtype=np.float64).reshape(-1)
    y = np.asarray(values, dtype=np.float64).reshape(-1)
    if t.size != y.size:
        raise ContractError("time/value length mismatch")
    good = np.isfinite(t) & np.isfinite(y)
    t, y = t[good], y[good]
    if t.size == 0:
        return t, y
    order = np.argsort(t, kind="stable")
    t, y = t[order], y[order]
    # Merge duplicate timestamps by arithmetic mean. np.interp requires an
    # increasing grid and silently ambiguous duplicates are too risky here.
    uniq, first, counts = np.unique(t, return_index=True, return_counts=True)
    if np.any(counts > 1):
        sums = np.add.reduceat(y, first)
        y = sums / counts
        t = uniq
    return t, y


def bounded_interp(times: object, values: object, targets: object) -> tuple[np.ndarray, np.ndarray]:
    """Interpolate one signal onto target times without fabricating slope extrapolation.

    The returned coverage mask is true only where the target lies inside the
    finite native time range.  Outside it we hold the nearest endpoint so model
    inputs stay finite while the companion coverage feature makes the condition
    explicit.
    """
    target = np.asarray(targets, dtype=np.float64).reshape(-1)
    if not np.isfinite(target).all():
        raise ContractError("target times must be finite")
    t, y = _unique_finite_xy(times, values)
    if t.size == 0:
        return np.zeros(target.size, dtype=np.float64), np.zeros(target.size, dtype=bool)
    if t.size == 1:
        return np.full(target.size, y[0], dtype=np.float64), target == t[0]
    out = np.interp(target, t, y)
    covered = (target >= t[0]) & (target <= t[-1])
    return out, covered


def _p95_scale(values: object, floor: float = 1e-12) -> float:
    a = np.asarray(values, dtype=np.float64).reshape(-1)
    a = np.abs(a[np.isfinite(a)])
    if a.size == 0:
        return 1.0
    v = float(np.percentile(a, 95.0))
    return max(v, floor)


def balanced_frame_indices(shot_ids: Sequence[str], max_per_shot: int = 48, seed: int = 42) -> np.ndarray:
    """Bound each shot's contribution so long discharges cannot dominate PCA."""
    ids = np.asarray([str(s) for s in shot_ids], dtype=object)
    if max_per_shot < 1:
        raise ValueError("max_per_shot must be positive")
    chosen: list[int] = []
    for shot in sorted(set(ids.tolist())):
        idx = np.flatnonzero(ids == shot)
        if idx.size <= max_per_shot:
            chosen.extend(idx.tolist())
            continue
        rng = np.random.default_rng(_stable_u64(shot, seed))
        take = np.sort(rng.choice(idx, size=max_per_shot, replace=False))
        chosen.extend(take.tolist())
    return np.asarray(sorted(chosen), dtype=np.int64)


