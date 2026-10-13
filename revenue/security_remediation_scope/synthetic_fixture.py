#!/usr/bin/env python3
"""Emit deterministic synthetic source findings and matching remediation scope."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def build_source_packet() -> dict:
    return {
        "schema": "security-remediation-findings-v1",
        "packet_id": "SYNTHETIC-QUESTIONNAIRE-001",
        "observed_at": "2026-09-15T12:00:00Z",
        "findings": [
            {
                "id": "F.ACCESS",
                "source_status": "PARTIAL",
                "requirement": "Administrative access should have retained MFA evidence.",
                "source_evidence_ids": ["E.ACCESS"],
                "current_state": "Role-based administrative access evidence is retained; MFA evidence is not retained for the reviewed scope.",
                "gap": "Retained MFA configuration and validation evidence is missing.",
            },
            {
                "id": "F.BACKUP",
                "source_status": "HOLD_STALE_EVIDENCE",
                "requirement": "A current restore exercise should be evidenced for the bounded service.",
                "source_evidence_ids": ["E.BACKUP"],
                "current_state": "A prior restore exercise exists but is outside the declared evidence-currentness window.",
                "gap": "No current retained restore exercise evidence is available.",
            },
            {
                "id": "F.LOGGING",
                "source_status": "SUPPORTED",
                "requirement": "Privileged administrative actions should produce retained audit events.",
                "source_evidence_ids": ["E.LOGGING"],
                "current_state": "Current retained evidence supports structured privileged-action audit events for the reviewed scope.",
                "gap": "No remediation gap is asserted.",
            },
        ],
    }


def source_packet_bytes() -> bytes:
    return canonical(build_source_packet())


def build_scope_manifest(source_raw: bytes | None = None) -> dict:
    source_raw = source_packet_bytes() if source_raw is None else source_raw
    return {
        "schema": "security-remediation-scope-v2",
        "scope_id": "SYNTHETIC-REMEDIATION-001",
        "as_of": "2026-09-16T12:00:00Z",
        "currency": "USD",
        "source_packet": {
            "packet_id": "SYNTHETIC-QUESTIONNAIRE-001",
            "sha256": hashlib.sha256(source_raw).hexdigest(),
            "observed_at": "2026-09-15T12:00:00Z",
        },
        "remediations": [
            {
                "finding_id": "F.ACCESS",
                "deliverable": "Implement owner-approved MFA configuration for the bounded administrative surface and retain configuration plus validation evidence.",
                "acceptance_test": "Owner-reviewed synthetic and staging checks show the bounded administrative paths require a second factor and retained evidence bytes reproduce the result.",
                "dependencies": ["Owner supplies approved identity-provider configuration", "Staging administrative surface is available"],
                "change_control_trigger": "Any additional identity provider, production rollout, or new administrative surface is separately scoped.",
                "owner_proposed_price_cents": 750000,
            },
            {
                "finding_id": "F.BACKUP",
                "deliverable": "Run one owner-approved non-production restore exercise for the bounded service and retain the procedure, timestamps, result, and artifact digests.",
                "acceptance_test": "The owner can reproduce the retained non-production restore procedure and verify the resulting artifact digests against the delivery packet.",
                "dependencies": ["Owner provides approved non-production backup set", "Owner defines recovery target for the exercise"],
                "change_control_trigger": "Production disaster-recovery execution, new backup products, or broader recovery objectives require a separate change order.",
                "owner_proposed_price_cents": 1000000,
            },
        ],
    }


def scope_bytes(source_raw: bytes | None = None) -> bytes:
    return canonical(build_scope_manifest(source_raw))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "scope"
    if mode == "source":
        sys.stdout.buffer.write(source_packet_bytes())
    elif mode == "scope":
        sys.stdout.buffer.write(scope_bytes())
    else:
        raise SystemExit("usage: synthetic_fixture.py [source|scope]")
