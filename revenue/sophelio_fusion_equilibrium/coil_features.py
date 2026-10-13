"""Cross-machine coil and scalar-current feature primitives."""
from __future__ import annotations
from typing import Mapping
import numpy as np
try:
    from .contract import ContractError
    from .resampling import bounded_interp, repair_d3d_ip_times, _p95_scale
except ImportError:
    from contract import ContractError
    from resampling import bounded_interp, repair_d3d_ip_times, _p95_scale

def _normalize_coord(a: np.ndarray, lo: float, hi: float) -> np.ndarray:
    span = float(hi - lo)
    if not np.isfinite(span) or span <= 0:
        raise ContractError("degenerate physical grid")
    return 2.0 * (a - lo) / span - 1.0


def _frame_time_feature(efit_times: np.ndarray) -> np.ndarray:
    if efit_times.size == 1:
        return np.zeros(1, dtype=np.float64)
    lo, hi = float(np.min(efit_times)), float(np.max(efit_times))
    if hi <= lo:
        return np.zeros(efit_times.size, dtype=np.float64)
    return 2.0 * (efit_times - lo) / (hi - lo) - 1.0


def _coil_geometry_features(row: Mapping[str, object], efit_times: np.ndarray) -> np.ndarray:
    required = ("coil_input_column", "coil_R", "coil_Z", "efit_grid_R", "efit_grid_Z")
    if not all(k in row for k in required):
        return np.zeros((efit_times.size, 15), dtype=np.float64)
    columns = np.asarray(row["coil_input_column"], dtype=str).reshape(-1)
    rr = np.asarray(row["coil_R"], dtype=np.float64).reshape(-1)
    zz = np.asarray(row["coil_Z"], dtype=np.float64).reshape(-1)
    if not (columns.size == rr.size == zz.size) or columns.size == 0:
        raise ContractError("coil geometry arrays disagree")
    grid_r = np.asarray(row["efit_grid_R"], dtype=np.float64).reshape(-1)
    grid_z = np.asarray(row["efit_grid_Z"], dtype=np.float64).reshape(-1)
    rn = _normalize_coord(rr, float(np.min(grid_r)), float(np.max(grid_r)))
    zn = _normalize_coord(zz, float(np.min(grid_z)), float(np.max(grid_z)))
    native_t = np.asarray(row.get("magnetics_time", []), dtype=np.float64)

    unique_cols = sorted({c for c in columns if c in row})
    if not unique_cols:
        return np.zeros((efit_times.size, 15), dtype=np.float64)

    native_scales = [_p95_scale(row[c]) for c in unique_cols]
    global_scale = float(np.median(native_scales)) if native_scales else 1.0
    global_scale = max(global_scale, 1e-12)
    currents: list[np.ndarray] = []
    coverages: list[np.ndarray] = []
    bases: list[np.ndarray] = []
    for col in unique_cols:
        vals = np.asarray(row[col], dtype=np.float64).reshape(-1)
        # Geometry-bound coil currents use the shared magnetics axis in the
        # released schema. Columns with incompatible lengths are skipped rather
        # than aligned to a guessed clock.
        if vals.size != native_t.size:
            continue
        resampled, covered = bounded_interp(native_t, vals, efit_times)
        currents.append(np.arcsinh(resampled / global_scale))
        coverages.append(covered.astype(np.float64))
        mask = columns == col
        # Average each current column over its own conductor elements. This is
        # deliberate: MAST may represent one powered coil with many conductor
        # rows, and summing would count that source multiple times.
        rbar = float(np.mean(rn[mask]))
        zbar = float(np.mean(zn[mask]))
        bases.append(np.array([1.0, rbar, zbar, rbar*rbar, zbar*zbar, rbar*zbar]))
    if not currents:
        return np.zeros((efit_times.size, 15), dtype=np.float64)
    c = np.column_stack(currents)  # T x C
    cov = np.column_stack(coverages)
    b = np.vstack(bases)  # C x 6
    signed = c @ b / c.shape[1]
    magnitude = np.abs(c) @ np.abs(b) / c.shape[1]
    spread = np.std(c, axis=1, keepdims=True)
    coverage = np.mean(cov, axis=1, keepdims=True)
    active = np.mean(np.abs(c) > 0.05, axis=1, keepdims=True)
    return np.hstack([signed, magnitude, spread, coverage, active])


def _native_scalar_signal(
    row: Mapping[str, object], machine: str, key: str, efit_times: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    if key not in row:
        return np.zeros(efit_times.size), np.zeros(efit_times.size, dtype=bool)
    values = np.asarray(row[key], dtype=np.float64).reshape(-1)
    if key == "magnetics_plasma_current" and machine == "DIII-D" and "magnetics_plasma_current_times" in row:
        times = repair_d3d_ip_times(row)
    else:
        times = np.asarray(row.get("magnetics_time", []), dtype=np.float64).reshape(-1)
    if times.size != values.size:
        return np.zeros(efit_times.size), np.zeros(efit_times.size, dtype=bool)
    return bounded_interp(times, values, efit_times)


