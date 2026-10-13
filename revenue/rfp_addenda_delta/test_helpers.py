from __future__ import annotations

import hashlib

try:
    from .schema import DECISION_SCHEMA, GEN_SCHEMA, normalize_generation, requirement_identity
except ImportError:
    from schema import DECISION_SCHEMA, GEN_SCHEMA, normalize_generation, requirement_identity


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def doc(doc_id="rfp", *, role="BASE_RFP", digest=None, supersedes=None, authority="OFFICIAL"):
    return {
        "document_id": doc_id, "authority": authority, "role": role,
        "url": f"https://buyer.example/{doc_id}.pdf", "sha256": digest or h(doc_id),
        "supersedes_sha256": supersedes,
    }


def req(req_id="R-001", *, doc_id="rfp", statement=None, supersedes=None, cls="MANDATORY",
        route="BOTH", curable=False, deadline=None, category="general", review_class="TECHNICAL",
        response="response"):
    return {
        "requirement_id": req_id, "document_id": doc_id, "coordinate": f"{doc_id} §1",
        "statement_sha256": statement or h(req_id), "class": cls, "category": category,
        "route": route, "curable": curable, "response_artifact": response,
        "deadline_utc": deadline, "review_class": review_class, "supersedes_sha256": supersedes,
    }


def generation(gen="g1", captured="2026-09-13T12:00:00Z", *, complete=True, documents=None, requirements=None):
    return {
        "schema": GEN_SCHEMA, "opportunity_id": "opp-1", "generation_id": gen,
        "captured_at": captured, "complete": complete,
        "documents": documents if documents is not None else [doc()],
        "requirements": requirements if requirements is not None else [req()],
    }


def decision_for(g, req_id="R-001"):
    norm = normalize_generation(g)
    row = next(r for r in norm["requirements"] if r["requirement_id"] == req_id)
    return {
        "schema": DECISION_SCHEMA, "decision_id": f"d-{req_id}",
        "opportunity_id": norm["opportunity_id"], "generation_id": norm["generation_id"],
        "requirement_id": req_id, "requirement_sha256": requirement_identity(row),
        "decision": "REVIEWED", "decided_at": "2026-09-13T12:30:00Z",
        "evidence_sha256": h("evidence-" + req_id),
    }
