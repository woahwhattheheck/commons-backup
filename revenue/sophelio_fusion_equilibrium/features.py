"""Target-blind cross-machine feature extraction."""
from __future__ import annotations
from typing import Mapping
import numpy as np
try:
    from .contract import ContractError
    from .resampling import align_mast_thomson_core, bounded_interp, _p95_scale, _unique_finite_xy
    from .coil_features import _frame_time_feature, _coil_geometry_features, _native_scalar_signal
except ImportError:
    from contract import ContractError
    from resampling import align_mast_thomson_core, bounded_interp, _p95_scale, _unique_finite_xy
    from coil_features import _frame_time_feature, _coil_geometry_features, _native_scalar_signal

def _profile_summary(times: object, profiles: object, efit_times: np.ndarray) -> np.ndarray:
    """Return six dimensionless profile summaries per EFIT frame."""
    t = np.asarray(times, dtype=np.float64).reshape(-1)
    p = np.asarray(profiles, dtype=np.float64)
    if p.ndim == 1:
        p = p[:, None]
    if p.ndim != 2 or p.shape[0] != t.size or p.shape[1] == 0:
        return np.column_stack([np.zeros((efit_times.size, 5)), np.ones(efit_times.size)])
    # Input-only, per-shot normalization is legal at inference and avoids the
    # machine-unit scale dominating zero-shot transfer.
    finite_positive = np.abs(p[np.isfinite(p)])
    scale = float(np.percentile(finite_positive, 90.0)) if finite_positive.size else 1.0
    scale = max(scale, 1e-12)
    out = np.full((efit_times.size, p.shape[1]), np.nan, dtype=np.float64)
    for j in range(p.shape[1]):
        tj, yj = _unique_finite_xy(t, p[:, j])
        if tj.size == 0:
            continue
        vals, covered = bounded_interp(tj, yj, efit_times)
        vals = np.arcsinh(vals / scale)
        vals[~covered] = np.nan
        out[:, j] = vals
    finite = np.isfinite(out)
    missing = 1.0 - np.mean(finite, axis=1)
    safe = np.where(finite, out, np.nan)
    result = np.zeros((efit_times.size, 6), dtype=np.float64)
    for i in range(efit_times.size):
        rowv = safe[i, np.isfinite(safe[i])]
        if rowv.size:
            result[i, :5] = [
                float(np.mean(rowv)),
                float(np.std(rowv)),
                float(np.quantile(rowv, 0.25)),
                float(np.quantile(rowv, 0.50)),
                float(np.quantile(rowv, 0.75)),
            ]
        result[i, 5] = missing[i]
    return result


def extract_features(row: Mapping[str, object], machine: str | None = None) -> np.ndarray:
    """Build a fixed-width, target-blind per-frame representation.

    No key beginning with ``efit_`` is read except the public input geometry and
    time axes: ``efit_times``, ``efit_grid_R`` and ``efit_grid_Z``. In
    particular ``efit_psirz``, ``efit_q95`` and ``efit_beta_n`` are ignored.
    """
    machine = str(machine or row.get("source", ""))
    if machine not in {"DIII-D", "MAST"}:
        raise ContractError(f"unsupported source machine {machine!r}")
    efit = np.asarray(row["efit_times"], dtype=np.float64).reshape(-1)
    if efit.size == 0 or not np.isfinite(efit).all():
        raise ContractError("invalid efit_times")

    blocks: list[np.ndarray] = []
    blocks.append(_frame_time_feature(efit)[:, None])
    blocks.append(_coil_geometry_features(row, efit))

    ip, ip_cov = _native_scalar_signal(row, machine, "magnetics_plasma_current", efit)
    tf_key = "magnetics_bcoil" if machine == "DIII-D" else "magnetics_tf_current"
    tf, tf_cov = _native_scalar_signal(row, machine, tf_key, efit)
    ip_s = _p95_scale(row.get("magnetics_plasma_current", ip))
    tf_s = _p95_scale(row.get(tf_key, tf))
    ipn = np.arcsinh(ip / ip_s)
    tfn = np.arcsinh(tf / tf_s)
    ratio = np.tanh(ipn / (np.abs(tfn) + 0.25))
    if efit.size > 1:
        dt = np.gradient(efit)
        dt = np.where(np.abs(dt) < 1e-9, 1.0, dt)
        dip = np.gradient(ipn) / dt
        # Normalize derivative inside the shot to make time-rate units portable.
        dip = np.arcsinh(dip / _p95_scale(dip))
    else:
        dip = np.zeros(1)
    blocks.append(np.column_stack([ipn, tfn, ratio, dip, ip_cov.astype(float), tf_cov.astype(float)]))

    # Thomson summaries: core/edge x Te/ne => 24 fixed features. MAST core's
    # ghost channel is repaired before summarization.
    for system in ("core", "edge"):
        times_key = f"thomson_{system}_times"
        if times_key not in row:
            blocks.extend([np.column_stack([np.zeros((efit.size, 5)), np.ones(efit.size)])] * 2)
            continue
        for measure in ("Te", "ne"):
            pkey = f"thomson_{system}_{measure}"
            if pkey not in row:
                blocks.append(np.column_stack([np.zeros((efit.size, 5)), np.ones(efit.size)]))
                continue
            profiles = np.asarray(row[pkey], dtype=np.float64)
            if machine == "MAST" and system == "core" and "thomson_core_R" in row:
                _, te, ne = align_mast_thomson_core(row)
                profiles = te if measure == "Te" else ne
            blocks.append(_profile_summary(row[times_key], profiles, efit))

    x = np.hstack(blocks).astype(np.float64, copy=False)
    if x.shape[1] != 46:
        raise AssertionError(f"internal feature width drifted: {x.shape}")
    if not np.isfinite(x).all():
        raise ContractError("feature extractor emitted non-finite values")
    return x


