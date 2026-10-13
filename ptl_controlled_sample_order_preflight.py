#!/usr/bin/env python3
"""Deterministic controlled-sample order preflight for Particle Technology Labs.

The gate accepts normalized/redacted order packets and returns only
READY_FOR_NAMED_HUMAN_ACCESSION or fail-closed HOLD decisions. It performs no
accession, payment, release, regulatory judgment, or external transmission.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

DEMAND_ID = "ptl-controlled-sample-order-preflight-01"
SCHEMA = "commons-ptl-controlled-sample-order-preflight/v1"
BUYER = "Particle Technology Labs / Antonette R. Seneviratne-Anglewicz"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
READY = "READY_FOR_NAMED_HUMAN_ACCESSION"
HOLD = "HOLD"

HOLD_CODES = (
    "MALFORMED_PACKET",
    "MISSING_LSO",
    "MISSING_PAYMENT_OR_PO",
    "MISSING_REQUIRED_SDS",
    "MISSING_REQUIRED_DEA_222",
    "INCOMPLETE_INTERNATIONAL_FIELDS",
)
ACCEPTANCE_HOLD_CODES = HOLD_CODES[1:]
INTERNATIONAL_FIELDS = (
    "consignee",
    "importer",
    "invoice_date",
    "po_or_invoice_number",
    "detailed_description",
)
SCHEDULES = ("NONE", "I", "II", "III", "IV", "V")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _hold(packet_id: str, code: str, input_hash: str) -> dict[str, Any]:
    if code not in HOLD_CODES:
        raise ValueError(f"unknown HOLD code: {code}")
    payload = {
        "packet_id": packet_id,
        "state": HOLD,
        "reason_code": code,
        "input_sha256": input_hash,
        "named_human_accession_required": True,
    }
    return {**payload, "decision_sha256": sha256_hex(payload)}


def classify_packet(packet: Any) -> dict[str, Any]:
    """Classify one normalized/redacted packet without side effects."""
    input_hash = sha256_hex(packet)
    if not isinstance(packet, dict):
        return _hold("UNSET", "MALFORMED_PACKET", input_hash)

    packet_id = _text(packet.get("packet_id")) or "UNSET"
    schedule = _text(packet.get("controlled_substance_schedule")).upper()
    required_text = (
        packet_id,
        _text(packet.get("requested_turnaround")),
        _text(packet.get("report_delivery_route")),
    )
    required_flags = (
        "lso_present",
        "sds_required",
        "sds_present",
        "dea_222_required",
        "dea_222_present",
        "international",
    )
    if (
        not all(required_text)
        or schedule not in SCHEDULES
        or any(type(packet.get(name)) is not bool for name in required_flags)
    ):
        return _hold(packet_id, "MALFORMED_PACKET", input_hash)

    if not packet["lso_present"] or not _text(packet.get("order_id")):
        return _hold(packet_id, "MISSING_LSO", input_hash)

    payment_status = _text(packet.get("payment_status")).upper()
    if not _text(packet.get("po_number")) and payment_status != "APPROVED":
        return _hold(packet_id, "MISSING_PAYMENT_OR_PO", input_hash)

    if packet["sds_required"] and not packet["sds_present"]:
        return _hold(packet_id, "MISSING_REQUIRED_SDS", input_hash)

    if packet["dea_222_required"] and not packet["dea_222_present"]:
        return _hold(packet_id, "MISSING_REQUIRED_DEA_222", input_hash)

    if packet["international"] and any(
        not _text(packet.get(field)) for field in INTERNATIONAL_FIELDS
    ):
        return _hold(packet_id, "INCOMPLETE_INTERNATIONAL_FIELDS", input_hash)

    payload = {
        "packet_id": packet_id,
        "state": READY,
        "reason_code": None,
        "input_sha256": input_hash,
        "order_id": _text(packet["order_id"]),
        "payment_basis": "PO" if _text(packet.get("po_number")) else "APPROVED_PAYMENT_STATUS",
        "sds_required": packet["sds_required"],
        "sds_present": packet["sds_present"],
        "controlled_substance_schedule": schedule,
        "dea_222_required": packet["dea_222_required"],
        "dea_222_present": packet["dea_222_present"],
        "international": packet["international"],
        "requested_turnaround": _text(packet["requested_turnaround"]),
        "report_delivery_route": _text(packet["report_delivery_route"]),
        "named_human_accession_required": True,
    }
    return {**payload, "decision_sha256": sha256_hex(payload)}


def _ready_packet(index: int, *, international: bool = False) -> dict[str, Any]:
    sds_required = index in {2, 4, 7}
    dea_required = index in {3, 7}
    packet = {
        "packet_id": f"SYN-PTL-{index:02d}",
        "lso_present": True,
        "order_id": f"SYN-LSO-{index:04d}",
        "po_number": f"SYN-PO-{index:04d}" if index % 2 else "",
        "payment_status": "APPROVED" if index % 2 == 0 else "PENDING",
        "sds_required": sds_required,
        "sds_present": True,
        "controlled_substance_schedule": "II" if dea_required else "NONE",
        "dea_222_required": dea_required,
        "dea_222_present": True,
        "international": international,
        "requested_turnaround": "STANDARD_10_BUSINESS_DAYS",
        "report_delivery_route": "SYNTHETIC_SECURE_PORTAL",
        "consignee": "SYN-CONSIGNEE" if international else "",
        "importer": "SYN-IMPORTER" if international else "",
        "invoice_date": "2026-09-01" if international else "",
        "po_or_invoice_number": f"SYN-INV-{index:04d}" if international else "",
        "detailed_description": "SYNTHETIC REDACTED CONTROLLED SAMPLE" if international else "",
        "synthetic": True,
        "redacted": True,
    }
    return packet


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """Return the locked 12-packet synthetic fixture: seven READY, five HOLD."""
    rows = [_ready_packet(i, international=(i in {5, 7})) for i in range(1, 8)]

    missing_lso = _ready_packet(8)
    missing_lso["lso_present"] = False

    missing_payment = _ready_packet(9)
    missing_payment["po_number"] = ""
    missing_payment["payment_status"] = "PENDING"

    missing_sds = _ready_packet(10)
    missing_sds["sds_required"] = True
    missing_sds["sds_present"] = False

    missing_dea = _ready_packet(11)
    missing_dea["controlled_substance_schedule"] = "II"
    missing_dea["dea_222_required"] = True
    missing_dea["dea_222_present"] = False

    incomplete_international = _ready_packet(12, international=True)
    incomplete_international["importer"] = ""

    rows.extend(
        [missing_lso, missing_payment, missing_sds, missing_dea, incomplete_international]
    )
    if len(rows) != 12:
        raise RuntimeError("acceptance fixture must contain exactly 12 packets")
    return rows


def run_preflight(packets: Iterable[Any] | None = None) -> dict[str, Any]:
    rows = deepcopy(list(build_acceptance_fixture() if packets is None else packets))
    decisions = [classify_packet(row) for row in rows]
    ready_count = sum(item["state"] == READY for item in decisions)
    hold_count = sum(item["state"] == HOLD for item in decisions)
    hold_code_counts = {
        code: sum(item["reason_code"] == code for item in decisions)
        for code in HOLD_CODES
        if any(item["reason_code"] == code for item in decisions)
    }
    audit = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_count": len(rows),
        "ready_count": ready_count,
        "hold_count": hold_count,
        "hold_code_counts": hold_code_counts,
        "fixture_sha256": sha256_hex(rows),
        "decisions_sha256": sha256_hex(decisions),
        "real_customer_records": 0,
        "accessions_created": 0,
        "releases_created": 0,
        "payment_actions": 0,
        "external_transmissions": 0,
        "autonomous_action": False,
    }
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "decisions": decisions,
        "audit": audit,
        "audit_sha256": sha256_hex(audit),
    }


def canonical_output(result: dict[str, Any]) -> bytes:
    return (_canonical(result) + "\n").encode("utf-8")


def pass_contract(result: dict[str, Any]) -> list[str]:
    audit = result.get("audit", {})
    errors: list[str] = []
    if audit.get("input_count") != 12:
        errors.append("INPUT_COUNT")
    if audit.get("ready_count") != 7:
        errors.append("READY_COUNT")
    if audit.get("hold_count") != 5:
        errors.append("HOLD_COUNT")
    expected = {code: 1 for code in ACCEPTANCE_HOLD_CODES}
    if audit.get("hold_code_counts") != expected:
        errors.append("HOLD_CODE_COUNTS")
    if any(audit.get(name) != 0 for name in (
        "real_customer_records",
        "accessions_created",
        "releases_created",
        "payment_actions",
        "external_transmissions",
    )):
        errors.append("SIDE_EFFECTS")
    if audit.get("autonomous_action") is not False:
        errors.append("AUTONOMOUS_ACTION")
    if result.get("audit_sha256") != sha256_hex(audit):
        errors.append("AUDIT_HASH")
    return errors


def load_packets(path: str | None) -> list[Any]:
    if not path:
        return build_acceptance_fixture()
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("packets")
    if not isinstance(payload, list):
        raise SystemExit("input must be a JSON list or an object containing a packets list")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="normalized/redacted packet JSON; defaults to locked fixture")
    args = parser.parse_args(argv)
    result = run_preflight(load_packets(args.input))
    print(canonical_output(result).decode("utf-8"), end="")
    return 0 if not (args.input is None and pass_contract(result)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
