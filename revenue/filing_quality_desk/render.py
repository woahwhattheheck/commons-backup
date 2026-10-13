import csv,html,io
from .core import FilingQualityError,canon,sha
from .compiler import compile_packet

def csv_bytes(rows,fields):
    b=io.StringIO(newline='');w=csv.DictWriter(b,fieldnames=fields,lineterminator='\n',extrasaction='ignore');w.writeheader()
    for r in rows:w.writerow({k:'' if r.get(k) is None else (';'.join(r[k]) if isinstance(r.get(k),list) else r.get(k)) for k in fields})
    return b.getvalue().encode()
def outputs(source_raw,policy_raw):
    p=compile_packet(source_raw,policy_raw);obs=['selector_id','taxonomy','concept','unit','kind','start','end','value','filed','accession','form','provenance_accessions','prior_values'];cmp=['selector_id','unit','period','prior_value','prior_filed','prior_accession','prior_form','selected_value','selected_filed','selected_accession','selected_form','delta','delta_pct'];fs=['id','severity','code','detail']
    rows=''.join('<tr>'+''.join(f'<td>{html.escape(str(o.get(k,"")))}</td>' for k in ('selector_id','concept','unit','end','value','filed','accession'))+'</tr>' for o in p['observations'])
    crows=''.join('<tr>'+''.join(f'<td>{html.escape(str(c.get(k,"")))}</td>' for k in ('selector_id','prior_value','prior_filed','prior_accession','selected_value','selected_filed','selected_accession','delta','delta_pct'))+'</tr>' for c in p['comparisons'])
    frows=''.join('<tr>'+''.join(f'<td>{html.escape(str(f.get(k,"")))}</td>' for k in ('severity','code','id','detail'))+'</tr>' for f in p['findings'])
    report=(f"<!doctype html><meta charset='utf-8'><title>Filing Quality Desk</title><h1>Filing Quality Desk</h1><p>Status: <b>{p['status']}</b></p><table border='1'>{rows}</table><h2>Observed value changes</h2><table border='1'>{crows}</table><h2>Findings</h2><table border='1'>{frows}</table>\n").encode()
    out={'packet.json':canon(p),'observations.csv':csv_bytes(p['observations'],obs),'comparisons.csv':csv_bytes(p['comparisons'],cmp),'findings.csv':csv_bytes(p['findings'],fs),'report.html':report}
    out['manifest.json']=canon({'schema':'tjlabs.filing-quality-desk.manifest/v1','source_sha256':p['source_sha256'],'policy_sha256':p['policy_sha256'],'semantic_sha256':p['semantic_sha256'],'files':{k:sha(v) for k,v in sorted(out.items())}});return out
def verify_outputs(source_raw,policy_raw,produced):
    expected=outputs(source_raw,policy_raw)
    if set(expected)!=set(produced):raise FilingQualityError('output file set mismatch')
    for k in expected:
        if expected[k]!=produced[k]:raise FilingQualityError(f'output mismatch: {k}')
