from __future__ import annotations
import argparse, copy, hashlib, hmac, json, sys
from collections import Counter, defaultdict

SCHEMA="sixty-vines-tap-integrity-rail/v1"
RECEIPT_SCHEMA="sixty-vines-tap-integrity-receipt/v1"
EFFECTS={"POUR","WASTE","VOID","REFUND"}
STATUSES={"COMMITTED","UNKNOWN_EFFECT"}
COMMON={"event_id","seq","type"}
FIELDS={
"KEG_RECEIVED":COMMON|{"keg_id","lot_id","wine_id","sku","volume_ml"},
"TAP_ASSIGN":COMMON|{"tap_id","line_id","keg_id"},
"LINE_CLEAN":COMMON|{"line_id","valid_through_seq"},
"TAP_STATUS":COMMON|{"tap_id","available","temperature_ok"},
"POUR":COMMON|{"effect_id","effect_status","tap_id","line_id","keg_id","lot_id","wine_id","sku","pour_ml","table_id","check_id","amount_cents"},
"WASTE":COMMON|{"effect_id","effect_status","tap_id","line_id","keg_id","lot_id","wine_id","sku","waste_ml","reason"},
"VOID":COMMON|{"effect_id","effect_status","target_effect_id","check_id","amount_cents"},
"REFUND":COMMON|{"effect_id","effect_status","target_effect_id","check_id","amount_cents"},
}
PII={"guest","guest_name","customer","customer_name","email","phone","address","dob","date_of_birth","age","license","id_number","card_number","card_token","payment_token"}

class IntegrityError(ValueError): pass

