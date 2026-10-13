"""Exact evidence types and validation helpers for the TITAN ladder-mixture gate."""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Any, Iterable, Mapping, Sequence

SCHEMA = "titan-v3-ladder-mixture-input/v1"
RECEIPT_SCHEMA = "titan-v3-ladder-mixture-receipt/v1"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
OUTCOME_RANK = {"L": 0, "T": 1, "W": 2}


class ValidationError(ValueError):
    """Raised only when the evidence document is structurally malformed."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": _canonical_json_value(self.details),
        }


def _require(condition: bool, code: str, message: str, **details: Any) -> None:
    if not condition:
        raise ValidationError(code, message, **details)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), "TYPE", f"{field} must be an object", field=field)
    return value


def _exact_keys(value: Mapping[str, Any], field: str, allowed: Iterable[str]) -> None:
    allowed_set = set(allowed)
    observed = set(value)
    non_text = sorted(repr(key) for key in observed if not isinstance(key, str))
    _require(not non_text, "OBJECT_KEY", f"{field} object keys must be strings", field=field, keys=non_text)
    unknown = sorted(observed - allowed_set)
    missing = sorted(allowed_set - observed)
    _require(not unknown, "UNKNOWN_FIELD", f"{field} contains unsupported fields", field=field, unknown=unknown)
    _require(not missing, "MISSING_FIELD", f"{field} is missing required fields", field=field, missing=missing)


def _list(value: Any, field: str) -> list[Any]:
    _require(isinstance(value, list), "TYPE", f"{field} must be an array", field=field)
    return value


def _text(value: Any, field: str) -> str:
    _require(isinstance(value, str), "TYPE", f"{field} must be a string", field=field)
    result = value.strip()
    _require(bool(result), "EMPTY", f"{field} must not be empty", field=field)
    return result


def _bool(value: Any, field: str) -> bool:
    _require(type(value) is bool, "TYPE", f"{field} must be a boolean", field=field)
    return value


def _integer(value: Any, field: str, *, minimum: int | None = None) -> int:
    _require(type(value) is int, "TYPE", f"{field} must be an integer", field=field)
    if minimum is not None:
        _require(value >= minimum, "RANGE", f"{field} must be >= {minimum}", field=field, value=value)
    return value


def _fraction(value: Any, field: str) -> Fraction:
    _require(type(value) is not bool, "TYPE", f"{field} must be numeric, not boolean", field=field)
    try:
        if isinstance(value, Fraction):
            result = value
        elif isinstance(value, Decimal):
            _require(value.is_finite(), "NONFINITE", f"{field} must be finite", field=field)
            result = Fraction(value)
        elif type(value) is int:
            result = Fraction(value, 1)
        elif type(value) is float:
            _require(math.isfinite(value), "NONFINITE", f"{field} must be finite", field=field)
            result = Fraction(str(value))
        elif isinstance(value, str):
            token = value.strip()
            _require(bool(token), "EMPTY", f"{field} must not be empty", field=field)
            _require(len(token) <= 256, "NUMBER_LENGTH", f"{field} numeric token is too long", field=field)
            result = Fraction(token)
        else:
            raise TypeError(type(value).__name__)
    except ValidationError:
        raise
    except (ValueError, ZeroDivisionError, TypeError) as exc:
        raise ValidationError("NUMBER", f"{field} is not an exact finite number", field=field, value=repr(value)) from exc
    return result


def _digest(value: Any, field: str, *, bits: int = 256) -> str:
    token = _text(value, field)
    pattern = HEX64 if bits == 256 else HEX40
    _require(pattern.fullmatch(token) is not None, "DIGEST", f"{field} must be lowercase hexadecimal", field=field, bits=bits)
    return token


def _family_name(value: Any, field: str) -> str:
    token = _text(value, field)
    _require(token == token.lower(), "FAMILY_CASE", f"{field} must be lowercase canonical form", field=field, value=token)
    _require(re.fullmatch(r"[a-z0-9][a-z0-9._-]*", token) is not None, "FAMILY_FORMAT", f"{field} has invalid characters", field=field, value=token)
    return token


def _seed_id(value: Any, field: str) -> str:
    _require(type(value) is not bool, "TYPE", f"{field} must be an integer or string", field=field)
    if type(value) is int:
        return str(value)
    token = _text(value, field)
    _require(len(token) <= 128, "SEED_LENGTH", f"{field} is too long", field=field)
    return token


def _outcome(own: Fraction, rival: Fraction) -> str:
    if own > rival:
        return "W"
    if own < rival:
        return "L"
    return "T"


def _mean(values: Sequence[Fraction]) -> Fraction:
    _require(bool(values), "EMPTY_MEAN", "cannot average an empty sequence")
    return sum(values, Fraction(0, 1)) / len(values)


def _ratio_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def _decimal_text(value: Fraction, *, precision: int = 24) -> str:
    with localcontext() as context:
        context.prec = precision
        result = Decimal(value.numerator) / Decimal(value.denominator)
        token = format(result, "f")
    if "." in token:
        token = token.rstrip("0").rstrip(".")
    return "0" if token in {"", "-0"} else token


def _quantity(value: Fraction) -> dict[str, str]:
    return {"fraction": _ratio_text(value), "decimal": _decimal_text(value)}


def _canonical_json_value(value: Any) -> Any:
    if isinstance(value, Fraction):
        return _ratio_text(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _canonical_json_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_canonical_json_value(item) for item in value]
    if isinstance(value, set):
        return sorted(_canonical_json_value(item) for item in value)
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _canonical_json_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


@dataclass(frozen=True)
class MixFamily:
    name: str
    hosted_count: int
    nominal: Fraction
    lower: Fraction
    upper: Fraction


@dataclass(frozen=True)
class Cell:
    family: str
    seed: str
    seat: int
    incumbent_own: Fraction
    incumbent_rival: Fraction
    candidate_own: Fraction
    candidate_rival: Fraction
    action_changed: bool
    trace_changed: bool

    @property
    def own_delta(self) -> Fraction:
        return self.candidate_own - self.incumbent_own

    @property
    def incumbent_margin(self) -> Fraction:
        return self.incumbent_own - self.incumbent_rival

    @property
    def candidate_margin(self) -> Fraction:
        return self.candidate_own - self.candidate_rival

    @property
    def margin_delta(self) -> Fraction:
        return self.candidate_margin - self.incumbent_margin

    @property
    def incumbent_outcome(self) -> str:
        return _outcome(self.incumbent_own, self.incumbent_rival)

    @property
    def candidate_outcome(self) -> str:
        return _outcome(self.candidate_own, self.candidate_rival)


@dataclass(frozen=True)
class ParsedInput:
    normalized: dict[str, Any]
    families: tuple[MixFamily, ...]
    cells: tuple[Cell, ...]
    expected_seats: tuple[int, ...]
    calibration_status: Mapping[str, str]
    minimum_seed_clusters: int
    minimum_seed_own_delta: Fraction
    minimum_seed_margin_delta: Fraction
    minimum_family_seat_own_delta: Fraction
    minimum_family_seat_margin_delta: Fraction
    total_variation_radius: Fraction
    strict_worst_case: bool
    require_uniform_family_reference: bool
    require_leave_one_family_out: bool
