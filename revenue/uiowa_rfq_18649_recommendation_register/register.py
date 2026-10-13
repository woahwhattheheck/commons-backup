#!/usr/bin/env python3
"""UIOWA-038: editable draft recommendation register and lossless projections.

Offline data processing only. This does not assess evidence, choose recommendations,
score maturity, infer implementation feasibility, or authorize any external action.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import sys
from pathlib import Path
from typing import Any

SCHEMA = "uiowa-rfq-18649-recommendation-register/v1"
DRAFT = "DRAFT_NON_AUTHORITATIVE"
GROUPS = ("ESS", "RIS", "IAM")
DIMENSIONS = ("software", "security", "deployment", "ai_readiness")
PHASES = ("0-90", "90-180", "180+")
MAX_BYTES = 2 * 1024 * 1024
META = ("schema_id", "register_id", "record_status", "data_classification", "provenance", "assumptions")
FINDING_FIELDS = ("finding_id", "group", "dimension", "statement", "evidence_refs")
REC_FIELDS = ("recommendation_id", "practice_change", "scope", "finding_ids", "impact", "effort", "skills", "dependencies", "owner_role", "outcome_measure", "maturity_step", "phase", "assumptions")


class RegisterError(ValueError):
    """A precise input or interchange error, not an assessment conclusion."""


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RegisterError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value: str) -> Any:
    raise RegisterError(f"non-finite JSON literal: {value}")


def loads(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_object, parse_constant=_constant)
    except (ValueError, RecursionError) as exc:
        raise RegisterError(f"invalid JSON: {exc}") from exc


def dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise RegisterError(f"not JSON data: {exc}") from exc


def _keys(value: Any, fields: tuple[str, ...], at: str) -> None:
    if not isinstance(value, dict) or set(value) != set(fields):
        raise RegisterError(f"{at}: expected exactly {', '.join(fields)}")


def _text(value: Any, at: str, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str) or not value.strip():
        raise RegisterError(f"{at}: expected nonblank text" + (" or null" if nullable else ""))
    try:
        value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise RegisterError(f"{at}: invalid Unicode") from exc
    if any(ord(c) < 32 and c not in "\n\r\t" for c in value):
        raise RegisterError(f"{at}: unsupported control character")


def _texts(value: Any, at: str) -> None:
    if not isinstance(value, list):
        raise RegisterError(f"{at}: expected a list, not a delimited string")
    for item in value:
        _text(item, at)
    if len(value) != len(set(value)):
        raise RegisterError(f"{at}: duplicate entry")


def _choice(value: Any, choices: tuple[str, ...], at: str, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str) or value not in choices:
        raise RegisterError(f"{at}: expected one of {choices}" + (" or null" if nullable else ""))


def _number(value: Any, at: str, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        valid = False
    if not valid:
        raise RegisterError(f"{at}: expected a finite nonnegative number, not a boolean")


def normalize(value: Any) -> dict[str, Any]:
    """Validate shape without manufacturing unknowns or resolving missing links.

    All arrays retain caller order. Dangling references are preserved and reported
    separately so incomplete drafts can still be edited and exported honestly.
    """
    _keys(value, META + ("findings", "recommendations"), "register")
    if value["schema_id"] != SCHEMA or value["record_status"] != DRAFT:
        raise RegisterError("register: unsupported schema or non-draft status")
    _text(value["register_id"], "register_id")
    _choice(value["data_classification"], ("SYNTHETIC", "LOCAL_WORKING_DRAFT"), "data_classification")
    for field in ("provenance", "assumptions"):
        _texts(value[field], field)
    if not value["provenance"]:
        raise RegisterError("provenance: at least one source or stated origin is required")
    for array in ("findings", "recommendations"):
        if not isinstance(value[array], list):
            raise RegisterError(f"{array}: expected list")
    ids: set[str] = set()
    for finding in value["findings"]:
        _keys(finding, FINDING_FIELDS, "finding")
        for field in ("finding_id", "statement"):
            _text(finding[field], f"finding.{field}")
        fid = finding["finding_id"]
        if fid in ids:
            raise RegisterError(f"duplicate finding_id: {fid}")
        ids.add(fid)
        _choice(finding["group"], GROUPS, f"{fid}.group")
        _choice(finding["dimension"], DIMENSIONS, f"{fid}.dimension")
        _texts(finding["evidence_refs"], f"{fid}.evidence_refs")
    ids = set()
    for rec in value["recommendations"]:
        _keys(rec, REC_FIELDS, "recommendation")
        for field in ("recommendation_id", "practice_change", "impact"):
            _text(rec[field], f"recommendation.{field}")
        rid = rec["recommendation_id"]
        if rid in ids:
            raise RegisterError(f"duplicate recommendation_id: {rid}; merge links into one record")
        ids.add(rid)
        for field in ("finding_ids", "skills", "dependencies", "assumptions"):
            _texts(rec[field], f"{rid}.{field}")
        _text(rec["owner_role"], f"{rid}.owner_role", nullable=True)
        _text(rec["maturity_step"], f"{rid}.maturity_step", nullable=True)
        _choice(rec["phase"], PHASES, f"{rid}.phase", nullable=True)
        if not isinstance(rec["scope"], list):
            raise RegisterError(f"{rid}.scope: expected list")
        scopes = set()
        for cell in rec["scope"]:
            _keys(cell, ("group", "dimension", "department"), f"{rid}.scope")
            _choice(cell["group"], GROUPS, f"{rid}.scope.group")
            _choice(cell["dimension"], DIMENSIONS, f"{rid}.scope.dimension")
            _text(cell["department"], f"{rid}.scope.department", nullable=True)
            key = (cell["group"], cell["dimension"], cell["department"])
            if key in scopes:
                raise RegisterError(f"{rid}.scope: duplicate cell")
            scopes.add(key)
        effort = rec["effort"]
        _keys(effort, ("low", "high", "unit", "basis"), f"{rid}.effort")
        _choice(effort["unit"], ("person_days",), f"{rid}.effort.unit")
        for field in ("low", "high"):
            _number(effort[field], f"{rid}.effort.{field}", nullable=True)
        _text(effort["basis"], f"{rid}.effort.basis", nullable=True)
        if (effort["low"] is None) != (effort["high"] is None):
            raise RegisterError(f"{rid}.effort: both bounds must be known or both null")
        if effort["low"] is not None:
            if effort["low"] > effort["high"] or effort["basis"] is None:
                raise RegisterError(f"{rid}.effort: inverted range or missing estimate basis")
        measure = rec["outcome_measure"]
        _keys(measure, ("description", "baseline", "target", "unit", "basis"), f"{rid}.outcome_measure")
        for field in ("description", "unit", "basis"):
            _text(measure[field], f"{rid}.outcome_measure.{field}", nullable=True)
        for field in ("baseline", "target"):
            _number(measure[field], f"{rid}.outcome_measure.{field}", nullable=True)
        if any(measure[f] is not None for f in ("baseline", "target")) and any(measure[f] is None for f in ("description", "unit", "basis")):
            raise RegisterError(f"{rid}.outcome_measure: numeric measures need description, unit and basis")
    # Copy through strict JSON also checks unusual mappings/cyclic Python objects.
    return loads(dumps(value))


def digest(register: dict[str, Any]) -> str:
    return hashlib.sha256(dumps(normalize(register)).encode("utf-8")).hexdigest()


def review_items(register: dict[str, Any]) -> list[dict[str, str]]:
    reg = normalize(register)
    findings = {f["finding_id"]: f for f in reg["findings"]}
    recs = {r["recommendation_id"]: r for r in reg["recommendations"]}
    result: list[dict[str, str]] = []
    for rid, rec in recs.items():
        def add(code: str, detail: str) -> None:
            result.append({"recommendation_id": rid, "code": code, "detail": detail})
        if not rec["scope"]:
            add("SCOPE_UNKNOWN", "No assessment cells were specified.")
        if not rec["finding_ids"]:
            add("NO_FINDINGS_LINKED", "No finding is currently linked; not proof of a gap.")
        for fid in rec["finding_ids"]:
            if fid not in findings:
                add("FINDING_UNRESOLVED", fid)
            elif not any(c["group"] == findings[fid]["group"] and c["dimension"] == findings[fid]["dimension"] for c in rec["scope"]):
                add("FINDING_OUTSIDE_SCOPE", fid)
        for dependency in rec["dependencies"]:
            if dependency not in recs:
                add("DEPENDENCY_UNRESOLVED", dependency)
        for field in ("owner_role", "phase", "maturity_step"):
            if rec[field] is None:
                add(field.upper() + "_UNKNOWN", "Not inferred from other recommendations.")
        if rec["effort"]["low"] is None:
            add("EFFORT_UNKNOWN", "Excluded from known subtotal, never treated as zero.")
    return result


def summary(register: dict[str, Any]) -> dict[str, Any]:
    reg = normalize(register)
    recs = reg["recommendations"]
    known = [r for r in recs if r["effort"]["low"] is not None]
    unknown = [r["recommendation_id"] for r in recs if r["effort"]["low"] is None]
    try:
        low = math.fsum(r["effort"]["low"] for r in known)
        high = math.fsum(r["effort"]["high"] for r in known)
    except OverflowError as exc:
        raise RegisterError("effort subtotal exceeds finite numeric range") from exc
    return {
        "unique_recommendations": len(recs),
        "defined_findings": len(reg["findings"]),
        "finding_links": sum(len(r["finding_ids"]) for r in recs),
        "known_effort_subtotal": {"low": low, "high": high, "unit": "person_days"},
        "effort_total_complete": bool(recs) and not unknown,
        "unknown_effort_ids": unknown,
        "unassigned_phase_ids": [r["recommendation_id"] for r in recs if r["phase"] is None],
        "interpretation": "Draft assumptions only. Subtotal is counted once per recommendation, not per finding or group. Dependency feasibility, approval and evidence truth are not evaluated.",
    }


def _csv_text(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> str:
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(fields)
    for row in rows:
        # Each decoded spreadsheet cell is a complete JSON value. Strings begin
        # with a literal double quote, not a formula sigil; null != empty text.
        writer.writerow(json.dumps(row[f], ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) for f in fields)
    return out.getvalue()


def _csv_rows(text: str, fields: tuple[str, ...], name: str) -> list[dict[str, Any]]:
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        if next(reader, None) != list(fields):
            raise RegisterError(f"{name}: columns must exactly match {fields}")
        rows = []
        for line, cells in enumerate(reader, 2):
            if len(cells) != len(fields):
                raise RegisterError(f"{name}:{line}: expected {len(fields)} cells; got {len(cells)}")
            rows.append({field: loads(cell) for field, cell in zip(fields, cells)})
        return rows
    except (csv.Error, UnicodeError) as exc:
        raise RegisterError(f"{name}: invalid CSV: {exc}") from exc


def tables(register: dict[str, Any]) -> dict[str, str]:
    reg = normalize(register)
    return {"metadata.json": dumps({k: reg[k] for k in META}), "findings.csv": _csv_text(reg["findings"], FINDING_FIELDS), "recommendations.csv": _csv_text(reg["recommendations"], REC_FIELDS)}


def from_tables(metadata: str, findings: str, recommendations: str) -> dict[str, Any]:
    meta = loads(metadata)
    _keys(meta, META, "metadata")
    return normalize({**meta, "findings": _csv_rows(findings, FINDING_FIELDS, "findings.csv"), "recommendations": _csv_rows(recommendations, REC_FIELDS, "recommendations.csv")})


def report_view(register: dict[str, Any]) -> dict[str, Any]:
    reg = normalize(register)
    return {"view_schema": SCHEMA + "/report", "register_sha256": digest(reg), "source_register": reg, "summary": summary(reg), "finding_links": [{"finding_id": f["finding_id"], "recommendation_ids": [r["recommendation_id"] for r in reg["recommendations"] if f["finding_id"] in r["finding_ids"]]} for f in reg["findings"]], "review_items": review_items(reg)}


def roadmap_view(register: dict[str, Any]) -> dict[str, Any]:
    reg = normalize(register)
    return {
        "view_schema": SCHEMA + "/roadmap", "register_sha256": digest(reg), "source_register": reg,
        "roadmap_id": reg["register_id"],
        "fiction_notice": "SYNTHETIC; not a University finding or recommendation." if reg["data_classification"] == "SYNTHETIC" else "LOCAL WORKING DRAFT; not an approved roadmap.",
        "phases": [{"phase_id": p, "order": i, "label": p + " days"} for i, p in enumerate(PHASES)],
        "items": [{"item_id": r["recommendation_id"], "title": r["practice_change"], "recommendation_ref": r["recommendation_id"], "owner_group": None if len(set(c["group"] for c in r["scope"])) != 1 else r["scope"][0]["group"], "owner_groups": list(dict.fromkeys(c["group"] for c in r["scope"])), "owner_role": r["owner_role"], "phase": r["phase"], "prerequisites": r["dependencies"], "finding_ids": r["finding_ids"]} for r in reg["recommendations"]],
        "review_items": review_items(reg),
        "scope_note": "UIOWA-115 item_id/phase/prerequisites projection. Same-phase order, cycles and capacity remain the existing checker's/planner's responsibility; source_register retains all fields.",
    }


def from_view(view: Any) -> dict[str, Any]:
    if not isinstance(view, dict) or "source_register" not in view:
        raise RegisterError("view: source_register required for lossless import")
    reg = normalize(view["source_register"])
    kind = view.get("view_schema")
    expected = report_view(reg) if kind == SCHEMA + "/report" else roadmap_view(reg) if kind == SCHEMA + "/roadmap" else None
    if expected is None or dumps(view) != dumps(expected):
        raise RegisterError("view: changed or incomplete projection; edit the register/CSV and regenerate, do not silently discard view edits")
    return reg


def _md(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def render(register: dict[str, Any]) -> str:
    reg = normalize(register)
    s = summary(reg)
    lines = [f"# Recommendation register — {_md(reg['register_id'])}", "", f"**{reg['data_classification']} · {DRAFT}**", "", "No University finding, approved recommendation, staffing commitment, maturity award, or implementation-feasibility decision is established by this register.", "", f"{s['unique_recommendations']} distinct recommendations; {s['finding_links']} finding links. Count and effort are never multiplied by the number of links or groups.", "", f"Known effort subtotal: {s['known_effort_subtotal']['low']:g}–{s['known_effort_subtotal']['high']:g} person-days. Complete total: {'yes (still an assumption)' if s['effort_total_complete'] else 'UNKNOWN; one or more estimates are absent, or the register is empty'}.", "", "These are proposed phase buckets, not an executable schedule. Parallelism is not replaced by a linear order.", ""]
    for phase in (*PHASES, None):
        lines += [f"## {_md(phase) if phase else 'UNASSIGNED — needs a planning decision'}", "", "| Recommendation | Practice change | Scope | Finding links | Prerequisites | Owner role | Effort assumption |", "|---|---|---|---|---|---|---|"]
        for r in reg["recommendations"]:
            if r["phase"] != phase:
                continue
            e = r["effort"]
            effort = "UNKNOWN" if e["low"] is None else f"{e['low']:g}–{e['high']:g} person-days"
            values = [r["recommendation_id"], r["practice_change"], "; ".join(f"{c['group']}/{c['dimension']} ({c['department'] or 'department UNKNOWN'})" for c in r["scope"]), ", ".join(r["finding_ids"]) or "NONE LINKED", ", ".join(r["dependencies"]) or "NONE DECLARED", r["owner_role"], effort]
            lines.append("| " + " | ".join(_md(v) for v in values) + " |")
        lines.append("")
    lines += ["## Practice and outcome detail", ""]
    for r in reg["recommendations"]:
        lines += [f"### {_md(r['recommendation_id'])}", f"Impact hypothesis: {_md(r['impact'])}", f"Outcome measure: {_md(r['outcome_measure']['description'])}; baseline {_md(r['outcome_measure']['baseline'])}; target {_md(r['outcome_measure']['target'])}; unit {_md(r['outcome_measure']['unit'])}.", f"Measurement basis: {_md(r['outcome_measure']['basis'])}", f"Proposed maturity step (not an awarded rating): {_md(r['maturity_step'])}", f"Skills: {_md(', '.join(r['skills'])) if r['skills'] else 'UNKNOWN'}", f"Effort basis: {_md(r['effort']['basis'])}", f"Assumptions: {_md('; '.join(r['assumptions'])) if r['assumptions'] else 'NONE RECORDED'}", ""]
    lines += ["## Unresolved review items", ""]
    issues = review_items(reg)
    lines += [f"- `{_md(i['recommendation_id'])}` {i['code']}: {_md(i['detail'])}" for i in issues] if issues else ["No unresolved links or missing planning fields detected by this limited data check. This is not a feasibility or approval verdict."]
    lines += ["", "## Register assumptions and provenance", ""] + ["- " + _md(x) for x in reg["assumptions"] + reg["provenance"]]
    return "\n".join(lines) + "\n"


def read(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise RegisterError(f"{path}: exceeds {MAX_BYTES} bytes")
        return raw.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise RegisterError(f"{path}: expected UTF-8") from exc


def write_new(path: Path, content: str) -> None:
    # Exclusive creation never deletes or overwrites a pre-existing final path.
    with path.open("x", encoding="utf-8", newline="") as stream:
        stream.write(content)


def export_bundle(register: dict[str, Any], destination: Path) -> None:
    reg = normalize(register)
    payloads = {**tables(reg), "register.json": dumps(reg), "report.json": dumps(report_view(reg)), "roadmap.json": dumps(roadmap_view(reg)), "report.md": render(reg)}
    destination.mkdir(exist_ok=False)
    # On failure leave already-created evidence intact; no recursive cleanup.
    for name, content in payloads.items():
        write_new(destination / name, content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Validate draft shape and report missing links/fields; not feasibility")
    check.add_argument("input", type=Path)
    export = sub.add_parser("export", help="Write a new editable bundle; refuse existing destination")
    export.add_argument("input", type=Path)
    export.add_argument("--out", type=Path, required=True)
    imp = sub.add_parser("import", help="Import edited CSV tables plus metadata into a new register")
    imp.add_argument("directory", type=Path)
    imp.add_argument("--out", type=Path, required=True)
    view = sub.add_parser("import-view", help="Lossless import of an unchanged derived view")
    view.add_argument("input", type=Path)
    view.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "import":
            reg = from_tables(read(args.directory / "metadata.json"), read(args.directory / "findings.csv"), read(args.directory / "recommendations.csv"))
        elif args.command == "import-view":
            reg = from_view(loads(read(args.input)))
        else:
            reg = normalize(loads(read(args.input)))
        if args.command == "export":
            export_bundle(reg, args.out)
        elif args.command in ("import", "import-view"):
            write_new(args.out, dumps(reg))
        issues = review_items(reg)
        print(dumps({"record_status": DRAFT, "summary": summary(reg), "review_items": issues}), end="")
        return 1 if args.command == "check" and issues else 0
    except (RegisterError, OSError, RecursionError) as exc:
        print(f"INPUT_OR_OUTPUT_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
