from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

SCHEMA = "commons-rfp-addenda-delta/v1"
GEN_SCHEMA = "commons-rfp-source-generation/v1"
DECISION_SCHEMA = "commons-rfp-review-decision/v1"
MAX_SOURCE_AGE = timedelta(days=7)

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_COORD = re.compile(r"^[^\x00-\x1f\x7f]{1,240}$")
_DOC_ROLES = {
    "BASE_RFP", "ADDENDUM", "Q_AND_A", "REQUIRED_FORM", "PRICING",
    "OTHER_CONTROLLING",
}
_AUTHORITY = {"OFFICIAL", "SECONDARY"}
_REQ_CLASSES = {"MANDATORY", "SCOREABLE", "INFORMATIONAL"}
_ROUTES = {"PRIME", "TEAMING", "BOTH", "OWNER_REVIEW"}
_REVIEW_CLASSES = {"TECHNICAL", "COMMERCIAL", "LEGAL", "SECURITY", "DELIVERY", "OTHER"}
_DECISIONS = {"REVIEWED", "OWNER_ACCEPTED", "EXCEPTION_REQUESTED", "NOT_APPLICABLE"}
_STATES = {"NO_MATERIAL_CHANGE", "REVIEW_REQUIRED", "SOURCE_REFRESH_REQUIRED", "CONFLICT", "HOLD"}

_GEN_KEYS = {
    "schema", "opportunity_id", "generation_id", "captured_at", "complete",
    "documents", "requirements",
}
_DOC_KEYS = {
    "document_id", "authority", "role", "url", "sha256",
    "supersedes_sha256",
}
_REQ_KEYS = {
    "requirement_id", "document_id", "coordinate", "statement_sha256",
    "class", "category", "route", "curable", "response_artifact",
    "deadline_utc", "review_class", "supersedes_sha256",
}
_DECISION_KEYS = {
    "schema", "decision_id", "opportunity_id", "generation_id",
    "requirement_id", "requirement_sha256", "decision", "decided_at",
    "evidence_sha256",
}


class DeltaError(ValueError):
    pass


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise DeltaError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(raw: bytes | str) -> Any:
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise DeltaError("input is not strict UTF-8") from exc
    elif type(raw) is str:
        text = raw
    else:
        raise DeltaError("JSON input must be bytes or str")
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=lambda x: (_ for _ in ()).throw(DeltaError(f"non-finite JSON: {x}")),
        )
    except DeltaError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise DeltaError("invalid JSON") from exc


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _exact_keys(value: Mapping[str, Any], keys: set[str], where: str) -> None:
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        raise DeltaError(f"{where} keys mismatch missing={missing} extra={extra}")


def _string(value: Any, where: str, *, max_len: int = 240) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        raise DeltaError(f"{where} must be a nonempty bounded string")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise DeltaError(f"{where} contains control characters")
    return value


def _id(value: Any, where: str) -> str:
    value = _string(value, where, max_len=128)
    if not _ID.fullmatch(value):
        raise DeltaError(f"{where} is not a safe identifier")
    return value


def _sha(value: Any, where: str) -> str:
    if type(value) is not str or not _SHA.fullmatch(value):
        raise DeltaError(f"{where} must be lowercase sha256")
    return value


def _nullable_sha(value: Any, where: str) -> str | None:
    if value is None:
        return None
    return _sha(value, where)


def _utc(value: Any, where: str) -> str:
    value = _string(value, where, max_len=32)
    if not value.endswith("Z"):
        raise DeltaError(f"{where} must be canonical UTC seconds")
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise DeltaError(f"{where} must be canonical UTC seconds") from exc
    if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise DeltaError(f"{where} is noncanonical")
    return value


def _dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _https(value: Any, where: str) -> str:
    value = _string(value, where, max_len=500)
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
        raise DeltaError(f"{where} must be canonical HTTPS without credentials/fragment")
    return value


def _enum(value: Any, allowed: set[str], where: str) -> str:
    if type(value) is not str or value not in allowed:
        raise DeltaError(f"{where} invalid")
    return value


