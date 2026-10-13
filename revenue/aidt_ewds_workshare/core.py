"""Offline AIDT workshare consistency receipts, not authenticated live evidence.

V2 retains compared manifests for semantic replay. The hosting Python process is
trusted; identifiers may be sensitive and no privacy certification is performed.
"""
from __future__ import annotations

import hashlib
import json
import re

SOLICITATION_ID="SRC0000036381"
BUYER="Alabama Industrial Development Training (AIDT)"
QUESTION_DEADLINE="2026-10-01T17:00:00-05:00"
PROPOSAL_DEADLINE="2026-10-15T16:30:00-05:00"
PUBLIC_PACKET_FILENAME="AIDT_RFP_-_Enterprise_Workforce_Development_System_FINAL.pdf"
REQUIRED_WORKSHARE_EVIDENCE=(
 "requirements_matrix","migration_reconciliation_plan",
 "salesforce_adobe_lms_integration_plan","workflow_acceptance_plan",
 "prime_qualification_matrix","economics_stop_ledger")
PRIME_GATE_EVIDENCE=(
 "three_relevant_references","two_relevant_state_or_local_case_studies",
 "salesforce_platform_compatibility","hosting_security_and_support_sla",
 "alabama_everify_and_required_compliance","alabama_buys_registration_for_submission",
 "complete_prime_pricing")
REQUIREMENTS=(
 ("historical_data_import",1,"migration_reconciliation"),
 ("workflow_automation",2,"acceptance_harness"),
 ("salesforce_interoperability",1,"integration_contract"),
 ("adobe_lms_sync",2,"integration_contract"),
 ("secure_role_based_access",1,"acceptance_harness"),
 ("reporting_and_dashboards",2,"acceptance_harness"),
 ("credential_tracking",2,"acceptance_harness"))
_ID=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,191}$")
_HEX=re.compile(r"^[0-9a-f]{64}$")
_SYSTEMS={"salesforce","adobe_lms","ewds"}
_OPS={"upsert_applicant","upsert_class","enroll","credential_update","attendance_update"}

MIGRATION_SCHEMA = "aidt-ewds-migration/v2"
SYNC_SCHEMA = "aidt-ewds-sync/v2"
READINESS_SCHEMA = "aidt-ewds-readiness/v2"
MAX_RECORDS = 10_000
MAX_CHILD_RECEIPTS = 128
MAX_COLLECTION_RECORDS = 20_000
MAX_CANONICAL_BYTES = 16 * 1024 * 1024


class WorkshareError(ValueError):
    """Invalid or internally inconsistent workshare evidence."""


def _obj(value, name):
    if type(value) is not dict:
        raise WorkshareError(f"{name}: plain object required")
    return value


def _exact(value, fields, name):
    _obj(value, name)
    if set(value) != set(fields):
        raise WorkshareError(f"{name}: exact fields required")


def _id(value, name):
    if type(value) is not str or not value.isascii() or not _ID.fullmatch(value):
        raise WorkshareError(f"{name}: bounded ASCII identifier required")
    return value


def _sha(value, name):
    if type(value) is not str or not _HEX.fullmatch(value):
        raise WorkshareError(f"{name}: lowercase SHA-256 required")
    return value


def _canon(value):
    try:
        result = json.dumps(value, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, RecursionError) as exc:
        raise WorkshareError("noncanonical JSON") from exc
    if len(result) > MAX_CANONICAL_BYTES:
        raise WorkshareError("canonical receipt exceeds byte bound")
    return result


def _digest(value):
    return hashlib.sha256(_canon(value)).hexdigest()


def _seal(value):
    out = dict(value)
    out["receipt_sha256"] = _digest(out)
    return out


def _list(value, name, limit):
    if type(value) not in (list, tuple):
        raise WorkshareError(f"{name}: plain sequence required")
    if len(value) > limit:
        raise WorkshareError(f"{name}: collection limit exceeded")
    return value


def _records(rows, name):
    out = {}
    for i, row in enumerate(_list(rows, name, MAX_RECORDS)):
        _exact(row, {"record_id", "record_sha256"}, f"{name}[{i}]")
        rid = _id(row["record_id"], "record_id")
        dig = _sha(row["record_sha256"], "record_sha256")
        if rid in out:
            raise WorkshareError(f"{name}: duplicate record_id {rid}")
        out[rid] = dig
    return out


