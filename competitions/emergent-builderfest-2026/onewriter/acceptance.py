#!/usr/bin/env python3
"""Offline acceptance verifier for OneWriter's synthetic coordination demo."""
from __future__ import annotations
import argparse, hashlib, json, re, sys, unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit

EXPECTED_DIGEST="4b15651ae153dff379375d285f3a705a2ce4b87014d5d1e08e2dea490251f553"
ROOT_KEYS={"schema_version","product","collision_key","states","events","lease","invariants","authority","contract_digest_sha256"}
EVENT_KEYS={"id","at_utc","kind","actor","org","domain","route","purpose","opportunity","lease_seconds","provider_receipt","human_evidence_id","reason","expect"}
AUTHORITY={"email_send_authorized":False,"dm_send_authorized":False,"form_submit_authorized":False,"provider_mutation_authorized":False,"contract_authorized":False,"signature_authorized":False,"payment_authorized":False,"cash_or_revenue_authorized":False,"contest_submission_authorized":False}
STATES=["CLEAR","LEASED","HARD_DNR","DEAD_ROUTE","HUMAN_EVENT_REOPEN","HOLD"]
EVENTS=["CLAIM","SENT","BOUNCE","HUMAN_EVENT","HOLD"]
FIELDS=["org","domain","purpose","opportunity"]
NORMALIZATION={"org":"unicode-casefold-trim-collapse-space","domain":"idna-host-lower-strip-scheme-www-path-trailing-dot","route":"unicode-casefold-trim-collapse-space","purpose":"unicode-casefold-trim-collapse-space","opportunity":"unicode-casefold-trim-collapse-space"}
EVIDENCE_ID_MAX=240
_DEFAULT_IGNORABLE_NON_C_RANGES=((0x034F,0x034F),(0x115F,0x1160),(0x17B4,0x17B5),(0x180B,0x180D),(0x180F,0x180F),(0x3164,0x3164),(0xFE00,0xFE0F),(0xFFA0,0xFFA0),(0xE0100,0xE01EF))
INVARIANTS=["exactly_one_active_lease_per_collision_key","active_lease_blocks_parallel_claims_across_routes","ordinary_expired_lease_may_be_recovered_with_an_explicit_route","sent_requires_current_lease_holder_matching_leased_route_and_provider_receipt","sent_hard_fences_lane_until_genuine_human_event","bounce_requires_current_lease_holder_matching_leased_route_and_provider_receipt","bounce_is_route_failure_not_buyer_rejection","human_event_requires_distinct_retained_evidence","human_event_reopens_only_a_bounded_next_action","hold_blocks_claims_until_new_human_event","event_ids_provider_receipts_and_human_evidence_ids_are_single_use","timestamps_are_strictly_monotone_utc","no_event_grants_external_send_authority"]

class ContractError(ValueError): pass
def require(ok,msg):
    if not ok: raise ContractError(msg)
def _object(pairs):
    out={}
    for k,v in pairs:
        require(k not in out,f"duplicate JSON key: {k}"); out[k]=v
    return out
def _constant(v): raise ContractError(f"non-finite JSON number: {v}")
def load_json(path):
    try: return json.loads(Path(path).read_text(encoding="utf-8"),object_pairs_hook=_object,parse_constant=_constant)
    except ContractError: raise
    except Exception as exc: raise ContractError(f"could not load {path}: {exc}") from exc
def canonical_bytes(v):
    try: return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    except (TypeError,ValueError,UnicodeError) as exc: raise ContractError("value is not canonical JSON") from exc
