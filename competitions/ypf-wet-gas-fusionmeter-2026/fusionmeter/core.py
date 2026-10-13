"""Deterministic wet-gas correction scaffold for the FusionMeter proposal.

The module is intentionally conservative: a model may correct an indicated gas
rate only inside the condition envelope recorded in its calibration certificate.
Nothing in this module asserts that the synthetic demonstration meets YPF's
field accuracy target.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Any, Iterable, Mapping


class FusionMeterError(ValueError):
    """Base class for invalid or unsupported measurement state."""


class OutOfDomainError(FusionMeterError):
    """Raised when a sample leaves the evidence-backed calibration envelope."""


@dataclass(frozen=True)
class MeterSample:
    indicated_gas_rate: float
    primary_dp_kpa: float
    permanent_loss_kpa: float
    dry_plr_reference: float
    density_ratio: float
    gas_froude: float
    beta: float
    pressure_kgf_cm2: float
    temperature_c: float
    indication_uncertainty_pct: float = 1.0
    sensor_health: bool = True

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MeterSample":
        allowed = set(cls.__dataclass_fields__)
        extra = sorted(set(value) - allowed)
        # Dataclass defaults are handled by the constructor; report unknown keys only.
        if extra:
            raise FusionMeterError(f"unknown sample fields: {', '.join(extra)}")
        try:
            sample = cls(**value)
        except TypeError as exc:
            raise FusionMeterError(str(exc)) from exc
        sample.validate()
        return sample

    def validate(self) -> None:
        positive = {
            "indicated_gas_rate": self.indicated_gas_rate,
            "primary_dp_kpa": self.primary_dp_kpa,
            "density_ratio": self.density_ratio,
            "gas_froude": self.gas_froude,
            "pressure_kgf_cm2": self.pressure_kgf_cm2,
        }
        for name, value in positive.items():
            _require_finite(name, value)
            if value <= 0:
                raise FusionMeterError(f"{name} must be > 0")
        for name, value in {
            "permanent_loss_kpa": self.permanent_loss_kpa,
            "dry_plr_reference": self.dry_plr_reference,
            "temperature_c": self.temperature_c,
            "indication_uncertainty_pct": self.indication_uncertainty_pct,
            "beta": self.beta,
        }.items():
            _require_finite(name, value)
        if self.permanent_loss_kpa < 0:
            raise FusionMeterError("permanent_loss_kpa must be >= 0")
        if not 0 < self.dry_plr_reference < 1:
            raise FusionMeterError("dry_plr_reference must be between 0 and 1")
        if not 0 < self.beta < 1:
            raise FusionMeterError("beta must be between 0 and 1")
        if self.indication_uncertainty_pct < 0:
            raise FusionMeterError("indication_uncertainty_pct must be >= 0")
        if not isinstance(self.sensor_health, bool):
            raise FusionMeterError("sensor_health must be boolean")
        if self.plr >= 1:
            raise FusionMeterError("permanent-loss ratio must be < 1")

    @property
    def plr(self) -> float:
        return self.permanent_loss_kpa / self.primary_dp_kpa

    @property
    def plr_excess(self) -> float:
        return max(0.0, self.plr - self.dry_plr_reference)


def _require_finite(name: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise FusionMeterError(f"{name} must be a finite number")


def raw_features(sample: MeterSample) -> list[float]:
    """Return observable, dimensionless features used by the residual model.

    PLR excess is the measured permanent-pressure-loss ratio above the meter's
    dry-gas reference. Density ratio, gas Froude number, and beta ratio describe
    pressure/phase-slip, velocity, and geometry sensitivity without requiring a
    hidden liquid-rate input at inference time.
    """
    sample.validate()
    return [
        math.sqrt(sample.plr_excess),
        sample.plr_excess,
        math.log(sample.density_ratio),
        math.log(sample.gas_froude),
        sample.beta,
        math.sqrt(sample.plr_excess) * math.log(sample.density_ratio),
    ]


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate_certificate(certificate: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "evidence_class",
        "feature_means",
        "feature_scales",
        "coefficients",
        "domain",
        "validation",
        "source_sha256",
        "certificate_sha256",
    }
    missing = sorted(required - set(certificate))
    if missing:
        raise FusionMeterError(f"certificate missing: {', '.join(missing)}")
    if certificate["schema_version"] != 1:
        raise FusionMeterError("unsupported certificate schema_version")
    means = certificate["feature_means"]
    scales = certificate["feature_scales"]
    coeffs = certificate["coefficients"]
    if not isinstance(means, list) or not isinstance(scales, list) or not isinstance(coeffs, list):
        raise FusionMeterError("certificate features/coefficients must be lists")
    if len(means) != len(scales) or len(coeffs) != len(means) + 1:
        raise FusionMeterError("certificate feature dimensions disagree")
    for idx, value in enumerate(means):
        _require_finite(f"feature_means[{idx}]", value)
    for idx, value in enumerate(scales):
        _require_finite(f"feature_scales[{idx}]", value)
        if value <= 0:
            raise FusionMeterError("feature scales must be > 0")
    for idx, value in enumerate(coeffs):
        _require_finite(f"coefficients[{idx}]", value)
    digest = certificate["source_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise FusionMeterError("source_sha256 must be lowercase SHA-256 hex")
    body = dict(certificate)
    claimed = body.pop("certificate_sha256")
    if not isinstance(claimed, str) or claimed != sha256_json(body):
        raise FusionMeterError("certificate_sha256 mismatch")


def _domain_values(sample: MeterSample) -> dict[str, float]:
    return {
        "plr_excess": sample.plr_excess,
        "density_ratio": sample.density_ratio,
        "gas_froude": sample.gas_froude,
        "beta": sample.beta,
        "pressure_kgf_cm2": sample.pressure_kgf_cm2,
        "temperature_c": sample.temperature_c,
    }


def _assert_in_domain(sample: MeterSample, domain: Mapping[str, Any]) -> None:
    observed = _domain_values(sample)
    for name, value in observed.items():
        bounds = domain.get(name)
        if not isinstance(bounds, Mapping) or set(bounds) != {"min", "max"}:
            raise FusionMeterError(f"certificate domain missing exact bounds for {name}")
        lo = bounds["min"]
        hi = bounds["max"]
        _require_finite(f"domain.{name}.min", lo)
        _require_finite(f"domain.{name}.max", hi)
        if lo > hi:
            raise FusionMeterError(f"invalid domain bounds for {name}")
        if not (lo <= value <= hi):
            raise OutOfDomainError(f"{name}={value:.9g} outside [{lo:.9g}, {hi:.9g}]")


def predict(certificate: Mapping[str, Any], sample: MeterSample) -> dict[str, Any]:
    """Correct an indicated gas rate inside a calibrated condition envelope.

    Returned ``screening_uncertainty_pct`` is a conservative engineering screen:
    indicated-meter uncertainty plus empirical validation p95 absolute error.
    It is deliberately *not* represented as a certified GUM expanded uncertainty.
    """
    sample.validate()
    validate_certificate(certificate)
    if not sample.sensor_health:
        raise FusionMeterError("sensor health is false; correction is unavailable")
    _assert_in_domain(sample, certificate["domain"])

    features = raw_features(sample)
    means = [float(x) for x in certificate["feature_means"]]
    scales = [float(x) for x in certificate["feature_scales"]]
    coeffs = [float(x) for x in certificate["coefficients"]]
    normalized = [(x - mean) / scale for x, mean, scale in zip(features, means, scales)]
    log_overread = coeffs[0] + sum(c * x for c, x in zip(coeffs[1:], normalized))
    # Wet-gas correction cannot claim negative liquid-induced over-reading.
    overread_factor = max(1.0, math.exp(log_overread))
    corrected = sample.indicated_gas_rate / overread_factor

    validation = certificate["validation"]
    p95 = validation.get("p95_abs_error_pct")
    _require_finite("validation.p95_abs_error_pct", p95)
    screening = float(sample.indication_uncertainty_pct) + float(p95)
    evidence_class = str(certificate["evidence_class"])
    authority = "FIELD_EVIDENCE" if evidence_class == "REPRESENTATIVE_POC" else "DEMONSTRATION_ONLY"

    result = {
        "schema_version": 1,
        "authority": authority,
        "evidence_class": evidence_class,
        "indicated_gas_rate": sample.indicated_gas_rate,
        "corrected_gas_rate": corrected,
        "overread_factor": overread_factor,
        "plr": sample.plr,
        "plr_excess": sample.plr_excess,
        "screening_uncertainty_pct": screening,
        "screening_uncertainty_semantics": "indication_uncertainty_pct + empirical_validation_p95_abs_error_pct; not GUM certification",
        "certificate_sha256": certificate["certificate_sha256"],
        "sample": asdict(sample),
    }
    result["receipt_sha256"] = sha256_json(result)
    return result


def percentile_nearest_rank(values: Iterable[float], fraction: float) -> float:
    seq = sorted(float(x) for x in values)
    if not seq:
        raise FusionMeterError("percentile requires at least one value")
    if not 0 < fraction <= 1:
        raise FusionMeterError("fraction must be in (0, 1]")
    rank = max(1, math.ceil(fraction * len(seq)))
    return seq[rank - 1]
