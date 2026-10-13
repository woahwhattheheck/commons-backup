"""Create a portable, offline view of a verified UIOWA-059 assessment."""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import sys
from pathlib import Path
from urllib.parse import quote

if __package__:
    from .lifecycle import InputError, MAX_BYTES, assess, findings_csv, loads, verify_report
else:
    from lifecycle import InputError, MAX_BYTES, assess, findings_csv, loads, verify_report


STYLE = """
:root{color-scheme:light;--ink:#172e39;--muted:#445c66;--line:#c6d3d7;--paper:#fff;--wash:#f0f5f5;--accent:#145e63}
*{box-sizing:border-box}body{margin:0;background:var(--wash);color:var(--ink);font:16px/1.5 system-ui,sans-serif}a{color:#07595f;text-underline-offset:3px}button,input,select{font:inherit}button,.download{padding:.6rem .85rem;border:1px solid var(--accent);border-radius:5px;background:white;color:var(--accent);cursor:pointer}button:hover,.download:hover{background:#e1eeee}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid #ad5d00;outline-offset:3px}main{max-width:1200px;margin:auto;padding:2rem}header{border-top:5px solid var(--accent);padding:1.5rem;background:var(--paper)}h1{font-size:clamp(1.7rem,4vw,2.7rem);line-height:1.1;margin:.5rem 0 1rem;letter-spacing:-.04em}h2{font-size:1.5rem;line-height:1.25;margin:0 0 .8rem}h3{font-size:1.1rem;margin:1.5rem 0 .7rem}p{margin:.6rem 0}.eyebrow{font-size:.8rem;letter-spacing:.08em;text-transform:uppercase;font-weight:750}.subtle,dt{color:var(--muted)}.notice{padding:1rem;border-left:4px solid var(--accent);background:#e6f0f0;margin:1rem 0}.badge{display:inline-block;padding:.18rem .45rem;border:1px solid var(--line);border-radius:4px;font-size:.79rem;font-weight:650;line-height:1.5;background:#f5f8f8}.attention{background:#fff0dc;border-color:#bd843c;color:#5c3505}.stats,.coverage{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:.65rem;margin:1.2rem 0}.stat{background:white;border:1px solid var(--line);padding:.8rem}.stat strong{display:block;font-size:1.8rem;line-height:1.2}.coverage .stat strong{font-size:1.3rem}.coverage .stat span{font-size:.8rem}.toolbar,.actions{display:flex;gap:.7rem;flex-wrap:wrap;align-items:end}.toolbar{background:#fff;border:1px solid var(--line);padding:1rem;margin:1.5rem 0 .5rem}.toolbar label{display:flex;flex-direction:column;gap:.3rem;flex:1 1 180px;font-size:.9rem}.toolbar input,.toolbar select{width:100%;padding:.6rem;border:1px solid #657f89;border-radius:4px;background:white;color:var(--ink)}.actions{margin:.8rem 0}.download{display:inline-block;text-decoration:none;font-size:.9rem}.jump{display:flex;flex-wrap:wrap;gap:.6rem 1.1rem;padding:1rem 0}.copy{background:var(--paper);border:1px solid var(--line);margin:1.5rem 0;padding:1.5rem;scroll-margin-top:1rem}.copy-title{display:flex;justify-content:space-between;gap:1rem;align-items:start}.copy-title .badge{max-width:54%}.fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.7rem 1.5rem;margin:1rem 0}.fields>div{min-width:0}dt{font-size:.78rem;font-weight:650;letter-spacing:.025em}dd{margin:.1rem 0 0;white-space:pre-wrap;overflow-wrap:anywhere}code,.digest{font: .87em ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}.table-wrap{overflow:auto;max-width:100%;border:1px solid var(--line)}table{border-collapse:collapse;width:100%;table-layout:fixed;font-size:.85rem}th,td{padding:.7rem;text-align:left;vertical-align:top;border-bottom:1px solid var(--line);overflow-wrap:anywhere}th{background:#eaf1f2;font-size:.8rem}tr:last-child td{border-bottom:0}td small{display:block;color:var(--muted);margin-top:.3rem}td p{margin:0 0 .3rem}.record{border-left:3px solid #9fb7bf;padding:.5rem 1rem;margin:1rem 0;scroll-margin-top:1rem}.record h4{font-size:1rem;margin:.3rem 0}.record .fields{margin:.5rem 0}.record p{white-space:pre-wrap;overflow-wrap:anywhere}details>summary{font-weight:700;cursor:pointer;padding:.6rem 0}details{border-top:1px solid var(--line);margin-top:1.2rem}footer{font-size:.9rem;padding:1rem 0 2rem}.no-results{padding:2rem;text-align:center;border:1px dashed var(--line)}[hidden]{display:none!important}body,h1,h2,h3,h4,p,.badge,.stat,li{overflow-wrap:anywhere}
@media(max-width:600px){main{padding:.8rem}header,.copy{padding:1rem}.fields{grid-template-columns:1fr}.copy-title{display:block}.copy-title .badge{max-width:100%}table{min-width:650px}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.coverage{grid-template-columns:repeat(2,minmax(0,1fr))}.toolbar label{flex-basis:100%}.actions>*{max-width:100%}}
@media print{@page{size:A4;margin:13mm}body{background:white;font-size:9pt;line-height:1.4}main{max-width:none;padding:0}header{padding:0;border-top-width:3px}h1{font-size:24pt}h2{font-size:17pt}.copy{padding:1rem 0;border:0;border-top:2px solid var(--ink);margin:1rem 0}.toolbar,.actions,.jump,.screen-only,.no-results{display:none!important}.copy[hidden]{display:block!important}.table-wrap{overflow:visible;border:0}table{min-width:0;font-size:8pt}th,td{padding:.45rem}thead{display:table-header-group}tr,.fields>div{break-inside:avoid}.fields{grid-template-columns:repeat(2,minmax(0,1fr))}.record{padding-left:.7rem;break-inside:auto}.record h4,h2,h3,summary{break-after:avoid}details::details-content{display:block;content-visibility:visible}details>summary{list-style:none}details>summary::-webkit-details-marker{display:none}.stats,.coverage{grid-template-columns:repeat(3,minmax(0,1fr))}.stat{padding:.5rem}.stat strong{font-size:18pt}a{color:inherit;text-decoration:none}footer{padding-bottom:0}.notice{break-inside:avoid}.badge{font-size:7.5pt}pre{white-space:pre-wrap}}
"""

