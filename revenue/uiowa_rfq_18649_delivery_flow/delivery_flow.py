#!/usr/bin/env python3
"""Offline UIOWA-062 delivery-trace instrument. No network or deployment actions.

COPPERLEAF-63 originated the order and interval/censoring design. This published
implementation and its tests are HALYARD-86-D62's recovery, not the earlier suite.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import sys
from typing import Any

SCHEMA = "uiowa-delivery-flow/v1"
STAGES = ("build", "verification", "packaging", "promotion", "deployment")
MAX_BYTES = 4 * 1024 * 1024
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z")


class InputError(ValueError):
    """A supplied record cannot be interpreted without changing its meaning."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InputError(message)


def text(value: Any, where: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{where}: nonempty string required")
    require(value == value.strip(), f"{where}: surrounding whitespace is ambiguous")
    return value


def timestamp(value: Any, where: str) -> datetime:
    require(isinstance(value, str) and STAMP.fullmatch(value) is not None,
            f"{where}: timestamp must include seconds and Z or a numeric timezone")
    if value[-1] != "Z":
        require(int(value[-5:-3]) <= 23 and int(value[-2:]) <= 59,
                f"{where}: invalid timezone offset")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise InputError(f"{where}: invalid calendar timestamp") from exc


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in out, f"duplicate JSON key: {key}")
        out[key] = value
    return out


def reject_constant(value: str) -> None:
    raise InputError(f"non-finite JSON number: {value}")


def decode(raw: bytes) -> dict[str, Any]:
    require(len(raw) <= MAX_BYTES, "input exceeds 4 MiB")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                           parse_constant=reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise InputError(f"invalid UTF-8 JSON: {exc}") from exc
    require(isinstance(value, dict), "packet: object required")
    return value


def union_seconds(intervals: list[tuple[datetime, datetime]]) -> float:
    """Elapsed interval union, never the sum of overlapping attempts."""
    if not intervals:
        return 0.0
    ordered = sorted(intervals)
    start, end = ordered[0]
    require(start <= end, "negative interval")
    total = timedelta(0)
    for left, right in ordered[1:]:
        require(left <= right, "negative interval")
        if left > end:
            total += end - start
            start, end = left, right
        else:
            end = max(end, right)
    return (total + end - start).total_seconds()


def references(value: Any, evidence: dict[str, Any], where: str) -> list[str]:
    require(isinstance(value, list), f"{where}: list required (use [] for unknown)")
    result = [text(item, where) for item in value]
    require(len(result) == len(set(result)), f"{where}: duplicate evidence reference")
    require(all(item in evidence for item in result), f"{where}: unresolved evidence reference")
    return result


