from __future__ import annotations

import argparse, hashlib, json, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

INPUT_SCHEMA='tjlabs.prize-readiness-input/v1'
PACKET_SCHEMA='tjlabs.prize-readiness-packet/v1'
NONE='NONE'; MAX_AGE_DAYS=30; CLOCK_SKEW_SECONDS=300
SHA_RE=re.compile(r'^[0-9a-f]{64}$')
STATES={'HOLD_SOURCE_INCOMPLETE','HOLD_SOURCE_STALE','HOLD_SOURCE_TIME','HOLD_OWNERSHIP_CONFLICT','HOLD_REVIEW_RED','RESEARCH_IN_PROGRESS','QUALIFYING_RESULT_REVIEW_REQUIRED','OWNER_SUBMISSION_REQUIRED','QUALIFYING_RESULT_READY','EXPIRED_NOT_SUBMITTED','SUBMITTED_AWAITING_DECISION','AWARDED_UNPAID','PAID'}

class ReadinessError(ValueError): pass

def _pairs(pairs):
    out={}
    for k,v in pairs:
        if k in out: raise ReadinessError(f'duplicate JSON key: {k}')
        out[k]=v
    return out

def strict_loads(text):
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=lambda x: (_ for _ in ()).throw(ReadinessError(f'non-finite number: {x}')))

def strict_load(path): return strict_loads(Path(path).read_text(encoding='utf-8'))
def canonical(value): return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()
def digest(value): return hashlib.sha256(value).hexdigest()
sha256_hex = digest
canonical_json = canonical

def exact(obj, keys, where):
    if type(obj) is not dict or set(obj)!=set(keys): raise ReadinessError(f'{where}: exact object keys required')
    return obj

def text(v, where, n=800):
    if type(v) is not str or not v or len(v)>n or any(ord(c)<32 and c not in '\t\n' for c in v): raise ReadinessError(f'{where}: bounded text required')
    return v

def boolean(v, where):
    if type(v) is not bool: raise ReadinessError(f'{where}: bool required')
    return v

def integer(v, where):
    if type(v) is not int or not 0<=v<=10**15: raise ReadinessError(f'{where}: nonnegative bounded int required')
    return v

def sha(v, where, allow_none=False):
    if allow_none and v==NONE: return v
    v=text(v,where,64)
    if not SHA_RE.fullmatch(v): raise ReadinessError(f'{where}: lowercase SHA-256 required')
    return v

def enum(v, choices, where):
    v=text(v,where,80)
    if v not in choices: raise ReadinessError(f'{where}: invalid enum')
    return v

def utc(v, where, allow_none=False):
    if allow_none and v==NONE: return None
    v=text(v,where,40)
    if not v.endswith('Z'): raise ReadinessError(f'{where}: UTC Z timestamp required')
    try: dt=datetime.fromisoformat(v[:-1]+'+00:00')
    except ValueError as e: raise ReadinessError(f'{where}: bad timestamp') from e
    return dt

def iso(dt): return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')

