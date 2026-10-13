#!/usr/bin/env python3
"""TurnBench: deterministic acceptance receipts for AssemblyAI Voice Agent traces."""
from __future__ import annotations
import argparse, hashlib, json, math, re
from pathlib import Path
from typing import Any

SCENARIO_SCHEMA="turnbench-scenario/v1"; TRACE_SCHEMA="turnbench-trace/v1"; RECEIPT_SCHEMA="turnbench-receipt/v1"
PROVIDER="assemblyai-voice-agent-api"; MAX_FILE_BYTES=2_000_000; MAX_EVENTS=20_000
SAFE_ID=re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$"); SHA256=re.compile(r"^[0-9a-f]{64}$")
EVENTS={"harness.session.configured","session.ready","session.updated","session.ended","input.speech.started","input.speech.stopped","transcript.user.delta","transcript.user","reply.started","reply.audio","transcript.agent.delta","transcript.agent","reply.done","tool.call","tool.result","session.error"}


def _pairs(pairs):
    out={}
    for k,v in pairs:
        if k in out: raise ValueError(f"duplicate JSON key: {k}")
        out[k]=v
    return out

def _constant(v): raise ValueError(f"non-finite JSON number: {v}")
def loads_strict(data:bytes)->Any:
    if len(data)>MAX_FILE_BYTES: raise ValueError("input exceeds size bound")
    try: text=data.decode("utf-8")
    except UnicodeDecodeError as e: raise ValueError("input is not UTF-8") from e
    return json.loads(text,object_pairs_hook=_pairs,parse_constant=_constant)
def _finite(v):
    if isinstance(v,float) and not math.isfinite(v): raise ValueError("non-finite number")
    if isinstance(v,list):
        for x in v:_finite(x)
    elif isinstance(v,dict):
        for k,x in v.items():
            if not isinstance(k,str): raise ValueError("JSON object key is not a string")
            _finite(x)
def canonical_bytes(v): _finite(v); return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def sha256_bytes(b): return hashlib.sha256(b).hexdigest()

def _expect_exact_keys(o,required,optional=set(),where="object"):
    if not isinstance(o,dict): raise ValueError(f"{where} must be an object")
    miss=required-set(o); extra=set(o)-required-optional
    if miss: raise ValueError(f"{where} missing keys: {sorted(miss)}")
    if extra: raise ValueError(f"{where} unknown keys: {sorted(extra)}")
    return o
def _expect_str(v,where,max_len=4096):
    if not isinstance(v,str) or not v or len(v)>max_len: raise ValueError(f"{where} must be a string")
    return v
def _expect_id(v,where):
    s=_expect_str(v,where,96)
    if not SAFE_ID.fullmatch(s): raise ValueError(f"{where} is not a safe identifier")
    return s
def _expect_int(v,where,lo,hi):
    if isinstance(v,bool) or not isinstance(v,int): raise ValueError(f"{where} must be an integer")
    if not lo<=v<=hi: raise ValueError(f"{where} out of range")
    return v
def _expect_bool(v,where):
    if not isinstance(v,bool): raise ValueError(f"{where} must be a boolean")
    return v
def _sha(v,where):
    s=_expect_str(v,where,64)
    if not SHA256.fullmatch(s): raise ValueError(f"{where} must be lowercase SHA-256")
    return s


