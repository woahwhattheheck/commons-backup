from __future__ import annotations

from typing import Any

from .codec import (
    AUTHORITY, BATCH_SCHEMA, MANIFEST_SCHEMA, MAX_RECORDS, RECEIPT_SCHEMA,
    GateInputError, _HEX64, _canonical, _dict, _keys, digest,
)
from .rules import classify, parse_record, parse_reference_set

__all__ = ["AUTHORITY", "GateInputError", "digest", "evaluate", "reference_commitment", "verify"]


def reference_commitment(references: Any) -> str:
    """Canonicalize and hash a reference set for trusted-host provisioning.

    Computing this digest does not authenticate provenance. Runtime callers must receive
    the expected digest from an independently retained host boundary.
    """
    return digest(parse_reference_set(references))


def _prepare(batch: Any, references: Any, expected_reference_sha256: str) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    if type(expected_reference_sha256) is not str or _HEX64.fullmatch(expected_reference_sha256) is None:
        raise GateInputError("expected_reference_sha256 must be lowercase sha256")
    ref = parse_reference_set(references)
    ref_sha = digest(ref)
    if ref_sha != expected_reference_sha256:
        raise GateInputError("reference-set commitment mismatch")

    obj = _dict(batch, "batch")
    _keys(obj, {"schema", "records"}, "batch")
    if obj["schema"] != BATCH_SCHEMA:
        raise GateInputError("unsupported batch schema")
    raw_records = obj["records"]
    if type(raw_records) is not list or not 1 <= len(raw_records) <= MAX_RECORDS:
        raise GateInputError("batch.records cardinality is out of bounds")

    by_id: dict[str, dict[str, Any]] = {}
    for raw in raw_records:
        record = parse_record(raw)
        prior = by_id.get(record["record_id"])
        if prior is not None:
            if digest(prior) != digest(record):
                raise GateInputError("same record_id decoded to different payload")
            continue
        by_id[record["record_id"]] = record

    ref_by_id = {row["record_id"]: row for row in ref["records"]}
    if set(ref_by_id) != set(by_id):
        missing = sorted(set(by_id) - set(ref_by_id))
        unused = sorted(set(ref_by_id) - set(by_id))
        raise GateInputError(f"reference universe mismatch: missing={missing} unused={unused}")
    return [by_id[rid] for rid in sorted(by_id)], ref, ref_sha


def evaluate(batch: Any, *, references: Any, expected_reference_sha256: str) -> dict[str, Any]:
    records, ref, ref_sha = _prepare(batch, references, expected_reference_sha256)
    ref_by_id = {row["record_id"]: row for row in ref["records"]}
    rows: list[dict[str, Any]] = []
    for record in records:
        reference = ref_by_id[record["record_id"]]
        status, holds = classify(record, reference)
        evidence = {
            "record_id": record["record_id"],
            "code": record["code"],
            "ingredient_id": record["ingredient_id"],
            "allergen_label_hash": record["allergen_label_hash"],
            "commercial_owner": record["commercial_owner"],
            "science_owner": record["science_owner"],
            "reference_generation": ref["generation"],
            "reference_record_sha256": digest(reference),
        }
        rows.append({
            "record_id": record["record_id"],
            "code": record["code"],
            "status": status,
            "holds": holds,
            "evidence_sha256": digest(evidence),
            "reference_record_sha256": digest(reference),
        })

    pass_count = sum(1 for row in rows if row["status"] == "PASS")
    hold_count = sum(1 for row in rows if row["status"] == "HOLD")
    defect_count = sum(len(row["holds"]) for row in rows)
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "authority": AUTHORITY,
        "reference_generation": ref["generation"],
        "reference_sha256": ref_sha,
        "rows": rows,
    }
    manifest_sha = digest(manifest)
    normalized_batch = {"schema": BATCH_SCHEMA, "records": records}
    core = {
        "schema": RECEIPT_SCHEMA,
        "authority": AUTHORITY,
        "decision": "HOLD" if hold_count else "PASS",
        "record_count": len(rows),
        "pass_count": pass_count,
        "hold_count": hold_count,
        "seeded_defect_count": defect_count,
        "batch_sha256": digest(normalized_batch),
        "reference_generation": ref["generation"],
        "reference_sha256": ref_sha,
        "manifest_sha256": manifest_sha,
        "source_writes": 0,
        "network_writes": 0,
        "external_authority": False,
        "formulation_approved": False,
        "claim_approved": False,
        "regulatory_decision": False,
        "product_release_authorized": False,
        "buyer_acceptance_inferred": False,
        "recognized_revenue_inferred": False,
        "trusted_reference_provenance_authenticated_by_this_package": False,
    }
    receipt = dict(core)
    receipt["receipt_sha256"] = digest(core)
    report = _report(rows, receipt)
    return {"receipt": receipt, "manifest": manifest, "report": report}


def _report(rows: list[dict[str, Any]], receipt: dict[str, Any]) -> str:
    lines = [
        "# Tate & Lyle / CP Kelco solution-proof report", "",
        f"authority: {receipt['authority']}",
        f"reference_generation: {receipt['reference_generation']}",
        f"reference_sha256: {receipt['reference_sha256']}",
        f"records: {receipt['record_count']}",
        f"PASS: {receipt['pass_count']}", f"HOLD: {receipt['hold_count']}",
        f"defects: {receipt['seeded_defect_count']}",
        f"manifest: {receipt['manifest_sha256']}", f"receipt: {receipt['receipt_sha256']}", "",
        "PASS/HOLD is evidence completeness only. The independently retained host pin is not authenticated by candidate bytes. Named owners decide.", "",
    ]
    for row in rows:
        holds = ",".join(row["holds"]) if row["holds"] else "-"
        lines.append(f"{row['status']} {row['record_id']} {row['code']} {holds}")
    return "\n".join(lines) + "\n"


def verify(result: Any, *, batch: Any, references: Any, expected_reference_sha256: str) -> bool:
    try:
        obj = _dict(result, "result")
        _keys(obj, {"receipt", "manifest", "report"}, "result")
        expected = evaluate(batch, references=references, expected_reference_sha256=expected_reference_sha256)
        receipt = _dict(obj["receipt"], "result.receipt")
        if receipt.get("source_writes") != 0 or receipt.get("network_writes") != 0:
            return False
        if receipt.get("external_authority") is not False:
            return False
        if receipt.get("trusted_reference_provenance_authenticated_by_this_package") is not False:
            return False
        return _canonical(expected) == _canonical(obj)
    except (GateInputError, KeyError, TypeError, ValueError):
        return False
