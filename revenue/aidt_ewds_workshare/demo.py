"""Synthetic, PII-free demonstration for the AIDT specialist workshare."""

from __future__ import annotations

import hashlib
import json

from .core import (
    REQUIRED_WORKSHARE_EVIDENCE,
    compile_readiness,
    compile_sync_receipt,
    reconcile_migration,
    verify_readiness,
)


def _h(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    source = [
        {"record_id": "synthetic-applicant-001", "record_sha256": _h("applicant-v1")},
        {"record_id": "synthetic-class-001", "record_sha256": _h("class-v1")},
    ]
    migration = reconcile_migration(source, list(reversed(source)))

    event = {
        "source_system": "salesforce",
        "target_system": "adobe_lms",
        "event_id": "synthetic-event-001",
        "entity_ref": "synthetic-applicant-001",
        "operation": "enroll",
        "payload_sha256": _h("synthetic-enrollment-v1"),
    }
    observed = {
        "accepted": True,
        "target_ref": "synthetic-adobe-enrollment-001",
        "target_payload_sha256": _h("synthetic-enrollment-v1"),
    }
    sync = compile_sync_receipt(event, observed)

    evidence = {key: _h(f"synthetic-evidence:{key}") for key in REQUIRED_WORKSHARE_EVIDENCE}
    readiness = compile_readiness(evidence, [migration], [sync])
    verify_readiness(readiness)
    print(json.dumps(readiness, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