def assess(packet: dict[str, Any]) -> dict[str, Any]:
    require(packet.get("schema_version") == SCHEMA, "unsupported schema_version")
    require(type(packet.get("synthetic")) is bool, "synthetic: explicit boolean required")
    cutoff = timestamp(packet.get("observed_at"), "observed_at")
    traces = packet.get("traces")
    require(isinstance(traces, list) and 0 < len(traces) <= 200, "traces: 1..200 records required")
    trace_ids: set[str] = set()
    reports = []
    for trace in traces:
        require(isinstance(trace, dict), "trace: object required")
        trace_id = text(trace.get("id"), "trace.id")
        require(trace_id not in trace_ids, f"duplicate trace id: {trace_id}")
        trace_ids.add(trace_id)
        require(trace.get("group") in ("ESS", "RIS", "IAM"), f"{trace_id}: unknown group")
        service = text(trace.get("service"), f"{trace_id}.service")
        requested = timestamp(trace.get("requested_at"), f"{trace_id}.requested_at")
        require(requested <= cutoff, f"{trace_id}: request is after observation")
        rows = trace.get("evidence")
        require(isinstance(rows, list), f"{trace_id}.evidence: list required")
        evidence: dict[str, Any] = {}
        for row in rows:
            require(isinstance(row, dict), "evidence: object required")
            key = text(row.get("id"), "evidence.id")
            require(key not in evidence, f"duplicate evidence id: {key}")
            text(row.get("locator"), f"evidence.{key}.locator")
            recorded = timestamp(row.get("recorded_at"), f"evidence.{key}.recorded_at")
            require(recorded <= cutoff, f"evidence.{key}: recorded after observation")
            evidence[key] = dict(row)
        attempts = trace.get("attempts")
        require(isinstance(attempts, list) and len(attempts) <= 1000,
                f"{trace_id}.attempts: list of at most 1000 required")
        known_ids: set[str] = set()
        ordinals: dict[tuple[str, str], set[int]] = {}
        results, questions, queues, executions, manual_queues = [], [], [], [], []
        def ask(code: str, subject: str, question: str, refs: list[str]) -> None:
            questions.append({"code": code, "subject": subject, "question": question,
                              "evidence_refs": refs})
        for item in attempts:
            require(isinstance(item, dict), "attempt: object required")
            aid = text(item.get("id"), "attempt.id")
            require(aid not in known_ids, f"duplicate attempt id: {aid}")
            known_ids.add(aid)
            stage, step, number = item.get("stage"), text(item.get("step"), aid + ".step"), item.get("attempt")
            require(stage in STAGES, f"{aid}: unknown stage")
            require(type(number) is int and 1 <= number <= 1000, f"{aid}: attempt must be integer 1..1000")
            sequence = ordinals.setdefault((stage, step), set())
            require(number not in sequence, f"{aid}: duplicate stage/step/attempt")
            sequence.add(number)
            mode, state, outcome = item.get("mode"), item.get("progress_state"), item.get("result")
            require(mode in ("manual", "automated"), f"{aid}: invalid mode")
            require(state in ("queued", "running", "finished", "unknown"), f"{aid}: invalid progress_state")
            require(outcome in ("success", "failure", "cancelled", "unknown"), f"{aid}: invalid result")
            owner = item.get("owner_role")
            if owner is not None:
                text(owner, aid + ".owner_role")
            refs = references(item.get("evidence_refs"), evidence, aid)
            times = {key: timestamp(item[key], aid + "." + key) if item.get(key) is not None else None
                     for key in ("queued_at", "started_at", "finished_at")}
            q, s, f = (times[key] for key in ("queued_at", "started_at", "finished_at"))
            present = [moment for moment in (q, s, f) if moment is not None]
            require(all(requested <= moment <= cutoff for moment in present), f"{aid}: time outside observation window")
            require(present == sorted(present), f"{aid}: timestamps out of order")
            require((state == "finished") == (f is not None), f"{aid}: finished state/time disagree")
            require((state == "finished") == (outcome != "unknown"), f"{aid}: state/result disagree")
            require(state != "queued" or (s is None and q is not None), f"{aid}: queued state requires only queue time")
            require(state != "running" or s is not None, f"{aid}: running state requires start time")
            queue_end = s if s is not None else cutoff if state == "queued" else None
            execution_end = f if f is not None else cutoff if state == "running" else None
            qi = (q, queue_end) if q is not None and queue_end is not None else None
            ei = (s, execution_end) if s is not None and execution_end is not None else None
            q_seconds = (qi[1] - qi[0]).total_seconds() if qi else None
            e_seconds = (ei[1] - ei[0]).total_seconds() if ei else None
            if qi:
                queues.append(qi)
                if mode == "manual":
                    manual_queues.append(qi)
            if ei:
                executions.append(ei)
            results.append({**item, "queue_seconds": q_seconds, "execution_seconds": e_seconds,
                            "queue_measure": "censored" if qi and state == "queued" else "complete" if qi else "unknown",
                            "execution_measure": "censored" if ei and state == "running" else "complete" if ei else "unknown"})
            if not refs:
                ask("UNREFERENCED_RECORD", aid, "Which retained source supports this supplied attempt record?", refs)
            if owner is None:
                ask("OWNER_UNKNOWN", aid, "Which organizational role maintains this step and handles failures?", refs)
            if q_seconds is None or e_seconds is None:
                ask("TIME_COVERAGE", aid, "Which queue/start/finish records or current-state observations are missing?", refs)
            if outcome == "failure":
                ask("FAILED_ATTEMPT", aid, "What caused this failure; was the next attempt a rerun or changed work?", refs)
        for (stage, step), numbers in sorted(ordinals.items()):
            gaps = sorted(set(range(1, max(numbers) + 1)) - numbers)
            if gaps:
                ask("ATTEMPT_GAPS", f"{stage}/{step}", f"Are attempts {gaps} missing from this export?", [])
        stages = []
        for stage in STAGES:
            subset = [row for row in results if row["stage"] == stage]
            stages.append({"stage": stage, "record_count": len(subset),
                           "results": dict(sorted(Counter(row["result"] for row in subset).items())),
                           "evidence_refs": sorted({ref for row in subset for ref in row["evidence_refs"]}),
                           "coverage": "records_supplied" if subset else "unknown"})
            if not subset:
                ask("STAGE_UNKNOWN", stage, "Is this stage absent, external/shared, combined with another step, or unrecorded?", [])
        reproducibility = trace.get("reproducibility")
        require(isinstance(reproducibility, dict), f"{trace_id}.reproducibility: object required")
        repro_state = reproducibility.get("status")
        require(repro_state in ("observed_match", "observed_mismatch", "documented_only", "unknown"),
                f"{trace_id}: invalid reproducibility status")
        repro_refs = references(reproducibility.get("evidence_refs"), evidence, "reproducibility")
        require(repro_state == "unknown" or bool(repro_refs), "non-unknown reproducibility requires references")
        # Even the strongest supplied label needs a human corroboration disposition.
        # A source reference alone is not independent artifact comparison.
        ask("REPRODUCIBILITY_REVIEW", "reproducibility",
            "What comparable input/artifact records and conditions corroborate this supplied reproducibility account?", repro_refs)
        def execution_coverage(subset: list[dict[str, Any]]) -> dict[str, int]:
            counts = Counter(row["execution_measure"] for row in subset)
            return {state: counts[state] for state in ("complete", "censored", "unknown")}
        failed = [row for row in results if row["result"] == "failure"]
        repeated = [row for row in results if row["attempt"] > 1]
        queue_union, exec_union = union_seconds(queues), union_seconds(executions)
        active_union = union_seconds(queues + executions)
        window = (cutoff - requested).total_seconds()
        successful = [timestamp(row["finished_at"], "deployment") for row in results
                      if row["stage"] == "deployment" and row["result"] == "success"]
        reports.append({"id": trace_id, "group": trace["group"], "service": service,
                        "requested_at": trace["requested_at"], "attempts": results,
                        "stage_matrix": stages, "evidence_register": rows,
                        "reproducibility": reproducibility,
                        "reproducibility_corroboration": {
                            "status": "NOT_ESTABLISHED_BY_TOOL", "evidence_refs": repro_refs,
                            "reason": "Supplied labels and locators are retained; the tool does not independently compare artifacts."},
                        "follow_up": questions,
                        "metrics": {"attempt_count": len(results),
                            "failed_attempt_count": sum(row["result"] == "failure" for row in results),
                            "repeat_attempt_count": sum(row["attempt"] > 1 for row in results),
                            "failed_execution_measure_counts": execution_coverage(failed),
                            "repeat_execution_measure_counts": execution_coverage(repeated),
                            "queue_measure_counts": dict(sorted(Counter(row["queue_measure"] for row in results).items())),
                            "execution_measure_counts": dict(sorted(Counter(row["execution_measure"] for row in results).items())),
                            "observation_window_seconds": window,
                            "queue_union_seconds": queue_union,
                            "execution_union_seconds": exec_union,
                            "queue_execution_overlap_seconds": round(queue_union + exec_union - active_union, 6),
                            "observed_activity_union_seconds": active_union,
                            "unattributed_window_seconds": round(window - active_union, 6),
                            "manual_queue_union_seconds": union_seconds(manual_queues),
                            "execution_attempt_seconds_sum": sum(row["execution_seconds"] or 0 for row in results),
                            "failed_execution_seconds_lower_bound": sum(row["execution_seconds"] or 0 for row in results if row["result"] == "failure"),
                            "repeat_execution_seconds_lower_bound": sum(row["execution_seconds"] or 0 for row in results if row["attempt"] > 1),
                            "recorded_first_deployment_latency_seconds": (min(successful) - requested).total_seconds() if successful else None}})
    return {"schema_version": SCHEMA, "synthetic": packet["synthetic"], "observed_at": packet["observed_at"],
            "external_action_authorized": False, "traces": reports,
            "interpretation": ["Supplied records are not independent verification or University findings.",
                "Censored durations are observed lower bounds; unknown durations are not zero.",
                "Attempt-duration sums are not person-hours. Failure and repeat measures overlap; never add them as savings.",
                "Unattributed time is not demonstrated waste. A success record is not release approval or whole-service readiness."]}


