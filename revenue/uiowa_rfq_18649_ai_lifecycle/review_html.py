#!/usr/bin/env python3
"""Generate a portable, script-free reader of the existing AI lifecycle analysis."""
from __future__ import annotations

import argparse
import hashlib
import html
import os
import sys
from pathlib import Path
from typing import Any, Iterable

if __package__:
    from . import lifecycle
else:
    import lifecycle

MAX_INPUT_BYTES = 16 * 1024 * 1024
METRIC_LABELS = {
    "correctness": "Correctness (fraction / Boolean)",
    "completeness": "Completeness (0–1)",
    "usefulness": "Usefulness (0–1)",
    "repair_minutes": "Active repair (minutes)",
    "latency_ms": "Latency (milliseconds)",
}
CSS = """
:root{color-scheme:light;--ink:#192939;--muted:#526271;--line:#ccd5dc;
--paper:#fff;--wash:#f3f6f8;--accent:#075985}
*{box-sizing:border-box}html{scroll-behavior:auto}body{margin:0;background:var(--wash);
color:var(--ink);font:16px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
a{color:var(--accent);text-underline-offset:3px}a:hover{text-decoration-thickness:2px}
a:focus-visible,summary:focus-visible,[tabindex]:focus-visible{outline:3px solid #995400;outline-offset:3px}
.skip{display:block;padding:.7rem 1.3rem}header,main,footer{max-width:1180px;margin:auto;padding:1.5rem}
header{background:var(--ink);color:white;padding-top:2rem;padding-bottom:2rem}
header a{color:#d8efff}h1{font-size:clamp(2rem,5vw,3.3rem);line-height:1.12;margin:.5rem 0 1rem}
h2{font-size:1.65rem;margin:0 0 1rem}h3{font-size:1.2rem;margin:0 0 .6rem}h4{margin:1.2rem 0 .3rem}
p{margin:.65rem 0}nav ul{list-style:none;display:flex;flex-wrap:wrap;gap:.6rem 1.3rem;padding:0;margin:1.2rem 0 0}
section{margin:0 0 2rem;scroll-margin-top:1rem}article,.panel{background:var(--paper);border:1px solid var(--line);
border-radius:8px;padding:1.25rem;margin:1rem 0}article:target{outline:3px solid var(--accent);outline-offset:3px}
.eyebrow{font-weight:650;letter-spacing:.06em;font-size:.85rem}.notice{border-left:4px solid var(--accent);
padding:.7rem 1rem;background:#edf5f8}.muted,footer{color:var(--muted)}.state{display:inline-block;
font-family:ui-monospace,monospace;font-size:.9em;border:1px solid currentColor;border-radius:4px;padding:.1rem .4rem}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr));gap:1rem}
.grid .panel{margin:0}dl{display:grid;grid-template-columns:minmax(120px,1fr) 4fr;gap:.4rem 1rem}
dt{font-weight:650}dd{margin:0}dd,p,li,td,th,code{overflow-wrap:anywhere}ul{padding-left:1.3rem}
.table-wrap{overflow-x:auto;margin:1rem 0}table{border-collapse:collapse;width:100%;font-size:.93rem}
caption{text-align:left;font-weight:650;margin-bottom:.5rem}th,td{padding:.6rem .7rem;border:1px solid var(--line);
text-align:left;vertical-align:top}th{background:var(--wash)}tbody tr:nth-child(even){background:#f9fafb}
code,pre{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.88em}
pre,.literal{white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word}
pre{border:1px solid var(--line);padding:1rem;background:var(--wash)}summary{cursor:pointer;font-weight:650}
.back{font-size:.85rem;margin-top:1rem}footer{font-size:.9rem}
@media(max-width:600px){header,main,footer{padding:1rem}article,.panel{padding:.9rem}dl{grid-template-columns:1fr;gap:.15rem}
dd{margin-bottom:.6rem}th,td{padding:.45rem}table{font-size:.85rem}}
@media print{body,header{background:white;color:black;font-size:10pt}header a,a{color:inherit}
header,main,footer{max-width:none;padding:0}.skip,nav,.back{display:none}article,.panel{border-radius:0}
.table-wrap{overflow:visible}table{table-layout:fixed;font-size:8pt}thead{display:table-header-group}
tr{break-inside:avoid}h2,h3,h4,summary{break-after:avoid}section{margin-bottom:1.3rem}
pre{font-size:8pt}details>summary{list-style:none}details>pre{display:block}
.notice{background:white;border:1px solid black}.grid{display:block}.grid .panel{margin:.7rem 0}}
"""


