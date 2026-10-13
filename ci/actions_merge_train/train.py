"""Train-level composition, receipts, verification, and Markdown rendering."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Sequence

from .contract import *  # noqa:F401,F403
from .workflow import *  # noqa:F401,F403


def compile_capture(raw):
    capture = normalize_capture(raw)
    workflows = [workflow_result(w, capture["repository"], capture["head_sha"]) for w in capture["workflows"]]
    # A rerun changes its attempt, not its workflow identity. Check both latest
    # and replaced attempts so one run cannot satisfy multiple required groups.
    run_workflows = {}
    for workflow in workflows:
        for row in workflow["latest_attempts"] + workflow["replaced_attempts"]:
            run_id = row["run_id"]
            previous_workflow = run_workflows.get(run_id)
            if previous_workflow is not None and previous_workflow != workflow["name"]:
                raise EvidenceError(
                    f"run_id appears in multiple workflows: {previous_workflow!r}, {workflow['name']!r}"
                )
            run_workflows[run_id] = workflow["name"]

    reasons = []
    if capture["topology"]["state"] != "CURRENT":
        reasons.append("TOPOLOGY_NOT_CURRENT")
    review_state = capture["source_review"]["state"]
    if review_state == "RED":
        reasons.append("SOURCE_REVIEW_RED")
    elif review_state != "GREEN":
        reasons.append("SOURCE_REVIEW_NOT_GREEN")

    dispositions = {workflow["disposition"] for workflow in workflows}
    if "EVIDENCE_INCOMPLETE" in dispositions:
        reasons.append("EXECUTION_EVIDENCE_INCOMPLETE")
    if "HOLD_AMBIGUOUS" in dispositions:
        reasons.append("EXECUTION_AMBIGUOUS")
    if "SOURCE_EXECUTED_RED" in dispositions:
        reasons.append("SOURCE_EXECUTED_RED")
    if "EVIDENCE_ABSENT" in dispositions:
        reasons.append("EXECUTION_EVIDENCE_ABSENT")
    if "PROVIDER_QUEUED" in dispositions:
        reasons.append("PROVIDER_QUEUED")
    if dispositions & {"PROVIDER_NO_RUN", "PROVIDER_CANCELLED_BEFORE_EXECUTION"}:
        reasons.append("PROVIDER_STARVATION")

    ordered = [reason for reason in HOLD_PRIORITY if reason in set(reasons)]
    overall = "READY_FOR_GUARDED_REVIEW" if not ordered else OVERALL_BY_REASON[ordered[0]]
    if overall == "READY_FOR_GUARDED_REVIEW" and any(
        workflow["disposition"] != "SOURCE_EXECUTED_GREEN" for workflow in workflows
    ):
        raise EvidenceError("internal invariant: guarded-review readiness requires all workflows source-executed green")

    provider_hold = bool(dispositions & {"PROVIDER_NO_RUN", "PROVIDER_QUEUED", "PROVIDER_CANCELLED_BEFORE_EXECUTION"})
    return {
        "repository": capture["repository"],
        "pr_number": capture["pr_number"],
        "head_sha": capture["head_sha"],
        "overall_disposition": overall,
        "hold_reasons": ordered,
        "source_review": capture["source_review"],
        "topology": capture["topology"],
        "workflows": workflows,
        "work_feed_projection": {
            "repository": capture["repository"],
            "pr_number": capture["pr_number"],
            "head_sha": capture["head_sha"],
            "state": overall,
            "first_hold_reason": ordered[0] if ordered else None,
            "provider_hold": provider_hold,
            "merge_authorized": False,
        },
        "source_regression_proven": False,
        "merge_authorized": False,
        "workflow_mutation_authorized": False,
    }


def compile_train(raws: Sequence[Any]):
    if not raws or len(raws) > MAX_CAPTURES:
        raise EvidenceError(f"expected 1..{MAX_CAPTURES} captures")
    prs = [compile_capture(raw) for raw in raws]
    keys = [(row["repository"], row["pr_number"]) for row in prs]
    if len(keys) != len(set(keys)):
        raise EvidenceError("duplicate repository/pr_number capture")
    prs.sort(key=lambda row: (row["repository"], row["pr_number"], row["head_sha"]))
    counts = Counter(row["overall_disposition"] for row in prs)
    ready = counts.get("READY_FOR_GUARDED_REVIEW", 0)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "prs": prs,
        "aggregate": {
            "pr_count": len(prs),
            "ready_for_guarded_review_count": ready,
            "hold_count": len(prs) - ready,
            "provider_hold_pr_count": sum(row["work_feed_projection"]["provider_hold"] for row in prs),
            "overall_disposition_counts": dict(sorted(counts.items())),
            "merge_authorized": False,
            "workflow_mutation_authorized": False,
        },
    }
    receipt["receipt_sha256"] = digest(receipt)
    return receipt


def verify_receipt(supplied, raws):
    recomputed = compile_train(raws)
    reasons = []
    supplied_sha = None
    if type(supplied) is not dict:
        reasons.append("SUPPLIED_RECEIPT_NOT_OBJECT")
    else:
        value = supplied.get("receipt_sha256")
        supplied_sha = value if type(value) is str else None
        if supplied.get("schema") != RECEIPT_SCHEMA:
            reasons.append("SUPPLIED_RECEIPT_SCHEMA_MISMATCH")
        if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
            reasons.append("SUPPLIED_RECEIPT_DIGEST_INVALID")
        else:
            projection = dict(supplied)
            projection.pop("receipt_sha256", None)
            if digest(projection) != value:
                reasons.append("SUPPLIED_RECEIPT_DIGEST_MISMATCH")
        if supplied != recomputed:
            reasons.append("RECEIPT_RECOMPUTE_MISMATCH")
    return {
        "schema": VERIFY_SCHEMA,
        "valid": not reasons,
        "reason_codes": sorted(set(reasons)),
        "supplied_receipt_sha256": supplied_sha,
        "recomputed_receipt_sha256": recomputed["receipt_sha256"],
    }


def render_markdown(receipt):
    if type(receipt) is not dict or receipt.get("schema") != RECEIPT_SCHEMA:
        raise EvidenceError("markdown: expected compiled merge-train receipt")
    lines = [
        "# Actions merge-train advisory report",
        "",
        f"Receipt: `{receipt.get('receipt_sha256', 'UNKNOWN')}`",
        "",
        "This report is advisory only. `READY_FOR_GUARDED_REVIEW` is not merge authorization.",
        "",
        "| Repository | PR | Head | Disposition | First hold | Provider hold |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for row in receipt["prs"]:
        projection = row["work_feed_projection"]
        lines.append(
            f"| {row['repository']} | #{row['pr_number']} | `{row['head_sha'][:12]}` | "
            f"{row['overall_disposition']} | {projection['first_hold_reason'] or '-'} | "
            f"{'yes' if projection['provider_hold'] else 'no'} |"
        )
    lines += ["", "## Workflow evidence", ""]
    for row in receipt["prs"]:
        lines += [f"### {row['repository']} PR #{row['pr_number']} @ `{row['head_sha']}`", ""]
        for workflow in row["workflows"]:
            observation = workflow["observation"]
            completeness = "complete" if observation["pagination_exhausted"] else "incomplete"
            lines.append(
                f"- `{workflow['name']}`: **{workflow['disposition']}**; "
                f"rerun advice `{workflow['rerun_advice']}`; attempts {workflow['all_attempt_count']}; "
                f"enumeration {completeness} across {observation['pages_fetched']} page(s)"
            )
        lines.append(
            f"- Hold reasons: {', '.join(row['hold_reasons'])}"
            if row["hold_reasons"]
            else "- Hold reasons: none; guarded human/current-head review is still required."
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
