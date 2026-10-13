from __future__ import annotations


H = "a" * 64
H2 = "b" * 64


def evidence(
    eid: str,
    category: str,
    *,
    subject_id=None,
    sha=H,
    issued="2026-09-01T00:00:00Z",
    captured="2026-09-01T01:00:00Z",
    expires="2027-09-01T00:00:00Z",
    verification="VERIFIED",
    source_class="ISSUER_CONTROLLED",
    verifier="ISSUER",
    reuse_scope="GLOBAL",
    opportunity_ids=None,
    stages=None,
    publicability="PRIVATE_REVIEW",
    supersedes=None,
    revoked_at=None,
    metadata=None,
    entity_id="token-junkie-labs",
):
    if opportunity_ids is None:
        opportunity_ids = []
    if stages is None:
        stages = ["SUBMISSION", "AWARD"]
    if metadata is None:
        metadata = {"financial_class": "AUDITED"} if category == "FINANCIAL_STATEMENT" else {}
    return {
        "id": eid,
        "category": category,
        "entity_id": entity_id,
        "subject_id": subject_id,
        "source_class": source_class,
        "issuer": "Synthetic Issuer",
        "descriptor": "synthetic-private-descriptor",
        "content_sha256": sha,
        "captured_at": captured,
        "issued_at": issued,
        "expires_at": expires,
        "verification_state": verification,
        "verifier_class": verifier,
        "reuse_scope": reuse_scope,
        "opportunity_ids": opportunity_ids,
        "stages": stages,
        "publicability": publicability,
        "supersedes": supersedes,
        "revoked_at": revoked_at,
        "metadata": metadata,
    }


def req(rid: str, category: str, *, stage="SUBMISSION", subject_id=None, opportunity="wrf-5417", financial=None):
    return {
        "id": rid,
        "category": category,
        "stage": stage,
        "subject_id": subject_id,
        "opportunity_id": opportunity,
        "required_financial_class": financial,
    }


def payload(evs=None, reqs=None):
    if evs is None:
        evs = [evidence("w9-2026", "W9")]
    if reqs is None:
        reqs = [req("r-w9", "W9")]
    return {
        "schema": "bidder-qualification-vault/entity-bound/v2",
        "generation_id": "gen-20260914",
        "entity_id": "token-junkie-labs",
        "as_of": "2026-09-14T03:50:00Z",
        "evidence": evs,
        "requirements": reqs,
    }