def h(value: Any) -> str:
    """Render unknown, empty text, false, and zero as different values."""
    if value is None:
        return '<span class="muted">UNKNOWN</span>'
    if value == "":
        return '<span class="muted">EMPTY TEXT</span>'
    return html.escape(str(value), quote=True)


def anchor(kind: str, ident: str) -> str:
    # Separate namespaces and a reversible ASCII encoding avoid fragment collisions.
    return kind + "-" + ident.encode("utf-8").hex()


def link(kind: str, ident: str | None) -> str:
    if ident is None:
        return h(None)
    return f'<a href="#{anchor(kind, ident)}">{h(ident)}</a>'


def links(kind: str, identifiers: Iterable[str], empty: str = "None recorded") -> str:
    items = [link(kind, ident) for ident in identifiers]
    return ", ".join(items) if items else h(empty)


def bullets(values: Iterable[str], empty: str = "None recorded") -> str:
    items = list(values)
    return "<ul>" + "".join(f"<li>{h(x)}</li>" for x in items) + "</ul>" if items else f"<p>{h(empty)}</p>"


def table(caption: str, headers: list[str], rows: Iterable[list[str]]) -> str:
    """Cells are escaped text or generated markup, never unescaped record values."""
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    if not body:
        return f"<p>{h(caption)}: none recorded.</p>"
    return ('<div class="table-wrap" tabindex="0" role="region" aria-label="' + html.escape(caption, quote=True) + '">'
            + f"<table><caption>{h(caption)}</caption><thead><tr>"
            + "".join(f'<th scope="col">{h(x)}</th>' for x in headers)
            + f"</tr></thead><tbody>{body}</tbody></table></div>")


def facts(rows: Iterable[tuple[str, str]]) -> str:
    return "<dl>" + "".join(f"<dt>{h(label)}</dt><dd>{value}</dd>" for label, value in rows) + "</dl>"


