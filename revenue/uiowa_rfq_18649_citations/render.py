"""Portable, linked views from one trace. No independent executive-summary prose."""
from __future__ import annotations

from html import escape
from urllib.parse import quote

CSS = """body{font:18px/1.55 system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem}
nav{display:flex;gap:1rem;flex-wrap:wrap}h1,h2,h3{line-height:1.2}article{border-top:1px solid;padding:1rem 0}
table{border-collapse:collapse;width:100%;font-size:.9rem}th,td{border:1px solid;padding:.5rem;text-align:left}
pre,code{overflow-wrap:anywhere;white-space:pre-wrap}blockquote{border-left:4px solid;padding:0 1rem;margin:1rem 0}
a:focus{outline:3px solid;outline-offset:3px}.scroll{overflow-x:auto}.meta{font-size:.9rem}
@media print{body{font-size:11pt;max-width:none}nav{display:none}h2,h3{break-after:avoid}thead{display:table-header-group}}
"""


def page(title: str, body: str) -> str:
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(title)}</title><style>{CSS}</style><body>{body}</body></html>\n')


def anchor(kind: str, identifier: str) -> str:
    return kind + "-" + identifier


def link(target: str, label: str, *, file: bool = False) -> str:
    href = quote(target, safe="/-_." if file else "/#-_.:")
    return f'<a href="{escape(href, quote=True)}">{escape(label)}</a>' 


def reader_path(citation: dict) -> str:
    return "reader-" + citation["sha256"] + ".html"


def report_html(trace: dict) -> str:
    out = [f'<h1>Citation review — synthetic rehearsal</h1><p><strong>{trace["label"]}</strong></p>',
           f'<p>{escape(trace["limits"])}</p>',
           '<nav><a href="#summary">Summary</a><a href="#findings">Findings</a>'
           '<a href="#recommendations">Recommendations</a><a href="#matrix">Compiler cells</a>'
           '<a href="#appendix">Source appendix</a></nav>',
           f'<p class="meta">Compiler receipt: <code>{trace["compiler_receipt_sha256"]}</code><br>'
           f'Citation packet SHA-256: <code>{trace["packet_sha256"]}</code></p>',
           f'<p>{trace["counts"]["resolved"]} byte/locator links resolved; '
           f'{trace["counts"]["unresolved"]} unresolved. Historical links are labeled separately.</p>',
           '<h2 id="summary">Executive-summary trace</h2>']
    findings = {f["finding_id"]: f for f in trace["findings"]}
    recs = {r["recommendation_id"]: r for r in trace["recommendations"]}
    for fid in trace["executive_summary"]["finding_ids"]:
        f = findings[fid]
        out.append(f'<p>{link("#" + anchor("finding", fid), fid)} — {escape(f["statement"])} '
                   f'[{f["trace_status"]}]</p>')
    for rid in trace["executive_summary"]["recommendation_ids"]:
        out.append(f'<p>Proposed action {link("#" + anchor("recommendation", rid), rid)} — '
                   f'{escape(recs[rid]["action"])}</p>')
    out.append('<h2 id="findings">Findings and limits</h2>')
    for f in trace["findings"]:
        out.append(f'<article id="{anchor("finding", f["finding_id"])}"><h3>{escape(f["finding_id"])} '
                   f'— {f["group"]} / {f["dimension"]} / {f["kind"]}</h3>'
                   f'<p>{escape(f["statement"])}</p><p><strong>{f["trace_status"]}</strong></p>'
                   f'<p>Interpretation limits: {escape(f["limits"])}</p><p>')
        out.append(" · ".join(link("#" + anchor("citation", c["citation_id"]), c["citation_id"])
                              for c in f["citations"]) + '</p></article>')
    out.append('<h2 id="recommendations">Proposed recommendations</h2>')
    for rec in trace["recommendations"]:
        rid = rec["recommendation_id"]
        out.append(f'<article id="{anchor("recommendation", rid)}"><h3>{escape(rid)}</h3>'
                   f'<p>{escape(rec["action"])}</p><p>{escape(rec["rationale"])}</p>'
                   f'<p>Relative phase: {rec["phase"]}; role: {escape(rec["owner_role"])}; '
                   f'effort assumption: {escape(rec["effort"])}</p>'
                   f'<p>Proposed outcome measure: {escape(rec["outcome_measure"])}</p><p>Basis: ')
        out.append(" · ".join(link("#" + anchor("finding", fid), fid) for fid in rec["finding_ids"]) +
                   '</p></article>')
    out.append('<h2 id="matrix">Existing compiler inspection — not ratings</h2><div class="scroll">'
               '<table><thead><tr><th>Group</th><th>Area</th><th>Compiler state</th><th>Sources</th>'
               '</tr></thead><tbody>')
    for c in trace["assessment_matrix"]:
        out.append('<tr>' + ''.join('<td>' + escape(str(value)) + '</td>' for value in
                   (c["group"], c["dimension"], c["status"], ', '.join(c["source_ids"]) or 'None supplied')) + '</tr>')
    out.append('</tbody></table></div><h2 id="sources">Retained source versions</h2>')
    for row in trace['source_inventory']:
        target = ('reader-' + row['sha256'] + '.html') if row['retained_path'] else None
        label = row['source_id'] + ' / ' + row['version']
        out.append('<p>' + (link(target, label) if target else escape(label)) + ' — ' +
                   escape(row['byte_status']) +
                   ('; superseded by ' + escape(row['superseded_by']) if row['superseded_by'] else '') + '</p>')
    out.append('<h2 id="appendix">Exact-source appendix</h2>')
    for f in trace["findings"]:
        for c in f["citations"]:
            out.append(f'<article id="{anchor("citation", c["citation_id"])}"><h3>{escape(c["citation_id"])}</h3>'
                       f'<p>{escape(c["source_id"])} / {escape(c["version"])} / <code>{c["sha256"]}</code></p>')
            if c["resolved"]:
                item = c["citation"]
                out.append(f'<p>{escape(item["title"])} — {escape(item["locator"])}</p>'
                           f'<p>{link(reader_path(c) + "#" + c["segment_id"], "Open exact segment")} · '
                           f'{link(item["retained_path"], "Retained original bytes", file=True)}</p>'
                           f'<blockquote>{escape(item["quote"])}</blockquote>'
                           f'<p>Evidence type: {escape(item["evidence_kind"])}; '
                           f'bound to report source: {str(c["bound_to_compiler_source"]).lower()}</p>')
                if item["warnings"]:
                    out.append('<p>Extraction limits: ' + escape('; '.join(item["warnings"])) + '</p>')
            else:
                out.append('<p><strong>Unresolved — no source citation is asserted.</strong></p>')
            if c["diagnostics"]:
                out.append('<p>Diagnosis: ' + escape('; '.join(c["diagnostics"])) + '</p>')
            out.append('<p>' + link('#' + anchor('finding', f['finding_id']), 'Back to finding') + '</p></article>')
    return page('Synthetic citation review', ''.join(out))