def _nullable_text(value: Any, where: str, *, max_len: int = 160) -> str | None:
    if value is None:
        return None
    return _string(value, where, max_len=max_len)


def _nullable_utc(value: Any, where: str) -> str | None:
    if value is None:
        return None
    return _utc(value, where)


def normalize_generation(value: Any) -> dict[str, Any]:
    if type(value) is not dict:
        raise DeltaError("generation must be an object")
    _exact_keys(value, _GEN_KEYS, "generation")
    if value["schema"] != GEN_SCHEMA:
        raise DeltaError("unsupported generation schema")
    opportunity_id = _id(value["opportunity_id"], "opportunity_id")
    generation_id = _id(value["generation_id"], "generation_id")
    captured_at = _utc(value["captured_at"], "captured_at")
    if type(value["complete"]) is not bool:
        raise DeltaError("complete must be bool")
    if type(value["documents"]) is not list or not (1 <= len(value["documents"]) <= 256):
        raise DeltaError("documents must contain 1..256 rows")
    if type(value["requirements"]) is not list or len(value["requirements"]) > 4096:
        raise DeltaError("requirements must be a bounded list")

    documents = []
    doc_ids = set()
    for i, row in enumerate(value["documents"]):
        if type(row) is not dict:
            raise DeltaError(f"documents[{i}] must be object")
        _exact_keys(row, _DOC_KEYS, f"documents[{i}]")
        doc_id = _id(row["document_id"], f"documents[{i}].document_id")
        if doc_id in doc_ids:
            raise DeltaError(f"duplicate document_id: {doc_id}")
        doc_ids.add(doc_id)
        documents.append({
            "document_id": doc_id,
            "authority": _enum(row["authority"], _AUTHORITY, f"documents[{i}].authority"),
            "role": _enum(row["role"], _DOC_ROLES, f"documents[{i}].role"),
            "url": _https(row["url"], f"documents[{i}].url"),
            "sha256": _sha(row["sha256"], f"documents[{i}].sha256"),
            "supersedes_sha256": _nullable_sha(row["supersedes_sha256"], f"documents[{i}].supersedes_sha256"),
        })
    documents.sort(key=lambda x: x["document_id"])
    doc_map = {d["document_id"]: d for d in documents}
    if not any(d["authority"] == "OFFICIAL" and d["role"] == "BASE_RFP" for d in documents):
        raise DeltaError("generation must include an OFFICIAL BASE_RFP")

    requirements = []
    req_ids = set()
    for i, row in enumerate(value["requirements"]):
        if type(row) is not dict:
            raise DeltaError(f"requirements[{i}] must be object")
        _exact_keys(row, _REQ_KEYS, f"requirements[{i}]")
        req_id = _id(row["requirement_id"], f"requirements[{i}].requirement_id")
        if req_id in req_ids:
            raise DeltaError(f"duplicate requirement_id: {req_id}")
        req_ids.add(req_id)
        doc_id = _id(row["document_id"], f"requirements[{i}].document_id")
        if doc_id not in doc_map:
            raise DeltaError(f"requirement {req_id} references missing document")
        if doc_map[doc_id]["authority"] != "OFFICIAL":
            raise DeltaError(f"requirement {req_id} cannot be controlled by SECONDARY source")
        coord = _string(row["coordinate"], f"requirements[{i}].coordinate", max_len=240)
        if not _COORD.fullmatch(coord):
            raise DeltaError("invalid source coordinate")
        category = _id(row["category"], f"requirements[{i}].category")
        response_artifact = _nullable_text(
            row["response_artifact"], f"requirements[{i}].response_artifact", max_len=160
        )
        requirements.append({
            "requirement_id": req_id,
            "document_id": doc_id,
            "coordinate": coord,
            "statement_sha256": _sha(row["statement_sha256"], f"requirements[{i}].statement_sha256"),
            "class": _enum(row["class"], _REQ_CLASSES, f"requirements[{i}].class"),
            "category": category,
            "route": _enum(row["route"], _ROUTES, f"requirements[{i}].route"),
            "curable": row["curable"],
            "response_artifact": response_artifact,
            "deadline_utc": _nullable_utc(row["deadline_utc"], f"requirements[{i}].deadline_utc"),
            "review_class": _enum(row["review_class"], _REVIEW_CLASSES, f"requirements[{i}].review_class"),
            "supersedes_sha256": _nullable_sha(row["supersedes_sha256"], f"requirements[{i}].supersedes_sha256"),
        })
        if type(requirements[-1]["curable"]) is not bool:
            raise DeltaError(f"requirements[{i}].curable must be bool")
    requirements.sort(key=lambda x: x["requirement_id"])
    return {
        "schema": GEN_SCHEMA,
        "opportunity_id": opportunity_id,
        "generation_id": generation_id,
        "captured_at": captured_at,
        "complete": value["complete"],
        "documents": documents,
        "requirements": requirements,
    }


