#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, json, re, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REQUEST_SCHEMA="owner-commercial-decision-request/v1"
SNAPSHOT_SCHEMA="owner-commercial-provider-snapshot/v1"
BRIEF_SCHEMA="owner-commercial-decision-brief/v1"
BRIEF_SET_SCHEMA="owner-commercial-decision-brief-set/v1"
DECISION_TYPES={"PRICE_BUDGET","PAID_SCOPE","PROCUREMENT_TERMS","CONTRACT_TERMS","OWNER_TIME"}
DISPOSITIONS={"ACTIONABLE","HOLD","CLOSED"}
READY,HOLD,DUPLICATE="READY_FOR_OWNER_RULING","HOLD","DUPLICATE_EXISTING"
MAX_ROWS=256
EMAIL=re.compile(r"^[^\s@<>(),;:]+@[^\s@<>(),;:]+$")
HEX64=re.compile(r"^[0-9a-f]{64}$")

class DecisionGateError(ValueError): pass
class DuplicateKeyError(DecisionGateError): pass

def _pairs(pairs):
    out={}
    for k,v in pairs:
        if k in out: raise DuplicateKeyError(f"duplicate JSON object key: {k}")
        out[k]=v
    return out

def obj(v,label):
    if type(v) is not dict: raise DecisionGateError(f"{label} must be an object")
    return v

def arr(v,label):
    if type(v) is not list: raise DecisionGateError(f"{label} must be a list")
    if len(v)>MAX_ROWS: raise DecisionGateError(f"{label} exceeds {MAX_ROWS} rows")
    return v

def boolean(v,label):
    if type(v) is not bool: raise DecisionGateError(f"{label} must be a boolean")
    return v

def integer(v,label,lo=0,hi=10**15):
    if type(v) is not int: raise DecisionGateError(f"{label} must be an integer")
    if not lo<=v<=hi: raise DecisionGateError(f"{label} must be between {lo} and {hi}")
    return v

def text(v,label,n=2048,multiline=False):
    if type(v) is not str: raise DecisionGateError(f"{label} must be a string")
    t=v.strip()
    if not t: raise DecisionGateError(f"{label} must not be empty")
    if len(t)>n: raise DecisionGateError(f"{label} exceeds {n} characters")
    if any(ord(c)<32 and not(multiline and c in "\n\t") for c in t): raise DecisionGateError(f"{label} contains control characters")
    return t+("\n" if multiline and v.endswith("\n") else "")

def keys(o,allowed,label):
    extra=set(o)-set(allowed)
    if extra: raise DecisionGateError(f"{label} has unknown fields: {', '.join(sorted(extra))}")

def parse_json_bytes(raw,label):
    try: s=raw.decode("utf-8","strict")
    except UnicodeDecodeError as e: raise DecisionGateError(f"{label} must be UTF-8 JSON") from e
    try:
        v=json.loads(s,object_pairs_hook=_pairs,parse_constant=lambda x:(_ for _ in()).throw(DecisionGateError(f"{label} contains non-finite number {x}")))
    except (DuplicateKeyError,DecisionGateError): raise
    except json.JSONDecodeError as e: raise DecisionGateError(f"{label} is not valid JSON: {e.msg}") from e
    return obj(v,label)

def email(v,label):
    s=text(v,label,320)
    if s.count("@")!=1 or not EMAIL.fullmatch(s): raise DecisionGateError(f"{label} must be one plain email address")
    local,domain=s.rsplit("@",1)
    if not local or not domain or domain.startswith(".") or domain.endswith(".") or ".." in domain: raise DecisionGateError(f"{label} is malformed")
    return f"{local}@{domain}".casefold()

def hex64(v,label):
    s=text(v,label,64)
    if not HEX64.fullmatch(s): raise DecisionGateError(f"{label} must be lowercase SHA-256 hex")
    return s

def time(v,label):
    s=text(v,label,64); s=s[:-1]+"+00:00" if s.endswith("Z") else s
    try: d=datetime.fromisoformat(s)
    except ValueError as e: raise DecisionGateError(f"{label} must be ISO-8601") from e
    if d.tzinfo is None or d.utcoffset() is None: raise DecisionGateError(f"{label} must include a timezone")
    return d.astimezone(timezone.utc)

