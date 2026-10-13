"""Deterministic, evidence-only bidder qualification vault.

The vault checks PII-minimized metadata against independently retained snapshot
roots. It never authorizes contact, submission, signing, certification claims,
payment, award, or revenue recognition.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any

AUTHORITY_SCHEMA = "bidder-qualification-vault/authority/v1"
REGISTRY_SCHEMA = "bidder-qualification-vault/registry/v1"
QUERY_SCHEMA = "bidder-qualification-vault/query/v1"
RESULT_SCHEMA = "bidder-qualification-vault/result/v1"
RECEIPT_SCHEMA = "bidder-qualification-vault/receipt/v1"
BUNDLE_SCHEMA = "bidder-qualification-vault/bundle/v1"

KINDS = {
    "ENTITY_STANDING", "CORPORATE_PAST_PERFORMANCE", "CLIENT_REFERENCE",
    "STAFF_CREDENTIAL", "STAFF_AVAILABILITY", "INSURANCE_ARTIFACT",
    "SECURITY_ARTIFACT", "FINANCIAL_DOCUMENT", "SIGNER_AUTHORITY", "VENDOR_FORM",
}
STATES = {"EVIDENCED", "PENDING", "WITHDRAWN"}
RELEASE_RANK = {"NONE": 0, "NAMING": 1, "CONTACT": 2}
ACTION_AUTHORITY_KEYS = (
    "buyer_contact", "reference_contact", "proposal_submission", "portal_mutation",
    "signature", "certification_claim", "insurance_adequacy_claim", "solvency_claim",
    "pricing_commitment", "contract_acceptance", "payment_mutation", "award_claim",
    "revenue_claim",
)
TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CURRENCY = re.compile(r"^[A-Z]{3}$")


class VaultError(ValueError):
    """Fail-closed input, trust, or verification error."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise VaultError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _bad_number(value: str) -> None:
    raise VaultError(f"non-finite JSON number forbidden: {value}")


def _bad_float(value: str) -> None:
    raise VaultError(f"floating-point JSON number forbidden: {value}")


def load_json(raw: bytes, label: str = "input") -> dict[str, Any]:
    if not isinstance(raw, (bytes, bytearray)):
        raise VaultError(f"{label}: bytes required")
    raw = bytes(raw)
    if raw.startswith(b"\xef\xbb\xbf"):
        raise VaultError(f"{label}: UTF-8 BOM forbidden")
    try:
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_pairs,
                           parse_constant=_bad_number, parse_float=_bad_float)
    except VaultError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise VaultError(f"{label}: invalid JSON/UTF-8") from exc
    if not isinstance(value, dict):
        raise VaultError(f"{label}: top level must be object")
    return value


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_sha256(value: dict[str, Any]) -> str:
    return _digest(canonical(value))


