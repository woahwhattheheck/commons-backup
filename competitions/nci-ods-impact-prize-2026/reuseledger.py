#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path
MANIFEST_SCHEMA='nci-reuseledger-manifest/v1'; PACKET_SCHEMA='nci-reuseledger-packet/v1'
KINDS={'dataset','software','protocol','model','publication','clinical_trial_results','biospecimen','other'}; ACCESS={'open','restricted','controlled','metadata_only'}
OUTPUT_KEYS={'id','kind','title','access','landing_url','license','data_use','fixity','depends_on'}; HEX64=re.compile(r'^[0-9a-f]{64}$'); PID=re.compile(r'^(?:https?://|doi:10\.\d{4,9}/|urn:)[^\s]+$',re.I)
class LedgerError(ValueError): pass

def strict_object(pairs):
    out={}
    for k,v in pairs:
        if k in out: raise LedgerError(f'duplicate JSON key: {k}')
        out[k]=v
    return out

def load_json(path):
    raw=Path(path).read_bytes()
    try: text=raw.decode('utf-8')
    except UnicodeDecodeError as e: raise LedgerError('JSON must be UTF-8') from e
    try: val=json.loads(text,object_pairs_hook=strict_object)
    except json.JSONDecodeError as e: raise LedgerError(f'invalid JSON: {e}') from e
    return val,raw

