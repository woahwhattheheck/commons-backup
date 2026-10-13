from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

INPUT_SCHEMA = "commons-offering-bundle-input/v1"
RECEIPT_SCHEMA = "commons-offering-bundle-receipt/v1"
READY = "READY_FOR_HUMAN_BUNDLE_REVIEW"
HOLD = "HOLD"
FAMILIES = {"product", "service", "expertise", "data"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.I)
SECRET_ASSIGN_RE = re.compile(r"\b(?:api[_-]?key|secret|password|token)\s*[:=]\s*\S+", re.I)
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")

TOP_KEYS = {"schema", "bundle_id", "title", "entries"}
ENTRY_KEYS = {
    "entry_id", "family", "version", "source", "evidence", "deliverables",
    "exclusions", "depends_on", "conflicts_with", "pricing", "authority",
}
SOURCE_KEYS = {"repository", "commit", "path", "content_sha256"}
EVIDENCE_KEYS = {"receipt_sha256", "verified_at", "max_age_seconds"}
DELIVERABLE_KEYS = {"deliverable_id", "description", "acceptance_criteria"}
PRICING_KEYS = {"mode", "currency", "amount_minor"}
AUTHORITY_KEYS = {
    "buyer_contact", "external_send", "contract_execution", "buyer_acceptance",
    "checkout_or_payment", "fulfillment", "revenue_recognition",
}


class DuplicateKeyError(ValueError):
    pass


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_strict(text: str) -> Any:
    def bad_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON value: {value}")

    return json.loads(text, object_pairs_hook=_pairs_no_duplicates, parse_constant=bad_constant)


