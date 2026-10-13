#!/usr/bin/env python3
"""Deterministic post-delivery buyer-acceptance evidence compiler."""
from __future__ import annotations
import argparse, csv, hashlib, io, json, re
from pathlib import Path
from typing import Any, Mapping

SCHEMA=1
ID=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SHA=re.compile(r"^[0-9a-f]{64}$")
UTC=re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
AUTH={"internal_record","delivery_transport","counterparty_evidence","owner_approved"}
DISP={"ACCEPTED","REVISION_REQUESTED","REJECTED"}
TERMINAL={"BUYER_ACCEPTED_EVIDENCE","PARTIALLY_ACCEPTED_EVIDENCE","DELIVERED_PENDING_BUYER_ACCEPTANCE","REVISION_REQUIRED","REJECTED","HOLD"}

def cb(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def dig(v): return hashlib.sha256(cb(v)).hexdigest()
def obj(v,w):
    if type(v) is not dict: raise ValueError(f"{w} must be object")
    return v
def arr(v,w):
    if type(v) is not list: raise ValueError(f"{w} must be list")
    return v
def txt(v,w,pat=None):
    if type(v) is not str or not v or v!=v.strip(): raise ValueError(f"{w} must be nonempty trimmed text")
    if pat and not pat.fullmatch(v): raise ValueError(f"{w} invalid format")
    return v
def ident(v,w): return txt(v,w,ID)
def sha(v,w): return txt(v,w,SHA)
def utc(v,w): return txt(v,w,UTC)
def boolean(v,w):
    if type(v) is not bool: raise ValueError(f"{w} must be boolean")
    return v
def enum(v, allowed, w):
    x=txt(v,w)
    if x not in allowed: raise ValueError(f"{w} unsupported")
    return x
def keys(o, req, opt, w):
    miss=req-set(o); extra=set(o)-req-opt
    if miss or extra: raise ValueError(f"{w} fields mismatch missing={sorted(miss)} extra={sorted(extra)}")
def uniq(rows,w):
    seen=set()
    for r in rows:
        x=ident(r.get("id"),f"{w}.id")
        if x in seen: raise ValueError(f"duplicate {w} id {x}")
        seen.add(x)

def _version_core(v):
    return {k:v[k] for k in ("id","milestone_id","ordinal","artifact_ref","artifact_sha256","criteria_ids","scope_agreement_sha256","delivery_receipt_sha256","created_at")}

def validate(packet):
    r=obj(packet,"packet"); keys(r,{"schema_version","portfolio","milestones","versions","evidence","events"},set(),"packet")
    if type(r["schema_version"]) is not int or r["schema_version"]!=SCHEMA: raise ValueError("schema_version must be integer 1")
    p=obj(r["portfolio"],"portfolio"); keys(p,{"name"},set(),"portfolio"); txt(p["name"],"portfolio.name")
    ms=[obj(x,"milestones[]") for x in arr(r["milestones"],"milestones")]
    vs=[obj(x,"versions[]") for x in arr(r["versions"],"versions")]
    ev=[obj(x,"evidence[]") for x in arr(r["evidence"],"evidence")]
    es=[obj(x,"events[]") for x in arr(r["events"],"events")]
    if not ms: raise ValueError("milestones required")
    for rows,w in ((ms,"milestone"),(vs,"version"),(ev,"evidence"),(es,"event")): uniq(rows,w)
    mids=set(); criteria={}
    for m in ms:
        keys(m,{"id","scope_ref","criteria"},set(),f"milestone {m.get('id','?')}")
        mid=ident(m["id"],"milestone.id"); mids.add(mid); ident(m["scope_ref"],f"milestone {mid}.scope_ref")
        cs=[obj(x,"criteria[]") for x in arr(m["criteria"],f"milestone {mid}.criteria")]
        if not cs: raise ValueError(f"milestone {mid} criteria required")
        uniq(cs,"criterion"); cmap={}
        for c in cs:
            keys(c,{"id","required","description_digest"},set(),f"criterion {c.get('id','?')}")
            cid=ident(c["id"],"criterion.id"); boolean(c["required"],f"criterion {cid}.required"); sha(c["description_digest"],f"criterion {cid}.description_digest"); cmap[cid]=c
        criteria[mid]=cmap
    vids={}; bymid={}
    for v in vs:
        keys(v,{"id","milestone_id","ordinal","artifact_ref","artifact_sha256","criteria_ids","scope_agreement_sha256","delivery_receipt_sha256","created_at"},set(),f"version {v.get('id','?')}")
        vid=ident(v["id"],"version.id"); mid=ident(v["milestone_id"],f"version {vid}.milestone_id")
        if mid not in mids: raise ValueError(f"version {vid} unknown milestone")
        if type(v["ordinal"]) is not int or type(v["ordinal"]) is bool or v["ordinal"]<1: raise ValueError(f"version {vid}.ordinal invalid")
        txt(v["artifact_ref"],f"version {vid}.artifact_ref"); sha(v["artifact_sha256"],f"version {vid}.artifact_sha256")
        sha(v["scope_agreement_sha256"],f"version {vid}.scope_agreement_sha256"); sha(v["delivery_receipt_sha256"],f"version {vid}.delivery_receipt_sha256"); utc(v["created_at"],f"version {vid}.created_at")
        ids=[ident(x,f"version {vid}.criteria_id") for x in arr(v["criteria_ids"],f"version {vid}.criteria_ids")]
        if len(ids)!=len(set(ids)) or set(ids)!=set(criteria[mid]): raise ValueError(f"version {vid} criteria_ids must exactly bind milestone criteria")
        if v["ordinal"] in bymid.setdefault(mid,{}): raise ValueError(f"milestone {mid} duplicate ordinal")
        bymid[mid][v["ordinal"]]=vid; vids[vid]=v
    proof={}
    for e in ev:
        keys(e,{"id","status","authority","captured_at","reference","sha256"},set(),f"evidence {e.get('id','?')}")
        eid=ident(e["id"],"evidence.id"); enum(e["status"],{"verified","pending","rejected"},f"evidence {eid}.status"); enum(e["authority"],AUTH,f"evidence {eid}.authority")
        utc(e["captured_at"],f"evidence {eid}.captured_at"); txt(e["reference"],f"evidence {eid}.reference"); sha(e["sha256"],f"evidence {eid}.sha256"); proof[eid]=e
    for e in es:
        keys(e,{"id","kind","milestone_id","version_id","version_sha256","occurred_at","evidence_id"},{"criterion_ids","disposition"},"event")
        x=ident(e["id"],"event.id"); kind=enum(e["kind"],{"DELIVERED","BUYER_DISPOSITION","SUPERSEDED"},f"event {x}.kind"); mid=ident(e["milestone_id"],f"event {x}.milestone_id"); vid=ident(e["version_id"],f"event {x}.version_id")
        if vid not in vids or vids[vid]["milestone_id"]!=mid: raise ValueError(f"event {x} version/milestone mismatch")
        if sha(e["version_sha256"],f"event {x}.version_sha256")!=dig(_version_core(vids[vid])): raise ValueError(f"event {x} version digest mismatch")
        utc(e["occurred_at"],f"event {x}.occurred_at"); eid=ident(e["evidence_id"],f"event {x}.evidence_id")
        if eid not in proof: raise ValueError(f"event {x} unknown evidence")
        if kind=="BUYER_DISPOSITION":
            disp=enum(e.get("disposition"),DISP,f"event {x}.disposition")
            cids=[ident(c,f"event {x}.criterion_id") for c in arr(e.get("criterion_ids"),f"event {x}.criterion_ids")]
            if not cids or len(cids)!=len(set(cids)) or not set(cids)<=set(criteria[mid]): raise ValueError(f"event {x} criterion_ids invalid")
            if disp in {"REVISION_REQUESTED","REJECTED"} and set(cids)!=set(criteria[mid]): raise ValueError(f"event {x} revision/rejection must bind all criteria")
        else:
            if "criterion_ids" in e or "disposition" in e: raise ValueError(f"event {x} unexpected disposition fields")
    return r,criteria,vids,proof

def evaluate(packet):
    r,criteria,vids,proof=validate(packet)
    events=sorted(r["events"],key=lambda x:(x["occurred_at"],x["id"]))
    out=[]
    for m in sorted(r["milestones"],key=lambda x:x["id"]):
        mid=m["id"]; versions=sorted((v for v in r["versions"] if v["milestone_id"]==mid),key=lambda x:x["ordinal"])
        blockers=[]; rows=[]; latest=None
        if versions: latest=versions[-1]
        if not latest:
            out.append({"milestone_id":mid,"state":"HOLD","current_version_id":None,"accepted_required":[],"pending_required":[],"blockers":["NO_VERSION"],"event_results":[]}); continue
        vid=latest["id"]; required={c["id"] for c in m["criteria"] if c["required"]}; accepted=set(); delivered=False; revision=False; rejected=False; superseded=False
        for e in (x for x in events if x["milestone_id"]==mid):
            pr=proof[e["evidence_id"]]; status="VERIFIED"; reason=None
            if pr["status"]!="verified": status,reason="EVIDENCE_NOT_VERIFIED",pr["status"]
            elif pr["captured_at"]<e["occurred_at"]: status,reason="CHRONOLOGY_HOLD","captured before event"
            elif e["occurred_at"]<vids[e["version_id"]]["created_at"]: status,reason="CHRONOLOGY_HOLD","event predates version"
            elif e["kind"]=="DELIVERED" and pr["authority"] not in {"delivery_transport","counterparty_evidence"}: status,reason="AUTHORITY_MISMATCH","delivery requires transport/counterparty"
            elif e["kind"]=="BUYER_DISPOSITION" and pr["authority"]!="counterparty_evidence": status,reason="AUTHORITY_MISMATCH","buyer disposition requires counterparty"
            elif e["kind"]=="SUPERSEDED" and pr["authority"]!="owner_approved": status,reason="AUTHORITY_MISMATCH","supersession requires owner"
            if status!="VERIFIED": blockers.append(f"{e['id']}:{status}")
            elif e["version_id"]==vid:
                if e["kind"]=="DELIVERED": delivered=True
                elif e["kind"]=="SUPERSEDED": superseded=True
                elif e["kind"]=="BUYER_DISPOSITION":
                    if e["disposition"]=="ACCEPTED":
                        if not delivered: blockers.append(f"{e['id']}:ACCEPTANCE_BEFORE_DELIVERY")
                        accepted.update(e["criterion_ids"])
                    elif e["disposition"]=="REVISION_REQUESTED": revision=True
                    elif e["disposition"]=="REJECTED": rejected=True
            rows.append({"event_id":e["id"],"version_id":e["version_id"],"kind":e["kind"],"status":status,"reason":reason})
        pending=required-accepted
        if blockers or superseded: state="HOLD"
        elif rejected: state="REJECTED"
        elif revision: state="REVISION_REQUIRED"
        elif required and not pending and delivered: state="BUYER_ACCEPTED_EVIDENCE"
        elif accepted: state="PARTIALLY_ACCEPTED_EVIDENCE"
        elif delivered: state="DELIVERED_PENDING_BUYER_ACCEPTANCE"
        else: state="HOLD"; blockers.append("CURRENT_VERSION_NOT_DELIVERED")
        out.append({"milestone_id":mid,"state":state,"current_version_id":vid,"current_version_sha256":dig(_version_core(latest)),"accepted_required":sorted(required&accepted),"pending_required":sorted(pending),"blockers":sorted(set(blockers)),"event_results":rows})
    normalized={"schema_version":SCHEMA,"portfolio":{"name":r["portfolio"]["name"]},"milestones":sorted(r["milestones"],key=lambda x:x["id"]),"versions":sorted(r["versions"],key=lambda x:x["id"]),"evidence":sorted(r["evidence"],key=lambda x:x["id"]),"events":sorted(r["events"],key=lambda x:x["id"])}
    core={"schema_version":SCHEMA,"portfolio":{"name":r["portfolio"]["name"]},"input_sha256":dig(normalized),"summary":{"milestone_count":len(out),"state_counts":{s:sum(x["state"]==s for x in out) for s in sorted(TERMINAL)},"buyer_acceptance_is_evidence_state_only":True,"fulfillment_authorized":False,"payment_authorized":False,"revenue_recognized":False},"milestones":out,"authority_boundary":{"technical_pass_is_not_buyer_acceptance":True,"delivery_is_not_buyer_acceptance":True,"pre_delivery_scope_acceptance_is_not_post_delivery_acceptance":True,"testimonial_or_endorsement_inferred":False,"no_external_action":True}}
    result=dict(core); result["ledger_sha256"]=dig(core); return result

def verify(packet,candidate):
    ok=type(candidate) is dict and candidate==evaluate(packet); return ok,"verified" if ok else "candidate does not match deterministic recomputation"
def markdown(x):
    lines=["# Post-delivery buyer-acceptance evidence","","Evidence state only. Delivery and technical PASS do not equal buyer acceptance.","","| Milestone | Version | State | Accepted required | Pending required | Blockers |","|---|---|---|---|---|---|"]
    for r in x["milestones"]: lines.append(f"| {r['milestone_id']} | {r['current_version_id']} | **{r['state']}** | {', '.join(r['accepted_required']) or '—'} | {', '.join(r['pending_required']) or '—'} | {', '.join(r['blockers']) or '—'} |")
    return "\n".join(lines)+"\n"
def csv_text(x):
    b=io.StringIO(newline=""); w=csv.writer(b,lineterminator="\n"); w.writerow(["milestone_id","current_version_id","state","accepted_required","pending_required","blockers"])
    for r in x["milestones"]: w.writerow([r["milestone_id"],r["current_version_id"],r["state"],";".join(r["accepted_required"]),";".join(r["pending_required"]),";".join(r["blockers"])])
    return b.getvalue()
def load(path):
    def pairs(rows):
        o={}
        for k,v in rows:
            if k in o: raise ValueError(f"duplicate JSON key: {k}")
            o[k]=v
        return o
    with Path(path).open(encoding="utf-8") as f: return json.load(f,object_pairs_hook=pairs)
def write_new(path,text):
    p=Path(path)
    if p.is_symlink(): raise FileExistsError("refusing symlink output")
    with p.open("x",encoding="utf-8",newline="") as f:f.write(text)
def main(argv=None):
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest="cmd",required=True)
    c=s.add_parser("compile"); c.add_argument("--input",required=True); c.add_argument("--json-out",required=True); c.add_argument("--markdown-out"); c.add_argument("--csv-out"); c.add_argument("--fail-on-hold",action="store_true")
    v=s.add_parser("verify"); v.add_argument("--input",required=True); v.add_argument("--ledger",required=True); a=p.parse_args(argv)
    if a.cmd=="compile":
        x=evaluate(load(a.input)); write_new(a.json_out,json.dumps(x,indent=2,sort_keys=True)+"\n")
        if a.markdown_out: write_new(a.markdown_out,markdown(x))
        if a.csv_out: write_new(a.csv_out,csv_text(x))
        return 2 if a.fail_on_hold and x["summary"]["state_counts"]["HOLD"] else 0
    ok,msg=verify(load(a.input),load(a.ledger)); print(msg); return 0 if ok else 3
if __name__=="__main__": raise SystemExit(main())
