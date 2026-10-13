#!/usr/bin/env python3
"""Denver Water 10575 qualification with verifier-owned buyer authority."""
from __future__ import annotations
import argparse, hashlib, json, os, re, stat
from datetime import datetime, timezone
from pathlib import Path

PAYLOAD_SCHEMA="denver-water-10575-qualification/v2"
AUTHORITY_SCHEMA="denver-water-10575-trusted-authority/v1"
RECEIPT_SCHEMA="denver-water-10575-qualification-receipt/v2"
VERIFY_SCHEMA="denver-water-10575-current-verification/v1"
TRUSTED_AUTHORITY_SHA256="d6e6a7a27e2a4760a4a15e38666d8146ca1e152049cbf8fa8658f51076e5ccfe"
CONTROLLING={"OFFICIAL_PACKET","OFFICIAL_ADDENDUM"}; SOURCE_CLASSES=CONTROLLING|{"OFFICIAL_NOTICE","SECONDARY"}
SOURCE_STATES={"OBSERVED","ACQUIRED","SUPERSEDED"}; ROUTES={"PRIME","TEAMING","BOTH"}
EVIDENCE_STATES={"PROVEN","MISSING","UNKNOWN","FAILED"}; CURES={"NONE","PARTNER_CURABLE","OWNER_CURABLE"}
READY={"PRIME_READY","TEAMING_READY"}; ID=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"); H64=re.compile(r"^[0-9a-f]{64}$")
MAX=1_000_000
class QualificationError(ValueError): pass

def exact(o, keys, w):
    if type(o) is not dict or set(o)!=set(keys): raise QualificationError(f"{w}: key mismatch")
def text(v,w,n=512):
    if type(v) is not str or not v or len(v)>n or "\0" in v: raise QualificationError(f"{w}: invalid string")
    return v
def ident(v,w):
    v=text(v,w,128)
    if not ID.fullmatch(v): raise QualificationError(f"{w}: invalid id")
    return v
def digest(v,w):
    v=text(v,w,64)
    if not H64.fullmatch(v): raise QualificationError(f"{w}: invalid sha256")
    return v
def url(v,w):
    v=text(v,w,1024)
    if not v.startswith("https://") or any(c.isspace() for c in v): raise QualificationError(f"{w}: invalid https url")
    return v