def validate_scenario(raw):
    s=_expect_exact_keys(raw,{"schema","scenario_id","title","session_contract","assertions"},where="scenario")
    if s["schema"]!=SCENARIO_SCHEMA: raise ValueError("unsupported scenario schema")
    _expect_id(s["scenario_id"],"scenario.scenario_id"); _expect_str(s["title"],"scenario.title",180)
    c=_expect_exact_keys(s["session_contract"],{"resolved_config_sha256","min_silence_ms","max_silence_ms"},where="scenario.session_contract")
    _sha(c["resolved_config_sha256"],"scenario.session_contract.resolved_config_sha256")
    mn=_expect_int(c["min_silence_ms"],"scenario.session_contract.min_silence_ms",50,10000); mx=_expect_int(c["max_silence_ms"],"scenario.session_contract.max_silence_ms",50,10000)
    if mn>=mx: raise ValueError("min_silence_ms must be less than max_silence_ms")
    a=_expect_exact_keys(s["assertions"],{"max_turn_start_latency_ms","max_interrupt_cancel_latency_ms","max_tool_call_latency_ms","min_user_turns","min_interruptions","require_clean_session_end","required_tool_calls","forbidden_error_codes"},where="scenario.assertions")
    for k,hi in (("max_turn_start_latency_ms",120000),("max_interrupt_cancel_latency_ms",60000),("max_tool_call_latency_ms",120000)): _expect_int(a[k],f"scenario.assertions.{k}",1,hi)
    _expect_int(a["min_user_turns"],"scenario.assertions.min_user_turns",0,1000); _expect_int(a["min_interruptions"],"scenario.assertions.min_interruptions",0,1000); _expect_bool(a["require_clean_session_end"],"scenario.assertions.require_clean_session_end")
    if not isinstance(a["required_tool_calls"],list) or len(a["required_tool_calls"])>64: raise ValueError("required_tool_calls must be a bounded array")
    names=[]
    for i,r in enumerate(a["required_tool_calls"]):
        _expect_exact_keys(r,{"name","required_argument_keys","must_follow_user_text"},where=f"required_tool_calls[{i}]"); names.append(_expect_id(r["name"],f"required_tool_calls[{i}].name"))
        if not isinstance(r["required_argument_keys"],list) or len(set(r["required_argument_keys"]))!=len(r["required_argument_keys"]): raise ValueError("duplicate required_argument_keys")
        for k in r["required_argument_keys"]:_expect_id(k,"required_argument_keys")
        p=_expect_str(r["must_follow_user_text"],"must_follow_user_text",512)
        if p!=p.strip() or p!=p.lower(): raise ValueError("must_follow_user_text must be lowercase and trimmed")
    if len(names)!=len(set(names)): raise ValueError("duplicate required tool name")
    if not isinstance(a["forbidden_error_codes"],list) or len(a["forbidden_error_codes"])>64: raise ValueError("forbidden_error_codes must be a bounded array")
    if len(a["forbidden_error_codes"])!=len(set(a["forbidden_error_codes"])): raise ValueError("duplicate forbidden_error_codes")
    for code in a["forbidden_error_codes"]: _expect_id(code,"forbidden_error_codes")
    return s


def _event(e,i):
    _expect_exact_keys(e,{"seq","at_ms","type","data"},where=f"event[{i}]"); _expect_int(e["seq"],"seq",0,10_000_000); _expect_int(e["at_ms"],"at_ms",0,86_400_000)
    t=_expect_str(e["type"],"type",64)
    if t not in EVENTS: raise ValueError(f"event[{i}] unknown type: {t}")
    d=e["data"]
    if not isinstance(d,dict): raise ValueError(f"event[{i}].data must be an object")
    if t=="harness.session.configured":
        _expect_exact_keys(d,{"resolved_config_sha256","min_silence_ms","max_silence_ms"}); _sha(d["resolved_config_sha256"],"resolved_config_sha256"); mn=_expect_int(d["min_silence_ms"],"min_silence_ms",50,10000); mx=_expect_int(d["max_silence_ms"],"max_silence_ms",50,10000)
        if mn>=mx: raise ValueError("configured min_silence_ms must be less than max_silence_ms")
    elif t in {"session.ready","session.updated"}: _expect_exact_keys(d,{"resolved_config_sha256"}); _sha(d["resolved_config_sha256"],"resolved_config_sha256")
    elif t=="session.ended": _expect_exact_keys(d,{"clean"}); _expect_bool(d["clean"],"clean")
    elif t in {"input.speech.started","input.speech.stopped","reply.audio"}: _expect_exact_keys(d,set())
    elif t in {"transcript.user.delta","transcript.user"}: _expect_exact_keys(d,{"item_id","text"}); _expect_id(d["item_id"],"item_id"); _expect_str(d["text"],"text",12000)
    elif t=="reply.started": _expect_exact_keys(d,{"reply_id","item_id"}); _expect_id(d["reply_id"],"reply_id"); _expect_id(d["item_id"],"item_id")
    elif t=="transcript.agent.delta": _expect_exact_keys(d,{"reply_id","item_id","delta"}); _expect_id(d["reply_id"],"reply_id"); _expect_id(d["item_id"],"item_id"); _expect_str(d["delta"],"delta",512)
    elif t=="transcript.agent": _expect_exact_keys(d,{"reply_id","item_id","text","interrupted"}); _expect_id(d["reply_id"],"reply_id"); _expect_id(d["item_id"],"item_id"); _expect_str(d["text"],"text",12000); _expect_bool(d["interrupted"],"interrupted")
    elif t=="reply.done":
        _expect_exact_keys(d,{"reply_id","status"}); _expect_id(d["reply_id"],"reply_id")
        if d["status"] not in {"completed","interrupted","failed"}: raise ValueError("reply.done status invalid")
    elif t=="tool.call":
        _expect_exact_keys(d,{"call_id","name","arguments"}); _expect_id(d["call_id"],"call_id"); _expect_id(d["name"],"name")
        if not isinstance(d["arguments"],dict): raise ValueError("tool.call arguments must be an object")
        _finite(d["arguments"])
    elif t=="tool.result": _expect_exact_keys(d,{"call_id","is_error"}); _expect_id(d["call_id"],"call_id"); _expect_bool(d["is_error"],"is_error")
    elif t=="session.error": _expect_exact_keys(d,{"code"}); _expect_id(d["code"],"code")
    return e


