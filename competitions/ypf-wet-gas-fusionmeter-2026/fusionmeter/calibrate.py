"""Fit deterministic FusionMeter residual-correction certificates."""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .core import FusionMeterError, MeterSample, percentile_nearest_rank, raw_features, sha256_json


def _row(value: Mapping[str, Any]) -> tuple[MeterSample, float]:
    if set(value) != {"sample", "reference_gas_rate"}:
        raise FusionMeterError("calibration row must contain exactly sample and reference_gas_rate")
    sample_value = value["sample"]
    if not isinstance(sample_value, Mapping):
        raise FusionMeterError("sample must be an object")
    sample = MeterSample.from_mapping(sample_value)
    reference = value["reference_gas_rate"]
    if isinstance(reference, bool) or not isinstance(reference, (int, float)) or not math.isfinite(reference) or reference <= 0:
        raise FusionMeterError("reference_gas_rate must be a finite number > 0")
    return sample, float(reference)


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    n = len(rhs)
    a = [list(row) + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise FusionMeterError("calibration system is singular")
        a[col], a[pivot] = a[pivot], a[col]
        div = a[col][col]
        a[col] = [v / div for v in a[col]]
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            if factor:
                a[row] = [x - factor * y for x, y in zip(a[row], a[col])]
    return [a[i][-1] for i in range(n)]


def _fit_ridge(x: Sequence[Sequence[float]], y: Sequence[float], ridge: float) -> list[float]:
    if not x or len(x) != len(y):
        raise FusionMeterError("training design and target sizes disagree")
    width = len(x[0])
    if any(len(row) != width for row in x):
        raise FusionMeterError("ragged training design")
    xtx = [[0.0 for _ in range(width)] for _ in range(width)]
    xty = [0.0 for _ in range(width)]
    for row, target in zip(x, y):
        for i in range(width):
            xty[i] += row[i] * target
            for j in range(width):
                xtx[i][j] += row[i] * row[j]
    for i in range(1, width):
        xtx[i][i] += ridge
    return _solve(xtx, xty)


def _predict_log_overread(sample: MeterSample, means: list[float], scales: list[float], coefficients: list[float]) -> float:
    features = raw_features(sample)
    normalized = [(x - m) / s for x, m, s in zip(features, means, scales)]
    return coefficients[0] + sum(c * x for c, x in zip(coefficients[1:], normalized))


def fit_certificate(training_rows: Sequence[Mapping[str, Any]], validation_rows: Sequence[Mapping[str, Any]], *, source_sha256: str, evidence_class: str = "SYNTHETIC", ridge: float = 1e-6) -> dict[str, Any]:
    if len(training_rows) < 12:
        raise FusionMeterError("at least 12 independent training rows are required")
    if len(validation_rows) < 6:
        raise FusionMeterError("at least 6 held-out validation rows are required")
    if evidence_class not in {"SYNTHETIC", "LAB_ANALOG", "REPRESENTATIVE_POC"}:
        raise FusionMeterError("unsupported evidence_class")
    if len(source_sha256) != 64 or any(c not in "0123456789abcdef" for c in source_sha256):
        raise FusionMeterError("source_sha256 must be lowercase SHA-256 hex")
    if not math.isfinite(ridge) or ridge <= 0:
        raise FusionMeterError("ridge must be finite and > 0")
    train = [_row(row) for row in training_rows]
    valid = [_row(row) for row in validation_rows]
    feature_rows = [raw_features(sample) for sample, _ in train]
    width = len(feature_rows[0])
    means = [sum(row[i] for row in feature_rows) / len(feature_rows) for i in range(width)]
    scales = []
    for i, mean in enumerate(means):
        variance = sum((row[i] - mean) ** 2 for row in feature_rows) / len(feature_rows)
        scales.append(max(math.sqrt(variance), 1e-9))
    design = [[1.0] + [(value - mean) / scale for value, mean, scale in zip(row, means, scales)] for row in feature_rows]
    targets = [math.log(max(1.0, sample.indicated_gas_rate / reference)) for sample, reference in train]
    coefficients = _fit_ridge(design, targets, ridge)
    errors = []
    for sample, reference in valid:
        corrected = sample.indicated_gas_rate / max(1.0, math.exp(_predict_log_overread(sample, means, scales, coefficients)))
        errors.append(abs(corrected - reference) / reference * 100.0)
    all_samples = [sample for sample, _ in train + valid]
    observed = {
        "plr_excess": [s.plr_excess for s in all_samples], "density_ratio": [s.density_ratio for s in all_samples],
        "gas_froude": [s.gas_froude for s in all_samples], "beta": [s.beta for s in all_samples],
        "pressure_kgf_cm2": [s.pressure_kgf_cm2 for s in all_samples], "temperature_c": [s.temperature_c for s in all_samples],
    }
    body = {
        "schema_version": 1, "model": "log-overread-ridge-v1", "evidence_class": evidence_class,
        "feature_order": ["sqrt_plr_excess", "plr_excess", "log_density_ratio", "log_gas_froude", "beta", "sqrt_plr_excess_x_log_density_ratio"],
        "feature_means": means, "feature_scales": scales, "coefficients": coefficients,
        "domain": {name: {"min": min(values), "max": max(values)} for name, values in observed.items()},
        "validation": {"count": len(errors), "mean_abs_error_pct": sum(errors) / len(errors), "p95_abs_error_pct": percentile_nearest_rank(errors, 0.95), "max_abs_error_pct": max(errors), "independent_holdout": True, "repeatability_p95_pct": None},
        "source_sha256": source_sha256, "fit": {"ridge": ridge, "training_count": len(train)},
    }
    body["certificate_sha256"] = sha256_json(body)
    return body