def escape(value: Any) -> str:
    result = html.escape(str(value), quote=False).replace("|", "&#124;")
    for char in ("\\", "`", "*", "_", "[", "]"):
        result = result.replace(char, "\\" + char)
    return result.replace("\n", "<br>").replace("\r", "")


def markdown(report: dict[str, Any]) -> str:
    lines = ["# Delivery-flow assessment", "", "SYNTHETIC REHEARSAL" if report["synthetic"] else "SUPPLIED RECORD REVIEW",
             "", "Observation: " + escape(report["observed_at"]), ""]
    if "source_sha256" in report:
        lines += ["Input SHA-256: `" + report["source_sha256"] + "`", ""]
    lines += ["## Interpretation", ""] + ["- " + escape(item) for item in report["interpretation"]]
    for trace in report["traces"]:
        lines += ["", "## " + escape(trace["id"]) + " — " + escape(trace["service"]), "",
                  "| Measure | Value |", "|---|---|"]
        lines += [f"| {escape(key)} | {escape('UNKNOWN' if value is None else value)} |"
                  for key, value in trace["metrics"].items()]
        lines += ["", "| Stage | Records | Results | Coverage | Evidence |", "|---|---:|---|---|---|"]
        lines += [f"| {row['stage']} | {row['record_count']} | {escape(row['results'])} | {row['coverage']} | {escape(', '.join(row['evidence_refs']))} |"
                  for row in trace["stage_matrix"]]
        lines += ["", "Reproducibility corroboration: " + escape(trace["reproducibility_corroboration"]["status"]),
                  "", "### Follow-up", "", "| Code / subject | Question | Evidence |", "|---|---|---|"]
        lines += [f"| {escape(row['code'] + ' / ' + row['subject'])} | {escape(row['question'])} | {escape(', '.join(row['evidence_refs']))} |"
                  for row in trace["follow_up"]]
        lines += ["", "### Evidence locators", ""]
        lines += ["- " + escape(row["id"]) + ": " + escape(row["locator"]) for row in trace["evidence_register"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", type=Path, help="New file only; existing paths are never overwritten")
    args = parser.parse_args(argv)
    try:
        with args.input.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        report = assess(decode(raw))
        report["source_sha256"] = hashlib.sha256(raw).hexdigest()
        rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n" if args.format == "json" else markdown(report)
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(rendered)
        else:
            sys.stdout.write(rendered)
        return 0
    except (InputError, OSError, ValueError, RecursionError) as exc:
        print(f"delivery-flow: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
