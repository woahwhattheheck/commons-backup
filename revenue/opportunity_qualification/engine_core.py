from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable
from urllib.parse import urlsplit


CONTRACT = "tjlabs.opportunity-qualification/v1"
RECEIPT_CONTRACT = "tjlabs.opportunity-qualification-receipt/v1"

PRIME_READY = "PRIME_READY"
TEAMING_READY = "TEAMING_READY"
HOLD = "HOLD"
NO_BID = "NO_BID"

_SOURCE_CLASSES = {"OFFICIAL", "SECONDARY"}
_SOURCE_SCOPES = {"BUYER", "CAPABILITY"}
_SUBJECTS = {"PRIME", "TEAM"}
_STATES = {"PASS", "MISSING", "FAIL"}
_ROUTES = {"PRIME", "TEAM", "BOTH"}
_CURES = {"NONE", "PARTNER"}
_TEAMING = {"ALLOWED", "UNKNOWN", "PROHIBITED"}
_CATEGORIES = {
    "EXPERIENCE",
    "REFERENCE",
    "REGISTRATION",
    "SECURITY",
    "INSURANCE",
    "STAFFING",
    "TECHNICAL",
    "COMMERCIAL",
    "SUBMISSION",
    "LEGAL",
    "OTHER",
}
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_SECRET_RE = re.compile(
    r"(?:\bsk-[A-Za-z0-9_-]{12,}|\bgh[pousr]_[A-Za-z0-9]{20,}|"
    r"\bxox[baprs]-[A-Za-z0-9-]{12,}|\bAKIA[0-9A-Z]{16}\b|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\bBearer\s+[A-Za-z0-9._~+/=-]{12,})",
    re.IGNORECASE,
)


class QualificationError(ValueError):
    """Input is malformed, contradictory, or not safely attributable."""


def loads_strict(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise QualificationError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    try:
        value = json.loads(
            text,
            object_pairs_hook=pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                QualificationError(f"non-finite JSON scalar: {token}")
            ),
        )
    except QualificationError:
        raise
    except json.JSONDecodeError as exc:
        raise QualificationError(f"invalid JSON: {exc.msg}") from exc
    _reject_floats(value, "$")
    return value


