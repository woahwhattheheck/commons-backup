from __future__ import annotations

import hashlib
import json
from unittest.mock import patch

try:
    from .schema import GEN_SCHEMA, DECISION_SCHEMA, requirement_identity, normalize_generation
    from . import engine as engine_module
    from .engine import compile_current
except ImportError:
    from schema import GEN_SCHEMA, DECISION_SCHEMA, requirement_identity, normalize_generation
    import engine as engine_module
    from engine import compile_current


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def generation(gen: str, captured: str, *, addendum: bool, changed: bool):
    docs = [{
        "document_id": "rfp",
        "authority": "OFFICIAL",
        "role": "BASE_RFP",
        "url": "https://buyer.example/rfp.pdf",
        "sha256": h("rfp-v1"),
        "supersedes_sha256": None,
    }]
    if addendum:
        docs.append({
            "document_id": "add-1",
            "authority": "OFFICIAL",
            "role": "ADDENDUM",
            "url": "https://buyer.example/addendum-1.pdf",
            "sha256": h("add-1"),
            "supersedes_sha256": None,
        })
    req = {
        "requirement_id": "R-001",
        "document_id": "rfp",
        "coordinate": "RFP §3.2",
        "statement_sha256": h("three references" if not changed else "five references"),
        "class": "MANDATORY",
        "category": "references",
        "route": "BOTH",
        "curable": False,
        "response_artifact": "reference-matrix",
        "deadline_utc": None,
        "review_class": "COMMERCIAL",
        "supersedes_sha256": h("three references") if changed else None,
    }
    reqs = [req]
    if addendum:
        reqs.append({
            "requirement_id": "R-002",
            "document_id": "add-1",
            "coordinate": "Addendum 1 Q4",
            "statement_sha256": h("new security form"),
            "class": "MANDATORY",
            "category": "security",
            "route": "BOTH",
            "curable": True,
            "response_artifact": "security-form",
            "deadline_utc": None,
            "review_class": "SECURITY",
            "supersedes_sha256": None,
        })
    return {
        "schema": GEN_SCHEMA,
        "opportunity_id": "demo-rfp",
        "generation_id": gen,
        "captured_at": captured,
        "complete": True,
        "documents": docs,
        "requirements": reqs,
    }


def main():
    old = generation("g1", "2026-09-13T12:00:00Z", addendum=False, changed=False)
    old_norm = normalize_generation(old)
    decision = [{
        "schema": DECISION_SCHEMA,
        "decision_id": "d-r1",
        "opportunity_id": "demo-rfp",
        "generation_id": "g1",
        "requirement_id": "R-001",
        "requirement_sha256": requirement_identity(old_norm["requirements"][0]),
        "decision": "REVIEWED",
        "decided_at": "2026-09-13T12:05:00Z",
        "evidence_sha256": h("review"),
    }]

    same = generation("g2", "2026-09-13T13:00:00Z", addendum=False, changed=False)
    added = generation("g3", "2026-09-13T14:00:00Z", addendum=True, changed=False)
    changed = generation("g4", "2026-09-13T15:00:00Z", addendum=False, changed=True)

    with patch.object(engine_module, "_process_now", return_value="2026-09-13T16:00:00Z"):
        reports = {
            "same": compile_current(old, same, decision),
            "addendum": compile_current(old, added, decision),
            "changed": compile_current(old, changed, decision),
        }
    summary = {name: {"state": row["state"], "review_required": row["review_required"]} for name, row in reports.items()}
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