def fmt(d):
    d=d.astimezone(timezone.utc)
    return d.isoformat(timespec="microseconds" if d.microsecond else "seconds").replace("+00:00","Z")

def canonical_bytes(v):
    try: return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    except (TypeError,ValueError) as e: raise DecisionGateError(f"value is not canonical JSON: {e}") from e

def digest(v): return hashlib.sha256(canonical_bytes(v)).hexdigest()
format_time=fmt
digest_object=digest

def event(v,label):
    o=obj(v,label); keys(o,{"event_id","event_sha256","observed_at"},label)
    return {"event_id":text(o.get("event_id"),label+".event_id",256),"event_sha256":hex64(o.get("event_sha256"),label+".event_sha256"),"observed_at":fmt(time(o.get("observed_at"),label+".observed_at"))}

def currency(v,label):
    s=text(v,label,3)
    if not re.fullmatch(r"[A-Z]{3}",s): raise DecisionGateError(f"{label} must be an uppercase 3-letter currency code")
    return s

def row(v,label,kind):
    o=obj(v,label)
    if kind=="offer":
        keys(o,{"offer_id","amount_minor","currency","status","evidence_event_id"},label)
        return {"offer_id":text(o.get("offer_id"),label+".offer_id",256),"amount_minor":integer(o.get("amount_minor"),label+".amount_minor"),"currency":currency(o.get("currency"),label+".currency"),"status":text(o.get("status"),label+".status",64),"evidence_event_id":text(o.get("evidence_event_id"),label+".evidence_event_id",256)}
    if kind=="promise":
        keys(o,{"summary","evidence_event_id"},label)
        return {"summary":text(o.get("summary"),label+".summary",1024),"evidence_event_id":text(o.get("evidence_event_id"),label+".evidence_event_id",256)}
    if kind=="amount":
        keys(o,{"label","amount_minor","currency","evidence_event_id"},label)
        return {"label":text(o.get("label"),label+".label",256),"amount_minor":integer(o.get("amount_minor"),label+".amount_minor"),"currency":currency(o.get("currency"),label+".currency"),"evidence_event_id":text(o.get("evidence_event_id"),label+".evidence_event_id",256)}
    keys(o,{"label","deadline_at","evidence_event_id"},label)
    return {"label":text(o.get("label"),label+".label",256),"deadline_at":fmt(time(o.get("deadline_at"),label+".deadline_at")),"evidence_event_id":text(o.get("evidence_event_id"),label+".evidence_event_id",256)}

def normalize_request(raw):
    allowed={"schema_version","request_id","mailbox","thread_id","inbound_event","decision_type","buyer_scope","opportunity_id","prior_offers","prior_promises","evidenced_amounts","deadlines","recommendation","ruling_needed"}
    keys(raw,allowed,"request")
    if raw.get("schema_version")!=REQUEST_SCHEMA: raise DecisionGateError(f"request.schema_version must equal {REQUEST_SCHEMA!r}")
    typ=text(raw.get("decision_type"),"request.decision_type",64)
    if typ not in DECISION_TYPES: raise DecisionGateError("request.decision_type must be one of "+", ".join(sorted(DECISION_TYPES)))
    rec=obj(raw.get("recommendation"),"request.recommendation"); keys(rec,{"action","rationale"},"request.recommendation")
    def rows(name,kind): return [row(v,f"request.{name}[{i}]",kind) for i,v in enumerate(arr(raw.get(name,[]),f"request.{name}"))]
    return {"schema_version":REQUEST_SCHEMA,"request_id":text(raw.get("request_id"),"request.request_id",256),"mailbox":email(raw.get("mailbox"),"request.mailbox"),"thread_id":text(raw.get("thread_id"),"request.thread_id",256),"inbound_event":event(raw.get("inbound_event"),"request.inbound_event"),"decision_type":typ,"buyer_scope":text(raw.get("buyer_scope"),"request.buyer_scope",320),"opportunity_id":text(raw.get("opportunity_id"),"request.opportunity_id",256),"prior_offers":rows("prior_offers","offer"),"prior_promises":rows("prior_promises","promise"),"evidenced_amounts":rows("evidenced_amounts","amount"),"deadlines":rows("deadlines","deadline"),"recommendation":{"action":text(rec.get("action"),"request.recommendation.action",1024),"rationale":text(rec.get("rationale"),"request.recommendation.rationale",4096)},"ruling_needed":text(raw.get("ruling_needed"),"request.ruling_needed",2048)}

