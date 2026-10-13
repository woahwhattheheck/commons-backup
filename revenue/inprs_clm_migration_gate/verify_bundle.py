#!/usr/bin/env python3
"""Deterministic evidence gate for an INPRS CLM migration/public-release bundle.

This validates a candidate evidence export. It does not connect to Conga, Icertis,
DocuSign, Outlook, INPRS, or any production system.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
from typing import Any

SCHEMA_VERSION = 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_KINDS = {"master", "amendment"}
ALLOWED_STATUS = {"active", "inactive"}
ALLOWED_PUBLIC_ACTIONS = {"publish_full", "publish_redacted", "withhold"}
ALLOWED_VENDOR_DOC_TYPES = {"certificate_of_insurance", "w9", "soc_report"}
PUBLIC_KEYS = {
    "legacy_id",
    "company_name",
    "service_type",
    "contract_cost_cents",
    "effective_date",
    "expiration_date",
    "procurement_method",
    "rfp_number",
    "document_sha256",
    "redacted",
    "redaction_attestation_sha256",
    "search_terms",
}
SEARCH_FIELDS = (
    "company_name",
    "service_type",
    "procurement_method",
    "rfp_number",
    "effective_date",
    "expiration_date",
)


def _err(code: str, subject: str, detail: str = "") -> str:
    suffix = f":{detail}" if detail else ""
    return f"{code}:{subject}{suffix}"


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


def _money_search_term(cents: Any) -> str | None:
    if not isinstance(cents, int) or isinstance(cents, bool) or cents < 0:
        return None
    return f"{cents // 100}.{cents % 100:02d}"


def canonical_search_terms(record: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in SEARCH_FIELDS:
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            values.append(value.strip().casefold())
    money = _money_search_term(record.get("contract_cost_cents"))
    if money is not None:
        values.append(money)
    return sorted(set(values))


def _validate_version_history(contract: dict[str, Any], cid: str, errors: list[str]) -> None:
    history = contract.get("version_history")
    if not isinstance(history, list) or not history:
        errors.append(_err("VERSION_HISTORY_MISSING", cid))
        return
    expected_revisions = list(range(1, len(history) + 1))
    actual_revisions: list[int] = []
    for idx, entry in enumerate(history, start=1):
        if not isinstance(entry, dict):
            errors.append(_err("VERSION_ENTRY_INVALID", cid, str(idx)))
            continue
        revision = entry.get("revision")
        sha = entry.get("sha256")
        if not isinstance(revision, int) or isinstance(revision, bool):
            errors.append(_err("VERSION_REVISION_INVALID", cid, str(idx)))
        else:
            actual_revisions.append(revision)
        if not _is_sha256(sha):
            errors.append(_err("VERSION_HASH_INVALID", cid, str(idx)))
    if actual_revisions and actual_revisions != expected_revisions:
        errors.append(_err("VERSION_SEQUENCE_INVALID", cid))
    if isinstance(history[-1], dict) and history[-1].get("sha256") != contract.get("target_sha256"):
        errors.append(_err("VERSION_FINAL_HASH_MISMATCH", cid))


def _validate_lineage(contracts: dict[str, dict[str, Any]], errors: list[str]) -> None:
    for cid, contract in sorted(contracts.items()):
        kind = contract.get("kind")
        parent = contract.get("parent_legacy_id")
        if kind == "master":
            if parent not in (None, ""):
                errors.append(_err("MASTER_HAS_PARENT", cid))
            continue
        if kind != "amendment":
            continue
        if not isinstance(parent, str) or not parent:
            errors.append(_err("AMENDMENT_PARENT_MISSING", cid))
            continue
        if parent not in contracts:
            errors.append(_err("AMENDMENT_PARENT_ORPHAN", cid, parent))
            continue

        seen = {cid}
        cursor = parent
        while True:
            if cursor in seen:
                errors.append(_err("LINEAGE_CYCLE", cid, cursor))
                break
            seen.add(cursor)
            ancestor = contracts.get(cursor)
            if ancestor is None:
                errors.append(_err("LINEAGE_ORPHAN", cid, cursor))
                break
            ancestor_kind = ancestor.get("kind")
            if ancestor_kind == "master":
                break
            if ancestor_kind != "amendment":
                errors.append(_err("LINEAGE_KIND_INVALID", cid, cursor))
                break
            next_parent = ancestor.get("parent_legacy_id")
            if not isinstance(next_parent, str) or not next_parent:
                errors.append(_err("LINEAGE_PARENT_MISSING", cid, cursor))
                break
            cursor = next_parent


def _expectation_errors(
    expectations: Any,
    *,
    contract_rows: list[dict[str, Any]],
    public_records: list[dict[str, Any]],
    vendor_documents: list[dict[str, Any]],
) -> list[str]:
    if not isinstance(expectations, dict):
        return ["EXPECTATIONS_MISSING:manifest"]

    counts = Counter(row.get("kind") for row in contract_rows)
    statuses = Counter(row.get("status") for row in contract_rows)
    actual = {
        "source_contract_count": len(contract_rows),
        "master_count": counts["master"],
        "amendment_count": counts["amendment"],
        "active_count": statuses["active"],
        "inactive_count": statuses["inactive"],
        "public_record_count": len(public_records),
        "vendor_document_count": len(vendor_documents),
    }
    errors: list[str] = []
    for key, value in actual.items():
        expected = expectations.get(key)
        if not isinstance(expected, int) or isinstance(expected, bool) or expected < 0:
            errors.append(_err("EXPECTATION_INVALID", key))
        elif expected != value:
            errors.append(_err("COUNT_MISMATCH", key, f"{expected}!={value}"))
    return errors


def validate_bundle(bundle: Any) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(bundle, dict):
        return {
            "ok": False,
            "schema_version": SCHEMA_VERSION,
            "stats": {},
            "errors": ["BUNDLE_INVALID:root"],
        }

    if bundle.get("schema_version") != SCHEMA_VERSION:
        errors.append(_err("SCHEMA_VERSION_INVALID", "bundle"))
    if bundle.get("source_system") != "Conga Contracts":
        errors.append(_err("SOURCE_SYSTEM_INVALID", "bundle"))

    raw_contracts = bundle.get("contracts")
    contract_rows = raw_contracts if isinstance(raw_contracts, list) else []
    if not isinstance(raw_contracts, list):
        errors.append(_err("CONTRACTS_INVALID", "bundle"))

    contracts: dict[str, dict[str, Any]] = {}
    for idx, row in enumerate(contract_rows):
        subject = f"row-{idx}"
        if not isinstance(row, dict):
            errors.append(_err("CONTRACT_INVALID", subject))
            continue
        cid = row.get("legacy_id")
        if not isinstance(cid, str) or not cid:
            errors.append(_err("CONTRACT_ID_INVALID", subject))
            continue
        if cid in contracts:
            errors.append(_err("DUPLICATE_CONTRACT_ID", cid))
            continue
        contracts[cid] = row

        if row.get("kind") not in ALLOWED_KINDS:
            errors.append(_err("CONTRACT_KIND_INVALID", cid))
        if row.get("status") not in ALLOWED_STATUS:
            errors.append(_err("CONTRACT_STATUS_INVALID", cid))
        if row.get("executed") is not True:
            errors.append(_err("CONTRACT_NOT_EXECUTED", cid))
        for field in ("source_sha256", "target_sha256"):
            if not _is_sha256(row.get(field)):
                errors.append(_err("CONTRACT_HASH_INVALID", cid, field))
        if _is_sha256(row.get("source_sha256")) and _is_sha256(row.get("target_sha256")):
            if row["source_sha256"] != row["target_sha256"]:
                errors.append(_err("MIGRATION_HASH_DRIFT", cid))
        if row.get("authorization_letter_attached") not in (True, False):
            errors.append(_err("AUTHORIZATION_LETTER_STATE_INVALID", cid))
        if row.get("public_action") not in ALLOWED_PUBLIC_ACTIONS:
            errors.append(_err("PUBLIC_ACTION_INVALID", cid))
        if row.get("public_action") == "withhold":
            reason = row.get("withhold_reason")
            if not isinstance(reason, str) or not reason.strip():
                errors.append(_err("WITHHOLD_REASON_MISSING", cid))
        if row.get("public_action") == "publish_redacted":
            if not _is_sha256(row.get("public_document_sha256")):
                errors.append(_err("PUBLIC_REDACTED_HASH_INVALID", cid))
            if not _is_sha256(row.get("redaction_attestation_sha256")):
                errors.append(_err("REDACTION_ATTESTATION_INVALID", cid))
            if row.get("public_document_sha256") == row.get("target_sha256"):
                errors.append(_err("REDACTION_HASH_NOT_DISTINCT", cid))
        if row.get("public_action") == "publish_full":
            if row.get("public_document_sha256") not in (None, row.get("target_sha256")):
                errors.append(_err("PUBLIC_FULL_HASH_MISMATCH", cid))
            if row.get("redaction_attestation_sha256") is not None:
                errors.append(_err("UNEXPECTED_REDACTION_ATTESTATION", cid))
        _validate_version_history(row, cid, errors)

    _validate_lineage(contracts, errors)

    raw_public = bundle.get("public_records")
    public_records = raw_public if isinstance(raw_public, list) else []
    if not isinstance(raw_public, list):
        errors.append(_err("PUBLIC_RECORDS_INVALID", "bundle"))
    public_by_id: dict[str, dict[str, Any]] = {}
    for idx, row in enumerate(public_records):
        subject = f"row-{idx}"
        if not isinstance(row, dict):
            errors.append(_err("PUBLIC_RECORD_INVALID", subject))
            continue
        cid = row.get("legacy_id")
        if not isinstance(cid, str) or not cid:
            errors.append(_err("PUBLIC_ID_INVALID", subject))
            continue
        if cid in public_by_id:
            errors.append(_err("DUPLICATE_PUBLIC_ID", cid))
            continue
        public_by_id[cid] = row
        extra = sorted(set(row) - PUBLIC_KEYS)
        if extra:
            errors.append(_err("PUBLIC_FIELD_LEAK", cid, ",".join(extra)))
        source = contracts.get(cid)
        if source is None:
            errors.append(_err("PUBLIC_SOURCE_MISSING", cid))
            continue
        publication_mode = source.get("public_action")
        if publication_mode == "withhold":
            errors.append(_err("WITHHELD_RECORD_PUBLISHED", cid))
            continue
        if publication_mode not in {"publish_full", "publish_redacted"}:
            continue

        for field in (
            "company_name",
            "service_type",
            "contract_cost_cents",
            "effective_date",
            "expiration_date",
            "procurement_method",
            "rfp_number",
        ):
            if row.get(field) != source.get(field):
                errors.append(_err("PUBLIC_METADATA_MISMATCH", cid, field))

        expected_redacted = publication_mode == "publish_redacted"
        if row.get("redacted") is not expected_redacted:
            errors.append(_err("PUBLIC_REDACTION_FLAG_MISMATCH", cid))
        expected_hash = source.get("public_document_sha256") if expected_redacted else source.get("target_sha256")
        if row.get("document_sha256") != expected_hash:
            errors.append(_err("PUBLIC_DOCUMENT_HASH_MISMATCH", cid))
        expected_attestation = source.get("redaction_attestation_sha256") if expected_redacted else None
        if row.get("redaction_attestation_sha256") != expected_attestation:
            errors.append(_err("PUBLIC_ATTESTATION_MISMATCH", cid))
        if row.get("search_terms") != canonical_search_terms(row):
            errors.append(_err("PUBLIC_SEARCH_TERMS_MISMATCH", cid))

    for cid, source in sorted(contracts.items()):
        publication_mode = source.get("public_action")
        if publication_mode in {"publish_full", "publish_redacted"} and cid not in public_by_id:
            errors.append(_err("PUBLIC_RECORD_MISSING", cid))

    raw_vendor_docs = bundle.get("vendor_documents")
    vendor_documents = raw_vendor_docs if isinstance(raw_vendor_docs, list) else []
    if not isinstance(raw_vendor_docs, list):
        errors.append(_err("VENDOR_DOCUMENTS_INVALID", "bundle"))
    vendor_ids: set[str] = set()
    for idx, row in enumerate(vendor_documents):
        subject = f"row-{idx}"
        if not isinstance(row, dict):
            errors.append(_err("VENDOR_DOCUMENT_INVALID", subject))
            continue
        doc_id = row.get("document_id")
        if not isinstance(doc_id, str) or not doc_id:
            errors.append(_err("VENDOR_DOCUMENT_ID_INVALID", subject))
            continue
        if doc_id in vendor_ids:
            errors.append(_err("DUPLICATE_VENDOR_DOCUMENT_ID", doc_id))
            continue
        vendor_ids.add(doc_id)
        if row.get("document_type") not in ALLOWED_VENDOR_DOC_TYPES:
            errors.append(_err("VENDOR_DOCUMENT_TYPE_INVALID", doc_id))
        if row.get("access") != "internal":
            errors.append(_err("VENDOR_DOCUMENT_PUBLIC_ACCESS", doc_id))
        if not _is_sha256(row.get("source_sha256")) or not _is_sha256(row.get("target_sha256")):
            errors.append(_err("VENDOR_DOCUMENT_HASH_INVALID", doc_id))
        elif row["source_sha256"] != row["target_sha256"]:
            errors.append(_err("VENDOR_DOCUMENT_HASH_DRIFT", doc_id))

    errors.extend(
        _expectation_errors(
            bundle.get("expectations"),
            contract_rows=contract_rows,
            public_records=public_records,
            vendor_documents=vendor_documents,
        )
    )

    stats = {
        "contracts": len(contract_rows),
        "masters": sum(1 for row in contract_rows if isinstance(row, dict) and row.get("kind") == "master"),
        "amendments": sum(1 for row in contract_rows if isinstance(row, dict) and row.get("kind") == "amendment"),
        "active": sum(1 for row in contract_rows if isinstance(row, dict) and row.get("status") == "active"),
        "inactive": sum(1 for row in contract_rows if isinstance(row, dict) and row.get("status") == "inactive"),
        "public_records": len(public_records),
        "vendor_documents": len(vendor_documents),
    }
    return {
        "ok": not errors,
        "schema_version": SCHEMA_VERSION,
        "stats": stats,
        "errors": sorted(set(errors)),
    }


def canonical_report_bytes(report: dict[str, Any]) -> bytes:
    return (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def load_bundle(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    report = validate_bundle(load_bundle(args.bundle))
    payload = canonical_report_bytes(report)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_bytes(payload)
    print(payload.decode("utf-8"), end="")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())