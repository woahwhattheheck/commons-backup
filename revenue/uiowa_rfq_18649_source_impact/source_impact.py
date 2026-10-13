#!/usr/bin/env python3
"""Offline source/version comparison. Produces review work, never conclusions."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import html
import io
import json
import re
import sys
from collections import Counter, defaultdict, deque
from datetime import datetime
from pathlib import Path

MANIFEST = "uiowa-source-manifest/v1"
GRAPH = "uiowa-source-dependencies/v1"
REPORT = "uiowa-source-impact/v1"
TEXT_REP = "exact-utf8-text/v1"
LIMIT = 10 * 1024 * 1024


class InputError(ValueError):
    """Invalid or ambiguous input; never silently repair evidence."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path):
    with Path(path).open("rb") as handle:
        raw = handle.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise InputError(f"input exceeds {LIMIT} bytes: {path}")
    def bad_constant(value):
        raise InputError(f"non-finite JSON number: {value}")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                      parse_constant=bad_constant)


def _require(condition, message):
    if not condition:
        raise InputError(message)


def _string(value, where):
    _require(isinstance(value, str) and bool(value.strip()), f"{where}: nonempty string required")
    _require(not any(ord(c) < 32 for c in value), f"{where}: control character")
    return value


def _fields(obj, required, optional, where):
    _require(isinstance(obj, dict), f"{where}: object required")
    _require(set(required) <= set(obj), f"{where}: missing fields {sorted(set(required)-set(obj))}")
    _require(set(obj) <= set(required) | set(optional),
             f"{where}: unknown fields {sorted(set(obj)-set(required)-set(optional))}; use metadata/extensions")


def _time(value):
    _string(value, "captured_at")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputError("captured_at: invalid ISO timestamp") from exc
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
             "captured_at: explicit UTC offset required")
    return parsed


def fingerprint(source):
    if source.get("text") is not None:
        return {"representation": TEXT_REP,
                "sha256": hashlib.sha256(source["text"].encode("utf-8")).hexdigest(),
                "basis": "inline_text"}
    if source.get("content") is not None:
        return {**source["content"], "basis": "declared_digest"}
    return None


def validate_manifest(manifest):
    _fields(manifest, {"schema", "snapshot_id", "captured_at", "namespace", "scope", "coverage", "sources"},
            {"provenance"}, "manifest")
    _require(manifest["schema"] == MANIFEST, "unsupported manifest schema")
    for field in ("snapshot_id", "namespace"):
        _string(manifest[field], field)
    _time(manifest["captured_at"])
    _require(manifest["coverage"] in ("complete", "partial"), "coverage must be complete or partial")
    _require(isinstance(manifest["scope"], dict), "scope: object required")
    _require(isinstance(manifest.get("provenance", {}), dict), "provenance: object required")
    _require(isinstance(manifest["sources"], list), "sources: array required")
    result = {}
    for source in manifest["sources"]:
        _fields(source, {"id", "revision", "metadata", "interpretation"},
                {"text", "content", "unavailable_reason"}, "source")
        sid = _string(source["id"], "source.id")
        _require(sid not in result, f"duplicate source ID: {sid}")
        _require(source["revision"] is None or isinstance(source["revision"], str), f"{sid}: invalid revision")
        for field in ("metadata", "interpretation"):
            _require(isinstance(source[field], dict), f"{sid}.{field}: object required")
        _require(source.get("text") is None or isinstance(source["text"], str), f"{sid}: invalid text")
        if source.get("unavailable_reason") is not None:
            _string(source["unavailable_reason"], f"{sid}.unavailable_reason")
        content = source.get("content")
        if content is not None:
            _fields(content, {"representation", "sha256"}, set(), f"{sid}.content")
            _string(content["representation"], "content.representation")
            _require(isinstance(content["sha256"], str) and
                     re.fullmatch(r"[0-9a-f]{64}", content["sha256"]) is not None,
                     f"{sid}: lowercase SHA-256 required")
            if source.get("text") is not None:
                computed = fingerprint(source)
                _require(content["representation"] == computed["representation"] and
                         content["sha256"] == computed["sha256"], f"{sid}: text/digest conflict")
        result[sid] = source
    # Also rejects non-finite floats and non-JSON objects supplied through the API.
    canonical(manifest)
    return result