def _rows(records):
    return [{"record_id": key, "record_sha256": records[key]}
            for key in sorted(records)]


def reconcile_migration(source_records, target_records):
    """Compare the complete caller-supplied ID/digest manifests.

    Empty collections match mathematically but do not demonstrate a migration.
    This function never opens records or establishes their external provenance.
    """
    source = _records(source_records, "source_records")
    target = _records(target_records, "target_records")
    source_ids, target_ids = set(source), set(target)
    missing = sorted(source_ids - target_ids)
    extra = sorted(target_ids - source_ids)
    mismatch = sorted(key for key in source_ids & target_ids
                      if source[key] != target[key])
    if not source and not target:
        decision = "NO_RECORDS_TO_RECONCILE"
    elif missing or extra or mismatch:
        decision = "HOLD_MIGRATION_RECONCILIATION"
    else:
        decision = "MIGRATION_RECONCILED"
    return _seal({
        "schema": MIGRATION_SCHEMA, "solicitation_id": SOLICITATION_ID,
        "source_records": _rows(source), "target_records": _rows(target),
        "source_count": len(source), "target_count": len(target),
        "source_manifest_sha256": _digest(sorted(source.items())),
        "target_manifest_sha256": _digest(sorted(target.items())),
        "missing_record_ids": missing, "extra_record_ids": extra,
        "mismatched_record_ids": mismatch, "decision": decision,
        "evidence_authority": "CALLER_SUPPLIED_MANIFESTS",
        "raw_record_payloads_included": False,
        "pii_assessment": "NOT_PERFORMED",
        "external_submission_authorized": False,
    })


def verify_migration_receipt(receipt, *, expected_source_manifest_sha256=None,
                             expected_target_manifest_sha256=None):
    """Replay semantics; optional independent manifest pins bind source bytes.

    Without independent pins this establishes consistency only. Legacy V1 lacks
    replay inputs and must be regenerated, not upgraded by trusting its summary.
    """
    r = _obj(receipt, "migration")
    if r.get("schema") != MIGRATION_SCHEMA:
        raise WorkshareError("migration v2 required; regenerate legacy receipt from manifests")
    fields = {
        "schema", "solicitation_id", "source_records", "target_records",
        "source_count", "target_count", "source_manifest_sha256",
        "target_manifest_sha256", "missing_record_ids", "extra_record_ids",
        "mismatched_record_ids", "decision", "evidence_authority",
        "raw_record_payloads_included", "pii_assessment",
        "external_submission_authorized", "receipt_sha256",
    }
    _exact(r, fields, "migration")
    for key in ("source_count", "target_count"):
        if type(r[key]) is not int or not 0 <= r[key] <= MAX_RECORDS:
            raise WorkshareError("migration count invalid")
    for key in ("source_records", "target_records", "missing_record_ids",
                "extra_record_ids", "mismatched_record_ids"):
        if type(r[key]) is not list:
            raise WorkshareError(f"{key}: receipt list required")
    for key in ("missing_record_ids", "extra_record_ids", "mismatched_record_ids"):
        for item in _list(r[key], key, MAX_RECORDS):
            _id(item, key)
    for key in ("source_manifest_sha256", "target_manifest_sha256", "receipt_sha256"):
        _sha(r[key], key)
    expected = reconcile_migration(r["source_records"], r["target_records"])
    if r["decision"] != expected["decision"]:
        raise WorkshareError("migration decision inconsistent")
    if _canon(r) != _canon(expected):
        raise WorkshareError("migration semantic or digest mismatch")
    for key, pin in (("source_manifest_sha256", expected_source_manifest_sha256),
                     ("target_manifest_sha256", expected_target_manifest_sha256)):
        if pin is not None and r[key] != _sha(pin, key + " independent pin"):
            raise WorkshareError(f"{key}: independent pin mismatch")
    return True


