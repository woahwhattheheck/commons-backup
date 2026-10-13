#!/usr/bin/env python3
"""Offline evidence-request planning with explicit effort and marginal coverage."""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import csv
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import sys

SCHEMA = "uiowa.evidence-requests.v1"


class PlanningError(ValueError):
    pass


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def load_json(text):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise PlanningError(f"duplicate JSON field: {key}")
            out[key] = value
        return out
    def constant(value):
        raise PlanningError(f"invalid JSON number: {value}")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def text(value, name):
    if type(value) is not str or not value.strip():
        raise PlanningError(f"{name} must be nonempty text")
    return value


def number(value, name):
    if type(value) is not int or value < 0:
        raise PlanningError(f"{name} must be a nonnegative integer")
    return value


def csv_rows(raw):
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
    try:
        header = next(reader)
    except StopIteration as exc:
        raise PlanningError("CSV is empty") from exc
    if any(not field for field in header) or len(set(header)) != len(header):
        raise PlanningError("CSV columns must be nonempty and unique")
    rows = []
    for ordinal, values in enumerate(reader, 2):
        if len(values) != len(header):
            raise PlanningError(f"CSV record {ordinal} has the wrong column count")
        rows.append((ordinal, dict(zip(header, values))))
    return header, rows


def from_register(raw: bytes, source_path: str) -> dict:
    header, rows = csv_rows(raw)
    required = {"evidence_id", "finding_id", "follow_up", "conflict_group", "evidence_state"}
    if not required.issubset(header):
        raise PlanningError("register lacks required columns: " + ", ".join(sorted(required - set(header))))
    questions, requests, conflict_members, seen = [], [], {}, set()
    for ordinal, row in rows:
        evidence_id = text(row["evidence_id"], "evidence_id")
        if evidence_id in seen:
            raise PlanningError("duplicate evidence_id: " + evidence_id)
        seen.add(evidence_id)
        if not row["follow_up"].strip():
            continue
        question_id = "follow-up:" + evidence_id
        locator = f"{source_path}#csv-record={ordinal}"
        questions.append({"question_id": question_id, "question": row["follow_up"],
                          "priority": 1, "finding_ids": [row["finding_id"]],
                          "evidence_ids": [evidence_id], "source_locators": [locator],
                          "source_rows": [deepcopy(row)]})
        coverage = [question_id]
        if row["conflict_group"]:
            group = row["conflict_group"]
            coverage.append("conflict:" + group)
            conflict_members.setdefault(group, []).append((locator, row))
        requests.append({"request_id": "request:" + evidence_id, "title": row["follow_up"],
                         "effort_minutes": None, "question_ids": coverage})
    for group, members in sorted(conflict_members.items()):
        questions.append({"question_id": "conflict:" + group,
                          "question": "Clarify the retained contradiction " + group,
                          "priority": 1,
                          "finding_ids": sorted({r["finding_id"] for _, r in members}),
                          "evidence_ids": sorted({r["evidence_id"] for _, r in members}),
                          "source_locators": [loc for loc, _ in members],
                          "source_rows": [deepcopy(r) for _, r in members]})
    return {"schema": SCHEMA, "questions": questions, "requests": requests,
            "assumptions": ["All initial question priorities are editable equal weights of 1.",
                            "All collection effort is initially unestimated, not zero.",
                            "A request's coverage is potential usefulness, not evidence resolution."],
            "source": {"path": source_path, "sha256": hashlib.sha256(raw).hexdigest(),
                       "bytes": len(raw), "base64": base64.b64encode(raw).decode("ascii"),
                       "columns": header, "record_count": len(rows)}}


