#!/usr/bin/env python3
"""Offline, vendor-neutral seasonal capacity planning. No network or scheduling."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import heapq
import io
import json
import math
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

VERSION = "uiowa.seasonal-capacity.v1"
Rate = tuple[Decimal, Decimal, Decimal] | None
ZERO = (Decimal(0),) * 3
PRESSURE = {"PRESSURE_SOME_ASSUMPTIONS", "PRESSURE_ALL_ASSUMPTIONS"}
ALLOWED_CHANGES = {
    "services": {"capacity_rps", "reserve_fraction"},
    "edges": {"calls_per_request"},
    "events": {"increments", "start", "end"},
    "maintenance": {"capacity_fraction", "start", "end"},
}


def keys(obj: Any, required: set[str], context: str) -> None:
    if not isinstance(obj, dict) or set(obj) != required:
        raise ValueError(f"{context}: expected fields {sorted(required)}")


def text(value: Any, context: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}: nonempty text required")


def number(value: Any, context: str) -> Decimal:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{context}: finite nonnegative number required (not boolean)")
    return Decimal(str(value))


def rate(value: Any, context: str = "range", fraction: bool = False) -> Rate:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{context}: use [low, typical, high] or null")
    result = tuple(number(v, context) for v in value)
    if not result[0] <= result[1] <= result[2] or (fraction and result[2] > 1):
        raise ValueError(f"{context}: unordered range or fraction outside [0,1]")
    return result


def instant(value: Any) -> datetime:
    text(value, "timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp: ISO-8601 with explicit UTC offset required") from exc
    if result.utcoffset() is None or result.microsecond:
        raise ValueError("timestamp: explicit offset and whole seconds required")
    return result.astimezone(timezone.utc)


def stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def window(record: dict) -> tuple[datetime, datetime]:
    start, end = instant(record["start"]), instant(record["end"])
    if start >= end:
        raise ValueError("window: end must be after start")
    return start, end


def index(records: Any, context: str) -> dict[str, dict]:
    if not isinstance(records, list):
        raise ValueError(f"{context}: array required")
    result = {}
    for row in records:
        if not isinstance(row, dict):
            raise ValueError(f"{context}: object rows required")
        text(row.get("id"), f"{context}.id")
        if row["id"] in result:
            raise ValueError(f"{context}: duplicate id {row['id']}")
        result[row["id"]] = row
    return result


def ordered_services(services: dict, edges: list[dict]) -> list[str]:
    degree = dict.fromkeys(services, 0)
    outgoing = {s: [] for s in services}
    seen = set()
    for edge in edges:
        pair = (edge["from"], edge["to"])
        if any(s not in services for s in pair) or pair in seen:
            raise ValueError("edge: missing service or duplicate service pair")
        seen.add(pair)
        degree[pair[1]] += 1
        outgoing[pair[0]].append(pair[1])
    ready = [s for s, count in degree.items() if count == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        source = heapq.heappop(ready)
        order.append(source)
        for target in outgoing[source]:
            degree[target] -= 1
            if degree[target] == 0:
                heapq.heappush(ready, target)
    if len(order) != len(services):
        raise ValueError("dependency cycle: model a finite effective call ratio instead")
    return order


def validate_core(packet: dict) -> tuple[dict, list[str]]:
    keys(packet, {"schema_version", "classification", "title", "period", "sources",
                  "services", "edges", "events", "maintenance", "options"}, "packet")
    if packet["schema_version"] != VERSION:
        raise ValueError("unsupported schema_version")
    if packet["classification"] not in {"SYNTHETIC", "PLANNING_INPUT"}:
        raise ValueError("classification: SYNTHETIC or PLANNING_INPUT required")
    text(packet["title"], "title")
    keys(packet["period"], {"start", "end"}, "period")
    first, last = window(packet["period"])
    sources = index(packet["sources"], "sources")
    for source in sources.values():
        keys(source, {"id", "kind", "locator", "note"}, "source")
        for name in ("kind", "locator", "note"):
            text(source[name], f"source.{name}")
        if source["kind"] not in {"synthetic", "observation", "interview", "contract", "assumption", "unavailable"}:
            raise ValueError("unknown source kind")
        if packet["classification"] == "SYNTHETIC" and source["kind"] != "synthetic":
            raise ValueError("synthetic packet must label every source synthetic")

    def evidence(row: dict) -> None:
        text(row["basis"], "basis")
        refs = row["source_refs"]
        if not isinstance(refs, list) or not refs or any(not isinstance(r, str) or r not in sources for r in refs):
            raise ValueError("source_refs: nonempty array of existing source IDs required")
        if len(set(refs)) != len(refs):
            raise ValueError("duplicate source reference")

    services = index(packet["services"], "services")
    if not services:
        raise ValueError("at least one service required")
    for service in services.values():
        keys(service, {"id", "group", "owner_role", "basis", "baseline_rps", "capacity_rps",
                       "reserve_fraction", "source_refs"}, "service")
        if service["group"] not in {"ESS", "RIS", "IAM", "SHARED", "EXTERNAL"}:
            raise ValueError("unknown group")
        text(service["owner_role"], "service.owner_role")
        evidence(service)
        rate(service["baseline_rps"], "baseline_rps")
        rate(service["capacity_rps"], "capacity_rps")
        if number(service["reserve_fraction"], "reserve_fraction") >= 1:
            raise ValueError("reserve_fraction must be less than one")
    edges = index(packet["edges"], "edges")
    for edge in edges.values():
        keys(edge, {"id", "from", "to", "calls_per_request", "basis", "source_refs"}, "edge")
        text(edge["from"], "edge.from")
        text(edge["to"], "edge.to")
        rate(edge["calls_per_request"], "calls_per_request")
        evidence(edge)
    order = ordered_services(services, packet["edges"])
    for collection in ("events", "maintenance"):
        rows = index(packet[collection], collection)
        for row in rows.values():
            extra = {"title", "increments"} if collection == "events" else {"service", "capacity_fraction"}
            keys(row, {"id", "start", "end", "owner_role", "basis", "source_refs"} | extra, collection)
            start, end = window(row)
            if start < first or end > last:
                raise ValueError(f"{collection}: window outside planning period")
            text(row["owner_role"], "owner_role")
            evidence(row)
            if collection == "events":
                text(row["title"], "event.title")
                if not isinstance(row["increments"], dict) or not row["increments"]:
                    raise ValueError("event.increments: nonempty service-to-range map required")
                for sid, value in row["increments"].items():
                    if sid not in services:
                        raise ValueError("event refers to missing service")
                    rate(value, "event increment")
            else:
                if not isinstance(row["service"], str) or row["service"] not in services:
                    raise ValueError("maintenance refers to missing service")
                rate(row["capacity_fraction"], "capacity_fraction", fraction=True)
    return services, order


def apply_option(packet: dict, option: dict) -> dict:
    keys(option, {"id", "title", "owner_role", "effort_hours", "prerequisites", "validation_needed", "source_refs", "changes"}, "option")
    for name in ("title", "owner_role"):
        text(option[name], f"option.{name}")
    rate(option["effort_hours"], "effort_hours")
    refs = option["source_refs"]
    sources = index(packet["sources"], "sources")
    if not isinstance(refs, list) or not refs or any(not isinstance(r, str) or r not in sources for r in refs):
        raise ValueError("option.source_refs: existing source IDs required")
    if len(set(refs)) != len(refs):
        raise ValueError("option: duplicate source reference")
    for name in ("prerequisites", "validation_needed"):
        if not isinstance(option[name], list) or not option[name]:
            raise ValueError(f"option.{name}: nonempty array required")
        for value in option[name]:
            text(value, name)
    if not isinstance(option["changes"], list) or not option["changes"]:
        raise ValueError("option.changes: nonempty array required")
    result = copy.deepcopy(packet)
    seen = set()
    for change in option["changes"]:
        keys(change, {"collection", "id", "field", "value"}, "change")
        for name in ("collection", "id", "field"):
            text(change[name], f"change.{name}")
        collection, rid, field = change["collection"], change["id"], change["field"]
        if collection not in ALLOWED_CHANGES or field not in ALLOWED_CHANGES[collection]:
            raise ValueError("unsupported option change")
        target = index(result[collection], collection)
        key = (collection, rid, field)
        if rid not in target or key in seen:
            raise ValueError("option: missing target or duplicate field change")
        seen.add(key)
        target[rid][field] = copy.deepcopy(change["value"])
    for collection, rid, _ in seen:
        row = index(result[collection], collection)[rid]
        row["source_refs"] = sorted(set(row["source_refs"]) | set(refs))
    validate_core(result)
    return result


def add(a: Rate, b: Rate) -> Rate:
    return None if a is None or b is None else tuple(x + y for x, y in zip(a, b))


def multiply(a: Rate, b: Rate) -> Rate:
    if a == ZERO or b == ZERO:
        return ZERO
    return None if a is None or b is None else tuple(x * y for x, y in zip(a, b))


def plain(value: Rate) -> list[float] | None:
    if value is None:
        return None
    result = [float(v) for v in value]
    if not all(math.isfinite(v) for v in result):
        raise ValueError("calculated range exceeds finite JSON number representation")
    return result


def classify(load: Rate, capacity: Rate) -> str:
    if load is None:
        return "UNKNOWN_DEMAND"
    if load == ZERO:
        return "NO_MODELED_DEMAND"
    if capacity is None:
        return "UNKNOWN_CAPACITY"
    if load[0] > capacity[2]:
        return "PRESSURE_ALL_ASSUMPTIONS"
    if load[2] > capacity[0]:
        return "PRESSURE_SOME_ASSUMPTIONS"
    if load[2] == capacity[0]:
        return "AT_ASSUMED_BOUNDARY"
    return "WITHIN_ASSUMED_ENVELOPE"


def evaluate(packet: dict, scenario_id: str) -> dict:
    services, order = validate_core(packet)
    begin, end = window(packet["period"])
    timed = packet["events"] + packet["maintenance"]
    times = sorted({begin, end} | {instant(r[k]) for r in timed for k in ("start", "end")})
    rows, calendar = [], []
    pressure_clock = Decimal(0)
    pressure_service = Decimal(0)
    unknown_service = Decimal(0)
    excess = ZERO
    for start, stop in zip(times, times[1:]):
        active = [r for r in packet["events"] if instant(r["start"]) <= start < instant(r["end"])]
        maintenance = [r for r in packet["maintenance"] if instant(r["start"]) <= start < instant(r["end"])]
        hours = Decimal(int((stop - start).total_seconds())) / 3600
        flows = {s: {f"baseline:{s}": rate(v["baseline_rps"])} for s, v in services.items()}
        refs = {s: set(v["source_refs"]) for s, v in services.items()}
        for event in active:
            for sid, value in event["increments"].items():
                flows[sid][f"event:{event['id']}:{sid}"] = rate(value)
                refs[sid].update(event["source_refs"])
        for sid in order:
            for edge in packet["edges"]:
                if edge["from"] != sid:
                    continue
                target = edge["to"]
                for origin, contribution in flows[sid].items():
                    term = multiply(contribution, rate(edge["calls_per_request"]))
                    flows[target][origin] = add(flows[target].get(origin, ZERO), term)
                refs[target].update(refs[sid])
                refs[target].update(edge["source_refs"])
        pressured, unknown = [], []
        for sid in sorted(services):
            service = services[sid]
            load = ZERO
            for contribution in flows[sid].values():
                load = add(load, contribution)
            reserve = Decimal(1) - number(service["reserve_fraction"], "reserve_fraction")
            capacity = multiply(rate(service["capacity_rps"]), (reserve,) * 3)
            outages = [r for r in maintenance if r["service"] == sid]
            notes = []
            if len(outages) > 1:
                capacity = None
                notes.append("Overlapping maintenance: combined capacity is unknown; reconcile the assumptions.")
            elif outages:
                capacity = multiply(capacity, rate(outages[0]["capacity_fraction"], fraction=True))
            for outage in outages:
                refs[sid].update(outage["source_refs"])
                notes.append(f"Maintenance overlaps this window: {outage['id']}")
            status = classify(load, capacity)
            if status in PRESSURE:
                pressured.append(sid)
                pressure_service += hours
            if load is None or capacity is None:
                unknown.append(sid)
                unknown_service += hours
            headroom = None if load is None or capacity is None else (
                capacity[0] - load[2], capacity[1] - load[1], capacity[2] - load[0])
            deficit = None if headroom is None else tuple(max(Decimal(0), -v) for v in reversed(headroom))
            if deficit is not None:
                excess = add(excess, multiply(deficit, (hours * 3600,) * 3))
            rows.append({"scenario_id": scenario_id, "start": stamp(start), "end": stamp(stop),
                         "hours": float(hours), "service_id": sid, "group": service["group"],
                         "owner_role": service["owner_role"], "offered_rps": plain(load),
                         "usable_capacity_rps": plain(capacity), "headroom_rps": plain(headroom),
                         "excess_service_rps": plain(deficit), "status": status, "active_event_ids": sorted(r["id"] for r in active),
                         "maintenance_ids": sorted(r["id"] for r in outages),
                         "contributions_rps": {k: plain(v) for k, v in sorted(flows[sid].items()) if v != ZERO},
                         "source_refs": sorted(refs[sid]), "notes": notes})
        if pressured:
            pressure_clock += hours
        calendar.append({"scenario_id": scenario_id, "start": stamp(start), "end": stamp(stop),
                         "hours": float(hours), "active_event_ids": sorted(r["id"] for r in active),
                         "maintenance_ids": sorted(r["id"] for r in maintenance),
                         "pressure_service_ids": pressured, "unknown_service_ids": unknown})
    return {"id": scenario_id, "pressure_clock_hours": float(pressure_clock),
            "pressure_service_hours": float(pressure_service), "unknown_service_hours": float(unknown_service),
            "excess_service_request_equivalents": plain(excess),
            "calendar": calendar, "capacity": rows}


def analyze(packet: dict) -> dict:
    validate_core(packet)
    options = index(packet["options"], "options")
    if "baseline" in options:
        raise ValueError("option id baseline is reserved for the unchanged scenario")
    scenarios = [evaluate(packet, "baseline")]
    for oid in sorted(options):
        scenario = evaluate(apply_option(packet, options[oid]), oid)
        scenario["option"] = copy.deepcopy(options[oid])
        scenarios.append(scenario)
    digest = hashlib.sha256(json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return {"schema_version": VERSION, "classification": packet["classification"],
            "title": packet["title"], "input_sha256": digest, "digest_kind": "canonical-json-utf8-sha256",
            "interpretation": "Calculated planning assumptions, not measured throughput, outages, maturity or scheduling.",
            "intervals": "[low, typical, high]; bounds are not probabilities; null is unknown, not zero.",
            "excess_interpretation": "Positive offered-minus-usable service-call ranges integrated over time; excludes unknown rows; not observed errors, queue lengths or unique users.",
            "sources": copy.deepcopy(packet["sources"]), "scenarios": scenarios}


def cell(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return "" if value is None else value


def csv_text(rows: list[dict], fields: list[str]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: cell(row.get(key)) for key in fields})
    return output.getvalue()


def md(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def render(report: dict) -> str:
    lines = [f"# {md(report['title'])}", "", f"**{report['classification']} — planning calculation only.**",
             report["interpretation"], "", report["intervals"], "",
             "Pressure clock-hours count the union of modeled pressure windows once. Service-hours sum across resources; neither is predicted downtime.", "",
             "Excess service-request equivalents integrate modeled positive (offered - usable) rates over time. They exclude unknown rows and count service calls, not users, failed requests or queue length.", "",
             "| Scenario | Pressure clock-hours | Pressure service-hours | Unknown service-hours | Typical excess equivalents |",
             "|---|---:|---:|---:|---:|"]
    for scenario in report["scenarios"]:
        lines.append(f"| {md(scenario['id'])} | {scenario['pressure_clock_hours']:g} | {scenario['pressure_service_hours']:g} | {scenario['unknown_service_hours']:g} | {scenario['excess_service_request_equivalents'][1]:g} |")
    for scenario in report["scenarios"]:
        lines += ["", f"## {md(scenario['id'])}", ""]
        if "option" in scenario:
            option = scenario["option"]
            lines += [md(option["title"]), "", f"Owner role: {md(option['owner_role'])}. Assumed person-hours: {md(option['effort_hours'])}.",
                      "Prerequisites: " + md("; ".join(option["prerequisites"])),
                      "Evidence still needed: " + md("; ".join(option["validation_needed"])),
                      "Option source IDs: " + md(", ".join(option["source_refs"])), ""]
        lines += ["| UTC window (half-open) | Events | Maintenance | Pressure resources | Unknown resources |", "|---|---|---|---|---|"]
        for row in scenario["calendar"]:
            lines.append("| " + " | ".join(md(v) for v in (row["start"] + " / " + row["end"], ", ".join(row["active_event_ids"]) or "none", ", ".join(row["maintenance_ids"]) or "none", ", ".join(row["pressure_service_ids"]) or "none", ", ".join(row["unknown_service_ids"]) or "none")) + " |")
    lines += ["", "## Source register", "", "| ID | Kind | Locator | Note |", "|---|---|---|---|"]
    for source in report["sources"]:
        lines.append("| " + " | ".join(md(source[k]) for k in ("id", "kind", "locator", "note")) + " |")
    lines += ["", "Detailed per-service ranges, ownership, source references and root-call contributions are retained in report.json and capacity.csv.",
              "A within-envelope result does not establish latency, availability, quality, staffing readiness or external-provider commitment.", ""]
    return "\n".join(lines)


def write_outputs(report: dict, destination: Path) -> None:
    rows, calendar, options = [], [], []
    for scenario in report["scenarios"]:
        calendar.extend(scenario["calendar"])
        option = scenario.get("option", {})
        options.append({"scenario_id": scenario["id"], "pressure_clock_hours": scenario["pressure_clock_hours"],
                        "pressure_service_hours": scenario["pressure_service_hours"], "unknown_service_hours": scenario["unknown_service_hours"],
                        "excess_service_request_equivalents": scenario["excess_service_request_equivalents"], "owner_role": option.get("owner_role"), "effort_hours": option.get("effort_hours"),
                        "prerequisites": option.get("prerequisites"), "validation_needed": option.get("validation_needed"),
                        "source_refs": option.get("source_refs")})
        for original in scenario["capacity"]:
            row = copy.deepcopy(original)
            for name in ("offered_rps", "usable_capacity_rps", "headroom_rps", "excess_service_rps"):
                values = row.pop(name)
                for idx, bound in enumerate(("low", "typical", "high")):
                    row[f"{name}_{bound}"] = None if values is None else values[idx]
            rows.append(row)
    files = {"report.json": json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
             "report.md": render(report), "capacity.csv": csv_text(rows, list(rows[0])),
             "calendar.csv": csv_text(calendar, list(calendar[0])), "options.csv": csv_text(options, list(options[0]))}
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (destination / name).write_text(content, encoding="utf-8")


def unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load(path: Path) -> dict:
    def invalid(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object, parse_constant=invalid)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = analyze(load(args.input))
        write_outputs(report, args.out)
    except (ValueError, OSError, TypeError, OverflowError) as exc:
        print(f"Input/output error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"classification": report["classification"], "scenarios": len(report["scenarios"]),
                      "input_sha256": report["input_sha256"], "output": str(args.out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