def machine_semantic(m): return {k:m[k] for k in sorted(ROOT_KEYS-{"contract_digest_sha256"})}
def validate_machine(m):
    require(isinstance(m,dict) and set(m)==ROOT_KEYS,"state-machine root key set changed")
    require(type(m["schema_version"]) is int and m["schema_version"]==2 and m["product"]=="OneWriter","machine identity changed")
    require(m["collision_key"]=={"algorithm":"sha256-canonical-json-v2-org-lane","fields":FIELDS,"normalization":NORMALIZATION},"collision-key contract changed")
    require(m["states"]==STATES and m["events"]==EVENTS,"state/event list changed")
    require(m["lease"]=={"default_ttl_seconds":300,"min_ttl_seconds":30,"max_ttl_seconds":1800},"lease policy changed")
    require(m["invariants"]==INVARIANTS,"invariant list changed"); require(m["authority"]==AUTHORITY,"authority must remain exact and all-false")
    digest=hashlib.sha256(canonical_bytes(machine_semantic(m))).hexdigest(); require(digest==EXPECTED_DIGEST and m["contract_digest_sha256"]==digest,"state-machine semantic digest mismatch")
    return {"status":"OK","contract_digest_sha256":digest}

_space=re.compile(r"\s+"); _scheme=re.compile(r"^[a-z][a-z0-9+.-]*://",re.I)
def norm_text(v,name):
    require(isinstance(v,str),f"{name} must be a string"); v=_space.sub(" ",v.strip()).casefold(); require(bool(v) and len(v)<=240,f"{name} invalid"); return v
def norm_domain(v):
    require(isinstance(v,str),"domain must be a string"); raw=v.strip(); require(bool(raw),"domain shape invalid")
    try: parsed=urlsplit(raw if _scheme.match(raw) else "https://"+raw)
    except ValueError as exc: raise ContractError("domain shape invalid") from exc
    require(parsed.username is None and parsed.password is None,"domain credentials forbidden")
    try: port=parsed.port
    except ValueError as exc: raise ContractError("domain shape invalid") from exc
    require(port is None,"domain port forbidden")
    host=(parsed.hostname or "").rstrip(".").lower(); host=host[4:] if host.startswith("www.") else host
    try: host=host.encode("idna").decode("ascii")
    except UnicodeError as exc: raise ContractError("domain IDNA invalid") from exc
    require(bool(host) and " " not in host and "@" not in host and len(host)<=253 and "." in host,"domain shape invalid")
    return host
def _default_ignorable_non_c(ch):
    cp=ord(ch); return any(lo<=cp<=hi for lo,hi in _DEFAULT_IGNORABLE_NON_C_RANGES)
def evidence_id(v,name):
    require(type(v) is str,f"{name} must be a string")
    require(v==v.strip() and 1<=len(v)<=EVIDENCE_ID_MAX,f"{name} must be trimmed nonempty text <= {EVIDENCE_ID_MAX} chars")
    require(not any(ord(ch)<32 or ord(ch)==127 for ch in v),f"{name} contains control characters")
    require(not any(ord(ch)>127 and unicodedata.category(ch).startswith("C") for ch in v),f"{name} contains non-visible Unicode control/format/private/unassigned codepoints")
    require(not any(_default_ignorable_non_c(ch) for ch in v),f"{name} contains Unicode Default_Ignorable codepoints")
    require(any(unicodedata.category(ch)[0] not in {"C","M","Z"} for ch in v),f"{name} must contain at least one visible base codepoint")
    return v
def identity(e): return {"org":norm_text(e["org"],"org"),"domain":norm_domain(e["domain"]),"purpose":norm_text(e["purpose"],"purpose"),"opportunity":norm_text(e["opportunity"],"opportunity")}
def event_route(e): return norm_text(e["route"],"route")
def collision_key(e): return hashlib.sha256(canonical_bytes(identity(e))).hexdigest()
def utc(v):
    require(isinstance(v,str) and v.endswith("Z"),"at_utc must be UTC-Z")
    try: return datetime.fromisoformat(v[:-1]+"+00:00").astimezone(timezone.utc)
    except ValueError as exc: raise ContractError("at_utc must be real ISO-8601") from exc
