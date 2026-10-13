from __future__ import annotations

from typing import Any

from .bindings_v2 import _same_subject, _subject
from .codec_v2 import ClaimError, enum, exact, git_sha, integer, repo, sha256, text, utc

ACCEPTANCE_CLASSES = frozenset({"TARGET_MERGE_EVENT", "SPONSOR_ACCEPTANCE", "BUYER_ACCEPTANCE", "PLATFORM_ACCEPTANCE"})
ELIGIBILITY = frozenset({"ELIGIBLE", "INELIGIBLE", "UNKNOWN", "NOT_REQUIRED"})
PAYMENT = frozenset({"PAID", "UNPAID", "UNKNOWN"})
PAYMENT_PROVENANCE = frozenset({"PROVIDER_OBSERVED", "COUNTERPARTY_STATED", "OWNER_LEDGER_RETAINED", "UNKNOWN"})
FOLLOWUP_KINDS = frozenset({"PAYMENT_REQUEST_SENT", "PAYMENT_STATUS_RECEIVED", "SPONSOR_REPLIED", "PAYMENT_REJECTED"})


def _acceptance(raw: Any, root_subject: dict[str, str], work: dict[str, Any]) -> dict[str, Any] | None:
    if raw is None:
        return None
    row = exact(raw, {"acceptance_id", "subject", "source_class", "source_ref", "source_sha256", "accepted_at", "repository", "pr_number", "merged_commit_sha"}, "acceptance")
    subject = _subject(row["subject"], "acceptance.subject"); _same_subject(subject, root_subject, "acceptance.subject")
    accepted_at, _ = utc(row["accepted_at"], "acceptance.accepted_at")
    normalized = {
        "acceptance_id": text(row["acceptance_id"], "acceptance.acceptance_id", 120),
        "subject": subject,
        "source_class": enum(row["source_class"], ACCEPTANCE_CLASSES, "acceptance.source_class"),
        "source_ref": text(row["source_ref"], "acceptance.source_ref"),
        "source_sha256": sha256(row["source_sha256"], "acceptance.source_sha256"),
        "accepted_at": accepted_at,
        "repository": repo(row["repository"], "acceptance.repository"),
        "pr_number": integer(row["pr_number"], "acceptance.pr_number", 1, 2_147_483_647),
        "merged_commit_sha": git_sha(row["merged_commit_sha"], "acceptance.merged_commit_sha"),
    }
    for field in ("repository", "pr_number", "merged_commit_sha"):
        if normalized[field] != work[field]:
            raise ClaimError(f"acceptance.{field}: cross-work transplant")
    return normalized


def _eligibility(raw: Any, root_subject: dict[str, str]) -> dict[str, Any] | None:
    if raw is None:
        return None
    row = exact(raw, {"subject", "status", "source_ref", "source_sha256", "observed_at"}, "eligibility")
    subject = _subject(row["subject"], "eligibility.subject"); _same_subject(subject, root_subject, "eligibility.subject")
    observed_at, _ = utc(row["observed_at"], "eligibility.observed_at")
    return {"subject": subject, "status": enum(row["status"], ELIGIBILITY, "eligibility.status"), "source_ref": text(row["source_ref"], "eligibility.source_ref"), "source_sha256": sha256(row["source_sha256"], "eligibility.source_sha256"), "observed_at": observed_at}


def _followups(raw: Any, root_subject: dict[str, str], work: dict[str, Any]) -> list[dict[str, Any]]:
    if type(raw) is not list or len(raw) > 200:
        raise ClaimError("followups: bounded array required")
    rows: list[dict[str, Any]] = []
    ids: set[str] = set(); economics: set[tuple[Any, ...]] = set()
    for i, item in enumerate(raw):
        where = f"followups[{i}]"
        row = exact(item, {"id", "subject", "repository", "pr_number", "kind", "route", "provider_ref", "thread_ref", "message_ref", "source_ref", "source_sha256", "observed_at"}, where)
        subject = _subject(row["subject"], f"{where}.subject"); _same_subject(subject, root_subject, f"{where}.subject")
        if repo(row["repository"], f"{where}.repository") != work["repository"] or integer(row["pr_number"], f"{where}.pr_number", 1, 2_147_483_647) != work["pr_number"]:
            raise ClaimError(f"{where}: cross-work followup transplant")
        event_id = text(row["id"], f"{where}.id", 120)
        if event_id in ids:
            raise ClaimError("followups: duplicate id")
        ids.add(event_id)
        observed_at, _ = utc(row["observed_at"], f"{where}.observed_at")
        def opt(name: str, maximum: int = 512):
            return None if row[name] is None else text(row[name], f"{where}.{name}", maximum)
        normalized = {
            "id": event_id,
            "subject": subject,
            "repository": work["repository"],
            "pr_number": work["pr_number"],
            "kind": enum(row["kind"], FOLLOWUP_KINDS, f"{where}.kind"),
            "route": opt("route", 320),
            "provider_ref": opt("provider_ref"),
            "thread_ref": opt("thread_ref"),
            "message_ref": opt("message_ref"),
            "source_ref": text(row["source_ref"], f"{where}.source_ref"),
            "source_sha256": sha256(row["source_sha256"], f"{where}.source_sha256"),
            "observed_at": observed_at,
        }
        econ = tuple(normalized[k] if k != "subject" else tuple(sorted(normalized["subject"].items())) for k in ("kind", "subject", "repository", "pr_number", "route", "provider_ref", "thread_ref", "message_ref", "source_ref", "source_sha256", "observed_at"))
        if econ in economics:
            raise ClaimError("followups: duplicate semantic event under reminted id")
        economics.add(econ); rows.append(normalized)
    rows.sort(key=lambda r: (r["observed_at"], r["id"]))
    return rows


def _payment(raw: Any, root_subject: dict[str, str], work: dict[str, Any]) -> dict[str, Any]:
    row = exact(raw, {"subject", "repository", "pr_number", "status", "provenance_class", "source_ref", "source_sha256", "observed_at", "paid_amount_minor", "payment_ref"}, "payment_status")
    subject = _subject(row["subject"], "payment_status.subject"); _same_subject(subject, root_subject, "payment_status.subject")
    if repo(row["repository"], "payment_status.repository") != work["repository"] or integer(row["pr_number"], "payment_status.pr_number", 1, 2_147_483_647) != work["pr_number"]:
        raise ClaimError("payment_status: cross-work transplant")
    observed_at, _ = utc(row["observed_at"], "payment_status.observed_at")
    status = enum(row["status"], PAYMENT, "payment_status.status")
    provenance = enum(row["provenance_class"], PAYMENT_PROVENANCE, "payment_status.provenance_class")
    paid_amount = row["paid_amount_minor"]; payment_ref = row["payment_ref"]
    if status == "PAID":
        paid_amount = integer(paid_amount, "payment_status.paid_amount_minor", 1)
        payment_ref = text(payment_ref, "payment_status.payment_ref")
    elif paid_amount is not None or payment_ref is not None:
        raise ClaimError("payment_status: non-PAID rows must not carry paid amount/ref")
    return {"subject": subject, "repository": work["repository"], "pr_number": work["pr_number"], "status": status, "provenance_class": provenance, "source_ref": text(row["source_ref"], "payment_status.source_ref"), "source_sha256": sha256(row["source_sha256"], "payment_status.source_sha256"), "observed_at": observed_at, "paid_amount_minor": paid_amount, "payment_ref": payment_ref}
