"""Render arbitrary evidence manifests through the existing lineage comparator.

No network, source-file writes, browser storage, or assessment decisions.
Run directly or as a package module; Python 3.10+, standard library only.
"""
from __future__ import annotations

import argparse
import base64
from collections import defaultdict
import html
import json
from pathlib import Path
import sys
from typing import Any

if __package__:
    from . import lineage
else:
    import lineage


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def json_view(value: Any) -> str:
    return '<pre class="json">' + escape(lineage.encoded(value)) + '</pre>'


def details(label: str, value: Any, anchor: str = '') -> str:
    ident = f' id="{escape(anchor)}" tabindex="-1"' if anchor else ''
    return f'<details{ident}><summary>{escape(label)}</summary>{json_view(value)}</details>'


STYLE = '''
:root{color-scheme:light;--ink:#172739;--muted:#526477;--line:#ced8e1;--paper:#fff;--soft:#f3f6f9;--accent:#125f85}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--soft);color:var(--ink);font:16px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
a{color:var(--accent);text-underline-offset:.15em}a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible,[tabindex]:focus-visible{outline:3px solid #d78416;outline-offset:3px}
main{max-width:1160px;margin:auto;padding:30px 24px 70px}header{border-top:6px solid var(--accent);padding:25px;background:var(--paper)}h1{font-size:clamp(1.9rem,4vw,3rem);line-height:1.15;margin:.25em 0}h2{font-size:1.6rem;margin:1.5em 0 .5em}h3{font-size:1.08rem;margin:0 0 .5em}.eyebrow{font-weight:750;letter-spacing:.1em;font-size:.8rem}.muted{color:var(--muted)}.small{font-size:.85rem}.banner{border-left:5px solid #bc7520;background:#fff3df;padding:16px 20px;margin:20px 0}.banner p{margin:.3em 0}.metrics{display:flex;flex-wrap:wrap;gap:10px;margin-top:20px}.metric{padding:10px 16px;background:var(--soft);min-width:140px}.metric strong{font-size:1.6rem;display:block}.metric span{font-size:.85rem}nav{display:flex;gap:10px 20px;flex-wrap:wrap;margin:20px 0}section{scroll-margin-top:20px}.toolbar{background:var(--paper);border:1px solid var(--line);padding:18px;margin:20px 0}.controls{display:flex;gap:12px;flex-wrap:wrap;align-items:end}.field{display:grid;gap:4px;flex:1;min-width:180px}label{font-weight:650;font-size:.88rem}input,select,button{font:inherit;border:1px solid #8395a5;border-radius:5px;padding:9px 12px;background:white;color:var(--ink)}button{cursor:pointer;background:#edf4f8;font-weight:650}button.primary{background:var(--accent);color:white;border-color:var(--accent)}.card{border:1px solid var(--line);border-radius:7px;padding:18px;background:var(--paper);margin:12px 0}.card p{margin:.5em 0}.status{display:inline-block;font-size:.78rem;font-weight:750;letter-spacing:.03em;padding:3px 7px;border:1px solid var(--line);background:var(--soft);overflow-wrap:anywhere}.pair{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px}.json,code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.83rem;overflow-wrap:anywhere}.json{white-space:pre-wrap;background:var(--soft);padding:12px;border:1px solid var(--line);max-height:32rem;overflow:auto}details{border-top:1px solid var(--line);padding-top:9px;margin-top:12px;scroll-margin-top:20px}summary{cursor:pointer;font-weight:650;overflow-wrap:anywhere}.refs{padding-left:22px}.refs li{margin:6px 0;overflow-wrap:anywhere}.presence{font-weight:750}.empty{padding:12px 0;color:var(--muted)}.count-line{margin-bottom:0}.binding{display:block;margin:7px 0;overflow-wrap:anywhere}footer{border-top:1px solid var(--line);margin-top:35px;padding-top:18px}.print-only{display:none}[hidden]{display:none!important}
@media(max-width:640px){main{padding:12px 12px 40px}header{padding:18px}.pair{grid-template-columns:1fr}.controls>*{width:100%}.card{padding:14px}.metric{flex:1}}
@media print{body{background:white;font-size:10pt}main{max-width:none;padding:0}header{padding:10px 0}.toolbar,nav,.screen-only{display:none!important}.print-only{display:block}.review-row[hidden]{display:block!important}.card,.banner{box-shadow:none;border-radius:0}.json{max-height:none;overflow:visible;font-size:8pt}details,details>*{display:block!important}details::details-content{content-visibility:visible!important;height:auto!important}summary{font-weight:bold}.pair{display:block}h2,h3,summary{break-after:avoid}.metric strong{font-size:16pt}a{color:inherit;text-decoration:underline}}
'''

