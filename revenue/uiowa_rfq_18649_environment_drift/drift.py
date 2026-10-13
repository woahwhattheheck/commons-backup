#!/usr/bin/env python3
"""Offline, evidence-aware environment comparison. Python 3.10+, stdlib only."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
import html
import json
import math
from pathlib import Path
import re
import sys

VERSION = "uiowa-environment-drift/v1"
STATUSES = ("ALIGNED", "INTENTIONAL_DIFFERENCE", "UNEXPLAINED_DIFFERENCE",
            "EXPLANATION_REVIEW_DUE", "UNKNOWN", "NOT_APPLICABLE", "NOT_COMPARABLE")
ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,79}\Z")
LIMITATION = ("Supplied-record consistency only; not live-environment verification, "
              "a maturity score, a deployment decision, or a University finding.")


class InputError(ValueError):
    """The packet is structurally ambiguous or malformed."""


def require(condition, message):
    if not condition:
        raise InputError(message)


def text(value, where):
    require(isinstance(value, str) and bool(value.strip()), f"{where}: nonempty text required")
    return value


def day(value, where):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value),
            f"{where}: expected YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise InputError(f"{where}: invalid date") from exc


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def json_value(value):
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if isinstance(value, list):
        return all(json_value(v) for v in value)
    if isinstance(value, dict):
        return all(type(k) is str and json_value(v) for k, v in value.items())
    return False


def canonical(value):
    require(json_value(value), "only finite JSON values are supported")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def indexed(items, where):
    require(isinstance(items, list), f"{where}: array required")
    result = {}
    for item in items:
        require(isinstance(item, dict), f"{where}: object required")
        ident = item.get("id")
        require(isinstance(ident, str) and ID.fullmatch(ident), f"{where}: invalid id")
        require(ident not in result, f"{where}: duplicate id {ident}")
        result[ident] = item
    return result


def validate(packet):
    require(isinstance(packet, dict), "packet: object required")
    canonical(packet)
    require(type(packet.get("schema_version")) is int and packet["schema_version"] == 1,
            "schema_version must be integer 1")
    text(packet.get("label"), "label")
    as_of = day(packet.get("as_of"), "as_of")
    age = packet.get("max_age_days")
    require(type(age) is int and 0 <= age <= 3660, "max_age_days: integer 0..3660 required")
    envs = packet.get("environments")
    require(isinstance(envs, list) and len(envs) >= 2, "at least two environments required")
    require(all(isinstance(e, str) and ID.fullmatch(e) for e in envs), "invalid environment id")
    require(len(set(envs)) == len(envs), "duplicate environment id")
    require(packet.get("baseline") in envs, "baseline must name an environment")
    evidence = indexed(packet.get("evidence"), "evidence")
    for ident, record in evidence.items():
        text(record.get("locator"), f"{ident}.locator")
        require(record.get("kind") in ("artifact", "statement"), f"{ident}.kind invalid")
        require(day(record.get("captured_on"), ident) <= as_of, f"{ident}: future evidence")
    checks = indexed(packet.get("checks"), "checks")
    require(bool(checks), "at least one check required")
    for ident, check in checks.items():
        for field in ("group", "service", "dimension", "key", "impact", "owner_role"):
            text(check.get(field), f"{ident}.{field}")
        effort = check.get("effort_hours")
        require(isinstance(effort, list) and len(effort) == 2 and
                all(type(x) in (int, float) and math.isfinite(x) and x >= 0 for x in effort)
                and effort[0] <= effort[1], f"{ident}: invalid effort range")
        values = check.get("values")
        require(isinstance(values, dict) and set(values) <= set(envs), f"{ident}: invalid values keys")
        for env, obs in values.items():
            require(isinstance(obs, dict), f"{ident}/{env}: observation object required")
            state = obs.get("state")
            require(state in ("observed", "unknown", "not_applicable"), f"{ident}/{env}: invalid state")
            if state == "observed":
                require("value" in obs, f"{ident}/{env}: observed requires value (null is allowed)")
            else:
                text(obs.get("reason"), f"{ident}/{env}.reason")
                require("value" not in obs, f"{ident}/{env}: non-observed state cannot carry value")
            require(obs.get("evidence_id") is None or isinstance(obs["evidence_id"], str),
                    f"{ident}/{env}: evidence_id must be text or null")
        for rid, rationale in indexed(check.get("intentions", []), f"{ident}.intentions").items():
            require(rationale.get("environment") in envs and rationale["environment"] != packet["baseline"],
                    f"{rid}: invalid target environment")
            for field in ("reason", "owner_role", "evidence_id"):
                text(rationale.get(field), f"{rid}.{field}")
            require("value" in rationale and "baseline_value" in rationale, f"{rid}: both expected values required")
            start = day(rationale.get("valid_from"), f"{rid}.valid_from")
            end = day(rationale.get("review_on"), f"{rid}.review_on")
            require(start <= end, f"{rid}: reversed validity dates")
    return as_of, evidence, checks


def evidence_problem(ident, evidence, as_of, max_age=None):
    record = evidence.get(ident)
    if record is None:
        return "missing_evidence"
    if record["kind"] != "artifact":
        return "statement_only"
    if max_age is not None and (as_of - day(record["captured_on"], ident)).days > max_age:
        return "stale_evidence"
    return None


def observation_problem(obs, evidence, as_of, max_age):
    if obs is None:
        return "missing_observation"
    if obs["state"] == "unknown":
        return "declared_unknown"
    return evidence_problem(obs.get("evidence_id"), evidence, as_of, max_age)


def compare(check, env, packet, evidence, as_of):
    baseline = packet["baseline"]
    observed = check["values"].get(env)
    reference = check["values"].get(baseline)
    notes = []
    intentions = sorted((r for r in check.get("intentions", []) if r["environment"] == env),
                        key=lambda r: r["id"])
    problem = observation_problem(observed, evidence, as_of, packet["max_age_days"])
    base_problem = observation_problem(reference, evidence, as_of, packet["max_age_days"])
    used = []
    if problem:
        status = "UNKNOWN"
        notes.append("target_" + problem)
        if base_problem:
            notes.append("baseline_" + base_problem)
    elif observed["state"] == "not_applicable":
        status = "NOT_APPLICABLE"
        notes.append("target_not_applicable")
    elif base_problem:
        status = "UNKNOWN"
        notes.append("baseline_" + base_problem)
    elif reference["state"] == "not_applicable":
        status = "NOT_COMPARABLE"
        notes.append("baseline_not_applicable")
    elif canonical(observed["value"]) == canonical(reference["value"]):
        status = "ALIGNED"
    else:
        matching = [r for r in intentions if canonical(r["value"]) == canonical(observed["value"])
                    and canonical(r["baseline_value"]) == canonical(reference["value"])]
        active = []
        expired = []
        for r in matching:
            issue = evidence_problem(r["evidence_id"], evidence, as_of)
            if issue:
                notes.append("rationale_" + issue + ":" + r["id"])
            elif as_of < day(r["valid_from"], r["id"]):
                notes.append("rationale_not_yet_valid:" + r["id"])
            elif as_of > day(r["review_on"], r["id"]):
                expired.append(r)
            else:
                active.append(r)
        if len(active) > 1:
            status = "UNKNOWN"
            notes.append("multiple_active_rationales")
            used = active
        elif active:
            status = "INTENTIONAL_DIFFERENCE"
            used = active
        elif expired:
            status = "EXPLANATION_REVIEW_DUE"
            notes.append("rationale_review_overdue")
            used = expired
        else:
            status = "UNEXPLAINED_DIFFERENCE"
            notes.append("rationale_values_mismatch" if intentions and not matching else "no_current_supported_rationale")
    questions = {
        "ALIGNED": "What behavioral test establishes that these equal recorded settings predict the intended outcome?",
        "INTENTIONAL_DIFFERENCE": "Does the documented difference still fit the testing purpose and its review date?",
        "UNEXPLAINED_DIFFERENCE": "Is this difference necessary, and what evidence establishes its effect on test representativeness?",
        "EXPLANATION_REVIEW_DUE": "Who will review the dated explanation and confirm or revise both expected values?",
        "UNKNOWN": "Which current artifact or clarification would resolve the diagnostic without guessing?",
        "NOT_APPLICABLE": "Does the recorded non-applicability remain appropriate for this service and environment?",
        "NOT_COMPARABLE": "Which alternative reference or behavior-based check makes this environment comparable?",
    }
    refs = {o.get("evidence_id") for o in (observed, reference) if o and o.get("evidence_id")}
    refs.update(r["evidence_id"] for r in intentions)
    return {"check_id": check["id"], "group": check["group"], "service": check["service"],
            "dimension": check["dimension"], "key": check["key"], "environment": env,
            "baseline_environment": baseline, "status": status, "observation": observed,
            "baseline_observation": reference, "diagnostics": sorted(set(notes)),
            "evidence_ids": sorted(refs), "rationales": intentions,
            "used_rationale_ids": [r["id"] for r in used], "question": questions[status],
            "impact_hypothesis": check["impact"], "owner_role": check["owner_role"],
            "effort_hours_assumption": check["effort_hours"]}


def analyze(packet):
    as_of, evidence, checks = validate(packet)
    rows = [compare(checks[c], env, packet, evidence, as_of) for c in sorted(checks)
            for env in sorted(packet["environments"]) if env != packet["baseline"]]
    counts = Counter(r["status"] for r in rows)
    comparable = sum(counts[s] for s in STATUSES[:4])
    return {"schema": VERSION, "label": packet["label"], "as_of": packet["as_of"],
            "input_sha256": hashlib.sha256(canonical(packet).encode()).hexdigest(),
            "limitation": LIMITATION, "baseline": packet["baseline"],
            "max_age_days_assumption": packet["max_age_days"],
            "coverage": {"total_comparisons": len(rows), "comparable": comparable,
                         "unknown": counts["UNKNOWN"], "not_applicable": counts["NOT_APPLICABLE"],
                         "not_comparable": counts["NOT_COMPARABLE"]},
            "counts": {s: counts[s] for s in STATUSES},
            "evidence_register": [evidence[k] for k in sorted(evidence)], "comparisons": rows,
            "follow_up": [r for r in rows if r["status"] not in
                          ("ALIGNED", "INTENTIONAL_DIFFERENCE", "NOT_APPLICABLE")]}


def cell(value):
    return html.escape(str(value), quote=True).replace("|", "&#124;").replace("`", "&#96;").replace("\r", " ").replace("\n", "<br>")


def observation_label(obs):
    if obs is None:
        return "MISSING"
    return canonical(obs["value"]) if obs["state"] == "observed" else obs["state"] + ": " + obs["reason"]


def markdown(report):
    lines = ["# Environment consistency assessment", "", cell(report["label"]), "",
             report["limitation"], "", f"As of {report['as_of']}; baseline: {cell(report['baseline'])}.",
             f"Canonical-input SHA-256: `{report['input_sha256']}`", "",
             "## Coverage (counts, not a readiness score)", "", cell(canonical(report["coverage"])), "",
             "## Environment comparison matrix", "",
             "| Check / service | Environment | Recorded value | Baseline value | Status | Evidence |",
             "|---|---|---|---|---|---|"]
    for r in report["comparisons"]:
        lines.append("| " + " | ".join(cell(v) for v in
                     (r["check_id"] + " / " + r["service"], r["environment"],
                      observation_label(r["observation"]), observation_label(r["baseline_observation"]),
                      r["status"], ", ".join(r["evidence_ids"]))) + " |")
    lines += ["", "## Follow-up worksheet", "",
              "Effort ranges and impacts are input assumptions, not measured costs or established consequences.", "",
              "| Check / environment | Diagnostic / question | Impact hypothesis | Proposed owner role | Hours range |",
              "|---|---|---|---|---|"]
    for r in report["follow_up"]:
        lines.append("| " + " | ".join(cell(v) for v in
                     (r["check_id"] + " / " + r["environment"], "; ".join(r["diagnostics"]) + " — " + r["question"],
                      r["impact_hypothesis"], r["owner_role"], r["effort_hours_assumption"])) + " |")
    lines += ["", "## Intentional-difference record worksheet", "",
              "| Check / environment | Rationale ID | Reason | Owner role | Valid from / review on | Used in decision |",
              "|---|---|---|---|---|---|"]
    for r in report["comparisons"]:
        for rationale in r["rationales"]:
            lines.append("| " + " | ".join(cell(v) for v in
                         (r["check_id"] + " / " + r["environment"], rationale["id"], rationale["reason"],
                          rationale["owner_role"], rationale["valid_from"] + " / " + rationale["review_on"],
                          rationale["id"] in r["used_rationale_ids"])) + " |")
    lines += ["", "## Supplied evidence register", "", "| ID | Kind | Captured | Locator (not fetched) |", "|---|---|---|---|"]
    for record in report["evidence_register"]:
        lines.append("| " + " | ".join(cell(record[k]) for k in ("id", "kind", "captured_on", "locator")) + " |")
    return "\n".join(lines) + "\n"


def load(path):
    require(path.stat().st_size <= 4_000_000, "input exceeds 4 MB")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(InputError("non-finite JSON number")))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output:
            require(args.output.resolve() != args.packet.resolve(), "output cannot replace input")
            require(not args.output.exists(), "output already exists; choose a new report path")
        report = analyze(load(args.packet))
        rendered = markdown(report) if args.format == "markdown" else json.dumps(report, indent=2, ensure_ascii=True) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as out:
                out.write(rendered)
        else:
            sys.stdout.write(rendered)
        return 0
    except (ValueError, TypeError, OSError, RecursionError, OverflowError) as exc:
        print(f"Input/report error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
