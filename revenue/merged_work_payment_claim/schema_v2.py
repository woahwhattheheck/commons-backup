from __future__ import annotations

from typing import Any

from .codec_v2 import ClaimError, exact, git_sha, integer, repo, sha256, text, utc
from .compensation_v2 import _compensation
from .evidence_v2 import _acceptance, _eligibility, _followups, _payment

SCHEMA = "TJL_MERGED_WORK_PAYMENT_CLAIM_V2"


def normalize(document: Any) -> dict[str, Any]:
    doc = exact(document, {"schema", "claim_id", "claimant_id", "counterparty_id", "opportunity_id", "work", "compensation", "acceptance", "eligibility", "followups", "payment_status", "policy"}, "document")
    if doc["schema"] != SCHEMA:
        raise ClaimError("document.schema: unsupported")
    root_subject = {
        "claimant_id": text(doc["claimant_id"], "claimant_id", 160),
        "counterparty_id": text(doc["counterparty_id"], "counterparty_id", 160),
        "opportunity_id": text(doc["opportunity_id"], "opportunity_id", 160),
        "work_id": text(doc["work"].get("work_id") if type(doc["work"]) is dict else None, "work.work_id", 160),
    }
    work = _work(doc["work"], root_subject)
    comps = _compensation(doc["compensation"], root_subject, work)
    acceptance = _acceptance(doc["acceptance"], root_subject, work)
    eligibility = _eligibility(doc["eligibility"], root_subject)
    followups = _followups(doc["followups"], root_subject, work)
    payment = _payment(doc["payment_status"], root_subject, work)
    policy = _policy(doc["policy"])
    return {
        "schema": SCHEMA,
        "claim_id": text(doc["claim_id"], "claim_id", 160),
        **{k: root_subject[k] for k in ("claimant_id", "counterparty_id", "opportunity_id")},
        "work": work,
        "compensation": comps,
        "acceptance": acceptance,
        "eligibility": eligibility,
        "followups": followups,
        "payment_status": payment,
        "policy": policy,
    }


def _work(raw: Any, root_subject: dict[str, str]) -> dict[str, Any]:
    row = exact(raw, {"work_id", "repository", "pr_number", "merged_commit_sha", "deliverable_sha256", "merged_at", "source_ref", "source_sha256"}, "work")
    if text(row["work_id"], "work.work_id", 160) != root_subject["work_id"]:
        raise ClaimError("work.work_id: subject mismatch")
    merged_at, _ = utc(row["merged_at"], "work.merged_at")
    return {
        "work_id": root_subject["work_id"],
        "repository": repo(row["repository"], "work.repository"),
        "pr_number": integer(row["pr_number"], "work.pr_number", 1, 2_147_483_647),
        "merged_commit_sha": git_sha(row["merged_commit_sha"], "work.merged_commit_sha"),
        "deliverable_sha256": sha256(row["deliverable_sha256"], "work.deliverable_sha256"),
        "merged_at": merged_at,
        "source_ref": text(row["source_ref"], "work.source_ref"),
        "source_sha256": sha256(row["source_sha256"], "work.source_sha256"),
    }


def _policy(raw: Any) -> dict[str, int]:
    row = exact(raw, {"max_status_age_hours", "cooldown_hours"}, "policy")
    return {"max_status_age_hours": integer(row["max_status_age_hours"], "policy.max_status_age_hours", 1, 720), "cooldown_hours": integer(row["cooldown_hours"], "policy.cooldown_hours", 0, 720)}
