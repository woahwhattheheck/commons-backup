"""Deterministic, defensive anomaly triage over abstract numerical feature vectors.

This module deliberately knows nothing about organisms, sequences, laboratory procedures,
or biological threat construction. It is a reusable scoring kernel for challenge-shaped
numerical feature tables: learn benign-background location/scale, score deviations,
and return confidence plus human-readable feature contributions.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import math
from statistics import median
from typing import Any, Mapping, Sequence

MODEL_SCHEMA = "ready-set-id.abstract-anomaly-model.v1"
RESULT_SCHEMA = "ready-set-id.abstract-anomaly-result.v1"
_EPS = 1e-9


class ValidationError(ValueError):
    """Raised when an input violates the deterministic scoring contract."""


def _finite_number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{label} must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        raise ValidationError(f"{label} must be a finite number")
    return value


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FeatureReference:
    name: str
    center: float
    scale: float


@dataclass(frozen=True)
class DetectorModel:
    schema: str
    features: tuple[FeatureReference, ...]
    threshold: float
    baseline_rows: int
    baseline_sha256: str
    model_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "features": [asdict(feature) for feature in self.features],
            "threshold": self.threshold,
            "baseline_rows": self.baseline_rows,
            "baseline_sha256": self.baseline_sha256,
            "model_sha256": self.model_sha256,
        }


def _canonical_row(row: Mapping[str, Any], feature_names: Sequence[str]) -> dict[str, float]:
    if set(row) != set(feature_names):
        missing = sorted(set(feature_names) - set(row))
        extra = sorted(set(row) - set(feature_names))
        raise ValidationError(f"feature mismatch; missing={missing}, extra={extra}")
    return {name: _finite_number(row[name], label=f"feature {name}") for name in feature_names}


def _quantile(values: Sequence[float], q: float) -> float:
    if not values:
        raise ValidationError("quantile requires at least one value")
    if not 0.0 <= q <= 1.0:
        raise ValidationError("quantile must be within [0, 1]")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = q * (len(ordered) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    weight = pos - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


def _risk_from_zscores(zscores: Sequence[float]) -> float:
    strongest = sorted((abs(z) for z in zscores), reverse=True)[: min(3, len(zscores))]
    energy = sum(z * z for z in strongest) / len(strongest)
    return 1.0 - math.exp(-0.5 * energy)


def _references(rows: Sequence[Mapping[str, float]], feature_names: Sequence[str]) -> tuple[FeatureReference, ...]:
    refs: list[FeatureReference] = []
    for name in feature_names:
        values = [row[name] for row in rows]
        center = median(values)
        mad = median([abs(value - center) for value in values])
        scale = max(mad * 1.4826, _EPS)
        refs.append(FeatureReference(name=name, center=float(center), scale=float(scale)))
    return tuple(refs)


def _raw_score(refs: Sequence[FeatureReference], row: Mapping[str, float]) -> float:
    zscores = [(row[ref.name] - ref.center) / ref.scale for ref in refs]
    return _risk_from_zscores(zscores)


def fit_reference(
    baseline_rows: Sequence[Mapping[str, Any]],
    *,
    target_background_acceptance: float = 0.99,
) -> DetectorModel:
    """Fit a robust benign-background reference model."""
    if len(baseline_rows) < 8:
        raise ValidationError("at least 8 baseline rows are required")
    acceptance = _finite_number(target_background_acceptance, label="target_background_acceptance")
    if not 0.5 <= acceptance < 1.0:
        raise ValidationError("target_background_acceptance must be within [0.5, 1.0)")

    first = baseline_rows[0]
    if not isinstance(first, Mapping) or not first:
        raise ValidationError("baseline rows must be non-empty mappings")
    feature_names = tuple(sorted(first))
    if any(not isinstance(name, str) or not name for name in feature_names):
        raise ValidationError("feature names must be non-empty strings")

    canonical_rows = []
    for index, row in enumerate(baseline_rows):
        if not isinstance(row, Mapping):
            raise ValidationError(f"baseline row {index} must be a mapping")
        canonical_rows.append(_canonical_row(row, feature_names))

    refs = _references(canonical_rows, feature_names)
    background_scores = [_raw_score(refs, row) for row in canonical_rows]
    threshold = min(1.0, _quantile(background_scores, acceptance) + 1e-12)
    baseline_sha = canonical_sha256(canonical_rows)

    unsigned = {
        "schema": MODEL_SCHEMA,
        "features": [asdict(ref) for ref in refs],
        "threshold": threshold,
        "baseline_rows": len(canonical_rows),
        "baseline_sha256": baseline_sha,
    }
    model_sha = canonical_sha256(unsigned)
    return DetectorModel(
        schema=MODEL_SCHEMA,
        features=refs,
        threshold=threshold,
        baseline_rows=len(canonical_rows),
        baseline_sha256=baseline_sha,
        model_sha256=model_sha,
    )


def score_sample(model: DetectorModel, sample: Mapping[str, Any], *, top_k: int = 3) -> dict[str, Any]:
    """Score one abstract feature row and explain the strongest deviations."""
    if model.schema != MODEL_SCHEMA:
        raise ValidationError(f"unsupported model schema: {model.schema}")
    if not isinstance(sample, Mapping):
        raise ValidationError("sample must be a mapping")
    feature_names = tuple(ref.name for ref in model.features)
    row = _canonical_row(sample, feature_names)
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ValidationError("top_k must be a positive integer")

    contributions = []
    zscores = []
    for ref in model.features:
        z = (row[ref.name] - ref.center) / ref.scale
        zscores.append(z)
        contributions.append(
            {
                "feature": ref.name,
                "value": row[ref.name],
                "reference_center": ref.center,
                "reference_scale": ref.scale,
                "z_score": z,
                "magnitude": abs(z),
                "direction": "high" if z > 0 else "low" if z < 0 else "at_reference",
            }
        )
    contributions.sort(key=lambda item: (-item["magnitude"], item["feature"]))
    risk = _risk_from_zscores(zscores)
    flagged = risk > model.threshold
    result = {
        "schema": RESULT_SCHEMA,
        "model_sha256": model.model_sha256,
        "sample_sha256": canonical_sha256(row),
        "risk_score": risk,
        "threshold": model.threshold,
        "flagged_for_follow_on": flagged,
        "confidence": abs(risk - model.threshold),
        "explanations": contributions[: min(top_k, len(contributions))],
    }
    result["result_sha256"] = canonical_sha256(result)
    return result


def validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Fail-closed validation for provenance metadata; performs no I/O."""
    if not isinstance(manifest, Mapping):
        raise ValidationError("manifest must be a mapping")
    required = {"schema", "dataset_id", "split", "feature_names", "rows_sha256"}
    missing = sorted(required - set(manifest))
    extra = sorted(set(manifest) - required)
    if missing or extra:
        raise ValidationError(f"manifest keys invalid; missing={missing}, extra={extra}")
    if manifest["schema"] != "ready-set-id.dataset-manifest.v1":
        raise ValidationError("unsupported manifest schema")
    for key in ("dataset_id", "split"):
        if not isinstance(manifest[key], str) or not manifest[key].strip():
            raise ValidationError(f"{key} must be a non-empty string")
    names = manifest["feature_names"]
    if not isinstance(names, list) or not names or any(not isinstance(name, str) or not name for name in names):
        raise ValidationError("feature_names must be a non-empty list of strings")
    if names != sorted(names) or len(names) != len(set(names)):
        raise ValidationError("feature_names must be unique and sorted")
    digest = manifest["rows_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValidationError("rows_sha256 must be lowercase 64-hex")
    return dict(manifest)
