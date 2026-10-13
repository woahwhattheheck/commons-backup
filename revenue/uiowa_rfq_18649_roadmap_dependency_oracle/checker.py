#!/usr/bin/env python3
"""Offline roadmap dependency analysis. Python 3.10+; standard library only.

Edges point from a prerequisite to the item that requires it. Frontiers describe
structural independence, not dates, staffing feasibility, or permission to start.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import html
import json
from pathlib import Path
import re
import sys
from typing import Any

INPUT_SCHEMA = "tjlabs.roadmap-dependencies/v1"
REPORT_SCHEMA = "tjlabs.roadmap-dependencies-report/v1"
MAX_BYTES = 2_000_000
MAX_ITEMS = 5_000
MAX_EDGES = 20_000
MAX_PHASES = 100
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}\Z")


class InputError(ValueError):
    """A caller-readable input or file error; not an assessment finding."""


def _object(value: Any, keys: set[str], required: set[str], path: str) -> None:
    if type(value) is not dict:
        raise InputError(f"{path}: expected a JSON object")
    if any(type(k) is not str for k in value):
        raise InputError(f"{path}: object keys must be strings")
    extra = set(value) - keys
    absent = required - set(value)
    if extra or absent:
        raise InputError(f"{path}: unknown keys {sorted(extra)}; missing keys {sorted(absent)}")


def _text(value: Any, path: str, *, identifier: bool = False) -> str:
    if type(value) is not str or not value.strip() or len(value) > (128 if identifier else 2000):
        raise InputError(f"{path}: expected a nonempty string of at most {128 if identifier else 2000} characters")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise InputError(f"{path}: invalid Unicode text") from exc
    if any((ord(c) < 32 and c not in "\n\t\r") or ord(c) == 127 for c in value):
        raise InputError(f"{path}: control characters are not allowed")
    if identifier and not _ID.fullmatch(value):
        raise InputError(f"{path}: use an alphanumeric character followed by letters, digits, dot, plus, underscore or hyphen")
    return value


def _array(value: Any, path: str, limit: int) -> list:
    if type(value) is not list or len(value) > limit:
        raise InputError(f"{path}: expected a JSON array with at most {limit} entries")
    return value


def _reject_constant(token: str) -> None:
    raise InputError(f"JSON: numeric token {token[:32]!r} is not supported by this schema")


def _parse_integer(token: str) -> int:
    if len(token.lstrip("-")) > 16:
        raise InputError("JSON: integer token exceeds the adapter numeric domain")
    value = int(token)
    if abs(value) > 1_000_000_000_000_000:
        raise InputError("JSON: integer exceeds the adapter numeric domain")
    return value


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    out: dict = {}
    for key, value in pairs:
        if key in out:
            raise InputError(f"JSON: duplicate object key {key[:80]!r}")
        out[key] = value
    return out


def _decode(data: bytes | str, *, allow_integers: bool = False) -> Any:
    """Parse bounded UTF-8 JSON without duplicate keys or numeric extensions."""
    if type(data) not in (bytes, str):
        raise InputError("JSON input must be bytes or text")
    try:
        raw = data.encode("utf-8") if type(data) is str else data
        if len(raw) > MAX_BYTES:
            raise InputError(f"JSON input exceeds {MAX_BYTES} bytes")
        text = raw.decode("utf-8")
        value = json.loads(text, object_pairs_hook=_pairs,
                           parse_constant=_reject_constant,
                           parse_float=_reject_constant, parse_int=_parse_integer if allow_integers else _reject_constant)
    except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise InputError(f"Invalid UTF-8 JSON: {type(exc).__name__}") from exc
    return value


def loads(data: bytes | str) -> dict:
    return validate(_decode(data))


def validate(packet: Any) -> dict:
    """Return an owned, shallow-schema-deep copy, retaining declared item order."""
    _object(packet, {"schema", "phases", "items", "source_label"},
            {"schema", "phases", "items"}, "$")
    if type(packet["schema"]) is not str or packet["schema"] != INPUT_SCHEMA:
        raise InputError(f"$.schema: expected {INPUT_SCHEMA!r}")
    phases = _array(packet["phases"], "$.phases", MAX_PHASES)
    if not phases:
        raise InputError("$.phases: declare at least one ordered phase")
    phase_copy, phase_ids = [], set()
    for i, phase in enumerate(phases):
        path = f"$.phases[{i}]"
        _object(phase, {"id", "label"}, {"id", "label"}, path)
        ident = _text(phase["id"], f"{path}.id", identifier=True)
        label = _text(phase["label"], f"{path}.label")
        if ident in phase_ids:
            raise InputError(f"{path}.id: duplicate phase {ident!r}")
        phase_ids.add(ident)
        phase_copy.append({"id": ident, "label": label})
    items = _array(packet["items"], "$.items", MAX_ITEMS)
    item_copy, ids, total_edges = [], set(), 0
    for i, item in enumerate(items):
        path = f"$.items[{i}]"
        _object(item, {"id", "title", "kind", "phase", "requires"},
                {"id", "title", "kind", "phase", "requires"}, path)
        ident = _text(item["id"], f"{path}.id", identifier=True)
        if ident in ids:
            raise InputError(f"{path}.id: duplicate item {ident!r}")
        ids.add(ident)
        title = _text(item["title"], f"{path}.title")
        kind = item["kind"]
        if type(kind) is not str or kind not in ("recommendation", "shared_dependency"):
            raise InputError(f"{path}.kind: expected recommendation or shared_dependency")
        phase = item["phase"]
        if phase is not None:
            _text(phase, f"{path}.phase", identifier=True)
            if phase not in phase_ids:
                raise InputError(f"{path}.phase: unknown phase {phase!r}")
        reqs = _array(item["requires"], f"{path}.requires", MAX_EDGES)
        total_edges += len(reqs)
        if total_edges > MAX_EDGES:
            raise InputError(f"$.items: more than {MAX_EDGES} dependency edges")
        copied, seen = [], set()
        for j, requirement in enumerate(reqs):
            reference = _text(requirement, f"{path}.requires[{j}]", identifier=True)
            if reference in seen:
                raise InputError(f"{path}.requires[{j}]: duplicate prerequisite {reference!r}")
            seen.add(reference)
            copied.append(reference)
        item_copy.append({"id": ident, "title": title, "kind": kind,
                          "phase": phase, "requires": copied})
    result = {"schema": INPUT_SCHEMA, "phases": phase_copy, "items": item_copy}
    if "source_label" in packet:
        result["source_label"] = _text(packet["source_label"], "$.source_label")
    # Bound direct-library input too, not only CLI bytes.
    if len(_canonical(result)) > MAX_BYTES:
        raise InputError(f"Canonical input exceeds {MAX_BYTES} bytes")
    return result


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _scc(adj: dict[str, list[str]], reverse: dict[str, list[str]]) -> list[list[str]]:
    """Iterative Kosaraju; no recursion or enumeration of all cycles."""
    seen, finish = set(), []
    for root in sorted(adj):
        if root in seen:
            continue
        seen.add(root)
        stack = [(root, iter(adj[root]))]
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                stack.pop()
                finish.append(node)
            elif child not in seen:
                seen.add(child)
                stack.append((child, iter(adj[child])))
    seen.clear()
    components = []
    for root in reversed(finish):
        if root in seen:
            continue
        component, pending = [], [root]
        seen.add(root)
        while pending:
            node = pending.pop()
            component.append(node)
            for child in reverse[node]:
                if child not in seen:
                    seen.add(child)
                    pending.append(child)
        components.append(sorted(component))
    return sorted(components)


def _cycle_witness(component: list[str], adj: dict[str, list[str]]) -> list[str]:
    """Return one genuine closed directed path from a cyclic component."""
    members, done = set(component), set()
    for root in component:
        if root in done:
            continue
        path, active = [root], {root: 0}
        stack = [(root, iter(adj[root]))]
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                stack.pop()
                active.pop(node)
                path.pop()
                done.add(node)
            elif child in members:
                if child in active:
                    return path[active[child]:] + [child]
                if child not in done:
                    active[child] = len(path)
                    path.append(child)
                    stack.append((child, iter(adj[child])))
    raise RuntimeError("Internal error: cyclic component has no witness")


def _reduce_graph(items: dict, adj: dict, reverse: dict, roots: dict) -> tuple[dict, list[list[str]]]:
    """Propagate blockers and retain whole simultaneous Kahn frontiers."""
    blocked = {ident: value.copy() for ident, value in roots.items()}
    pending = deque(sorted(blocked))
    while pending:
        node = pending.popleft()
        for child in adj[node]:
            if child not in blocked:
                blocked[child] = {"root_diagnostic": blocked[node]["root_diagnostic"],
                                  "blocked_by": node}
                pending.append(child)
    remaining = set(items) - set(blocked)
    indegree = {node: sum(p in remaining for p in reverse[node]) for node in remaining}
    frontier = sorted(node for node in remaining if indegree[node] == 0)
    waves, emitted = [], 0
    while frontier:
        waves.append(frontier)
        emitted += len(frontier)
        following = []
        for node in frontier:
            for child in adj[node]:
                if child in indegree:
                    indegree[child] -= 1
                    if indegree[child] == 0:
                        following.append(child)
        frontier = sorted(following)
    if emitted != len(remaining):
        raise RuntimeError("Internal error: nonblocked graph is not acyclic")
    return blocked, waves


def analyze(packet: dict) -> dict:
    data = validate(packet)
    items = {item["id"]: item for item in data["items"]}
    positions = {item["id"]: i for i, item in enumerate(data["items"])}
    order = {phase["id"]: i for i, phase in enumerate(data["phases"])}
    adj = {ident: [] for ident in sorted(items)}
    reverse = {ident: [] for ident in sorted(items)}
    edges, diagnostics, roots = [], [], {}

    def finding(code: str, severity: str, message: str,
                affected: list[str] = (), **detail: Any) -> None:
        number = f"D{len(diagnostics) + 1:04d}"
        diagnostics.append({"id": number, "code": code, "severity": severity,
                            "message": message, **detail})
        for ident in affected:
            roots.setdefault(ident, {"root_diagnostic": number, "blocked_by": None})

    if not items:
        finding("EMPTY_ROADMAP", "warning", "No items were supplied; no roadmap was assessed.")
    for ident in sorted(items):
        item = items[ident]
        if item["phase"] is None:
            finding("UNASSIGNED_PHASE", "warning",
                    f"{ident} has no proposed phase; its phase ordering cannot be checked.",
                    item=ident, path=f"$.items[{positions[ident]}].phase")
        for j, prerequisite in sorted(enumerate(item["requires"]), key=lambda pair: pair[1]):
            path = f"$.items[{positions[ident]}].requires[{j}]"
            if prerequisite not in items:
                finding("MISSING_PREREQUISITE", "error",
                        f"{ident} requires missing item {prerequisite}; add or correct this reference.",
                        [ident], item=ident, prerequisite=prerequisite, path=path,
                        edge={"from": prerequisite, "to": ident})
                continue
            adj[prerequisite].append(ident)
            reverse[ident].append(prerequisite)
            edge = {"from": prerequisite, "to": ident}
            edges.append(edge)
            source_phase = items[prerequisite]["phase"]
            target_phase = item["phase"]
            if source_phase is not None and target_phase is not None and order[source_phase] > order[target_phase]:
                finding("PHASE_INVERSION", "error",
                        f"{ident} in {target_phase} requires {prerequisite} in later phase {source_phase}; review this edge or the proposed phases.",
                        [ident], item=ident, prerequisite=prerequisite, path=path,
                        edge=edge.copy(), prerequisite_phase=source_phase, item_phase=target_phase)
    for value in adj.values():
        value.sort()
    for value in reverse.values():
        value.sort()
    cycles = []
    for component in _scc(adj, reverse):
        if len(component) == 1 and component[0] not in adj[component[0]]:
            continue
        members = set(component)
        inside = [{"from": a, "to": b} for a in component for b in adj[a] if b in members]
        witness = _cycle_witness(component, adj)
        cycle = {"members": component, "internal_edges": inside, "witness_path": witness}
        cycles.append(cycle)
        finding("DEPENDENCY_CYCLE", "error",
                "Closed prerequisite path: " + " -> ".join(witness) +
                ". Review the real dependencies; no edge is automatically deleted.",
                component, **cycle)
    blocked, waves = _reduce_graph(items, adj, reverse, roots)
    # A later phase can constrain an earlier one through an unphased intermediary.
    # Propagate one latest known phase bound per item over the valid DAG.
    latest: dict[str, tuple[int, str]] = {}
    bound_parent: dict[str, str | None] = {}
    new_phase_roots = False
    phase_blocked: set[str] = set()
    for wave in waves:
        for node in wave:
            if any(p in phase_blocked for p in reverse[node]):
                phase_blocked.add(node)
                continue
            inherited = [(latest[p][0], latest[p][1], p) for p in reverse[node] if p in latest]
            best = max(inherited, default=None)
            phase = items[node]["phase"]
            own = order[phase] if phase is not None else None
            if best is not None and own is not None and best[0] > own:
                path = [node, best[2]]
                while path[-1] != best[1]:
                    parent = bound_parent[path[-1]]
                    if parent is None:
                        raise RuntimeError("Internal error: missing phase witness parent")
                    path.append(parent)
                path.reverse()
                finding("TRANSITIVE_PHASE_INVERSION", "error",
                        f"{node} in {phase} transitively requires {best[1]} in later phase {items[best[1]]['phase']}; review the exact prerequisite path.",
                        [node], item=node, prerequisite=best[1], witness_path=path,
                        path_edges=[{"from": x, "to": y} for x, y in zip(path, path[1:])],
                        item_phase=phase, prerequisite_phase=items[best[1]]["phase"])
                new_phase_roots = True
                phase_blocked.add(node)
                continue
            if best is not None and (own is None or best[0] > own):
                latest[node] = (best[0], best[1])
                bound_parent[node] = best[2]
            elif own is not None:
                latest[node] = (own, node)
                bound_parent[node] = None
    if new_phase_roots:
        blocked, waves = _reduce_graph(items, adj, reverse, roots)
    errors = sum(d["severity"] == "error" for d in diagnostics)
    warnings = sum(d["severity"] == "warning" for d in diagnostics)
    return {
        "schema": REPORT_SCHEMA,
        "input_sha256": hashlib.sha256(_canonical(data)).hexdigest(),
        "digest_basis": "Canonical accepted input JSON; not source authentication or approval.",
        "source_label": data.get("source_label"),
        "dependency_check_status": "NEEDS_REPAIR" if errors else "INCOMPLETE" if warnings else "CONSISTENT",
        "counts": {"items": len(items), "known_edges": len(edges),
                   "errors": errors, "warnings": warnings, "blocked_items": len(blocked)},
        "phases": data["phases"],
        "nodes": [items[ident] for ident in sorted(items)],
        "edges": sorted(edges, key=lambda e: (e["from"], e["to"])),
        "diagnostics": diagnostics,
        "cycles": cycles,
        "blocked_items": [{"id": ident, **blocked[ident]} for ident in sorted(blocked)],
        "dependency_frontiers": waves,
        "frontier_meaning": "Prerequisite independence only. Same frontier is not a promise of concurrent scheduling; proposed phases, capacity, duration and external constraints still apply.",
        "authority": {"schedule_authorized": False, "release_authorized": False,
                      "university_findings_established": False},
    }


ROADMAP085_CONTRACT = {
    "repository": "woahwhattheheck/commons",
    "path": "revenue/uiowa_rfq_18649_roadmap/roadmap.py",
    "inspected_commit": "9ae8594e1c09c4e856d4a8430e2d58e68cd2eb9d",
    "inspected_blob": "4870639c2cb077657feeba3a4e9dae739df5acfe",
    "meaning": "Schema contract inspected at this revision; not provenance of the caller's data.",
}


def analyze_roadmap085(document: Any) -> dict:
    """Consume the actual 085 v1 interchange, without its scheduling semantics."""
    required = {"schema_version", "title", "synthetic", "assumptions", "recommendations"}
    _object(document, required, required, "$")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise InputError("$.schema_version: expected integer 1 for the roadmap085 adapter")
    title = _text(document["title"], "$.title")
    if type(document["synthetic"]) is not bool:
        raise InputError("$.synthetic: expected a boolean")
    def strings(values: Any, path: str) -> list[str]:
        return [_text(v, f"{path}[{i}]") for i, v in enumerate(_array(values, path, MAX_EDGES))]
    copied = {"schema_version": 1, "title": title, "synthetic": document["synthetic"],
              "assumptions": strings(document["assumptions"], "$.assumptions"), "recommendations": []}
    fields = {"id", "title", "group", "phase", "owner_role", "depends_on", "duration_days",
              "finding_refs", "evidence_refs", "practice_change", "observable_outcome", "assumptions"}
    recommendations = _array(document["recommendations"], "$.recommendations", MAX_ITEMS)
    if not recommendations:
        raise InputError("$.recommendations: the roadmap085 format requires at least one item")
    for i, row in enumerate(recommendations):
        path = f"$.recommendations[{i}]"
        _object(row, fields, fields, path)
        record = {}
        for field in ("id", "title", "group", "phase", "practice_change", "observable_outcome"):
            record[field] = _text(row[field], f"{path}.{field}", identifier=field == "id")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", record["id"]):
            raise InputError(f"{path}.id: unsupported roadmap085 identifier")
        if record["group"] not in ("ESS", "RIS", "IAM", "DEPARTMENT"):
            raise InputError(f"{path}.group: unknown roadmap085 group")
        if record["phase"] not in ("0-90", "90-180", "180+"):
            raise InputError(f"{path}.phase: unknown roadmap085 phase")
        record["owner_role"] = None if row["owner_role"] is None else _text(row["owner_role"], f"{path}.owner_role")
        for field in ("depends_on", "finding_refs", "evidence_refs", "assumptions"):
            record[field] = strings(row[field], f"{path}.{field}")
            if len(set(record[field])) != len(record[field]):
                raise InputError(f"{path}.{field}: duplicate values")
        duration = row["duration_days"]
        if duration is None:
            record["duration_days"] = None
        elif (type(duration) is list and len(duration) == 2
                and all(type(v) is int and 0 <= v <= 1_000_000_000_000_000 for v in duration)
                and duration[0] <= duration[1]):
            record["duration_days"] = duration.copy()
        else:
            raise InputError(f"{path}.duration_days: expected null or ordered nonnegative integer day bounds")
        copied["recommendations"].append(record)
    if len(_canonical(copied)) > MAX_BYTES:
        raise InputError(f"Roadmap085 input exceeds {MAX_BYTES} canonical bytes")
    packet = {
        "schema": INPUT_SCHEMA, "source_label": title,
        "phases": [{"id": phase, "label": phase + " relative calendar days"} for phase in ("0-90", "90-180", "180+")],
        "items": [{"id": row["id"], "title": row["title"], "kind": "recommendation",
                   "phase": row["phase"], "requires": row["depends_on"]}
                  for row in copied["recommendations"]],
    }
    report = analyze(packet)
    report["source_projection"] = {
        "format": "UIOWA-085 schema_version=1 input (not a derived planner report)",
        "contract_reference": ROADMAP085_CONTRACT.copy(),
        "full_input_sha256": hashlib.sha256(_canonical(copied)).hexdigest(),
        "synthetic_label_as_supplied": copied["synthetic"],
        "evaluated_fields": ["id", "title", "phase", "depends_on"],
        "not_evaluated": "Duration feasibility, ownership adequacy, capacity, evidence authenticity and observed outcomes remain the upstream planner/reviewer's work.",
    }
    return report


def _md(text: Any) -> str:
    value = html.escape(str(text), quote=False).replace("\\", "\\\\")
    for character in "|`[]*_":
        value = value.replace(character, "\\" + character)
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>").replace("\t", "    ")


def markdown(report: dict) -> str:
    out = ["# Roadmap dependency review", "",
           f"**Status: {report['dependency_check_status']}**", "",
           f"Input SHA-256: `{report['input_sha256']}`", "",
           _md(report["digest_basis"]), "",
           "This is an offline structural check, not an approved schedule, release decision or University assessment.", "",
           "## Findings", ""]
    if "source_projection" in report:
        projection = report["source_projection"]
        out[10:10] = ["UIOWA-085 adapter; full upstream input SHA-256: `" + projection["full_input_sha256"] + "`", "", projection["not_evaluated"], ""]
    if not report["diagnostics"]:
        out.append("No missing references, dependency cycles or proposed-phase inversions were found in the supplied packet.")
    for row in report["diagnostics"]:
        out.append(f"### {row['id']} · {row['code']} · {row['severity']}")
        out.extend(["", _md(row["message"]), ""])
        if "path" in row:
            out.append(f"Input location: `{row['path']}`")
        if "path_edges" in row:
            out.append("Exact prerequisite path: " + " -> ".join(f"`{node}`" for node in row["witness_path"]))
        if "internal_edges" in row:
            out.append("Exact edges inside this cyclic component: " + "; ".join(
                f"`{e['from']} -> {e['to']}`" for e in row["internal_edges"]))
    out.extend(["", "## Dependency-independent frontiers", "", report["frontier_meaning"], ""])
    if not report["dependency_frontiers"]:
        out.append("No unblocked items remain in the supplied graph.")
    for i, wave in enumerate(report["dependency_frontiers"], 1):
        out.append(f"Frontier {i}: " + ", ".join(f"`{node}`" for node in wave))
    out.extend(["", "## Blocked items", "", "| Item | Root finding | Immediate blocking prerequisite |",
                "| --- | --- | --- |"])
    for row in report["blocked_items"]:
        out.append(f"| {row['id']} | {row['root_diagnostic']} | {row['blocked_by'] or 'Direct finding'} |")
    if not report["blocked_items"]:
        out.append("| None | — | — |")
    out.extend(["", "## Declared items", "", "| ID | Kind | Proposed phase | Title |", "| --- | --- | --- | --- |"])
    for row in report["nodes"]:
        out.append(f"| {row['id']} | {row['kind']} | {row['phase'] or 'Unassigned'} | {_md(row['title'])} |")
    return "\n".join(out) + "\n"


def dot(report: dict) -> str:
    """Portable Graphviz source; quoting prevents user text becoming DOT syntax."""
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    out = ["digraph roadmap {", "  rankdir=LR;", '  graph [label="Prerequisite -> dependent (not an execution schedule)", labelloc=t];']
    blocked = {row["id"] for row in report["blocked_items"]}
    for row in report["nodes"]:
        label = f"{row['id']} | {row['title']}\nphase: {row['phase'] or 'UNASSIGNED'}"
        shape = "ellipse" if row["kind"] == "shared_dependency" else "box"
        style = ", style=dashed" if row["id"] in blocked else ""
        out.append(f"  {quote(row['id'])} [label={quote(label)}, shape={shape}{style}];")
    inversions = {(d["edge"]["from"], d["edge"]["to"]) for d in report["diagnostics"] if d["code"] == "PHASE_INVERSION"}
    for edge in report["edges"]:
        attributes = ' [label="phase inversion", style=dashed]' if (edge["from"], edge["to"]) in inversions else ""
        out.append(f"  {quote(edge['from'])} -> {quote(edge['to'])}{attributes};")
    missing = [d for d in report["diagnostics"] if d["code"] == "MISSING_PREREQUISITE"]
    for ident in sorted({d["prerequisite"] for d in missing}):
        out.append(f"  {quote('__missing__' + ident)} [label={quote('MISSING: ' + ident)}, shape=diamond, style=dashed];")
    for row in missing:
        out.append(f"  {quote('__missing__' + row['prerequisite'])} -> {quote(row['item'])} [style=dashed];")
    out.append("}")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Roadmap JSON packet")
    parser.add_argument("--input-format", choices=("native", "roadmap085"), default="native")
    parser.add_argument("--format", choices=("json", "markdown", "dot"), default="json")
    parser.add_argument("--output", type=Path, help="Output file; defaults to stdout")
    args = parser.parse_args(argv)
    try:
        if args.output is not None:
            if args.input.resolve() == args.output.resolve():
                raise InputError("Output must not replace the input file")
            if args.output.exists() and args.input.samefile(args.output):
                raise InputError("Output must not replace an input-file alias")
        with args.input.open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
        report = (analyze(loads(raw)) if args.input_format == "native"
                  else analyze_roadmap085(_decode(raw, allow_integers=True)))
        rendered = (json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
                    if args.format == "json" else markdown(report) if args.format == "markdown" else dot(report))
        if args.output is None:
            sys.stdout.write(rendered)
        else:
            args.output.write_text(rendered, encoding="utf-8")
        return 0 if report["dependency_check_status"] == "CONSISTENT" else 1
    except (InputError, OSError) as exc:
        print(f"roadmap-dependencies: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
