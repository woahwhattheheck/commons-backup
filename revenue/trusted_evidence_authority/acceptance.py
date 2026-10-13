from __future__ import annotations

import json
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .authority import (
    AuthorityError,
    load_trusted_registry,
    make_packet,
    registry_from_value_for_tests,
    sha256_bytes,
    verify_current,
    verify_historical,
    verify_receipt,
)
from .strict_json import canonical_json, loads_strict

UTC = timezone.utc
BASE = datetime(2026, 9, 13, 11, 0, tzinfo=UTC)


def registry_value() -> dict:
    return {
        "schema": "trusted-evidence-authority-registry/v1",
        "registry_id": "demo-registry-v7",
        "issued_at": "2026-09-13T10:59:00Z",
        "sources": [
            {
                "source_id": "provider-status",
                "provider": "provider-a",
                "scope": "account/status",
                "resource": "acct-42/status",
                "generation": 7,
                "content_sha256": "1" * 64,
                "captured_at": "2026-09-13T10:58:00Z",
                "max_age_seconds": 600,
                "required": True,
            },
            {
                "source_id": "rules",
                "provider": "rules-owner",
                "scope": "policy/rules",
                "resource": "rules/v3",
                "generation": 3,
                "content_sha256": "2" * 64,
                "captured_at": "2026-09-13T10:57:00Z",
                "max_age_seconds": 3600,
                "required": True,
            },
        ],
    }


def packet_value(registry: dict) -> dict:
    sources = [
        {k: row[k] for k in ("source_id", "provider", "scope", "resource", "generation", "content_sha256", "captured_at")}
        for row in registry["sources"]
    ]
    return make_packet(
        registry_id=registry["registry_id"],
        subject_id="op-123",
        decision_id="preflight-001",
        payload={"action": "owner_review", "amount_cents": 250000},
        sources=sources,
    )


def run() -> dict:
    registry_raw = registry_value()
    registry = registry_from_value_for_tests(registry_raw)
    packet = packet_value(registry_raw)
    checks: list[tuple[str, bool]] = []

    good = verify_current(packet, registry, now=BASE)
    checks.append(("valid_current", good["current_source_authority"] and verify_receipt(good)))

    forged = deepcopy(packet)
    forged["sources"][0]["content_sha256"] = "f" * 64
    checks.append(("forged_provider_json_holds", not verify_current(forged, registry, now=BASE)["current_source_authority"]))

    omitted = deepcopy(packet)
    omitted["sources"] = omitted["sources"][:-1]
    checks.append(("omitted_required_source_holds", not verify_current(omitted, registry, now=BASE)["current_source_authority"]))

    alias = deepcopy(packet)
    alias["sources"][0]["resource"] = "acct-42/status-alt"
    checks.append(("resource_alias_holds", not verify_current(alias, registry, now=BASE)["current_source_authority"]))

    superseded = deepcopy(packet)
    superseded["sources"][0]["generation"] = 6
    checks.append(("superseded_generation_holds", not verify_current(superseded, registry, now=BASE)["current_source_authority"]))

    stale_now = BASE + timedelta(hours=2)
    checks.append(("stale_current_holds", not verify_current(packet, registry, now=stale_now)["current_source_authority"]))

    forensic = verify_historical(packet, registry, as_of=BASE - timedelta(minutes=2))
    checks.append(("forensic_never_current", forensic["evidence_level"] == "HISTORICAL_INTEGRITY" and not forensic["current_source_authority"]))

    packet_rebound = deepcopy(packet)
    packet_rebound["subject_id"] = "other-op"
    checks.append(("subject_transplant_changes_packet_identity", verify_current(packet_rebound, registry, now=BASE)["packet_sha256"] != good["packet_sha256"]))

    try:
        loads_strict('{"a":1,"a":2}')
        dup_ok = False
    except Exception:
        dup_ok = True
    checks.append(("duplicate_json_rejected", dup_ok))

    try:
        loads_strict('{"__proto__":{}}')
        proto_ok = False
    except Exception:
        proto_ok = True
    checks.append(("reserved_proto_key_rejected", proto_ok))

    with tempfile.TemporaryDirectory() as td:
        legitimate = Path(td) / "registry.json"
        legitimate_bytes = (canonical_json(registry_raw) + "\n").encode()
        legitimate.write_bytes(legitimate_bytes)
        pin = sha256_bytes(legitimate_bytes)
        loaded = load_trusted_registry(legitimate, expected_file_sha256=pin)
        checks.append(("independent_registry_pin_accepts_exact_bytes", loaded.registry_id == registry.registry_id))
        fake_raw = deepcopy(registry_raw)
        fake_raw["sources"][0]["content_sha256"] = "f" * 64
        fake = Path(td) / "forged.json"
        fake.write_text(canonical_json(fake_raw) + "\n", encoding="utf-8")
        try:
            load_trusted_registry(fake, expected_file_sha256=pin)
            self_sign_ok = False
        except AuthorityError:
            self_sign_ok = True
        checks.append(("coordinated_self_signing_rejected_by_external_pin", self_sign_ok))

    changed_payload = deepcopy(packet)
    changed_payload["payload"]["amount_cents"] = 1
    try:
        verify_current(changed_payload, registry, now=BASE)
        payload_ok = False
    except AuthorityError:
        payload_ok = True
    checks.append(("changed_payload_without_rebind_rejected", payload_ok))

    failures = [name for name, ok in checks if not ok]
    return {
        "schema": "trusted-evidence-authority-acceptance/v1",
        "checks": len(checks),
        "passed": len(checks) - len(failures),
        "failed": failures,
        "receipt_sha256": good["receipt_sha256"],
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if not result["failed"] else 1)
