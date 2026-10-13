"""Read-only before/after inspection of canonical identity-map reports.

This consumer preserves both snapshots and never reconciles or approves an ID.
A report seal checks content integrity, not the truth of its source statements.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
from html import escape
import json
from pathlib import Path
import sys
from typing import Any

SOURCE_SCHEMA = "uiowa.identity-map.v1"
SCHEMA = "uiowa.identity-import-impact.v1"
KEY_FIELDS = ("namespace", "kind", "id", "revision")
MAX_BYTES = 16 * 1024 * 1024


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _text(value: Any, label: str) -> str:
    _require(type(value) is str and bool(value.strip()), label + " must be nonempty text")
    return value


def _objects(value: Any, label: str) -> list:
    _require(type(value) is list and all(type(row) is dict for row in value), label + " must be an array of objects")
    return value


def _unique(rows: list, field: str, label: str) -> dict:
    result = {}
    for row in rows:
        ident = _text(row.get(field), label + "." + field)
        _require(ident not in result, "duplicate " + label + ": " + ident)
        result[ident] = row
    return result


def original_key(row: dict) -> tuple[str, ...]:
    original = row.get("original")
    _require(type(original) is dict, "record.original must be an object")
    return tuple(_text(original.get(k), "record.original." + k) for k in KEY_FIELDS)


def source_digest(report: dict) -> str:
    unsigned = {k: v for k, v in report.items() if k != "snapshot_sha256"}
    raw = (SOURCE_SCHEMA + "/report\0" + canonical(unsigned)).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def inspect_snapshot(report: dict) -> tuple[dict, dict]:
    """Validate the consumed envelope, seal and references, not mapping semantics."""
    _require(type(report) is dict and report.get("schema") == SOURCE_SCHEMA, "unsupported report schema")
    _require(report.get("assessment_authority") is False, "report must disclaim assessment authority")
    _require(report.get("snapshot_sha256") == source_digest(report), "snapshot seal mismatch")
    rows = _objects(report.get("records"), "records")
    by_id = _unique(rows, "occurrence_id", "record")
    by_key = {}
    for row in rows:
        key = original_key(row)
        _require(key not in by_key, "duplicate original occurrence key")
        by_key[key] = row
        _text(row.get("entity_id"), "entity_id")
        _text(row.get("equivalence_group"), "equivalence_group")
        _require(type(row.get("duplicate_count")) is int and row["duplicate_count"] >= 1, "duplicate_count must include the first occurrence")
        _require(type(row["original"].get("synthetic")) is bool, "record.original.synthetic must be boolean")
    links = _unique(_objects(report.get("links"), "links"), "link_id", "link")
    for row in links.values():
        _require(type(row.get("original")) is dict, "link.original must be an object")
        states = []
        for side in ("from", "to"):
            endpoint = row.get(side)
            _require(type(endpoint) is dict and type(endpoint.get("selector")) is dict, "endpoint selector must be an object")
            state = endpoint.get("status")
            _require(state in ("resolved", "ambiguous", "missing"), "unsupported endpoint status")
            candidates = endpoint.get("candidate_ids")
            _require(type(candidates) is list and all(type(x) is str for x in candidates), "candidate_ids must be text array")
            _require(len(set(candidates)) == len(candidates) and all(x in by_id for x in candidates), "candidate is duplicate or absent from snapshot")
            selected = endpoint.get("resolved_id")
            expected = "missing" if not candidates else "resolved" if len(candidates) == 1 else "ambiguous"
            _require(state == expected, "endpoint status disagrees with candidate count")
            _require((state == "resolved" and selected == candidates[0]) or (state != "resolved" and selected is None), "endpoint selected ID disagrees with status")
            states.append(state)
        expected = "resolved" if states == ["resolved", "resolved"] else "unresolved"
        _require(row.get("status") == expected, "link status disagrees with endpoints")
    return by_key, links


def _endpoint_delta(before: dict, after: dict) -> dict:
    declaration_changed = before["selector"] != after["selector"]
    selected_changed = before["resolved_id"] != after["resolved_id"]
    retargeted = (not declaration_changed and before["status"] == after["status"] == "resolved"
                  and selected_changed)
    return {"before": deepcopy(before), "after": deepcopy(after),
            "declaration_changed": declaration_changed,
            "resolution_changed": before["status"] != after["status"] or selected_changed,
            "candidate_set_changed": set(before["candidate_ids"]) != set(after["candidate_ids"]),
            "retargeted_without_selector_change": retargeted}


def compare(before: dict, after: dict) -> dict:
    old, old_links = inspect_snapshot(before)
    new, new_links = inspect_snapshot(after)
    unchanged, changed = [], []
    for key in sorted(old.keys() & new.keys()):
        left, right = old[key], new[key]
        if left == right:
            unchanged.append({"key": list(key), "occurrence_id": left["occurrence_id"]})
            continue
        changed.append({"key": list(key), "before": deepcopy(left), "after": deepcopy(right),
                        "occurrence_rekeyed": left["occurrence_id"] != right["occurrence_id"],
                        "original_changed_without_new_revision": left["original"] != right["original"],
                        "entity_id_changed": left["entity_id"] != right["entity_id"],
                        "equivalence_snapshot_changed": left["equivalence_group"] != right["equivalence_group"],
                        "duplicate_count_changed": left["duplicate_count"] != right["duplicate_count"]})
    added = [deepcopy(new[k]) for k in sorted(new.keys() - old.keys())]
    removed = [deepcopy(old[k]) for k in sorted(old.keys() - new.keys())]
    same_links, changed_links = [], []
    for lid in sorted(old_links.keys() & new_links.keys()):
        left, right = old_links[lid], new_links[lid]
        if left == right:
            same_links.append(lid)
            continue
        endpoints = {side: _endpoint_delta(left[side], right[side]) for side in ("from", "to")}
        changed_links.append({"link_id": lid, "before": deepcopy(left), "after": deepcopy(right),
                              "declaration_changed": left["original"] != right["original"],
                              "newly_unresolved": left["status"] == "resolved" and right["status"] == "unresolved",
                              "newly_resolved": left["status"] == "unresolved" and right["status"] == "resolved",
                              "endpoints": endpoints})
    unresolved_after = [deepcopy(new_links[lid]) for lid in sorted(new_links)
                        if new_links[lid]["status"] == "unresolved"]
    summary = {"occurrences_before": len(old), "occurrences_after": len(new),
               "occurrences_added": len(added), "occurrences_removed": len(removed),
               "occurrences_unchanged": len(unchanged), "occurrences_changed": len(changed),
               "same_key_rekeys": sum(r["occurrence_rekeyed"] for r in changed),
               "same_revision_original_changes": sum(r["original_changed_without_new_revision"] for r in changed),
               "links_before": len(old_links), "links_after": len(new_links),
               "links_changed": len(changed_links), "links_unchanged": len(same_links),
               "links_added": len(new_links.keys() - old_links.keys()),
               "links_removed": len(old_links.keys() - new_links.keys()),
               "newly_unresolved_links": sum(r["newly_unresolved"] for r in changed_links),
               "newly_resolved_links": sum(r["newly_resolved"] for r in changed_links),
               "unresolved_before": sum(r["status"] == "unresolved" for r in old_links.values()),
               "unresolved_after": len(unresolved_after),
               "retargeted_endpoints_without_selector_change": sum(e["retargeted_without_selector_change"] for r in changed_links for e in r["endpoints"].values())}
    return {"schema": SCHEMA, "assessment_authority": False,
            "interpretation": "Observed import changes only; no automatic join, rating, approval, or attribution of cause.",
            "summary": summary,
            "records": {"added": added, "removed": removed, "unchanged": unchanged, "changed": changed},
            "links": {"added": [deepcopy(new_links[k]) for k in sorted(new_links.keys() - old_links.keys())],
                      "removed": [deepcopy(old_links[k]) for k in sorted(old_links.keys() - new_links.keys())],
                      "unchanged": same_links, "changed": changed_links, "unresolved_after": unresolved_after},
            "snapshots": {"before": deepcopy(before), "after": deepcopy(after)}}


def render_html(result: dict) -> str:
    """Portable, script-free reviewer view. Every source-derived value is escaped."""
    esc = lambda value: escape(str(value), quote=True)
    summary = result["summary"]
    snapshots = result["snapshots"]
    synthetic = any(report["records"] for report in snapshots.values()) and all(row["original"]["synthetic"] for report in snapshots.values() for row in report["records"])
    banner = ("SYNTHETIC DEMONSTRATION — not University findings" if synthetic else
              "LOCAL INSPECTION — source content is not independently validated")
    cards = [("New occurrences", summary["occurrences_added"], "Original identities retained, not folded into a lookalike."),
             ("Unchanged occurrences", summary["occurrences_unchanged"], "The complete original record and occurrence ID stayed the same."),
             ("Newly unresolved links", summary["newly_unresolved_links"], "Previously selected references now need inspection."),
             ("Newly resolved links", summary["newly_resolved_links"], "Previously unresolved references now have a selected target.")]
    out = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
           '<title>Identity import impact — inspection only</title><style>',
           'body{margin:0;background:#f3f5f7;color:#152536;font:16px/1.55 system-ui,sans-serif}main{max-width:1120px;margin:auto;padding:32px 24px 64px}h1{font-size:clamp(30px,5vw,46px);line-height:1.12;max-width:850px;margin:18px 0}h2{font-size:24px;margin:32px 0 12px}h3{font-size:18px;margin:0 0 8px}p{margin:10px 0}.banner{display:inline-block;padding:6px 10px;background:#fff0cc;border:1px solid #8a640f;font-weight:700;font-size:12px;letter-spacing:.04em}.intro{max-width:820px;color:#415466}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:24px 0}.card,.change,details{background:white;border:1px solid #bac7d2;border-radius:8px;padding:18px}.number{display:block;font-size:40px;font-weight:750;line-height:1.1;margin:10px 0}.small{font-size:13px;color:#415466}.note{padding:16px 18px;background:#e4edf5;border-left:4px solid #244f72}.change{margin:14px 0}.status{display:inline-block;padding:3px 8px;border:1px solid #687d91;border-radius:4px;font-weight:650;margin:4px 0}.hash,code,pre{font:13px/1.55 ui-monospace,monospace;overflow-wrap:anywhere;white-space:pre-wrap}.hash{padding:10px;background:#e9eef3;margin:6px 0}table{border-collapse:collapse;min-width:650px;width:100%;font-size:14px}th,td{text-align:left;border-bottom:1px solid #cad3dc;padding:10px;vertical-align:top}th{background:#e9eef3}.table-scroll{overflow:auto;max-width:100%;border:1px solid #bac7d2;border-radius:6px}summary{cursor:pointer;font-weight:650}details{margin:16px 0}pre{max-height:420px;overflow:auto}footer{margin-top:30px;border-top:1px solid #bac7d2;padding-top:16px}.break{overflow-wrap:anywhere}@media(max-width:800px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}main{padding:24px 16px 40px}}@media(max-width:420px){.cards{gap:10px}.card{padding:12px}.number{font-size:32px}}@media print{body{background:white}main{max-width:none;padding:0}.cards{grid-template-columns:repeat(4,minmax(0,1fr))}.change,.card{break-inside:avoid}.table-scroll{overflow:visible}details{display:none}}',
           '</style><main>', '<div class="banner">' + banner + '</div>',
           '<h1>What changed in this import?</h1>',
           '<p class="intro">A new source can make an unqualified reference ambiguous without changing any existing occurrence ID. This view shows the transitions that aggregate counts can conceal.</p>',
           '<div class="cards">']
    for title, value, description in cards:
        out.append('<section class="card"><h3>' + esc(title) + '</h3><span class="number">' + esc(value) + '</span><p class="small">' + esc(description) + '</p></section>')
    out.append('</div><div class="note"><strong>Unresolved totals: ' + esc(summary["unresolved_before"]) + ' before → ' + esc(summary["unresolved_after"]) + ' after.</strong> Equal totals do not prove that the same references are unresolved. No reference is automatically selected or approved here.</div>')
    out.append('<h2>Changed references</h2>')
    if not result["links"]["changed"]:
        out.append('<p>No common reference changed. Added, removed and unresolved references remain in the full report below.</p>')
    for row in result["links"]["changed"]:
        out.append('<section class="change"><h3 class="break">' + esc(row["link_id"]) + '</h3><div class="status">' + esc(row["before"]["status"]) + ' → ' + esc(row["after"]["status"]) + '</div>')
        out.append('<p>' + ('The link declaration changed; do not attribute the transition to imported records alone.' if row["declaration_changed"] else 'The original link declaration is unchanged.') + '</p>')
        for side, delta in row["endpoints"].items():
            left, right = delta["before"], delta["after"]
            if left == right:
                continue
            out.append('<p><strong>' + esc(side) + ' endpoint:</strong> ' + esc(left["status"]) + ' → ' + esc(right["status"]) + '; candidate count ' + str(len(left["candidate_ids"])) + ' → ' + str(len(right["candidate_ids"])) + '.</p>')
            out.append('<div class="hash">Selector: ' + esc(canonical(right["selector"])) + '</div>')
            out.append('<p class="small">Selected occurrence after import: <span class="break">' + esc(right["resolved_id"] or 'None — unresolved') + '</span></p>')
            if delta["retargeted_without_selector_change"]:
                out.append('<p><strong>Inspect: the same selector now resolves to a different occurrence.</strong></p>')
        out.append('</section>')
    out.append('<h2>Identity preservation</h2><p>' + str(summary["occurrences_before"]) + ' occurrences before; ' + str(summary["occurrences_after"]) + ' after; ' + str(summary["occurrences_removed"]) + ' removed.</p>')
    out.append('<p>Same-key rekeys: <strong>' + str(summary["same_key_rekeys"]) + '</strong>. Original changes without a new revision: <strong>' + str(summary["same_revision_original_changes"]) + '</strong>. Equivalence-group IDs are snapshot membership labels, not stable occurrence IDs.</p>')
    out.append('<h2>Still unresolved after import</h2><div class="table-scroll" tabindex="0" role="region" aria-label="Unresolved references; scroll horizontally on narrow screens"><table><caption class="small">Every unresolved link remains visible, including unchanged ones.</caption><thead><tr><th scope="col">Link</th><th scope="col">From endpoint</th><th scope="col">To endpoint</th><th scope="col">Selected target</th></tr></thead><tbody>')
    for row in result["links"]["unresolved_after"]:
        out.append('<tr><td class="break">' + esc(row["link_id"]) + '</td><td>' + esc(row["from"]["status"]) + '</td><td>' + esc(row["to"]["status"]) + '</td><td class="break">' + esc(row["to"]["resolved_id"] or 'None') + '</td></tr>')
    out.append('</tbody></table></div><h2>Exact input snapshots</h2>')
    for label, report in snapshots.items():
        out.append('<p><strong>' + esc(label.title()) + '</strong></p><div class="hash">' + esc(report["snapshot_sha256"]) + '</div>')
    out.append('<details><summary>Full lossless comparison and both original snapshots</summary><pre>' + esc(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)) + '</pre></details>')
    out.append('<footer class="small">Inspection only. Content seals identify the supplied snapshots; they do not authenticate evidence, prove correct mapping, assign a maturity rating, or authorize an action. Original source declarations and unresolved references are retained in the full comparison.</footer></main></html>')
    return '\n'.join(out) + '\n'


def load_report(path: Path) -> dict:
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    _require(len(raw) <= MAX_BYTES, 'report exceeds the 16 MiB input limit')
    def pairs(items):
        value = {}
        for key, item in items:
            _require(key not in value, 'duplicate JSON key: ' + key)
            value[key] = item
        return value
    def bad_constant(value):
        raise ValueError('non-finite JSON constant: ' + value)
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=bad_constant)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    parser.add_argument('--format', choices=('json', 'html'), default='json')
    args = parser.parse_args(argv)
    try:
        result = compare(load_report(args.before), load_report(args.after))
        print(render_html(result) if args.format == 'html' else json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    except (OSError, ValueError, TypeError, RecursionError, UnicodeError) as exc:
        print('identity-import-impact: ' + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
