from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any

VAULT_SCHEMA = "qualification-evidence-vault/v1"
SOLICITATION_SCHEMA = "qualification-solicitation/v1"
ASSESSMENT_SCHEMA = "qualification-assessment/v1"
REDACTED_SCHEMA = "qualification-evidence-vault-public/v1"

STATUSES = {"VERIFIED", "MISSING", "OWNER_ONLY", "EXPIRED", "UNKNOWN"}
VISIBILITIES = {"PUBLIC", "PRIVATE"}
CATEGORIES = {
    "LEGAL_ENTITY",
    "INSURANCE",
    "PAST_PERFORMANCE",
    "REFERENCE_PERMISSION",
    "STAFFING",
    "CERTIFICATION",
    "RESELLER_STATUS",
    "SUBCONTRACTOR_STATUS",
    "TECHNICAL_CAPABILITY",
    "DELIVERY_RECEIPT",
    "PAYMENT_RECEIPT",
}
SOURCE_KINDS = {
    "FIRST_PARTY_PUBLIC",
    "GITHUB_MERGED_PR",
    "PROVIDER_RECEIPT",
    "OWNER_PRIVATE_DOCUMENT",
    "OWNER_ASSERTION",
    "SYNTHETIC_FIXTURE",
}
ALLOWED_VERIFIED_SOURCES = {
    "LEGAL_ENTITY": {"FIRST_PARTY_PUBLIC", "PROVIDER_RECEIPT", "OWNER_PRIVATE_DOCUMENT"},
    "INSURANCE": {"FIRST_PARTY_PUBLIC", "PROVIDER_RECEIPT", "OWNER_PRIVATE_DOCUMENT"},
    "PAST_PERFORMANCE": {"FIRST_PARTY_PUBLIC", "PROVIDER_RECEIPT", "OWNER_PRIVATE_DOCUMENT"},
    "REFERENCE_PERMISSION": {"PROVIDER_RECEIPT", "OWNER_PRIVATE_DOCUMENT"},
    "STAFFING": {"FIRST_PARTY_PUBLIC", "OWNER_PRIVATE_DOCUMENT"},
    "CERTIFICATION": {"FIRST_PARTY_PUBLIC", "PROVIDER_RECEIPT", "OWNER_PRIVATE_DOCUMENT"},
    "RESELLER_STATUS": {"FIRST_PARTY_PUBLIC", "PROVIDER_RECEIPT", "OWNER_PRIVATE_DOCUMENT"},
    "SUBCONTRACTOR_STATUS": {"FIRST_PARTY_PUBLIC", "PROVIDER_RECEIPT", "OWNER_PRIVATE_DOCUMENT"},
    "TECHNICAL_CAPABILITY": {"FIRST_PARTY_PUBLIC", "GITHUB_MERGED_PR", "PROVIDER_RECEIPT", "OWNER_PRIVATE_DOCUMENT"},
    "DELIVERY_RECEIPT": {"FIRST_PARTY_PUBLIC", "GITHUB_MERGED_PR", "PROVIDER_RECEIPT", "OWNER_PRIVATE_DOCUMENT"},
    "PAYMENT_RECEIPT": {"PROVIDER_RECEIPT", "OWNER_PRIVATE_DOCUMENT"},
}
OUTCOMES = {
    "PRIME_SUPPORTED",
    "PARTNER_ONLY",
    "HOLD_MISSING_EVIDENCE",
    "DISQUALIFIED",
}
REQ_RESULTS = {
    "SATISFIED_BY_PRIME",
    "PARTNER_GAP",
    "OWNER_EVIDENCE_REQUIRED",
    "DISQUALIFYING_GAP",
}
ASCII_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,199}$")
QUALIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+ -]{0,159}$|^\*$")


class EvidenceError(ValueError):
    pass


def _pairs_no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise EvidenceError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_loads(data: bytes | str) -> Any:
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise EvidenceError("input is not strict UTF-8") from exc
    elif type(data) is str:
        text = data
    else:
        raise EvidenceError("strict_loads expects bytes or str")

    def bad_constant(value: str) -> None:
        raise EvidenceError(f"non-finite JSON number: {value}")

    try:
        return json.loads(text, object_pairs_hook=_pairs_no_dupes, parse_constant=bad_constant)
    except EvidenceError:
        raise
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"invalid JSON: {exc.msg}") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise EvidenceError("value cannot be canonically encoded") from exc


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _obj(value: Any, name: str, keys: set[str]) -> dict[str, Any]:
    if type(value) is not dict:
        raise EvidenceError(f"{name} must be an object")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        raise EvidenceError(f"{name} keys mismatch; missing={missing} extra={extra}")
    return value


