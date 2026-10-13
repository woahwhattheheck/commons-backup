"""Evidence-bound public-procurement price intelligence compiler."""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from datetime import datetime, timezone
from pathlib import Path

INPUT="procurement-price-intelligence/input/v1"
PACKET="procurement-price-intelligence/packet/v1"
RECEIPT="procurement-price-intelligence/receipt/v1"
BOUNDARY="INTERNAL_PRICE_RESEARCH_ONLY"
AUTH={"BUYER_OFFICIAL","SECONDARY_INDEX","SELF_AUTHORED","SYNTHETIC_FIXTURE"}
SCLASS={"AWARD_NOTICE","BID_TABULATION","EXECUTED_CONTRACT","BOARD_AWARD","SOLICITATION","AMENDMENT","OTHER"}
KINDS={"AWARD","BID","ESTIMATE","BUDGET","CEILING","OPTION","RENEWAL"}
BASIS={"HOURLY_RATE","UNIT_RATE","LUMP_SUM","CONTRACT_TOTAL"}
READY_KINDS={"AWARD","BID"}
TOK=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$")
SHA=re.compile(r"^[0-9a-f]{64}$")
TS=re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
CUR=re.compile(r"^[A-Z]{3}$")

class Error(ValueError): pass

def _pairs(items):
    out={}
    for k,v in items:
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
def keys(v,want,w):
    if not isinstance(v,dict) or set(v)!=set(want): raise Error(f"{w}: keys mismatch")
def s(v,w,token=False,limit=4096):
    if not isinstance(v,str) or not v or len(v)>limit: raise Error(f"{w}: invalid string")
    if any(ord(c)<32 and c not in "\n\t" for c in v): raise Error(f"{w}: control char")
    if token and not TOK.fullmatch(v): raise Error(f"{w}: invalid token")
    return v
def integer(v,w,lo=0,hi=10**15):
    if isinstance(v,bool) or not isinstance(v,int) or not lo<=v<=hi: raise Error(f"{w}: integer required")
    return v
def sha(v,w):
    v=s(v,w,limit=64)
    if not SHA.fullmatch(v): raise Error(f"{w}: sha256 required")
    return v