def moment(v,w):
    v=text(v,w,32)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",v): raise QualificationError(f"{w}: invalid UTC")
    try: d=datetime.strptime(v,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as e: raise QualificationError(f"{w}: invalid UTC") from e
    if d.strftime("%Y-%m-%dT%H:%M:%SZ")!=v: raise QualificationError(f"{w}: noncanonical UTC")
    return d
def nowstr(): return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
def canon(x): return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def h(x): return hashlib.sha256(canon(x)).hexdigest()
def pairs(ps):
    o={}
    for k,v in ps:
        if k in o: raise QualificationError(f"duplicate JSON key: {k}")
        o[k]=v
    return o
def load_bytes(b):
    if type(b) is not bytes or len(b)>MAX: raise QualificationError("invalid input bytes")
    try: return json.loads(b.decode(),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(QualificationError(f"nonfinite:{x}")))
    except QualificationError: raise
    except Exception as e: raise QualificationError(f"invalid JSON: {e}") from e

def reqdesc(r, official=None, w="requirement"):
    keys={"id","title","route","mandatory","cure","requirement_source_id","source_locator","evidence_subject","evidence_kind","allow_shared_source"}
    exact(r,keys,w); route=text(r["route"],w+".route",16); cure=text(r["cure"],w+".cure",32)
    if route not in ROUTES or cure not in CURES or type(r["mandatory"]) is not bool or type(r["allow_shared_source"]) is not bool: raise QualificationError(w+": invalid route/cure/bool")
    src=ident(r["requirement_source_id"],w+".source")
    if official is not None and src not in official: raise QualificationError(w+": untrusted requirement source")
    return {"id":ident(r["id"],w+".id"),"title":text(r["title"],w+".title",220),"route":route,"mandatory":r["mandatory"],"cure":cure,"requirement_source_id":src,"source_locator":text(r["source_locator"],w+".locator",300),"evidence_subject":ident(r["evidence_subject"],w+".subject"),"evidence_kind":ident(r["evidence_kind"],w+".kind"),"allow_shared_source":r["allow_shared_source"]}

def authority(a, now):
    keys={"schema","opportunity_id","solicitation_id","buyer","state","checked_at","fresh_until","proposal_deadline","deadline_source_id","official_files","requirements","requirements_sha256"}
    exact(a,keys,"authority")
    if a["schema"]!=AUTHORITY_SCHEMA or h(a)!=TRUSTED_AUTHORITY_SHA256: raise QualificationError("trusted authority root mismatch")
    state=text(a["state"],"authority.state",24)
    if state not in {"NOT_ACQUIRED","ACQUIRED"}: raise QualificationError("authority state")
    checked=moment(a["checked_at"],"authority.checked_at")
    if checked>now: raise QualificationError("future authority check")
    if type(a["official_files"]) is not list or type(a["requirements"]) is not list: raise QualificationError("authority arrays")
    fs=[]; seen=set()
    for i,x in enumerate(a["official_files"]):
        exact(x,{"id","class","url","sha256"},f"authority.file[{i}]"); fid=ident(x["id"],"file.id"); cls=text(x["class"],"file.class",32)
        if fid in seen or cls not in CONTROLLING: raise QualificationError("bad trusted file")
        seen.add(fid); fs.append({"id":fid,"class":cls,"url":url(x["url"],"file.url"),"sha256":digest(x["sha256"],"file.sha")})
    fs=sorted(fs,key=lambda x:x["id"]); rs=sorted((reqdesc(x,seen,f"authority.requirement[{i}]") for i,x in enumerate(a["requirements"])),key=lambda x:x["id"])
    if len({x["id"] for x in rs})!=len(rs) or digest(a["requirements_sha256"],"requirements_sha256")!=h(rs): raise QualificationError("trusted requirement manifest digest mismatch")
    out={**a,"official_files":fs,"requirements":rs}
    if state=="NOT_ACQUIRED":
        if fs or rs or any(a[k] is not None for k in ("fresh_until","proposal_deadline","deadline_source_id")): raise QualificationError("NOT_ACQUIRED authority must not carry readiness material")
        return out
    if not fs or not rs: raise QualificationError("ACQUIRED missing files/requirements")
    fresh=moment(a["fresh_until"],"fresh_until"); deadline=moment(a["proposal_deadline"],"proposal_deadline"); dsrc=ident(a["deadline_source_id"],"deadline_source")
    if dsrc not in seen: raise QualificationError("trusted deadline source is not in official file set")
    if fresh<checked: raise QualificationError("bad freshness authority")
    return out

def source(x,now,w):
    exact(x,{"id","class","state","url","captured_at","sha256","label"},w); cls=text(x["class"],w+".class",32); st=text(x["state"],w+".state",32)
    if cls not in SOURCE_CLASSES or st not in SOURCE_STATES: raise QualificationError(w+": source class/state")
    if moment(x["captured_at"],w+".captured")>now: raise QualificationError(w+": future source")
    d=x["sha256"]; d=digest(d,w+".sha") if d is not None else None
    if cls in CONTROLLING and st=="ACQUIRED" and d is None: raise QualificationError(w+": missing digest")
    return {"id":ident(x["id"],w+".id"),"class":cls,"state":st,"url":url(x["url"],w+".url"),"captured_at":x["captured_at"],"sha256":d,"label":text(x["label"],w+".label",180)}
def evidence(e,now,w):
    exact(e,{"id","claim_id","subject","kind","state","observed_at","sha256","ref"},w); st=text(e["state"],w+".state",16)
    if st not in EVIDENCE_STATES or moment(e["observed_at"],w+".observed")>now: raise QualificationError(w+": bad/future evidence")
    d,ref=e["sha256"],e["ref"]
    if st=="PROVEN": d=digest(d,w+".sha"); ref=text(ref,w+".ref",300)
    elif d is not None or ref is not None: raise QualificationError(w+": proof fields on non-PROVEN")
    return {"id":ident(e["id"],w+".id"),"claim_id":ident(e["claim_id"],w+".claim"),"subject":ident(e["subject"],w+".subject"),"kind":ident(e["kind"],w+".kind"),"state":st,"observed_at":e["observed_at"],"sha256":d,"ref":ref}
def payload(p,now):
    exact(p,{"schema","opportunity","sources","gates"},"root")
    if p["schema"]!=PAYLOAD_SCHEMA: raise QualificationError("payload schema")
    o=p["opportunity"]; exact(o,{"id","solicitation_id","title"},"opportunity"); opp={"id":ident(o["id"],"opp.id"),"solicitation_id":ident(o["solicitation_id"],"opp.solicitation"),"title":text(o["title"],"opp.title",240)}
    if type(p["sources"]) is not list or type(p["gates"]) is not list or not p["sources"] or not p["gates"] or len(p["sources"])>128 or len(p["gates"])>256: raise QualificationError("source/gate cardinality")
    ss=[source(x,now,f"source[{i}]") for i,x in enumerate(p["sources"])]; sm={x["id"]:x for x in ss}
    if len(sm)!=len(ss): raise QualificationError("duplicate source id")
    gs=[]; gids=set(); eids=set()
    for i,x in enumerate(p["gates"]):
        exact(x,{"id","title","route","mandatory","cure","requirement_source_id","source_locator","evidence_subject","evidence_kind","allow_shared_source","evidence"},f"gate[{i}]")
        d=reqdesc({k:v for k,v in x.items() if k!="evidence"},set(sm),f"gate[{i}]"); d["evidence"]=evidence(x["evidence"],now,f"gate[{i}].evidence")
        if d["id"] in gids or d["evidence"]["id"] in eids: raise QualificationError("duplicate gate/evidence id")
        gids.add(d["id"]); eids.add(d["evidence"]["id"]); gs.append(d)
    return {"schema":PAYLOAD_SCHEMA,"opportunity":opp,"sources":sorted(ss,key=lambda x:x["id"]),"gates":sorted(gs,key=lambda x:x["id"])}

def evaluate_at(p,a,when):
    now=moment(when,"trusted current time"); A=authority(a,now); P=payload(p,now)
    reasons=[]; routes={}
    if P["opportunity"]["id"]!=A["opportunity_id"] or P["opportunity"]["solicitation_id"]!=A["solicitation_id"]: disp,reasons="HOLD",["OPPORTUNITY_AUTHORITY_MISMATCH"]
    elif A["state"]!="ACQUIRED": disp,reasons="HOLD",["CONTROLLING_PACKET_NOT_ACQUIRED"]
    elif now>=moment(A["proposal_deadline"],"deadline"): disp,reasons="NO_BID",["TRUSTED_PROPOSAL_DEADLINE_EXPIRED"]
    elif now>moment(A["fresh_until"],"fresh_until"): disp,reasons="HOLD",["TRUSTED_AUTHORITY_STALE"]
    else:
        want={x["id"]:x for x in A["official_files"]}; got={x["id"]:{k:x[k] for k in ("id","class","url","sha256")} for x in P["sources"] if x["class"] in CONTROLLING and x["state"]=="ACQUIRED"}
        desc=sorted((reqdesc({k:v for k,v in g.items() if k!="evidence"}) for g in P["gates"]),key=lambda x:x["id"])
        if got!=want: disp,reasons="HOLD",["CONTROLLING_FILE_SET_MISMATCH"]
        elif desc!=A["requirements"] or h(desc)!=A["requirements_sha256"]: disp,reasons="HOLD",["REQUIREMENT_MANIFEST_MISMATCH"]
        else:
            rm={x["id"]:x for x in A["requirements"]}; uses={}; bind=None
            for g in P["gates"]:
                r=rm[g["id"]]; e=g["evidence"]
                if (e["claim_id"],e["subject"],e["kind"])!=(g["id"],r["evidence_subject"],r["evidence_kind"]): bind=f"EVIDENCE_CLAIM_BINDING_MISMATCH:{g['id']}"; break
                if e["state"]=="PROVEN": uses.setdefault((e["sha256"],e["ref"]),[]).append(r)
            if bind: disp,reasons="HOLD",[bind]
            elif any(len(v)>1 and not all(x["allow_shared_source"] for x in v) for v in uses.values()): disp,reasons="HOLD",["EVIDENCE_SOURCE_REUSE_NOT_AUTHORIZED"]
            else:
                for route in ("PRIME","TEAMING"):
                    passed=[]; holds=[]; failed=[]; gaps=[]
                    for g in P["gates"]:
                        if not g["mandatory"] or g["route"] not in {route,"BOTH"}: continue
                        st=g["evidence"]["state"]
                        if st=="PROVEN": passed.append(g["id"])
                        elif st=="FAILED" and route=="PRIME" and g["cure"]=="PARTNER_CURABLE": gaps.append(g["id"])
                        elif st=="FAILED": failed.append(g["id"])
                        else: holds.append(f"{g['id']}:{st}")
                    status="FAIL" if failed else "PARTNER_GAP" if gaps and route=="PRIME" else "HOLD" if holds else "PASS"
                    routes[route]={"status":status,"passed_gate_ids":sorted(passed),"hold_reasons":sorted(holds),"failed_gate_ids":sorted(failed),"partner_curable_failed_gate_ids":sorted(gaps)}
                pr,tm=routes["PRIME"],routes["TEAMING"]
                if pr["status"]=="PASS": disp,reasons="PRIME_READY",["ALL_TRUSTED_PRIME_GATES_PROVEN"]
                elif tm["status"]=="PASS": disp,reasons="TEAMING_READY",["ALL_TRUSTED_TEAMING_GATES_PROVEN"]+(["PRIME_HAS_PARTNER_CURABLE_GAPS"] if pr["status"]=="PARTNER_GAP" else [])
                elif pr["status"]==tm["status"]=="FAIL": disp,reasons="NO_BID",["BOTH_ROUTES_HAVE_NONCURABLE_MANDATORY_FAILURES"]
                else: disp,reasons="HOLD",["MANDATORY_EVIDENCE_INCOMPLETE"]
    return {"disposition":disp,"reasons":sorted(set(reasons)),"route_detail":routes,"evaluated_at":when,"payload_sha256":h(P),"authority_sha256":h(A),"requirements_sha256":A["requirements_sha256"]}
def compile_at(p,a,when):
    core={"schema":RECEIPT_SCHEMA,**evaluate_at(p,a,when),"authority":{"buyer_contact":False,"portal_action":False,"proposal_submission":False,"pricing_commitment":False,"certification_or_reference_claim":False,"contract_acceptance":False,"spend":False,"award_or_revenue_claim":False}}
    return {**core,"receipt_sha256":h(core)}
_digest=h
load_json_bytes=load_bytes
_now_string=nowstr
_evaluate_at=evaluate_at
_compile_at=compile_at
def compile_current(p,a): return compile_at(p,a,_now_string())
def verify_current(p,a,r):
    if type(r) is not dict or r.get("schema")!=RECEIPT_SCHEMA or r!=compile_at(p,a,r.get("evaluated_at")): raise QualificationError("receipt mismatch/tamper")
    c=evaluate_at(p,a,_now_string()); same=all(c[k]==r[k] for k in ("disposition","reasons","payload_sha256","authority_sha256","requirements_sha256"))
    return {"schema":VERIFY_SCHEMA,"historical_integrity":"PASS","receipt_disposition":r["disposition"],"current_evaluated_at":c["evaluated_at"],"current_disposition":c["disposition"],"current_reasons":c["reasons"],"current_receipt_valid":same,"current_commercial_authority":same and c["disposition"] in READY}
def read(path):
    st=Path(path).stat(follow_symlinks=False)
    if not stat.S_ISREG(st.st_mode) or st.st_size>MAX: raise QualificationError("invalid input file")
    return load_bytes(Path(path).read_bytes())
def write(path,b):
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|(getattr(os,"O_NOFOLLOW",0)); fd=os.open(path,flags,0o600)
    try: os.write(fd,b)
    finally: os.close(fd)
def main(argv=None):
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True)
    for name in ("compile","verify"):
        q=sub.add_parser(name); q.add_argument("--input",required=True); q.add_argument("--authority",required=True); q.add_argument("--output" if name=="compile" else "--receipt",required=True)
    x=p.parse_args(argv); P,A=read(x.input),read(x.authority)
    if x.cmd=="compile": write(x.output,json.dumps(compile_current(P,A),indent=2,sort_keys=True).encode()+b"\n"); return 0
    v=verify_current(P,A,read(x.receipt)); print(json.dumps(v,sort_keys=True)); return 0 if v["current_receipt_valid"] else 3
if __name__=="__main__": raise SystemExit(main())