def _delta(before, after):
    changes = {}
    for key in sorted(set(before) | set(after)):
        left = {"present": key in before, "value": before.get(key)}
        right = {"present": key in after, "value": after.get(key)}
        if canonical(left) != canonical(right):
            changes[key] = {"before": left, "after": right}
    return changes


def compare_source(sid, before, after, before_complete, after_complete):
    row = {"source_id": sid, "before_revision": before["revision"] if before else None,
           "after_revision": after["revision"] if after else None,
           "before_fingerprint": fingerprint(before) if before else None,
           "after_fingerprint": fingerprint(after) if after else None,
           "metadata_changes": {}, "interpretation_changes": {}, "revision_changed": False, "text_comparison": "unavailable", "text_change": None}
    if before is None or after is None:
        established = before_complete if before is None else after_complete
        row["change_type"] = ("added" if before is None else "removed") if established else "comparison_unavailable"
        row["reason"] = ("Source entered/left the declared complete manifest; this does not assert file creation/deletion."
                         if established else "Absence in a partial manifest does not establish addition/removal.")
        return row
    row["metadata_changes"] = _delta(before["metadata"], after["metadata"])
    row["revision_changed"] = before["revision"] != after["revision"]
    row["interpretation_changes"] = _delta(before["interpretation"], after["interpretation"])
    a, b = row["before_fingerprint"], row["after_fingerprint"]
    if a is None or b is None or a["representation"] != b["representation"]:
        row["change_type"] = "comparison_unavailable"
        row["reason"] = "Missing fingerprints or incompatible content representations; unchanged text is not established."
        row["unavailable_reasons"] = [s.get("unavailable_reason") for s in (before, after) if s.get("unavailable_reason")]
    else:
        both_text = before.get("text") is not None and after.get("text") is not None
        equal = a["sha256"] == b["sha256"]
        row["text_comparison"] = ("equal" if equal else "different") if both_text else "unavailable"
        if not equal and both_text:
            row["text_change"] = {"before_preview": before["text"][:2048], "after_preview": after["text"][:2048],
                                  "truncated": len(before["text"]) > 2048 or len(after["text"]) > 2048,
                                  "limit_characters_per_side": 2048}
        if not equal:
            row["change_type"] = "text_changed" if both_text else "content_changed"
            row["reason"] = "Exact UTF-8 text differs." if both_text else "Comparable declared content digests differ; source text was not inspected."
        elif row["interpretation_changes"]:
            row["change_type"] = "interpretation_changed"
            row["reason"] = "Content fingerprint is unchanged but recorded claims/ratings changed; review the interpretation."
        elif row["metadata_changes"] or row["revision_changed"]:
            row["change_type"] = "metadata_only"
            row["reason"] = "Content fingerprint is unchanged; descriptive metadata/revision changed."
        else:
            row["change_type"] = "unchanged"
            row["reason"] = "Comparable fingerprints and tracked source fields are unchanged; not an approval or currentness finding."
    return row