def canonical_json(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def sha256_json(v): return hashlib.sha256(canonical_json(v).encode()).hexdigest()

def _keys(v):
    if isinstance(v,dict):
        for k,x in v.items():
            yield str(k); yield from _keys(x)
    elif isinstance(v,list):
        for x in v: yield from _keys(x)

def _sid(v,n):
    if not isinstance(v,str) or not v or len(v)>128 or any(c.isspace() for c in v):
        raise IntegrityError(f"{n} must be a non-empty string <= 128 chars without whitespace")
def _int(v,n,minimum=0):
    if isinstance(v,bool) or not isinstance(v,int): raise IntegrityError(f"{n} must be an integer")
    if v<minimum: raise IntegrityError(f"{n} must be >= {minimum}")
def _bool(v,n):
    if type(v) is not bool: raise IntegrityError(f"{n} must be boolean")

def _event(raw):
    if not isinstance(raw,dict): raise IntegrityError("each event must be an object")
    e=copy.deepcopy(raw); bad=sorted({k.lower() for k in _keys(e)}&PII)
    if bad: raise IntegrityError("PII/customer field(s) are forbidden: "+",".join(bad))
    t=e.get("type")
    if t not in FIELDS: raise IntegrityError(f"unknown event type: {t!r}")
    miss=sorted(FIELDS[t]-set(e)); extra=sorted(set(e)-FIELDS[t])
    if miss: raise IntegrityError(f"{t} missing fields: {','.join(miss)}")
    if extra: raise IntegrityError(f"{t} unexpected fields: {','.join(extra)}")
    _sid(e["event_id"],"event_id"); _int(e["seq"],"seq",1)
    for k in ("keg_id","lot_id","wine_id","sku","tap_id","line_id","effect_id","target_effect_id","table_id","check_id","reason"):
        if k in e: _sid(e[k],k)
    for k in ("volume_ml","pour_ml","waste_ml"):
        if k in e: _int(e[k],k,1)
    if "amount_cents" in e: _int(e["amount_cents"],"amount_cents",0)
    if "valid_through_seq" in e: _int(e["valid_through_seq"],"valid_through_seq",e["seq"])
    if "available" in e: _bool(e["available"],"available")
    if "temperature_ok" in e: _bool(e["temperature_ok"],"temperature_ok")
    if "effect_status" in e and e["effect_status"] not in STATUSES: raise IntegrityError("invalid effect_status")
    return e

def _hold(e,*reasons):
    return {"event_id":e["event_id"],"effect_id":e.get("effect_id"),"seq":e["seq"],"type":e["type"],"reasons":sorted(set(reasons))}
def _fp(e): return sha256_json({k:v for k,v in e.items() if k not in {"event_id","seq"}})

def reconcile(events,expected_taps=None):
    if not isinstance(events,list): raise IntegrityError("events must be a list")
    by={}; exact=0
    for raw in events:
        e=_event(raw); old=by.get(e["event_id"])
        if old is None: by[e["event_id"]]=e
        elif canonical_json(old)==canonical_json(e): exact+=1
        else: raise IntegrityError(f"event_id collision: {e['event_id']}")
    ordered=sorted(by.values(),key=lambda e:(e["seq"],e["event_id"])); seqs={}
    for e in ordered:
        old=seqs.setdefault(e["seq"],e["event_id"])
        if old!=e["event_id"]: raise IntegrityError(f"sequence collision at {e['seq']}: {old} vs {e['event_id']}")
    kegs={}; assign={}; line_tap={}; clean={}; status={}; effects={}; pours={}; rev=defaultdict(int)
    holds=[]; unknown=[]; retries=[]; cov=Counter()
    receipts=[]
    for e in ordered:
        t=e["type"]
        if t=="KEG_RECEIVED":
            row={"keg_id":e["keg_id"],"lot_id":e["lot_id"],"wine_id":e["wine_id"],"sku":e["sku"],"volume_ml":e["volume_ml"],"used_ml":0}
            if e["keg_id"] in kegs:
                same=all(kegs[e["keg_id"]][k]==row[k] for k in ("keg_id","lot_id","wine_id","sku","volume_ml"))
                if not same: raise IntegrityError(f"keg identity collision: {e['keg_id']}")
                raise IntegrityError(f"duplicate keg receipt requires event retry: {e['keg_id']}")
            kegs[e["keg_id"]]=row; cov["keg_received"]+=1; continue
        if t=="TAP_ASSIGN":
            if e["keg_id"] not in kegs: holds.append(_hold(e,"unknown_keg")); continue
            other=line_tap.get(e["line_id"])
            if other and other!=e["tap_id"]: holds.append(_hold(e,"line_already_assigned")); continue
            prev=assign.get(e["tap_id"])
            if prev and prev["line_id"]!=e["line_id"]: line_tap.pop(prev["line_id"],None)
            assign[e["tap_id"]]={"line_id":e["line_id"],"keg_id":e["keg_id"]}; line_tap[e["line_id"]]=e["tap_id"]; cov["tap_assign"]+=1; continue
        if t=="LINE_CLEAN":
            if e["line_id"] in clean and e["valid_through_seq"]<clean[e["line_id"]]:
                holds.append(_hold(e,"cleaning_window_regression")); continue
            clean[e["line_id"]]=e["valid_through_seq"]; cov["line_clean"]+=1; continue
        if t=="TAP_STATUS":
            if e["tap_id"] not in assign: holds.append(_hold(e,"tap_unassigned")); continue
            status[e["tap_id"]]={"available":e["available"],"temperature_ok":e["temperature_ok"]}; cov["tap_status"]+=1; continue
        eid=e["effect_id"]; fp=_fp(e)
        if eid in effects:
            if effects[eid]["fp"]!=fp: raise IntegrityError(f"effect_id collision: {eid}")
            retries.append({"effect_id":eid,"event_id":e["event_id"],"seq":e["seq"],"disposition":"DUPLICATE_EFFECT_SUPPRESSED"}); cov["effect_retries_suppressed"]+=1; continue
        effects[eid]={"fp":fp,"type":t,"status":e["effect_status"],"event_id":e["event_id"],"seq":e["seq"],"applied":False}
        if e["effect_status"]=="UNKNOWN_EFFECT":
            unknown.append({"effect_id":eid,"event_id":e["event_id"],"seq":e["seq"],"type":t}); cov["unknown_effect"]+=1; continue
        if t in {"POUR","WASTE"}:
            reasons=[]; a=assign.get(e["tap_id"])
            if not a: reasons.append("tap_unassigned")
            else:
                if a["line_id"]!=e["line_id"]: reasons.append("line_mismatch")
                if a["keg_id"]!=e["keg_id"]: reasons.append("keg_mismatch")
            k=kegs.get(e["keg_id"])
            if not k: reasons.append("unknown_keg")
            else:
                for field,reason in (("lot_id","lot_mismatch"),("wine_id","wine_mismatch"),("sku","sku_mismatch")):
                    if k[field]!=e[field]: reasons.append(reason)
            st=status.get(e["tap_id"])
            if not st: reasons.append("tap_status_unknown")
            else:
                if not st["available"]: reasons.append("tap_unavailable")
                if not st["temperature_ok"]: reasons.append("temperature_hold")
            thru=clean.get(e["line_id"])
            if thru is None: reasons.append("cleaning_unknown")
            elif e["seq"]>thru: reasons.append("cleaning_overdue")
            qty=e["pour_ml"] if t=="POUR" else e["waste_ml"]
            if k and qty>k["volume_ml"]-k["used_ml"]: reasons.append("insufficient_keg_volume")
            if reasons: holds.append(_hold(e,*reasons)); cov[t.lower()+"_held"]+=1; continue
            k["used_ml"]+=qty
            r={"effect_id":eid,"event_id":e["event_id"],"seq":e["seq"],"type":t,"wine_id":k["wine_id"],"sku":k["sku"],"keg_id":k["keg_id"],"lot_id":k["lot_id"],"tap_id":e["tap_id"],"line_id":e["line_id"],"remaining_ml_after":k["volume_ml"]-k["used_ml"],"quantity_ml":qty}
            if t=="POUR":
                r.update(table_id=e["table_id"],check_id=e["check_id"],amount_cents=e["amount_cents"])
                pours[eid]={"check_id":e["check_id"],"amount_cents":e["amount_cents"]}; cov["pour_committed"]+=1
                if qty<150: cov["partial_pour"]+=1
            else: r["reason"]=e["reason"]; cov["waste_committed"]+=1
            receipts.append(r); effects[eid].update(applied=True,receipt=r); cov["tap:"+e["tap_id"]]+=1; continue
        target=pours.get(e["target_effect_id"]); reasons=[]
        if not target: reasons.append("target_not_committed_pour")
        else:
            if target["check_id"]!=e["check_id"]: reasons.append("check_mismatch")
            if rev[e["target_effect_id"]]+e["amount_cents"]>target["amount_cents"]: reasons.append("reversal_overage")
        if reasons: holds.append(_hold(e,*reasons)); cov[t.lower()+"_held"]+=1; continue
        rev[e["target_effect_id"]]+=e["amount_cents"]
        r={"effect_id":eid,"event_id":e["event_id"],"seq":e["seq"],"type":t,"target_effect_id":e["target_effect_id"],"check_id":e["check_id"],"amount_cents":e["amount_cents"]}
        receipts.append(r); effects[eid].update(applied=True,receipt=r); cov[t.lower()+"_committed"]+=1
    receipts.sort(key=lambda r:(r["seq"],r["effect_id"]))
    tap_ids=sorted(k[4:] for k in cov if k.startswith("tap:") and cov[k])
    coverage={k:cov[k] for k in sorted(cov) if not k.startswith("tap:")}
    coverage.update(unique_taps_with_committed_effects=len(tap_ids),exact_input_retries_suppressed=exact)
    gross=sum(r["amount_cents"] for r in receipts if r["type"]=="POUR"); reversal=sum(rev.values())
    core={"schema":SCHEMA,"input_rows":len(events),"unique_events":len(ordered),"kegs":len(kegs),"tap_assignments":len(assign),"taps_with_committed_effects":tap_ids,
          "effects":[{"effect_id":i,"type":x["type"],"status":x["status"],"applied":x["applied"],"event_id":x["event_id"],"seq":x["seq"]} for i,x in sorted(effects.items())],
          "effect_receipts":receipts,"holds":sorted(holds,key=lambda x:(x["seq"],x["event_id"])),"unknown_effects":sorted(unknown,key=lambda x:(x["seq"],x["event_id"])),"retry_receipts":sorted(retries,key=lambda x:(x["seq"],x["event_id"])),"coverage":coverage,
          "reconciliation":{"monetary_gross_cents":gross,"reversal_cents":reversal,"monetary_net_cents":gross-reversal,"inventory_used_ml":sum(k["used_ml"] for k in kegs.values()),"inventory_remaining_ml":sum(k["volume_ml"]-k["used_ml"] for k in kegs.values()),"committed_pours":sum(r["type"]=="POUR" for r in receipts),"committed_waste":sum(r["type"]=="WASTE" for r in receipts),"committed_voids":sum(r["type"]=="VOID" for r in receipts),"committed_refunds":sum(r["type"]=="REFUND" for r in receipts),"held_events":len(holds),"unknown_effects":len(unknown)}}
    digest=sha256_json(core); ok=(expected_taps is None or len(tap_ids)==expected_taps) and gross>=reversal and all(r.get("remaining_ml_after",0)>=0 for r in receipts)
    return {**core,"manifest_sha256":digest,"integrity_pass":ok,"expected_taps":expected_taps}

def make_receipt(result):
    core={k:v for k,v in result.items() if k!="manifest_sha256"}
    return {"schema":RECEIPT_SCHEMA,"manifest_sha256":result["manifest_sha256"],"result_sha256":sha256_json(core),"integrity_pass":bool(result["integrity_pass"]),"input_rows":result["input_rows"]}
def verify_receipt(receipt,result):
    if not isinstance(receipt,dict) or not isinstance(result,dict) or receipt.get("schema")!=RECEIPT_SCHEMA: return False
    try: expected=make_receipt(result)
    except (KeyError,TypeError): return False
    return all(hmac.compare_digest(str(receipt.get(k,"")),str(expected[k])) for k in ("manifest_sha256","result_sha256")) and receipt.get("integrity_pass") is expected["integrity_pass"] and receipt.get("input_rows")==expected["input_rows"]

def _e(seq,t,s,**kw): return {"event_id":f"E-{seq:05d}-{s}","seq":seq,"type":t,**kw}

def build_synthetic_fixture(event_count=20000,tap_count=60):
    _int(event_count,"event_count",1000); _int(tap_count,"tap_count",8)
    if tap_count>999: raise IntegrityError("tap_count too large for synthetic fixture")
    ev=[]; seq=1; normal=event_count+10000
    for i in range(1,tap_count+1):
        tap=f"T{i:02d}"; line=f"L{i:02d}"; keg=f"K{i:02d}-A"; lot=f"LOT-{i:02d}-A"; wine=f"WINE-{i:02d}"; sku=f"SKU-{i:02d}"
        ev.append(_e(seq,"KEG_RECEIVED",f"KR-{i}",keg_id=keg,lot_id=lot,wine_id=wine,sku=sku,volume_ml=200000)); seq+=1
        ev.append(_e(seq,"TAP_ASSIGN",f"TA-{i}",tap_id=tap,line_id=line,keg_id=keg)); seq+=1
        ev.append(_e(seq,"LINE_CLEAN",f"LC-{i}",line_id=line,valid_through_seq=4*tap_count+17 if i==8 else normal)); seq+=1
        ev.append(_e(seq,"TAP_STATUS",f"TS-{i}",tap_id=tap,available=True,temperature_ok=True)); seq+=1
    ev.append(_e(seq,"KEG_RECEIVED","SUB",keg_id="K01-B",lot_id="LOT-01-B",wine_id="WINE-01-B",sku="SKU-01-B",volume_ml=200000)); seq+=1
    ev.append(_e(seq,"TAP_ASSIGN","SUBA",tap_id="T01",line_id="L01",keg_id="K01-B")); seq+=1
    target=_e(seq,"POUR","TARGET",effect_id="FX-TARGET",effect_status="COMMITTED",tap_id="T01",line_id="L01",keg_id="K01-B",lot_id="LOT-01-B",wine_id="WINE-01-B",sku="SKU-01-B",pour_ml=150,table_id="TABLE-001",check_id="CHECK-001",amount_cents=1800); ev.append(target); seq+=1
    retry=copy.deepcopy(target); retry.update(event_id=f"E-{seq:05d}-RETRY",seq=seq); ev.append(retry); seq+=1
    def add(t,s,**kw):
        nonlocal seq; ev.append(_e(seq,t,s,**kw)); seq+=1
    add("WASTE","SPILL",effect_id="FX-WASTE-1",effect_status="COMMITTED",tap_id="T02",line_id="L02",keg_id="K02-A",lot_id="LOT-02-A",wine_id="WINE-02",sku="SKU-02",waste_ml=90,reason="synthetic_spill")
    add("POUR","PARTIAL",effect_id="FX-PARTIAL-1",effect_status="COMMITTED",tap_id="T03",line_id="L03",keg_id="K03-A",lot_id="LOT-03-A",wine_id="WINE-03",sku="SKU-03",pour_ml=75,table_id="TABLE-003",check_id="CHECK-003",amount_cents=900)
    add("VOID","VOID",effect_id="FX-VOID-1",effect_status="COMMITTED",target_effect_id="FX-TARGET",check_id="CHECK-001",amount_cents=600)
    add("REFUND","REFUND",effect_id="FX-REFUND-1",effect_status="COMMITTED",target_effect_id="FX-TARGET",check_id="CHECK-001",amount_cents=400)
    add("POUR","UNKNOWN",effect_id="FX-UNKNOWN-1",effect_status="UNKNOWN_EFFECT",tap_id="T04",line_id="L04",keg_id="K04-A",lot_id="LOT-04-A",wine_id="WINE-04",sku="SKU-04",pour_ml=150,table_id="TABLE-004",check_id="CHECK-004",amount_cents=1600)
    add("POUR","MISROUTE",effect_id="FX-HOLD-MISROUTE",effect_status="COMMITTED",tap_id="T05",line_id="L05",keg_id="K05-A",lot_id="LOT-05-A",wine_id="WINE-05",sku="WRONG-SKU",pour_ml=150,table_id="TABLE-005",check_id="CHECK-005",amount_cents=1700)
    add("TAP_STATUS","OFF",tap_id="T06",available=False,temperature_ok=True)
    add("POUR","OFFP",effect_id="FX-HOLD-UNAVAILABLE",effect_status="COMMITTED",tap_id="T06",line_id="L06",keg_id="K06-A",lot_id="LOT-06-A",wine_id="WINE-06",sku="SKU-06",pour_ml=150,table_id="TABLE-006",check_id="CHECK-006",amount_cents=1700)
    add("TAP_STATUS","ON",tap_id="T06",available=True,temperature_ok=True)
    add("TAP_STATUS","TEMP",tap_id="T07",available=True,temperature_ok=False)
    add("POUR","TEMPP",effect_id="FX-HOLD-TEMP",effect_status="COMMITTED",tap_id="T07",line_id="L07",keg_id="K07-A",lot_id="LOT-07-A",wine_id="WINE-07",sku="SKU-07",pour_ml=150,table_id="TABLE-007",check_id="CHECK-007",amount_cents=1700)
    add("TAP_STATUS","TEMPOK",tap_id="T07",available=True,temperature_ok=True)
    add("LINE_CLEAN","EXP8",line_id="L08",valid_through_seq=seq)
    add("POUR","DIRTY",effect_id="FX-HOLD-CLEAN",effect_status="COMMITTED",tap_id="T08",line_id="L08",keg_id="K08-A",lot_id="LOT-08-A",wine_id="WINE-08",sku="SKU-08",pour_ml=150,table_id="TABLE-008",check_id="CHECK-008",amount_cents=1700)
    add("LINE_CLEAN","REST8",line_id="L08",valid_through_seq=normal)
    n=1
    while len(ev)<event_count:
        i=(n-1)%tap_count+1; tap=f"T{i:02d}"; line=f"L{i:02d}"
        if i==1: keg,lot,wine,sku="K01-B","LOT-01-B","WINE-01-B","SKU-01-B"
        else: keg,lot,wine,sku=f"K{i:02d}-A",f"LOT-{i:02d}-A",f"WINE-{i:02d}",f"SKU-{i:02d}"
        ml=75 if n%113==0 else 150
        add("POUR",f"F{n}",effect_id=f"FX-FILL-{n:05d}",effect_status="COMMITTED",tap_id=tap,line_id=line,keg_id=keg,lot_id=lot,wine_id=wine,sku=sku,pour_ml=ml,table_id=f"TABLE-{n%400+1:03d}",check_id=f"CHECK-{n:05d}",amount_cents=900 if ml<150 else 1800); n+=1
    ev[-1]=copy.deepcopy(ev[-2]); return ev

def acceptance_summary(event_count=20000,tap_count=60):
    result=reconcile(build_synthetic_fixture(event_count,tap_count),expected_taps=tap_count); c=result["coverage"]
    required={"effect_retries_suppressed":1,"partial_pour":1,"waste_committed":1,"void_committed":1,"refund_committed":1,"unknown_effect":1,"pour_held":4,"unique_taps_with_committed_effects":tap_count,"exact_input_retries_suppressed":1}
    reasons={x for h in result["holds"] for x in h["reasons"]}
    passed=result["integrity_pass"] and all(c.get(k,0)>=v for k,v in required.items()) and {"sku_mismatch","tap_unavailable","temperature_hold","cleaning_overdue"}<=reasons and result["input_rows"]==event_count
    receipt=make_receipt(result)
    return {"schema":SCHEMA,"acceptance_pass":passed,"event_count":event_count,"tap_count":tap_count,"manifest_sha256":result["manifest_sha256"],"receipt":receipt,"receipt_valid":verify_receipt(receipt,result),"coverage":c,"hold_reasons":sorted(reasons),"reconciliation":result["reconciliation"]}

def main(argv=None):
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest="command",required=True); a=s.add_parser("acceptance")
    a.add_argument("--events",type=int,default=20000); a.add_argument("--taps",type=int,default=60); a.add_argument("--require-pass",action="store_true"); x=p.parse_args(argv)
    try: out=acceptance_summary(x.events,x.taps)
    except IntegrityError as exc: print(canonical_json({"acceptance_pass":False,"error":str(exc)})); return 2
    print(canonical_json(out)); return 0 if out["acceptance_pass"] or not x.require_pass else 1
if __name__=="__main__": sys.exit(main())
