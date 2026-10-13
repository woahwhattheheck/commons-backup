#!/usr/bin/env python3
"""Local, dependency-free launch operations for one operator-supplied SKU."""
from __future__ import annotations
import argparse, copy, hashlib, json, os, re, sys
from pathlib import Path
from typing import Any

class LaunchError(ValueError): pass
REQ=("sku","name","description","price_cents","currency","stock","reorder_at","shipping_terms","return_days","support_contact","attributes","benefits","channels")
CHAN=re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")

def canon(v:Any)->bytes:
    try:
        return (json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)+"\n").encode()
    except ValueError as e:
        raise LaunchError(f"non-finite number in JSON payload: {e}") from e
def sha(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def text(v:Any,n:str)->str:
    if not isinstance(v,str) or not v.strip(): raise LaunchError(f"{n} must be a non-empty string")
    return v

def validate(p:Any)->dict[str,Any]:
    if not isinstance(p,dict): raise LaunchError("product must be an object")
    miss=[k for k in REQ if k not in p]
    if miss: raise LaunchError("missing required fields: "+", ".join(miss))
    p=copy.deepcopy(p)
    for k in ("sku","name","description","shipping_terms","support_contact"): text(p[k],k)
    if not isinstance(p["price_cents"],int) or isinstance(p["price_cents"],bool) or p["price_cents"]<0: raise LaunchError("price_cents must be non-negative int")
    if not isinstance(p["currency"],str) or not re.fullmatch(r"[A-Z]{3}",p["currency"]): raise LaunchError("currency must be uppercase 3-letter code")
    for k in ("stock","reorder_at","return_days"):
        if not isinstance(p[k],int) or isinstance(p[k],bool) or p[k]<0: raise LaunchError(f"{k} must be non-negative int")
    if not isinstance(p["attributes"],dict) or not p["attributes"]: raise LaunchError("attributes must be non-empty object")
    for k,v in p["attributes"].items():
        text(k,"attribute key")
        if v is None or isinstance(v,(dict,list)): raise LaunchError("attribute values must be scalar source facts")
    if not isinstance(p["benefits"],list) or not p["benefits"]: raise LaunchError("benefits must be non-empty list")
    for v in p["benefits"]: text(v,"benefit")
    if not isinstance(p["channels"],list) or not p["channels"]: raise LaunchError("channels must be non-empty list")
    if len(set(p["channels"]))!=len(p["channels"]): raise LaunchError("channels must be unique")
    if any(not isinstance(v,str) or not CHAN.fullmatch(v) for v in p["channels"]): raise LaunchError("invalid channel slug")
    c=p.get("creative_constraints",[])
    if not isinstance(c,list) or any(not isinstance(v,str) or not v.strip() for v in c): raise LaunchError("creative_constraints must be strings")
    return p

def inventory(s:dict[str,Any])->dict[str,Any]:
    need=s["available"]<=s["reorder_at"]
    return {"sku":s["sku"],"available":s["available"],"reorder_at":s["reorder_at"],"reorder_needed":need,"action":"DRAFT_REORDER_ONLY" if need else "NONE"}

def _is_managed_workspace(out:Path)->bool:
    """True when the destination already holds a prior launch_ops workspace."""
    return (out / "state.json").is_file() or (out / "manifest.json").is_file()

def build(p:Any,out:str|Path)->dict[str,Any]:
    p=validate(p); out=Path(out)
    if out.exists() and _is_managed_workspace(out):
        raise LaunchError("output directory already contains a managed launch workspace; use a fresh/empty directory")
    out.mkdir(parents=True,exist_ok=True)
    listing={k:{"channel":k,**{x:copy.deepcopy(p[x]) for x in ("sku","name","description","price_cents","currency","shipping_terms","return_days","attributes","benefits")},"source":"operator_supplied"} for k in p["channels"]}
    constraints="\n".join(f"- {v}" for v in p.get("creative_constraints",[])) or "- None supplied."
    brief=f"# Creative brief — {p['name']}\n\nSKU: `{p['sku']}`\n\n## Source description\n{p['description']}\n\n## Supplied benefits\n"+"\n".join(f"- {v}" for v in p["benefits"])+f"\n\n## Constraints\n{constraints}\n\nUse only supplied facts. Do not invent performance, health, safety, scarcity, endorsement, or fulfillment claims.\n"
    support=f"# Support playbook — {p['name']}\n\nContact: {p['support_contact']}\n\nShipping: {p['shipping_terms']}\n\nReturn window: {p['return_days']} days. Create a staff handoff; this tool does not approve refunds or move money. Escalate safety questions, unsupported claims, payment disputes, and damaged-item decisions.\n"
    runbook="# Order / return handoff\n\nLocal acceptance only; no real order, payment, refund, stock publish, or supplier action. Same-ID same-payload retries are idempotent; conflicting reuse is rejected. `restock` restores local stock, `hold` does not.\n"
    s={"schema":1,"sku":p["sku"],"available":p["stock"],"reorder_at":p["reorder_at"],"channels":{c:{"available":p["stock"]} for c in p["channels"]},"orders":{},"returns":{},"events":[]}
    payloads={
      "product_source.json":canon(p),"listings.json":canon({"listings":listing}),"creative_brief.md":brief.encode(),"support_playbook.md":support.encode(),"order_return_runbook.md":runbook.encode(),"state.json":canon(s),
      "inventory_handoff.json":canon({"sku":p["sku"],"source_available":p["stock"],"channels":{c:{"available":p["stock"],"publication":"NOT_SENT"} for c in p["channels"]}}),"reorder_reminder.json":canon(inventory(s))}
    for n,b in payloads.items(): (out/n).write_bytes(b)
    m={"schema":1,"sku":p["sku"],"source_sha256":sha(out/"product_source.json"),"files":{n:sha(out/n) for n in payloads}}
    (out/"manifest.json").write_bytes(canon(m)); return m

def load(path:Path)->dict[str,Any]:
    try: s=json.loads(path.read_text())
    except FileNotFoundError as e: raise LaunchError(f"state file not found: {path}") from e
    if not isinstance(s,dict) or s.get("schema")!=1: raise LaunchError("invalid state file")
    return s
def save(path:Path,s:dict[str,Any]):
    tmp=path.with_name(path.name+".tmp"); tmp.write_bytes(canon(s)); os.replace(tmp,path)
def sync(s):
    for v in s["channels"].values(): v["available"]=s["available"]

def order(path:str|Path,oid:str,qty:int)->dict[str,Any]:
    path=Path(path); s=load(path); text(oid,"order_id")
    if not isinstance(qty,int) or isinstance(qty,bool) or qty<=0: raise LaunchError("quantity must be positive int")
    if oid in s["orders"]:
        o=s["orders"][oid]
        if o["quantity"]!=qty: raise LaunchError("order_id exists with different quantity")
        return {"idempotent":True,"order":o,"inventory":inventory(s)}
    if qty>s["available"]: raise LaunchError("insufficient available stock")
    s["available"]-=qty; o={"order_id":oid,"sku":s["sku"],"quantity":qty,"status":"FULFILLMENT_HANDOFF"}; s["orders"][oid]=o
    s["events"].append({"type":"ORDER_HANDOFF","order_id":oid,"quantity":qty}); sync(s); save(path,s)
    return {"idempotent":False,"order":o,"inventory":inventory(s)}

def ret(path:str|Path,oid:str,rid:str,disposition:str)->dict[str,Any]:
    path=Path(path); s=load(path); text(oid,"order_id"); text(rid,"return_id")
    if disposition not in {"restock","hold"}: raise LaunchError("disposition must be restock or hold")
    if oid not in s["orders"]: raise LaunchError("unknown order_id")
    if rid in s["returns"]:
        r=s["returns"][rid]
        if r["order_id"]!=oid or r["disposition"]!=disposition: raise LaunchError("return_id exists with different payload")
        return {"idempotent":True,"return":r,"inventory":inventory(s)}
    if any(r["order_id"]==oid for r in s["returns"].values()): raise LaunchError("order already has a return handoff")
    o=s["orders"][oid]; r={"return_id":rid,"order_id":oid,"sku":s["sku"],"quantity":o["quantity"],"disposition":disposition,"status":"RETURN_HANDOFF"}; s["returns"][rid]=r; o["status"]="RETURN_HANDOFF"
    if disposition=="restock": s["available"]+=o["quantity"]
    s["events"].append({"type":"RETURN_HANDOFF","order_id":oid,"return_id":rid,"quantity":o["quantity"],"disposition":disposition}); sync(s); save(path,s)
    return {"idempotent":False,"return":r,"inventory":inventory(s)}

def parser():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True)
    b=sub.add_parser("build"); b.add_argument("product_json"); b.add_argument("--out",required=True)
    o=sub.add_parser("order"); o.add_argument("--state",required=True); o.add_argument("--order-id",required=True); o.add_argument("--quantity",type=int,required=True)
    r=sub.add_parser("return"); r.add_argument("--state",required=True); r.add_argument("--order-id",required=True); r.add_argument("--return-id",required=True); r.add_argument("--disposition",choices=("restock","hold"),required=True)
    s=sub.add_parser("status"); s.add_argument("--state",required=True); return p

def main(argv=None):
    a=parser().parse_args(argv)
    try:
        if a.cmd=="build": v=build(json.loads(Path(a.product_json).read_text()),a.out)
        elif a.cmd=="order": v=order(a.state,a.order_id,a.quantity)
        elif a.cmd=="return": v=ret(a.state,a.order_id,a.return_id,a.disposition)
        else: s=load(Path(a.state)); v={"state":s,"inventory":inventory(s)}
        print(json.dumps(v,indent=2,sort_keys=True)); return 0
    except (LaunchError,OSError,json.JSONDecodeError) as e: print(f"ERROR: {e}",file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())