def compile_sync_receipt(event, observed):
    """Compare one supplied event with one supplied target observation; no I/O."""
    event_fields = {"source_system", "target_system", "event_id", "entity_ref",
                    "operation", "payload_sha256"}
    _exact(event, event_fields, "event")
    _exact(observed, {"accepted", "target_ref", "target_payload_sha256"}, "observed")
    source = _id(event["source_system"], "source_system")
    target = _id(event["target_system"], "target_system")
    if source not in _SYSTEMS or target not in _SYSTEMS or source == target:
        raise WorkshareError("unsupported system pair")
    operation = _id(event["operation"], "operation")
    if operation not in _OPS:
        raise WorkshareError("unsupported operation")
    material = {
        "source_system": source, "target_system": target,
        "event_id": _id(event["event_id"], "event_id"),
        "entity_ref": _id(event["entity_ref"], "entity_ref"),
        "operation": operation,
        "payload_sha256": _sha(event["payload_sha256"], "payload_sha256"),
    }
    if type(observed["accepted"]) is not bool:
        raise WorkshareError("accepted: bool required")
    target_ref = _id(observed["target_ref"], "target_ref")
    target_digest = _sha(observed["target_payload_sha256"], "target_payload_sha256")
    ok = observed["accepted"] and material["payload_sha256"] == target_digest
    return _seal({
        "schema": SYNC_SCHEMA, "solicitation_id": SOLICITATION_ID, **material,
        "idempotency_key": _digest(material),
        "observed_accepted": observed["accepted"],
        "observed_target_ref": target_ref,
        "observed_target_payload_sha256": target_digest,
        "decision": "SYNC_ACCEPTED_EXACT" if ok else "HOLD_SYNC_ACCEPTANCE",
        "evidence_authority": "CALLER_SUPPLIED_TARGET_RESULT",
        "transport_performed_by_compiler": False,
        "external_submission_authorized": False,
    })


def verify_sync_receipt(receipt):
    r = _obj(receipt, "sync")
    fields = {
        "schema", "solicitation_id", "source_system", "target_system", "event_id",
        "entity_ref", "operation", "payload_sha256", "idempotency_key",
        "observed_accepted", "observed_target_ref", "observed_target_payload_sha256",
        "decision", "evidence_authority", "transport_performed_by_compiler",
        "external_submission_authorized", "receipt_sha256",
    }
    _exact(r, fields, "sync")
    event = {key: r[key] for key in ("source_system", "target_system", "event_id",
                                    "entity_ref", "operation", "payload_sha256")}
    observed = {"accepted": r["observed_accepted"],
                "target_ref": r["observed_target_ref"],
                "target_payload_sha256": r["observed_target_payload_sha256"]}
    if _canon(compile_sync_receipt(event, observed)) != _canon(r):
        raise WorkshareError("sync semantic or digest mismatch")
    return True


def _children(receipts, name, verifier):
    result, seen = [], set()
    for receipt in _list(receipts, name, MAX_CHILD_RECEIPTS):
        verifier(receipt)
        identity = receipt["receipt_sha256"]
        if identity in seen:
            raise WorkshareError(f"{name}: duplicate receipt")
        seen.add(identity)
        # Verification fixed the schema/types. Detach every nested manifest now;
        # a later caller mutation must not rewrite an already-returned packet.
        result.append(json.loads(_canon(receipt)))
    return sorted(result, key=lambda row: row["receipt_sha256"])