def _ensure_json_value(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if type(value) is int:
        return
    if isinstance(value, float):
        raise ValueError(f"float forbidden at {path}")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _ensure_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"non-string key at {path}")
            _ensure_json_value(item, f"{path}.{key}")
        return
    raise ValueError(f"non-JSON value at {path}: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    _ensure_json_value(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _parse_z(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return parsed


def _exact_keys(obj: Any, expected: set[str], reason: str, reasons: list[str]) -> bool:
    if not isinstance(obj, dict):
        reasons.append(reason)
        return False
    if set(obj) != expected:
        reasons.append(reason)
        return False
    return True


def _safe_id(value: Any) -> bool:
    return isinstance(value, str) and bool(ID_RE.fullmatch(value))


def _safe_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/"):
        return False
    p = PurePosixPath(value)
    return all(part not in {"", ".", ".."} for part in p.parts)


def _sensitive_text(value: Any) -> bool:
    if not isinstance(value, str):
        return True
    return bool(
        EMAIL_RE.search(value)
        or SSN_RE.search(value)
        or BEARER_RE.search(value)
        or SECRET_ASSIGN_RE.search(value)
        or PRIVATE_KEY_RE.search(value)
    )


def _append_unique(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _entry_structural(entry: Any, reasons: list[str]) -> bool:
    if not _exact_keys(entry, ENTRY_KEYS, "ENTRY_SCHEMA_INVALID", reasons):
        return False
    if not _safe_id(entry["entry_id"]):
        _append_unique(reasons, "ENTRY_ID_INVALID")
    if entry["family"] not in FAMILIES:
        _append_unique(reasons, "FAMILY_INVALID")
    if not isinstance(entry["version"], str) or not entry["version"].strip() or len(entry["version"]) > 128:
        _append_unique(reasons, "VERSION_INVALID")

    source = entry["source"]
    if _exact_keys(source, SOURCE_KEYS, "SOURCE_SCHEMA_INVALID", reasons):
        if not isinstance(source["repository"], str) or not REPO_RE.fullmatch(source["repository"]):
            _append_unique(reasons, "SOURCE_REPOSITORY_INVALID")
        if not isinstance(source["commit"], str) or not COMMIT_RE.fullmatch(source["commit"]):
            _append_unique(reasons, "SOURCE_REF_NOT_IMMUTABLE")
        if not _safe_path(source["path"]):
            _append_unique(reasons, "SOURCE_PATH_INVALID")
        if not isinstance(source["content_sha256"], str) or not SHA256_RE.fullmatch(source["content_sha256"]):
            _append_unique(reasons, "SOURCE_DIGEST_INVALID")

    evidence = entry["evidence"]
    if _exact_keys(evidence, EVIDENCE_KEYS, "EVIDENCE_SCHEMA_INVALID", reasons):
        if not isinstance(evidence["receipt_sha256"], str) or not SHA256_RE.fullmatch(evidence["receipt_sha256"]):
            _append_unique(reasons, "EVIDENCE_DIGEST_INVALID")
        if _parse_z(evidence["verified_at"]) is None:
            _append_unique(reasons, "EVIDENCE_TIME_INVALID")
        if type(evidence["max_age_seconds"]) is not int or not (1 <= evidence["max_age_seconds"] <= 31_536_000):
            _append_unique(reasons, "EVIDENCE_MAX_AGE_INVALID")

    deliverables = entry["deliverables"]
    if not isinstance(deliverables, list) or not deliverables:
        _append_unique(reasons, "DELIVERABLES_MISSING")
    else:
        seen_deliverables: set[str] = set()
        for deliverable in deliverables:
            if not _exact_keys(deliverable, DELIVERABLE_KEYS, "DELIVERABLE_SCHEMA_INVALID", reasons):
                continue
            did = deliverable["deliverable_id"]
            if not _safe_id(did):
                _append_unique(reasons, "DELIVERABLE_ID_INVALID")
            elif did in seen_deliverables:
                _append_unique(reasons, "DELIVERABLE_ID_DUPLICATE")
            else:
                seen_deliverables.add(did)
            if not isinstance(deliverable["description"], str) or not deliverable["description"].strip():
                _append_unique(reasons, "DELIVERABLE_DESCRIPTION_INVALID")
            elif _sensitive_text(deliverable["description"]):
                _append_unique(reasons, "SENSITIVE_METADATA")
            criteria = deliverable["acceptance_criteria"]
            if not isinstance(criteria, list) or not criteria:
                _append_unique(reasons, "ACCEPTANCE_COVERAGE_MISSING")
            else:
                seen_criteria: set[str] = set()
                for criterion in criteria:
                    if not isinstance(criterion, str) or not criterion.strip() or len(criterion) > 500:
                        _append_unique(reasons, "ACCEPTANCE_CRITERION_INVALID")
                    elif criterion in seen_criteria:
                        _append_unique(reasons, "ACCEPTANCE_CRITERION_DUPLICATE")
                    elif _sensitive_text(criterion):
                        _append_unique(reasons, "SENSITIVE_METADATA")
                    else:
                        seen_criteria.add(criterion)

    exclusions = entry["exclusions"]
    if not isinstance(exclusions, list):
        _append_unique(reasons, "EXCLUSIONS_INVALID")
    else:
        for exclusion in exclusions:
            if not isinstance(exclusion, str) or not exclusion.strip() or len(exclusion) > 500:
                _append_unique(reasons, "EXCLUSIONS_INVALID")
            elif _sensitive_text(exclusion):
                _append_unique(reasons, "SENSITIVE_METADATA")

    for key, reason in (("depends_on", "DEPENDENCIES_INVALID"), ("conflicts_with", "CONFLICTS_INVALID")):
        value = entry[key]
        if not isinstance(value, list) or any(not _safe_id(x) for x in value) or len(set(value)) != len(value):
            _append_unique(reasons, reason)

    pricing = entry["pricing"]
    if _exact_keys(pricing, PRICING_KEYS, "PRICING_SCHEMA_INVALID", reasons):
        mode = pricing["mode"]
        if mode == "FIXED":
            if not isinstance(pricing["currency"], str) or not CURRENCY_RE.fullmatch(pricing["currency"]):
                _append_unique(reasons, "PRICE_CURRENCY_INVALID")
            if type(pricing["amount_minor"]) is not int or not (1 <= pricing["amount_minor"] <= 10**15):
                _append_unique(reasons, "PRICE_AMOUNT_INVALID")
        elif mode == "QUOTE_REQUIRED":
            if pricing["currency"] is not None or pricing["amount_minor"] is not None:
                _append_unique(reasons, "QUOTE_REQUIRED_MUST_NOT_CARRY_PRICE")
        else:
            _append_unique(reasons, "PRICING_MODE_INVALID")

    authority = entry["authority"]
    if _exact_keys(authority, AUTHORITY_KEYS, "AUTHORITY_SCHEMA_INVALID", reasons):
        for value in authority.values():
            if value is not False:
                _append_unique(reasons, "EXTERNAL_AUTHORITY_PRESENT")
    return True


def _cycle_exists(graph: dict[str, list[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for child in graph.get(node, []):
            if child in graph and visit(child):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def compile_bundle(manifest: Any, *, trusted_as_of: str) -> dict[str, Any]:
    reasons: list[str] = []
    try:
        _ensure_json_value(manifest)
        manifest_digest = sha256_json(manifest)
    except ValueError:
        manifest_digest = hashlib.sha256(repr(manifest).encode("utf-8", "backslashreplace")).hexdigest()
        reasons.append("NON_CANONICAL_JSON_VALUE")

    as_of = _parse_z(trusted_as_of)
    if as_of is None:
        reasons.append("TRUSTED_AS_OF_INVALID")

    bundle_id = None
    title = None
    entries: list[Any] = []
    if not _exact_keys(manifest, TOP_KEYS, "TOP_SCHEMA_INVALID", reasons):
        pass
    else:
        bundle_id = manifest["bundle_id"]
        title = manifest["title"]
        if not _safe_id(bundle_id):
            _append_unique(reasons, "BUNDLE_ID_INVALID")
        if not isinstance(title, str) or not title.strip() or len(title) > 160:
            _append_unique(reasons, "TITLE_INVALID")
        elif _sensitive_text(title):
            _append_unique(reasons, "SENSITIVE_METADATA")
        if manifest["schema"] != INPUT_SCHEMA:
            _append_unique(reasons, "INPUT_SCHEMA_UNSUPPORTED")
        if not isinstance(manifest["entries"], list) or len(manifest["entries"]) < 2 or len(manifest["entries"]) > 64:
            _append_unique(reasons, "ENTRY_COUNT_INVALID")
        else:
            entries = manifest["entries"]

    ids: list[str] = []
    families: set[str] = set()
    source_keys: dict[tuple[str, str, str], str] = {}
    graph: dict[str, list[str]] = {}
    fixed_currencies: set[str] = set()
    fixed_total = 0
    any_quote = False

    for entry in entries:
        structurally_dict = _entry_structural(entry, reasons)
        if not structurally_dict:
            continue
        entry_id = entry["entry_id"]
        if isinstance(entry_id, str):
            if entry_id in ids:
                _append_unique(reasons, "ENTRY_ID_DUPLICATE")
            ids.append(entry_id)
        family = entry["family"]
        if family in FAMILIES:
            families.add(family)

        source = entry["source"]
        if isinstance(source, dict) and set(source) == SOURCE_KEYS:
            repo, commit, path = source["repository"], source["commit"], source["path"]
            if isinstance(repo, str) and isinstance(commit, str) and isinstance(path, str):
                key = (repo, commit, path)
                prior = source_keys.get(key)
                if prior is not None and prior != entry_id:
                    _append_unique(reasons, "SOURCE_IDENTITY_DUPLICATE")
                source_keys[key] = entry_id

        depends = entry["depends_on"] if isinstance(entry["depends_on"], list) else []
        if isinstance(entry_id, str):
            graph[entry_id] = [x for x in depends if isinstance(x, str)]
        conflicts = entry["conflicts_with"] if isinstance(entry["conflicts_with"], list) else []
        if isinstance(entry_id, str) and entry_id in conflicts:
            _append_unique(reasons, "SELF_CONFLICT")

        pricing = entry["pricing"]
        if isinstance(pricing, dict) and set(pricing) == PRICING_KEYS:
            if pricing["mode"] == "FIXED" and isinstance(pricing["currency"], str) and type(pricing["amount_minor"]) is int:
                fixed_currencies.add(pricing["currency"])
                fixed_total += pricing["amount_minor"]
            elif pricing["mode"] == "QUOTE_REQUIRED":
                any_quote = True

        evidence = entry["evidence"]
        if as_of is not None and isinstance(evidence, dict) and set(evidence) == EVIDENCE_KEYS:
            verified = _parse_z(evidence["verified_at"])
            max_age = evidence["max_age_seconds"]
            if verified is not None and type(max_age) is int:
                if verified > as_of:
                    _append_unique(reasons, "EVIDENCE_FROM_FUTURE")
                elif (as_of - verified).total_seconds() > max_age:
                    _append_unique(reasons, "EVIDENCE_STALE")

    id_set = set(ids)
    if len(families) < 2:
        _append_unique(reasons, "CROSS_FAMILY_COMPOSITION_REQUIRED")
    for node, dependencies in graph.items():
        if node in dependencies:
            _append_unique(reasons, "DEPENDENCY_SELF_REFERENCE")
        if any(dep not in id_set for dep in dependencies):
            _append_unique(reasons, "DEPENDENCY_MISSING")
    if _cycle_exists(graph):
        _append_unique(reasons, "DEPENDENCY_CYCLE")
    for entry in entries:
        if not isinstance(entry, dict) or "entry_id" not in entry or "conflicts_with" not in entry:
            continue
        conflicts = entry["conflicts_with"]
        if isinstance(conflicts, list) and any(conflict in id_set for conflict in conflicts):
            _append_unique(reasons, "ENTRY_CONFLICT")
    if len(fixed_currencies) > 1:
        _append_unique(reasons, "MIXED_FIXED_CURRENCIES_UNSUPPORTED")
    if fixed_total > 10**15:
        _append_unique(reasons, "BUNDLE_PRICE_OVERFLOW")

    if any_quote:
        pricing_out: dict[str, Any] = {"mode": "QUOTE_REQUIRED", "currency": None, "amount_minor": None}
    elif fixed_currencies and len(fixed_currencies) == 1:
        pricing_out = {"mode": "FIXED", "currency": next(iter(fixed_currencies)), "amount_minor": fixed_total}
    else:
        pricing_out = {"mode": "QUOTE_REQUIRED", "currency": None, "amount_minor": None}

    source_commitments = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        source = entry.get("source")
        entry_id = entry.get("entry_id")
        if isinstance(source, dict) and set(source) == SOURCE_KEYS and isinstance(entry_id, str):
            source_commitments.append({"entry_id": entry_id, **source})
    source_commitments.sort(key=lambda row: row.get("entry_id", ""))

    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "bundle_id": bundle_id if isinstance(bundle_id, str) else None,
        "title": title if isinstance(title, str) else None,
        "status": READY if not reasons else HOLD,
        "reasons": sorted(reasons),
        "families": sorted(families),
        "entry_ids": sorted(set(ids)),
        "pricing": pricing_out,
        "source_commitments": source_commitments,
        "trusted_as_of": trusted_as_of,
        "manifest_digest": manifest_digest,
        "authority": {
            "buyer_contact": False,
            "external_send": False,
            "contract_execution": False,
            "buyer_acceptance": False,
            "checkout_or_payment": False,
            "fulfillment": False,
            "revenue_recognition": False,
        },
    }
    receipt["receipt_digest"] = sha256_json(receipt)
    return receipt


def verify_receipt(manifest: Any, *, trusted_as_of: str, receipt: Any) -> bool:
    if not isinstance(receipt, dict):
        return False
    return canonical_json(compile_bundle(manifest, trusted_as_of=trusted_as_of)) == canonical_json(receipt)


def render_markdown(receipt: dict[str, Any]) -> str:
    lines = [
        f"# Offering bundle — {receipt.get('bundle_id') or 'invalid'}",
        "",
        f"Status: **{receipt.get('status', HOLD)}**",
        f"Families: {', '.join(receipt.get('families', [])) or 'none'}",
        f"Entries: {', '.join(receipt.get('entry_ids', [])) or 'none'}",
    ]
    pricing = receipt.get("pricing", {})
    if pricing.get("mode") == "FIXED":
        lines.append(f"Price: {pricing.get('currency')} {pricing.get('amount_minor')} minor units")
    else:
        lines.append("Price: QUOTE_REQUIRED")
    reasons = receipt.get("reasons", [])
    if reasons:
        lines += ["", "## Holds"] + [f"- {reason}" for reason in reasons]
    lines += [
        "",
        "## Authority boundary",
        "This artifact is review evidence only. It does not authorize buyer contact, sending, contract execution, acceptance, payment, fulfillment, or revenue recognition.",
        "",
        f"Manifest SHA-256: `{receipt.get('manifest_digest', '')}`",
        f"Receipt SHA-256: `{receipt.get('receipt_digest', '')}`",
    ]
    return "\n".join(lines) + "\n"
