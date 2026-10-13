"""Public EDSS migration/interoperability acceptance API."""
from datetime import datetime, timezone
from typing import Any
from ._core import (
    ACCEPTANCE_READY, EVIDENCE_INCOMPLETE, EVIDENCE_STALE, MIGRATION_MISMATCH,
    INTERFACE_MISMATCH, HOLD, STATES, DEFAULT_POLICY, RECEIPT_SCHEMA,
    EdssAcceptanceError, canonical_json_bytes, sha256_hex, load_json_strict,
    _parse_utc, _utc_text, _validate_policy,
)
from ._schema import rows_digest, expected_events_digest, expected_record_ids_digest, _validate_packet
from ._reconcile import _evaluate

def compile_acceptance(packet: Any, *, as_of: datetime, policy: Any = DEFAULT_POLICY) -> dict[str, Any]:
    """Compile a deterministic historical acceptance receipt at trusted ``as_of``."""
    p = _validate_policy(policy)
    if as_of.tzinfo is None:
        raise EdssAcceptanceError("trusted as_of must be timezone-aware")
    trusted_as_of = as_of.astimezone(timezone.utc).replace(microsecond=0)
    normalized = _validate_packet(packet, p)
    state, reasons, records, record_counts, interfaces, interface_counts = _evaluate(normalized, as_of=trusted_as_of, policy=p)
    packet_sha = sha256_hex(canonical_json_bytes(normalized))
    policy_sha = sha256_hex(canonical_json_bytes(p))
    core = {
        "schema": RECEIPT_SCHEMA,
        "state": state,
        "as_of": _utc_text(trusted_as_of),
        "engagement_ref": normalized["engagement_ref"],
        "packet_sha256": packet_sha,
        "policy_sha256": policy_sha,
        "source_snapshot_id": normalized["source_snapshot"]["snapshot_id"],
        "target_snapshot_id": normalized["target_snapshot"]["snapshot_id"],
        "expectation_observation_id": normalized["expectation"]["observation_id"],
        "cutover": normalized["cutover"],
        "reasons": reasons,
        "record_counts": record_counts,
        "records": records,
        "interface_counts": interface_counts,
        "interfaces": interfaces,
        "authority": {
            "evidence_only": True,
            "production_access": False,
            "clinical_or_public_health_decision": False,
            "protocol_certification": False,
            "security_privacy_compliance_attestation": False,
            "provider_or_state_contact": False,
            "proposal_or_submission": False,
            "commercial_commitment": False,
            "acceptance_award_payment_revenue": False,
        },
    }
    return {**core, "receipt_sha256": sha256_hex(canonical_json_bytes(core))}


def render_markdown(receipt: dict[str, Any]) -> str:
    if type(receipt) is not dict or receipt.get("schema") != RECEIPT_SCHEMA:
        raise EdssAcceptanceError("invalid receipt")
    lines = [
        "# EDSS migration/interoperability acceptance evidence",
        "",
        f"**State:** `{receipt['state']}`",
        f"**Engagement:** `{receipt['engagement_ref']}`",
        f"**Compiled at:** `{receipt['as_of']}`",
        f"**Source snapshot:** `{receipt['source_snapshot_id']}`",
        f"**Target snapshot:** `{receipt['target_snapshot_id']}`",
        f"**Expectation observation:** `{receipt['expectation_observation_id']}`",
        f"**Cutover:** `{receipt['cutover']['start']}` → `{receipt['cutover']['end']}` (half-open)",
        "",
        "## Disposition",
        "",
    ]
    lines.extend(f"- {reason}" for reason in receipt["reasons"])
    lines += ["", "## Migration reconciliation", ""]
    if receipt["record_counts"]:
        lines.extend(f"- `{status}`: {count}" for status, count in sorted(receipt["record_counts"].items()))
    else:
        lines.append("- No record classifications emitted because evidence binding failed before reconciliation.")
    mismatch_records = [row for row in receipt["records"] if row["status"] != "PARITY_OK"]
    if mismatch_records:
        lines += ["", "### Record findings", ""]
        for row in mismatch_records:
            suffix = f"; fields={','.join(row['differing_field_ids'])}" if row["differing_field_ids"] else ""
            lines.append(f"- `{row['record_id']}` — `{row['status']}`{suffix}")
    lines += ["", "## Interface acceptance", ""]
    if receipt["interface_counts"]:
        lines.extend(f"- `{status}`: {count}" for status, count in sorted(receipt["interface_counts"].items()))
    else:
        lines.append("- No interface classifications emitted because evidence binding failed before reconciliation.")
    interface_findings = [row for row in receipt["interfaces"] if row["status"] != "INTERFACE_OK"]
    if interface_findings:
        lines += ["", "### Interface findings", ""]
        for row in interface_findings:
            lines.append(f"- `{row['interface_id']}` / `{row['message_id']}` seq {row['source_sequence']} — `{row['status']}`")
    lines += [
        "",
        "## Authority ceiling",
        "",
        "This receipt is synthetic/approved evidence only. It does not establish clinical or epidemiological correctness, HL7/FHIR certification, security/privacy/legal compliance, production deployment, State or vendor acceptance, award, payment, or revenue. Offline verification proves this historical receipt against the supplied packet and policy; it is not a fresh provider or cutover check.",
        "",
        f"Packet SHA-256: `{receipt['packet_sha256']}`",
        f"Receipt SHA-256: `{receipt['receipt_sha256']}`",
    ]
    return "\n".join(lines) + "\n"


def verify_receipt(packet: Any, receipt: Any, *, policy: Any = DEFAULT_POLICY) -> bool:
    if type(receipt) is not dict or receipt.get("schema") != RECEIPT_SCHEMA:
        raise EdssAcceptanceError("invalid receipt schema")
    expected_keys = {
        "schema", "state", "as_of", "engagement_ref", "packet_sha256", "policy_sha256",
        "source_snapshot_id", "target_snapshot_id", "expectation_observation_id", "cutover",
        "reasons", "record_counts", "records", "interface_counts", "interfaces", "authority",
        "receipt_sha256",
    }
    if set(receipt) != expected_keys or receipt["state"] not in STATES:
        raise EdssAcceptanceError("invalid receipt structure/state")
    as_of = _parse_utc(receipt["as_of"], where="receipt.as_of")
    rebuilt = compile_acceptance(packet, as_of=as_of, policy=policy)
    if canonical_json_bytes(rebuilt) != canonical_json_bytes(receipt):
        raise EdssAcceptanceError("receipt does not verify")
    return True
