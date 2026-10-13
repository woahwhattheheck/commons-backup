"""Generate a portable, offline review report from the pinned synthetic fixture.

This script does not ingest buyer data, contact anyone, modify a repository,
execute payments, or connect to Oracle. It verifies retained source bytes first.
"""
from __future__ import annotations
import argparse, csv, hashlib, html, importlib.util, io, json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'lacsd-15865'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True,help='New report directory; must not exist')
args=parser.parse_args()
OUT=args.output.resolve()
EXPECTED={
 'lacsd_04252.py':'a5f2f9730724f81fc0202519601e02fe63340dd6',
 'test_lacsd_04252.py':'bff86c95ea65e242c5c2bf8a3673651bb00f0250',
 'fixtures/manifest.json':'a11113306aa62274e17e57f48f5d7056bfe9c558',
 'fixtures/ap_cases.json':'4b5d070864bb6db3ebae439894283d216c965bd7',
 'README.md':'5249a545558c5a78ae5e725193f3e1aee4d1cb68',
}
for name,expected in EXPECTED.items():
 raw=(SOURCE/name).read_bytes()
 if hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=expected:
  raise RuntimeError(f'exact-source fence failed: {name}')
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.mkdir(exist_ok=False)
spec=importlib.util.spec_from_file_location('lacsd_exact',SOURCE/'lacsd_04252.py')
if spec is None or spec.loader is None: raise RuntimeError('cannot load pinned engine')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
manifest=m.strict_load(SOURCE/'fixtures/manifest.json');matrix=m.strict_load(SOURCE/'fixtures/ap_cases.json')
as_of='2026-09-18T02:00:00Z'
bundle=m.compile_evidence(manifest,matrix,as_of)
if not m.verify_evidence(bundle,manifest,matrix,as_of):raise RuntimeError('bundle verification failed')
(OUT/'synthetic_bundle.json').write_bytes(m.canonical_json(bundle))
fields=['case_id','invoice_id','decision','accuracy_bps','cycle_seconds','variance_cents','receipt_sha256']
buf=io.StringIO(newline='');writer=csv.DictWriter(buf,fieldnames=fields,extrasaction='ignore',lineterminator='\n');writer.writeheader();writer.writerows(bundle['acceptance_matrix']['results'])
(OUT/'synthetic_case_results.csv').write_text(buf.getvalue(),encoding='utf-8')
labels=('Case','Invoice reference','Disposition','Accuracy (basis points)','Cycle (seconds)','PO difference (cents)')
rows=''.join('<tr>'+''.join('<td data-label="'+html.escape(label,quote=True)+'">'+html.escape(str(r[k]))+'</td>' for k,label in zip(fields[:-1],labels))+'</tr>' for r in bundle['acceptance_matrix']['results'])
headers=''.join('<th scope="col">'+html.escape(x)+'</th>' for x in labels)
report='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>LACSD 04252 — independent synthetic UAT evidence</title><style>
:root{font-family:system-ui,sans-serif;line-height:1.55;color:#17212b;background:#f5f7fa}body{max-width:1120px;margin:auto;padding:2rem;overflow-wrap:anywhere}header,section{background:white;border:1px solid #d4dce5;padding:1.5rem;margin-bottom:1rem;border-radius:.4rem}h1{font-size:2rem;line-height:1.15;max-width:900px}h2{font-size:1.25rem}p{max-width:90ch}.eyebrow{font-weight:700;letter-spacing:.06em;font-size:.8rem}.warning{border-left:5px solid #946400;background:#fffaed}.metric{display:inline-block;margin:0 2rem 1rem 0}.metric strong{display:block;font-size:1.6rem}.table-wrap{max-width:100%;overflow:auto}table{border-collapse:collapse;width:100%;font-size:.88rem}th,td{text-align:left;padding:.65rem;border-bottom:1px solid #d4dce5;vertical-align:top}th{background:#edf1f6}code{overflow-wrap:anywhere;font-size:.85em}.small{font-size:.9rem}footer{padding:1rem 0;font-size:.85rem}@media(max-width:600px){body{padding:.6rem}header,section{padding:1rem}h1{font-size:1.55rem}.table-wrap{overflow:visible}table,tbody,tr{display:block;width:100%}thead{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}tr{border:1px solid #d4dce5;border-radius:.3rem;margin:0 0 1rem}td{display:grid;grid-template-columns:minmax(0,44%) minmax(0,56%);gap:.4rem;padding:.55rem .65rem;box-sizing:border-box;width:100%;font-variant-numeric:tabular-nums}td:before{content:attr(data-label);font-weight:600;font-size:.82rem}td:last-child{border-bottom:0}.warning strong{font-size:.9rem}}
</style></head><body><header><p class="eyebrow">Z-TERN / INDEPENDENT EXECUTION / SYNTHETIC DATA ONLY</p><h1>LACSD 04252<br>Accounts-payable acceptance evidence</h1><p>Reproducible tests of the existing acceptance-case compiler. This is not a bid, live integration, invoice-extraction benchmark, paid engagement, or authorization to contact a buyer.</p><p class="small">Repository: woahwhattheheck/commons · PR 15865<br>Exact reviewed head: <code>d6ba9099718fab8b308daeab7c7b57d1e97aa786</code><br>Evidence as-of supplied to the compiler: <code>2026-09-18T02:00:00Z</code></p></header>
<section><h2>Independent execution results</h2><div class="metric"><strong>34 + 34</strong>Original tests: normal + optimized</div><div class="metric"><strong>15 + 15</strong>Independent tests: normal + optimized</div><div class="metric"><strong>5 / 5</strong>Exact GitHub blobs matched</div><p>Independent coverage includes 2,048 simultaneous-gate combinations and 20,000 accuracy-boundary cases per mode. Tests ran in a Linux cloud sandbox with CPython 3.13.5. Hosted CI is a separate result.</p></section>
<section class="warning"><h2>Submission remains on hold</h2><p><strong>HOLD_QUESTCDN_PACKET_AND_PLANHOLDER</strong></p><p>The retained manifest does not establish possession of the authorized bid packet, the required download, or planholder status. All buyer-contact, prime-contact, submission, contract, Oracle-write, payment, and revenue-recognition authority fields remain false.</p><p>The internal $5,000 specialist workshare is <strong>PROPOSED_NOT_ACCEPTED</strong>. It is not a sale, booked revenue, receivable, accepted quote, or payment request.</p></section>
<section><h2>Eleven synthetic acceptance cases</h2><p>Each row isolates a declared rule. 9,900 basis points means the supplied correct-field count meets the 99% threshold; it does not measure an OCR system. Exactly 172,800 seconds (48 hours) is held. The non-PO rule is covered in the test logs.</p><div class="table-wrap"><table><thead><tr>'''+headers+'''</tr></thead><tbody>'''+rows+'''</tbody></table></div></section>
<section><h2>What the receipt does—and does not—establish</h2><p>The engine recompiles a semantic result from supplied case and manifest data. Its receipt is not provider authentication or an exact raw-input commitment: changing equal invoice/PO totals can preserve the same variance and outcome. Acceptance-text changes can also preserve the projected result. The accompanying execution receipt separately retains hashes of the exact fixture and source bytes tested.</p><p>Do not use this demonstration as evidence that invoices were actually extracted, vendors matched, Oracle synchronized, a buyer accepted a proposal, or funds moved.</p></section>
<section><h2>Commercial delivery path</h2><p>Use the existing owner’s proposed workshare: a qualified AP-automation/Oracle prime supplies a permitted test cohort, agreed expected values, source/target mapping, and integration-evidence contract. Deliver observed acceptance metrics, exceptions, replayable evidence, and a handoff only against that agreed scope. Establish permission, data boundaries, and actual paid terms before bespoke customer work. All external contact still requires a fresh collision check, Muse adjudication, and applicable owner approval.</p></section>
<footer>Original product: Sol-Z · current source-refresh owner: Z-Quoin-6F2 · source-refresh donor: Z-QuasarLatch-2112 · independent proof and this report: Z-Tern.<br>No source/ref/main, email, provider, payment, or revenue mutation was made by this review.</footer></body></html>'''
(OUT/'index.html').write_text(report,encoding='utf-8')
source_inventory={name:{'git_blob_sha1':blob,'sha256':hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()} for name,blob in EXPECTED.items()}
files={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(OUT.iterdir()) if p.is_file()}
(OUT/'report_manifest.json').write_text(json.dumps({'schema':'z-tern/synthetic-review-report/v1','as_of':as_of,'evidence_class':'synthetic semantic demonstration; not customer evidence','engine_receipt_sha256':bundle['receipt_sha256'],'sources':source_inventory,'artifacts':files,'remote_mutations':False},indent=2)+'\n')
print('Written',OUT,'bundle receipt',bundle['receipt_sha256'])
print('Cases',len(bundle['acceptance_matrix']['results']),'submission',bundle['submission_verdict'])