def validate_trace(raw):
    t=_expect_exact_keys(raw,{"schema","scenario_id","provider","evidence_class","events"},where="trace")
    if t["schema"]!=TRACE_SCHEMA or t["provider"]!=PROVIDER: raise ValueError("trace schema/provider mismatch")
    _expect_id(t["scenario_id"],"trace.scenario_id")
    if t["evidence_class"] not in {"SYNTHETIC","LIVE_CAPTURE_UNVERIFIED"}: raise ValueError("trace evidence_class invalid")
    if not isinstance(t["events"],list) or not t["events"] or len(t["events"])>MAX_EVENTS: raise ValueError("events must be a non-empty bounded array")
    seq=ms=-1
    for i,e in enumerate(t["events"]):
        _event(e,i)
        if e["seq"]<=seq: raise ValueError("event sequence is not strictly increasing")
        if e["at_ms"]<ms: raise ValueError("event time regressed")
        seq=e["seq"]; ms=e["at_ms"]
    return t


def evaluate(scenario,trace):
    s=validate_scenario(scenario); t=validate_trace(trace)
    if s["scenario_id"]!=t["scenario_id"]: raise ValueError("scenario/trace scenario_id mismatch")
    e=t["events"]; a=s["assertions"]; c=s["session_contract"]; f=[]
    def add(code,passed,detail): f.append({"code":code,"passed":bool(passed),"detail":detail})
    cfg=[x for x in e if x["type"]=="harness.session.configured"]; resolved=[x for x in e if x["type"] in {"session.ready","session.updated"}]; ready=[x for x in resolved if x["type"]=="session.ready"]; updates=[x for x in resolved if x["type"]=="session.updated"]
    ok=len(cfg)==1 and bool(ready) and cfg[0]["data"]==c and all(x["data"]["resolved_config_sha256"]==c["resolved_config_sha256"] for x in resolved)
    add("CONFIG_BOUND",ok,{"configured_count":len(cfg),"ready_count":len(ready),"updated_count":len(updates)})
    errs=[x["data"]["code"] for x in e if x["type"]=="session.error"]; bad=sorted(set(errs)&set(a["forbidden_error_codes"])); add("NO_FORBIDDEN_PROVIDER_ERROR",not bad,{"forbidden_seen":bad})
    users=[x for x in e if x["type"]=="transcript.user"]; add("MIN_USER_TURNS",len(users)>=a["min_user_turns"],{"observed":len(users),"required":a["min_user_turns"]})
    lats=[]; missing=[]
    for u in users:
        starts=[x for x in e if x["type"]=="reply.started" and x["data"]["item_id"]==u["data"]["item_id"] and x["at_ms"]>=u["at_ms"]]
        if not starts: missing.append(u["data"]["item_id"])
        else: lats.append(starts[0]["at_ms"]-u["at_ms"])
    add("TURN_START_LATENCY",not missing and all(x<=a["max_turn_start_latency_ms"] for x in lats),{"latencies_ms":lats,"max_allowed_ms":a["max_turn_start_latency_ms"],"unmatched_items":missing})
    done={x["data"]["reply_id"]:x for x in e if x["type"]=="reply.done"}; atr={x["data"]["reply_id"]:x for x in e if x["type"]=="transcript.agent"}; active=None; ints=[]
    for x in e:
        if x["type"]=="reply.started": active=x
        elif x["type"]=="reply.done" and active and x["data"]["reply_id"]==active["data"]["reply_id"]: active=None
        elif x["type"]=="input.speech.started" and active:
            rid=active["data"]["reply_id"]; d=done.get(rid); tr=atr.get(rid); lat=None if not d else d["at_ms"]-x["at_ms"]
            passed=bool(d and d["at_ms"]>=x["at_ms"] and d["data"]["status"]=="interrupted" and lat<=a["max_interrupt_cancel_latency_ms"] and tr and tr["data"]["interrupted"] is True)
            ints.append({"reply_id":rid,"latency_ms":lat,"passed":passed})
    add("BARGE_IN_CANCELLATION",len(ints)>=a["min_interruptions"] and all(x["passed"] for x in ints),{"observed_interruptions":ints,"observed_count":len(ints),"required_count":a["min_interruptions"],"max_allowed_ms":a["max_interrupt_cancel_latency_ms"]})
    td=[]
    for req in a["required_tool_calls"]:
        calls=[x for x in e if x["type"]=="tool.call" and x["data"]["name"]==req["name"]]; row={"name":req["name"],"passed":False,"latency_ms":None,"missing_argument_keys":[]}
        if calls:
            call=calls[0]; wit=[u for u in users if u["at_ms"]<=call["at_ms"] and req["must_follow_user_text"] in u["data"]["text"].lower()]
            if wit:
                lat=call["at_ms"]-wit[-1]["at_ms"]; miss=sorted(set(req["required_argument_keys"])-set(call["data"]["arguments"])); row.update(latency_ms=lat,missing_argument_keys=miss,passed=not miss and lat<=a["max_tool_call_latency_ms"])
        td.append(row)
    add("TOOL_CAUSALITY",all(x["passed"] for x in td),{"tools":td})
    ends=[x for x in e if x["type"]=="session.ended"]; endok=(len(ends)==1 and ends[0]["data"]["clean"] is True) if a["require_clean_session_end"] else len(ends)<=1; add("SESSION_END",endok,{"end_events":len(ends),"clean_required":a["require_clean_session_end"]})
    body={"schema":RECEIPT_SCHEMA,"scenario_id":s["scenario_id"],"provider":PROVIDER,"decision":"PASS" if all(x["passed"] for x in f) else "FAIL","live_provider_performance_proven":False,"provider_origin_status":"SYNTHETIC" if t["evidence_class"]=="SYNTHETIC" else "LIVE_CAPTURE_UNVERIFIED","source":{"scenario_sha256":sha256_bytes(canonical_bytes(s)),"trace_sha256":sha256_bytes(canonical_bytes(t)),"trace_evidence_class":t["evidence_class"]},"findings":f}
    return {**body,"receipt_sha256":sha256_bytes(canonical_bytes(body))}