def normalize_snapshot(raw):
    allowed={"schema_version","complete","mailbox","thread_id","captured_at","latest_inbound","latest_provider_event","history_digest","relationship_generation","relationship_disposition","relationship_state"}; keys(raw,allowed,"snapshot")
    if raw.get("schema_version")!=SNAPSHOT_SCHEMA: raise DecisionGateError(f"snapshot.schema_version must equal {SNAPSHOT_SCHEMA!r}")
    disp=text(raw.get("relationship_disposition"),"snapshot.relationship_disposition",32)
    if disp not in DISPOSITIONS: raise DecisionGateError("snapshot.relationship_disposition must be one of "+", ".join(sorted(DISPOSITIONS)))
    return {"schema_version":SNAPSHOT_SCHEMA,"complete":boolean(raw.get("complete"),"snapshot.complete"),"mailbox":email(raw.get("mailbox"),"snapshot.mailbox"),"thread_id":text(raw.get("thread_id"),"snapshot.thread_id",256),"captured_at":fmt(time(raw.get("captured_at"),"snapshot.captured_at")),"latest_inbound":event(raw.get("latest_inbound"),"snapshot.latest_inbound"),"latest_provider_event":event(raw.get("latest_provider_event"),"snapshot.latest_provider_event"),"history_digest":hex64(raw.get("history_digest"),"snapshot.history_digest"),"relationship_generation":integer(raw.get("relationship_generation"),"snapshot.relationship_generation",1,2**63-1),"relationship_disposition":disp,"relationship_state":text(raw.get("relationship_state"),"snapshot.relationship_state",128)}

def decision_key(r): return digest({"mailbox":r["mailbox"],"thread_id":r["thread_id"],"inbound_event_id":r["inbound_event"]["event_id"],"decision_type":r["decision_type"]})
def binding(s): return {k:s[k] for k in ("mailbox","thread_id","history_digest","relationship_generation","relationship_disposition","relationship_state","latest_inbound","latest_provider_event")}
def unsigned(b): return {k:v for k,v in b.items() if k!="receipt_digest"}
_brief_unsigned=unsigned

def prior(v,i):
    label=f"prior_briefs[{i}]"; o=obj(v,label)
    fields={"schema_version","decision_key","request_digest","provider_binding_digest","relationship_generation","compiled_at","decision","owner_alert_allowed","owner_alert_lease_key","side_effects_authorized","reasons","owner_brief_markdown","receipt_digest"}; keys(o,fields,label)
    if o.get("schema_version")!=BRIEF_SCHEMA: raise DecisionGateError(f"{label}.schema_version must equal {BRIEF_SCHEMA!r}")
    n={"schema_version":BRIEF_SCHEMA,"decision_key":hex64(o.get("decision_key"),label+".decision_key"),"request_digest":hex64(o.get("request_digest"),label+".request_digest"),"provider_binding_digest":hex64(o.get("provider_binding_digest"),label+".provider_binding_digest"),"relationship_generation":integer(o.get("relationship_generation"),label+".relationship_generation",1,2**63-1),"compiled_at":fmt(time(o.get("compiled_at"),label+".compiled_at")),"decision":text(o.get("decision"),label+".decision",64),"owner_alert_allowed":boolean(o.get("owner_alert_allowed"),label+".owner_alert_allowed"),"owner_alert_lease_key":text(o.get("owner_alert_lease_key"),label+".owner_alert_lease_key",160),"side_effects_authorized":boolean(o.get("side_effects_authorized"),label+".side_effects_authorized"),"reasons":[text(x,f"{label}.reasons[{j}]",512) for j,x in enumerate(arr(o.get("reasons"),label+".reasons"))],"owner_brief_markdown":text(o.get("owner_brief_markdown"),label+".owner_brief_markdown",16384,True),"receipt_digest":hex64(o.get("receipt_digest"),label+".receipt_digest")}
    if n["side_effects_authorized"]: raise DecisionGateError(f"{label}.side_effects_authorized must be false")
    if n["decision"] not in {READY,HOLD,DUPLICATE}: raise DecisionGateError(f"{label}.decision is invalid")
    if n["receipt_digest"]!=digest(unsigned(n)): raise DecisionGateError(f"{label}.receipt_digest does not match brief contents")
    return n