def validate_event(e):
    require(isinstance(e,dict) and set(e)==EVENT_KEYS,"event key set changed")
    for f in ("kind","actor","org","domain","route","purpose","opportunity","reason"): require(isinstance(e[f],str) and e[f].strip(),f"{f} must be nonempty")
    evidence_id(e["id"],"event id")
    require(e["kind"] in EVENTS,"unknown event kind"); utc(e["at_utc"]); identity(e); event_route(e)
    lease=e["lease_seconds"]; provider=e["provider_receipt"]; human=e["human_evidence_id"]
    require(lease is None or type(lease) is int,"lease_seconds must be null or integer (bool forbidden)")
    require(provider is None or type(provider) is str,"provider receipt invalid"); require(human is None or type(human) is str,"human evidence invalid")
    if provider is not None: evidence_id(provider,"provider_receipt")
    if human is not None: evidence_id(human,"human_evidence_id")
    require(isinstance(e["expect"],dict) and set(e["expect"])=={"decision","state"} and e["expect"]["state"] in STATES,"expect invalid")
    if e["kind"]=="CLAIM": require(type(lease) is int and 30<=lease<=1800 and provider is None and human is None,"CLAIM lease/evidence invalid")
    elif e["kind"] in {"SENT","BOUNCE"}: require(lease is None and bool(provider) and human is None,f"{e['kind']} evidence invalid")
    elif e["kind"]=="HUMAN_EVENT": require(lease is None and provider is None and bool(human),"HUMAN_EVENT evidence invalid")
    else: require(lease is None and provider is None and human is None,"HOLD evidence invalid")

def accepted_event(e,route,key):
    return {"event_id":e["id"],"at_utc":e["at_utc"],"kind":e["kind"],"actor":e["actor"],"identity":identity(e),"collision_key":key,"event_route":route,"lease_seconds":e["lease_seconds"],"provider_receipt":e["provider_receipt"],"human_evidence_id":e["human_evidence_id"],"reason":e["reason"]}

@dataclass
class Lane:
    state:str="CLEAR"; holder:str|None=None; until:datetime|None=None; route:str|None=None; reopen_from:str|None=None; reopen_route:str|None=None

def _refence_expired_reopen(lane,now):
    if lane.state=="LEASED" and lane.reopen_from is not None and lane.until is not None and now>=lane.until:
        lane.state=lane.reopen_from; lane.holder=None; lane.until=None; lane.route=lane.reopen_route; lane.reopen_from=None; lane.reopen_route=None; return True
    return False

