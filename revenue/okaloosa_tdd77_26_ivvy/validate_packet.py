#!/usr/bin/env python3
"""Fail-closed verifier for the Okaloosa TDD 77-26 / iVvy workshare packet.

The verifier is intentionally offline. It binds the reviewed public-notice facts,
source authority ceilings, proposed commercial state, workshare boundary,
non-inferences, all-false external/commercial authority, and the packet's root
metadata contract. A hosted notice copy is evidence for notice facts only; it is
not promoted into the controlling RFP/addenda.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent
DEFAULT_LEDGER = ROOT / "source_ledger.json"
SCHEMA_VERSION = 2
EXPECTED_GENERATED_AT_UTC = "2026-09-17T08:31:00Z"
EXPECTED_LAST_SOURCE_AUDIT_UTC = "2026-09-17T08:40:00Z"
COVERED_FIELDS = (
    "opportunity",
    "commercial_hypothesis",
    "sources",
    "workshare_boundary",
    "non_inferences",
    "authority",
)
EXPECTED_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "generated_at_utc",
        "last_source_audit_utc",
        *COVERED_FIELDS,
        "semantic_receipt",
    }
)
EXPECTED_SEMANTIC_DIGEST = "c1ed1857aee0ade48a9d13863632a836ff7d962f74fe6b925bf8ce1bb6d02e3d"
EXPECTED_AUTHORITY_KEYS = frozenset(
    {
        "muse_selected",
        "external_send_authorized",
        "buyer_contact_authorized",
        "prime_contact_authorized",
        "bid_authorized",
        "portal_submission_authorized",
        "signature_authorized",
        "production_access_authorized",
        "production_mutation_authorized",
        "payment_mutation_authorized",
        "proposal_accepted",
        "contract_exists",
        "work_authorized",
        "invoice_exists",
        "receivable_exists",
        "payment_received",
        "booked_revenue",
        "recognized_revenue",
    }
)


class PacketError(ValueError):
    """The retained packet does not satisfy its reviewed truth contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PacketError(message)


def _no_duplicate_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise PacketError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_packet(path: Path = DEFAULT_LEDGER) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        value = json.loads(text, object_pairs_hook=_no_duplicate_object)
    except PacketError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PacketError(f"could not load ledger: {exc}") from exc
    _require(isinstance(value, dict), "ledger root must be an object")
    return value


def semantic_payload(packet: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in COVERED_FIELDS if field not in packet]
    _require(not missing, "semantic fields missing: " + ", ".join(missing))
    return {field: packet[field] for field in COVERED_FIELDS}


def semantic_digest(packet: dict[str, Any]) -> str:
    try:
        canonical = json.dumps(
            semantic_payload(packet),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise PacketError(f"semantic payload is not canonical JSON: {exc}") from exc
    return hashlib.sha256(canonical).hexdigest()


def _source_count(packet: dict[str, Any]) -> int:
    rows = packet.get("sources")
    _require(isinstance(rows, list), "sources must be a list")
    _require(len(rows) == 9, "source inventory changed")
    ids: set[str] = set()
    for index, row in enumerate(rows):
        _require(isinstance(row, dict), f"sources[{index}] must be an object")
        source_id = row.get("id")
        _require(isinstance(source_id, str) and source_id, f"sources[{index}].id is invalid")
        _require(source_id not in ids, f"duplicate source id: {source_id}")
        ids.add(source_id)
    return len(rows)


def validate_packet(packet: dict[str, Any]) -> dict[str, Any]:
    _require(isinstance(packet, dict), "ledger root must be an object")
    _require(set(packet) == EXPECTED_ROOT_KEYS, "root key set changed")
    _require(type(packet.get("schema_version")) is int, "schema_version must be an integer")
    _require(packet["schema_version"] == SCHEMA_VERSION, "unsupported schema_version")
    _require(
        packet.get("generated_at_utc") == EXPECTED_GENERATED_AT_UTC,
        "generated_at_utc changed",
    )
    _require(
        packet.get("last_source_audit_utc") == EXPECTED_LAST_SOURCE_AUDIT_UTC,
        "last_source_audit_utc changed",
    )

    opportunity = packet.get("opportunity")
    _require(isinstance(opportunity, dict), "opportunity must be an object")
    _require(
        opportunity.get("literal_response_deadline_from_notice")
        == "September 25, 2026 @ 3:00 PM (CST)",
        "notice deadline changed",
    )
    _require(
        opportunity.get("submission_method_from_notice") == "OpenGov only",
        "submission method changed",
    )
    _require(
        opportunity.get("buyer_controlled_full_rfp_and_addenda_retained") is False,
        "full-RFP custody changed",
    )
    _require(
        opportunity.get("qualification_state")
        == "CURRENT_NOTICE_FACTS_BOUND_FULL_SCOPE_REQUIRES_CONTROLLING_PACKET",
        "qualification state changed",
    )

    commercial = packet.get("commercial_hypothesis")
    _require(isinstance(commercial, dict), "commercial_hypothesis must be an object")
    _require(commercial.get("counterparty") == "iVvy", "counterparty changed")
    _require(commercial.get("currency") == "USD", "currency changed")
    _require(commercial.get("fixed_fee_minor_units") == 3500000, "commercial price changed")
    _require(
        commercial.get("delivery_target_business_days") == 15,
        "delivery target changed",
    )
    _require(commercial.get("state") == "PROPOSED_NOT_ACCEPTED", "commercial state changed")

    source_count = _source_count(packet)

    authority = packet.get("authority")
    _require(isinstance(authority, dict), "authority must be an object")
    _require(set(authority) == EXPECTED_AUTHORITY_KEYS, "authority key set changed")
    for key in EXPECTED_AUTHORITY_KEYS:
        _require(authority[key] is False, f"authority must remain false: {key}")

    receipt = packet.get("semantic_receipt")
    _require(
        receipt
        == {
            "algorithm": "sha256-canonical-json-v1",
            "covers": list(COVERED_FIELDS),
            "digest": EXPECTED_SEMANTIC_DIGEST,
        },
        "semantic receipt changed",
    )
    observed_digest = semantic_digest(packet)
    _require(observed_digest == EXPECTED_SEMANTIC_DIGEST, "semantic digest mismatch")

    return {
        "status": "OK",
        "schema_version": SCHEMA_VERSION,
        "semantic_digest": observed_digest,
        "source_count": source_count,
        "authority_false_count": len(EXPECTED_AUTHORITY_KEYS),
        "commercial_state": commercial["state"],
        "notice_deadline": opportunity["literal_response_deadline_from_notice"],
        "full_rfp_retained": opportunity["buyer_controlled_full_rfp_and_addenda_retained"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--verify", action="store_true", help="verify and emit one JSON receipt")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        packet = load_packet(args.ledger)
        result = validate_packet(packet)
    except PacketError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.verify:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
