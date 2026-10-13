"""Fail-closed procurement response module compiler.

Compiles owner-review response packets from versioned modules + cited evidence.
It never authorizes submission, contact, signature, certification, pricing,
payment, award, or revenue recognition.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LIB="procurement-response-modules/library/v1"; SOL="procurement-response-modules/solicitation/v1"
PACK="procurement-response-modules/packet/v1"; REC="procurement-response-modules/receipt/v1"
BOUNDARY="INTERNAL_OWNER_REVIEW_ONLY"; ESTAT={"SUPPORTED","PARTIAL","MISSING","NOT_APPLICABLE"}; OSTAT={"APPROVED","PENDING","DENIED"}
TOK=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$"); SHA=re.compile(r"^[0-9a-f]{64}$"); TS=re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

class Error(ValueError): pass
@dataclass(frozen=True)
class Output: packet:bytes; markdown:bytes; receipt:bytes; status:str

def _pairs(pairs):
    out={}
    for k,v in pairs:
        if k in out: raise Error(f"duplicate JSON key: {k}")
        out[k]=v
    return out

def _bad(v): raise Error(f"non-integer JSON number forbidden: {v}")
def load(raw:bytes,label="input"):
    if not isinstance(raw,(bytes,bytearray)): raise Error(f"{label}: bytes required")
    raw=bytes(raw)
    if raw.startswith(b"\xef\xbb\xbf"): raise Error(f"{label}: BOM forbidden")
    try: v=json.loads(raw.decode("utf-8"),object_pairs_hook=_pairs,parse_float=_bad,parse_constant=_bad)
    except Error: raise
    except Exception as e: raise Error(f"{label}: invalid JSON/UTF-8") from e
    if not isinstance(v,dict): raise Error(f"{label}: object required")
    return v

def canon(v): return (json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()
def digest(b): return hashlib.sha256(b).hexdigest()
def keys(v,want,where):
    if not isinstance(v,dict) or set(v)!=set(want): raise Error(f"{where}: keys mismatch")
    return v
def s(v,w,token=False,limit=4096):
    if not isinstance(v,str) or not v or len(v)>limit or any(ord(c)<32 and c not in "\n\t" for c in v): raise Error(f"{w}: invalid string")
    if token and not TOK.fullmatch(v): raise Error(f"{w}: invalid token")
    return v
def i(v,w,lo=0,hi=10**9):
    if isinstance(v,bool) or not isinstance(v,int) or not lo<=v<=hi: raise Error(f"{w}: integer required")
    return v
def b(v,w):
    if not isinstance(v,bool): raise Error(f"{w}: boolean required")
    return v
def sh(v,w):
    v=s(v,w,limit=64)
    if not SHA.fullmatch(v): raise Error(f"{w}: sha256 required")
    return v
def dt(v,w):
    v=s(v,w,limit=20)
    try:
        if not TS.fullmatch(v): raise ValueError
        datetime.strptime(v,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as e: raise Error(f"{w}: RFC3339 UTC second timestamp required") from e
    return v
def dtime(v): return datetime.strptime(v,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
def toks(v,w,minn=0,maxn=64):
    if not isinstance(v,list) or not minn<=len(v)<=maxn: raise Error(f"{w}: invalid list")
    out=[s(x,f"{w}[{n}]",True,128) for n,x in enumerate(v)]
    if len(out)!=len(set(out)): raise Error(f"{w}: duplicate item")
    return sorted(out)
def fresh(obs,now,maxage,w):
    age=int((dtime(now)-dtime(obs)).total_seconds())
    if age<0: raise Error(f"{w}: future evidence")
    if age>maxage: raise Error(f"{w}: stale evidence")

def norm_library(v):
    keys(v,["schema","library_id","generated_at","evidence_max_age_seconds","truth_boundary","evidence","modules"],"library")
    if v["schema"]!=LIB or v["truth_boundary"]!=BOUNDARY: raise Error("library: unsupported schema/boundary")
    now=dt(v["generated_at"],"library.generated_at"); maxage=i(v["evidence_max_age_seconds"],"library.evidence_max_age_seconds",1,31536000)
    if not isinstance(v["evidence"],list) or not isinstance(v["modules"],list) or not v["evidence"] or not v["modules"]: raise Error("library: evidence/modules required")
    ev=[]
    for n,x in enumerate(v["evidence"]):
        w=f"evidence[{n}]"; keys(x,["evidence_id","ref","sha256","observed_at","status","summary"],w); status=s(x["status"],w+".status",True,32)
        if status not in ESTAT: raise Error(w+": bad status")
        row={"evidence_id":s(x["evidence_id"],w+".evidence_id",True),"ref":s(x["ref"],w+".ref",limit=2048),"sha256":sh(x["sha256"],w+".sha256"),"observed_at":dt(x["observed_at"],w+".observed_at"),"status":status,"summary":s(x["summary"],w+".summary",limit=1024)}; fresh(row["observed_at"],now,maxage,w); ev.append(row)
    ids=[x["evidence_id"] for x in ev]
    if len(ids)!=len(set(ids)): raise Error("library: duplicate evidence_id")
    evmap={x["evidence_id"]:x for x in ev}; mods=[]
    for n,x in enumerate(v["modules"]):
        w=f"modules[{n}]"; keys(x,["module_id","revision","family","title","tags","owner_status","valid_from","valid_until","source_ref","source_sha256","claims"],w)
        owner=s(x["owner_status"],w+".owner_status",True,32)
        if owner not in OSTAT: raise Error(w+": bad owner_status")
        vf=dt(x["valid_from"],w+".valid_from"); vu=dt(x["valid_until"],w+".valid_until")
        if not dtime(vf)<=dtime(now)<=dtime(vu): raise Error(w+": outside validity window")
        claims=[]
        if not isinstance(x["claims"],list) or not x["claims"]: raise Error(w+": claims required")
        for q,c in enumerate(x["claims"]):
            cw=f"{w}.claims[{q}]"; keys(c,["claim_id","text","evidence_ids"],cw); eids=toks(c["evidence_ids"],cw+".evidence_ids",1)
            unknown=set(eids)-set(evmap)
            if unknown: raise Error(cw+": unknown evidence")
            claims.append({"claim_id":s(c["claim_id"],cw+".claim_id",True),"text":s(c["text"],cw+".text"),"evidence_ids":eids})
        cids=[c["claim_id"] for c in claims]
        if len(cids)!=len(set(cids)): raise Error(w+": duplicate claim_id")
        mods.append({"module_id":s(x["module_id"],w+".module_id",True),"revision":i(x["revision"],w+".revision",1,10**6),"family":s(x["family"],w+".family",True),"title":s(x["title"],w+".title",limit=256),"tags":toks(x["tags"],w+".tags"),"owner_status":owner,"valid_from":vf,"valid_until":vu,"source_ref":s(x["source_ref"],w+".source_ref",limit=2048),"source_sha256":sh(x["source_sha256"],w+".source_sha256"),"claims":sorted(claims,key=lambda c:c["claim_id"])})
    mids=[(m["module_id"],m["revision"]) for m in mods]
    if len(mids)!=len(set(mids)): raise Error("library: duplicate module revision")
    return {"library_id":s(v["library_id"],"library.library_id",True),"generated_at":now,"evidence":sorted(ev,key=lambda x:x["evidence_id"]),"modules":sorted(mods,key=lambda x:(x["family"],x["module_id"],x["revision"]))}

def norm_sol(v):
    keys(v,["schema","solicitation_id","source_ref","source_sha256","observed_at","generated_at","source_max_age_seconds","requirements"],"solicitation")
    if v["schema"]!=SOL: raise Error("solicitation: unsupported schema")
    now=dt(v["generated_at"],"solicitation.generated_at"); obs=dt(v["observed_at"],"solicitation.observed_at"); fresh(obs,now,i(v["source_max_age_seconds"],"solicitation.source_max_age_seconds",1,31536000),"solicitation")
    if not isinstance(v["requirements"],list) or not v["requirements"]: raise Error("solicitation: requirements required")
    req=[]
    for n,x in enumerate(v["requirements"]):
        w=f"requirements[{n}]"; keys(x,["section_id","family","required_tags","required"],w); req.append({"section_id":s(x["section_id"],w+".section_id",True),"family":s(x["family"],w+".family",True),"required_tags":toks(x["required_tags"],w+".required_tags"),"required":b(x["required"],w+".required")})
    ids=[x["section_id"] for x in req]
    if len(ids)!=len(set(ids)): raise Error("solicitation: duplicate section_id")
    return {"solicitation_id":s(v["solicitation_id"],"solicitation.solicitation_id",True),"source_ref":s(v["source_ref"],"solicitation.source_ref",limit=2048),"source_sha256":sh(v["source_sha256"],"solicitation.source_sha256"),"generated_at":now,"requirements":sorted(req,key=lambda x:x["section_id"])}

def authority(): return {k:False for k in ["submission_authorized","buyer_contact_authorized","signature_authorized","certification_authorized","price_commitment_authorized","payment_authorized","award_or_revenue_recognized"]}
def diagnose(m,ev):
    r=[]
    if m["owner_status"]!="APPROVED": r.append("OWNER_"+m["owner_status"])
    for c in m["claims"]:
        for eid in c["evidence_ids"]:
            if ev[eid]["status"]!="SUPPORTED": r.append(f"EVIDENCE_{ev[eid]['status']}:{eid}")
    return sorted(set(r))
def select(req,mods,ev):
    tags=set(req["required_tags"]); cand=[m for m in mods if m["family"]==req["family"] and tags<=set(m["tags"])]
    if not cand: return None,["NO_MATCHING_MODULE"]
    good=[]; bad=[]
    for m in cand:
        rs=diagnose(m,ev)
        if rs: bad += [f"{m['module_id']}@{m['revision']}:{r}" for r in rs]
        else: good.append(m)
    if not good: return None,sorted(set(bad))
    return sorted(good,key=lambda m:(-m["revision"],m["module_id"]))[0],[]
def project(m,ev):
    return {"module_id":m["module_id"],"revision":m["revision"],"family":m["family"],"title":m["title"],"source_ref":m["source_ref"],"source_sha256":m["source_sha256"],"claims":[{"claim_id":c["claim_id"],"text":c["text"],"citations":[{k:ev[e][k] for k in ["evidence_id","ref","sha256","observed_at"]} for e in c["evidence_ids"]]} for c in m["claims"]]}
def md(pkt):
    lines=["# Procurement Response Packet","",f"- Solicitation: `{pkt['solicitation_id']}`",f"- Status: **{pkt['status']}**","- Authority: **internal owner review only; every external/commercial authority flag is false**","","## Compliance crosswalk","","| Section | Family | Status | Module | Reasons |","| --- | --- | --- | --- | --- |"]
    for x in pkt["sections"]:
        mod="—" if x["module"] is None else f"{x['module']['module_id']}@{x['module']['revision']}"; rs=", ".join(x["reasons"]) or "—"; lines.append(f"| `{x['section_id']}` | `{x['family']}` | **{x['status']}** | `{mod}` | {rs} |")
    lines += ["","## Selected modules",""]; seen=set()
    for x in pkt["sections"]:
        m=x["module"]
        if not m or (m["module_id"],m["revision"]) in seen: continue
        seen.add((m["module_id"],m["revision"])); lines += [f"### {m['title']}","",f"Source: `{m['source_ref']}` / `{m['source_sha256']}`",""]
        for c in m["claims"]:
            lines.append("- "+c["text"])
            for z in c["citations"]: lines.append(f"  - Evidence `{z['evidence_id']}`: `{z['ref']}` · `{z['sha256']}` · `{z['observed_at']}`")
        lines.append("")
    return ("\n".join(lines).rstrip()+"\n").encode()

def compile(lraw,sraw):
    L=norm_library(load(lraw,"library")); S=norm_sol(load(sraw,"solicitation"))
    if L["generated_at"]!=S["generated_at"]: raise Error("generated_at mismatch")
    ev={x["evidence_id"]:x for x in L["evidence"]}; sections=[]; hold=False
    for req in S["requirements"]:
        m,reasons=select(req,L["modules"],ev); status="SUPPORTED" if m else "HOLD"; hold |= req["required"] and not m
        sections.append({**req,"status":status,"reasons":reasons,"module":None if not m else project(m,ev)})
    pkt={"schema":PACK,"truth_boundary":BOUNDARY,"library_id":L["library_id"],"solicitation_id":S["solicitation_id"],"generated_at":S["generated_at"],"status":"HOLD" if hold else "OWNER_REVIEW_READY","source":{"library_input_sha256":digest(lraw),"solicitation_input_sha256":digest(sraw),"solicitation_source_ref":S["source_ref"],"solicitation_source_sha256":S["source_sha256"]},"authority":authority(),"sections":sections}
    pb=canon(pkt); mb=md(pkt); rec={"schema":REC,"truth_boundary":BOUNDARY,"status":pkt["status"],"library_input_sha256":digest(lraw),"solicitation_input_sha256":digest(sraw),"packet_sha256":digest(pb),"markdown_sha256":digest(mb),"authority":authority()}; return Output(pb,mb,canon(rec),pkt["status"])
def verify(l,s,p,m,r):
    exp=compile(l,s)
    if canon(load(p,"packet"))!=p: raise Error("packet non-canonical")
    if canon(load(r,"receipt"))!=r: raise Error("receipt non-canonical")
    if p!=exp.packet: raise Error("packet mismatch")
    if m!=exp.markdown: raise Error("markdown mismatch")
    if r!=exp.receipt: raise Error("receipt mismatch")
    return {"verified":True,"status":exp.status,"packet_sha256":digest(exp.packet),"markdown_sha256":digest(exp.markdown)}

def main(argv=None):
    ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest="cmd",required=True)
    c=sp.add_parser("compile"); [c.add_argument(x,required=True) for x in ["--library","--solicitation","--out-dir"]]
    v=sp.add_parser("verify"); [v.add_argument(x,required=True) for x in ["--library","--solicitation","--packet","--markdown","--receipt"]]
    a=ap.parse_args(argv)
    try:
        rb=lambda p:Path(p).read_bytes()
        if a.cmd=="compile":
            o=compile(rb(a.library),rb(a.solicitation)); out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True); (out/"packet.json").write_bytes(o.packet); (out/"packet.md").write_bytes(o.markdown); (out/"receipt.json").write_bytes(o.receipt); print(json.dumps({"status":o.status,"packet_sha256":digest(o.packet)},sort_keys=True))
        else: print(json.dumps(verify(rb(a.library),rb(a.solicitation),rb(a.packet),rb(a.markdown),rb(a.receipt)),sort_keys=True))
        return 0
    except (Error,OSError) as e: print(f"HOLD: {e}",file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())