SCRIPT = """
'use strict';
const cards = [...document.querySelectorAll('.copy')];
const search = document.getElementById('search');
const group = document.getElementById('group');
const state = document.getElementById('state');
const count = document.getElementById('visible-count');
const empty = document.getElementById('empty');
const normalized = cards.map(card => card.textContent.toLocaleLowerCase());
function filter() {
  const term = search.value.trim().toLocaleLowerCase();
  let visible = 0;
  cards.forEach((card, i) => {
    card.hidden = Boolean((group.value && card.dataset.group !== group.value) ||
      (state.value && card.dataset.state !== state.value) || (term && !normalized[i].includes(term)));
    if (!card.hidden) visible += 1;
  });
  count.textContent = visible + ' of ' + cards.length + ' copies shown. Search includes their checks, follow-ups and evidence.';
  empty.hidden = visible !== 0;
}
function reset() { search.value = ''; group.value = ''; state.value = ''; filter(); }
search.addEventListener('input', filter);
group.addEventListener('change', filter);
state.addEventListener('change', filter);
document.getElementById('reset').addEventListener('click', reset);
function revealHash(hash) {
  const target = document.getElementById(hash.slice(1));
  if (!target) return;
  const card = target.closest('.copy');
  if (card && card.hidden) reset();
  for (let node = target.parentElement; node; node = node.parentElement) {
    if (node.tagName === 'DETAILS') node.open = true;
  }
}
document.addEventListener('click', event => {
  const link = event.target.closest('a[href^="#"]');
  if (link) revealHash(link.getAttribute('href'));
});
window.addEventListener('hashchange', () => revealHash(location.hash));
let printState = null;
function beforePrint() {
  if (printState) return;
  printState = { hidden: cards.map(card => card.hidden), details: [...document.querySelectorAll('details')].map(node => [node, node.open]) };
  cards.forEach(card => { card.hidden = false; });
  printState.details.forEach(([node]) => { node.open = true; });
}
function afterPrint() {
  if (!printState) return;
  cards.forEach((card, i) => { card.hidden = printState.hidden[i]; });
  printState.details.forEach(([node, open]) => { node.open = open; });
  printState = null;
}
window.addEventListener('beforeprint', beforePrint);
window.addEventListener('afterprint', afterPrint);
document.getElementById('print').addEventListener('click', () => window.print());
document.querySelectorAll('[data-enhance]').forEach(node => { node.hidden = false; });
filter();
revealHash(location.hash);
"""


