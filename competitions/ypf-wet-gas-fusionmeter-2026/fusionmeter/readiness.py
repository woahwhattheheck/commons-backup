"""Fail-closed technical/submission readiness checks for FusionMeter."""
from __future__ import annotations

import math
from typing import Any, Mapping

from .core import FusionMeterError, validate_certificate


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _finite_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number


def evaluate_readiness(certificate: Mapping[str, Any], readiness: Mapping[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    try:
        validate_certificate(certificate)
    except FusionMeterError as exc:
        blockers.append(f"calibration certificate invalid: {exc}")

    if certificate.get("evidence_class") != "REPRESENTATIVE_POC":
        blockers.append("representative POC calibration certificate is absent")
    validation = certificate.get("validation", {})
    count = _finite_int(validation.get("count")) if isinstance(validation, Mapping) else None
    if count is None or count < 60:
        blockers.append("fewer than 60 independent representative validation points")
    p95 = _finite_float(validation.get("p95_abs_error_pct")) if isinstance(validation, Mapping) else None
    if p95 is None or p95 > 3.0:
        blockers.append("validation p95 absolute gas-rate error is missing/non-finite or exceeds 3%")
    repeatability = _finite_float(validation.get("repeatability_p95_pct")) if isinstance(validation, Mapping) else None
    if repeatability is None or repeatability > 3.0:
        blockers.append("representative repeated-condition p95 spread is missing/non-finite or exceeds 3%")
    if not isinstance(validation, Mapping) or validation.get("independent_holdout") is not True:
        blockers.append("independent holdout validation is not attested")

    domain = certificate.get("domain", {})
    required_coverage = {
        "pressure_kgf_cm2": (60.0, 85.0),
        "temperature_c": (30.0, 60.0),
    }
    for name, (need_lo, need_hi) in required_coverage.items():
        bounds = domain.get(name, {}) if isinstance(domain, Mapping) else {}
        lo = _finite_float(bounds.get("min")) if isinstance(bounds, Mapping) else None
        hi = _finite_float(bounds.get("max")) if isinstance(bounds, Mapping) else None
        if lo is None or hi is None:
            blockers.append(f"{name} representative coverage missing or non-finite")
            continue
        if lo > need_lo or hi < need_hi:
            blockers.append(f"{name} does not span YPF envelope {need_lo:g}..{need_hi:g}")

    total_dp = _finite_float(readiness.get("measured_total_pressure_drop_psi"))
    if total_dp is None or total_dp < 0 or total_dp > 15.0:
        blockers.append("measured total measurement-point pressure drop is missing/non-finite or exceeds 15 psi")
    hours = _finite_int(readiness.get("continuous_run_hours"))
    if hours is None or hours < 720:
        blockers.append("24/7 reliability evidence shorter than 720 continuous hours")
    availability = _finite_float(readiness.get("availability_fraction"))
    if availability is None or not 0.0 <= availability <= 1.0 or availability < 0.995:
        blockers.append("availability evidence missing/non-finite/out-of-range or below 99.5% engineering gate")
    boolean_requirements = {
        "reference_system_traceable": "reference-system traceability review absent",
        "validation_runs_blinded": "held-out validation runs were not independently/blindly evaluated",
        "aga3_alignment_reviewed": "AGA-3 alignment review absent",
        "online_transmission_tested": "online transmission path untested",
        "hazardous_area_design_reviewed": "hazardous-area / process-safety design review absent",
        "poc_support_owner_confirmed": "POC technical-support owner not confirmed",
        "experience_field_human_authored": "submission experience field still requires truthful human authorship",
        "ip_rights_reviewed": "IP/right-to-submit review absent",
        "challenge_agreement_reviewed": "challenge agreement not reviewed/accepted by owner",
        "substantive_human_contribution_confirmed": "substantive human contribution not confirmed",
    }
    for key, message in boolean_requirements.items():
        if readiness.get(key) is not True:
            blockers.append(message)

    return {
        "schema_version": 1,
        "status": "READY" if not blockers else "BLOCKED",
        "blockers": blockers,
        "note": "READY is an internal release gate only; it is not sponsor acceptance, field performance certification, or an award.",
    }


def validate_readiness_document(value: Mapping[str, Any]) -> None:
    if value.get("schema_version") != 1:
        raise FusionMeterError("readiness schema_version must equal 1")