def evaluate(machine,doc):
    validate_machine(machine); require(isinstance(doc,dict) and set(doc)=={"schema_version","scenario","events","expected_summary"},"demo-events root key set changed"); require(doc["schema_version"]==2 and doc["scenario"]=="synthetic-onewriter-business-demo-v2","demo metadata changed")
    used_ids=set(); lanes={}; receipts=[]; prev=None; metrics={"claims_granted":0,"collisions_prevented":0,"duplicate_touches_prevented":0,"stale_lanes_recovered":0,"sent_hard_fences":0,"dead_routes_recorded":0,"human_reopens":0}
    for pos,e in enumerate(doc["events"]):
        validate_event(e); now=utc(e["at_utc"]); require(prev is None or now>prev,"timestamps must be strictly monotone"); prev=now
        for label,value in (("event id",e["id"]),("provider receipt",e["provider_receipt"]),("human evidence",e["human_evidence_id"])):
            if value is not None:
                require(value not in used_ids,f"workspace identifier reused: {label} {value}"); used_ids.add(value)
        key=collision_key(e); lane=lanes.setdefault(key,Lane()); refenced=_refence_expired_reopen(lane,now); prior=lane.state; kind=e["kind"]; route=event_route(e)
        if kind=="CLAIM":
            if lane.state=="LEASED" and now<lane.until: decision="DENIED_ACTIVE_LEASE"; metrics["collisions_prevented"]+=1; metrics["duplicate_touches_prevented"]+=1
            elif lane.state=="LEASED": lane.holder=e["actor"]; lane.until=now+timedelta(seconds=e["lease_seconds"]); lane.route=route; decision="GRANTED_STALE_RECOVERY"; metrics["claims_granted"]+=1; metrics["stale_lanes_recovered"]+=1
            elif lane.state in {"HARD_DNR","DEAD_ROUTE","HOLD"}: decision=f"DENIED_{lane.state}"; metrics["duplicate_touches_prevented"]+=1
            else:
                decision="GRANTED_AFTER_HUMAN_EVENT" if lane.state=="HUMAN_EVENT_REOPEN" else "GRANTED"; lane.state="LEASED"; lane.holder=e["actor"]; lane.until=now+timedelta(seconds=e["lease_seconds"]); lane.route=route; metrics["claims_granted"]+=1
        elif kind in {"SENT","BOUNCE"}:
            require(lane.state=="LEASED",f"{kind} requires an active lease"); require(lane.holder==e["actor"],f"{kind} actor is not current lease holder"); require(now<lane.until,f"{kind} lease expired"); require(lane.route==route,f"{kind} route does not match current leased route"); lane.holder=None; lane.until=None; lane.reopen_from=None; lane.reopen_route=None
            if kind=="SENT": lane.state="HARD_DNR"; decision="RECORDED_SENT"; metrics["sent_hard_fences"]+=1
            else: lane.state="DEAD_ROUTE"; decision="RECORDED_DEAD_ROUTE"; metrics["dead_routes_recorded"]+=1
        elif kind=="HUMAN_EVENT":
            require(lane.state in {"HARD_DNR","DEAD_ROUTE","HOLD"},"HUMAN_EVENT requires fenced prior lane"); lane.reopen_from=lane.state; lane.reopen_route=lane.route; lane.state="HUMAN_EVENT_REOPEN"; decision="REOPENED_HUMAN_EVENT"; metrics["human_reopens"]+=1
        else:
            require(lane.state!="LEASED","HOLD cannot revoke active lease"); lane.state="HOLD"; lane.route=route; lane.reopen_from=None; lane.reopen_route=None; decision="RECORDED_HOLD"
        observed={"decision":decision,"state":lane.state}; require(observed==e["expect"],f"expected receipt mismatch at {e['id']}: computed {observed}")
        ae=accepted_event(e,route,key); sem={"position":pos,"event_id":e["id"],"at_utc":e["at_utc"],"actor":e["actor"],"collision_key":key,"event_route":route,"lane_route":lane.route,"prior_state":prior,"decision":decision,"state":lane.state,"reopen_expiry_refenced":refenced,"accepted_event":ae,"accepted_event_sha256":hashlib.sha256(canonical_bytes(ae)).hexdigest(),"external_send_authorized":False}; receipts.append({**sem,"receipt_sha256":hashlib.sha256(canonical_bytes(sem)).hexdigest()})
    summary={"status":"OK","scenario":doc["scenario"],"event_count":len(doc["events"]),"lane_count":len(lanes),"metrics":metrics,"authority":AUTHORITY,"receipt_chain_sha256":hashlib.sha256(canonical_bytes(receipts)).hexdigest()}; return {"summary":summary,"receipts":receipts}

def replay(machine,doc):
    result=evaluate(machine,doc); require(result["summary"]==doc["expected_summary"],"expected_summary mismatch: computed "+json.dumps(result["summary"],sort_keys=True,separators=(",",":"))); return result

def main(argv=None):
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest="cmd",required=True); v=s.add_parser("verify-machine"); v.add_argument("machine",type=Path); r=s.add_parser("replay"); r.add_argument("machine",type=Path); r.add_argument("events",type=Path); a=p.parse_args(argv)
    try: result=validate_machine(load_json(a.machine)) if a.cmd=="verify-machine" else replay(load_json(a.machine),load_json(a.events))["summary"]
    except ContractError as exc: print(f"ERROR: {exc}",file=sys.stderr); return 2
    print(json.dumps(result,sort_keys=True,separators=(",",":"))); return 0
if __name__=="__main__": raise SystemExit(main())