def ts(v,w):
    v=s(v,w,limit=20)
    try:
        if not TS.fullmatch(v): raise ValueError
        datetime.strptime(v,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as e: raise Error(f"{w}: UTC second timestamp required") from e
    return v
def dtime(v): return datetime.strptime(v,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
def toklist(v,w,minn=0,maxn=32):
    if not isinstance(v,list) or not minn<=len(v)<=maxn: raise Error(f"{w}: invalid list")
    out=[s(x,f"{w}[{i}]",True,128) for i,x in enumerate(v)]
    if len(out)!=len(set(out)): raise Error(f"{w}: duplicate item")
    return sorted(out)

def authority():
    return {k:False for k in ["quote_authorized","bid_authorized","submission_authorized","buyer_or_partner_contact_authorized","signature_authorized","price_commitment_authorized","award_recognized","invoice_authorized","payment_authorized","revenue_recognized"]}

def normalize(v):
    keys(v,["schema","dataset_id","generated_at","max_source_age_seconds","truth_boundary","sources","observations","target"],"input")
    if v["schema"]!=INPUT or v["truth_boundary"]!=BOUNDARY: raise Error("input: unsupported schema/boundary")
    now=ts(v["generated_at"],"generated_at"); maxage=integer(v["max_source_age_seconds"],"max_source_age_seconds",1,31536000)
    if not isinstance(v["sources"],list) or not v["sources"]: raise Error("sources required")
    src=[]
    for n,x in enumerate(v["sources"]):
        w=f"sources[{n}]"; keys(x,["source_id","uri","sha256","observed_at","authority","source_class","title"],w)
        a=s(x["authority"],w+".authority",True,32); sc=s(x["source_class"],w+".source_class",True,32)
        if a not in AUTH: raise Error(w+": bad authority")
        if sc not in SCLASS: raise Error(w+": bad source_class")
        ob=ts(x["observed_at"],w+".observed_at"); age=int((dtime(now)-dtime(ob)).total_seconds())
        if age<0: raise Error(w+": future source")
        src.append({"source_id":s(x["source_id"],w+".source_id",True),"uri":s(x["uri"],w+".uri",limit=2048),"sha256":sha(x["sha256"],w+".sha256"),"observed_at":ob,"authority":a,"source_class":sc,"title":s(x["title"],w+".title",limit=256),"stale":age>maxage})
    ids=[x["source_id"] for x in src]
    if len(ids)!=len(set(ids)): raise Error("duplicate source_id")
    sm={x["source_id"]:x for x in src}
    if not isinstance(v["observations"],list): raise Error("observations: list required")
    obs=[]
    for n,x in enumerate(v["observations"]):
        w=f"observations[{n}]"; keys(x,["observation_id","claim_key","opportunity_id","vendor","price_kind","amount_minor","currency","basis","unit","term_months","event_date","source_ids"],w)
        kind=s(x["price_kind"],w+".price_kind",True,32); basis=s(x["basis"],w+".basis",True,32)
        if kind not in KINDS: raise Error(w+": bad price_kind")
        if basis not in BASIS: raise Error(w+": bad basis")
        cur=s(x["currency"],w+".currency",limit=3)
        if not CUR.fullmatch(cur): raise Error(w+": currency ISO-like uppercase code required")
        term=x["term_months"]
        if term is not None: term=integer(term,w+".term_months",1,1200)
        unit=x["unit"]
        if unit is not None: unit=s(unit,w+".unit",True,128)
        if basis in {"HOURLY_RATE","UNIT_RATE"} and unit is None: raise Error(w+": rate basis requires unit")
        if basis in {"LUMP_SUM","CONTRACT_TOTAL"} and unit is not None: raise Error(w+": lump/total basis forbids unit")
        eids=toklist(x["source_ids"],w+".source_ids",1)
        if set(eids)-set(sm): raise Error(w+": unknown source")
        event=s(x["event_date"],w+".event_date",limit=10)
        try: datetime.strptime(event,"%Y-%m-%d")
        except ValueError as e: raise Error(w+": event_date YYYY-MM-DD required") from e
        obs.append({"observation_id":s(x["observation_id"],w+".observation_id",True),"claim_key":s(x["claim_key"],w+".claim_key",True),"opportunity_id":s(x["opportunity_id"],w+".opportunity_id",True),"vendor":s(x["vendor"],w+".vendor",limit=256),"price_kind":kind,"amount_minor":integer(x["amount_minor"],w+".amount_minor",0,10**15),"currency":cur,"basis":basis,"unit":unit,"term_months":term,"event_date":event,"source_ids":eids})
    oids=[x["observation_id"] for x in obs]
    if len(oids)!=len(set(oids)): raise Error("duplicate observation_id")
    t=v["target"]; keys(t,["target_id","currency","basis","unit","term_months","allowed_price_kinds"],"target")
    cur=s(t["currency"],"target.currency",limit=3)
    if not CUR.fullmatch(cur): raise Error("target.currency invalid")
    bas=s(t["basis"],"target.basis",True,32)
    if bas not in BASIS: raise Error("target.basis invalid")
    unit=t["unit"]
    if unit is not None: unit=s(unit,"target.unit",True,128)
    if bas in {"HOURLY_RATE","UNIT_RATE"} and unit is None: raise Error("target rate basis requires unit")
    if bas in {"LUMP_SUM","CONTRACT_TOTAL"} and unit is not None: raise Error("target lump/total basis forbids unit")
    term=t["term_months"]
    if term is not None: term=integer(term,"target.term_months",1,1200)
    allowed=toklist(t["allowed_price_kinds"],"target.allowed_price_kinds",1,2)
    if not set(allowed)<=READY_KINDS: raise Error("target.allowed_price_kinds only AWARD/BID")
    return {"dataset_id":s(v["dataset_id"],"dataset_id",True),"generated_at":now,"sources":sorted(src,key=lambda x:x["source_id"]),"source_map":sm,"observations":sorted(obs,key=lambda x:x["observation_id"]),"target":{"target_id":s(t["target_id"],"target.target_id",True),"currency":cur,"basis":bas,"unit":unit,"term_months":term,"allowed_price_kinds":allowed}}

def comp_tuple(x): return (x["currency"],x["basis"],x["unit"],x["term_months"])
def claim_signature(x): return (x["opportunity_id"],x["vendor"],x["amount_minor"])+comp_tuple(x)+(x["price_kind"],)
def fresh_official(o,sm):
    rows=[sm[x] for x in o["source_ids"]]
    return any(x["authority"]=="BUYER_OFFICIAL" and not x["stale"] for x in rows)
def stale_official(o,sm):
    rows=[sm[x] for x in o["source_ids"]]
    return any(x["authority"]=="BUYER_OFFICIAL" and x["stale"] for x in rows)
def projected(o,sm):
    return {**o,"sources":[{k:sm[e][k] for k in ["source_id","uri","sha256","observed_at","authority","source_class"]} for e in o["source_ids"]]}

def compile(raw:bytes):
    N=normalize(load(raw)); sm=N["source_map"]; t=N["target"]; target_tuple=comp_tuple(t)
    eligible_kind=[o for o in N["observations"] if o["price_kind"] in t["allowed_price_kinds"]]
    official=[o for o in eligible_kind if fresh_official(o,sm)]
    byclaim={}
    for o in official: byclaim.setdefault(o["claim_key"],[]).append(o)
    conflicts=[]; claim_rows=[]
    for ck,rows in sorted(byclaim.items()):
        signatures={claim_signature(x) for x in rows}
        if len(signatures)>1:
            conflicts.append({"claim_key":ck,"observation_ids":sorted(x["observation_id"] for x in rows)})
            claim_rows.extend(rows)
            continue
        ordered=sorted(rows,key=lambda x:x["observation_id"])
        merged={**ordered[0]}
        merged["source_ids"]=sorted({source_id for row in ordered for source_id in row["source_ids"]})
        claim_rows.append(merged)
    comparable=[o for o in claim_rows if comp_tuple(o)==target_tuple]
    stale_matching=[o for o in eligible_kind if comp_tuple(o)==target_tuple and stale_official(o,sm) and not fresh_official(o,sm)]
    if conflicts:
        status="HOLD_SOURCE_CONFLICT"; reasons=[f"authoritative claim conflict: {x['claim_key']}" for x in conflicts]
    elif comparable:
        status="PRICE_EVIDENCE_READY"; reasons=[]
    elif stale_matching:
        status="HOLD_STALE"; reasons=["matching authoritative history exists but source observation is stale"]
    elif official:
        status="HOLD_INCOMPARABLE"; reasons=["fresh authoritative history exists but currency/basis/unit/term differs from target"]
    else:
        status="HOLD_NO_HISTORY"; reasons=["no fresh buyer-official AWARD/BID history is admissible"]
    groups=[]
    for kind in t["allowed_price_kinds"]:
        rows=[o for o in comparable if o["price_kind"]==kind]
        if not rows: continue
        amounts=sorted(x["amount_minor"] for x in rows)
        groups.append({"price_kind":kind,"count":len(rows),"min_minor":amounts[0],"max_minor":amounts[-1],"median_minor":amounts[(len(amounts)-1)//2],"observation_ids":sorted(x["observation_id"] for x in rows)})
    packet={"schema":PACKET,"truth_boundary":BOUNDARY,"dataset_id":N["dataset_id"],"generated_at":N["generated_at"],"status":status,"reasons":reasons,"target":t,"authority":authority(),"comparable_groups":groups,"conflicts":conflicts,"admissible_observations":[projected(o,sm) for o in comparable]}
    pb=canon(packet); mb=memo(packet); receipt={"schema":RECEIPT,"truth_boundary":BOUNDARY,"status":status,"input_sha256":digest(raw),"packet_sha256":digest(pb),"memo_sha256":digest(mb),"authority":authority()}
    return pb,mb,canon(receipt)

def money(minor,currency): return f"{currency} {minor//100}.{minor%100:02d}"
def memo(p):
    t=p["target"]; lines=["# Procurement price intelligence memo","",f"- Status: **{p['status']}**",f"- Target: `{t['currency']} / {t['basis']} / {t['unit'] or 'NONE'} / term={t['term_months']}`","- Authority: **internal price research only; quote/bid/submission/contact/commitment/payment/revenue are all false**",""]
    if p["reasons"]: lines += ["## Holds",""]+[f"- {x}" for x in p["reasons"]]+[""]
    lines += ["## Comparable historical ranges",""]
    if not p["comparable_groups"]: lines += ["No admissible comparable range.",""]
    for g in p["comparable_groups"]:
        lines += [f"### {g['price_kind']}","",f"- Count: {g['count']}",f"- Range: {money(g['min_minor'],t['currency'])} — {money(g['max_minor'],t['currency'])}",f"- Deterministic median: {money(g['median_minor'],t['currency'])}",""]
    if p["admissible_observations"]:
        lines += ["## Evidence",""]
        for o in p["admissible_observations"]:
            lines.append(f"- `{o['observation_id']}` · {o['vendor']} · {o['price_kind']} · {money(o['amount_minor'],o['currency'])}")
            for z in o["sources"]: lines.append(f"  - `{z['source_id']}` {z['source_class']} · {z['uri']} · `{z['sha256']}` · observed {z['observed_at']}")
        lines.append("")
    return ("\n".join(lines).rstrip()+"\n").encode()

def verify(inp,pkt,md,rec):
    ep,em,er=compile(inp)
    if canon(load(pkt,"packet"))!=pkt: raise Error("packet non-canonical")
    if canon(load(rec,"receipt"))!=rec: raise Error("receipt non-canonical")
    if pkt!=ep: raise Error("packet mismatch")
    if md!=em: raise Error("memo mismatch")
    if rec!=er: raise Error("receipt mismatch")
    return {"verified":True,"status":json.loads(ep)["status"],"packet_sha256":digest(ep),"memo_sha256":digest(em)}

def main(argv=None):
    ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest="cmd",required=True)
    c=sp.add_parser("compile"); c.add_argument("--input",required=True); c.add_argument("--out-dir",required=True)
    v=sp.add_parser("verify")
    for x in ["--input","--packet","--memo","--receipt"]: v.add_argument(x,required=True)
    a=ap.parse_args(argv)
    try:
        rb=lambda p:Path(p).read_bytes()
        if a.cmd=="compile":
            p,m,r=compile(rb(a.input)); out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True); (out/"packet.json").write_bytes(p); (out/"memo.md").write_bytes(m); (out/"receipt.json").write_bytes(r); print(json.dumps({"status":json.loads(p)["status"],"packet_sha256":digest(p)},sort_keys=True))
        else: print(json.dumps(verify(rb(a.input),rb(a.packet),rb(a.memo),rb(a.receipt)),sort_keys=True))
        return 0
    except (Error,OSError) as e: print(f"HOLD: {e}",file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())