def normalize(raw):
    r=exact(raw,{'schema','opportunity_id','synthetic_fixture','source','work','entry','award','payment','ownership'},'input')
    if r['schema']!=INPUT_SCHEMA: raise ReadinessError('unsupported schema')
    opp=text(r['opportunity_id'],'opportunity_id',160); synthetic=boolean(r['synthetic_fixture'],'synthetic_fixture')
    s=exact(r['source'],{'source_type','source_url','source_sha256','capture_receipt_sha256','captured_at','source_complete','currency','advertised_amount_minor','deadline_utc','deliverable_kind','deliverable_requirement'},'source')
    st=enum(s['source_type'],{'FIRST_PARTY','FIXTURE_DERIVED'},'source_type')
    if not synthetic and st!='FIRST_PARTY': raise ReadinessError('production inputs require FIRST_PARTY')
    u=text(s['source_url'],'source_url',700); p=urlparse(u)
    if p.scheme!='https' or not p.hostname or p.username or p.password: raise ReadinessError('source_url: public HTTPS required')
    captured=utc(s['captured_at'],'captured_at'); deadline=utc(s['deadline_utc'],'deadline_utc',True)
    currency=enum(s['currency'],{'USD','EUR','GBP','CAD','AUD','JPY','CHF'},'currency')
    source={'source_type':st,'source_url':u,'source_sha256':sha(s['source_sha256'],'source_sha256'),'capture_receipt_sha256':sha(s['capture_receipt_sha256'],'capture_receipt_sha256'),'captured_at':iso(captured),'source_complete':boolean(s['source_complete'],'source_complete'),'currency':currency,'advertised_amount_minor':integer(s['advertised_amount_minor'],'advertised_amount_minor'),'deadline_utc':NONE if deadline is None else iso(deadline),'deliverable_kind':enum(s['deliverable_kind'],{'PUBLISHED_PROOF','CODE_PACKAGE','LEADERBOARD_SUBMISSION','PROPOSAL','RESEARCH_ARTIFACT','OTHER'},'deliverable_kind'),'deliverable_requirement':text(s['deliverable_requirement'],'deliverable_requirement')}
    w=exact(r['work'],{'carrier_repo','carrier_ref','carrier_sha256','result_level','independent_review','evidence_sha256'},'work')
    evidence=w['evidence_sha256']
    if type(evidence) is not list or len(evidence)>32: raise ReadinessError('work evidence list required')
    evidence=[sha(x,'work evidence') for x in evidence]
    if len(set(evidence))!=len(evidence): raise ReadinessError('duplicate work evidence')
    work={'carrier_repo':text(w['carrier_repo'],'carrier_repo',160),'carrier_ref':text(w['carrier_ref'],'carrier_ref',160),'carrier_sha256':sha(w['carrier_sha256'],'carrier_sha256',True),'result_level':enum(w['result_level'],{'NONE','PARTIAL','QUALIFYING'},'result_level'),'independent_review':enum(w['independent_review'],{'UNKNOWN','PASS','RED'},'independent_review'),'evidence_sha256':sorted(evidence)}
    if work['result_level']!='NONE' and work['carrier_sha256']==NONE: raise ReadinessError('result requires carrier SHA')
    if work['result_level']=='QUALIFYING' and not evidence: raise ReadinessError('qualifying result requires evidence')
    e=exact(r['entry'],{'account_required','registration_required','registration_evidence_sha256','submission_required','submission_evidence_sha256','submitted_at','submission_route'},'entry')
    entry={'account_required':boolean(e['account_required'],'account_required'),'registration_required':boolean(e['registration_required'],'registration_required'),'registration_evidence_sha256':sha(e['registration_evidence_sha256'],'registration evidence',True),'submission_required':boolean(e['submission_required'],'submission_required'),'submission_evidence_sha256':sha(e['submission_evidence_sha256'],'submission evidence',True),'submitted_at':e['submitted_at'],'submission_route':text(e['submission_route'],'submission_route',300)}
    submitted=utc(entry['submitted_at'],'submitted_at',True); entry['submitted_at']=NONE if submitted is None else iso(submitted)
    if (entry['submission_evidence_sha256']==NONE)!=(submitted is None): raise ReadinessError('submission evidence and timestamp must coexist')
    if entry['registration_required'] and entry['submission_evidence_sha256']!=NONE and entry['registration_evidence_sha256']==NONE: raise ReadinessError('submission requires registration evidence')
    a=exact(r['award'],{'award_evidence_sha256','amount_minor','currency','provider_ref'},'award')
    award={'award_evidence_sha256':sha(a['award_evidence_sha256'],'award evidence',True),'amount_minor':integer(a['amount_minor'],'award amount'),'currency':enum(a['currency'],{currency},'award currency'),'provider_ref':text(a['provider_ref'],'award provider',160)}
    if award['award_evidence_sha256']==NONE and (award['amount_minor']!=0 or award['provider_ref']!=NONE): raise ReadinessError('award facts require evidence')
    if award['award_evidence_sha256']!=NONE and (award['amount_minor']<=0 or award['provider_ref']==NONE): raise ReadinessError('award evidence requires positive amount/provider')
    if award['award_evidence_sha256']!=NONE and entry['submission_required'] and entry['submission_evidence_sha256']==NONE: raise ReadinessError('award cannot precede required submission')
    q=exact(r['payment'],{'payment_evidence_sha256','amount_minor','currency','provider_ref'},'payment')
    payment={'payment_evidence_sha256':sha(q['payment_evidence_sha256'],'payment evidence',True),'amount_minor':integer(q['amount_minor'],'payment amount'),'currency':enum(q['currency'],{currency},'payment currency'),'provider_ref':text(q['provider_ref'],'payment provider',160)}
    if payment['payment_evidence_sha256']==NONE and (payment['amount_minor']!=0 or payment['provider_ref']!=NONE): raise ReadinessError('payment facts require evidence')
    if payment['payment_evidence_sha256']!=NONE:
        if award['award_evidence_sha256']==NONE: raise ReadinessError('payment requires award evidence')
        if payment['amount_minor']<=0 or payment['provider_ref']==NONE or payment['amount_minor']>award['amount_minor']: raise ReadinessError('invalid payment evidence')
    o=exact(r['ownership'],{'owner_key','duplicate_state'},'ownership')
    ownership={'owner_key':text(o['owner_key'],'owner_key',160),'duplicate_state':enum(o['duplicate_state'],{'UNIQUE','UNKNOWN','CONFLICT'},'duplicate_state')}
    roots=[source['capture_receipt_sha256'],*evidence,*[x for x in (entry['registration_evidence_sha256'],entry['submission_evidence_sha256'],award['award_evidence_sha256'],payment['payment_evidence_sha256']) if x!=NONE]]
    if len(set(roots))!=len(roots): raise ReadinessError('evidence roots must be disjoint')
    return {'schema':INPUT_SCHEMA,'opportunity_id':opp,'synthetic_fixture':synthetic,'source':source,'work':work,'entry':entry,'award':award,'payment':payment,'ownership':ownership}