def validate(packet):
    if type(packet) is not dict or packet.get("schema") != SCHEMA:
        raise PlanningError("unsupported worksheet schema")
    questions, requests = {}, {}
    for field in ("questions", "requests"):
        if type(packet.get(field)) is not list:
            raise PlanningError(field + " must be an array")
    for q in packet["questions"]:
        if type(q) is not dict:
            raise PlanningError("question must be an object")
        key = text(q.get("question_id"), "question_id")
        if key in questions:
            raise PlanningError("duplicate question_id: " + key)
        text(q.get("question"), "question")
        number(q.get("priority"), "question priority")
        questions[key] = q
    for request in packet["requests"]:
        if type(request) is not dict:
            raise PlanningError("request must be an object")
        key = text(request.get("request_id"), "request_id")
        if key in requests:
            raise PlanningError("duplicate request_id: " + key)
        text(request.get("title"), "request title")
        if "effort_minutes" not in request:
            raise PlanningError("request requires effort_minutes; use null when unknown")
        if request["effort_minutes"] is not None:
            number(request["effort_minutes"], "effort_minutes")
        coverage = request.get("question_ids")
        if type(coverage) is not list or any(type(q) is not str for q in coverage):
            raise PlanningError("request question_ids must be an array of strings")
        if len(coverage) != len(set(coverage)):
            raise PlanningError("duplicate question reference in " + key)
        if set(coverage) - questions.keys():
            raise PlanningError("request references unknown questions: " + key)
        requests[key] = request
    return questions, requests


