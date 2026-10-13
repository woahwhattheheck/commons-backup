"""Deterministic within-scan 3D feature extraction; no cohort/test fitting."""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np

from .contract import (
    EPS,
    FEATURE_NAMES,
    MAX_INPUT_VOXELS,
    MAX_WORKING_AXIS,
    ModelContractError,
)


def _as_finite_3d(volume: np.ndarray) -> np.ndarray:
    arr = np.asarray(volume, dtype=np.float32)
    if arr.ndim != 3:
        raise ModelContractError(f"volume must be 3D, got shape {arr.shape}")
    if min(arr.shape) < 4:
        raise ModelContractError(f"volume dimensions must each be >=4, got {arr.shape}")
    if arr.size > MAX_INPUT_VOXELS:
        raise ModelContractError("volume exceeds bounded input size ceiling")
    if not np.isfinite(arr).all():
        raise ModelContractError("volume contains NaN or infinity")
    return arr


def robust_normalize(volume: np.ndarray) -> np.ndarray:
    """Per-volume robust normalization to [0, 1] with no cohort statistics."""
    arr = _as_finite_3d(volume)
    lo, hi = np.percentile(arr, [1.0, 99.0])
    lo = float(lo)
    hi = float(hi)
    if not math.isfinite(lo) or not math.isfinite(hi):
        raise ModelContractError("volume percentile calculation was non-finite")
    if hi - lo <= EPS:
        return np.zeros_like(arr, dtype=np.float32)
    normalized = (arr - lo) / (hi - lo)
    return np.clip(normalized, 0.0, 1.0).astype(np.float32, copy=False)


def _foreground_crop(arr: np.ndarray) -> np.ndarray:
    """Crop obvious low-intensity margins without allocating a coordinate mesh."""
    mask = arr > 0.05
    if not bool(mask.any()):
        return arr
    active = [np.flatnonzero(np.any(mask, axis=tuple(i for i in range(3) if i != axis))) for axis in range(3)]
    slices: list[slice] = []
    for axis, indices in enumerate(active):
        if len(indices) == 0:
            return arr
        lo = max(0, int(indices[0]) - 1)
        hi = min(arr.shape[axis], int(indices[-1]) + 2)
        if hi - lo < 4:
            return arr
        slices.append(slice(lo, hi))
    return arr[tuple(slices)]


def _pool_axis(arr: np.ndarray, axis: int, max_length: int) -> np.ndarray:
    length = arr.shape[axis]
    if length <= max_length:
        return arr
    edges = np.linspace(0, length, max_length + 1, dtype=np.int64)
    pooled: list[np.ndarray] = []
    for start, stop in zip(edges[:-1], edges[1:]):
        if stop <= start:
            raise ModelContractError("deterministic pooling produced an empty bin")
        selector = [slice(None)] * 3
        selector[axis] = slice(int(start), int(stop))
        pooled.append(np.asarray(arr[tuple(selector)].mean(axis=axis), dtype=np.float32))
    return np.stack(pooled, axis=axis).astype(np.float32, copy=False)


def prepare_volume(volume: np.ndarray) -> np.ndarray:
    """Normalize, foreground-crop, and deterministically pool to a bounded working set."""
    arr = _foreground_crop(robust_normalize(volume))
    for axis in range(3):
        arr = _pool_axis(arr, axis, MAX_WORKING_AXIS)
    if arr.ndim != 3 or min(arr.shape) < 4 or max(arr.shape) > MAX_WORKING_AXIS:
        raise ModelContractError("bounded preprocessing produced an invalid working shape")
    if not np.isfinite(arr).all():
        raise ModelContractError("bounded preprocessing produced non-finite values")
    return arr


def _axis_bins(length: int, bins: int) -> list[np.ndarray]:
    if length < bins:
        raise ModelContractError(f"dimension {length} is smaller than requested {bins} bins")
    pieces = [part for part in np.array_split(np.arange(length), bins) if len(part)]
    if len(pieces) != bins:
        raise ModelContractError("adaptive binning failed to produce requested bin count")
    return pieces


def _grid_stats(arr: np.ndarray, bins: int) -> tuple[list[float], list[str]]:
    values: list[float] = []
    names: list[str] = []
    z_parts = _axis_bins(arr.shape[0], bins)
    y_parts = _axis_bins(arr.shape[1], bins)
    x_parts = _axis_bins(arr.shape[2], bins)
    total_mass = float(arr.sum(dtype=np.float64)) + EPS
    for iz, zs in enumerate(z_parts):
        for iy, ys in enumerate(y_parts):
            for ix, xs in enumerate(x_parts):
                block = arr[np.ix_(zs, ys, xs)]
                values.append(float(block.mean()))
                names.append(f"grid{bins}_mean_z{iz}y{iy}x{ix}")
                values.append(float(block.sum(dtype=np.float64) / total_mass))
                names.append(f"grid{bins}_massfrac_z{iz}y{iy}x{ix}")
    return values, names