def derive(d, now):
    s,w,e,a,p,o=d['source'],d['work'],d['entry'],d['award'],d['payment'],d['ownership']
    cap=utc(s['captured_at'],'captured_at'); deadline=utc(s['deadline_utc'],'deadline',True); submitted=utc(e['submitted_at'],'submitted_at',True)
    if (cap-now).total_seconds()>CLOCK_SKEW_SECONDS: return 'HOLD_SOURCE_TIME',['source capture is future-dated']
    if p['payment_evidence_sha256']!=NONE: return 'PAID',['distinct provider award and payment evidence retained']
    if a['award_evidence_sha256']!=NONE: return 'AWARDED_UNPAID',['provider award evidence retained; payment evidence absent']
    if e['submission_evidence_sha256']!=NONE:
        if deadline and submitted and submitted>deadline: raise ReadinessError('submission is after controlling deadline')
        return 'SUBMITTED_AWAITING_DECISION',['submission receipt retained; award evidence absent']
    if not s['source_complete']: return 'HOLD_SOURCE_INCOMPLETE',['controlling first-party terms incomplete']
    if (now-cap).total_seconds()>MAX_AGE_DAYS*86400: return 'HOLD_SOURCE_STALE',['controlling source capture is stale']
    if o['duplicate_state']=='CONFLICT': return 'HOLD_OWNERSHIP_CONFLICT',['ownership conflict unresolved']
    if deadline and now>deadline: return 'EXPIRED_NOT_SUBMITTED',['deadline passed without submission receipt']
    if w['independent_review']=='RED': return 'HOLD_REVIEW_RED',['independent review is RED']
    if w['result_level']=='QUALIFYING':
        if w['independent_review']!='PASS': return 'QUALIFYING_RESULT_REVIEW_REQUIRED',['qualifying-result claim lacks PASS review']
        missing=[]
        if e['registration_required'] and e['registration_evidence_sha256']==NONE: missing.append('required registration evidence absent')
        if e['submission_required']: missing.append('qualifying submission receipt absent')
        if missing: return 'OWNER_SUBMISSION_REQUIRED',missing
        return 'QUALIFYING_RESULT_READY',['reviewed qualifying result requires no separate submission']
    return 'RESEARCH_IN_PROGRESS',['no independently reviewed qualifying result retained']

def compile_readiness(raw, trusted_now=None):
    now=(trusted_now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    d=normalize(raw); state,reasons=derive(d,now)
    packet={'schema':PACKET_SCHEMA,'opportunity_id':d['opportunity_id'],'synthetic_fixture':d['synthetic_fixture'],'evaluated_at':iso(now),'state':state,'reasons':reasons,'source':d['source'],'work':d['work'],'entry':d['entry'],'award':d['award'],'payment':d['payment'],'ownership':d['ownership'],'authority':{'can_claim_submitted':d['entry']['submission_evidence_sha256']!=NONE,'can_claim_awarded':d['award']['award_evidence_sha256']!=NONE,'can_claim_paid':d['payment']['payment_evidence_sha256']!=NONE,'outbound_contact_authorized':False,'registration_mutation_authorized':False,'submission_mutation_authorized':False,'payout_request_authorized':False},'input_sha256':digest(canonical(d))}
    packet['receipt_sha256']=digest(canonical(packet)); return packet

def verify_readiness(raw, packet, trusted_now=None):
    if type(packet) is not dict or not SHA_RE.fullmatch(str(packet.get('receipt_sha256',''))): return False
    unsigned=dict(packet); receipt=unsigned.pop('receipt_sha256')
    if digest(canonical(unsigned))!=receipt: return False
    try: expected=compile_readiness(raw,trusted_now=trusted_now)
    except ReadinessError: return False
    return canonical(expected)==canonical(packet)

def main(argv=None):
    ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest='cmd',required=True)
    c=sp.add_parser('compile'); c.add_argument('input'); c.add_argument('output')
    v=sp.add_parser('verify'); v.add_argument('input'); v.add_argument('packet')
    try:
        a=ap.parse_args(argv); raw=strict_load(a.input)
        if a.cmd=='compile':
            out=Path(a.output); payload=canonical(compile_readiness(raw)); out.parent.mkdir(parents=True,exist_ok=True)
            try:
                with out.open('xb') as f: f.write(payload); f.flush()
            except FileExistsError as ex: raise ReadinessError(f'refusing to overwrite existing output: {out}') from ex
            return 0
        ok=verify_readiness(raw,strict_load(a.packet)); print(json.dumps({'valid':ok},separators=(',',':'))); return 0 if ok else 2
    except (ReadinessError,OSError,json.JSONDecodeError) as ex:
        print(f'ERROR: {ex}',file=sys.stderr); return 2

if __name__=='__main__': raise SystemExit(main())