def _array(value: Any, name: str, limit: int) -> list[Any]:
    if type(value) is not list:
        raise EvidenceError(f"{name} must be an array")
    if len(value) > limit:
        raise EvidenceError(f"{name} exceeds {limit} entries")
    return value


def _text(value: Any, name: str, limit: int = 500) -> str:
    if type(value) is not str or not value or len(value) > limit:
        raise EvidenceError(f"{name} must be non-empty text <= {limit} chars")
    for char in value:
        if ord(char) < 0x20 and char not in "\t\n\r":
            raise EvidenceError(f"{name} contains a control character")
        if 0xD800 <= ord(char) <= 0xDFFF:
            raise EvidenceError(f"{name} contains a Unicode surrogate")
    return value


def _token(value: Any, name: str) -> str:
    text = _text(value, name, 200)
    if not ASCII_TOKEN.fullmatch(text):
        raise EvidenceError(f"{name} is not a bounded opaque token")
    return text


def _qualifier(value: Any, name: str) -> str:
    text = _text(value, name, 160)
    if not QUALIFIER.fullmatch(text):
        raise EvidenceError(f"{name} is not a valid qualifier")
    return text


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise EvidenceError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


def _boolean(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise EvidenceError(f"{name} must be boolean")
    return value


def parse_ts(value: Any, name: str) -> datetime:
    text = _text(value, name, 40)
    if not text.endswith("Z"):
        raise EvidenceError(f"{name} must be RFC3339 UTC ending Z")
    try:
        dt = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise EvidenceError(f"{name} is not RFC3339 UTC") from exc
    if dt.tzinfo != timezone.utc:
        raise EvidenceError(f"{name} must use UTC")
    return dt


def _normalize_record(raw: Any, index: int, as_of: datetime) -> dict[str, Any]:
    name = f"vault.records[{index}]"
    record = _obj(
        raw,
        name,
        {
            "evidence_id",
            "category",
            "qualifier",
            "status",
            "visibility",
            "source_kind",
            "source_ref",
            "description",
            "event_at",
            "valid_until",
        },
    )
    evidence_id = _token(record["evidence_id"], f"{name}.evidence_id")
    category = _text(record["category"], f"{name}.category", 64)
    if category not in CATEGORIES:
        raise EvidenceError(f"{name}.category unsupported: {category}")
    qualifier = _qualifier(record["qualifier"], f"{name}.qualifier")
    status = _text(record["status"], f"{name}.status", 32)
    if status not in STATUSES:
        raise EvidenceError(f"{name}.status unsupported: {status}")
    visibility = _text(record["visibility"], f"{name}.visibility", 16)
    if visibility not in VISIBILITIES:
        raise EvidenceError(f"{name}.visibility unsupported: {visibility}")
    source_kind = _text(record["source_kind"], f"{name}.source_kind", 64)
    if source_kind not in SOURCE_KINDS:
        raise EvidenceError(f"{name}.source_kind unsupported: {source_kind}")
    source_ref = record["source_ref"]
    if source_ref is not None:
        source_ref = _text(source_ref, f"{name}.source_ref", 500)
    description = record["description"]
    if description is not None:
        description = _text(description, f"{name}.description", 1000)
    event_at = parse_ts(record["event_at"], f"{name}.event_at")
    if event_at > as_of:
        raise EvidenceError(f"{name}.event_at is after assessment time")
    valid_until_raw = record["valid_until"]
    valid_until = None
    if valid_until_raw is not None:
        valid_until = parse_ts(valid_until_raw, f"{name}.valid_until")
        if valid_until < event_at:
            raise EvidenceError(f"{name}.valid_until precedes event_at")

    if status == "VERIFIED":
        if source_kind in {"OWNER_ASSERTION", "SYNTHETIC_FIXTURE"}:
            raise EvidenceError(f"{name}: {source_kind} cannot mint VERIFIED evidence")
        if source_kind not in ALLOWED_VERIFIED_SOURCES[category]:
            raise EvidenceError(
                f"{name}: {source_kind} cannot establish VERIFIED {category} evidence"
            )
        if source_kind == "GITHUB_MERGED_PR":
            if source_ref is None or not source_ref.startswith("https://github.com/"):
                raise EvidenceError(f"{name}: GitHub merge evidence requires a github.com source_ref")
    if source_kind == "OWNER_PRIVATE_DOCUMENT" and visibility != "PRIVATE":
        raise EvidenceError(f"{name}: private-document evidence must be PRIVATE")
    if source_kind == "SYNTHETIC_FIXTURE" and status not in {"UNKNOWN", "MISSING"}:
        raise EvidenceError(f"{name}: synthetic fixtures cannot assert qualification support")

    effective_status = status
    if status == "VERIFIED" and valid_until is not None and valid_until < as_of:
        effective_status = "EXPIRED"

    return {
        "evidence_id": evidence_id,
        "category": category,
        "qualifier": qualifier,
        "status": status,
        "effective_status": effective_status,
        "visibility": visibility,
        "source_kind": source_kind,
        "source_ref": source_ref,
        "description": description,
        "event_at": record["event_at"],
        "valid_until": valid_until_raw,
    }


def normalize_vault(raw: Any, as_of: str) -> dict[str, Any]:
    as_of_dt = parse_ts(as_of, "as_of")
    vault = _obj(raw, "vault", {"schema", "records"})
    if vault["schema"] != VAULT_SCHEMA:
        raise EvidenceError("vault.schema mismatch")
    records = [
        _normalize_record(item, i, as_of_dt)
        for i, item in enumerate(_array(vault["records"], "vault.records", 2048))
    ]
    ids = [item["evidence_id"] for item in records]
    if len(ids) != len(set(ids)):
        raise EvidenceError("vault contains duplicate evidence_id")
    records.sort(key=lambda item: item["evidence_id"])
    return {"schema": VAULT_SCHEMA, "records": records}


def _normalize_requirement(raw: Any, index: int) -> dict[str, Any]:
    name = f"solicitation.requirements[{index}]"
    req = _obj(
        raw,
        name,
        {
            "requirement_id",
            "category",
            "qualifier",
            "min_count",
            "max_age_days",
            "partner_can_cure",
            "missing_disqualifies",
        },
    )
    category = _text(req["category"], f"{name}.category", 64)
    if category not in CATEGORIES:
        raise EvidenceError(f"{name}.category unsupported: {category}")
    max_age_days = req["max_age_days"]
    if max_age_days is not None:
        max_age_days = _integer(max_age_days, f"{name}.max_age_days", 0, 36500)
    return {
        "requirement_id": _token(req["requirement_id"], f"{name}.requirement_id"),
        "category": category,
        "qualifier": _qualifier(req["qualifier"], f"{name}.qualifier"),
        "min_count": _integer(req["min_count"], f"{name}.min_count", 1, 100),
        "max_age_days": max_age_days,
        "partner_can_cure": _boolean(req["partner_can_cure"], f"{name}.partner_can_cure"),
        "missing_disqualifies": _boolean(req["missing_disqualifies"], f"{name}.missing_disqualifies"),
    }


def normalize_solicitation(raw: Any) -> dict[str, Any]:
    solicitation = _obj(
        raw,
        "solicitation",
        {"schema", "solicitation_id", "title", "requirements"},
    )
    if solicitation["schema"] != SOLICITATION_SCHEMA:
        raise EvidenceError("solicitation.schema mismatch")
    requirements = [
        _normalize_requirement(item, i)
        for i, item in enumerate(_array(solicitation["requirements"], "solicitation.requirements", 256))
    ]
    ids = [item["requirement_id"] for item in requirements]
    if len(ids) != len(set(ids)):
        raise EvidenceError("solicitation contains duplicate requirement_id")
    requirements.sort(key=lambda item: item["requirement_id"])
    return {
        "schema": SOLICITATION_SCHEMA,
        "solicitation_id": _token(solicitation["solicitation_id"], "solicitation.solicitation_id"),
        "title": _text(solicitation["title"], "solicitation.title", 300),
        "requirements": requirements,
    }


def _record_is_fresh(record: dict[str, Any], req: dict[str, Any], as_of: datetime) -> bool:
    if record["effective_status"] != "VERIFIED":
        return False
    max_age = req["max_age_days"]
    if max_age is None:
        return True
    event = parse_ts(record["event_at"], "record.event_at")
    age_seconds = (as_of - event).total_seconds()
    return age_seconds <= max_age * 86400


def _evaluate_requirement(
    req: dict[str, Any], records: list[dict[str, Any]], as_of: datetime
) -> dict[str, Any]:
    matching = [
        item
        for item in records
        if item["category"] == req["category"]
        and (req["qualifier"] == "*" or item["qualifier"] == req["qualifier"])
    ]
    verified = [item for item in matching if _record_is_fresh(item, req, as_of)]
    owner_or_unknown = [
        item
        for item in matching
        if item["effective_status"] in {"OWNER_ONLY", "UNKNOWN"}
        or (item["effective_status"] == "VERIFIED" and not _record_is_fresh(item, req, as_of))
    ]
    explicit_gap = [
        item for item in matching if item["effective_status"] in {"MISSING", "EXPIRED"}
    ]

    if len(verified) >= req["min_count"]:
        result = "SATISFIED_BY_PRIME"
        reason = f"{len(verified)} verified exact-category evidence item(s) satisfy min_count={req['min_count']}"
    elif owner_or_unknown or not matching:
        result = "OWNER_EVIDENCE_REQUIRED"
        reason = "evidence is unknown/owner-only/stale or no explicit evidence record exists"
    elif explicit_gap and req["partner_can_cure"]:
        result = "PARTNER_GAP"
        reason = "explicit missing/expired prime evidence may be supplied by a qualified partner"
    elif explicit_gap and req["missing_disqualifies"]:
        result = "DISQUALIFYING_GAP"
        reason = "explicit missing/expired mandatory evidence is not partner-curable"
    else:
        result = "OWNER_EVIDENCE_REQUIRED"
        reason = "mandatory evidence is not verified"

    verified_public = [item for item in verified if item["visibility"] == "PUBLIC"]
    verified_private = [item for item in verified if item["visibility"] == "PRIVATE"]
    candidate_public = [item for item in matching if item["visibility"] == "PUBLIC"]
    candidate_private = [item for item in matching if item["visibility"] == "PRIVATE"]
    return {
        "requirement_id": req["requirement_id"],
        "category": req["category"],
        "qualifier": req["qualifier"],
        "min_count": req["min_count"],
        "result": result,
        "reason": reason,
        "verified_evidence_ids": sorted(item["evidence_id"] for item in verified_public),
        "verified_private_count": len(verified_private),
        "candidate_evidence_ids": sorted(item["evidence_id"] for item in candidate_public),
        "candidate_private_count": len(candidate_private),
    }


def _overall(results: list[dict[str, Any]]) -> str:
    kinds = {item["result"] for item in results}
    if "DISQUALIFYING_GAP" in kinds:
        return "DISQUALIFIED"
    if "OWNER_EVIDENCE_REQUIRED" in kinds:
        return "HOLD_MISSING_EVIDENCE"
    if "PARTNER_GAP" in kinds:
        return "PARTNER_ONLY"
    return "PRIME_SUPPORTED"


def compile_assessment(raw_vault: Any, raw_solicitation: Any, as_of: str) -> dict[str, Any]:
    as_of_dt = parse_ts(as_of, "as_of")
    vault = normalize_vault(raw_vault, as_of)
    solicitation = normalize_solicitation(raw_solicitation)
    results = [
        _evaluate_requirement(req, vault["records"], as_of_dt)
        for req in solicitation["requirements"]
    ]
    overall = _overall(results)
    partner_gaps = [
        {
            "requirement_id": item["requirement_id"],
            "category": item["category"],
            "qualifier": item["qualifier"],
            "prime_must_supply": False,
            "partner_may_supply": True,
        }
        for item in results
        if item["result"] == "PARTNER_GAP"
    ]
    owner_holds = [
        item["requirement_id"]
        for item in results
        if item["result"] == "OWNER_EVIDENCE_REQUIRED"
    ]
    packet = {
        "schema": ASSESSMENT_SCHEMA,
        "solicitation_id": solicitation["solicitation_id"],
        "title": solicitation["title"],
        "as_of": as_of,
        "outcome": overall,
        "vault_sha256": sha256_value(vault),
        "solicitation_sha256": sha256_value(solicitation),
        "requirements": results,
        "partner_gap_brief": partner_gaps,
        "owner_evidence_holds": sorted(owner_holds),
        "evidence_input_authentication": "CURATED_BUNDLE_NOT_LIVE_PROVIDER_AUTHENTICATED",
        "authority_flags": {
            "outreach_authorized": False,
            "proposal_submission_authorized": False,
            "buyer_acceptance_established": False,
            "award_established": False,
            "contract_authorized": False,
            "certification_assertion_authorized": False,
            "reference_use_authorized": False,
            "payment_or_revenue_established": False,
        },
        "interpretation": "Evidence qualification only. PRIME_SUPPORTED means every modeled requirement is supported by exact-category evidence in this vault; it is not buyer approval, award, certification, reference permission, contract authority, or revenue.",
    }
    packet["assessment_sha256"] = sha256_value(packet)
    return packet


def verify_assessment(raw_vault: Any, raw_solicitation: Any, packet: Any) -> bool:
    if type(packet) is not dict or packet.get("schema") != ASSESSMENT_SCHEMA:
        return False
    as_of = packet.get("as_of")
    if type(as_of) is not str:
        return False
    try:
        expected = compile_assessment(raw_vault, raw_solicitation, as_of)
        return canonical_bytes(expected) == canonical_bytes(packet)
    except EvidenceError:
        return False


def redact_vault(raw_vault: Any, as_of: str) -> dict[str, Any]:
    vault = normalize_vault(raw_vault, as_of)
    public_records: list[dict[str, Any]] = []
    private_count = 0
    for item in vault["records"]:
        if item["visibility"] == "PRIVATE":
            private_count += 1
            continue
        public_records.append(
            {
                "evidence_id": item["evidence_id"],
                "category": item["category"],
                "qualifier": item["qualifier"],
                "status": item["status"],
                "effective_status": item["effective_status"],
                "visibility": item["visibility"],
                "source_kind": item["source_kind"],
                "source_ref": item["source_ref"],
                "description": item["description"],
                "event_at": item["event_at"],
                "valid_until": item["valid_until"],
            }
        )
    out = {
        "schema": REDACTED_SCHEMA,
        "as_of": as_of,
        "records": public_records,
        "private_record_count": private_count,
    }
    out["public_vault_sha256"] = sha256_value(out)
    return out


def _md(text: Any) -> str:
    value = str(text)
    for char in ("\\", "`", "*", "_", "{", "}", "[", "]", "(", ")", "#", "+", "-", ".", "!", "|"):
        value = value.replace(char, "\\" + char)
    return value.replace("\r", " ").replace("\n", " ")


def render_markdown(packet: Any) -> str:
    if type(packet) is not dict or packet.get("schema") != ASSESSMENT_SCHEMA:
        raise EvidenceError("packet is not a qualification assessment")
    lines = [
        f"# Qualification assessment: {_md(packet['title'])}",
        "",
        f"- Solicitation: `{_md(packet['solicitation_id'])}`",
        f"- As of: `{_md(packet['as_of'])}`",
        f"- Outcome: **{_md(packet['outcome'])}**",
        f"- Assessment SHA-256: `{_md(packet['assessment_sha256'])}`",
        "",
        "## Mandatory evidence",
        "",
        "| Requirement | Category | Qualifier | Result | Evidence |",
        "|---|---|---|---|---|",
    ]
    for item in packet["requirements"]:
        evidence = ", ".join(item["verified_evidence_ids"]) or "—"
        lines.append(
            f"| {_md(item['requirement_id'])} | {_md(item['category'])} | {_md(item['qualifier'])} | {_md(item['result'])} | {_md(evidence)} |"
        )
    if packet["partner_gap_brief"]:
        lines += ["", "## Partner gaps", ""]
        for item in packet["partner_gap_brief"]:
            lines.append(
                f"- `{_md(item['requirement_id'])}`: partner may supply {_md(item['category'])} / {_md(item['qualifier'])}."
            )
    if packet["owner_evidence_holds"]:
        lines += ["", "## Owner evidence holds", ""]
        for item in packet["owner_evidence_holds"]:
            lines.append(f"- `{_md(item)}`")
    lines += [
        "",
        "## Authority ceiling",
        "",
        "This is evidence qualification only. It does not authorize outreach or submission and does not establish buyer acceptance, award, certification, reference permission, contract authority, payment, or revenue.",
        "",
    ]
    return "\n".join(lines)