def render(source: bytes, *, include_artifact_text: bool = False) -> str:
    """Analyze original UTF-8 record bytes with the canonical engine, then render.

    This deliberately does not accept a caller-supplied assessment projection.
    The input's artifact text is omitted unless explicitly requested.
    """
    if len(source) > MAX_INPUT_BYTES:
        raise ValueError(f"input exceeds {MAX_INPUT_BYTES} bytes")
    data = lifecycle.load(source.decode("utf-8"))
    report = lifecycle.analyze(data)
    versions = {v["id"]: v for v in data["versions"]}
    runs = {r["id"]: r for r in data["runs"]}
    sets = {s["artifact_ref"]: s for s in data["evaluation_sets"]}
    used_by: dict[str, set[tuple[str, str]]] = {a["id"]: set() for a in data["artifacts"]}

    def evidence(ident: str | None, kind: str, owner: str) -> str:
        if ident is not None:
            used_by[ident].add((kind, owner))
        return link("artifact", ident)

    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width,initial-scale=1">',
           '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">',
           f"<title>{h(report['workflow_id'])} — lifecycle investigation</title><style>{CSS}</style></head><body>",
           '<a class="skip" href="#review">Skip to review</a><header id="top">',
           '<div class="eyebrow">UIOWA-079 · PORTABLE INVESTIGATION READER</div>',
           f"<h1>{h(report['workflow_id'])}</h1><p>{h(data['description'])}</p>",
           f"<p><strong>{h(report['provenance'])}</strong><br>{h(report['authority'])} · Group: {h(report['group'])}</p>",
           '<p>No model execution, rescoring, live monitoring, deployment approval, or savings claim.</p>',
           '<nav aria-label="Review sections"><ul>' + "".join(f'<li><a href="#{key}">{label}</a></li>' for key, label in
           (("review", "Review focus"), ("versions", "Versions"), ("runs", "Runs"), ("comparisons", "Comparisons"),
            ("replays", "Recorded replays"), ("events", "Investigation trace"), ("cases", "Cases & sets"),
            ("artifacts", "Artifacts"))) + '</ul></nav></header><main>',
           '<section id="review"><h2>Review focus</h2><div class="notice">',
           '<p>UNKNOWN is not zero. Mean-of-known and paired subsets do not describe unobserved cases. '
           'Reported resolution is not independent proof of effectiveness.</p>',
           '<p>This file contains metadata and locators. ' +
           ('<strong>Retained artifact text is included; sharing the file shares that content.</strong>' if include_artifact_text else
            'Artifact text is omitted. Metadata itself may still be confidential.') + '</p></div>',
           f'<p class="muted">Original input SHA-256: <code>{hashlib.sha256(source).hexdigest()}</code>. '
           'This identifies supplied bytes; it is not an authenticity or approval certificate.</p><div class="grid">']
    focus = (
        ("Version evidence gaps", [("version", v["version_id"]) for v in report["timeline"] if v["reproduction_gaps"]]),
        ("Runs with missing metric values", [("run", r["run_id"]) for r in report["runs"] if any(m["missing"] for m in r["metrics"].values())]),
        ("Incomparable or subset comparisons", [("comparison", c["id"]) for c in report["comparisons"] if c["reasons"] or any(m["coverage"] != "complete" for m in c["metrics"].values())]),
        ("Open or unsupported-resolution incidents", [("event", e["id"]) for e in report["events"] if e["incident_state"] in ("open", "resolution_claim_without_evidence")]),
    )
    for title, items in focus:
        out += [f'<div class="panel"><h3>{title}</h3>',
                "<ul>" + "".join(f"<li>{link(k, ident)}</li>" for k, ident in items) + "</ul>" if items else
                '<p>None in this supplied analysis. This is not a completeness finding.</p>', '</div>']
    out += ['</div></section><section id="versions"><h2>Version lineage & reproduction evidence</h2>']
    for v in report["timeline"]:
        raw = versions[v["version_id"]]
        out += [f'<article id="{anchor("version", v["version_id"])}"><h3>{h(v["version_id"])}</h3>',
                facts((("Parent", link("version", v["parent_id"]) if v["parent_id"] is not None else "No parent declared"),
                       ("Changed at", h(v["changed_at"])), ("Reason", h(v["reason"])),
                       ("Support owner", h(v["support_owner"])), ("Model revision", h(raw["model_revision"])),
                       ("Mutable model alias", h(raw["model_alias_is_mutable"])), ("Seed", h(raw["seed"])),
                       ("Runs", links("run", v["run_ids"])), ("Replays", links("replay", v["replay_ids"])))),
                table("Component evidence", ["Component", "Artifact", "Recorded evidence state", "Locator (not fetched)"],
                      [[h(c["component"]), evidence(c["artifact_ref"], "version", v["version_id"]), h(c["state"]), h(c["locator"])] for c in v["components"]]),
                '<h4>Reproduction gaps reported by the analyzer</h4>',
                bullets(v["reproduction_gaps"], "None in the required metadata; this does not guarantee reproduction."), '</article>']
    out += ['</section><section id="runs"><h2>Runs & case-level evidence</h2>',
            '<p>Quality values are supplied observations, not judgments computed from the output text. '
            'False is a recorded Boolean outcome; UNKNOWN is missing evidence.</p>']
    for r in report["runs"]:
        raw = runs[r["run_id"]]
        observations = {o["case_id"]: o for o in raw["observations"]}
        expected = sets[versions[r["version_id"]]["components"]["evaluation_set"]]["case_ids"]
        out += [f'<article id="{anchor("run", r["run_id"])}"><h3>{h(r["run_id"])}</h3>',
                facts((("Version", link("version", r["version_id"])), ("Started", h(raw["started_at"])),
                       ("Finished", h(raw["finished_at"])), ("Missing observations", links("case", r["missing_case_ids"])),
                       ("Execution errors", links("case", r["error_case_ids"])))),
                table("Metric coverage — means of known values only", ["Metric / unit", "Known", "Expected", "Missing", "Mean of known"],
                      [[h(METRIC_LABELS[name])] + [h(m[k]) for k in ("known", "expected", "missing", "mean_of_known")] for name, m in r["metrics"].items()])]
        rows = []
        for ident in sorted(expected):
            o = observations.get(ident)
            rows.append([link("case", ident), "MISSING OBSERVATION" if o is None else "Recorded",
                         h(None) if o is None else evidence(o["output_ref"], "run", r["run_id"]),
                         "No observation" if o is None else h(o["error"]) if o["error"] is not None else "No error recorded"]
                        + [h(o[m] if o is not None else None) for m in lifecycle.METRICS])
        out += [table("All expected cases, including missing observations", ["Case", "Observation", "Output", "Error"]
                      + [METRIC_LABELS[m] for m in lifecycle.METRICS], rows), '</article>']
    out += ['</section><section id="comparisons"><h2>Explicit comparisons</h2>',
            '<p>All deltas are candidate minus baseline. These are recorded associations, not causal estimates. '
            'No comparison is silently selected or promoted to an approval.</p>']
    for c in report["comparisons"]:
        out += [f'<article id="{anchor("comparison", c["id"])}"><h3>{h(c["id"])}</h3>',
                f'<p class="state">{h(c["status"])}</p>',
                facts((("Baseline", link("run", c["baseline_run"])), ("Candidate", link("run", c["candidate_run"])),
                       ("Changed components", h(", ".join(c["changed_components"]) or "None recorded"))))]
        if c["reasons"]:
            out += ['<h4>Why numerical deltas are unavailable</h4>', bullets(c["reasons"])]
        else:
            out += [table("Paired comparison — retain coverage with every delta",
                          ["Metric / unit", "Paired / expected", "Baseline", "Candidate", "Delta", "Coverage", "Better direction", "Excluded cases"],
                          [[h(METRIC_LABELS[name]), f'{m["paired"]} / {m["expected"]}', h(m["baseline_mean"]),
                            h(m["candidate_mean"]), h(m["delta"]), h(m["coverage"]), h(m["better_direction"]),
                            links("case", m["excluded_case_ids"])] for name, m in c["metrics"].items()])]
        out += [f'<p>{h(c["interpretation"])}</p></article>']
    if not report["comparisons"]:
        out += ['<p>No comparisons declared.</p>']
    out += ['</section><section id="replays"><h2>Recorded replay outcomes</h2>',
            '<p>The analyzer compares supplied records; this reader does not run a model or reproduce an execution.</p>']
    for r in report["replays"]:
        out += [f'<article id="{anchor("replay", r["id"])}"><h3>{h(r["id"])}</h3><p class="state">{h(r["status"])}</p>',
                facts((("Version", link("version", r["version_id"])), ("Original run", link("run", r["original_run"])),
                       ("Repeat run", link("run", r["repeat_run"])), ("Compared hashes", h(r["compared"])),
                       ("Content verified / expected", f'{r["content_verified"]} / {r["expected"]}'),
                       ("Different outputs", links("case", r["mismatch_case_ids"])),
                       ("Unverified or missing cases", links("case", r["missing_case_ids"])))),
                f'<p>{h(r["limit"])}</p></article>']
    if not report["replays"]:
        out += ['<p>No replay records declared.</p>']
    out += ['</section><section id="events"><h2>Runtime & investigation trace</h2>']
    for e in report["events"]:
        out += [f'<article id="{anchor("event", e["id"])}"><h3>{h(e["id"])}</h3>',
                f'<p class="state">{h(e["kind"])} · {h(e["incident_state"])}</p>',
                facts((("Version", link("version", e["version_id"])), ("Occurred at", h(e["occurred_at"])),
                       ("Owner", h(e["owner"])), ("Summary", h(e["summary"])),
                       ("Related runs", links("run", e["related_run_ids"])),
                       ("Resolves incident", link("event", e["resolves_event_id"]) if e["resolves_event_id"] is not None else "None declared"),
                       ("Resolution record", link("event", e["resolution_event_id"]) if e["resolution_event_id"] is not None else "None recorded"),
                       ("Evidence", ", ".join(evidence(a, "event", e["id"]) for a in e["evidence_refs"]) or "None recorded"))), '</article>']
    if not report["events"]:
        out += ['<p>No events recorded.</p>']
    out += ['</section><section id="cases"><h2>Case definitions & evaluation sets</h2>']
    for c in sorted(data["cases"], key=lambda x: x["id"]):
        out += [f'<article id="{anchor("case", c["id"])}"><h3>{h(c["id"])}</h3>',
                facts((("Stratum", h(c["stratum"])), ("Input", evidence(c["input_ref"], "case", c["id"])),
                       ("Expected answer", evidence(c["expectation_ref"], "case", c["id"])))), '</article>']
    out += [table("Explicit evaluation-set membership", ["Manifest artifact", "Protocol", "Cases"],
                  [[link("artifact", s["artifact_ref"]), h(s["protocol_id"]), links("case", s["case_ids"])] for s in data["evaluation_sets"]]),
            '</section><section id="artifacts"><h2>Artifact register</h2>',
            '<p>Locators below are literal text, never fetched or converted to external links. '
            'Retained text is displayed as text, not HTML or executable content.</p>']
    for a in sorted(data["artifacts"], key=lambda x: x["id"]):
        out += [f'<article id="{anchor("artifact", a["id"])}"><h3>{h(a["id"])}</h3>',
                facts((("Kind", h(a["kind"])), ("Locator", h(a["locator"])), ("Retained declaration", h(a["retained"])),
                       ("Supplied SHA-256", f'<code>{h(a["sha256"])}</code>'),
                       ("Inline text", "Not supplied" if a["text"] is None else "Supplied; digest checked by the analyzer"),
                       ("Referenced by", ", ".join(link(k, ident) for k, ident in sorted(used_by[a["id"]])) or "No version, run, case or event references")))]
        if include_artifact_text and a["text"] is not None:
            out += ['<h4>Retained inline text</h4>', f'<pre class="literal">{h(a["text"])}</pre>']
        elif a["text"] is not None:
            out += ['<p class="muted">Text omitted from this export. Generate with --include-artifact-text only when appropriate.</p>']
        out += ['<p class="back"><a href="#top">Back to navigation</a></p></article>']
    out += ['</section><section id="limits"><h2>Interpretation limits</h2>', bullets(report["limits"]),
            '</section></main><footer>UIOWA-079 portable reader · Draft analysis of supplied records. '
            'Browser printing is a reader convenience, not a certified document or universal pagination guarantee. '
            'Retain the original JSON separately; HTML is not a lossless interchange format.</footer></body></html>']
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Original lifecycle JSON path, or - for stdin")
    parser.add_argument("--output", required=True, type=Path, help="New HTML file; existing paths are never overwritten")
    parser.add_argument("--include-artifact-text", action="store_true", help="Embed all supplied inline text; sharing HTML shares that content")
    args = parser.parse_args(argv)
    try:
        if args.input == "-":
            source = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        else:
            with Path(args.input).open("rb") as stream:
                source = stream.read(MAX_INPUT_BYTES + 1)
        document = render(source, include_artifact_text=args.include_artifact_text).encode("utf-8")
        # Render before creating output. Exclusive creation also refuses symlink aliases.
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(document)
        print(f"WROTE {args.output} ({len(document)} bytes); draft analysis, no model execution")
        return 0
    except (OSError, ValueError, TypeError, RecursionError, OverflowError) as exc:
        print(f"REVIEW_NOT_WRITTEN_OR_INCOMPLETE: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