def verify_receipt(s,t,r): return canonical_bytes(evaluate(s,t))==canonical_bytes(r)
def _read_regular(p):
    p=Path(p)
    if p.is_symlink(): raise ValueError(f"symlink input refused: {p}")
    if not p.is_file(): raise ValueError(f"input must be a regular file: {p}")
    return p.read_bytes()
def _load(p): return loads_strict(_read_regular(p))
def _write_new(p,data):
    p=Path(p)
    if p.exists() or p.is_symlink(): raise ValueError(f"output already exists: {p}")
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("xb") as h:h.write(data);h.flush()

def main(argv=None):
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True)
    for n in ("evaluate","verify"):
        q=sub.add_parser(n); q.add_argument("--scenario",required=True); q.add_argument("--trace",required=True); q.add_argument("--out" if n=="evaluate" else "--receipt",required=True)
    ns=p.parse_args(argv)
    try:
        s=validate_scenario(_load(ns.scenario)); t=validate_trace(_load(ns.trace))
        if ns.cmd=="evaluate":
            r=evaluate(s,t); _write_new(ns.out,canonical_bytes(r)+b"\n"); print(r["decision"]); return 0 if r["decision"]=="PASS" else 2
        ok=verify_receipt(s,t,_load(ns.receipt)); print("VALID" if ok else "INVALID"); return 0 if ok else 3
    except (OSError,ValueError,json.JSONDecodeError) as e: print(f"ERROR: {e}"); return 64
if __name__=="__main__": raise SystemExit(main())
