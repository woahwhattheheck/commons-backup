"""Deterministic acceptance fixture for the commercial acceptance bridge."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from .gate import (
        canonical_json,
        receipt_self_digest_matches,
        reconcile,
        verify_receipt,
    )
except ImportError:
    from gate import canonical_json, receipt_self_digest_matches, reconcile, verify_receipt

SNAPSHOT = "2026-09-13T12:00:00Z"
ACTIVE_ISSUED = "2026-09-10T12:00:00Z"
ACTIVE_EXPIRES = "2026-09-20T12:00:00Z"
RESPONSE_AT = "2026-09-11T12:00:00Z"
EXPECTED_FIXTURE_RECEIPT_SHA256 = "dede4ae4fb681198b46e5d4433f182f05afe4583539d2f62487672bda27767fb"
EXPECTED_STATES = {
    "HUMAN_CLOSING_READY": 15,
    "COUNTEROFFER_REVIEW": 10,
    "CLARIFICATION_REQUIRED": 5,
    "OWNER_REPLY_REQUIRED": 5,
    "DECLINED": 5,
    "HUMAN_REVIEW_REQUIRED": 10,
    "AWAITING_RESPONSE": 5,
    "EXPIRED_NO_ACCEPTANCE": 5,
}
EXPECTED_QUARANTINES = {
    "SUPERSEDED_OFFER_VERSION": 5,
    "EXACT_ACCEPT_MISMATCH": 5,
}


def sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def offer_event(index: int, version: int = 1) -> dict[str, Any]:
    series = f"OFFER-SERIES-{index:03d}"
    version_id = f"OFFER-{index:03d}-V{version}"
    if version == 1:
        supersedes = "NONE"
        issued = "2026-09-08T12:00:00Z" if index <= 5 else ACTIVE_ISSUED
        expires = "2026-09-15T12:00:00Z" if index <= 5 else ACTIVE_EXPIRES
    else:
        supersedes = f"OFFER-{index:03d}-V{version - 1}"
        issued = ACTIVE_ISSUED
        expires = ACTIVE_EXPIRES
    if 56 <= index <= 60:
        issued = "2026-09-01T12:00:00Z"
        expires = "2026-09-12T12:00:00Z"
    return {
        "event_id": f"EV-OFFER-{index:03d}-V{version}",
        "kind": "offer",
        "offer_series_id": series,
        "offer_version_id": version_id,
        "version": version,
        "supersedes_version_id": supersedes,
        "counterparty_id": f"SYNTH-COUNTERPARTY-{index:03d}",
        "provider_thread_id": f"SYNTH-THREAD-{index:03d}",
        "scope_sha256": sha(f"scope-{index:03d}-v{version}"),
        "acceptance_criteria_sha256": sha(f"criteria-{index:03d}-v{version}"),
        "terms_sha256": sha(f"terms-{index:03d}-v{version}"),
        "currency": "USD",
        "price_minor": 100_000 + index * 1_000 + version,
        "issued_at": issued,
        "expires_at": expires,
    }


def response_event(index: int, review_class: str, *, version: int = 1, mismatch: bool = False, suffix: str = "MAIN") -> dict[str, Any]:
    offer = offer_event(index, version)
    return {
        "event_id": f"EV-RESPONSE-{index:03d}-{suffix}",
        "kind": "response",
        "response_id": f"RESPONSE-{index:03d}-{suffix}",
        "provider_message_id": f"SYNTH-MESSAGE-{index:03d}-{suffix}",
        "provider_thread_id": offer["provider_thread_id"],
        "counterparty_id": offer["counterparty_id"],
        "received_at": RESPONSE_AT,
        "reviewed_offer_version_id": offer["offer_version_id"],
        "review_class": review_class,
        "scope_sha256": sha(f"mismatch-{index:03d}") if mismatch else offer["scope_sha256"],
        "acceptance_criteria_sha256": offer["acceptance_criteria_sha256"],
        "terms_sha256": offer["terms_sha256"],
        "currency": offer["currency"],
        "price_minor": offer["price_minor"],
        "reviewer_attestation_sha256": sha(f"review-attestation-{index:03d}-{suffix}"),
    }


def generate_fixture() -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for index in range(1, 61):
        events.append(offer_event(index, 1))
        if index <= 5:
            events.append(offer_event(index, 2))

    for index in range(1, 16):
        version = 2 if index <= 5 else 1
        events.append(response_event(index, "EXACT_ACCEPT", version=version))
    for index in range(16, 26):
        response = response_event(index, "COUNTEROFFER")
        response["price_minor"] += 50_000
        events.append(response)
    for index in range(26, 31):
        response = response_event(index, "PARTIAL_ACCEPT")
        response["terms_sha256"] = sha(f"partial-terms-{index:03d}")
        events.append(response)
    for index in range(31, 36):
        events.append(response_event(index, "QUESTION"))
    for index in range(36, 41):
        events.append(response_event(index, "DECLINE"))
    for index in range(41, 46):
        events.append(response_event(index, "AMBIGUOUS"))
    for index in range(46, 51):
        events.append(response_event(index, "EXACT_ACCEPT", mismatch=True))

    for index in range(1, 6):
        events.append(response_event(index, "EXACT_ACCEPT", version=1, suffix="STALE"))

    if len(events) != 120:
        raise RuntimeError(f"fixture unique-event drift: {len(events)}")
    for position in (0, 17, 42, 73, 111):
        events.append(deepcopy(events[position]))
    if len(events) != 125:
        raise RuntimeError(f"fixture replay drift: {len(events)}")
    return {"schema_version": 1, "snapshot_at": SNAPSHOT, "events": events}


def check_acceptance(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    batch = deepcopy(payload) if payload is not None else generate_fixture()
    manifest = reconcile(batch, evaluated_at=batch["snapshot_at"])
    failures: list[str] = []
    if manifest["input_records"] != 125:
        failures.append(f"input_records {manifest['input_records']} != 125")
    if manifest["unique_events"] != 120:
        failures.append(f"unique_events {manifest['unique_events']} != 120")
    if manifest["replay_collapsed"] != 5:
        failures.append(f"replay_collapsed {manifest['replay_collapsed']} != 5")
    if manifest["counts"]["offer_series"] != 60:
        failures.append("offer_series != 60")
    if manifest["counts"]["offer_versions"] != 65:
        failures.append("offer_versions != 65")
    if manifest["counts"]["responses"] != 55:
        failures.append("responses != 55")
    if manifest["counts"]["states"] != EXPECTED_STATES:
        failures.append(f"state contract mismatch: {manifest['counts']['states']!r}")
    actual_quarantines: dict[str, int] = {}
    for row in manifest["quarantines"]:
        actual_quarantines[row["code"]] = actual_quarantines.get(row["code"], 0) + 1
    if actual_quarantines != EXPECTED_QUARANTINES:
        failures.append(f"quarantine contract mismatch: {actual_quarantines!r}")
    if manifest["counts"]["quarantined"] != 10:
        failures.append("quarantined != 10")
    if any(manifest["authorities"].values()):
        failures.append("one or more forbidden authority flags became true")
    if not receipt_self_digest_matches(manifest):
        failures.append("receipt failed self-digest integrity check")
    if manifest["receipt_sha256"] != EXPECTED_FIXTURE_RECEIPT_SHA256:
        failures.append(
            f"fixture receipt drift: {manifest['receipt_sha256']} != {EXPECTED_FIXTURE_RECEIPT_SHA256}"
        )
    if not verify_receipt(
        manifest,
        EXPECTED_FIXTURE_RECEIPT_SHA256,
        batch,
        evaluated_at=batch["snapshot_at"],
    ):
        failures.append("receipt failed trusted commitment/source/time verification")
    reversed_batch = {**batch, "events": list(reversed(batch["events"]))}
    if reconcile(reversed_batch, evaluated_at=batch["snapshot_at"])["receipt_sha256"] != manifest["receipt_sha256"]:
        failures.append("receipt changed under reversed input order")
    return {"status": "PASS" if not failures else "FAIL", "failures": failures, "manifest": manifest}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-receipt", type=Path)
    parser.add_argument("--write-source-batch", type=Path)
    parser.add_argument("--verify-receipt", type=Path)
    parser.add_argument("--source-batch", type=Path)
    parser.add_argument(
        "--expected-receipt-sha256",
        help="trusted out-of-band receipt SHA-256 required with --verify-receipt",
    )
    args = parser.parse_args(argv)
    if args.verify_receipt:
        if not args.expected_receipt_sha256:
            parser.error("--verify-receipt requires --expected-receipt-sha256 from a trusted out-of-band source")
        if not args.source_batch:
            parser.error("--verify-receipt requires --source-batch from a trusted source channel")
        payload = json.loads(args.verify_receipt.read_text(encoding="utf-8"))
        manifest = payload.get("manifest", payload)
        source_batch = json.loads(args.source_batch.read_text(encoding="utf-8"))
        valid = verify_receipt(manifest, args.expected_receipt_sha256, source_batch)
        print(json.dumps({"valid": valid}, sort_keys=True))
        return 0 if valid else 2
    if args.expected_receipt_sha256 or args.source_batch:
        parser.error("--expected-receipt-sha256 and --source-batch are only valid with --verify-receipt")

    fixture = generate_fixture()
    result = check_acceptance(fixture)
    if args.write_receipt:
        args.write_receipt.write_text(canonical_json(result) + "\n", encoding="utf-8")
    if args.write_source_batch:
        args.write_source_batch.write_text(canonical_json(fixture) + "\n", encoding="utf-8")
    manifest = result["manifest"]
    print(canonical_json({
        "status": result["status"],
        "failures": result["failures"],
        "input_records": manifest["input_records"],
        "unique_events": manifest["unique_events"],
        "replay_collapsed": manifest["replay_collapsed"],
        "states": manifest["counts"]["states"],
        "quarantined": manifest["counts"]["quarantined"],
        "receipt_sha256": manifest["receipt_sha256"],
    }))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