def validate_graph(graph, namespace):
    _fields(graph, {"schema", "namespace", "coverage", "artifacts"}, {"provenance", "scope"}, "dependencies")
    _require(graph["schema"] == GRAPH, "unsupported dependency schema")
    _require(graph["namespace"] == namespace, "dependency namespace mismatch")
    _require(graph["coverage"] in ("complete", "partial"), "dependency coverage must be complete or partial")
    _require(isinstance(graph["artifacts"], list), "artifacts: array required")
    nodes = {}
    for node in graph["artifacts"]:
        _fields(node, {"id", "kind", "locator", "depends_on"}, {"notes"}, "artifact")
        if "notes" in node:
            _require(isinstance(node["notes"], str), "artifact.notes: string required")
        nid = _string(node["id"], "artifact.id")
        _require(nid not in nodes, f"duplicate artifact ID: {nid}")
        _string(node["kind"], "artifact.kind")
        _string(node["locator"], "artifact.locator")
        _require(isinstance(node["depends_on"], list), f"{nid}.depends_on: array required")
        refs = set()
        for ref in node["depends_on"]:
            _require(isinstance(ref, dict) and len(ref) == 1 and
                     next(iter(ref)) in ("source_id", "artifact_id"), f"{nid}: typed dependency reference required")
            key, value = next(iter(ref.items()))
            _string(value, f"{nid}.{key}")
            _require((key, value) not in refs, f"{nid}: duplicate dependency {value}")
            refs.add((key, value))
        nodes[nid] = node
    _require(isinstance(graph.get("provenance", {}), dict), "dependency provenance: object required")
    canonical(graph)
    return nodes


def _cycles(nodes):
    """Iterative DFS: report actual back-edge witnesses, not all downstream nodes."""
    state, found = {}, []
    for start in sorted(nodes):
        if state.get(start):
            continue
        path, positions = [start], {start: 0}
        def children(n):
            return iter(sorted(r["artifact_id"] for r in nodes[n]["depends_on"]
                               if "artifact_id" in r and r["artifact_id"] in nodes))
        stack = [(start, children(start))]
        state[start] = 1
        while stack:
            current, iterator = stack[-1]
            child = next(iterator, None)
            if child is None:
                stack.pop(); path.pop(); positions.pop(current); state[current] = 2
            elif state.get(child) == 1:
                found.append(path[positions[child]:] + [child])
            elif not state.get(child):
                state[child] = 1; positions[child] = len(path); path.append(child)
                stack.append((child, children(child)))
    return found