def money(n,c): return f"${n//100:,}.{n%100:02d} USD" if c=="USD" else f"{n} minor-units {c}"
def render(r,s):
    lines=[f"# Owner decision: {r['buyer_scope']} / {r['opportunity_id']}","",f"- Decision type: `{r['decision_type']}`",f"- Mailbox/thread: `{r['mailbox']}` / `{r['thread_id']}`",f"- Controlling inbound: `{r['inbound_event']['event_id']}` at {r['inbound_event']['observed_at']}",f"- Provider history digest: `{s['history_digest']}`",f"- Relationship generation/state: `{s['relationship_generation']}` / `{s['relationship_state']}`","","## Prior offers"]
    lines += [f"- `{x['offer_id']}` — {money(x['amount_minor'],x['currency'])} — {x['status']} — evidence `{x['evidence_event_id']}`" for x in r["prior_offers"]] or ["- None supplied."]
    lines += ["","## Prior promises"]+([f"- {x['summary']} — evidence `{x['evidence_event_id']}`" for x in r["prior_promises"]] or ["- None supplied."])
    lines += ["","## Evidenced amounts"]+([f"- {x['label']}: {money(x['amount_minor'],x['currency'])} — evidence `{x['evidence_event_id']}`" for x in r["evidenced_amounts"]] or ["- None supplied."])
    lines += ["","## Deadlines"]+([f"- {x['label']}: {x['deadline_at']} — evidence `{x['evidence_event_id']}`" for x in r["deadlines"]] or ["- None supplied."])
    lines += ["","## Recommendation",r["recommendation"]["action"],"",r["recommendation"]["rationale"],"","## Ruling needed",r["ruling_needed"],"","> Decision support only: no email/provider mutation, calendar commitment, scope/terms acceptance, payment capture, or revenue recognition. Any later outbound must reacquire current provider history and the canonical atomic send lease."]
    return "\n".join(lines)+"\n"