def source_html(extraction: dict, retained: str) -> str:
    doc = extraction["document"]
    out = [f'<h1>Retained synthetic source</h1><p>{escape(doc["sha256"])}</p>',
           '<p>' + link('index.html#appendix', 'Citation appendix') + ' · ' +
           link(retained, 'Original bytes', file=True) + '</p>']
    for segment in extraction["segments"]:
        out.append(f'<article id="{escape(segment["segment_id"], quote=True)}">'
                   f'<h2>{escape(segment["locator"])}</h2><p>{escape(" / ".join(segment["heading_path"]))}</p>'
                   f'<pre>{escape(segment["text"])}</pre><p>{escape("; ".join(segment["warnings"]))}</p></article>')
    return page('Exact source segments', ''.join(out))


def report_markdown(trace: dict) -> str:
    # HTML escaping plus explicit Markdown punctuation handling keeps prose inert.
    def safe(value):
        s = escape(str(value))
        for char in ('\\', '`', '*', '_', '[', ']', '|', '#'):
            s = s.replace(char, '\\' + char)
        return s
    out = ['# Citation review — synthetic rehearsal', '', trace['label'], '', safe(trace['limits']), '',
           'Compiler receipt: `' + trace['compiler_receipt_sha256'] + '`', '',
           '[Interactive source appendix](index.html#appendix)', '', '## Findings', '']
    for f in trace['findings']:
        out += ['### ' + safe(f['finding_id']) + ' — ' + safe(f['kind']), '', safe(f['statement']), '',
                '**' + f['trace_status'] + '**', '', 'Limits: ' + safe(f['limits']), '']
        for c in f['citations']:
            out.append('- ' + safe(c['citation_id']) + ': ' + ('RESOLVED' if c['resolved'] else 'UNRESOLVED'))
            if c['resolved']:
                target = reader_path(c) + '#' + c['segment_id']
                out.append('  [' + safe(c['citation']['locator']) + '](' + target + ') — ' +
                           safe(c['citation']['quote']))
            if c['diagnostics']:
                out.append('  Diagnosis: ' + safe('; '.join(c['diagnostics'])))
        out.append('')
    out += ['## Proposed recommendations', '']
    for r in trace['recommendations']:
        out += ['### ' + safe(r['recommendation_id']), '', safe(r['action']), '', safe(r['rationale']), '',
                'Basis: ' + safe(', '.join(r['finding_ids'])) + '; phase: ' + safe(r['phase']), '',
                'Effort assumption: ' + safe(r['effort']), '', 'Outcome measure: ' + safe(r['outcome_measure']), '']
    return '\n'.join(out) + '\n'