def canonical_bytes(value: Any) -> bytes:
    _reject_floats(value, "$")
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _reject_floats(value: Any, path: str) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return
    if isinstance(value, float):
        raise QualificationError(f"{path}: floats are not accepted")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_floats(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise QualificationError(f"{path}: object keys must be strings")
            _reject_floats(item, f"{path}.{key}")
        return
    raise QualificationError(f"{path}: unsupported value type {type(value).__name__}")


def _expect_object(value: Any, path: str, allowed: set[str], required: set[str]) -> dict[str, Any]:
    if type(value) is not dict:
        raise QualificationError(f"{path}: expected object")
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown:
        raise QualificationError(f"{path}: unknown fields: {', '.join(sorted(unknown))}")
    if missing:
        raise QualificationError(f"{path}: missing fields: {', '.join(sorted(missing))}")
    return value


def _expect_list(value: Any, path: str) -> list[Any]:
    if type(value) is not list:
        raise QualificationError(f"{path}: expected list")
    return value


def _expect_bool(value: Any, path: str) -> bool:
    if type(value) is not bool:
        raise QualificationError(f"{path}: expected boolean")
    return value


def _expect_text(value: Any, path: str, *, max_len: int = 512, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise QualificationError(f"{path}: expected string")
    if not allow_empty and not value:
        raise QualificationError(f"{path}: empty string")
    if len(value) > max_len:
        raise QualificationError(f"{path}: text exceeds {max_len} characters")
    if any(ord(ch) < 32 and ch not in "\t" for ch in value):
        raise QualificationError(f"{path}: control characters are not accepted")
    if _SECRET_RE.search(value):
        raise QualificationError(f"{path}: secret-shaped text is not accepted")
    return value


def _expect_id(value: Any, path: str) -> str:
    text = _expect_text(value, path, max_len=128)
    if not _ID_RE.fullmatch(text):
        raise QualificationError(f"{path}: malformed identifier")
    return text


def _expect_sha(value: Any, path: str) -> str:
    text = _expect_text(value, path, max_len=64)
    if not _SHA_RE.fullmatch(text):
        raise QualificationError(f"{path}: expected lowercase SHA-256")
    return text


def _expect_enum(value: Any, path: str, allowed: set[str]) -> str:
    text = _expect_text(value, path, max_len=64)
    if text not in allowed:
        raise QualificationError(f"{path}: unsupported value {text!r}")
    return text


def _parse_utc(value: Any, path: str) -> datetime:
    text = _expect_text(value, path, max_len=32)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", text):
        raise QualificationError(f"{path}: expected canonical UTC timestamp")
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise QualificationError(f"{path}: invalid UTC timestamp") from exc
    return parsed


def _expect_url(value: Any, path: str) -> str:
    text = _expect_text(value, path, max_len=2048)
    parsed = urlsplit(text)
    if parsed.scheme != "https" or not parsed.hostname:
        raise QualificationError(f"{path}: expected absolute https URL")
    if parsed.username is not None or parsed.password is not None:
        raise QualificationError(f"{path}: URL userinfo is not accepted")
    if any(ch.isspace() for ch in text):
        raise QualificationError(f"{path}: URL whitespace is not accepted")
    return text


def _unique_ids(records: Iterable[dict[str, Any]], key: str, path: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        record_id = record[key]
        if record_id in out:
            if canonical_bytes(out[record_id]) != canonical_bytes(record):
                raise QualificationError(f"{path}[{index}]: {key} replay changed payload")
            raise QualificationError(f"{path}[{index}]: duplicate {key}")
        out[record_id] = record
    return out


def _validate_source(raw: Any, index: int, as_of: datetime) -> dict[str, Any]:
    path = f"$.sources[{index}]"
    source = _expect_object(
        raw,
        path,
        {"source_id", "scope", "source_class", "url", "captured_at", "sha256", "label"},
        {"source_id", "scope", "source_class", "url", "captured_at", "sha256", "label"},
    )
    source_id = _expect_id(source["source_id"], f"{path}.source_id")
    scope = _expect_enum(source["scope"], f"{path}.scope", _SOURCE_SCOPES)
    source_class = _expect_enum(source["source_class"], f"{path}.source_class", _SOURCE_CLASSES)
    url = _expect_url(source["url"], f"{path}.url")
    captured_at = _parse_utc(source["captured_at"], f"{path}.captured_at")
    if captured_at > as_of:
        raise QualificationError(f"{path}.captured_at: future evidence")
    sha = _expect_sha(source["sha256"], f"{path}.sha256")
    label = _expect_text(source["label"], f"{path}.label", max_len=200)
    return {
        "source_id": source_id,
        "scope": scope,
        "source_class": source_class,
        "url": url,
        "captured_at": source["captured_at"],
        "sha256": sha,
        "label": label,
    }


def _validate_evidence(
    raw: Any,
    index: int,
    as_of: datetime,
    sources: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    path = f"$.evidence[{index}]"
    item = _expect_object(
        raw,
        path,
        {
            "evidence_id",
            "subject",
            "category",
            "source_id",
            "captured_at",
            "sha256",
            "statement",
            "valid_until",
        },
        {"evidence_id", "subject", "category", "source_id", "captured_at", "sha256", "statement"},
    )
    evidence_id = _expect_id(item["evidence_id"], f"{path}.evidence_id")
    subject = _expect_enum(item["subject"], f"{path}.subject", _SUBJECTS)
    category = _expect_enum(item["category"], f"{path}.category", _CATEGORIES)
    source_id = _expect_id(item["source_id"], f"{path}.source_id")
    source = sources.get(source_id)
    if source is None:
        raise QualificationError(f"{path}.source_id: unknown source")
    if source["scope"] != "CAPABILITY":
        raise QualificationError(f"{path}.source_id: evidence must bind a CAPABILITY source")
    if source["source_class"] != "OFFICIAL":
        raise QualificationError(f"{path}.source_id: readiness evidence must bind an OFFICIAL source")
    captured_at = _parse_utc(item["captured_at"], f"{path}.captured_at")
    if captured_at > as_of:
        raise QualificationError(f"{path}.captured_at: future evidence")
    if captured_at < _parse_utc(source["captured_at"], f"{path}.source.captured_at"):
        raise QualificationError(f"{path}.captured_at: predates bound source capture")
    sha = _expect_sha(item["sha256"], f"{path}.sha256")
    statement = _expect_text(item["statement"], f"{path}.statement", max_len=500)

    valid_until = item.get("valid_until")
    if valid_until is not None:
        valid_dt = _parse_utc(valid_until, f"{path}.valid_until")
        if valid_dt < captured_at:
            raise QualificationError(f"{path}.valid_until: predates evidence capture")

    return {
        "evidence_id": evidence_id,
        "subject": subject,
        "category": category,
        "source_id": source_id,
        "captured_at": item["captured_at"],
        "sha256": sha,
        "statement": statement,
        **({"valid_until": valid_until} if valid_until is not None else {}),
    }


def _validate_state_evidence(
    state: str,
    evidence_ids: list[str],
    expected_subject: str,
    category: str,
    path: str,
    evidence: dict[str, dict[str, Any]],
    as_of: datetime,
) -> list[str]:
    if state == "MISSING":
        if evidence_ids:
            raise QualificationError(f"{path}: MISSING state cannot carry evidence")
        return []

    if not evidence_ids:
        raise QualificationError(f"{path}: {state} state requires evidence")

    normalized: list[str] = []
    seen: set[str] = set()
    for index, evidence_id_raw in enumerate(evidence_ids):
        evidence_id = _expect_id(evidence_id_raw, f"{path}[{index}]")
        if evidence_id in seen:
            raise QualificationError(f"{path}[{index}]: duplicate evidence id")
        seen.add(evidence_id)
        item = evidence.get(evidence_id)
        if item is None:
            raise QualificationError(f"{path}[{index}]: unknown evidence id")
        if item["subject"] != expected_subject:
            raise QualificationError(f"{path}[{index}]: evidence subject drift")
        if item["category"] != category and item["category"] != "OTHER":
            raise QualificationError(f"{path}[{index}]: evidence category drift")
        if "valid_until" in item and _parse_utc(item["valid_until"], f"{path}[{index}].valid_until") < as_of:
            raise QualificationError(f"{path}[{index}]: expired evidence")
        normalized.append(evidence_id)
    return sorted(normalized)


def _validate_requirement(
    raw: Any,
    index: int,
    sources: dict[str, dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
    as_of: datetime,
) -> dict[str, Any]:
    path = f"$.requirements[{index}]"
    item = _expect_object(
        raw,
        path,
        {
            "gate_id",
            "category",
            "mandatory",
            "route",
            "cure",
            "buyer_source_id",
            "description",
            "prime_state",
            "prime_evidence_ids",
            "team_state",
            "team_evidence_ids",
        },
        {
            "gate_id",
            "category",
            "mandatory",
            "route",
            "cure",
            "buyer_source_id",
            "description",
            "prime_state",
            "prime_evidence_ids",
            "team_state",
            "team_evidence_ids",
        },
    )
    gate_id = _expect_id(item["gate_id"], f"{path}.gate_id")
    category = _expect_enum(item["category"], f"{path}.category", _CATEGORIES)
    mandatory = _expect_bool(item["mandatory"], f"{path}.mandatory")
    route = _expect_enum(item["route"], f"{path}.route", _ROUTES)
    cure = _expect_enum(item["cure"], f"{path}.cure", _CURES)
    buyer_source_id = _expect_id(item["buyer_source_id"], f"{path}.buyer_source_id")
    source = sources.get(buyer_source_id)
    if source is None:
        raise QualificationError(f"{path}.buyer_source_id: unknown source")
    if source["scope"] != "BUYER":
        raise QualificationError(f"{path}.buyer_source_id: requirement must bind a BUYER source")
    description = _expect_text(item["description"], f"{path}.description", max_len=500)
    prime_state = _expect_enum(item["prime_state"], f"{path}.prime_state", _STATES)
    team_state = _expect_enum(item["team_state"], f"{path}.team_state", _STATES)
    prime_ids_raw = _expect_list(item["prime_evidence_ids"], f"{path}.prime_evidence_ids")
    team_ids_raw = _expect_list(item["team_evidence_ids"], f"{path}.team_evidence_ids")
    prime_ids = _validate_state_evidence(
        prime_state,
        prime_ids_raw,
        "PRIME",
        category,
        f"{path}.prime_evidence_ids",
        evidence,
        as_of,
    )
    team_ids = _validate_state_evidence(
        team_state,
        team_ids_raw,
        "TEAM",
        category,
        f"{path}.team_evidence_ids",
        evidence,
        as_of,
    )
    if route == "TEAM" and cure == "PARTNER":
        raise QualificationError(f"{path}.cure: TEAM requirement is already partner-scoped")
    return {
        "gate_id": gate_id,
        "category": category,
        "mandatory": mandatory,
        "route": route,
        "cure": cure,
        "buyer_source_id": buyer_source_id,
        "description": description,
        "prime_state": prime_state,
        "prime_evidence_ids": prime_ids,
        "team_state": team_state,
        "team_evidence_ids": team_ids,
    }


def _buyer_official(source_id: str | None, sources: dict[str, dict[str, Any]]) -> bool:
    if source_id is None:
        return False
    source = sources.get(source_id)
    return bool(source and source["scope"] == "BUYER" and source["source_class"] == "OFFICIAL")


def _evaluate_prime(requirements: list[dict[str, Any]], sources: dict[str, dict[str, Any]]) -> tuple[bool, bool, list[str]]:
    ready = True
    possible = True
    reasons: list[str] = []
    for req in requirements:
        if not req["mandatory"] or req["route"] == "TEAM":
            continue
        prefix = req["gate_id"]
        if not _buyer_official(req["buyer_source_id"], sources):
            ready = False
            reasons.append(f"{prefix}:MANDATORY_SOURCE_NOT_OFFICIAL")
            continue
        if req["prime_state"] == "PASS":
            continue
        ready = False
        if req["prime_state"] == "FAIL":
            possible = False
            reasons.append(f"{prefix}:PRIME_FAILED")
        else:
            reasons.append(f"{prefix}:PRIME_MISSING")
    return ready, possible, sorted(reasons)


def _evaluate_team(
    requirements: list[dict[str, Any]],
    sources: dict[str, dict[str, Any]],
    teaming: str,
    teaming_source_id: str | None,
) -> tuple[bool, bool, list[str]]:
    if teaming == "PROHIBITED":
        return False, False, ["TEAMING_PROHIBITED"]
    if teaming != "ALLOWED" or not _buyer_official(teaming_source_id, sources):
        return False, True, ["TEAMING_NOT_OFFICIALLY_EVIDENCED"]

    ready = True
    possible = True
    reasons: list[str] = []
    for req in requirements:
        if not req["mandatory"]:
            continue
        prefix = req["gate_id"]
        if not _buyer_official(req["buyer_source_id"], sources):
            ready = False
            reasons.append(f"{prefix}:MANDATORY_SOURCE_NOT_OFFICIAL")
            continue

        route = req["route"]
        prime_state = req["prime_state"]
        team_state = req["team_state"]
        cure = req["cure"]

        if route == "PRIME":
            if prime_state == "PASS":
                continue
            if cure == "PARTNER" and team_state == "PASS":
                continue
            ready = False
            if prime_state == "FAIL" and cure == "NONE":
                possible = False
                reasons.append(f"{prefix}:NONCURABLE_PRIME_FAILURE")
            elif cure == "PARTNER" and team_state == "FAIL":
                possible = False
                reasons.append(f"{prefix}:PARTNER_CURE_FAILED")
            else:
                reasons.append(f"{prefix}:TEAM_ROUTE_MISSING_CURE")
            continue

        if route == "TEAM":
            if team_state == "PASS":
                continue
            ready = False
            if team_state == "FAIL":
                possible = False
                reasons.append(f"{prefix}:TEAM_FAILED")
            else:
                reasons.append(f"{prefix}:TEAM_MISSING")
            continue

        side_fail = False
        if prime_state != "PASS":
            ready = False
            side_fail = side_fail or prime_state == "FAIL"
            reasons.append(
                f"{prefix}:PRIME_{'FAILED' if prime_state == 'FAIL' else 'MISSING'}"
            )
        if team_state != "PASS":
            ready = False
            side_fail = side_fail or team_state == "FAIL"
            reasons.append(
                f"{prefix}:TEAM_{'FAILED' if team_state == 'FAIL' else 'MISSING'}"
            )
        if side_fail:
            possible = False
    return ready, possible, sorted(set(reasons))


def _scoreable_gaps(requirements: list[dict[str, Any]], sources: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    for req in requirements:
        if req["mandatory"]:
            continue
        official = _buyer_official(req["buyer_source_id"], sources)
        prime = req["prime_state"]
        team = req["team_state"]
        if official and prime == "PASS":
            continue
        gaps.append(
            {
                "gate_id": req["gate_id"],
                "category": req["category"],
                "buyer_source": "OFFICIAL" if official else "SECONDARY_OR_UNKNOWN",
                "prime_state": prime,
                "team_state": team,
            }
        )
    return sorted(gaps, key=lambda item: item["gate_id"])


def compile_qualification(packet: dict[str, Any], *, trusted_as_of: str) -> dict[str, Any]:
    packet = copy.deepcopy(packet)
    _reject_floats(packet, "$")
    root = _expect_object(
        packet,
        "$",
        {"contract", "opportunity", "sources", "evidence", "requirements", "as_of"},
        {"contract", "opportunity", "sources", "evidence", "requirements", "as_of"},
    )
    if _expect_text(root["contract"], "$.contract", max_len=80) != CONTRACT:
        raise QualificationError("$.contract: unsupported contract")

    as_of_dt = _parse_utc(trusted_as_of, "trusted_as_of")
    packet_as_of = _parse_utc(root["as_of"], "$.as_of")
    if packet_as_of != as_of_dt:
        raise QualificationError("$.as_of: does not match trusted_as_of")

    opportunity = _expect_object(
        root["opportunity"],
        "$.opportunity",
        {
            "opportunity_id",
            "buyer",
            "solicitation_id",
            "title",
            "controlling_source_id",
            "proposal_deadline",
            "proposal_deadline_source_id",
            "question_deadline",
            "question_deadline_source_id",
            "teaming",
            "teaming_source_id",
        },
        {
            "opportunity_id",
            "buyer",
            "solicitation_id",
            "title",
            "controlling_source_id",
            "proposal_deadline",
            "proposal_deadline_source_id",
            "question_deadline",
            "question_deadline_source_id",
            "teaming",
            "teaming_source_id",
        },
    )
    normalized_opportunity = {
        "opportunity_id": _expect_id(opportunity["opportunity_id"], "$.opportunity.opportunity_id"),
        "buyer": _expect_text(opportunity["buyer"], "$.opportunity.buyer", max_len=200),
        "solicitation_id": _expect_text(
            opportunity["solicitation_id"], "$.opportunity.solicitation_id", max_len=160
        ),
        "title": _expect_text(opportunity["title"], "$.opportunity.title", max_len=300),
        "controlling_source_id": None,
        "proposal_deadline": None,
        "proposal_deadline_source_id": None,
        "question_deadline": None,
        "question_deadline_source_id": None,
        "teaming": _expect_enum(opportunity["teaming"], "$.opportunity.teaming", _TEAMING),
        "teaming_source_id": None,
    }
    for field in ("controlling_source_id", "proposal_deadline_source_id", "question_deadline_source_id", "teaming_source_id"):
        value = opportunity[field]
        if value is not None:
            normalized_opportunity[field] = _expect_id(value, f"$.opportunity.{field}")
    for field in ("proposal_deadline", "question_deadline"):
        value = opportunity[field]
        if value is not None:
            _parse_utc(value, f"$.opportunity.{field}")
            normalized_opportunity[field] = value

    raw_sources = _expect_list(root["sources"], "$.sources")
    if not raw_sources:
        raise QualificationError("$.sources: at least one source is required")
    source_records = [_validate_source(raw, i, as_of_dt) for i, raw in enumerate(raw_sources)]
    sources = _unique_ids(source_records, "source_id", "$.sources")

    for field in (
        "controlling_source_id",
        "proposal_deadline_source_id",
        "question_deadline_source_id",
        "teaming_source_id",
    ):
        source_id = normalized_opportunity[field]
        if source_id is not None and source_id not in sources:
            raise QualificationError(f"$.opportunity.{field}: unknown source")

    if normalized_opportunity["proposal_deadline"] is None and normalized_opportunity["proposal_deadline_source_id"] is not None:
        raise QualificationError("$.opportunity.proposal_deadline_source_id: deadline is absent")
    if normalized_opportunity["proposal_deadline"] is not None and normalized_opportunity["proposal_deadline_source_id"] is None:
        raise QualificationError("$.opportunity.proposal_deadline: source binding is required")
    if normalized_opportunity["question_deadline"] is None and normalized_opportunity["question_deadline_source_id"] is not None:
        raise QualificationError("$.opportunity.question_deadline_source_id: deadline is absent")
    if normalized_opportunity["question_deadline"] is not None and normalized_opportunity["question_deadline_source_id"] is None:
        raise QualificationError("$.opportunity.question_deadline: source binding is required")
    if normalized_opportunity["teaming"] == "UNKNOWN" and normalized_opportunity["teaming_source_id"] is not None:
        raise QualificationError("$.opportunity.teaming_source_id: UNKNOWN teaming cannot carry source")
    if normalized_opportunity["teaming"] != "UNKNOWN" and normalized_opportunity["teaming_source_id"] is None:
        raise QualificationError("$.opportunity.teaming: source binding is required")

    raw_evidence = _expect_list(root["evidence"], "$.evidence")
    evidence_records = [
        _validate_evidence(raw, i, as_of_dt, sources) for i, raw in enumerate(raw_evidence)
    ]
    evidence = _unique_ids(evidence_records, "evidence_id", "$.evidence")

    raw_requirements = _expect_list(root["requirements"], "$.requirements")
    if not raw_requirements:
        raise QualificationError("$.requirements: at least one requirement is required")
    requirements_records = [
        _validate_requirement(raw, i, sources, evidence, as_of_dt)
        for i, raw in enumerate(raw_requirements)
    ]
    requirements = _unique_ids(requirements_records, "gate_id", "$.requirements")
    ordered_requirements = [requirements[key] for key in sorted(requirements)]

    controlling_ok = _buyer_official(normalized_opportunity["controlling_source_id"], sources)
    deadline_source_ok = (
        normalized_opportunity["proposal_deadline"] is not None
        and _buyer_official(normalized_opportunity["proposal_deadline_source_id"], sources)
    )
    question_source_ok = (
        normalized_opportunity["question_deadline"] is None
        or _buyer_official(normalized_opportunity["question_deadline_source_id"], sources)
    )

    expired = False
    if normalized_opportunity["proposal_deadline"] is not None:
        expired = as_of_dt > _parse_utc(
            normalized_opportunity["proposal_deadline"], "$.opportunity.proposal_deadline"
        )

    prime_ready, prime_possible, prime_reasons = _evaluate_prime(ordered_requirements, sources)
    team_ready, team_possible, team_reasons = _evaluate_team(
        ordered_requirements,
        sources,
        normalized_opportunity["teaming"],
        normalized_opportunity["teaming_source_id"],
    )

    package_reasons: list[str] = []
    if not controlling_ok:
        package_reasons.append("CONTROLLING_PACKAGE_NOT_OFFICIALLY_EVIDENCED")
    if not deadline_source_ok:
        package_reasons.append("PROPOSAL_DEADLINE_NOT_OFFICIALLY_EVIDENCED")
    if not question_source_ok:
        package_reasons.append("QUESTION_DEADLINE_SOURCE_NOT_OFFICIAL")

    if expired:
        disposition = NO_BID
        disposition_reasons = ["PROPOSAL_DEADLINE_EXPIRED"]
    elif not controlling_ok or not deadline_source_ok:
        disposition = HOLD
        disposition_reasons = sorted(package_reasons)
    elif prime_ready:
        disposition = PRIME_READY
        disposition_reasons = []
    elif team_ready:
        disposition = TEAMING_READY
        disposition_reasons = []
    elif not prime_possible and not team_possible:
        disposition = NO_BID
        disposition_reasons = sorted(set(prime_reasons + team_reasons))
    else:
        disposition = HOLD
        disposition_reasons = sorted(set(package_reasons + prime_reasons + team_reasons))

    normalized_packet = {
        "contract": CONTRACT,
        "opportunity": normalized_opportunity,
        "sources": [sources[key] for key in sorted(sources)],
        "evidence": [evidence[key] for key in sorted(evidence)],
        "requirements": ordered_requirements,
        "as_of": root["as_of"],
    }
    receipt: dict[str, Any] = {
        "contract": RECEIPT_CONTRACT,
        "input_digest": digest(normalized_packet),
        "as_of": root["as_of"],
        "opportunity": {
            "opportunity_id": normalized_opportunity["opportunity_id"],
            "buyer": normalized_opportunity["buyer"],
            "solicitation_id": normalized_opportunity["solicitation_id"],
            "title": normalized_opportunity["title"],
            "proposal_deadline": normalized_opportunity["proposal_deadline"],
            "question_deadline": normalized_opportunity["question_deadline"],
        },
        "disposition": disposition,
        "reasons": disposition_reasons,
        "package": {
            "controlling_source_official": controlling_ok,
            "proposal_deadline_source_official": deadline_source_ok,
            "question_deadline_source_official": question_source_ok,
            "proposal_expired": expired,
        },
        "prime": {
            "ready": prime_ready,
            "possible": prime_possible,
            "reasons": prime_reasons,
        },
        "team": {
            "ready": team_ready,
            "possible": team_possible,
            "teaming": normalized_opportunity["teaming"],
            "reasons": team_reasons,
        },
        "scoreable_gaps": _scoreable_gaps(ordered_requirements, sources),
        "counts": {
            "sources": len(sources),
            "evidence": len(evidence),
            "mandatory_requirements": sum(1 for req in ordered_requirements if req["mandatory"]),
            "scoreable_requirements": sum(1 for req in ordered_requirements if not req["mandatory"]),
        },
        "authority": {
            "buyer_contact": False,
            "partner_contact": False,
            "portal_login": False,
            "registration": False,
            "proposal_submission": False,
            "question_submission": False,
            "pricing_commitment": False,
            "signature": False,
            "contract_execution": False,
            "spend": False,
            "payment_provider_mutation": False,
            "deployment": False,
            "award_claim": False,
            "recognized_revenue": False,
        },
    }
    receipt["receipt_digest"] = digest(receipt)
    return receipt


def verify_receipt(receipt: dict[str, Any]) -> bool:
    if type(receipt) is not dict:
        return False
    candidate = copy.deepcopy(receipt)
    received = candidate.pop("receipt_digest", None)
    if type(received) is not str or not _SHA_RE.fullmatch(received):
        return False
    if candidate.get("contract") != RECEIPT_CONTRACT:
        return False
    authority = candidate.get("authority")
    if type(authority) is not dict or not authority:
        return False
    if any(value is not False for value in authority.values()):
        return False
    try:
        return digest(candidate) == received
    except QualificationError:
        return False


def render_markdown(receipt: dict[str, Any]) -> str:
    if not verify_receipt(receipt):
        raise QualificationError("receipt verification failed")
    opportunity = receipt["opportunity"]
    lines = [
        f"# Opportunity Qualification — {opportunity['solicitation_id']}",
        "",
        f"- Buyer: {opportunity['buyer']}",
        f"- Title: {opportunity['title']}",
        f"- Disposition: **{receipt['disposition']}**",
        f"- As of: {receipt['as_of']}",
        f"- Proposal deadline: {opportunity['proposal_deadline'] or 'unknown'}",
        f"- Question deadline: {opportunity['question_deadline'] or 'unknown'}",
        f"- Receipt SHA-256: `{receipt['receipt_digest']}`",
        "",
        "## Evidence boundary",
        "",
        f"- Sources: {receipt['counts']['sources']}",
        f"- Capability evidence records: {receipt['counts']['evidence']}",
        f"- Mandatory requirements: {receipt['counts']['mandatory_requirements']}",
        f"- Scoreable requirements: {receipt['counts']['scoreable_requirements']}",
        f"- Prime route ready: {str(receipt['prime']['ready']).lower()}",
        f"- Team route ready: {str(receipt['team']['ready']).lower()}",
        "",
    ]
    if receipt["reasons"]:
        lines += ["## Reasons", ""] + [f"- {reason}" for reason in receipt["reasons"]] + [""]
    if receipt["scoreable_gaps"]:
        lines += ["## Scoreable gaps", ""]
        for gap in receipt["scoreable_gaps"]:
            lines.append(
                f"- `{gap['gate_id']}` ({gap['category']}): "
                f"prime={gap['prime_state']}, team={gap['team_state']}, "
                f"buyer-source={gap['buyer_source']}"
            )
        lines.append("")
    lines += [
        "## Commercial boundary",
        "",
        "This receipt is an offline qualification result. External commercial actions remain human-controlled.",
        "",
    ]
    return "\n".join(lines)


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Compile or verify opportunity qualification receipts.")
    parser.add_argument("packet", help="qualification packet JSON")
    parser.add_argument("--as-of", required=True, help="trusted UTC time, YYYY-MM-DDTHH:MM:SSZ")
    parser.add_argument("--markdown", help="optional Markdown output path")
    args = parser.parse_args()

    with open(args.packet, "r", encoding="utf-8") as handle:
        packet = loads_strict(handle.read())
    receipt = compile_qualification(packet, trusted_as_of=args.as_of)
    print(json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False))
    if args.markdown:
        with open(args.markdown, "x", encoding="utf-8", newline="\n") as handle:
            handle.write(render_markdown(receipt) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