def _weighted_moments(arr: np.ndarray) -> tuple[list[float], list[str]]:
    """Compute moments from 1D/2D marginals, avoiding full coordinate meshgrids."""
    weights = np.asarray(arr, dtype=np.float64) + EPS
    total = float(weights.sum())
    coords = [np.linspace(-1.0, 1.0, n, dtype=np.float64) for n in arr.shape]
    marginals = [
        weights.sum(axis=(1, 2)),
        weights.sum(axis=(0, 2)),
        weights.sum(axis=(0, 1)),
    ]
    means = [float(np.dot(marginal, coord) / total) for marginal, coord in zip(marginals, coords)]
    variances = [
        float(np.dot(marginal, (coord - mean) ** 2) / total)
        for marginal, coord, mean in zip(marginals, coords, means)
    ]
    dz = coords[0] - means[0]
    dy = coords[1] - means[1]
    dx = coords[2] - means[2]
    cov_zy = float(np.sum(weights.sum(axis=2) * dz[:, None] * dy[None, :]) / total)
    cov_zx = float(np.sum(weights.sum(axis=1) * dz[:, None] * dx[None, :]) / total)
    cov_yx = float(np.sum(weights.sum(axis=0) * dy[:, None] * dx[None, :]) / total)
    vals = means + variances + [cov_zy, cov_zx, cov_yx]
    names = [
        "com_z", "com_y", "com_x",
        "var_z", "var_y", "var_x",
        "cov_zy", "cov_zx", "cov_yx",
    ]
    return vals, names


def _asymmetry_features(arr: np.ndarray) -> tuple[list[float], list[str]]:
    vals: list[float] = []
    names: list[str] = []
    for axis, label in enumerate(("z", "y", "x")):
        n = arr.shape[axis]
        half = n // 2
        first_slicer = [slice(None)] * 3
        second_slicer = [slice(None)] * 3
        first_slicer[axis] = slice(0, half)
        second_slicer[axis] = slice(n - half, n)
        first = arr[tuple(first_slicer)]
        second = np.flip(arr[tuple(second_slicer)], axis=axis)
        if first.shape != second.shape:
            raise ModelContractError("asymmetry halves failed to align")
        denom = float(first.mean() + second.mean() + EPS)
        signed = float((second.mean() - first.mean()) / denom)
        absolute = float(np.mean(np.abs(second - first)))
        vals.extend([signed, absolute])
        names.extend([f"half_{label}_signed", f"half_{label}_abs"])
    return vals, names


def _gradient_features(arr: np.ndarray) -> tuple[list[float], list[str]]:
    grads = np.gradient(arr.astype(np.float32, copy=False), edge_order=1)
    mag = np.square(grads[0], dtype=np.float32)
    for grad in grads[1:]:
        mag += np.square(grad, dtype=np.float32)
    np.sqrt(mag, out=mag)
    vals = [
        float(mag.mean()),
        float(mag.std()),
        float(np.quantile(mag, 0.90)),
        float(np.quantile(mag, 0.99)),
    ]
    names = ["grad_mean", "grad_std", "grad_q90", "grad_q99"]
    return vals, names


def extract_features(volume: np.ndarray) -> tuple[np.ndarray, tuple[str, ...]]:
    """Extract a deterministic fixed-length feature vector from one 3D scan array."""
    arr = prepare_volume(volume)
    values: list[float] = []
    names: list[str] = []

    qs = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99)
    for q in qs:
        values.append(float(np.quantile(arr, q)))
        names.append(f"q{int(q * 100):02d}")
    values.extend([float(arr.mean()), float(arr.std())])
    names.extend(["mean", "std"])
    for threshold in (0.25, 0.50, 0.75, 0.90):
        values.append(float(np.mean(arr >= threshold)))
        names.append(f"fraction_ge_{threshold:.2f}")

    for bins in (2, 3):
        v, n = _grid_stats(arr, bins)
        values.extend(v)
        names.extend(n)

    for feature_fn in (_weighted_moments, _asymmetry_features, _gradient_features):
        v, n = feature_fn(arr)
        values.extend(v)
        names.extend(n)

    cutoff = float(np.quantile(arr, 0.90))
    mask = arr >= cutoff
    values.extend([float(mask.mean()), float(arr[mask].mean()) if mask.any() else 0.0])
    names.extend(["top10_volume_fraction", "top10_mean"])

    vector = np.asarray(values, dtype=np.float64)
    if vector.ndim != 1 or len(vector) != len(names):
        raise ModelContractError("feature extractor internal shape mismatch")
    if not np.isfinite(vector).all():
        raise ModelContractError("feature vector contains non-finite value")
    if len(set(names)) != len(names):
        raise ModelContractError("feature names are not unique")
    if tuple(names) != FEATURE_NAMES:
        raise ModelContractError("feature extractor drifted from the public fixed schema")
    return vector, tuple(names)


def feature_matrix(volumes: Iterable[np.ndarray]) -> tuple[np.ndarray, tuple[str, ...]]:
    rows: list[np.ndarray] = []
    schema: tuple[str, ...] | None = None
    for volume in volumes:
        vector, names = extract_features(volume)
        if schema is None:
            schema = names
        elif names != schema:
            raise ModelContractError("feature schema drifted across scans")
        rows.append(vector)
    if not rows:
        raise ModelContractError("at least one volume is required")
    matrix = np.vstack(rows)
    if not np.isfinite(matrix).all():
        raise ModelContractError("feature matrix contains non-finite value")
    return matrix, schema or ()
