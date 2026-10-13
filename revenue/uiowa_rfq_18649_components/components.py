#!/usr/bin/env python3
"""UIOWA-056: offline, evidence-qualified component lifecycle assessment.

Python 3.10+, standard library only. No network, scanner, or dependency execution.
A result describes supplied records; it does not establish runtime exposure.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import math
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

VERSION = "uiowa.components.v1"
MAX_BYTES = 4 * 1024 * 1024
LIMIT = ("Supplied-record assessment only; not a vulnerability scan, authenticity "
         "verification, compliance verdict, or finding about the University of Iowa. "
         "No advisory records does not mean no vulnerabilities. Not-observed exposure "
         "does not prove absence. Effort estimates are preparation assumptions.")


class InputError(ValueError):
    """The supplied record cannot be interpreted without guessing."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InputError(message)


def fields(obj: Any, names: str, label: str) -> None:
    require(isinstance(obj, dict), f"{label}: expected object")
    require(set(obj) == set(names.split()), f"{label}: expected fields {names}")


def text(value: Any, label: str, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    require(isinstance(value, str) and bool(value.strip()) and len(value) <= 2000,
            f"{label}: expected nonempty text <=2000 characters")
    require(not any(ord(c) < 32 and c not in "\t\r\n" for c in value),
            f"{label}: unsupported control character")


def day(value: Any, label: str, nullable: bool = False) -> date | None:
    if nullable and value is None:
        return None
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None,
            f"{label}: expected YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise InputError(f"{label}: invalid calendar date") from exc


def choice(value: Any, allowed: str, label: str) -> None:
    require(isinstance(value, str) and value in allowed.split(),
            f"{label}: expected one of {allowed}")


def records(value: Any, label: str) -> dict[str, dict]:
    require(isinstance(value, list) and len(value) <= 10000, f"{label}: expected bounded array")
    indexed = {}
    for row in value:
        require(isinstance(row, dict) and "id" in row, f"{label}: missing id")
        text(row["id"], label + ".id")
        require(row["id"] not in indexed, f"{label}: duplicate id {row['id']}")
        indexed[row["id"]] = row
    return indexed


def refs(value: Any, available: dict, label: str, nonempty: bool = False) -> None:
    require(isinstance(value, list) and all(isinstance(x, str) for x in value),
            f"{label}: expected reference array")
    require(len(value) == len(set(value)), f"{label}: repeated reference")
    require(not nonempty or bool(value), f"{label}: requires at least one reference")
    require(all(x in available for x in value), f"{label}: unresolved reference")


def validate(doc: dict) -> tuple[date, dict, dict, dict]:
    fields(doc, "schema_version as_of max_evidence_age_days horizon_days services evidence components", "root")
    require(doc["schema_version"] == VERSION, "root: unsupported schema_version")
    as_of = day(doc["as_of"], "as_of")
    for key in ("max_evidence_age_days", "horizon_days"):
        require(type(doc[key]) is int and 0 <= doc[key] <= 3650, key + ": expected integer 0..3650")
    services = records(doc["services"], "services")
    components = records(doc["components"], "components")
    evidence = records(doc["evidence"], "evidence")
    for s in services.values():
        fields(s, "id name group", "service")
        text(s["name"], "service.name")
        choice(s["group"], "ESS RIS IAM", "service.group")
    for e in evidence.values():
        fields(e, "id kind observed_on locator component_ids advisory_id", "evidence")
        choice(e["kind"], "inventory support advisory exposure closure exception update", "evidence.kind")
        require(day(e["observed_on"], "evidence.observed_on") <= as_of, "future evidence")
        text(e["locator"], "evidence.locator")
        refs(e["component_ids"], components, "evidence.component_ids", True)
        if e["kind"] in ("advisory", "exposure", "closure", "exception"):
            text(e["advisory_id"], "evidence.advisory_id")
            for cid in e["component_ids"]:
                require(e["advisory_id"] in records(components[cid].get("advisories"), "advisories"),
                        "evidence: advisory not present in scoped component")
        else:
            require(e["advisory_id"] is None, "non-advisory evidence: advisory_id must be null")

    def evidence_refs(ids: Any, kind: str, cid: str, aid: str | None = None, since: date | None = None) -> None:
        refs(ids, evidence, f"{cid}.{kind}_evidence")
        for eid in ids:
            e = evidence[eid]
            require(e["kind"] == kind and cid in e["component_ids"],
                    f"{cid}: evidence {eid} has wrong kind or component scope")
            require(e["advisory_id"] == aid, f"{cid}: evidence {eid} has wrong advisory scope")
            require(since is None or day(e["observed_on"], eid) >= since,
                    f"{cid}: disposition evidence predates advisory intake")

    for c in components.values():
        fields(c, "id name version services owner_role inherited support inventory_evidence review_due_on last_update_on advisories maintenance", "component")
        cid = c["id"]
        text(c["name"], "component.name")
        text(c["version"], "component.version")
        text(c["owner_role"], "component.owner_role", True)
        require(type(c["inherited"]) is bool, "component.inherited: expected boolean")
        refs(c["services"], services, "component.services", True)
        evidence_refs(c["inventory_evidence"], "inventory", cid)
        day(c["review_due_on"], "review_due_on", True)
        updated = day(c["last_update_on"], "last_update_on", True)
        require(updated is None or updated <= as_of, "future last_update_on")
        s = c["support"]
        fields(s, "state ends_on evidence", "support")
        choice(s["state"], "supported unsupported unknown", "support.state")
        day(s["ends_on"], "support.ends_on", True)
        evidence_refs(s["evidence"], "support", cid)
        m = c["maintenance"]
        fields(m, "change effort_low_days effort_high_days coordination_notes", "maintenance")
        text(m["change"], "maintenance.change")
        text(m["coordination_notes"], "maintenance.coordination_notes")
        lo, hi = m["effort_low_days"], m["effort_high_days"]
        require((lo is None) == (hi is None), "effort: supply both bounds or neither")
        if lo is not None:
            require(all(type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 100000 for x in (lo, hi))
                    and lo <= hi, "effort: expected finite ordered nonnegative bounds")
        for a in records(c["advisories"], "advisories").values():
            fields(a, "id reported_on applicability applicability_evidence exposure exposure_evidence disposition owner_role due_on exception_until disposition_evidence", "advisory")
            require(day(a["reported_on"], "advisory.reported_on") <= as_of, "future advisory")
            choice(a["applicability"], "affected not_affected unknown", "applicability")
            choice(a["exposure"], "confirmed not_observed unknown", "exposure")
            choice(a["disposition"], "open investigating resolved accepted_risk", "disposition")
            text(a["owner_role"], "advisory.owner_role", True)
            day(a["due_on"], "advisory.due_on", True)
            day(a["exception_until"], "advisory.exception_until", True)
            evidence_refs(a["applicability_evidence"], "advisory", cid, a["id"])
            evidence_refs(a["exposure_evidence"], "exposure", cid, a["id"])
            kind = {"resolved": "closure", "accepted_risk": "exception"}.get(a["disposition"])
            if kind:
                evidence_refs(a["disposition_evidence"], kind, cid, a["id"], day(a["reported_on"], "reported_on"))
            else:
                require(a["disposition_evidence"] == [], "open advisory: disposition_evidence must be empty")
            require(a["disposition"] == "accepted_risk" or a["exception_until"] is None,
                    "exception_until applies only to accepted_risk")
    return as_of, services, components, evidence


def assess(doc: dict) -> dict:
    as_of, services, components, evidence = validate(doc)
    max_age, horizon = doc["max_evidence_age_days"], doc["horizon_days"]

    def quality(ids: list[str]) -> str:
        if not ids:
            return "missing"
        return "current" if all((as_of - day(evidence[x]["observed_on"], x)).days <= max_age
                                for x in ids) else "stale"

    rows, advisory_rows, roadmap = [], [], []
    for cid, c in sorted(components.items()):
        reasons: dict[str, int] = {}
        q = quality(c["support"]["evidence"])
        declared = c["support"]["state"]
        end = day(c["support"]["ends_on"], "ends_on", True)
        state = declared if q == "current" else "unknown"
        if state == "unsupported" and end is not None and end >= as_of:
            state = "unknown"
            reasons["reconcile_conflicting_support_record"] = 3
        if state == "supported" and end is not None:
            remaining = (end - as_of).days
            state = "unsupported" if remaining < 0 else "ending_soon" if remaining <= horizon else "supported"
        if state == "unknown":
            reasons["establish_current_support_evidence"] = 3
        elif state == "unsupported":
            reasons["plan_supported_maintenance_path"] = 2
        elif state == "ending_soon":
            reasons["plan_before_support_ends"] = 2
        elif end is None:
            reasons["establish_support_horizon"] = 3
        inventory = quality(c["inventory_evidence"])
        if inventory != "current":
            reasons["refresh_inventory_evidence"] = 3
        if c["owner_role"] is None:
            reasons["assign_inherited_owner" if c["inherited"] else "establish_owner"] = 2
        due = day(c["review_due_on"], "review_due_on", True)
        if due is None:
            reasons["establish_review_cadence"] = 3
        elif due < as_of:
            reasons["perform_overdue_component_review"] = 2
        for a in sorted(c["advisories"], key=lambda a: a["id"]):
            app_q = quality(a["applicability_evidence"])
            exp_q = quality(a["exposure_evidence"])
            app = a["applicability"] if app_q == "current" else "unknown"
            exp = a["exposure"] if exp_q == "current" else "unknown"
            disposition = a["disposition"]
            disp_q = quality(a["disposition_evidence"])
            until = day(a["exception_until"], "exception_until", True)
            if disposition == "resolved":
                disposition = "documented_closure" if disp_q == "current" else "unverified_closure"
            elif disposition == "accepted_risk":
                disposition = ("recorded_exception_current" if disp_q == "current" and
                               a["owner_role"] is not None and until is not None and until >= as_of
                               else "expired_exception" if until is not None and until < as_of
                               else "unverified_exception")
            advisory_due = day(a["due_on"], "due_on", True)
            completed = disposition == "documented_closure"
            excepted = disposition == "recorded_exception_current"
            conflict = app == "not_affected" and exp == "confirmed"
            overdue = bool(advisory_due and advisory_due < as_of and not completed and not excepted)
            if conflict:
                reasons["reconcile_applicability_exposure_conflict"] = 1
            if not completed:
                if app == "unknown":
                    reasons["establish_advisory_applicability"] = 2
                if app == "affected" and exp == "unknown":
                    reasons["establish_exposure_context"] = 2
                if app == "affected" and exp == "confirmed" and not excepted:
                    reasons["review_reported_exposure"] = 1
                if disposition in ("unverified_closure", "unverified_exception", "expired_exception"):
                    reasons["verify_advisory_disposition"] = 2
                if a["owner_role"] is None:
                    reasons["establish_advisory_owner"] = 2
                if overdue:
                    reasons["review_overdue_advisory"] = 2
                if excepted and (until - as_of).days <= horizon:
                    reasons["review_exception_before_expiry"] = 2
            advisory_rows.append({"component_id": cid, "advisory_id": a["id"],
                "reported_on": a["reported_on"], "reported_applicability": a["applicability"],
                "qualified_applicability": app, "applicability_evidence_quality": app_q,
                "reported_exposure": a["exposure"], "qualified_reported_exposure": exp,
                "exposure_evidence_quality": exp_q, "record_disposition": disposition,
                "disposition_evidence_quality": disp_q, "owner_role": a["owner_role"],
                "due_on": a["due_on"], "exception_until": a["exception_until"],
                "overdue": overdue, "conflicting_records": conflict,
                "evidence_ids": sorted(set(a["applicability_evidence"] + a["exposure_evidence"] + a["disposition_evidence"]))})
        service_ids = sorted(c["services"])
        rows.append({"component_id": cid, "name": c["name"], "version": c["version"],
            "service_ids": service_ids, "groups": sorted({services[s]["group"] for s in service_ids}),
            "owner_role": c["owner_role"], "inherited": c["inherited"],
            "support_declared": declared, "support_state": state, "support_evidence_quality": q,
            "support_ends_on": c["support"]["ends_on"], "inventory_evidence_quality": inventory,
            "review_due_on": c["review_due_on"], "last_update_on": c["last_update_on"],
            "advisory_record_count": len(c["advisories"]),
            "evidence_ids": sorted(set(c["support"]["evidence"] + c["inventory_evidence"]))})
        if reasons:
            roadmap.append({"maintenance_id": "maint:" + cid, "component_id": cid,
                "priority": min(reasons.values()), "service_ids": service_ids,
                "owner_role": c["owner_role"], "reasons": sorted(reasons), **c["maintenance"]})
    roadmap.sort(key=lambda row: (row["priority"], row["component_id"]))
    estimated = [r for r in roadmap if r["effort_low_days"] is not None]
    summary = {"component_count": len(rows), "service_count": len(services),
        "support_counts": dict(sorted(Counter(r["support_state"] for r in rows).items())),
        "advisory_record_count": len(advisory_rows), "maintenance_item_count": len(roadmap),
        "unestimated_item_count": len(roadmap) - len(estimated),
        "known_effort_low_days": sum(r["effort_low_days"] for r in estimated),
        "known_effort_high_days": sum(r["effort_high_days"] for r in estimated)}
    return {"schema_version": VERSION, "as_of": doc["as_of"], "limitations": LIMIT,
        "parameters": {"max_evidence_age_days": max_age, "horizon_days": horizon},
        "summary": summary, "components": rows, "advisories": advisory_rows,
        "roadmap": roadmap, "services": [services[x].copy() for x in sorted(services)],
        "evidence": [{**evidence[x], "component_ids": sorted(evidence[x]["component_ids"])} for x in sorted(evidence)]}


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def safe_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, list):
        value = "; ".join(str(x) for x in value)
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def csv_bytes(rows: list[dict], columns: list[str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows([safe_cell(row.get(key)) for key in columns] for row in rows)
    return output.getvalue().encode("utf-8")


def md(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    return html.escape(str(value)).replace("|", "&#124;").replace("`", "&#96;").replace("\n", " ").replace("\r", " ")


def bundle(doc: dict) -> dict[str, bytes]:
    report = assess(doc)
    payload = {"assessment.json": json_bytes(report)}
    columns = {
        "components": "component_id name version service_ids groups owner_role inherited support_declared support_state support_evidence_quality support_ends_on inventory_evidence_quality review_due_on last_update_on advisory_record_count evidence_ids",
        "advisories": "component_id advisory_id reported_on reported_applicability qualified_applicability applicability_evidence_quality reported_exposure qualified_reported_exposure exposure_evidence_quality record_disposition disposition_evidence_quality owner_role due_on exception_until overdue conflicting_records evidence_ids",
        "roadmap": "maintenance_id component_id priority service_ids owner_role reasons change effort_low_days effort_high_days coordination_notes",
        "evidence": "id kind observed_on locator component_ids advisory_id",
        "services": "id name group"}
    for name, keys in columns.items():
        payload[name + ".csv"] = csv_bytes(report[name], keys.split())
    lines = ["# Component maintenance assessment", "", "As of " + report["as_of"], "", LIMIT, "",
        "Priority 1 = reconcile reported exposure/conflicts; 2 = time-sensitive maintenance/review; 3 = establish evidence. These are workflow priorities, not severity or maturity scores.", "",
        "| Component | Services | Support | Inventory evidence | Owner |", "|---|---|---|---|---|"]
    for r in report["components"]:
        lines.append("| " + " | ".join(md(x) for x in (r["component_id"], ", ".join(r["service_ids"]), r["support_state"], r["inventory_evidence_quality"], r["owner_role"])) + " |")
    lines.extend(["", "## Maintenance decisions", "", "Shared components appear once. Known effort totals exclude unknown estimates, not assume them zero.", ""])
    for r in report["roadmap"]:
        lines.extend(["### " + md(r["maintenance_id"]), "", "Priority: " + str(r["priority"]),
            "Owner role: " + md(r["owner_role"]), "Services: " + md(", ".join(r["service_ids"])),
            "Reasons: " + md(", ".join(r["reasons"])), "Proposed practice change: " + md(r["change"]),
            "Effort range (person-days): " + md(r["effort_low_days"]) + " to " + md(r["effort_high_days"]),
            "Coordination: " + md(r["coordination_notes"]), ""])
    payload["summary.md"] = ("\n".join(lines) + "\n").encode("utf-8")
    payload["manifest.json"] = json_bytes({"schema_version": VERSION,
        "canonical_input_sha256": hashlib.sha256(json_bytes(doc)).hexdigest(),
        "files": {n: hashlib.sha256(b).hexdigest() for n, b in sorted(payload.items())}})
    return payload


def load(path: Path) -> dict:
    def pairs(items: list[tuple]) -> dict:
        obj = {}
        for key, value in items:
            require(key not in obj, "duplicate JSON key: " + key)
            obj[key] = value
        return obj
    def reject_constant(value: str) -> None:
        raise InputError("nonfinite JSON value: " + value)
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, "input exceeds 4 MiB")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise InputError("invalid UTF-8 JSON: " + str(exc)) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", required=True, type=Path, help="new directory; never overwrites an existing bundle")
    args = parser.parse_args(argv)
    try:
        files = bundle(load(args.input))
        args.out.mkdir(parents=False, exist_ok=False)
        for name, data in files.items():
            with (args.out / name).open("xb") as stream:
                stream.write(data)
        print("Wrote supplied-record assessment: " + str(args.out))
        return 0
    except (InputError, OSError, ValueError, OverflowError) as exc:
        print("Assessment not completed: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