def canon(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(raw): return hashlib.sha256(raw).hexdigest()
def exact(d,keys,where):
    if type(d) is not dict: raise LedgerError(f'{where}: expected object')
    if set(d)!=keys: raise LedgerError(f'{where}: key mismatch missing={sorted(keys-set(d))} extra={sorted(set(d)-keys)}')
def s(v,where,limit=1000):
    if type(v) is not str or not v.strip(): raise LedgerError(f'{where}: expected non-empty string')
    v=v.strip()
    if len(v)>limit: raise LedgerError(f'{where}: too long')
    return v

def fixity(v,where):
    if v is None: return None
    exact(v,{'sha256','bytes'},where); h=s(v['sha256'],where+'.sha256',64).lower()
    if not HEX64.fullmatch(h): raise LedgerError(f'{where}.sha256: expected 64-hex')
    n=v['bytes']
    if type(n) is not int or n<0: raise LedgerError(f'{where}.bytes: expected non-negative integer')
    return {'sha256':h,'bytes':n}

def norm_output(row,i):
    w=f'outputs[{i}]'; exact(row,OUTPUT_KEYS,w); oid=s(row['id'],w+'.id')
    if not PID.fullmatch(oid): raise LedgerError(f'{w}.id: stable DOI/HTTP(S)/URN identifier required')
    kind=s(row['kind'],w+'.kind',64); access=s(row['access'],w+'.access',32)
    if kind not in KINDS: raise LedgerError(f'{w}.kind: unsupported')
    if access not in ACCESS: raise LedgerError(f'{w}.access: unsupported')
    url=s(row['landing_url'],w+'.landing_url')
    if not url.startswith('https://'): raise LedgerError(f'{w}.landing_url: HTTPS required')
    lic=None if row['license'] is None else s(row['license'],w+'.license',200); use=None if row['data_use'] is None else s(row['data_use'],w+'.data_use')
    deps=row['depends_on']
    if type(deps) is not list: raise LedgerError(f'{w}.depends_on: expected array')
    nd=[s(d,f'{w}.depends_on[{j}]') for j,d in enumerate(deps)]
    if len(nd)!=len(set(nd)): raise LedgerError(f'{w}.depends_on: duplicates')
    return {'id':oid,'kind':kind,'title':s(row['title'],w+'.title',500),'access':access,'landing_url':url,'license':lic,'data_use':use,'fixity':fixity(row['fixity'],w+'.fixity'),'depends_on':sorted(nd)}

def normalize(m):
    exact(m,{'schema','project','outputs'},'manifest')
    if m['schema']!=MANIFEST_SCHEMA: raise LedgerError('manifest.schema mismatch')
    rows=m['outputs']
    if type(rows) is not list or not rows or len(rows)>1000: raise LedgerError('manifest.outputs: expected 1..1000 rows')
    rows=sorted((norm_output(x,i) for i,x in enumerate(rows)),key=lambda x:x['id']); by={}
    for x in rows:
        if x['id'] in by: raise LedgerError(f"duplicate id: {x['id']}")
        by[x['id']]=x
    for x in rows:
        for d in x['depends_on']:
            if d==x['id']: raise LedgerError('self-dependency')
            if d not in by: raise LedgerError(f'unknown dependency: {d}')
    state={}
    def visit(n,stack):
        if state.get(n)==2:return
        if state.get(n)==1: raise LedgerError('dependency cycle: '+' -> '.join(stack+[n]))
        state[n]=1
        for d in by[n]['depends_on']:visit(d,stack+[n])
        state[n]=2
    for n in sorted(by):visit(n,[])
    return {'schema':MANIFEST_SCHEMA,'project':s(m['project'],'manifest.project',200),'outputs':rows}

def findings(rows):
    out=[]
    def add(code,r,severity,msg):out.append({'code':code,'output_id':r['id'],'severity':severity,'message':msg})
    for x in rows:
        if x['license'] is None:add('MISSING_LICENSE',x,'blocker' if x['access']=='open' else 'warning','Record an explicit reuse license or rights statement.')
        if x['access'] in {'restricted','controlled','metadata_only'} and x['data_use'] is None:add('MISSING_DATA_USE',x,'blocker','Record the access/data-use conditions.')
        if x['access']=='open' and x['kind'] in {'dataset','software','protocol','model','other'} and x['fixity'] is None:add('MISSING_FIXITY',x,'warning','Publish byte-level fixity when practical.')
    return sorted(out,key=lambda x:(x['severity'],x['code'],x['output_id']))

def compile_packet(m,source_hash):
    if type(source_hash) is not str or not HEX64.fullmatch(source_hash):raise LedgerError('source hash malformed')
    n=normalize(m); fs=findings(n['outputs']); edges=sorted(({'from':x['id'],'relation':'depends_on','to':d} for x in n['outputs'] for d in x['depends_on']),key=lambda e:(e['from'],e['to'])); b=sum(x['severity']=='blocker' for x in fs); w=sum(x['severity']=='warning' for x in fs)
    p={'schema':PACKET_SCHEMA,'project':n['project'],'source_file_sha256':source_hash,'manifest_semantic_sha256':sha(canon(n)),'outputs':n['outputs'],'graph':edges,'findings':fs,'summary':{'output_count':len(n['outputs']),'dependency_edges':len(edges),'blockers':b,'warnings':w,'reuse_readiness_score':max(0,100-20*b-5*w)}};p['semantic_sha256']=sha(canon(p));return p

def verify_packet(p):
    try:
        exact(p,{'schema','project','source_file_sha256','manifest_semantic_sha256','outputs','graph','findings','summary','semantic_sha256'},'packet')
        if p['schema']!=PACKET_SCHEMA:raise LedgerError('packet.schema mismatch')
        sem=p['semantic_sha256'];u=dict(p);u.pop('semantic_sha256')
        if type(sem) is not str or not HEX64.fullmatch(sem) or sha(canon(u))!=sem:raise LedgerError('packet semantic digest mismatch')
        sh=p['source_file_sha256']
        if type(sh) is not str or not HEX64.fullmatch(sh):raise LedgerError('source hash malformed')
        n=normalize({'schema':MANIFEST_SCHEMA,'project':p['project'],'outputs':p['outputs']})
        if sha(canon(n))!=p['manifest_semantic_sha256']:raise LedgerError('manifest semantic digest mismatch')
        if compile_packet(n,sh)!=p:raise LedgerError('packet derivation mismatch')
        return True,'ok'
    except (LedgerError,TypeError,ValueError) as e:return False,str(e)

def verify_manifest(p,m,raw):
    ok,why=verify_packet(p)
    if not ok:return ok,why
    try:
        if compile_packet(normalize(m),sha(raw))!=p:raise LedgerError('packet does not match exact supplied manifest bytes')
        return True,'ok'
    except (LedgerError,TypeError,ValueError) as e:return False,str(e)

def report(p):
    ok,why=verify_packet(p)
    if not ok:raise LedgerError(why)
    q=p['summary']; lines=[f"# ReuseLedger report — {p['project']}",'',f"- Outputs: {q['output_count']}",f"- Dependency edges: {q['dependency_edges']}",f"- Blockers: {q['blockers']}",f"- Warnings: {q['warnings']}",f"- Reuse-readiness score: {q['reuse_readiness_score']}/100",f"- Packet SHA-256: `{p['semantic_sha256']}`",'','## Findings','']
    lines+=['No rule-based findings.'] if not p['findings'] else [f"- **{x['severity'].upper()} {x['code']}** — `{x['output_id']}` — {x['message']}" for x in p['findings']]
    lines+=['','Metadata quality only: not scientific, clinical, privacy, legal, consent, or repository certification.',''];return '\n'.join(lines)
def write_new(path,raw):
    if path.exists():raise LedgerError(f'refusing to overwrite {path}')
    path.write_bytes(raw)
def main(argv=None):
    ap=argparse.ArgumentParser();sp=ap.add_subparsers(dest='cmd',required=True);c=sp.add_parser('compile');c.add_argument('manifest',type=Path);c.add_argument('--out',type=Path,required=True);v=sp.add_parser('verify');v.add_argument('packet',type=Path);v.add_argument('--manifest',type=Path,required=True);q=sp.add_parser('report');q.add_argument('packet',type=Path);q.add_argument('--out',type=Path,required=True);a=ap.parse_args(argv)
    try:
        if a.cmd=='compile':m,raw=load_json(a.manifest);write_new(a.out,(json.dumps(compile_packet(m,sha(raw)),indent=2,sort_keys=True)+'\n').encode());return 0
        if a.cmd=='verify':p,_=load_json(a.packet);m,raw=load_json(a.manifest);ok,why=verify_manifest(p,m,raw);print('VALID' if ok else 'INVALID: '+why);return 0 if ok else 2
        p,_=load_json(a.packet);write_new(a.out,report(p).encode());return 0
    except LedgerError as e:print('ERROR:',e);return 2
if __name__=='__main__':raise SystemExit(main())