def compile_readiness(evidence, migrations, syncs):
    """Evaluate ALL supplied current receipts, not one cherry-picked success.

    The caller selects the current collection. This does not establish complete
    project coverage or source authenticity. Retain history separately; removal
    of a failed current item requires an explicit operator scope decision.
    """
    evidence = _obj(evidence, "evidence")
    allowed = set(REQUIRED_WORKSHARE_EVIDENCE)
    if set(evidence) - allowed:
        raise WorkshareError("unknown keys in workshare evidence")
    retained = {key: _sha(value, key) for key, value in evidence.items()}
    migration_rows = _list(migrations, "migrations", MAX_CHILD_RECEIPTS)
    record_budget = 0
    # Bound total retained records before replaying or copying a large collection.
    for row in migration_rows:
        _obj(row, "migration")
        for key in ("source_records", "target_records"):
            record_budget += len(_list(row.get(key), key, MAX_RECORDS))
            if record_budget > MAX_COLLECTION_RECORDS:
                raise WorkshareError("migration collection record budget exceeded")
    ms = _children(migration_rows, "migrations", verify_migration_receipt)
    ss = _children(syncs, "syncs", verify_sync_receipt)
    event_identities = set()
    for row in ss:
        identity = (row["source_system"], row["target_system"], row["event_id"])
        if identity in event_identities:
            raise WorkshareError("syncs: conflicting current observations for one event")
        event_identities.add(identity)
    missing = sorted(allowed - set(retained))
    blocked_migrations = sorted(row["receipt_sha256"] for row in ms
                                if row["decision"] != "MIGRATION_RECONCILED")
    blocked_syncs = sorted(row["receipt_sha256"] for row in ss
                           if row["decision"] != "SYNC_ACCEPTED_EXACT")
    reasons = []
    if missing:
        reasons.append("MISSING_WORKSHARE_EVIDENCE")
    if not ms:
        reasons.append("NO_MIGRATION_RECEIPTS")
    if not ss:
        reasons.append("NO_SYNC_RECEIPTS")
    if blocked_migrations:
        reasons.append("MIGRATION_RECEIPTS_NOT_RECONCILED")
    if blocked_syncs:
        reasons.append("SYNC_RECEIPTS_NOT_ACCEPTED_EXACT")
    return _seal({
        "schema": READINESS_SCHEMA, "solicitation_id": SOLICITATION_ID, "buyer": BUYER,
        "question_deadline": QUESTION_DEADLINE, "proposal_deadline": PROPOSAL_DEADLINE,
        "public_packet_filename": PUBLIC_PACKET_FILENAME,
        "source_authority": "PUBLIC_PACKET_COPY_REQUIRES_ALABAMA_BUYS_RECHECK",
        "controlling_source_recheck_required": True,
        "requirement_evidence": {key: retained[key] for key in sorted(retained)},
        "missing_workshare_evidence": missing,
        "migration_receipts": ms, "sync_receipts": ss,
        "collection_policy": "ALL_SUPPLIED_CURRENT_RECEIPTS",
        "coverage_authority": "CALLER_SELECTED_COLLECTION_NOT_PROJECT_COMPLETENESS",
        "blocking_migration_receipts": blocked_migrations,
        "blocking_sync_receipts": blocked_syncs,
        "hold_reasons": sorted(reasons),
        "state": "HOLD_WORKSHARE_INCOMPLETE" if reasons else "WORKSHARE_READY_FOR_PRIME_REVIEW",
        "prime_gate_evidence_required": list(PRIME_GATE_EVIDENCE),
        "prime_qualified": False, "alabama_buys_registered": False,
        "external_outbound_authorized": False, "proposal_submission_authorized": False,
        "buyer_acceptance_claim_authorized": False, "award_claim_authorized": False,
        "payment_claim_authorized": False, "revenue_claim_authorized": False,
    })


def verify_readiness(receipt):
    r = _obj(receipt, "readiness")
    fields = {
        "schema", "solicitation_id", "buyer", "question_deadline", "proposal_deadline",
        "public_packet_filename", "source_authority", "controlling_source_recheck_required",
        "requirement_evidence", "missing_workshare_evidence", "migration_receipts",
        "sync_receipts", "state", "prime_gate_evidence_required", "prime_qualified",
        "alabama_buys_registered", "external_outbound_authorized", "proposal_submission_authorized",
        "buyer_acceptance_claim_authorized", "award_claim_authorized", "payment_claim_authorized",
        "revenue_claim_authorized", "collection_policy", "coverage_authority",
        "blocking_migration_receipts", "blocking_sync_receipts", "hold_reasons", "receipt_sha256",
    }
    _exact(r, fields, "readiness")
    for key in ("migration_receipts", "sync_receipts"):
        if type(r[key]) is not list:
            raise WorkshareError("child receipts must be lists")
    expected = compile_readiness(r["requirement_evidence"], r["migration_receipts"], r["sync_receipts"])
    if _canon(expected) != _canon(r):
        raise WorkshareError("readiness semantic or digest mismatch")
    return True