def normalize_decisions(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if type(value) is not list or len(value) > 4096:
        raise DeltaError("decisions must be a bounded list")
    out = []
    ids = set()
    for i, row in enumerate(value):
        if type(row) is not dict:
            raise DeltaError(f"decisions[{i}] must be object")
        _exact_keys(row, _DECISION_KEYS, f"decisions[{i}]")
        if row["schema"] != DECISION_SCHEMA:
            raise DeltaError("unsupported decision schema")
        did = _id(row["decision_id"], f"decisions[{i}].decision_id")
        if did in ids:
            raise DeltaError(f"duplicate decision_id: {did}")
        ids.add(did)
        out.append({
            "schema": DECISION_SCHEMA,
            "decision_id": did,
            "opportunity_id": _id(row["opportunity_id"], f"decisions[{i}].opportunity_id"),
            "generation_id": _id(row["generation_id"], f"decisions[{i}].generation_id"),
            "requirement_id": _id(row["requirement_id"], f"decisions[{i}].requirement_id"),
            "requirement_sha256": _sha(row["requirement_sha256"], f"decisions[{i}].requirement_sha256"),
            "decision": _enum(row["decision"], _DECISIONS, f"decisions[{i}].decision"),
            "decided_at": _utc(row["decided_at"], f"decisions[{i}].decided_at"),
            "evidence_sha256": _sha(row["evidence_sha256"], f"decisions[{i}].evidence_sha256"),
        })
    out.sort(key=lambda x: x["decision_id"])
    return out


def _req_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    return {k: row[k] for k in (
        "requirement_id", "document_id", "coordinate", "statement_sha256", "class",
        "category", "route", "curable", "response_artifact", "deadline_utc", "review_class",
    )}


def requirement_identity(row: Mapping[str, Any]) -> str:
    return sha(_req_projection(row))


def _doc_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    return {k: row[k] for k in ("document_id", "authority", "role", "url", "sha256")}


def _index(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, Mapping[str, Any]]:
    return {str(r[key]): r for r in rows}


def _decision_coverage(old: Mapping[str, Any], decisions: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    old_req = _index(old["requirements"], "requirement_id")
    coverage = {}
    for row in decisions:
        if row["opportunity_id"] != old["opportunity_id"] or row["generation_id"] != old["generation_id"]:
            raise DeltaError(f"decision {row['decision_id']} is cross-opportunity/generation")
        req = old_req.get(row["requirement_id"])
        if req is None:
            raise DeltaError(f"decision {row['decision_id']} references unknown old requirement")
        expected = requirement_identity(req)
        if row["requirement_sha256"] != expected:
            raise DeltaError(f"decision {row['decision_id']} is stale or forged")
        if _dt(row["decided_at"]) < _dt(old["captured_at"]):
            raise DeltaError(f"decision {row['decision_id']} predates its source generation")
        if row["requirement_id"] in coverage:
            raise DeltaError(f"multiple prior decisions for requirement {row['requirement_id']}")
        coverage[row["requirement_id"]] = row["decision_id"]
    return coverage

