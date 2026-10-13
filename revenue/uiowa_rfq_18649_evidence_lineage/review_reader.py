"""Package one existing lineage comparison as an offline, read-only HTML review."""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
from typing import Any

import lineage


def escaped(value: Any) -> str:
    return html.escape(str(value), quote=True)


def pretty(value: Any) -> str:
    return escaped(lineage.encoded(value).rstrip())


def read_report(path: Path) -> tuple[bytes, dict]:
    with path.open("rb") as stream:
        raw = stream.read(lineage.MAX_BYTES + 1)
    lineage.require(len(raw) <= lineage.MAX_BYTES, "Report exceeds the engine's 16 MiB input limit")
    report = json.loads(raw.decode("utf-8"), object_pairs_hook=lineage._pairs,
                        parse_constant=lineage._constant)
    lineage.require(isinstance(report, dict) and report.get("schema") == lineage.SCHEMA,
                    "Expected a uiowa.evidence-lineage.v1 comparison report")
    lineage.text(report.get("status"), "report.status")
    lineage.require(type(report.get("synthetic")) is bool, "report.synthetic must be a boolean")
    for side in ("before", "after"):
        lineage.validate_manifest(report.get(side))
    for name in ("finding_impacts", "changes", "departures", "duplicates_after", "anomalies", "limitations"):
        lineage.require(isinstance(report.get(name), list), f"report.{name} must be a list")
    findings = report.get("input_findings")
    lineage.require(isinstance(findings, dict) and isinstance(findings.get("findings"), list),
                    "report.input_findings.findings must be a list")
    for finding in findings["findings"]:
        lineage.require(isinstance(finding, dict), "Finding record must be an object")
        lineage.text(finding.get("finding_id"), "finding.finding_id")
    for impact in report["finding_impacts"]:
        lineage.require(isinstance(impact, dict), "Finding impact must be an object")
        lineage.text(impact.get("finding_id"), "impact.finding_id")
        lineage.text(impact.get("status"), "impact.status")
        refs = []
        if "citation" in impact:
            refs.append(impact["citation"])
        for field in ("retained_exact_copies", "declared_successors", "missing_declared_successors"):
            rows = impact.get(field, [])
            lineage.require(isinstance(rows, list), f"impact.{field} must be a list")
            refs.extend(rows)
        for ref in refs:
            lineage.require(isinstance(ref, dict), "Citation or successor reference must be an object")
            lineage.text(ref.get("record_id"), "reference.record_id")
            lineage.digest(ref.get("sha256"), "reference.sha256")
    return raw, report