def compile_decision(request_raw,snapshot_raw,prior_briefs_raw=(),*,prior_ledger_complete=False,_now=None,max_snapshot_age_seconds=900,max_future_skew_seconds=300):
    r,s=normalize_request(request_raw),normalize_snapshot(snapshot_raw); ps=[prior(x,i) for i,x in enumerate(prior_briefs_raw)]
    now=(_now or datetime.now(timezone.utc)).astimezone(timezone.utc); age=integer(max_snapshot_age_seconds,"max_snapshot_age_seconds",0,604800); skew=integer(max_future_skew_seconds,"max_future_skew_seconds",0,86400)
    if type(prior_ledger_complete) is not bool: raise DecisionGateError("prior_ledger_complete must be a boolean")
    k,rd,pd=decision_key(r),digest(r),digest(binding(s)); reasons=[]
    if not prior_ledger_complete: reasons.append("OWNER_DECISION_LEDGER_INCOMPLETE")
    cap=time(s["captured_at"],"snapshot.captured_at"); lp=time(s["latest_provider_event"]["observed_at"],"latest_provider_event.observed_at"); li=time(s["latest_inbound"]["observed_at"],"latest_inbound.observed_at"); ri=time(r["inbound_event"]["observed_at"],"request.inbound_event.observed_at")
    if not s["complete"]: reasons.append("PROVIDER_HISTORY_INCOMPLETE")
    if (r["mailbox"],r["thread_id"])!=(s["mailbox"],s["thread_id"]): reasons.append("MAILBOX_THREAD_MISMATCH")
    if r["inbound_event"]!=s["latest_inbound"]: reasons.append("CONTROLLING_INBOUND_NOT_LATEST_INBOUND")
    if r["inbound_event"]!=s["latest_provider_event"]: reasons.append("NEWER_OR_DIFFERENT_PROVIDER_EVENT_EXISTS")
    if s["relationship_disposition"]!="ACTIONABLE": reasons.append("RELATIONSHIP_"+s["relationship_disposition"])
    if cap<lp: reasons.append("SNAPSHOT_CAPTURE_PRECEDES_LATEST_PROVIDER_EVENT")
    if li>lp: reasons.append("PROVIDER_CHRONOLOGY_INCONSISTENT")
    if ri>lp: reasons.append("REQUEST_INBOUND_AFTER_PROVIDER_HEAD")
    if now-cap>timedelta(seconds=age): reasons.append("PROVIDER_SNAPSHOT_STALE")
    cutoff=now+timedelta(seconds=skew)
    if cap>cutoff: reasons.append("SNAPSHOT_CAPTURE_IN_FUTURE")
    if max(lp,li,ri)>cutoff: reasons.append("PROVIDER_EVENT_IN_FUTURE")
    same=[x for x in ps if x["decision_key"]==k]; exact=[x for x in same if (x["request_digest"],x["provider_binding_digest"],x["relationship_generation"])==(rd,pd,s["relationship_generation"])]
    if any(x not in exact for x in same): reasons.append("EXISTING_DECISION_KEY_CONFLICT")
    if reasons: dec,allow=HOLD,False
    elif exact: dec,allow,reasons=DUPLICATE,False,["EXACT_DECISION_ALREADY_COMPILED"]
    else: dec,allow,reasons=READY,True,["CURRENT_COMPLETE_PROVIDER_SNAPSHOT","UNIQUE_OWNER_DECISION_KEY"]
    out={"schema_version":BRIEF_SCHEMA,"decision_key":k,"request_digest":rd,"provider_binding_digest":pd,"relationship_generation":s["relationship_generation"],"compiled_at":fmt(now),"decision":dec,"owner_alert_allowed":allow,"owner_alert_lease_key":f"owner-decision-lease/v1/{k}","side_effects_authorized":False,"reasons":reasons,"owner_brief_markdown":render(r,s)}; out["receipt_digest"]=digest(out); return out

def load_ledger(path):
    if path is None: return False,[]
    o=parse_json_bytes(path.read_bytes(),"prior_briefs"); keys(o,{"schema_version","complete","briefs"},"prior_briefs")
    if o.get("schema_version")!=BRIEF_SET_SCHEMA: raise DecisionGateError(f"prior_briefs.schema_version must equal {BRIEF_SET_SCHEMA!r}")
    return boolean(o.get("complete"),"prior_briefs.complete"),arr(o.get("briefs"),"prior_briefs.briefs")

def main(argv=None):
    p=argparse.ArgumentParser(description="Compile one deduplicated, provider-current owner commercial decision brief."); p.add_argument("--request",required=True,type=Path); p.add_argument("--provider-snapshot",required=True,type=Path); p.add_argument("--prior-briefs",type=Path); a=p.parse_args(argv)
    try:
        c,ps=load_ledger(a.prior_briefs); out=compile_decision(parse_json_bytes(a.request.read_bytes(),"request"),parse_json_bytes(a.provider_snapshot.read_bytes(),"provider_snapshot"),ps,prior_ledger_complete=c)
    except (DecisionGateError,OSError) as e: print(f"owner-decision-gate: {e}",file=sys.stderr); return 2
    sys.stdout.buffer.write(canonical_bytes(out)); return 0 if out["decision"]==READY else 3 if out["decision"]==DUPLICATE else 4

if __name__=="__main__": raise SystemExit(main())