SCRIPT = '''
(function(){
'use strict';
const rows=Array.from(document.querySelectorAll('.review-row'));
const search=document.getElementById('query');
const status=document.getElementById('status-filter');
const count=document.getElementById('filter-count');
const statuses=Array.from(new Set(rows.map(row=>row.dataset.status))).sort();
for(const value of statuses){const option=document.createElement('option');option.value=value;option.textContent=value.replaceAll('_',' ');status.appendChild(option);}
function apply(){
 const query=search.value.trim().toLocaleLowerCase();let visible=0;
 for(const row of rows){const match=(!status.value||row.dataset.status===status.value)&&(!query||row.textContent.toLocaleLowerCase().includes(query));row.hidden=!match;if(match)visible++;}
 count.textContent=visible+' of '+rows.length+' change / citation rows shown. Other sections are not filtered.';
 document.getElementById('no-matches').hidden=visible!==0;
}
search.addEventListener('input',apply);status.addEventListener('change',apply);
document.getElementById('reset-filters').addEventListener('click',()=>{search.value='';status.value='';apply();search.focus();});
document.getElementById('print-review').addEventListener('click',()=>window.print());
let printState=[];
window.addEventListener('beforeprint',()=>{printState=Array.from(document.querySelectorAll('details')).map(node=>[node,node.open]);for(const [node] of printState)node.open=true;});
window.addEventListener('afterprint',()=>{for(const [node,open] of printState)node.open=open;printState=[];});
function reveal(id){
 const target=document.getElementById(id);if(!target)return;
 let node=target;while(node){if(node.tagName==='DETAILS')node.open=true;node=node.parentElement;}
 target.scrollIntoView({block:'start'});if(target.hasAttribute('tabindex'))target.focus({preventScroll:true});
}
document.addEventListener('click',event=>{const link=event.target.closest('a[href^="#"]');if(link){const id=link.getAttribute('href').slice(1);if(document.getElementById(id)){event.preventDefault();history.replaceState(null,'','#'+id);reveal(id);}}});
if(location.hash)reveal(location.hash.slice(1));
document.getElementById('download-json').addEventListener('click',()=>{
 const notice=document.getElementById('download-notice');let url;
 try{
  const raw=atob(document.getElementById('report-data').textContent.trim());
  const bytes=Uint8Array.from(raw,char=>char.charCodeAt(0));
  url=URL.createObjectURL(new Blob([bytes],{type:'application/json;charset=utf-8'}));
  const link=document.createElement('a');link.href=url;link.download='evidence-lineage-review.json';document.body.appendChild(link);link.click();link.remove();
  notice.textContent='JSON download requested. The file contains complete supplied metadata; keep it on an appropriate private surface.';
 }catch(error){notice.textContent='Download could not be prepared: '+error.message;}
 finally{if(url)setTimeout(()=>URL.revokeObjectURL(url),60000);}
});
document.getElementById('controls').hidden=false;apply();
})();
'''