def esc(value: object) -> str:
    if value is None:
        return '<span class="subtle">null — not recorded</span>'
    if isinstance(value, bool):
        value = "true" if value else "false"
    return html.escape(str(value), quote=True)


def badge(value: str) -> str:
    # Presentation only: every label remains the assessor's exact supplied value.
    attention = value in {"CONTRADICTORY", "OBSERVED_GAP", "DOCUMENTED_GAP", "DISPOSAL_REPORTED_UNVERIFIED"}
    return '<span class="badge' + (' attention' if attention else '') + '">' + esc(value) + '</span>'


def fields(rows: list[tuple[str, str]]) -> str:
    return '<dl class="fields">' + ''.join('<div><dt>' + esc(label) + '</dt><dd>' + value + '</dd></div>' for label, value in rows) + '</dl>'


def render_html(packet: dict, report: dict) -> str:
    """Verify full native semantics before rendering; this does not verify authenticity."""
    if not verify_report(packet, report):
        raise InputError("report does not match the supplied packet")
    item_anchors = {row['item']['id']: 'copy-' + str(i) for i, row in enumerate(report['items'])}
    evidence_anchors = {row['id']: 'evidence-' + str(i) for i, row in enumerate(report['evidence'])}

    def link(value: str, anchors: dict) -> str:
        return '<a href="#' + anchors[value] + '">' + esc(value) + '</a>'

    def evidence_links(ids: list[str]) -> str:
        return ', '.join(link(value, evidence_anchors) for value in ids) or '<span class="subtle">No evidence IDs supplied</span>'

    def options(values: list[str], label: str) -> str:
        return '<option value="">' + label + '</option>' + ''.join('<option value="' + html.escape(v, quote=True) + '">' + esc(v) + '</option>' for v in sorted(set(values)))

    native_json = json.dumps(report, indent=2, ensure_ascii=True) + '\n'
    native_csv = findings_csv(report)
    summary = report['summary']
    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">']
    script_hash = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    csp = "default-src 'none'; script-src 'sha256-" + script_hash + "'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
    out += ['<meta http-equiv="Content-Security-Policy" content="' + html.escape(csp, quote=True) + '">',
            '<title>Data lifecycle review · ' + esc(report['assessment_id']) + '</title><style>' + STYLE + '</style></head><body><main id="top">',
            '<header><div class="eyebrow">UIOWA-059 · Supplied-record review</div><h1>Development data lifecycle</h1>',
            '<p><strong>' + esc(report['assessment_id']) + '</strong> · As of <time>' + esc(report['as_of']) + '</time></p>',
            '<p>' + badge(report['evidence_mode']) + ' ' + badge(report['authority']) + '</p>',
            '<div class="notice"><strong>Evidence coverage, without operational authority.</strong><ul>' + ''.join('<li>' + esc(v) + '</li>' for v in report['limitations']) + '</ul></div>',
            '<p class="subtle">Each retained copy is assessed independently. A supported stage does not itself establish verified disposition. Unknowns, contradictions and prior evidence remain visible.</p>',
            '<div class="actions"><a class="download" download="report.json" href="data:application/json;charset=utf-8,' + quote(native_json, safe='') + '">Download full native report JSON</a>',
            '<a class="download" download="follow-ups.csv" href="data:text/csv;charset=utf-8,' + quote(native_csv, safe='') + '">Download full native follow-ups CSV</a>',
            '<button id="print" type="button" data-enhance hidden>Print full review</button></div>',
            '<p class="subtle">Downloads always contain the complete native assessment, regardless of the visible filters.</p></header>',
            '<section aria-label="Assessment counts"><div class="stats">']
    for key, label in [('items', 'Retained copies'), ('evidence_records', 'Evidence records'), ('applicable_checks', 'Applicable checks'), ('findings', 'Follow-ups')]:
        out.append('<div class="stat"><strong>' + str(summary[key]) + '</strong><span>' + label + '</span></div>')
    out.append('</div><h2>Evidence coverage</h2><p class="subtle">Native check counts; these are not maturity or risk scores.</p><div class="coverage">')
    for status, count in summary['check_counts'].items():
        out.append('<div class="stat"><strong>' + str(count) + '</strong><span>' + esc(status) + '</span></div>')
    out += ['</div></section><nav class="jump" aria-label="Jump to retained copy">',
            ''.join(link(row['item']['id'], item_anchors) for row in report['items']), '</nav>',
            '<section class="toolbar" aria-label="Filter copies" data-enhance hidden><label>Search copies and their records<input id="search" type="search" placeholder="Identifier, statement, finding…"></label>',
            '<label><span id="group-label">Group</span><select id="group" aria-labelledby="group-label">' + options([r['item']['group'] for r in report['items']], 'All groups') + '</select></label>',
            '<label><span id="state-label">Disposition state</span><select id="state" aria-labelledby="state-label">' + options([r['state'] for r in report['items']], 'All states') + '</select></label>',
            '<button type="button" id="reset">Reset filters</button></section>',
            '<p id="visible-count" class="screen-only" role="status" aria-live="polite" data-enhance hidden></p>',
            '<p id="empty" class="no-results" hidden>No copies match. Reset the filters to view the complete assessment.</p>']
    for row in report['items']:
        item = row['item']
        iid = item['id']
        out += ['<article class="copy" id="' + item_anchors[iid] + '" data-group="' + html.escape(item['group'], quote=True) + '" data-state="' + html.escape(row['state'], quote=True) + '">',
                '<div class="copy-title"><div><div class="eyebrow">' + esc(item['group']) + '</div><h2>' + esc(iid) + '</h2></div>' + badge(row['state']) + '</div>']
        values = [(name.replace('_', ' ').capitalize(), esc(value)) for name, value in item.items() if name not in {'id', 'group', 'parent_id', 'retained_categories'}]
        values += [('Parent copy', link(item['parent_id'], item_anchors) if item['parent_id'] is not None else 'null — root / independently inventoried source'),
                   ('Retained categories', ', '.join(esc(v) for v in item['retained_categories']) or '[] — no categories supplied'),
                   ('Expiry reached at selected as of', esc(row['expiry_reached']))]
        out += [fields(values), '<h3>Applicable checks</h3><p class="subtle">Observation and documentation are separate. Only checks selected by the assessor appear here.</p>',
                '<div class="table-wrap" role="region" aria-label="Checks for ' + html.escape(iid, quote=True) + '" tabindex="0"><table><thead><tr><th scope="col">Stage / status</th><th scope="col">Latest observation</th><th scope="col">Latest documentation</th><th scope="col">Complete evidence IDs</th></tr></thead><tbody>']
        for check in row['applicable_checks']:
            out.append('<tr><td><p>' + esc(check['stage']) + '</p>' + badge(check['status']) + '</td><td>' + esc(check['latest_observed_at']) + '<small>' + evidence_links(check['latest_observed_ids']) + '</small></td><td>' + esc(check['documented_outcome']) + '<small>' + esc(check['latest_documented_at']) + '</small><small>' + evidence_links(check['latest_documented_ids']) + '</small></td><td>' + evidence_links(check['evidence_ids']) + '</td></tr>')
        out.append('</tbody></table></div><details open><summary>Follow-ups for ' + esc(iid) + '</summary>')
        findings = [finding for finding in report['findings'] if finding['item_id'] == iid]
        if not findings:
            out.append('<p>No follow-ups emitted for this copy by the native assessment.</p>')
        for finding in findings:
            out += ['<section class="record"><h4>' + esc(finding['code']) + '</h4><p>' + badge(finding['severity']) + '</p><p>' + esc(finding['detail']) + '</p>',
                    fields([('Copy / group', esc(finding['item_id']) + ' / ' + esc(finding['group'])), ('Stage', esc(finding['stage'])), ('Next step', esc(finding['next_step'])), ('Dependencies', esc(finding['dependencies'])), ('Illustrative effort', esc(finding['effort_hint'])), ('Effort is a planning assumption', esc(finding['effort_is_planning_assumption'])), ('Evidence IDs', evidence_links(finding['evidence_ids']))]), '</section>']
        out.append('</details><details open><summary>Retained evidence for ' + esc(iid) + '</summary><p class="subtle">Complete native identifier order, including older and conflicting supplied records. References are literal source locators.</p>')
        evidence = [record for record in report['evidence'] if record['item_id'] == iid]
        if not evidence:
            out.append('<p>No evidence records supplied for this copy.</p>')
        for record in evidence:
            out += ['<section class="record" id="' + evidence_anchors[record['id']] + '"><h4>' + esc(record['id']) + '</h4>',
                    fields([(name.replace('_', ' ').capitalize(), esc(value)) for name, value in record.items() if name != 'id']), '</section>']
        out.append('</details><p class="screen-only"><a href="#top">Back to overview</a></p></article>')
    out += ['<footer><h2>Provenance and interpretation</h2>', fields([('Report schema', esc(report['schema'])), ('Semantic input SHA-256', '<span class="digest">' + esc(report['input_sha256']) + '</span>'), ('Native report SHA-256', '<span class="digest">' + esc(report['report_sha256']) + '</span>')]),
            '<p>The report was verified against the supplied packet before rendering. Digests establish consistency with those records; they do not establish authenticity or completeness. HTML presentation is not part of the native report digest.</p>',
            '<p>Original implementation: ZZ-ORIEL-27. Chronology and diagnostic recovery: yZ-Larch-47. Portable review continuation: UIOWA059-PORTABLE-REVIEW-20261003-A3DEA.</p>',
            '<p>' + esc(report['evidence_mode']) + ' · ' + esc(report['authority']) + '. No compliance, maturity ranking, data deletion or operational action is authorized.</p>',
            '</footer></main><script>' + SCRIPT + '</script></body></html>\n']
    return ''.join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='New HTML file; existing paths are never overwritten')
    args = parser.parse_args(argv)
    try:
        with args.packet.open('rb') as source:
            raw = source.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise InputError('input exceeds 2 MB')
        packet = loads(raw.decode('utf-8'))
        report = assess(packet)
        rendered = render_html(packet, report)
        with args.output.open('x', encoding='utf-8', newline='') as target:
            target.write(rendered)
        print(json.dumps({'status': 'OFFLINE_REVIEW_WRITTEN', 'output': str(args.output), 'report_sha256': report['report_sha256'], 'html_sha256': hashlib.sha256(rendered.encode('utf-8')).hexdigest()}, sort_keys=True))
        return 0
    except (InputError, OSError, UnicodeError, RecursionError) as exc:
        print(f'review error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
