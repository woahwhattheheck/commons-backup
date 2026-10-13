#!/usr/bin/env python3
"""Build the deterministic synthetic fixture manifest from retained evidence bytes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
DEFAULT_EVIDENCE_ROOT = HERE / "fixtures" / "evidence"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> dict:
    evidence_root = Path(evidence_root)
    evidence = [
        {
            "id": "E.ACCESS",
            "statement": "Administrative API paths require an authenticated admin role in the reviewed synthetic configuration.",
            "source_ref": "fixture://access-control",
            "artifact_path": "access-control.txt",
            "sha256": _sha(evidence_root / "access-control.txt"),
            "observed_at": "2026-09-01T12:00:00Z",
            "valid_until": "2026-12-31T23:59:59Z",
            "scope": "synthetic administrative API configuration",
        },
        {
            "id": "E.BACKUP",
            "statement": "A backup restore procedure was exercised successfully in the retained synthetic test fixture.",
            "source_ref": "fixture://backup",
            "artifact_path": "backup.txt",
            "sha256": _sha(evidence_root / "backup.txt"),
            "observed_at": "2026-07-01T12:00:00Z",
            "valid_until": "2026-09-01T00:00:00Z",
            "scope": "synthetic backup restore fixture",
        },
        {
            "id": "E.LOGGING",
            "statement": "Privileged administrative actions emit structured audit events in the reviewed synthetic configuration.",
            "source_ref": "fixture://audit-log",
            "artifact_path": "audit-log.txt",
            "sha256": _sha(evidence_root / "audit-log.txt"),
            "observed_at": "2026-09-02T12:00:00Z",
            "valid_until": "2026-12-31T23:59:59Z",
            "scope": "synthetic administrative audit-event configuration",
        },
    ]
    questions = [
        {
            "id": "Q.ACCESS",
            "prompt": "Are administrative interfaces access-controlled?",
            "required_evidence_ids": ["E.ACCESS"],
        },
        {
            "id": "Q.BACKUP",
            "prompt": "Is current backup-restore evidence available?",
            "required_evidence_ids": ["E.BACKUP"],
        },
        {
            "id": "Q.MFA",
            "prompt": "Is multifactor-authentication evidence available for the reviewed scope?",
            "required_evidence_ids": ["E.MFA"],
        },
        {
            "id": "Q.NA",
            "prompt": "Does the synthetic export-only fixture process payment-card data?",
            "required_evidence_ids": [],
            "not_applicable_reason": "Not applicable to the synthetic export-only fixture.",
        },
        {
            "id": "Q.PARTIAL",
            "prompt": "Are both access-control and backup-restore controls supported by current evidence?",
            "required_evidence_ids": ["E.ACCESS", "E.BACKUP"],
        },
    ]
    return {
        "schema": "security-questionnaire-evidence-v1",
        "as_of": "2026-09-16T12:00:00Z",
        "questionnaire_id": "SYNTHETIC-SECURITY-001",
        "evidence": evidence,
        "questions": questions,
    }


def fixture_bytes(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> bytes:
    return (json.dumps(build_manifest(evidence_root), sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


if __name__ == "__main__":
    sys.stdout.buffer.write(fixture_bytes())
