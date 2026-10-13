#!/usr/bin/env python3
"""Offline review-practice assessment. Metadata signals, never code-quality scores."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any

SCHEMA = "uiowa-review-practice/v1"
KINDS = {"question", "change_request", "tradeoff", "test_evidence"}


class InputError(ValueError):
    """Malformed or internally inconsistent input; no report is emitted."""


def fail(path: str, message: str) -> None:
    raise InputError(f"{path}: {message}")


def mapping(value: Any, path: str, fields: set[str]) -> dict:
    if not isinstance(value, dict):
        fail(path, "expected an object")
    missing, extra = fields - value.keys(), value.keys() - fields
    if missing or extra:
        fail(path, f"missing fields {sorted(missing)}; unknown fields {sorted(extra)}")
    return value


def text(value: Any, path: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.strip():
        fail(path, "expected a nonempty string" + (" or null" if nullable else ""))
    return value


def timestamp(value: Any, path: str, nullable: bool = False) -> datetime | None:
    if value is None and nullable:
        return None
    text(value, path)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail(path, "expected an ISO-8601 timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        fail(path, "timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def choice(value: Any, allowed: set[str], path: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        fail(path, f"expected one of {sorted(allowed)}")
    return value


def boolean(value: Any, path: str) -> bool:
    if type(value) is not bool:
        fail(path, "expected true or false")
    return value


def records(value: Any, path: str) -> list:
    if not isinstance(value, list):
        fail(path, "expected an array")
    return value


def unique_json(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def loads(raw: str) -> dict:
    def reject(value: str) -> None:
        raise InputError(f"non-finite JSON value: {value}")
    try:
        return json.loads(raw, object_pairs_hook=unique_json, parse_constant=reject)
    except json.JSONDecodeError as error:
        raise InputError(f"invalid JSON at line {error.lineno}: {error.msg}") from error


def validate(packet: dict) -> None:
    mapping(packet, "packet", {"schema", "synthetic", "as_of", "sampling_note", "changes"})
    if packet["schema"] != SCHEMA:
        fail("packet.schema", f"expected {SCHEMA}")
    boolean(packet["synthetic"], "packet.synthetic")
    as_of = timestamp(packet["as_of"], "packet.as_of")
    text(packet["sampling_note"], "packet.sampling_note")
    ids = set()
    for ci, change in enumerate(records(packet["changes"], "packet.changes")):
        p = f"changes[{ci}]"
        mapping(change, p, {"id", "group", "service", "context", "author", "head", "created_at",
                           "review_requested_at", "merged_at", "export", "emergency", "reviews"})
        for field in ("id", "service", "author", "head"):
            text(change[field], f"{p}.{field}")
        if change["id"] in ids:
            fail(p + ".id", "duplicate change ID")
        ids.add(change["id"])
        choice(change["group"], {"ESS", "RIS", "IAM"}, p + ".group")
        context = mapping(change["context"], p + ".context", {"workflow", "review_expectation", "constraints"})
        for field, value in context.items():
            text(value, p + ".context." + field)
        created = timestamp(change["created_at"], p + ".created_at")
        requested = timestamp(change["review_requested_at"], p + ".review_requested_at", True)
        merged = timestamp(change["merged_at"], p + ".merged_at", True)
        for label, value in (("created_at", created), ("review_requested_at", requested), ("merged_at", merged)):
            if value is not None and (value < created or value > as_of):
                fail(p + "." + label, "must be between creation and as_of")
        if merged is not None and requested is not None and requested > merged:
            fail(p + ".review_requested_at", "must not follow merge")
        export = mapping(change["export"], p + ".export", {"complete", "reference", "captured_at"})
        boolean(export["complete"], p + ".export.complete")
        text(export["reference"], p + ".export.reference", True)
        captured = timestamp(export["captured_at"], p + ".export.captured_at", True)
        if captured is not None and (captured > as_of or captured < created):
            fail(p + ".export.captured_at", "must be between creation and as_of")
        if export["complete"] and (captured is None or export["reference"] is None):
            fail(p + ".export", "a completeness claim requires a reference and captured_at")
        emergency = mapping(change["emergency"], p + ".emergency", {"declared", "rationale", "followup_due_at"})
        boolean(emergency["declared"], p + ".emergency.declared")
        text(emergency["rationale"], p + ".emergency.rationale", True)
        due = timestamp(emergency["followup_due_at"], p + ".emergency.followup_due_at", True)
        if not emergency["declared"] and (due is not None or emergency["rationale"] is not None):
            fail(p + ".emergency", "non-emergency changes must use null rationale and due date")
        if due is not None and (merged is None or due < merged):
            fail(p + ".emergency.followup_due_at", "requires a merge and cannot precede it")
        seen_reviews = set()
        seen_feedback = set()
        for ri, review in enumerate(records(change["reviews"], p + ".reviews")):
            q = f"{p}.reviews[{ri}]"
            mapping(review, q, {"id", "reviewer", "head", "state", "submitted_at", "source_ref", "context_ref", "feedback"})
            for field in ("id", "reviewer", "head", "source_ref"):
                text(review[field], q + "." + field)
            text(review["context_ref"], q + ".context_ref", True)
            choice(review["state"], {"approved", "commented", "changes_requested", "dismissed"}, q + ".state")
            submitted = timestamp(review["submitted_at"], q + ".submitted_at", True)
            if submitted is not None and (submitted < created or submitted > as_of):
                fail(q + ".submitted_at", "must be between creation and as_of")
            if captured is not None and submitted is not None and submitted > captured:
                fail(q + ".submitted_at", "cannot follow export capture")
            if review["id"] in seen_reviews:
                fail(q + ".id", "duplicate review ID; deduplicate provider pagination before import")
            seen_reviews.add(review["id"])
            for fi, item in enumerate(records(review["feedback"], q + ".feedback")):
                f = f"{q}.feedback[{fi}]"
                mapping(item, f, {"id", "kind", "summary", "source_ref", "disposition", "resolution_ref", "resolved_at"})
                for field in ("id", "summary", "source_ref"):
                    text(item[field], f + "." + field)
                choice(item["kind"], KINDS, f + ".kind")
                choice(item["disposition"], {"resolved", "open", "unknown"}, f + ".disposition")
                text(item["resolution_ref"], f + ".resolution_ref", True)
                resolved = timestamp(item["resolved_at"], f + ".resolved_at", True)
                if resolved is not None and (submitted is None or resolved < submitted or resolved > as_of):
                    fail(f + ".resolved_at", "requires known submission and cannot precede it or follow as_of")
                if resolved is not None and captured is not None and resolved > captured:
                    fail(f + ".resolved_at", "cannot follow export capture")
                if item["disposition"] != "resolved" and (resolved is not None or item["resolution_ref"] is not None):
                    fail(f, "only resolved feedback can supply resolution evidence")
                if item["id"] in seen_feedback:
                    fail(f + ".id", "duplicate feedback ID in change; deduplicate repeated threads before import")
                seen_feedback.add(item["id"])


def minutes(start: datetime, end: datetime) -> float:
    return round((end - start).total_seconds() / 60.0, 6)


def resolved_by(item: dict, end: datetime) -> bool:
    resolved = timestamp(item["resolved_at"], "resolved_at", True)
    return (item["disposition"] == "resolved" and item["resolution_ref"] is not None
            and resolved is not None and resolved <= end)


def assess_change(change: dict, as_of: datetime) -> dict:
    merged = timestamp(change["merged_at"], "merged_at", True)
    cutoff = merged or as_of
    requested = timestamp(change["review_requested_at"], "review_requested_at", True)
    export = change["export"]
    captured = timestamp(export["captured_at"], "captured_at", True)
    complete = bool(export["complete"] and captured is not None and captured >= cutoff)
    reviews = [r for r in change["reviews"] if r["state"] != "dismissed"]
    peers = [r for r in reviews if r["reviewer"] != change["author"]]
    current = [r for r in peers if r["head"] == change["head"]]
    dated = [r for r in current if r["submitted_at"] is not None]
    before = [r for r in dated if timestamp(r["submitted_at"], "submitted_at") <= cutoff]
    substantive = [r for r in before if r["feedback"]]
    approved = [r for r in before if r["state"] == "approved"]
    stale = [r for r in peers if r["head"] != change["head"]]
    unknown_time = [r for r in current if r["submitted_at"] is None]
    if substantive:
        signal = "substantive_feedback_recorded"
    elif approved:
        signal = "approval_only_recorded"
    elif before:
        signal = "comment_without_structured_feedback"
    elif unknown_time:
        signal = "unknown_review_timing"
    elif stale:
        signal = "older_head_evidence_only"
    elif complete:
        signal = "no_final_head_peer_record_in_complete_export"
    else:
        signal = "unknown_incomplete_export"
    findings = []

    def finding(code: str, question: str, refs: list[str]) -> None:
        findings.append({"code": code, "question": question, "source_refs": sorted(set(refs)),
                         "suggested_owner_role": "team delivery lead", "effort": "discovery follow-up; estimate with team"})

    if signal != "substantive_feedback_recorded":
        finding(signal, "What records establish review of this exact change, and what does the local workflow expect?",
                [r["source_ref"] for r in before + stale + unknown_time])
    if unknown_time:
        finding("undated_review_records", "Which assessment window contains the undated review, and what exact revision did it cover?",
                [r["source_ref"] for r in unknown_time])
    if stale:
        finding("older_head_review_records", "Were earlier comments carried forward or superseded, and what establishes review of the intervening change?",
                [r["source_ref"] for r in stale])
    if not complete:
        finding("export_window_incomplete", "Obtain a bounded complete export through the assessment cutoff before inferring absence.",
                [export["reference"]] if export["reference"] else [])
    if any(r["context_ref"] is None for r in substantive):
        finding("reviewer_context_unknown", "How did reviewers obtain service, requirement and test context?",
                [r["source_ref"] for r in substantive if r["context_ref"] is None])
    unresolved = [f for r in substantive for f in r["feedback"] if not resolved_by(f, cutoff)]
    if unresolved:
        finding("feedback_not_resolved_by_cutoff", "Was each open point resolved, consciously deferred, or left unknown before delivery?",
                [f["source_ref"] for f in unresolved])
    request_order_conflict = bool(requested is not None and any(timestamp(r["submitted_at"], "submitted_at") < requested for r in substantive))
    wait = None
    censor = None
    if request_order_conflict:
        finding("request_after_recorded_feedback", "Was this a re-request, or is the first request timestamp missing? Do not report zero wait.",
                [r["source_ref"] for r in substantive])
    elif requested is None:
        finding("review_request_time_unknown", "Can the initial request time be established?", [])
    elif substantive and (not complete or unknown_time):
        finding("latency_coverage_unknown", "A first-feedback interval requires complete, dated records through the cutoff.", [])
    elif substantive:
        wait = minutes(requested, min(timestamp(r["submitted_at"], "submitted_at") for r in substantive))
    else:
        censor = minutes(requested, cutoff)

    emergency = change["emergency"]
    followup = "not_applicable"
    if emergency["declared"]:
        due = timestamp(emergency["followup_due_at"], "followup_due_at", True)
        # Emergency closure requires an actual post-merge, final-head peer record,
        # contextual evidence, and dated dispositions for every feedback item.
        candidates = [r for r in dated if merged is not None
                      and timestamp(r["submitted_at"], "submitted_at") > merged
                      and r["feedback"] and r["context_ref"] is not None]
        all_feedback = [f for r in current for f in r["feedback"]]
        complete_now = bool(export["complete"] and captured is not None and captured >= as_of)
        closure = (candidates and not unknown_time and complete_now
                   and all(r["context_ref"] is not None for r in current if r["feedback"])
                   and all(resolved_by(f, as_of) for f in all_feedback))
        if closure:
            # One later resolved thread cannot conceal another outstanding point.
            finished = max([timestamp(r["submitted_at"], "submitted_at") for r in candidates]
                           + [timestamp(f["resolved_at"], "resolved_at") for f in all_feedback])
            followup = "completed_due_unknown" if due is None else ("completed_on_time" if finished <= due else "completed_late")
        elif merged is None:
            followup = "not_yet_merged"
        elif due is None:
            followup = "due_unknown"
        elif not complete_now:
            followup = "unknown_incomplete_export"
        elif unknown_time:
            followup = "unknown_review_timing"
        else:
            followup = "overdue" if as_of > due else "pending"
        if followup not in {"completed_on_time", "not_yet_merged"}:
            finding("emergency_" + followup, "Show the post-change peer review, dispositions, agreed due date and emergency rationale.",
                    [r["source_ref"] for r in candidates])
        if emergency["rationale"] is None:
            finding("emergency_rationale_unknown", "What justified the exception, and what support was available?", [])

    refs = {r["source_ref"] for r in change["reviews"]}
    refs.update(r["context_ref"] for r in change["reviews"] if r["context_ref"])
    for review in change["reviews"]:
        for item in review["feedback"]:
            refs.add(item["source_ref"])
            if item["resolution_ref"]:
                refs.add(item["resolution_ref"])
    if export["reference"]:
        refs.add(export["reference"])
    return {"id": change["id"], "group": change["group"], "service": change["service"],
            "context": change["context"], "head": change["head"], "merged": merged is not None,
            "assessment_cutoff": cutoff.isoformat(), "export_complete_through_cutoff": complete,
            "review_signal": signal, "substantive_before_cutoff": bool(substantive),
            "unknown_time_review_count": len(unknown_time),
            "approval_before_cutoff": bool(approved), "older_head_review_count": len(stale),
            "self_review_count": sum(r["reviewer"] == change["author"] for r in reviews),
            "feedback_unresolved_at_cutoff": len(unresolved), "first_substantive_feedback_wait_minutes": wait,
            "no_observed_feedback_window_minutes": censor, "emergency_followup": followup,
            "source_refs": sorted(refs), "followups": findings}


def ratio(numerator: int, denominator: int) -> dict:
    return {"numerator": numerator, "denominator": denominator,
            "fraction": numerator / denominator if denominator else None}


def summarize(rows: list[dict]) -> dict:
    merged = [r for r in rows if r["merged"]]
    # Include observed positives from partial exports, but do not use incomplete
    # exports as evidence of a negative. Also report coverage against all samples.
    decidable = [r for r in merged if r["substantive_before_cutoff"] or
                 (r["export_complete_through_cutoff"] and r["unknown_time_review_count"] == 0)]
    waits = [r["first_substantive_feedback_wait_minutes"] for r in rows
             if r["first_substantive_feedback_wait_minutes"] is not None]
    return {"sampled_changes": len(rows), "merged_changes": len(merged),
            "substantive_signal_among_assessable_merged": ratio(sum(r["substantive_before_cutoff"] for r in decidable), len(decidable)),
            "assessable_merged_coverage": ratio(len(decidable), len(merged)),
            "observed_substantive_among_all_merged": ratio(sum(r["substantive_before_cutoff"] for r in merged), len(merged)),
            "review_signal_counts": dict(sorted(Counter(r["review_signal"] for r in rows).items())),
            "latency": {"unit": "calendar_minutes", "observed_pairs": len(waits),
                        "median": statistics.median(waits) if waits else None,
                        "p90_nearest_rank": sorted(waits)[math.ceil(0.9 * len(waits)) - 1] if waits else None,
                        "excluded_changes": len(rows) - len(waits),
                        "unobserved_feedback_windows": sum(r["no_observed_feedback_window_minutes"] is not None for r in rows)}}


def assess(packet: dict) -> dict:
    validate(packet)
    as_of = timestamp(packet["as_of"], "as_of")
    rows = [assess_change(c, as_of) for c in packet["changes"]]
    rows.sort(key=lambda row: row["id"])
    canonical = json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {"schema": SCHEMA + "/report", "synthetic": packet["synthetic"], "as_of": packet["as_of"],
            "input_sha256": hashlib.sha256(canonical).hexdigest(), "sampling_note": packet["sampling_note"],
            "interpretation": "Signals in supplied records only: not verified source authenticity, code quality, individual productivity, maturity, or University findings.",
            "summary": summarize(rows), "by_group": {g: summarize([r for r in rows if r["group"] == g]) for g in ("ESS", "RIS", "IAM")},
            "changes": rows}


def cell(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def render(report: dict) -> str:
    heading = "SYNTHETIC REHEARSAL" if report["synthetic"] else "SUPPLIED-RECORD ASSESSMENT"
    lines = [f"# Review practice — {heading}", "", report["interpretation"], "",
             f"As of: {cell(report['as_of'])}", f"Input SHA-256: `{report['input_sha256']}`", "",
             "Sampling: " + cell(report["sampling_note"]), "", "## Summary", ""]
    for group, summary in [("All", report["summary"]), *report["by_group"].items()]:
        coverage = summary["assessable_merged_coverage"]
        signal = summary["substantive_signal_among_assessable_merged"]
        latency = summary["latency"]
        lines.append(f"{group}: substantive signal {signal['numerator']}/{signal['denominator']} assessable merged changes; "
                     f"coverage {coverage['numerator']}/{coverage['denominator']}; "
                     f"feedback median {latency['median']} calendar minutes across {latency['observed_pairs']} observed pairs, "
                     f"{latency['excluded_changes']} excluded. These are sample descriptors, not benchmarks.")
        lines.append("")
    lines += ["## Change-level evidence", "", "| Change | Group | Review signal | Unresolved at cutoff | Emergency follow-up |", "|---|---|---|---:|---|"]
    for row in report["changes"]:
        lines.append("| " + " | ".join(cell(row[k]) for k in ("id", "group", "review_signal", "feedback_unresolved_at_cutoff", "emergency_followup")) + " |")
    for row in report["changes"]:
        lines += ["", "## " + cell(row["id"]), "", "Service: " + cell(row["service"]), "Context: " + cell(json.dumps(row["context"], sort_keys=True)),
                  "", "Evidence references (not fetched or authenticated):"]
        lines += ["- " + cell(ref) for ref in row["source_refs"]] or ["- No source references supplied."]
        lines += ["", "Follow-up questions:"]
        lines += [f"- {cell(f['code'])}: {cell(f['question'])}" for f in row["followups"]] or ["- No configured metadata follow-up triggered; source review is still required."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Local UTF-8 JSON metadata packet")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    try:
        report = assess(loads(args.input.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, InputError) as error:
        print(f"review-practice: {error}", file=sys.stderr)
        return 2
    print(render(report) if args.format == "markdown" else json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), end="" if args.format == "markdown" else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