def render(raw: bytes, report: dict) -> str:
    sources: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for side in ("before", "after"):
        for index, record in enumerate(report[side]["records"]):
            sources.setdefault(lineage.ref_key(record), []).append((side, f"source-{side}-{index}"))
    finding_links: dict[str, list[str]] = {}
    for index, finding in enumerate(report["input_findings"]["findings"]):
        finding_links.setdefault(finding["finding_id"], []).append(f"finding-{index}")

    def reference(ref: dict) -> str:
        links = sources.get(lineage.ref_key(ref), [])
        destinations = " · ".join(f'<a href="#{anchor}">{side} source</a>' for side, anchor in links)
        return (f'<li><strong>{escaped(ref["record_id"])}</strong> · {destinations or "No matching source record supplied"}'
                f'<code>{escaped(ref["sha256"])}</code></li>')

    def group(title: str, refs: list, empty: str) -> str:
        content = '<ul class="refs">' + "".join(reference(ref) for ref in refs) + "</ul>" if refs else f"<p>{empty}</p>"
        return f'<section class="ref-group"><h3>{title}</h3>{content}</section>'

    impacts = report["finding_impacts"]
    statuses = list(dict.fromkeys(row["status"] for row in impacts))
    parts = [f'<p class="classification">{escaped(report["status"])} · '
             + ("Synthetic collections" if report["synthetic"] else "Not marked wholly synthetic; handle as potentially private") + "</p>",
             f'<h1>{escaped(report["before"]["collection_id"])} → {escaped(report["after"]["collection_id"])}</h1>',
             '<p class="boundary">This page presents the supplied report; it does not rerun the comparator, authenticate evidence, '
             'or grant approval. Omission is not deletion. A supplied revision is not necessarily current or approved.</p>',
             f'<p class="counts">{len(report["before"]["records"])} previous records · {len(report["after"]["records"])} supplied after · '
             f'{len(report["input_findings"]["findings"])} finding records · {len(impacts)} citation-impact rows</p>',
             '<nav class="jump" aria-label="Report sections"><a href="#queue">Finding queue</a> <a href="#sources">Source records</a> '
             '<a href="#collection-changes">Collection changes</a> <a href="#original-report">Original report</a></nav>',
             '<section id="queue"><h2>Which finding needs another look?</h2><div class="filters">'
             '<label>Search findings, citations and statuses<input id="search" type="search" placeholder="Finding ID, record, locator…"></label>'
             '<label>Reported status<select id="status"><option value="">All statuses</option>',
             "".join(f'<option value="{escaped(status)}">{escaped(status)}</option>' for status in statuses),
             '</select></label><button id="clear" type="button">Clear filters</button></div>'
             '<p id="visible-count" role="status" aria-live="polite"></p><p id="empty" hidden>No impact rows match these filters.</p>']
    for index, impact in enumerate(impacts):
        citation = impact.get("citation")
        source = citation["record_id"] if citation else "No citation supplied"
        locator = str(citation.get("locator", "No locator supplied")) if citation else "No locator supplied"
        links = " · ".join(f'<a href="#{anchor}">Original finding</a>' for anchor in finding_links.get(impact["finding_id"], []))
        parts.extend([f'<details class="impact" id="impact-{index}" data-status="{escaped(impact["status"])}" open>',
                      f'<summary><strong>{escaped(impact["finding_id"])}</strong><span class="status">{escaped(impact["status"])}</span>'
                      f'<span class="citation">{escaped(source)} · {escaped(locator)}</span></summary><div class="impact-body">',
                      f'<p>{links or "No matching original finding record supplied"} · '
                      f'Locator validation: {escaped(impact.get("locator_validation", "Not supplied"))}</p>'])
        if citation:
            parts.append(group("Original citation", [citation], ""))
        parts.append('<div class="reference-grid">')
        parts.append(group("Supplied declared successors", impact.get("declared_successors", []), "None reported."))
        parts.append(group("Known but omitted successors", impact.get("missing_declared_successors", []), "None reported."))
        parts.append(group("Retained exact copies", impact.get("retained_exact_copies", []), "None reported."))
        parts.append(f'</div><details><summary>Full impact record</summary><pre>{pretty(impact)}</pre></details></div></details>')
    parts.append('</section><section id="sources"><h2>Preserved source records</h2>'
                 '<p>References resolve by both record ID and digest. Source locations are text, not automatic downloads.</p><div class="collections">')
    for side in ("before", "after"):
        parts.append(f'<section><h3>{"Previous collection" if side == "before" else "Supplied after collection"}</h3>')
        for index, record in enumerate(report[side]["records"]):
            passage = record.get("metadata", {}).get("example_text")
            parts.append(f'<details id="source-{side}-{index}" class="source"><summary><strong>{escaped(record["record_id"])}</strong> · '
                         f'{escaped(record["title"])} · {escaped(record["version"])}</summary>'
                         f'<p>Document: {escaped(record["document_id"])}<br>Location: {escaped(record["location"])}</p>'
                         f'<code>{escaped(record["sha256"])}</code>')
            if isinstance(passage, str):
                parts.append(f'<h4>Embedded example text (supplied metadata, not a validated locator)</h4><pre>{escaped(passage)}</pre>')
            else:
                parts.append('<p class="boundary">Passage text is not embedded. Consult the preserved locator in your own source collection.</p>')
            parts.append(f'<h4>Complete source record</h4><pre>{pretty(record)}</pre></details>')
        if not report[side]["records"]:
            parts.append('<p>No records in this supplied collection. This does not establish deletion.</p>')
        parts.append('</section>')
    parts.append('</div></section><section><h2>Original finding records</h2>')
    for index, finding in enumerate(report["input_findings"]["findings"]):
        parts.append(f'<details id="finding-{index}"><summary>{escaped(finding["finding_id"])}</summary><pre>{pretty(finding)}</pre></details>')
    parts.append('</section><section id="collection-changes"><h2>Collection changes and context</h2>')
    for field, title in (("changes", "Record changes"), ("departures", "Records absent from after"),
                         ("duplicates_after", "Duplicate-byte groups"), ("anomalies", "Reported anomalies"),
                         ("summary", "Supplied summary"), ("limitations", "Interpretation limits")):
        parts.append(f'<details><summary>{title}</summary><pre>{pretty(report.get(field))}</pre></details>')
    parts.append('</section><section id="original-report"><h2>Original report</h2>'
                 '<p>The complete report contains all supplied metadata. Sharing this HTML shares that information too.</p>'
                 '<button id="save-report" type="button">Save original JSON bytes</button>'
                 f'<p>File SHA-256: <code>{hashlib.sha256(raw).hexdigest()}</code></p>'
                 f'<details><summary>Complete original JSON text</summary><pre>{escaped(raw.decode("utf-8"))}</pre></details></section>')
    template = Path(__file__).with_name("review_reader.html").read_text(encoding="utf-8")
    for marker in ("__REVIEW_BODY__", "__REPORT_BASE64__"):
        lineage.require(template.count(marker) == 1, f"Reader template requires one {marker}")
    # Split the trusted template first; user text must never become another replacement target.
    before, tail = template.split("__REVIEW_BODY__")
    middle, after = tail.split("__REPORT_BASE64__")
    return before + "\n".join(parts) + middle + base64.b64encode(raw).decode("ascii") + after


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="existing lineage.py compare JSON")
    parser.add_argument("output", type=Path, help="new self-contained HTML filename")
    args = parser.parse_args()
    try:
        raw, report = read_report(args.report)
        result = render(raw, report).encode("utf-8")
        with args.output.open("xb") as stream:
            stream.write(result)
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        parser.exit(2, f"Could not create review page: {exc}\n")
    print(json.dumps({"output": str(args.output), "bytes": len(result),
                      "finding_impacts": len(report["finding_impacts"]), "comparator_rerun": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