def analyze(before, after, graph):
    old, new = validate_manifest(before), validate_manifest(after)
    _require(before["namespace"] == after["namespace"], "source namespace mismatch; do not join same-looking IDs")
    _require(canonical(before["scope"]) == canonical(after["scope"]), "source scope mismatch")
    _require(_time(after["captured_at"]) >= _time(before["captured_at"]), "snapshots are in reverse chronological order")
    nodes = validate_graph(graph, before["namespace"])
    if "scope" in graph:
        _require(canonical(graph["scope"]) == canonical(before["scope"]), "dependency scope mismatch")
    changes = [compare_source(s, old.get(s), new.get(s), before["coverage"] == "complete",
                              after["coverage"] == "complete") for s in sorted(set(old) | set(new))]
    change_map = {r["source_id"]: r for r in changes}
    source_users, dependents, diagnostics = defaultdict(list), defaultdict(list), []
    bad_nodes = set()
    if "scope" not in graph:
        diagnostics.append({"code": "unbound_dependency_scope", "detail": "Bind dependencies to the manifest scope before relying on the queue."})
        bad_nodes.update(nodes)
    for nid, node in sorted(nodes.items()):
        for ref in node["depends_on"]:
            if "source_id" in ref:
                sid = ref["source_id"]; source_users[sid].append(nid)
                if sid not in change_map:
                    diagnostics.append({"code": "unknown_source_reference", "artifact_id": nid, "source_id": sid})
                    bad_nodes.add(nid)
            else:
                parent = ref["artifact_id"]; dependents[parent].append(nid)
                if parent not in nodes:
                    diagnostics.append({"code": "unknown_artifact_reference", "artifact_id": nid, "reference": parent})
                    bad_nodes.add(nid)
    for cycle in _cycles(nodes):
        diagnostics.append({"code": "dependency_cycle", "path": cycle}); bad_nodes.update(cycle)
    if graph["coverage"] == "partial":
        diagnostics.append({"code": "partial_dependency_coverage", "detail": "Unlisted dependents are outside this review queue."})
    queue = deque(sorted(bad_nodes))
    while queue:
        for child in dependents[queue.popleft()]:
            if child not in bad_nodes:
                bad_nodes.add(child); queue.append(child)
    impacts = {nid: {"artifact_id": nid, "kind": n["kind"], "locator": n["locator"],
                     "causes": [], "mapping_incomplete": nid in bad_nodes} for nid, n in sorted(nodes.items())}
    for sid, change in sorted(change_map.items()):
        if change["change_type"] == "unchanged":
            continue
        queue = deque((n, [f"source:{sid}", f"artifact:{n}"]) for n in sorted(source_users[sid]))
        seen = set()
        while queue:
            nid, witness = queue.popleft()
            if nid in seen:
                continue
            seen.add(nid)
            impacts[nid]["causes"].append({"source_id": sid, "change_type": change["change_type"], "path": witness})
            for child in sorted(dependents[nid]):
                queue.append((child, witness + [f"artifact:{child}"]))
    for row in impacts.values():
        types = {c["change_type"] for c in row["causes"]}
        if row["mapping_incomplete"] or "comparison_unavailable" in types:
            row["action"] = "resolve_comparison_or_mapping"
        elif types - {"metadata_only"}:
            row["action"] = "review_content_and_interpretation"
        elif types:
            row["action"] = "review_metadata_and_locators"
        else:
            row["action"] = "no_detected_change_in_declared_dependencies"
    unavailable = any(c["change_type"] == "comparison_unavailable" for c in changes)
    changed = any(c["change_type"] != "unchanged" for c in changes)
    incomplete = unavailable or bool(diagnostics) or before["coverage"] == "partial" or after["coverage"] == "partial"
    report = {"schema": REPORT, "status": "INCOMPLETE" if incomplete else "REVIEW_REQUIRED" if changed else "NO_DETECTED_CHANGE",
              "notice": "Review assistance only. No findings, ratings, recommendations, or source files were changed.",
              "scope": copy.deepcopy(before["scope"]), "namespace": before["namespace"],
              "snapshots": [{k: m[k] for k in ("snapshot_id", "captured_at", "coverage")} for m in (before, after)],
              "input_sha256": {"before": digest(before), "after": digest(after), "dependencies": digest(graph)},
              "counts": dict(sorted(Counter(c["change_type"] for c in changes).items())),
              "source_changes": changes, "artifacts": list(impacts.values()), "diagnostics": diagnostics,
              "unmapped_changed_sources": sorted(c["source_id"] for c in changes
                                                 if c["change_type"] != "unchanged" and not source_users[c["source_id"]]),
              "dependency_coverage": graph["coverage"],
              "witness_policy": "One deterministic shortest dependency path per changed source/artifact pair; original graph retains all edges."}
    return copy.deepcopy(report)