def _keys(value: Any, expected: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VaultError(f"{where}: object required")
    got = set(value)
    if got != expected:
        raise VaultError(f"{where}: keys mismatch missing={sorted(expected-got)} extra={sorted(got-expected)}")
    return value


def _str(value: Any, where: str, *, token: bool = False, limit: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value) > limit or any(ord(ch) < 32 for ch in value):
        raise VaultError(f"{where}: safe non-empty string <= {limit} chars required")
    if token and not TOKEN.fullmatch(value):
        raise VaultError(f"{where}: invalid token")
    return value


def _int(value: Any, where: str, lo: int = 0, hi: int = 10**12) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise VaultError(f"{where}: integer {lo}..{hi} required (bool forbidden)")
    return value


def _bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise VaultError(f"{where}: boolean required")
    return value


def _sha(value: Any, where: str) -> str:
    text = _str(value, where, limit=64)
    if not SHA.fullmatch(text):
        raise VaultError(f"{where}: lowercase sha256 required")
    return text


def _optional_sha(value: Any, where: str) -> str | None:
    return None if value is None else _sha(value, where)


def _parse_ts(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _ts(value: Any, where: str) -> str:
    text = _str(value, where, limit=20)
    try:
        if not TS.fullmatch(text):
            raise ValueError
        _parse_ts(text)
    except ValueError as exc:
        raise VaultError(f"{where}: RFC3339 UTC second timestamp required") from exc
    return text


def _day(value: Any, where: str) -> str:
    text = _str(value, where, limit=10)
    try:
        if not DAY.fullmatch(text):
            raise ValueError
        date.fromisoformat(text)
    except ValueError as exc:
        raise VaultError(f"{where}: YYYY-MM-DD required") from exc
    return text


def _optional_day(value: Any, where: str) -> str | None:
    return None if value is None else _day(value, where)


def _enum(value: Any, allowed: set[str] | dict[str, int], where: str) -> str:
    text = _str(value, where, token=True)
    if text not in allowed:
        raise VaultError(f"{where}: unsupported value {text!r}")
    return text


def _now(value: datetime | str, where: str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise VaultError(f"{where}: timezone-aware datetime required")
        value = value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    return _ts(value, where)


def _meta(kind: str, value: Any, where: str) -> dict[str, Any]:
    if kind == "ENTITY_STANDING":
        value = _keys(value, {"jurisdiction", "standing"}, where)
        return {"jurisdiction": _str(value["jurisdiction"], where+".jurisdiction", token=True),
                "standing": _enum(value["standing"], {"GOOD", "OTHER"}, where+".standing")}
    if kind == "CORPORATE_PAST_PERFORMANCE":
        value = _keys(value, {"engagement_type", "completed_on", "corporate_history"}, where)
        return {"engagement_type": _str(value["engagement_type"], where+".engagement_type", token=True),
                "completed_on": _day(value["completed_on"], where+".completed_on"),
                "corporate_history": _bool(value["corporate_history"], where+".corporate_history")}
    if kind == "CLIENT_REFERENCE":
        value = _keys(value, {"organization_sha256", "release"}, where)
        return {"organization_sha256": _sha(value["organization_sha256"], where+".organization_sha256"),
                "release": _enum(value["release"], RELEASE_RANK, where+".release")}
    if kind == "STAFF_CREDENTIAL":
        value = _keys(value, {"staff_id", "credential", "status"}, where)
        return {"staff_id": _str(value["staff_id"], where+".staff_id", token=True),
                "credential": _str(value["credential"], where+".credential", token=True),
                "status": _enum(value["status"], {"CURRENT", "OTHER"}, where+".status")}
    if kind == "STAFF_AVAILABILITY":
        value = _keys(value, {"staff_id", "available_from", "available_through"}, where)
        start, end = _day(value["available_from"], where+".available_from"), _day(value["available_through"], where+".available_through")
        if start > end:
            raise VaultError(f"{where}: availability range reversed")
        return {"staff_id": _str(value["staff_id"], where+".staff_id", token=True), "available_from": start, "available_through": end}
    if kind == "INSURANCE_ARTIFACT":
        value = _keys(value, {"coverage", "currency", "limit_minor", "status"}, where)
        currency = _str(value["currency"], where+".currency", limit=3)
        if not CURRENCY.fullmatch(currency):
            raise VaultError(f"{where}.currency: uppercase ISO-like code required")
        return {"coverage": _str(value["coverage"], where+".coverage", token=True), "currency": currency,
                "limit_minor": _int(value["limit_minor"], where+".limit_minor"),
                "status": _enum(value["status"], {"ACTIVE", "OTHER"}, where+".status")}
    if kind == "SECURITY_ARTIFACT":
        value = _keys(value, {"artifact", "status"}, where)
        return {"artifact": _str(value["artifact"], where+".artifact", token=True),
                "status": _enum(value["status"], {"CURRENT", "OTHER"}, where+".status")}
    if kind == "FINANCIAL_DOCUMENT":
        value = _keys(value, {"document_type", "period_start", "period_end"}, where)
        start, end = _day(value["period_start"], where+".period_start"), _day(value["period_end"], where+".period_end")
        if start > end:
            raise VaultError(f"{where}: financial period reversed")
        return {"document_type": _str(value["document_type"], where+".document_type", token=True), "period_start": start, "period_end": end}
    if kind == "SIGNER_AUTHORITY":
        value = _keys(value, {"staff_id", "scope", "delegation_status"}, where)
        return {"staff_id": _str(value["staff_id"], where+".staff_id", token=True),
                "scope": _str(value["scope"], where+".scope", token=True),
                "delegation_status": _enum(value["delegation_status"], {"ACTIVE", "OTHER"}, where+".delegation_status")}
    if kind == "VENDOR_FORM":
        value = _keys(value, {"form_type", "status"}, where)
        return {"form_type": _str(value["form_type"], where+".form_type", token=True),
                "status": _enum(value["status"], {"CURRENT", "OTHER"}, where+".status")}
    raise VaultError(f"{where}: unsupported kind")


def normalize_authority(value: dict[str, Any]) -> dict[str, Any]:
    value = _keys(value, {"schema", "authority_id", "generation", "previous_authority_sha256", "issued_at", "evidence"}, "authority")
    if value["schema"] != AUTHORITY_SCHEMA:
        raise VaultError("authority.schema: unsupported")
    generation = _int(value["generation"], "authority.generation", 1)
    previous = _optional_sha(value["previous_authority_sha256"], "authority.previous_authority_sha256")
    if (generation == 1) != (previous is None):
        raise VaultError("authority.previous_authority_sha256: generation 1 has no predecessor; later generations require one")
    raw = value["evidence"]
    if not isinstance(raw, list) or not 1 <= len(raw) <= 4096:
        raise VaultError("authority.evidence: 1..4096 items required")
    items = []
    for i, row in enumerate(raw):
        row = _keys(row, {"evidence_id", "kind", "source_sha256"}, f"authority.evidence[{i}]")
        items.append({"evidence_id": _str(row["evidence_id"], f"authority.evidence[{i}].evidence_id", token=True),
                      "kind": _enum(row["kind"], KINDS, f"authority.evidence[{i}].kind"),
                      "source_sha256": _sha(row["source_sha256"], f"authority.evidence[{i}].source_sha256")})
    if len({x["evidence_id"] for x in items}) != len(items):
        raise VaultError("authority.evidence: duplicate evidence_id")
    return {"authority_id": _str(value["authority_id"], "authority.authority_id", token=True), "evidence": sorted(items, key=lambda x: x["evidence_id"]),
            "generation": generation, "issued_at": _ts(value["issued_at"], "authority.issued_at"), "previous_authority_sha256": previous, "schema": AUTHORITY_SCHEMA}


def normalize_registry(value: dict[str, Any]) -> dict[str, Any]:
    value = _keys(value, {"schema", "registry_id", "authority_id", "authority_generation", "generated_at", "items"}, "registry")
    if value["schema"] != REGISTRY_SCHEMA:
        raise VaultError("registry.schema: unsupported")
    raw = value["items"]
    if not isinstance(raw, list) or not 1 <= len(raw) <= 4096:
        raise VaultError("registry.items: 1..4096 items required")
    items = []
    for i, row in enumerate(raw):
        where = f"registry.items[{i}]"
        row = _keys(row, {"evidence_id", "kind", "source_sha256", "observed_at", "max_age_seconds", "valid_through", "state", "metadata"}, where)
        kind = _enum(row["kind"], KINDS, where+".kind")
        items.append({"evidence_id": _str(row["evidence_id"], where+".evidence_id", token=True), "kind": kind,
                      "max_age_seconds": _int(row["max_age_seconds"], where+".max_age_seconds", 1, 31536000),
                      "metadata": _meta(kind, row["metadata"], where+".metadata"), "observed_at": _ts(row["observed_at"], where+".observed_at"),
                      "source_sha256": _sha(row["source_sha256"], where+".source_sha256"), "state": _enum(row["state"], STATES, where+".state"),
                      "valid_through": _optional_day(row["valid_through"], where+".valid_through")})
    if len({x["evidence_id"] for x in items}) != len(items):
        raise VaultError("registry.items: duplicate evidence_id")
    return {"authority_generation": _int(value["authority_generation"], "registry.authority_generation", 1),
            "authority_id": _str(value["authority_id"], "registry.authority_id", token=True), "generated_at": _ts(value["generated_at"], "registry.generated_at"),
            "items": sorted(items, key=lambda x: x["evidence_id"]), "registry_id": _str(value["registry_id"], "registry.registry_id", token=True), "schema": REGISTRY_SCHEMA}


EXACT_FIELDS = {
    "ENTITY_STANDING": {"jurisdiction", "standing"}, "CORPORATE_PAST_PERFORMANCE": {"engagement_type"},
    "CLIENT_REFERENCE": {"organization_sha256", "release_at_least"}, "STAFF_CREDENTIAL": {"staff_id", "credential", "status"},
    "STAFF_AVAILABILITY": {"staff_id"}, "INSURANCE_ARTIFACT": {"coverage", "currency", "status"},
    "SECURITY_ARTIFACT": {"artifact", "status"}, "FINANCIAL_DOCUMENT": {"document_type"},
    "SIGNER_AUTHORITY": {"staff_id", "scope", "delegation_status"}, "VENDOR_FORM": {"form_type", "status"},
}


def normalize_query(value: dict[str, Any]) -> dict[str, Any]:
    value = _keys(value, {"schema", "query_id", "subject_id", "authority_id", "authority_generation", "registry_id", "registry_max_age_seconds", "requirements"}, "query")
    if value["schema"] != QUERY_SCHEMA:
        raise VaultError("query.schema: unsupported")
    raw = value["requirements"]
    if not isinstance(raw, list) or not 1 <= len(raw) <= 512:
        raise VaultError("query.requirements: 1..512 items required")
    requirements = []
    for i, row in enumerate(raw):
        where = f"query.requirements[{i}]"
        row = _keys(row, {"requirement_id", "kind", "min_count", "exact"}, where)
        kind = _enum(row["kind"], KINDS, where+".kind")
        exact = row["exact"]
        if not isinstance(exact, dict) or not set(exact) <= EXACT_FIELDS[kind]:
            raise VaultError(f"{where}.exact: unsupported selector field")
        norm_exact: dict[str, Any] = {}
        for key, val in exact.items():
            if key in {"organization_sha256"}:
                norm_exact[key] = _sha(val, where+".exact."+key)
            elif key == "release_at_least":
                norm_exact[key] = _enum(val, RELEASE_RANK, where+".exact.release_at_least")
            else:
                norm_exact[key] = _str(val, where+".exact."+key, token=True)
        requirements.append({"exact": dict(sorted(norm_exact.items())), "kind": kind, "min_count": _int(row["min_count"], where+".min_count", 1, 4096),
                             "requirement_id": _str(row["requirement_id"], where+".requirement_id", token=True)})
    if len({x["requirement_id"] for x in requirements}) != len(requirements):
        raise VaultError("query.requirements: duplicate requirement_id")
    return {"authority_generation": _int(value["authority_generation"], "query.authority_generation", 1),
            "authority_id": _str(value["authority_id"], "query.authority_id", token=True), "query_id": _str(value["query_id"], "query.query_id", token=True),
            "registry_id": _str(value["registry_id"], "query.registry_id", token=True), "registry_max_age_seconds": _int(value["registry_max_age_seconds"], "query.registry_max_age_seconds", 1, 31536000),
            "requirements": sorted(requirements, key=lambda x: x["requirement_id"]), "schema": QUERY_SCHEMA,
            "subject_id": _str(value["subject_id"], "query.subject_id", token=True)}


def roots(authority: dict[str, Any], registry: dict[str, Any]) -> tuple[str, str]:
    """Setup convenience only; production roots must be independently retained."""
    return canonical_sha256(normalize_authority(deepcopy(authority))), canonical_sha256(normalize_registry(deepcopy(registry)))


def _bind(authority: dict[str, Any], registry: dict[str, Any], query: dict[str, Any], expected_authority_sha256: str, expected_registry_sha256: str) -> tuple[str, str, str]:
    a_sha, r_sha, q_sha = canonical_sha256(authority), canonical_sha256(registry), canonical_sha256(query)
    if a_sha != _sha(expected_authority_sha256, "expected_authority_sha256"):
        raise VaultError("authority root mismatch")
    if r_sha != _sha(expected_registry_sha256, "expected_registry_sha256"):
        raise VaultError("registry root mismatch")
    if registry["authority_id"] != authority["authority_id"] or registry["authority_generation"] != authority["generation"]:
        raise VaultError("registry: authority binding mismatch")
    if query["authority_id"] != authority["authority_id"] or query["authority_generation"] != authority["generation"] or query["registry_id"] != registry["registry_id"]:
        raise VaultError("query: snapshot binding mismatch")
    auth = {x["evidence_id"]: x for x in authority["evidence"]}
    reg = {x["evidence_id"]: x for x in registry["items"]}
    if set(auth) != set(reg):
        raise VaultError("authority/registry evidence set mismatch")
    for eid in auth:
        if auth[eid]["kind"] != reg[eid]["kind"] or auth[eid]["source_sha256"] != reg[eid]["source_sha256"]:
            raise VaultError(f"authority/registry evidence binding mismatch: {eid}")
    return a_sha, r_sha, q_sha


def _liveness(item: dict[str, Any], when: str) -> tuple[bool, list[str]]:
    now = _parse_ts(when)
    observed = _parse_ts(item["observed_at"])
    reasons: list[str] = []
    if observed > now:
        reasons.append("FUTURE_OBSERVATION")
    elif int((now-observed).total_seconds()) > item["max_age_seconds"]:
        reasons.append("STALE_EVIDENCE")
    if item["valid_through"] is not None and when[:10] > item["valid_through"]:
        reasons.append("EXPIRED")
    if item["state"] != "EVIDENCED":
        reasons.append("STATE_"+item["state"])
    m, kind = item["metadata"], item["kind"]
    if kind == "ENTITY_STANDING" and m["standing"] != "GOOD": reasons.append("ENTITY_NOT_GOOD")
    if kind == "CORPORATE_PAST_PERFORMANCE" and not m["corporate_history"]: reasons.append("NOT_CORPORATE_HISTORY")
    if kind == "STAFF_CREDENTIAL" and m["status"] != "CURRENT": reasons.append("CREDENTIAL_NOT_CURRENT")
    if kind == "STAFF_AVAILABILITY" and not (m["available_from"] <= when[:10] <= m["available_through"]): reasons.append("STAFF_NOT_AVAILABLE")
    if kind == "INSURANCE_ARTIFACT" and m["status"] != "ACTIVE": reasons.append("INSURANCE_NOT_ACTIVE")
    if kind == "SECURITY_ARTIFACT" and m["status"] != "CURRENT": reasons.append("SECURITY_NOT_CURRENT")
    if kind == "SIGNER_AUTHORITY" and m["delegation_status"] != "ACTIVE": reasons.append("DELEGATION_NOT_ACTIVE")
    if kind == "VENDOR_FORM" and m["status"] != "CURRENT": reasons.append("FORM_NOT_CURRENT")
    return not reasons, sorted(reasons)


def _matches(item: dict[str, Any], exact: dict[str, Any]) -> bool:
    meta = item["metadata"]
    for key, val in exact.items():
        if key == "release_at_least":
            if item["kind"] != "CLIENT_REFERENCE" or RELEASE_RANK[meta["release"]] < RELEASE_RANK[val]: return False
        elif meta.get(key) != val:
            return False
    return True


def _authority_bits() -> dict[str, bool]:
    return {key: False for key in ACTION_AUTHORITY_KEYS}


def _semantic_notes() -> list[str]:
    return [
        "EVIDENCE_READY means only that the exact host-pinned evidence query is satisfied at evaluation time.",
        "Client reference release is evidence metadata and never authorizes contacting the reference.",
        "Financial documents prove presence and period only; solvency is never inferred.",
        "Insurance/security artifacts never become adequacy, certification, or authorization claims.",
        "Signer evidence never authorizes a signature; all action-authority flags are false.",
    ]


def _markdown(result: dict[str, Any]) -> str:
    lines = ["# Bidder Qualification Evidence Vault", "", f"- Query: `{result['query_id']}`", f"- Status: **{result['status']}**", f"- Evaluated at: `{result['evaluated_at']}`",
             f"- Authority: `{result['authority_id']}` generation `{result['authority_generation']}`", f"- Registry: `{result['registry_id']}`", "",
             "| Requirement | Kind | Status | Matched evidence | Reasons |", "|---|---|---|---|---|"]
    for row in result["requirements"]:
        lines.append(f"| {row['requirement_id']} | {row['kind']} | {row['status']} | {', '.join(row['matched_evidence_ids']) or '-'} | {', '.join(row['status_reasons']) or '-'} |")
    lines += ["", "## Semantic boundary", ""] + [f"- {x}" for x in result["semantic_notes"]]
    lines += ["", "All action-authority flags in this receipt are `false`.", ""]
    return "\n".join(lines)


def compile_vault(authority_value: dict[str, Any], registry_value: dict[str, Any], query_value: dict[str, Any], *, expected_authority_sha256: str, expected_registry_sha256: str, evaluated_at: datetime | str) -> dict[str, Any]:
    authority, registry, query = normalize_authority(deepcopy(authority_value)), normalize_registry(deepcopy(registry_value)), normalize_query(deepcopy(query_value))
    when = _now(evaluated_at, "evaluated_at")
    a_sha, r_sha, q_sha = _bind(authority, registry, query, expected_authority_sha256, expected_registry_sha256)
    now = _parse_ts(when)
    if _parse_ts(authority["issued_at"]) > now: raise VaultError("authority.issued_at: future authority")
    if _parse_ts(registry["generated_at"]) > now: raise VaultError("registry.generated_at: future registry")
    registry_age = int((now-_parse_ts(registry["generated_at"])).total_seconds())
    registry_stale = registry_age > query["registry_max_age_seconds"]
    rows = []
    for req in query["requirements"]:
        matched, rejected = [], []
        for item in registry["items"]:
            if item["kind"] != req["kind"] or not _matches(item, req["exact"]): continue
            live, reasons = _liveness(item, when)
            if live and not registry_stale: matched.append(item["evidence_id"])
            else: rejected.append({"evidence_id": item["evidence_id"], "reasons": sorted(reasons + (["REGISTRY_STALE"] if registry_stale else []))})
        ready = len(matched) >= req["min_count"]
        reasons = [] if ready else (["INSUFFICIENT_EVIDENCE"] + (["REGISTRY_STALE"] if registry_stale else []))
        rows.append({"kind": req["kind"], "matched_evidence_ids": sorted(matched), "min_count": req["min_count"], "rejected": sorted(rejected, key=lambda x:x["evidence_id"]),
                     "requirement_id": req["requirement_id"], "status": "EVIDENCE_READY" if ready else "HOLD", "status_reasons": sorted(set(reasons))})
    status = "EVIDENCE_READY" if all(x["status"] == "EVIDENCE_READY" for x in rows) else "HOLD"
    result = {"authority": _authority_bits(), "authority_generation": authority["generation"], "authority_id": authority["authority_id"], "authority_sha256": a_sha,
              "counts": {"EVIDENCE_READY": sum(x["status"]=="EVIDENCE_READY" for x in rows), "HOLD": sum(x["status"]=="HOLD" for x in rows)},
              "evaluated_at": when, "query_id": query["query_id"], "query_sha256": q_sha, "registry_id": registry["registry_id"], "registry_sha256": r_sha,
              "requirements": rows, "schema": RESULT_SCHEMA, "semantic_notes": _semantic_notes(), "status": status, "subject_id": query["subject_id"]}
    result_bytes = canonical(result)
    markdown = _markdown(result)
    receipt = {"authority": "EVIDENCE_ONLY", "authority_sha256": a_sha, "decision": status, "evaluated_at": when, "markdown_sha256": _digest(markdown.encode()),
               "query_sha256": q_sha, "registry_sha256": r_sha, "result_sha256": _digest(result_bytes), "schema": RECEIPT_SCHEMA}
    bundle = {"markdown": markdown, "receipt": receipt, "result": result, "schema": BUNDLE_SCHEMA}
    return bundle


def verify_bundle(authority_value: dict[str, Any], registry_value: dict[str, Any], query_value: dict[str, Any], bundle_value: dict[str, Any], *, expected_authority_sha256: str, expected_registry_sha256: str, verified_at: datetime | str) -> dict[str, Any]:
    bundle = _keys(deepcopy(bundle_value), {"schema", "result", "markdown", "receipt"}, "bundle")
    if bundle["schema"] != BUNDLE_SCHEMA or not isinstance(bundle["result"], dict) or not isinstance(bundle["receipt"], dict) or not isinstance(bundle["markdown"], str):
        raise VaultError("bundle: malformed or unsupported")
    result = bundle["result"]
    if result.get("schema") != RESULT_SCHEMA or "evaluated_at" not in result:
        raise VaultError("bundle.result: malformed or unsupported")
    historical = compile_vault(authority_value, registry_value, query_value, expected_authority_sha256=expected_authority_sha256,
                               expected_registry_sha256=expected_registry_sha256, evaluated_at=_ts(result["evaluated_at"], "bundle.result.evaluated_at"))
    if historical != bundle:
        raise VaultError("bundle: deterministic historical verification failed")
    current = compile_vault(authority_value, registry_value, query_value, expected_authority_sha256=expected_authority_sha256,
                            expected_registry_sha256=expected_registry_sha256, evaluated_at=verified_at)
    return {"authority": _authority_bits(), "current_counts": current["result"]["counts"], "current_evaluated_at": current["result"]["evaluated_at"],
            "current_result_sha256": _digest(canonical(current["result"])), "current_status": current["result"]["status"],
            "historical_evaluated_at": result["evaluated_at"], "historical_status": result["status"], "verified": True}


def _stdin() -> dict[str, Any]:
    return load_json(sys.stdin.buffer.read(), "stdin")


def _required(obj: dict[str, Any], keys: set[str], where: str) -> None:
    if set(obj) != keys:
        raise VaultError(f"{where}: keys mismatch missing={sorted(keys-set(obj))} extra={sorted(set(obj)-keys)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evidence-only bidder qualification vault")
    parser.add_argument("command", choices=("roots", "compile", "verify"))
    args = parser.parse_args(argv)
    try:
        env = _stdin()
        if args.command == "roots":
            _required(env, {"authority", "registry"}, "roots envelope")
            a, r = roots(env["authority"], env["registry"])
            out = {"authority_sha256": a, "registry_sha256": r,
                   "warning": "SETUP_ONLY: roots computed from supplied bytes do not establish trust; production consumers must use independently retained expected roots"}
            sys.stdout.buffer.write(canonical(out)); return 0
        now = datetime.now(timezone.utc).replace(microsecond=0)
        if args.command == "compile":
            _required(env, {"authority", "registry", "query", "expected_authority_sha256", "expected_registry_sha256"}, "compile envelope")
            bundle = compile_vault(env["authority"], env["registry"], env["query"], expected_authority_sha256=env["expected_authority_sha256"],
                                   expected_registry_sha256=env["expected_registry_sha256"], evaluated_at=now)
            sys.stdout.buffer.write(canonical(bundle)); return 0 if bundle["result"]["status"] == "EVIDENCE_READY" else 2
        _required(env, {"authority", "registry", "query", "expected_authority_sha256", "expected_registry_sha256", "bundle"}, "verify envelope")
        proof = verify_bundle(env["authority"], env["registry"], env["query"], env["bundle"], expected_authority_sha256=env["expected_authority_sha256"],
                              expected_registry_sha256=env["expected_registry_sha256"], verified_at=now)
        sys.stdout.buffer.write(canonical(proof)); return 0 if proof["current_status"] == "EVIDENCE_READY" else 2
    except VaultError as exc:
        sys.stderr.write(f"HOLD: {exc}\n"); return 3


if __name__ == "__main__":
    raise SystemExit(main())
