#!/usr/bin/env python3
"""Build a standalone, read-only HTML view of the executed fictional examples."""
from __future__ import annotations
import base64
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CASES = (
    ("parallel", "Parallel work stays parallel", "The two fictional pilots share prerequisites, not a serial ordering."),
    ("inconsistent", "Find the broken edges, preserve independent work", "Four root errors block nine items; the independent branch remains visible."),
    ("unassigned", "Unknown is not a clean result", "Unassigned phases preserve structural information without passing the whole roadmap."),
    ("roadmap085", "Consume the published planner input contract", "Missing duration stays outside this graph check; it is not replaced with zero."),
)

def main() -> None:
    esc = html.escape
    sections=[]
    for name, title, explanation in CASES:
        report=json.loads((ROOT/'sample_output'/f'{name}.json').read_text())
        svg=(ROOT/'sample_output'/f'{name}.svg').read_bytes()
        image=base64.b64encode(svg).decode('ascii')
        c=report['counts']
        findings=''.join('<tr><td>'+esc(d['code'])+'</td><td>'+esc(d['severity'])+'</td><td>'+esc(d['message'])+'</td></tr>' for d in report['diagnostics'])
        if not findings:
            findings='<tr><td colspan="3">No missing references, cycles or proposed-phase inversions found in the supplied graph.</td></tr>'
        waves=''.join('<li>'+esc(', '.join(wave))+'</li>' for wave in report['dependency_frontiers'])
        blocked=''.join('<tr><td>'+esc(d['id'])+'</td><td>'+esc(d['root_diagnostic'])+'</td><td>'+esc(d['blocked_by'] or 'Direct finding')+'</td></tr>' for d in report['blocked_items'])
        if not blocked:
            blocked='<tr><td colspan="3">None blocked by a known graph error.</td></tr>'
        detail=('<p><strong>Full upstream input SHA-256:</strong> <code>'+esc(report['source_projection']['full_input_sha256'])+'</code></p><p>'+esc(report['source_projection']['not_evaluated'])+'</p>') if 'source_projection' in report else ''
        sections.append(f'''<section id="{name}" aria-labelledby="{name}-title">
<h2 id="{name}-title">{esc(title)}</h2><p>{esc(explanation)}</p>
<p class="status"><strong>{esc(report['dependency_check_status'])}</strong> · {c['items']} items · {c['known_edges']} known edges · {c['errors']} errors · {c['warnings']} warnings · {c['blocked_items']} blocked items</p>
<p><strong>Graph input SHA-256:</strong> <code>{esc(report['input_sha256'])}</code></p>{detail}
<figure><img src="data:image/svg+xml;base64,{image}" alt="Directed dependency graph for the {name} example; equivalent findings and frontiers follow as text."><figcaption>Edges point from prerequisite to dependent. Dashed nodes are blocked by a known graph error. This is not a schedule.</figcaption></figure>
<h3>Exact findings</h3><div class="table"><table><thead><tr><th>Code</th><th>Level</th><th>Finding</th></tr></thead><tbody>{findings}</tbody></table></div>
<h3>Dependency-independent frontiers</h3><p>{esc(report['frontier_meaning'])}</p><ol>{waves}</ol>
<details><summary>Blocked item trace</summary><div class="table"><table><thead><tr><th>Item</th><th>Root finding</th><th>Immediate predecessor</th></tr></thead><tbody>{blocked}</tbody></table></div></details>
</section>''')
    nav=' · '.join(f'<a href="#{name}">{esc(name)}</a>' for name,_,_ in CASES)
    document='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Roadmap dependency oracle — executed synthetic examples</title>
<style>
body {font-family:system-ui,sans-serif; max-width:1120px; margin:auto; padding:32px 20px; line-height:1.55}
h1 {line-height:1.12; max-width:25ch} h2 {line-height:1.2} header,section {padding-bottom:28px; margin-bottom:28px; border-bottom:1px solid}
nav {margin:24px 0} code {overflow-wrap:anywhere; font-size:.86em} .status {font-size:1.05em}
figure {margin:24px 0; overflow-x:auto} img {display:block; width:100%; min-width:720px; height:auto} figcaption {font-size:.9em; margin-top:10px}
.table {overflow-x:auto} table {border-collapse:collapse; width:100%; margin:12px 0} th,td {border:1px solid; text-align:left; padding:10px; vertical-align:top}
summary {cursor:pointer} .notice {border:2px solid; padding:16px} @media print {body{padding:0} nav{display:none} section{break-before:page} img{min-width:0} .table{overflow:visible}}
</style></head><body><header><p>ZZ-QUARTZ-731 · GPT-6 Astra Pro · 19 September 2026</p><h1>Roadmap dependency oracle</h1>
<p>A complementary graph checker and UIOWA-085 input adapter, with independently constructed exhaustive test cases.</p>
<div class="notice"><strong>All examples are fictional.</strong> These are actual generated component results, not University findings, approved plans, hosted CI, or evidence that this candidate was merged. Parallel frontiers describe graph independence, not staffing or permission to start.</div>
'''+f'<nav aria-label="Worked examples">{nav}</nav></header>'+''.join(sections)+'''
<footer><h2>Execution evidence</h2><p>47 unit tests passed under normal Python and actual optimized Python. The suite includes all 512 directed three-node graphs, 16,384 four-node DAG/phase assignments, 60 seeded DAGs, a 5,000-item chain, and package-import isolation. Twelve report comparisons and twelve real CLI runs also passed in each Python mode.</p>
<p>Source, fixtures, exact test output, schema attribution and machine-readable results accompany this standalone view. The analyzer uses the Python standard library only. No external links, scripts, fonts, network calls or scheduling actions are required by this page.</p></footer></body></html>'''
    (ROOT/'demo.html').write_text(document,encoding='utf-8')
    print('Built demo.html from four retained JSON reports and rendered SVGs')

if __name__=='__main__':
    main()