def adapt_authority(bundle, snapshot_id, captured_at, *, coverage, provenance=None):
    """Losslessly retain record fields; no authority verification or rating operation."""
    _require(isinstance(bundle, dict) and bundle.get("schema") == "uiowa-rfq18649-evidence-authority/v2",
             "unsupported authority bundle")
    for name in ("generation", "solicitation_id", "prime_candidate"):
        _string(bundle.get(name), name)
    _require(isinstance(bundle.get("sources"), list), "authority.sources: array required")
    sources = []
    for record in bundle["sources"]:
        _require(isinstance(record, dict), "authority source: object required")
        required = {"source_id", "authority_generation", "source_content_sha256", "prime_candidate", "solicitation_id"}
        _require(required <= set(record), "authority source: missing identity/content fields")
        for field, top in (("authority_generation", "generation"), ("prime_candidate", "prime_candidate"),
                           ("solicitation_id", "solicitation_id")):
            _require(record[field] == bundle[top], f"authority source {record['source_id']}: {field} mismatch")
        interpretation = {k: copy.deepcopy(v) for k, v in record.items() if k in {"claim", "maturity", "confidence_bp"}}
        reserved = {"source_id", "authority_generation", "source_content_sha256"} | set(interpretation)
        sources.append({"id": record["source_id"], "revision": record["authority_generation"],
                        "content": {"representation": "authority-source-content-sha256/v2", "sha256": record["source_content_sha256"]},
                        "metadata": {k: copy.deepcopy(v) for k, v in record.items() if k not in reserved},
                        "interpretation": interpretation})
    result = {"schema": MANIFEST, "snapshot_id": snapshot_id, "captured_at": captured_at,
              "namespace": "uiowa-evidence-authority/v2", "coverage": coverage,
              "scope": {"solicitation_id": bundle["solicitation_id"], "prime_candidate": bundle["prime_candidate"]},
              "sources": sources, "provenance": {"adapter": "authority-v2", "bundle_sha256": digest(bundle),
                 "bundle_header": {k: copy.deepcopy(v) for k, v in bundle.items() if k != "sources"},
                 "operator_context": copy.deepcopy(provenance or {}),
                 "notice": "Declared source digests, not inspected source text; no authority verification performed."}}
    validate_manifest(result)
    return result


def _cell(value):
    return html.escape(str(value), quote=False).replace("\\", "\\\\").replace("|", "\\|").replace("\r", "\\r").replace("\n", "\\n")


def render_markdown(report):
    lines = ["# Source-version impact review", "", f"Status: **{report['status']}**", "", report["notice"], "",
             "Source changes are not University findings. Dependency coverage: " + report["dependency_coverage"], "",
             "| Source | Change | Before revision | After revision | Explanation |", "|---|---|---|---|---|"]
    for r in report["source_changes"]:
        lines.append("| " + " | ".join(_cell(r[k]) for k in ("source_id", "change_type", "before_revision", "after_revision", "reason")) + " |")
    lines += ["", "## Artifact review queue", "", "| Artifact | Kind | Action | Changed sources |", "|---|---|---|---|"]
    for r in report["artifacts"]:
        lines.append("| " + " | ".join(map(_cell, (r["artifact_id"], r["kind"], r["action"], ", ".join(c["source_id"] for c in r["causes"])))) + " |")
    lines += ["", "## Exact field changes and dependency witnesses", ""]
    for r in report["source_changes"]:
        if r["metadata_changes"] or r["interpretation_changes"] or r["revision_changed"] or r["text_change"]:
            lines += [f"### {_cell(r['source_id'])}", "", "    " + canonical({k: r[k] for k in ("metadata_changes", "interpretation_changes", "before_revision", "after_revision", "revision_changed", "text_change")}), ""]
    for r in report["artifacts"]:
        for cause in r["causes"]:
            lines.append("- " + _cell(" → ".join(cause["path"])) + " (" + cause["change_type"] + ")")
    lines += ["", "## Diagnostics", "", "    " + canonical(report["diagnostics"]), "",
              "Unmapped changed sources: " + _cell(", ".join(report["unmapped_changed_sources"]) or "none"), "",
              report["witness_policy"], "", "Input digests: " + canonical(report["input_sha256"]), ""]
    return "\n".join(lines)


