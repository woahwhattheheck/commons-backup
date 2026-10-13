#!/usr/bin/env python3
"""Portable, read-only HTML projection of the existing analyst reconciler.

Inputs are recompiled/validated by handoff_review.reconcile, never accepted as an
unverified result. This module does not score, adjudicate, or contact a service.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
from html import escape
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlsplit

import handoff_review as hr

CLASSIFICATIONS = ("SYNTHETIC_REHEARSAL", "OPERATOR_DRAFT")
DIMENSION_NAMES = {"software": "Software", "security": "Security",
                   "deployment": "Deployment", "ai_readiness": "AI readiness"}
REASONS = {
    "ALL_UNREVIEWED": "No active draft review is recorded.",
    "INCOMPLETE_REVIEW": "At least one supplied draft is still unreviewed.",
    "DISPOSITION_DISAGREEMENT": "Active draft dispositions differ; retain them for discussion.",
    "NOTE_VARIATION_REQUIRES_REVIEW": "The wording differs; this does not itself prove conflicting evidence.",
    "SINGLE_DRAFT_ENTRY": "Only one distinct draft was supplied; copies add no corroboration.",
    "MATCHING_DRAFT_ENTRIES": "These entries match across distinct exports; this is not acceptance.",
}
CSS = """
:root{font-family:system-ui,sans-serif;color:#16222f;background:#edf1f4;line-height:1.5}
*{box-sizing:border-box}body{margin:0}a{color:#174c79;text-underline-offset:.18em}
button,input,select{font:inherit}button,select,input{padding:.6rem;border:1px solid #596b7b;border-radius:.3rem;background:white;color:inherit}
button{cursor:pointer}button[aria-pressed=true]{background:#16222f;color:white}
:focus-visible{outline:3px solid #8c3d08;outline-offset:4px}
.skip{position:absolute;top:-5rem;left:1rem;background:white;padding:.7rem;z-index:10}.skip:focus{top:1rem}
header,main,footer{max-width:86rem;margin:auto;padding:1.4rem 2rem}header{background:#fff;border-bottom:4px solid #174c79}
h1{font-size:2rem;margin:.3rem 0}h2{font-size:1.4rem}h3{font-size:1.05rem}p{max-width:85ch}
.eyebrow{font-weight:700;letter-spacing:.09em;font-size:.8rem}.boundary{padding:1rem;border-left:4px solid #8c3d08;background:#fff4e5}
.stats{display:flex;flex-wrap:wrap;gap:1rem;margin:1rem 0}.stat{background:#e6edf3;padding:.8rem 1.2rem;min-width:10rem}.stat strong{display:block;font-size:1.8rem}
code,pre{font-family:ui-monospace,monospace;overflow-wrap:anywhere;white-space:pre-wrap;font-size:.87em}pre{border:1px solid #a7b5c1;padding:1rem;background:#f5f7f9}
.controls{padding:1rem;background:#fff;border:1px solid #a7b5c1;margin-bottom:1rem}.filters{display:flex;flex-wrap:wrap;gap:.55rem}.searches{display:flex;flex-wrap:wrap;gap:1rem;margin:1rem 0}
.searches .field{display:grid;gap:.35rem;flex:1;min-width:12rem}.searches input{width:100%}
.index{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.4rem;margin:1rem 0}.index a{display:block;background:white;border:1px solid #8999a7;padding:.65rem;overflow-wrap:anywhere}
.cell{background:white;border:1px solid #8999a7;border-top:4px solid #596b7b;margin:1.2rem 0;padding:1.3rem;scroll-margin-top:1rem}
.cell h2{margin:0 0 .4rem}.cell:target{border-top-color:#8c3d08}.state{font-weight:bold}.reasons{padding-left:1.2rem}.reasons li{margin:.3rem 0}
.notes{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,19rem),1fr));gap:1rem}.note{border:1px solid #a7b5c1;padding:1rem;min-width:0;background:#f5f7f9}.note h3{margin:0}
.note-text{white-space:pre-wrap;overflow-wrap:anywhere;max-width:none;tab-size:4}.empty{font-style:italic;color:#485769}
.sources{padding-left:1.2rem}.sources li{margin:1rem 0;overflow-wrap:anywhere}details{margin:.75rem 0}summary{cursor:pointer;overflow-wrap:anywhere}
.receipts{padding:1rem;border:1px solid #8999a7;background:#fff}.receipts p{max-width:none}.download{display:inline-block;padding:.6rem;border:1px solid #174c79;border-radius:.3rem}
[hidden]{display:none!important}.print-note{display:none}footer{font-size:.9rem}#missing-target{border:2px solid #8c3d08;padding:1rem;background:white}
@media(max-width:42rem){header,main,footer{padding:1rem}h1{font-size:1.6rem}.index{grid-template-columns:repeat(2,minmax(0,1fr))}.cell{padding:1rem}}
@media print{body{background:white;color:black}header,main,footer{padding:0;max-width:none}header{border-color:black}.controls,.index,.download,.skip{display:none!important}.cell[hidden]{display:block!important}.cell{border-color:black;break-before:auto}.note{background:white}.notes{display:block}.note{margin:.5rem 0;break-inside:auto}.cell h2,.cell h3{break-after:avoid}pre{background:white}.print-note{display:block;font-weight:bold}.boundary{background:white;border-color:black}a{color:black}details:not([open]){display:none}.stats .stat{background:white;border:1px solid black}.receipts{break-inside:avoid}}
""".strip()
SCRIPT = """
(()=>{'use strict';
const cards=[...document.querySelectorAll('.cell')], group=document.getElementById('group-filter'), search=document.getElementById('text-filter'), status=document.getElementById('filter-status');
const buttons=[...document.querySelectorAll('[data-filter]')];let mode='all';
function apply(){const query=search.value.toLocaleLowerCase(),chosen=group.value;let visible=0;
 for(const c of cards){const reasons=c.dataset.reasons.split(' ');const matchMode=mode==='all'||(mode==='pending'&&c.dataset.pending==='yes')||(mode==='disagreement'&&reasons.includes('DISPOSITION_DISAGREEMENT'))||(mode==='unreviewed'&&reasons.includes('ALL_UNREVIEWED'));
 c.hidden=!(matchMode&&(!chosen||c.dataset.group===chosen)&&(!query||c.textContent.toLocaleLowerCase().includes(query)));if(!c.hidden)visible++;}
 status.textContent=`${visible} of ${cards.length} cells shown. Filters do not change records; printing includes all cells.`;
 for(const b of buttons)b.setAttribute('aria-pressed',String(b.dataset.filter===mode));}
for(const b of buttons)b.addEventListener('click',()=>{mode=b.dataset.filter;apply();});group.addEventListener('change',apply);search.addEventListener('input',apply);
document.getElementById('reset-filters').addEventListener('click',()=>{mode='all';group.value='';search.value='';apply();});
function follow(){const raw=location.hash.slice(1),message=document.getElementById('missing-target');message.hidden=true;if(!raw)return;
 let id;try{id=decodeURIComponent(raw);}catch(_){message.hidden=false;message.textContent='The link has an invalid item identifier.';return;}
 const target=cards.find(c=>c.id===id);if(!target){if(id!=='review-start'){message.hidden=false;message.textContent='The requested item is not present in this exported review. Choose one of the twelve indexed cells.';}return;}
 if(target.hidden){mode='all';group.value='';search.value='';apply();}
 target.querySelector('h2').focus({preventScroll:true});target.scrollIntoView({block:'start'});}
window.addEventListener('hashchange',follow);document.getElementById('reader-controls').hidden=false;apply();follow();
})();
""".strip()


def _e(value: Any) -> str:
    return escape(str(value), quote=True)


def _hash(text: str) -> str:
    return base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii")


def _locator(value: str) -> str:
    """Retain every locator literally; only ordinary web URLs are clickable."""
    try:
        parsed = urlsplit(value)
        clickable = parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        clickable = False
    if clickable:
        return f'<a href="{_e(value)}" rel="noreferrer noopener">{_e(value)}</a>'
    return f'<code>{_e(value)}</code>'


def build_html(report: Any, handoffs: list[tuple[str, Any]], *, classification: str) -> str:
    """Validate with the original engine, then create a deterministic projection."""
    if classification not in CLASSIFICATIONS:
        raise hr.ReviewError("classification must be SYNTHETIC_REHEARSAL or OPERATOR_DRAFT")
    result = hr.reconcile(report, handoffs)
    # Source rows were already validated by the parent's semantic recompile.
    sources = {row["source_id"]: row for row in report["evidence_authority"]["sources"]}
    pending = {(row["group"], row["dimension"]) for row in result["review_queue"]}
    banner = ("SYNTHETIC REHEARSAL — fictional inputs, not University observations."
              if classification == "SYNTHETIC_REHEARSAL" else
              "OPERATOR DRAFT — supplied inputs have not been authenticated as University evidence.")
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             '<meta name="referrer" content="no-referrer">',
             f'<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; base-uri \'none\'; form-action \'none\'; connect-src \'none\'; script-src \'sha256-{_hash(SCRIPT)}\'; style-src \'sha256-{_hash(CSS)}\'">',
             '<title>Draft analyst review · TJLabs</title>', f'<style>{CSS}</style></head><body>',
             '<a class="skip" href="#review-start">Skip to review</a>',
             '<header><div class="eyebrow">TJLabs / ANALYST HANDOFF</div><h1>Compare drafts. Keep the evidence.</h1>',
             f'<p class="boundary"><strong>{banner}</strong><br>Classification is operator-declared, not independently verified. This is a read-only draft review, not adjudication or acceptance.</p>',
             '<p>Compare the supplied notes without losing their original wording, source references or unresolved questions. Labels identify files, not verified people.</p>',
             '<div class="stats">',
             f'<div class="stat"><strong>{result["input_count"]}</strong>input labels</div>',
             f'<div class="stat"><strong>{result["distinct_handoff_content_count"]}</strong>distinct draft contents</div>',
             f'<div class="stat"><strong>{len(pending)}</strong>cells in review queue</div>',
             '<div class="stat"><strong>12</strong>cells retained</div></div>',
             '<p>Matching entries do not establish agreement between independent reviewers. Different notes do not automatically prove conflicting evidence.</p></header>',
             '<main id="review-start" tabindex="-1"><h2>Review the twelve cells</h2>',
             '<p class="print-note">Complete print view: all twelve cells are included, regardless of screen filters.</p>',
             '<div id="reader-controls" class="controls" hidden><div class="filters" role="group" aria-label="Filter cells by review state">',
             ''.join(f'<button type="button" data-filter="{value}" aria-pressed="{str(value=="all").lower()}">{label}</button>'
                     for value, label in (("all","All cells"),("pending","Pending review"),("disagreement","Disagreement"),("unreviewed","Unreviewed"))),
             '</div><div class="searches"><div class="field"><label for="group-filter">Group</label><select id="group-filter"><option value="">All groups</option>' + ''.join(f'<option>{g}</option>' for g in hr.GROUPS) + '</select></div>',
             '<div class="field"><label for="text-filter">Search notes, labels and sources</label><input type="search" id="text-filter" aria-describedby="filter-status" autocomplete="off"></div></div>',
             '<button type="button" id="reset-filters">Clear filters</button><p id="filter-status" role="status" aria-live="polite"></p></div>',
             '<nav class="index" aria-label="All assessment cells">',
             ''.join(f'<a href="#cell-{g}-{d}">{g} / {DIMENSION_NAMES[d]}</a>' for g,d in hr.CELLS),
             '</nav><p id="missing-target" role="status" hidden></p>',
             '<section class="receipts" aria-labelledby="input-title"><h2 id="input-title">Input lineage</h2>',
             '<p>Identical content is not independent corroboration. Every label and normalized-content digest is retained below.</p><ul>']
    for item in result['inputs']:
        parts.append(f'<li><strong>{_e(item["label"])}</strong> · <code>{item["normalized_handoff_sha256"]}</code></li>')
    parts.append('</ul>')
    groups = result['identical_content_groups']
    if groups:
        parts.append('<p><strong>Identical-content groups:</strong> ' + '; '.join(', '.join(_e(x) for x in group) for group in groups) + '</p>')
    else:
        parts.append('<p>No identical whole-export contents were supplied. This does not authenticate different authors.</p>')
    parts.append('</section>')
    for cell in result['assessment_cells']:
        g,d = cell['group'],cell['dimension']
        reasons = cell['review_reason_codes']
        parts.extend([f'<article class="cell" id="cell-{g}-{d}" data-group="{g}" data-pending="{"yes" if (g,d) in pending else "no"}" data-reasons="{_e(" ".join(reasons))}">',
                      f'<h2 tabindex="-1">{g} / {DIMENSION_NAMES[d]}</h2>',
                      f'<p class="state">{"Pending review" if (g,d) in pending else "Matching entries — not acceptance"}</p>',
                      f'<p>Original compiler state: <code>{_e(cell["compiler_status"])}</code></p><ul class="reasons">'])
        for reason in reasons:
            parts.append(f'<li><code>{_e(reason)}</code><br>{_e(REASONS.get(reason,"Retained engine reason; inspect the original record."))}</li>')
        parts.append('</ul><div class="notes">')
        for entry in cell['entries']:
            note = entry['analyst_note']
            parts.extend(['<section class="note">', f'<h3>{_e(entry["label"])}</h3><p><code>{_e(entry["disposition"])}</code></p>',
                          f'<div class="note-text">{_e(note)}</div>' if note else '<p class="empty">No note supplied.</p>', '</section>'])
        parts.append('</div><h3>Original evidence references</h3>')
        if not cell['source_ids']:
            parts.append('<p>No source record supplied for this cell. Missing evidence is not a performance score.</p>')
        else:
            parts.append('<ul class="sources">')
            for sid, record_sha in zip(cell['source_ids'],cell['source_record_sha256s']):
                source = sources[sid]
                parts.extend([f'<li><strong>{_e(sid)}</strong> · {_locator(source["source_ref"])}',
                              f'<br>Source record digest: <code>{record_sha}</code>',
                              f'<br>Observed at: <code>{_e(source["observed_at"])}</code>',
                              f'<p>{_e(source["claim"])}</p><details><summary>Exact source record</summary><pre>{_e(json.dumps(source,ensure_ascii=False,sort_keys=True,indent=2))}</pre></details></li>'])
            parts.append('</ul>')
        parts.extend([f'<details><summary>Full retained cell record</summary><pre>{_e(json.dumps(cell,ensure_ascii=False,sort_keys=True,indent=2))}</pre></details>',
                      '<p>Compiler reason codes: <code>' + _e(', '.join(cell['compiler_reason_codes']) or '(none supplied)') + '</code></p></article>'])
    encoded = base64.b64encode(hr.canonical(result)+b'\n').decode('ascii')
    parts.extend(['<section class="receipts"><h2>Receipts and limits</h2>',
                  f'<p>Parent report: <code>{result["report_receipt_sha256"]}</code><br>Reconciliation: <code>{result["reconciliation_sha256"]}</code></p>',
                  '<p>The existing compiler verified internal report semantics. It did not authenticate source provenance, reviewer identities, current authority or University conclusions. All approval, submission, signature and payment authority flags remain false.</p>',
                  f'<a class="download" download="draft-reconciliation.json" href="data:application/json;base64,{encoded}">Download exact reconciliation JSON</a>',
                  '</section></main><footer>Read-only export. No uploads, external services, analytics or persistent browser storage. Screen filters never edit data. Regenerate the file after source changes.</footer>',
                  f'<script>{SCRIPT}</script></body></html>\n'])
    return '\n'.join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    parser.add_argument('--handoff',nargs=2,metavar=('LABEL','PATH'),action='append',required=True)
    parser.add_argument('--classification',choices=CLASSIFICATIONS,required=True)
    parser.add_argument('--output',type=Path,required=True,help='New HTML file; existing files are never overwritten')
    args=parser.parse_args(argv)
    try:
        if len(args.handoff)>hr.MAX_HANDOFFS:
            raise hr.ReviewError('at most twenty handoffs are supported')
        report=hr.load_json(args.report)
        handoffs=[(label,hr.load_json(Path(path))) for label,path in args.handoff]
        text=build_html(report,handoffs,classification=args.classification)
        hr._write_new(args.output,text.encode('utf-8'))
        print('DRAFT_REVIEW_HTML_WRITTEN')
        return 0
    except (hr.ReviewError,OSError,ValueError) as exc:
        detail=str(exc) if isinstance(exc,hr.ReviewError) else 'file operation or parent compilation failed'
        print(f'ERROR: {detail}',file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