def render(before: dict, after: dict, findings: dict | None = None,
           title: str = 'Evidence lineage review') -> tuple[str, dict]:
    """Compute, then project; caller-supplied report verdicts are never consumed."""
    report = lineage.compare(before, after, findings)
    native_json = lineage.encoded(report)
    encoded_report = base64.b64encode(native_json.encode('utf-8')).decode('ascii')
    sources: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    source_panels = []
    for side, label in (('before', 'Before'), ('after', 'After')):
        manifest = report[side]
        cards = []
        for index, record in enumerate(manifest['records'], 1):
            anchor = f'source-{side}-{index}'
            sources[lineage.ref_key(record)].append((label, anchor))
            cards.append(details(f"{record['record_id']} — {record['document_id']} — {record['version']}", record, anchor))
        metadata = {key: value for key, value in manifest.items() if key != 'records'}
        source_panels.append(
            f'<section><h3>{label}: {escape(manifest["collection_id"])}</h3>'
            + details('Collection metadata (all fields except records)', metadata)
            + (''.join(cards) or '<p class="empty">No source records supplied.</p>') + '</section>')

    def references(items: list[dict], empty: str = 'None supplied.') -> str:
        if not items:
            return '<p class="muted">' + escape(empty) + '</p>'
        rendered = []
        for reference in items:
            key = lineage.ref_key(reference)
            targets = sources.get(key, [])
            links = ' · '.join(f'<a href="#{anchor}">{label} metadata</a>' for label, anchor in targets)
            presence = ''
            if 'present_in_after' in reference:
                presence = '<span class="presence">' + (
                    'Present in after' if reference['present_in_after'] else 'Absent from after — not a deletion claim') + '</span><br>'
            rendered.append('<li>' + presence + '<strong>' + escape(key[0]) + '</strong><br><code>'
                            + escape(key[1]) + '</code><br>' + (links or 'No matching supplied record.') + '</li>')
        return '<ul class="refs">' + ''.join(rendered) + '</ul>'

    changes = []
    after_by_id = {row['record_id']: row for row in report['after']['records']}
    for index, change in enumerate(report['changes'], 1):
        current = after_by_id[change['record_id']]
        changes.append(
            f'<article class="card review-row" data-status="{escape(change["kind"])}">'
            f'<span class="status">{escape(change["kind"])}</span>'
            f'<h3>{escape(change["record_id"])} — {escape(current["title"])}</h3>'
            f'<p>{escape(current["document_id"])} · Version label: {escape(current["version"])}</p>'
            '<div class="pair"><div><h4>Supplied after record</h4>'
            + references([current]) + '</div><div><h4>Prior candidates retained by comparator</h4>'
            + references(change['before_candidates']) + '</div></div>'
            + details('Exact change record', change, f'change-{index}') + '</article>')

    original_findings = report['input_findings']['findings']
    finding_anchors = {finding['finding_id']: f'finding-{index}' for index, finding in enumerate(original_findings, 1)}
    impacts = []
    for index, impact in enumerate(report['finding_impacts'], 1):
        fid = impact['finding_id']
        citation = impact.get('citation')
        citation_view = ('<p>No citation was supplied for this finding.</p>' if citation is None else
                         '<p><strong>Original locator:</strong> ' + escape(citation['locator']) + '</p>'
                         + references([citation]) + '<p class="muted">Locator validation: NOT_PERFORMED.</p>')
        terminals = impact.get('declared_terminal_successors')
        if terminals is None:
            terminals = [{**value, 'present_in_after': True} for value in impact.get('declared_successors', [])]
        impacts.append(
            f'<article class="card review-row" data-status="{escape(impact["status"])}">'
            f'<span class="status">{escape(impact["status"])}</span><h3>{escape(fid)}</h3>'
            f'<p><a href="#{finding_anchors[fid]}">Complete supplied finding</a></p>' + citation_view
            + '<div class="pair"><div><h4>Retained exact copies in after</h4>'
            + references(impact.get('retained_exact_copies', []))
            + '</div><div><h4>All known declared terminal successors</h4>'
            + references(terminals, 'No terminal successor declaration supplied for this citation.') + '</div></div>'
            + details('Exact citation-impact record (all fields)', impact, f'impact-{index}') + '</article>')

    departures = ''.join(
        '<article class="card"><span class="status">RECORD_ABSENT_FROM_AFTER</span>'
        + references([value]) + '<p>Absent from this supplied collection; storage deletion was not established.</p></article>'
        for value in report['departures'])
    duplicates = ''.join(
        '<article class="card"><h3>Shared digest</h3><code>' + escape(group['sha256']) + '</code>'
        + references([{'record_id': rid, 'sha256': group['sha256']} for rid in group['record_ids']])
        + '<p><strong>Distinct supplied document identities:</strong> ' + escape(', '.join(group['document_ids'])) + '</p>'
        + details('Exact duplicate group', group) + '</article>' for group in report['duplicates_after'])
    anomalies = ''.join('<article class="card"><h3>' + escape(item.get('kind', 'Reported anomaly'))
                        + '</h3>' + json_view(item) + '</article>' for item in report['anomalies'])
    finding_panels = ''.join(details(value['finding_id'], value, finding_anchors[value['finding_id']])
                             for value in original_findings)
    finding_metadata = {key: value for key, value in report['input_findings'].items() if key != 'findings'}
    binding = ''.join('<span class="binding"><strong>' + escape(key) + ':</strong> <code>'
                      + escape(value) + '</code></span>' for key, value in report['input_sha256'].items())
    limits = ''.join('<li>' + escape(value) + '</li>' for value in report['limitations'])
    empty = '<p class="empty">No rows reported by the comparator.</p>'
    kind = ('SYNTHETIC — as declared in both manifests' if report['synthetic'] else
            'PRIVATE / MIXED — at least one manifest is not marked synthetic')
    summary = report['summary']
    metrics = ''.join('<div class="metric"><strong>' + str(value) + '</strong><span>' + label + '</span></div>'
                      for label, value in [('Before records', summary['before_records']),
                                           ('After records', summary['after_records']),
                                           ('Supplied findings', len(original_findings)),
                                           ('Citation / uncited rows', len(report['finding_impacts'])),
                                           ('Global anomalies', len(report['anomalies']))])
    page = '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
    page += '<meta name="viewport" content="width=device-width,initial-scale=1">'
    page += '<meta name="referrer" content="no-referrer">'
    page += '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'; connect-src \'none\'; form-action \'none\'; base-uri \'none\'; object-src \'none\'">'
    page += '<title>' + escape(title) + '</title><style>' + STYLE + '</style></head><body><main>'
    page += '<header><div class="eyebrow">EVIDENCE · VERSION · CITATION</div><h1>' + escape(title) + '</h1>'
    page += '<p>' + escape(report['before']['collection_id']) + ' → ' + escape(report['after']['collection_id']) + '</p>'
    page += '<span class="status">DRAFT_NON_AUTHORITATIVE</span><p>' + escape(kind) + '</p><div class="metrics">' + metrics + '</div></header>'
    page += '<div class="banner"><p><strong>Review aid, not an acceptance decision.</strong> Processing completed; conflicts, absent evidence and unresolved findings may remain.</p>'
    page += '<p>Complete supplied metadata is embedded in this page and its JSON download. Data-kind labels are operator declarations, not privacy checks. Keep private material on an appropriate private surface.</p>'
    page += '<p>Counts are global. Citation rows are not a count of distinct findings. Filtering never resolves or removes a finding.</p></div>'
    page += '<nav aria-label="Review sections"><a href="#anomalies">Global anomalies</a><a href="#changes">Collection changes</a><a href="#impacts">Citation follow-up</a><a href="#departures">Absent records</a><a href="#duplicates">Duplicate groups</a><a href="#sources">Retained inputs</a><a href="#limits">Limits and bindings</a></nav>'
    page += '<div class="toolbar" id="controls" hidden><div class="controls"><div class="field"><label for="query">Search change and citation rows</label><input type="search" id="query" autocomplete="off"></div><div class="field"><label for="status-filter">Classification</label><select id="status-filter"><option value="">All classifications</option></select></div><button id="reset-filters" type="button">Reset</button><button id="print-review" type="button">Print full report</button><button id="download-json" type="button" class="primary">Download comparison JSON</button></div><p class="count-line small" id="filter-count" role="status" aria-live="polite"></p><p class="small" id="download-notice" role="status" aria-live="polite"></p></div>'
    page += '<noscript><p>All report rows and retained metadata are readable without JavaScript. Search, JSON download and automatic opening of linked details require JavaScript; open details manually.</p></noscript>'
    page += '<p class="print-only">Full report: browser search and classification filters are ignored for printing.</p><p id="no-matches" class="banner" hidden>No change or citation rows match these filters. Global anomalies and other sections remain below.</p>'
    page += '<section id="anomalies"><h2>Global anomalies · ' + str(len(report['anomalies'])) + '</h2><p class="muted">Always visible; unaffected by search or classification filters.</p>' + (anomalies or empty) + '</section>'
    page += '<section id="changes"><h2>Collection changes · ' + str(len(changes)) + '</h2>' + (''.join(changes) or empty) + '</section>'
    page += '<section id="impacts"><h2>Citation follow-up · ' + str(len(impacts)) + '</h2><p class="muted">Each original citation is separate. A citation-free finding contributes one row. Known omitted successor branches stay visible.</p>' + (''.join(impacts) or empty) + '</section>'
    page += '<section id="departures"><h2>Records absent from after · ' + str(len(report['departures'])) + '</h2>' + (departures or empty) + '</section>'
    page += '<section id="duplicates"><h2>Duplicate-content groups · ' + str(len(report['duplicates_after'])) + '</h2><p class="muted">Identical bytes do not prove independent corroboration or identical document scope.</p>' + (duplicates or empty) + '</section>'
    page += '<section id="sources"><h2>Complete retained input metadata</h2><p class="muted">Metadata and locators are supplied text, not executable instructions or automatic external links. No source files are opened by this page.</p><div class="pair">' + ''.join(source_panels) + '</div><h3>Original findings</h3>' + details('Finding-collection metadata', finding_metadata) + (finding_panels or empty) + '</section>'
    page += '<section id="limits"><h2>Limits and input bindings</h2><ul>' + limits + '</ul><p>Bindings identify the comparator’s canonical JSON representation, not the original JSON file formatting. They are not signatures or authentication. Downloaded JSON is that exact comparator output, without browser number conversion.</p>' + binding + details('Global summary from comparator', summary) + '</section>'
    page += '<footer><p>Generated by the existing evidence-lineage comparator and its read-only HTML projection. No source, citation, custody decision, account or provider was changed.</p></footer>'
    page += '<script id="report-data" type="application/octet-stream">' + encoded_report + '</script><script>' + SCRIPT + '</script></main></body></html>\n'
    return page, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path, help='Before manifest JSON')
    parser.add_argument('after', type=Path, help='After manifest JSON')
    parser.add_argument('--findings', type=Path, help='Optional original finding/citation JSON')
    parser.add_argument('--output', type=Path, required=True, help='New HTML file; existing paths are never overwritten')
    parser.add_argument('--title', default='Evidence lineage review', help='Display title, rendered as plain text')
    args = parser.parse_args(argv)
    try:
        for path in (args.before, args.after, args.findings):
            if path is not None and not path.is_file():
                raise ValueError(f'{path}: a regular JSON input file is required')
        page, report = render(lineage.load(args.before), lineage.load(args.after),
                              lineage.load(args.findings) if args.findings is not None else None,
                              args.title)
        # Build fully before creating the destination. Exclusive creation also
        # refuses input aliases and occupied/dangling final output symlinks.
        with args.output.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(page)
        print(json.dumps({'output': str(args.output), 'status': report['status'],
                          'synthetic': report['synthetic'], 'summary': report['summary']},
                         ensure_ascii=True))
        return 0
    except (OSError, ValueError, TypeError, RecursionError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
