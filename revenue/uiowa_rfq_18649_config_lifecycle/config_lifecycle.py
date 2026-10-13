#!/usr/bin/env python3
"""Offline configuration-lifecycle evidence analysis. Never executes configuration."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

VERSION = "uiowa-config-lifecycle/v1"
ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,95}$")


class InputError(ValueError):
    """Malformed input, distinct from valid records containing evidence gaps."""


def fail(message: str) -> None:
    raise InputError(message)


def obj(value: Any, fields: str, where: str) -> dict:
    if not isinstance(value, dict) or set(value) != set(fields.split()):
        fail(f"{where}: expected exactly these fields: {fields}")
    return value


def text(value: Any, where: str, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if not isinstance(value, str) or not value.strip():
        fail(f"{where}: nonempty text required")


def ident(value: Any, where: str) -> None:
    if not isinstance(value, str) or not ID.fullmatch(value):
        fail(f"{where}: invalid identifier")


def choice(value: Any, options: str, where: str) -> None:
    if not isinstance(value, str) or value not in options.split():
        fail(f"{where}: expected one of {options}")


def sequence(value: Any, where: str) -> list:
    if not isinstance(value, list):
        fail(f"{where}: list required")
    return value


def references(value: Any, where: str, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    for item in sequence(value, where):
        ident(item, where)
    if len(set(value)) != len(value):
        fail(f"{where}: duplicate reference")


def day(value: Any, where: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        fail(f"{where}: ISO date YYYY-MM-DD required")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise InputError(f"{where}: invalid date") from exc


def unique(rows: list, where: str) -> dict:
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            fail(f"{where}: objects required")
        ident(row.get("id"), where)
        if row["id"] in result:
            fail(f"{where}: duplicate id {row['id']}")
        result[row["id"]] = row
    return result


def loads(raw: str) -> dict:
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                fail(f"duplicate JSON key: {key}")
            out[key] = value
        return out
    def constant(value):
        fail(f"non-finite JSON number: {value}")
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid JSON at line {exc.lineno}, column {exc.colno}") from exc


def validate(data: Any) -> None:
    obj(data, "schema synthetic as_of evidence_max_age_days inventory_coverage sources components exercises", "packet")
    if data["schema"] != VERSION or type(data["synthetic"]) is not bool:
        fail("packet: invalid schema or synthetic flag")
    choice(data["inventory_coverage"], "complete partial unknown", "inventory_coverage")
    as_of = day(data["as_of"], "as_of")
    horizon = data["evidence_max_age_days"]
    if type(horizon) is not int or horizon < 0:
        fail("evidence_max_age_days: nonnegative integer required")
    for source in unique(sequence(data["sources"], "sources"), "sources").values():
        obj(source, "id kind observed_on locator excerpt", "source")
        choice(source["kind"], "artifact interview", "source.kind")
        if day(source["observed_on"], "source.observed_on") > as_of:
            fail("source observed after as_of")
        text(source["locator"], "source.locator")
        text(source["excerpt"], "source.excerpt")
    for c in unique(sequence(data["components"], "components"), "components").values():
        obj(c, "id name group state owner_role owner_evidence revision config_evidence recipe_mode recipe_evidence dependencies inputs steps checks changes retirement_evidence", "component")
        text(c["name"], "component.name")
        choice(c["group"], "ESS RIS IAM shared", "component.group")
        choice(c["state"], "active retiring retired", "component.state")
        choice(c["recipe_mode"], "manual automated mixed unknown", "component.recipe_mode")
        for key in ("owner_role", "revision"):
            text(c[key], key, nullable=True)
        for key in ("owner_evidence", "config_evidence", "recipe_evidence", "retirement_evidence", "checks"):
            references(c[key], key)
        references(c["dependencies"], "dependencies", nullable=True)
        if c["inputs"] is not None:
            for r in unique(sequence(c["inputs"], "inputs"), "inputs").values():
                obj(r, "id version evidence", "input")
                text(r["version"], "input.version", nullable=True)
                references(r["evidence"], "input.evidence")
        for step in unique(sequence(c["steps"], "steps"), "steps").values():
            obj(step, "id instruction evidence", "step")
            text(step["instruction"], "step.instruction")
            references(step["evidence"], "step.evidence")
        for change in unique(sequence(c["changes"], "changes"), "changes").values():
            obj(change, "id revision on record_evidence review_evidence review_outcome", "change")
            text(change["revision"], "change.revision")
            if day(change["on"], "change.on") > as_of:
                fail("change after as_of")
            references(change["record_evidence"], "change.record_evidence")
            references(change["review_evidence"], "change.review_evidence")
            choice(change["review_outcome"], "accepted pending rejected unknown", "change.review_outcome")
    for e in unique(sequence(data["exercises"], "exercises"), "exercises").values():
        obj(e, "id target on scope manifest executed_steps checks evidence", "exercise")
        ident(e["target"], "exercise.target")
        if day(e["on"], "exercise.on") > as_of:
            fail("exercise after as_of")
        choice(e["scope"], "from_scratch in_place_repair walkthrough unknown", "exercise.scope")
        for key in ("manifest", "executed_steps", "checks"):
            if not isinstance(e[key], dict):
                fail(f"exercise.{key}: object required")
            for cid in e[key]:
                ident(cid, f"exercise.{key}")
        for version in e["manifest"].values():
            text(version, "manifest revision")
        for steps in e["executed_steps"].values():
            references(steps, "executed_steps")
        for outcome in e["checks"].values():
            choice(outcome, "pass fail unknown", "check outcome")
        references(e["evidence"], "exercise.evidence")


def digest(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def closure(target: str, components: dict) -> dict:
    """Iterative DFS: dependency-first order; unresolved nodes never disappear."""
    colors, order, problems, nodes = {}, [], [], set()
    stack = [(target, False)]
    while stack:
        cid, leaving = stack.pop()
        if leaving:
            colors[cid] = 2
            order.append(cid)
            continue
        if colors.get(cid) == 2:
            continue
        if colors.get(cid) == 1:
            problems.append(f"dependency_cycle:{cid}")
            continue
        nodes.add(cid)
        if cid not in components:
            problems.append(f"dependency_not_in_inventory:{cid}")
            colors[cid] = 2
            continue
        colors[cid] = 1
        c = components[cid]
        if c["dependencies"] is None:
            problems.append(f"dependency_inventory_unknown:{cid}")
        if c["state"] == "retired":
            problems.append(f"dependency_retired:{cid}")
        stack.append((cid, True))
        for dep in reversed(sorted(c["dependencies"] or [])):
            stack.append((dep, False))
    return {"members": sorted(nodes), "dependency_first_order": order if not problems else [], "problems": sorted(set(problems))}


def analyze(data: dict) -> dict:
    validate(data)
    sources = {s["id"]: s for s in data["sources"]}
    components = {c["id"]: c for c in data["components"]}
    as_of = day(data["as_of"], "as_of")
    horizon = data["evidence_max_age_days"]

    def support(ids: list[str]) -> str:
        if not ids:
            return "unknown"
        if any(sid not in sources for sid in ids):
            return "unresolved_reference"
        fresh = [sources[sid] for sid in ids if (as_of - day(sources[sid]["observed_on"], "observed_on")).days <= horizon]
        if any(s["kind"] == "artifact" for s in fresh):
            return "documented"
        return "reported_only" if fresh else "stale_only"

    def criterion(status: str, evidence: list[str], question: str) -> dict:
        return {"status": status, "evidence": sorted(set(evidence)), "follow_up": question if status != "documented" else ""}

    local = {}
    for cid, c in sorted(components.items()):
        current = [x for x in c["changes"] if x["revision"] == c["revision"]]
        change_refs = [r for x in current for k in ("record_evidence", "review_evidence") for r in x[k]]
        accepted = [x for x in current if x["review_outcome"] == "accepted" and support(x["record_evidence"]) == "documented" and support(x["review_evidence"]) == "documented"]
        changed_after = [x for x in c["changes"] if current and x["on"] > max(t["on"] for t in current) and x["revision"] != c["revision"]]
        if changed_after or (accepted and any(x["review_outcome"] == "rejected" for x in current)):
            change_status = "conflicting_records"
        else:
            change_status = "documented" if accepted else "unknown"
        recipe_refs = c["recipe_evidence"] + [r for step in c["steps"] for r in step["evidence"]]
        recipe_status = support(c["recipe_evidence"])
        if not c["steps"]:
            recipe_status = "unknown"
        elif recipe_status == "documented":
            statuses = [support(s["evidence"]) for s in c["steps"]]
            recipe_status = next((s for s in statuses if s != "documented"), "documented")
        inputs = c["inputs"]
        inputs_status = "unknown" if inputs is None else "documented"
        for inp in inputs or []:
            if not inp["version"] or support(inp["evidence"]) != "documented":
                inputs_status = "unresolved_inputs"
        local[cid] = {
            "ownership": criterion(support(c["owner_evidence"]) if c["owner_role"] else "unknown", c["owner_evidence"], "Which accountable role can maintain and reconstruct this configuration?"),
            "configuration": criterion(support(c["config_evidence"]) if c["revision"] else "unknown", c["config_evidence"], "Locate the exact current configuration revision and its retained description."),
            "change_trace": criterion(change_status, change_refs + [r for x in changed_after for r in x["record_evidence"]], "Reconcile current revision, change record and substantive review disposition."),
            "recipe": criterion(recipe_status, recipe_refs, "Ask another operator to follow each step; replace recollection with usable records."),
            "inputs": criterion(inputs_status, [r for i in inputs or [] for r in i["evidence"]], "Identify versions and retrieval records for every required external input; unknown inventory is not an empty inventory.")}
    results = []
    for cid, c in sorted(components.items()):
        graph = closure(cid, components)
        blockers = list(graph["problems"])
        for member in graph["members"]:
            for key, value in local.get(member, {}).items():
                if value["status"] != "documented":
                    blockers.append(f"{member}:{key}:{value['status']}")
        if data["inventory_coverage"] != "complete":
            blockers.append("collection_scope_not_complete")
        checks_required = c["checks"]
        if not checks_required:
            blockers.append(f"{cid}:business_checks_unknown")
        exercises = []
        for e in sorted((e for e in data["exercises"] if e["target"] == cid), key=lambda e: (e["on"], e["id"])):
            reasons = []
            manifest = {m: components[m]["revision"] for m in graph["members"] if m in components}
            current_manifest = not graph["problems"] and e["manifest"] == manifest and all(manifest.values())
            if not current_manifest:
                reasons.append("manifest_does_not_match_current_dependency_closure")
            if set(e["executed_steps"]) != set(manifest):
                reasons.append("step_component_set_does_not_match_manifest")
            for member in graph["members"]:
                if member in components:
                    introduced = [x["on"] for x in components[member]["changes"] if x["revision"] == components[member]["revision"]]
                    if introduced and e["on"] < min(introduced):
                        reasons.append(f"exercise_predates_current_revision:{member}")
            if e["scope"] != "from_scratch":
                reasons.append("not_a_from_scratch_rebuild")
            if (as_of - day(e["on"], "exercise.on")).days > horizon:
                reasons.append("exercise_outside_selected_evidence_window")
            if support(e["evidence"]) != "documented":
                reasons.append("exercise_has_no_current_artifact_support")
            # An evidence record cannot predate the exercise it purports to document.
            if not any(sid in sources and sources[sid]["kind"] == "artifact" and sources[sid]["observed_on"] >= e["on"] for sid in e["evidence"]):
                reasons.append("exercise_artifact_predates_exercise_or_is_absent")
            for member in graph["members"]:
                if member in components:
                    expected = {s["id"] for s in components[member]["steps"]}
                    if not expected or set(e["executed_steps"].get(member, [])) != expected:
                        reasons.append(f"step_execution_incomplete_or_mismatched:{member}")
            if not checks_required or any(e["checks"].get(check) != "pass" for check in checks_required):
                reasons.append("business_verification_incomplete_or_failed")
            if any(value == "fail" for value in e["checks"].values()):
                reasons.append("reported_check_failure")
            exercises.append({"id": e["id"], "on": e["on"], "current_manifest": bool(current_manifest), "qualifying": not reasons, "reasons": sorted(set(reasons)), "evidence": e["evidence"]})
        current_exercises = [e for e in exercises if e["current_manifest"]]
        latest = [e for e in current_exercises if e["on"] == max(x["on"] for x in current_exercises)] if current_exercises else []
        if c["state"] == "retired":
            rebuild_status = "not_applicable_retired"
        elif blockers:
            rebuild_status = "preparation_gaps"
        elif latest and all(e["qualifying"] for e in latest):
            rebuild_status = "demonstrated_current_snapshot"
        elif any(e["qualifying"] for e in latest):
            rebuild_status = "conflicting_latest_exercises"
        else:
            rebuild_status = "current_rebuild_not_demonstrated"
        consumers = sorted(k for k, v in components.items() if cid in (v["dependencies"] or []) and v["state"] != "retired")
        retirement_status = "not_applicable" if c["state"] == "active" else "documented" if support(c["retirement_evidence"]) == "documented" and not consumers and data["inventory_coverage"] == "complete" else "follow_up_required"
        results.append({"id": cid, "name": c["name"], "group": c["group"], "state": c["state"], "owner_role": c["owner_role"], "revision": c["revision"], "recipe_mode": c["recipe_mode"], "criteria": local[cid], "dependency_plan": graph, "rebuild_status": rebuild_status, "blockers": sorted(set(blockers)), "exercises": exercises, "retirement": {"status": retirement_status, "observed_active_consumers": consumers, "evidence": c["retirement_evidence"]}})
    return {"schema": VERSION, "synthetic": data["synthetic"], "as_of": data["as_of"], "evidence_max_age_days": horizon, "inventory_coverage": data["inventory_coverage"], "input_sha256": digest(data), "notice": "Supplied-record analysis, not source authentication, a live rebuild, a maturity score, or a University finding.", "orphan_exercises": sorted(e["id"] for e in data["exercises"] if e["target"] not in components), "sources": [{**s, "excerpt_sha256": hashlib.sha256(s["excerpt"].encode()).hexdigest()} for s in sorted(data["sources"], key=lambda x: x["id"])], "components": results}


def markdown(report: dict) -> str:
    def esc(s):
        return str(s if s is not None else "UNKNOWN").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|").replace("\r", "").replace("\n", "<br>")
    lines = ["# Configuration lifecycle assessment", "", "**SYNTHETIC REHEARSAL**" if report["synthetic"] else "**SUPPLIED RECORDS — ANALYST REVIEW REQUIRED**", "", report["notice"], "", f"As of {report['as_of']}; selected evidence window: {report['evidence_max_age_days']} days; inventory coverage: {report['inventory_coverage']}.", f"Input SHA-256: `{report['input_sha256']}`", "", "|Component|Group|Method|Current rebuild evidence|", "|---|---|---|---|"]
    for c in report["components"]:
        lines.append("|" + "|".join(esc(c[k]) for k in ("id", "group", "recipe_mode", "rebuild_status")) + "|")
    for c in report["components"]:
        lines += ["", f"## {c['id']} — {esc(c['name'])}", f"Owner: {esc(c['owner_role'])}; revision: {esc(c['revision'])}.", "", "Dependency-first order: " + (", ".join(c["dependency_plan"]["dependency_first_order"]) or "UNRESOLVED"), "", "|Criterion|Status|Evidence IDs|Follow-up|", "|---|---|---|---|"]
        for key, value in c["criteria"].items():
            lines.append("|" + "|".join(esc(v) for v in (key, value["status"], ", ".join(value["evidence"]) or "UNKNOWN", value["follow_up"])) + "|")
        lines += ["", "Preparation blockers: " + ("; ".join(c["blockers"]) or "None identified within the supplied inventory."), "Retirement: " + c["retirement"]["status"] + "; observed active consumers: " + (", ".join(c["retirement"]["observed_active_consumers"]) or "none in supplied inventory"), ""]
        for e in c["exercises"]:
            lines.append(f"Exercise {e['id']} ({e['on']}): " + ("qualifying supplied record" if e["qualifying"] else "; ".join(e["reasons"])) + ". Evidence: " + ", ".join(e["evidence"]))
    lines += ["", "## Source lookup", "", "Hashes below identify excerpt bytes, not original documents or authenticity.", ""]
    for source in report["sources"]:
        lines += [f"### {source['id']}", f"{source['kind']}; observed {source['observed_on']}; locator: {esc(source['locator'])}", f"Excerpt: {esc(source['excerpt'])}", f"Excerpt SHA-256: `{source['excerpt_sha256']}`", ""]
    if report["orphan_exercises"]:
        lines += ["## Unresolved exercise targets", ", ".join(report["orphan_exercises"])]
    return "\n".join(lines) + "\n"


def worksheet(report: dict) -> str:
    """CSV for editing; JSON stays the lossless machine representation."""
    stream = io.StringIO(newline="")
    out = csv.writer(stream)
    out.writerow(["component_id", "group", "criterion", "status", "evidence_ids_json", "follow_up", "proposed_owner_role", "analyst_notes", "improvement_option", "effort_assumption", "adoption_condition"])
    options = {
        "ownership": ("Name a maintaining role and backup operator in the retained record", "1–2 staff hours per component", "Role holders can confirm responsibilities"),
        "configuration": ("Retain the current description with an immutable revision reference", "2–4 staff hours per component", "Current configuration can be described without collecting secrets"),
        "change_trace": ("Link change rationale, reviewed revision and review outcome", "1–3 staff hours per sampled change", "Change owner and reviewer records are available"),
        "recipe": ("Have a second operator annotate the existing manual or automated recipe", "2–6 staff hours per component", "A disposable exercise environment and maintaining operator are available"),
        "inputs": ("Record retrievable input versions and their retention locations", "2–4 staff hours per component", "Inventory scope is agreed; artifacts can be retained appropriately"),
        "dependencies": ("Reconcile declared dependencies and resolve missing nodes or cycles", "2–6 staff hours per component", "Upstream owners can describe required reconstruction order"),
        "rebuild": ("Record a from-scratch exercise with exact versions, steps and behavior checks", "4–12 staff hours per small component", "Isolated resources and agreed behavior checks exist; costs excluded"),
        "retirement": ("Reconcile disposition evidence with all observed active consumers", "2–4 staff hours per component", "Dependency owners and retention requirements can be consulted"),
    }
    for c in report["components"]:
        extra = {
            "dependencies": {"status": "documented" if not c["dependency_plan"]["problems"] else "unresolved", "evidence": [], "follow_up": "; ".join(c["dependency_plan"]["problems"])},
            "rebuild": {"status": c["rebuild_status"], "evidence": [sid for e in c["exercises"] for sid in e["evidence"]], "follow_up": "Reconcile exercise reasons and current dependency closure; retain business-function checks."},
            "retirement": {"status": c["retirement"]["status"], "evidence": c["retirement"]["evidence"], "follow_up": "Reconcile retirement records with observed consumers: " + ", ".join(c["retirement"]["observed_active_consumers"])}
        }
        for key, value in {**c["criteria"], **extra}.items():
            row = [c["id"], c["group"], key, value["status"], json.dumps(value["evidence"]), value["follow_up"], c["owner_role"] or "UNKNOWN", "", *options[key]]
            out.writerow(["'" + str(v) if str(v).lstrip().startswith(("=", "+", "-", "@")) else v for v in row])
    return stream.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="new directory for JSON, Markdown and editable CSV")
    args = parser.parse_args(argv)
    try:
        report = analyze(loads(args.packet.read_text(encoding="utf-8")))
        rendered = {"report.json": json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", "report.md": markdown(report), "worksheet.csv": worksheet(report)}
        args.out.mkdir(parents=True, exist_ok=False)
        for name, content in rendered.items():
            with (args.out / name).open("x", encoding="utf-8", newline="") as handle:
                handle.write(content)
        print(f"components={len(report['components'])} input_sha256={report['input_sha256']}")
        return 0
    except (InputError, OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