def render_html(report):
    esc = lambda x: html.escape(str(x), quote=True)
    anchor = lambda x: "s-" + hashlib.sha256(x.encode()).hexdigest()[:20]
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">',
             '<title>Source-version impact review</title><style>body{font:18px/1.5 system-ui;margin:2rem;max-width:100rem}table{border-collapse:collapse;width:100%}td,th{border:1px solid;padding:.6rem;text-align:left;vertical-align:top;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere}a:focus,summary:focus{outline:3px solid}caption{text-align:left;font-weight:bold;padding:1rem 0}@media print{body{font-size:11pt;margin:0}thead{display:table-header-group}tr{break-inside:avoid}}</style>',
             '<main><h1>Source-version impact review</h1>', '<p><strong>' + esc(report["status"]) + '</strong></p>',
             '<p>' + esc(report["notice"]) + '</p><p>Preparation example only, not University findings. Dependency coverage: ' + esc(report["dependency_coverage"]) + '</p>',
             '<table><caption>Source comparisons</caption><thead><tr><th scope="col">Source</th><th scope="col">Change</th><th scope="col">Explanation and exact fields</th></tr></thead><tbody>']
    for r in report["source_changes"]:
        parts.append('<tr id="' + anchor(r["source_id"]) + '"><th scope="row">' + esc(r["source_id"]) + '</th><td>' + esc(r["change_type"]) + '</td><td>' + esc(r["reason"]) + '<details><summary>Versions, fingerprints and field changes</summary><pre>' + esc(json.dumps(r, ensure_ascii=False, indent=2, sort_keys=True)) + '</pre></details></td></tr>')
    parts.append('</tbody></table><h2>Artifact review queue</h2>')
    for r in report["artifacts"]:
        parts.append('<section><h3>' + esc(r["artifact_id"]) + '</h3><p>' + esc(r["kind"] + ' · ' + r["action"]) + '</p><p>Locator: <code>' + esc(r["locator"]) + '</code></p><ul>')
        for c in r["causes"]:
            parts.append('<li><a href="#' + anchor(c["source_id"]) + '">' + esc(c["source_id"]) + '</a>: ' + esc(' → '.join(c["path"])) + '</li>')
        parts.append('</ul></section>')
    parts += ['<h2>Diagnostics and unmapped changes</h2><pre>' + esc(json.dumps({"diagnostics": report["diagnostics"], "unmapped_changed_sources": report["unmapped_changed_sources"]}, ensure_ascii=False, indent=2)) + '</pre>', '<p>' + esc(report["witness_policy"]) + '</p><pre>' + esc(canonical(report["input_sha256"])) + '</pre></main></html>\n']
    return "\n".join(parts)


def render_csv(report):
    def safe(value):
        value = str(value)
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["artifact_id", "kind", "locator", "action", "changed_source_ids", "witnesses", "mapping_incomplete"])
    for r in report["artifacts"]:
        writer.writerow([safe(v) for v in (r["artifact_id"], r["kind"], r["locator"], r["action"],
                          canonical([c["source_id"] for c in r["causes"]]), canonical([c["path"] for c in r["causes"]]), r["mapping_incomplete"])])
    return output.getvalue()


def write_report(report, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    formats = {"report.json": json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
               "report.md": render_markdown(report), "report.html": render_html(report), "review-queue.csv": render_csv(report)}
    for name, content in formats.items():
        with (directory / name).open("x", encoding="utf-8", newline="") as handle:
            handle.write(content)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    compare = commands.add_parser("compare")
    for name in ("before", "after", "dependencies"):
        compare.add_argument(name, type=Path)
    compare.add_argument("--out-dir", type=Path, required=True, help="new directory; existing results are never overwritten")
    adapt = commands.add_parser("adapt-authority")
    adapt.add_argument("input", type=Path); adapt.add_argument("output", type=Path)
    adapt.add_argument("--snapshot-id", required=True); adapt.add_argument("--captured-at", required=True)
    adapt.add_argument("--coverage", required=True, choices=("complete", "partial"))
    args = parser.parse_args(argv)
    try:
        if args.command == "compare":
            report = analyze(load_json(args.before), load_json(args.after), load_json(args.dependencies))
            write_report(report, args.out_dir)
            print(canonical({"status": report["status"], "counts": report["counts"], "output": str(args.out_dir)}))
            return 2 if report["status"] == "INCOMPLETE" else 0
        result = adapt_authority(load_json(args.input), args.snapshot_id, args.captured_at, coverage=args.coverage)
        with args.output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return 0
    except (InputError, ValueError, TypeError, OSError, UnicodeError, RecursionError) as exc:
        print(f"INPUT_OR_OUTPUT_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
