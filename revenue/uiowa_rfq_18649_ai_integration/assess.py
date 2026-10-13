#!/usr/bin/env python3
"""Offline, vendor-neutral architecture tradeoffs. No network or production actions."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Any

VERSION = "1.0"
PATTERNS = {"synchronous_assist", "asynchronous_job", "retrieval_assist"}
OWNERS = ("integration", "support", "data", "evaluation", "change")
PORTABILITY = ("request_response_contract", "prompt_export", "evaluation_replay", "adapter_swap", "data_export")


class InputError(ValueError):
    """A malformed input, as distinct from missing assessment evidence."""


def obj(value: Any, where: str) -> dict:
    if not isinstance(value, dict):
        raise InputError(f"{where}: expected object")
    return value


def seq(value: Any, where: str, nonempty: bool = False) -> list:
    if not isinstance(value, list) or (nonempty and not value):
        raise InputError(f"{where}: expected {'nonempty ' if nonempty else ''}list")
    return value


def text(value: Any, where: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{where}: expected nonblank string")
    return value


def number(value: Any, where: str, maximum: float | None = None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{where}: expected nonnegative number or null")
    try:
        finite = math.isfinite(value)
    except (OverflowError, ValueError):
        finite = False
    if not finite or value < 0 or (maximum is not None and value > maximum):
        raise InputError(f"{where}: out of range")
    return float(value)


def strings(value: Any, where: str, nullable: bool = False) -> list[str] | None:
    if value is None and nullable:
        return None
    result = [text(v, where) for v in seq(value, where)]
    if len(result) != len(set(result)):
        raise InputError(f"{where}: duplicate value")
    return result


def interval(value: Any, where: str) -> dict:
    value = obj(value, where)
    if set(value) != {"low", "high"}:
        raise InputError(f"{where}: interval requires exactly low and high")
    low, high = (number(value[k], f"{where}.{k}") for k in ("low", "high"))
    if low is not None and high is not None and low > high:
        raise InputError(f"{where}: low exceeds high")
    return {"low": low, "high": high}


def total(rows: Any, field: str, where: str, nonempty: bool = False) -> dict:
    rows = seq(rows, where, nonempty)
    parts = []
    seen = set()
    for i, row in enumerate(rows):
        row = obj(row, f"{where}[{i}]")
        name = text(row.get("name"), f"{where}[{i}].name")
        if name in seen:
            raise InputError(f"{where}: duplicate item {name}")
        seen.add(name)
        parts.append(interval(row.get(field), f"{where}[{i}].{field}"))
    complete = all(p["low"] is not None and p["high"] is not None for p in parts)
    try:
        low = math.fsum(p["low"] for p in parts) if complete else None
        high = math.fsum(p["high"] for p in parts) if complete else None
        subtotal = math.fsum(p["low"] for p in parts if p["low"] is not None)
    except OverflowError as exc:
        raise InputError(f"{where}: aggregate exceeds finite numeric range") from exc
    return {"low": low, "high": high, "complete": complete,
            "known_low_subtotal": subtotal,
            "missing_items": [r["name"] for r, p in zip(rows, parts)
                              if p["low"] is None or p["high"] is None]}


def check_budget(metric: dict, budget: float | None) -> str:
    if budget is None or metric["low"] is None or metric["high"] is None:
        return "unknown"
    if metric["low"] > budget:
        return "conflict"
    if metric["high"] > budget:
        return "conditional"
    return "supported_by_inputs"


def availability(rows: Any, independence: Any, expected_window: str | None) -> dict:
    rows = seq(rows, "response_dependencies", True)
    if not isinstance(independence, bool):
        raise InputError("independence_assumed: expected boolean")
    probabilities = []
    comparable = expected_window is not None
    seen = set()
    for row in rows:
        row = obj(row, "response_dependency")
        name = text(row.get("name"), "response_dependency.name")
        if name in seen:
            raise InputError("response_dependencies: duplicate name")
        seen.add(name)
        probabilities.append(number(row.get("availability"), "availability", 1))
        window = text(row.get("window"), "response_dependency.window", nullable=True)
        comparable = comparable and window == expected_window
    complete = None not in probabilities and comparable
    known = [p for p in probabilities if p is not None]
    # Frechet bounds apply to the intersection of component-up events, without
    # an independence assumption. Unknown components retain an unknown lower bound.
    lower = max(0.0, math.fsum(known) - (len(known) - 1)) if complete else None
    upper = min(known) if known and comparable else None
    return {"lower": lower, "upper": upper, "complete": complete,
            "independent_estimate": math.prod(known) if complete and independence else None,
            "independence_assumed": independence, "comparable_windows": comparable,
            "expected_window": expected_window,
            "scope": "response path only; not AI completion or semantic correctness"}


def check_availability(metric: dict, target: float | None) -> str:
    if target is None:
        return "unknown"
    if metric["upper"] is not None and metric["upper"] < target - 1e-12:
        return "conflict"
    if not metric["complete"]:
        return "unknown"
    if metric["lower"] >= target - 1e-12:
        return "supported_by_inputs"
    return "conditional"


def assess_case(case: dict, evidence: dict) -> dict:
    case = obj(case, "case")
    case_id = text(case.get("id"), "case.id")
    req = obj(case.get("requirements"), f"{case_id}.requirements")
    for key in ("response_budget_ms", "completion_deadline_ms", "monthly_maintenance_hours", "migration_budget_hours"):
        number(req.get(key), f"requirements.{key}")
    target = number(req.get("response_availability_target"), "response_availability_target", 1)
    window = text(req.get("availability_window"), "availability_window", nullable=True)
    zones = strings(req.get("allowed_zones"), "allowed_zones", nullable=True)
    retention = number(req.get("max_retention_days"), "max_retention_days")
    required = strings(req.get("required_capabilities"), "required_capabilities")
    must_continue = req.get("core_must_continue_without_ai")
    if must_continue is not None and not isinstance(must_continue, bool):
        raise InputError("core_must_continue_without_ai: expected boolean or null")
    result = {"id": case_id, "title": text(case.get("title"), "case.title"),
              "recommendation_id": text(case.get("recommendation_id"), "recommendation_id"),
              "requirements": req, "alternatives": []}
    seen = set()
    for alt in seq(case.get("alternatives"), "alternatives", True):
        alt = obj(alt, "alternative")
        alt_id = text(alt.get("id"), "alternative.id")
        if alt_id in seen:
            raise InputError(f"{case_id}: duplicate alternative {alt_id}")
        seen.add(alt_id)
        pattern = alt.get("pattern")
        if not isinstance(pattern, str) or pattern not in PATTERNS:
            raise InputError(f"{alt_id}: unrecognized pattern")
        for key in ("suitable_when", "tradeoffs", "change_option"):
            text(alt.get(key), f"{alt_id}.{key}")
        refs = strings(alt.get("evidence_refs"), f"{alt_id}.evidence_refs")
        if any(ref not in evidence for ref in refs):
            raise InputError(f"{alt_id}: unresolved evidence reference")
        latency = total(alt.get("response_stages"), "ms", "response_stages", True)
        completion = total(alt.get("completion_stages"), "ms", "completion_stages", pattern == "asynchronous_job")
        if pattern != "asynchronous_job" and alt["completion_stages"]:
            raise InputError("completion_stages are separate only for asynchronous_job")
        if pattern != "asynchronous_job":
            completion = dict(latency)
        if not isinstance(alt.get("latency_basis"), str) or alt["latency_basis"] not in {"planning_envelope", "measured_bound"}:
            raise InputError("latency_basis must be planning_envelope or measured_bound; do not sum percentiles")
        uptime = availability(alt.get("response_dependencies"), alt.get("independence_assumed"), window)
        integration = total(alt.get("integration_tasks"), "hours", "integration_tasks", True)
        maintenance = total(alt.get("maintenance_tasks"), "hours_per_month", "maintenance_tasks", True)
        migration = total(alt.get("migration_tasks"), "hours", "migration_tasks", True)
        for task_key in ("integration_tasks", "maintenance_tasks", "migration_tasks"):
            for task in alt[task_key]:
                text(task.get("owner_role"), f"{task_key}.owner_role", nullable=True)
        offered = strings(alt.get("capabilities"), "capabilities")
        missing_capabilities = sorted(set(required) - set(offered))
        checks = {"evidence_coverage": "supported_by_inputs" if refs else "unknown",
                  "response_latency": check_budget(latency, req.get("response_budget_ms")),
                  "completion_deadline": check_budget(completion, req.get("completion_deadline_ms")),
                  "response_availability": check_availability(uptime, target),
                  "maintenance_capacity": check_budget(maintenance, req.get("monthly_maintenance_hours")),
                  "migration_effort": check_budget(migration, req.get("migration_budget_hours")),
                  "capability_match": "conflict" if missing_capabilities else "supported_by_inputs"}
        # Null deadline is not applicable for sync cases; async needs a completion budget.
        if pattern != "asynchronous_job" and req.get("completion_deadline_ms") is None:
            checks["completion_deadline"] = "not_applicable"
        flows = seq(alt.get("data_flows"), "data_flows", True)
        flow_results = []
        flow_ids = set()
        for flow in flows:
            flow = obj(flow, "data_flow")
            fid = text(flow.get("id"), "data_flow.id")
            if fid in flow_ids:
                raise InputError("duplicate data_flow.id")
            flow_ids.add(fid)
            for key in ("source", "destination", "payload", "minimization"):
                text(flow.get(key), f"data_flow.{key}", nullable=(key == "minimization"))
            zone = text(flow.get("zone"), "data_flow.zone", nullable=True)
            days = number(flow.get("retention_days"), "retention_days")
            zone_status = "unknown" if zones is None or zone is None else (
                "supported_by_inputs" if zone in zones else "conflict")
            retention_status = "unknown" if retention is None or days is None else (
                "supported_by_inputs" if days <= retention else "conflict")
            flow_results.append({**flow, "zone_status": zone_status, "retention_status": retention_status})
            checks[f"data_zone:{fid}"] = zone_status
            checks[f"retention:{fid}"] = retention_status
        owners = obj(alt.get("owners"), "owners")
        absent_owners = [key for key in OWNERS if text(owners.get(key), f"owners.{key}", True) is None]
        unowned_tasks = [f"{key}:{t['name']}" for key in ("integration_tasks", "maintenance_tasks", "migration_tasks")
                         for t in alt[key] if t.get("owner_role") is None]
        checks["ownership"] = "unknown" if absent_owners or unowned_tasks else "supported_by_inputs"
        portable = obj(alt.get("portability"), "portability")
        for key in PORTABILITY:
            item = obj(portable.get(key), f"portability.{key}")
            state = item.get("state")
            if not isinstance(state, str) or state not in {"demonstrated", "asserted", "unknown", "not_applicable"}:
                raise InputError(f"portability.{key}: invalid state")
            text(item.get("note"), f"portability.{key}.note")
            proof = strings(item.get("evidence_refs"), f"portability.{key}.evidence_refs")
            if any(ref not in evidence for ref in proof) or (state == "demonstrated" and not proof):
                raise InputError(f"portability.{key}: missing or unresolved evidence")
            checks[f"portability:{key}"] = {"demonstrated": "supported_by_inputs", "asserted": "conditional",
                                            "unknown": "unknown", "not_applicable": "not_applicable"}[state]
        degraded = obj(alt.get("degraded_mode"), "degraded_mode")
        mode = degraded.get("behavior")
        if not isinstance(mode, str) or mode not in {"core_continues", "manual_queue", "blocks_core", "unknown"}:
            raise InputError("degraded_mode.behavior: invalid value")
        text(degraded.get("note"), "degraded_mode.note")
        tested = degraded.get("tested")
        if tested is not None and not isinstance(tested, bool):
            raise InputError("degraded_mode.tested: expected boolean or null")
        fallback_refs = strings(degraded.get("evidence_refs"), "degraded_mode.evidence_refs")
        if any(ref not in evidence for ref in fallback_refs) or (tested is True and not fallback_refs):
            raise InputError("degraded_mode: missing or unresolved evidence")
        checks["degraded_mode"] = ("unknown" if must_continue is None else "not_applicable")
        if must_continue is True:
            checks["degraded_mode"] = ("conflict" if mode == "blocks_core" else "unknown" if mode == "unknown"
                                       else "conditional" if mode == "manual_queue" or tested is not True
                                       else "supported_by_inputs")
        status = next((name for name in ("conflict", "unknown", "conditional") if name in checks.values()),
                      "supported_by_inputs")
        questions = [f"Resolve {name}: {state}; retain an observation, owner decision or test record."
                     for name, state in checks.items() if state in {"unknown", "conditional", "conflict"}]
        result["alternatives"].append({**alt, "checks": checks, "status": status, "questions": questions,
             "latency_ms": latency, "completion_ms": completion, "response_availability": uptime,
             "integration_hours": integration, "maintenance_hours_per_month": maintenance,
             "migration_hours": migration, "missing_capabilities": missing_capabilities,
             "missing_owners": absent_owners, "unowned_tasks": unowned_tasks, "data_flows": flow_results})
    return result


def assess(document: Any) -> dict:
    document = obj(document, "document")
    if document.get("schema_version") != VERSION:
        raise InputError(f"schema_version must be {VERSION}")
    if not isinstance(document.get("synthetic"), bool):
        raise InputError("synthetic: expected boolean")
    basis = text(document.get("basis"), "basis")
    evidence = obj(document.get("evidence"), "evidence")
    for ref, item in evidence.items():
        text(ref, "evidence id")
        item = obj(item, f"evidence.{ref}")
        text(item.get("locator"), "evidence.locator")
        text(item.get("note"), "evidence.note")
        if not isinstance(item.get("kind"), str) or item["kind"] not in {"synthetic", "retained", "assumption"}:
            raise InputError("evidence.kind must be synthetic, retained or assumption")
    if not document["synthetic"] and any(e["kind"] == "synthetic" for e in evidence.values()):
        raise InputError("synthetic evidence cannot be relabeled as nonsynthetic")
    cases = [assess_case(c, evidence) for c in seq(document.get("cases"), "cases", True)]
    if len({c["id"] for c in cases}) != len(cases):
        raise InputError("duplicate case id")
    return {"schema_version": VERSION, "synthetic": document["synthetic"], "basis": basis,
            "caveat": "Design assessment only. Input-supported is not production readiness, a University finding, or vendor selection.",
            "evidence": evidence, "cases": cases}


def no_duplicates(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise InputError(f"invalid JSON numeric constant: {value}")


def load(raw: bytes) -> dict:
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f"invalid UTF-8 JSON: {exc}") from exc


def display(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    if isinstance(value, float):
        return f"{value:.8g}"
    return str(value)


def md(value: Any) -> str:
    return display(value).replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", " / ").replace("<", "&lt;").replace(">", "&gt;")


def span(value: dict) -> str:
    return f"{display(value['low'])}–{display(value['high'])}"


def markdown(report: dict) -> str:
    lines = ["# AI integration and portability assessment", "",
             f"**SYNTHETIC: {str(report['synthetic']).upper()}** — {md(report['basis'])}", "", report["caveat"], "",
             f"Input SHA-256: `{report.get('input_sha256', 'not supplied')}`", "",
             "Latency totals are serial planning envelopes, not sums of percentiles. Availability bounds assume a consistent observation window, not independence; only an explicitly requested product estimate uses independence. Response availability never means AI correctness or completed-job availability.", ""]
    for case in report["cases"]:
        lines.extend([f"## {md(case['id'])}: {md(case['title'])}", "", f"Recommendation: {md(case['recommendation_id'])}", "",
                      "| Alternative | Pattern | Status | Response ms | Completion ms | Integration h | Maintenance h/month | Migration h |",
                      "|---|---|---|---|---|---|---|---|"])
        for a in case["alternatives"]:
            lines.append("| " + " | ".join(md(x) for x in [a['id'], a['pattern'], a['status'], span(a['latency_ms']),
                         span(a['completion_ms']), span(a['integration_hours']), span(a['maintenance_hours_per_month']), span(a['migration_hours'])]) + " |")
        for a in case["alternatives"]:
            u = a["response_availability"]
            lines.extend(["", f"### {md(a['id'])}", "", f"Suitable when: {md(a['suitable_when'])}", "",
                f"Tradeoffs: {md(a['tradeoffs'])}", "", f"Change option: {md(a['change_option'])}", "",
                f"Response availability bound: {display(u['lower'])}–{display(u['upper'])}; independent estimate: {display(u['independent_estimate'])}.", "",
                f"Degraded behavior: {md(a['degraded_mode']['behavior'])}; {md(a['degraded_mode']['note'])}", "",
                "| Check | State |", "|---|---|"])
            lines.extend(f"| {md(k)} | {md(v)} |" for k, v in a["checks"].items())
            lines.extend(["", "| Data movement | Zone | Retention days | Minimization |", "|---|---|---|---|"])
            lines.extend(f"| {md(f['source'])} → {md(f['destination'])}: {md(f['payload'])} | {md(f['zone'])} | {md(f['retention_days'])} | {md(f['minimization'])} |" for f in a["data_flows"])
            lines.extend(["", "Ownership: " + "; ".join(f"{k}={md(a['owners'].get(k))}" for k in OWNERS), "",
                          "Evidence: " + ", ".join(md(ref) for ref in a["evidence_refs"]), "", "Investigation backlog:"])
            lines.extend(f"- {md(q)}" for q in a["questions"])
            if not a["questions"]:
                lines.append("- Validate all assumptions in the actual environment before selecting a design.")
    lines.extend(["", "## Evidence register", "", "| ID | Kind | Locator | Note |", "|---|---|---|---|"])
    lines.extend(f"| {md(k)} | {md(e['kind'])} | {md(e['locator'])} | {md(e['note'])} |" for k, e in report["evidence"].items())
    return "\n".join(lines) + "\n"


def csv_text(report: dict) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["case_id", "recommendation_id", "alternative_id", "pattern", "synthetic", "status", "check", "check_state", "input_sha256"])
    for case in report["cases"]:
        for alt in case["alternatives"]:
            for key, state in alt["checks"].items():
                row = [case['id'], case['recommendation_id'], alt['id'], alt['pattern'], report['synthetic'], alt['status'], key, state, report.get('input_sha256', '')]
                # Preserve labels while preventing a spreadsheet from evaluating them.
                writer.writerow(["'" + str(v) if str(v).lstrip().startswith(("=", "+", "-", "@")) else v for v in row])
    return stream.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        raw = args.input.read_bytes()
        report = assess(load(raw))
        report["input_sha256"] = hashlib.sha256(raw).hexdigest()
        args.out.mkdir(parents=True, exist_ok=True)
        payloads = {"assessment.json": json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    "assessment.md": markdown(report), "checks.csv": csv_text(report)}
        for name, content in payloads.items():
            destination = args.out / name
            if destination.resolve() == args.input.resolve():
                raise InputError("output would overwrite the input")
        for name, content in payloads.items():
            (args.out / name).write_text(content, encoding="utf-8", newline="")
    except (InputError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(f"Assessed {len(report['cases'])} cases / {sum(len(c['alternatives']) for c in report['cases'])} alternatives; input {report['input_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
