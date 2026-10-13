"""Deterministic Water4All 2026 consortium-readiness compiler.

This module is intentionally offline and non-authoritative.  It turns exact,
operator-supplied evidence generations into an owner-review packet.  It never
contacts partners, creates portal accounts, commits funding, submits a
proposal, or recognizes revenue.
"""

from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import json
import math
import re
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple

INPUT_SCHEMA = "water4all-2026-readiness-input/v1"
PACKET_SCHEMA = "water4all-2026-readiness-packet/v1"
BUNDLE_SCHEMA = "water4all-2026-readiness-bundle/v1"

SOURCE_CLASSES = {
    "OFFICIAL_CALL_PAGE",
    "OFFICIAL_CALL_ANNOUNCEMENT",
    "OFFICIAL_NATIONAL_REGULATIONS",
    "OFFICIAL_FAQ",
}
REQUIRED_SOURCE_CLASSES = {
    "OFFICIAL_CALL_PAGE",
    "OFFICIAL_CALL_ANNOUNCEMENT",
    "OFFICIAL_NATIONAL_REGULATIONS",
}
FORMAL_ROLES = {"FUNDED_PARTNER", "SELF_FUNDED_PARTNER"}
APPLICANT_ROLES = FORMAL_ROLES | {"PAID_TECHNICAL_SUBCONTRACT_CANDIDATE"}
PUBLICABILITY = {"PUBLIC_DESCRIPTOR", "PRIVATE_DESCRIPTOR"}
COMMERCIAL_STATES = {"PROPOSED_NOT_ACCEPTED", "OWNER_APPROVED_INTERNAL", "ACCEPTED_EXTERNAL"}
KNOWN_NONPARTICIPATING_FUNDED_COUNTRIES = {"US"}

SOURCE_MAX_AGE_SECONDS = 14 * 24 * 60 * 60
EVIDENCE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
CURRENT_PACKET_MAX_AGE_SECONDS = 5 * 60
FUTURE_SKEW_SECONDS = 5 * 60
MAX_INPUT_BYTES = 2 * 1024 * 1024

_TOPIC_REQUIREMENTS = {
    1: {
        "water_monitoring",
        "multimodal_data_integration",
        "uncertainty_quantification",
        "decision_support",
        "provenance_receipts",
    },
    3: {
        "smart_infrastructure",
        "anomaly_detection",
        "adaptive_control",
        "cyber_resilience",
        "provenance_receipts",
    },
}

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_COUNTRY = re.compile(r"^[A-Z]{2}$")


class ReadinessError(ValueError):
    """Raised when an input or packet is structurally invalid."""


def _reject_constant(value: str) -> None:
    raise ReadinessError("non-finite JSON number is forbidden: %s" % value)


def _reject_duplicate_pairs(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReadinessError("duplicate JSON key: %s" % key)
        result[key] = value
    return result


def strict_json_loads(raw: str) -> Any:
    if not isinstance(raw, str):
        raise ReadinessError("JSON input must be text")
    if len(raw.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ReadinessError("JSON input exceeds size ceiling")
    try:
        return json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except ReadinessError:
        raise
    except (TypeError, ValueError) as exc:
        raise ReadinessError("invalid JSON: %s" % exc) from exc


def _assert_json_value(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ReadinessError("non-finite number at %s" % path)
        raise ReadinessError("floating-point numbers are forbidden at %s" % path)
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_json_value(item, "%s[%d]" % (path, index))
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ReadinessError("non-string object key at %s" % path)
            _assert_json_value(item, "%s.%s" % (path, key))
        return
    raise ReadinessError("unsupported JSON value at %s" % path)


def canonical_bytes(value: Any) -> bytes:
    _assert_json_value(value)
    try:
        text = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ReadinessError("value is not canonical JSON: %s" % exc) from exc
    return text.encode("utf-8")


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _expect_dict(value: Any, path: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ReadinessError("%s must be an object" % path)
    return value


def _expect_list(value: Any, path: str) -> List[Any]:
    if not isinstance(value, list):
        raise ReadinessError("%s must be an array" % path)
    return value


def _expect_str(value: Any, path: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ReadinessError("%s must be a string" % path)
    if not allow_empty and not value:
        raise ReadinessError("%s must not be empty" % path)
    return value


def _expect_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ReadinessError("%s must be a boolean" % path)
    return value


def _expect_int(value: Any, path: str, minimum: Optional[int] = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReadinessError("%s must be an integer" % path)
    if minimum is not None and value < minimum:
        raise ReadinessError("%s must be >= %d" % (path, minimum))
    return value


def _expect_id(value: Any, path: str) -> str:
    text = _expect_str(value, path)
    if not _ID.fullmatch(text):
        raise ReadinessError("%s has invalid identifier syntax" % path)
    return text


def _expect_country(value: Any, path: str) -> str:
    text = _expect_str(value, path)
    if not _COUNTRY.fullmatch(text):
        raise ReadinessError("%s must be an ISO-style two-letter uppercase code" % path)
    return text


def _expect_hex(value: Any, path: str, pattern: re.Pattern[str]) -> str:
    text = _expect_str(value, path)
    if not pattern.fullmatch(text):
        raise ReadinessError("%s has invalid digest syntax" % path)
    return text


def parse_time(value: Any, path: str) -> _dt.datetime:
    text = _expect_str(value, path)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise ReadinessError("%s must be ISO-8601" % path) from exc
    if parsed.tzinfo is None:
        raise ReadinessError("%s must include a UTC offset" % path)
    return parsed.astimezone(_dt.timezone.utc)


def format_time(value: _dt.datetime) -> str:
    if value.tzinfo is None:
        raise ReadinessError("internal timestamp lacks timezone")
    return value.astimezone(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)


def _https_url(value: Any, path: str, allowed_host: Optional[str] = None) -> str:
    text = _expect_str(value, path)
    if not text.startswith("https://"):
        raise ReadinessError("%s must be HTTPS" % path)
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text):
        raise ReadinessError("%s contains a control character" % path)
    if allowed_host is not None:
        prefix = "https://" + allowed_host + "/"
        if not text.startswith(prefix):
            raise ReadinessError("%s must use %s" % (path, allowed_host))
    return text


def _fact_payload(source: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "source_id": source["source_id"],
        "authority_class": source["authority_class"],
        "source_url": source["source_url"],
        "version": source["version"],
        "observed_at": source["observed_at"],
        "published_at": source.get("published_at"),
        "call_title": source["call_title"],
        "preproposal_deadline_at": source["preproposal_deadline_at"],
        "full_proposal_deadline_at": source["full_proposal_deadline_at"],
        "budget_eur_cents": source["budget_eur_cents"],
        "complete": source["complete"],
        "declared_current": source["declared_current"],
    }


def source_fact_commitment(source: Mapping[str, Any]) -> str:
    """Return the content commitment for a normalized official-source record."""

    return sha256_hex(_fact_payload(source))


def seal_source(source: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a deep-copied source record with its fact commitment populated."""

    result = copy.deepcopy(dict(source))
    result["fact_commitment"] = source_fact_commitment(result)
    return result


def _reason(code: str, detail: str, refs: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    return {
        "code": code,
        "detail": detail,
        "refs": sorted(set(refs or [])),
    }