def plan(packet: dict, budgets: list[int]) -> dict:
    questions, requests = validate(packet)
    if not budgets:
        raise PlanningError("supply at least one budget in minutes")
    for budget in budgets:
        number(budget, "budget")
    scenarios = []
    for budget in sorted(set(budgets)):
        remaining, covered, selected = budget, set(), []
        pending = dict(requests)
        while True:
            candidates = []
            for key, request in pending.items():
                effort = request["effort_minutes"]
                novel = set(request["question_ids"]) - covered
                gain = sum(questions[q]["priority"] for q in novel)
                if effort is None or effort > remaining or gain == 0:
                    continue
                candidates.append((key, request, novel, gain))
            if not candidates:
                break
            # Explicit zero effort is distinct from missing effort. Free useful
            # requests go first; exact fractions keep tie ordering reproducible.
            key, request, novel, gain = min(candidates, key=lambda item: (
                0 if item[1]["effort_minutes"] == 0 else 1,
                -Fraction(item[3], item[1]["effort_minutes"] or 1),
                -item[3], item[1]["effort_minutes"], item[0]))
            effort = request["effort_minutes"]
            covered.update(novel)
            remaining -= effort
            selected.append({"step": len(selected) + 1, "request_id": key,
                             "title": request["title"], "effort_minutes": effort,
                             "marginal_question_ids": sorted(novel), "marginal_priority": gain,
                             "cumulative_minutes": budget - remaining,
                             "cumulative_priority": sum(questions[q]["priority"] for q in covered)})
            del pending[key]
        omitted = []
        for key, request in sorted(pending.items()):
            novel = set(request["question_ids"]) - covered
            gain = sum(questions[q]["priority"] for q in novel)
            reason = ("EFFORT_UNESTIMATED" if request["effort_minutes"] is None else
                      "NO_ADDITIONAL_PRIORITY" if gain == 0 else "REMAINING_BUDGET")
            omitted.append({"request_id": key, "reason": reason,
                            "effort_minutes": request["effort_minutes"],
                            "remaining_question_ids": sorted(novel), "remaining_priority": gain})
        scenarios.append({"budget_minutes": budget, "used_minutes": budget - remaining,
                          "remaining_minutes": remaining, "selected": selected,
                          "covered_question_ids": sorted(covered),
                          "uncovered_question_ids": sorted(questions.keys() - covered),
                          "covered_priority": sum(questions[q]["priority"] for q in covered),
                          "unselected": omitted})
    canonical = json.dumps(packet, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    return {"schema": "uiowa.evidence-request-plan.v1",
            "method": "deterministic marginal-priority-per-minute greedy heuristic; not an optimum certificate",
            "worksheet_sha256": hashlib.sha256(canonical).hexdigest(),
            "worksheet": deepcopy(packet), "scenarios": scenarios,
            "collection_performed": False, "evidence_resolved": False,
            "assessment_authority": False}


def csv_text(columns, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def worksheet_csv(packet, kind):
    validate(packet)
    if kind == "questions":
        columns = ["question_id", "question", "priority"]
        rows = [{k: q[k] for k in columns} for q in packet["questions"]]
    else:
        columns = ["request_id", "title", "effort_minutes", "question_ids"]
        rows = [{**{k: r[k] for k in columns if k != "question_ids"},
                 "question_ids": json.dumps(r["question_ids"], ensure_ascii=False)} for r in packet["requests"]]
    return csv_text(columns, rows)


def apply_csv(packet, raw, kind):
    result = deepcopy(packet)
    header, rows = csv_rows(raw)
    columns = ({"question_id", "question", "priority"} if kind == "questions" else
               {"request_id", "title", "effort_minutes", "question_ids"})
    if not columns.issubset(header):
        raise PlanningError("worksheet CSV is missing columns")
    key_field = "question_id" if kind == "questions" else "request_id"
    existing = {row[key_field]: row for row in result[kind]}
    seen = set()
    for ordinal, row in rows:
        key = row[key_field]
        if key in seen or key not in existing:
            raise PlanningError(f"CSV record {ordinal}: unknown or duplicate {key_field}")
        seen.add(key)
        update = existing[key]
        if kind == "questions":
            update["question"] = row["question"]
            update["priority"] = int(row["priority"])
        else:
            update["title"] = row["title"]
            update["effort_minutes"] = int(row["effort_minutes"]) if row["effort_minutes"].strip() else None
            update["question_ids"] = load_json(row["question_ids"])
        update["worksheet_csv_row"] = row
    validate(result)
    return result


def render_markdown(report):
    lines = ["# Evidence request budget scenarios", "", report["method"], "",
             "Potential question coverage only. Selection does not resolve evidence or authorize collection.", ""]
    def cell(value):
        return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")
    for scenario in report["scenarios"]:
        lines += [f"## {scenario['budget_minutes']} minutes", "",
                  f"Uses {scenario['used_minutes']} minutes; covers {len(scenario['covered_question_ids'])} questions with total editable priority {scenario['covered_priority']}.", "",
                  "| Step | Request | Minutes | New priority | New questions |",
                  "| --- | --- | ---: | ---: | --- |"]
        for row in scenario["selected"]:
            lines.append("| " + " | ".join(cell(x) for x in (row["step"], row["request_id"], row["effort_minutes"], row["marginal_priority"], ", ".join(row["marginal_question_ids"]))) + " |")
        if not scenario["selected"]:
            lines += ["", "No request selected under the supplied estimates and budget."]
        lines += ["", "Unselected requests:", ""]
        lines += [f"- `{cell(row['request_id'])}`: {row['reason']}" for row in scenario["unselected"]]
        lines += [""]
    return "\n".join(lines) + "\n"


def report_csv(report):
    columns = ["budget_minutes", "step", "request_id", "effort_minutes", "marginal_priority", "cumulative_minutes", "marginal_question_ids"]
    rows = []
    for scenario in report["scenarios"]:
        for step in scenario["selected"]:
            rows.append({**{k: step[k] for k in columns if k not in ("budget_minutes", "marginal_question_ids")},
                         "budget_minutes": scenario["budget_minutes"],
                         "marginal_question_ids": json.dumps(step["marginal_question_ids"], ensure_ascii=False)})
    return csv_text(columns, rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("from-register")
    make.add_argument("input", type=Path)
    export = sub.add_parser("worksheet-csv")
    export.add_argument("input", type=Path)
    export.add_argument("kind", choices=("questions", "requests"))
    calculate = sub.add_parser("plan")
    calculate.add_argument("input", type=Path)
    calculate.add_argument("--budgets", required=True, help="Comma-separated independent minute budgets")
    calculate.add_argument("--questions-csv", type=Path)
    calculate.add_argument("--requests-csv", type=Path)
    calculate.add_argument("--format", choices=("json", "csv", "markdown"), default="json")
    args = parser.parse_args(argv)
    try:
        if args.command == "from-register":
            result = encode(from_register(args.input.read_bytes(), args.input.as_posix()))
        else:
            packet = load_json(args.input.read_text(encoding="utf-8"))
            validate(packet)
            if args.command == "worksheet-csv":
                result = worksheet_csv(packet, args.kind)
            else:
                for kind in ("questions", "requests"):
                    path = getattr(args, kind + "_csv")
                    if path:
                        packet = apply_csv(packet, path.read_bytes(), kind)
                report = plan(packet, [int(value) for value in args.budgets.split(",")])
                result = {"json": encode, "csv": report_csv, "markdown": render_markdown}[args.format](report)
        sys.stdout.write(result)
        return 0
    except (ValueError, OSError, UnicodeError, csv.Error, RecursionError) as exc:
        print(f"evidence-requests: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
