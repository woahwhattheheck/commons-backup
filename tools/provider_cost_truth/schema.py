"""Bounded request/evidence schema validation for provider cost truth."""
from __future__ import annotations
from typing import Any, Mapping
from .codec import AUTHORITIES,KINDS,REQUEST_SCHEMA,SCOPES,SNAPSHOT_SCHEMA,GateError,_CURRENCY_RE,_SHA256_RE,_parse_ts,_require_bool,_require_exact_keys,_require_minor,_require_text

def _target_scope(r: Mapping[str,Any])->str:
    if r["session_id"] is not None:return "SESSION"
    if r["model"] is not None:return "MODEL"
    if r["product"] is not None:return "PRODUCT"
    return "ACCOUNT"

def _scope_identity(e: Mapping[str,Any])->tuple[Any,...]:
    s=e["scope"]
    if s=="ACCOUNT":return(e["provider"],e["account_id"])
    if s=="PRODUCT":return(e["provider"],e["account_id"],e["product"])
    if s=="MODEL":return(e["provider"],e["account_id"],e["product"],e["model"])
    return(e["provider"],e["account_id"],e["product"],e["model"],e["session_id"])

def _request_identity(r: Mapping[str,Any],s:str)->tuple[Any,...]:
    if s=="ACCOUNT":return(r["provider"],r["account_id"])
    if s=="PRODUCT":return(r["provider"],r["account_id"],r["product"])
    if s=="MODEL":return(r["provider"],r["account_id"],r["product"],r["model"])
    return(r["provider"],r["account_id"],r["product"],r["model"],r["session_id"])

def _validate_request(r:Any,_exact=_require_exact_keys,_text=_require_text,_bool=_require_bool,_schema=REQUEST_SCHEMA)->dict[str,Any]:
    if not isinstance(r,dict):raise GateError("request must be an object")
    keys={"schema","provider","account_id","product","model","session_id","free_only"};_exact(r,keys,"request")
    if r["schema"]!=_schema:raise GateError(f"unsupported request schema: {r['schema']!r}")
    _text(r["provider"],"request.provider");_text(r["account_id"],"request.account_id")
    _text(r["product"],"request.product",nullable=True);_text(r["model"],"request.model",nullable=True);_text(r["session_id"],"request.session_id",nullable=True);_bool(r["free_only"],"request.free_only")
    if r["model"] is not None and r["product"] is None:raise GateError("request.model requires request.product")
    if r["session_id"] is not None and r["model"] is None:raise GateError("request.session_id requires request.model")
    return dict(r)

def _validate_event(e:Any,r:Mapping[str,Any],i:int,_exact=_require_exact_keys,_text=_require_text,_minor=_require_minor,_parse=_parse_ts,_scopes=SCOPES,_kinds=KINDS,_authorities=AUTHORITIES,_currency_re=_CURRENCY_RE,_sha_re=_SHA256_RE)->dict[str,Any]:
    if not isinstance(e,dict):raise GateError(f"evidence[{i}] must be an object")
    keys={"event_id","scope","provider","account_id","product","model","session_id","kind","amount_minor","currency","event_at_utc","observed_at_utc","valid_until_utc","source_ref","source_sha256","authority"};_exact(e,keys,f"evidence[{i}]")
    _text(e["event_id"],f"evidence[{i}].event_id")
    if e["scope"] not in _scopes:raise GateError(f"evidence[{i}].scope must be one of {_scopes}")
    for k in("provider","account_id"):_text(e[k],f"evidence[{i}].{k}")
    for k in("product","model","session_id"):_text(e[k],f"evidence[{i}].{k}",nullable=True)
    if e["provider"]!=r["provider"] or e["account_id"]!=r["account_id"]:raise GateError(f"evidence[{i}] provider/account identity transplant")
    s=e["scope"]
    if s=="ACCOUNT" and any(e[k] is not None for k in("product","model","session_id")):raise GateError(f"evidence[{i}] ACCOUNT scope must not carry lower-scope identifiers")
    if s=="PRODUCT" and(e["product"] is None or e["model"] is not None or e["session_id"] is not None):raise GateError(f"evidence[{i}] PRODUCT scope identity is malformed")
    if s=="MODEL" and(e["product"] is None or e["model"] is None or e["session_id"] is not None):raise GateError(f"evidence[{i}] MODEL scope identity is malformed")
    if s=="SESSION" and(e["product"] is None or e["model"] is None or e["session_id"] is None):raise GateError(f"evidence[{i}] SESSION scope identity is malformed")
    if e["kind"] not in _kinds:raise GateError(f"evidence[{i}].kind must be one of {_kinds}")
    amount=_minor(e["amount_minor"],f"evidence[{i}].amount_minor");currency=_text(e["currency"],f"evidence[{i}].currency")
    if not _currency_re.fullmatch(currency):raise GateError(f"evidence[{i}].currency must be three uppercase ASCII letters")
    event_at=_parse(e["event_at_utc"],f"evidence[{i}].event_at_utc");observed_at=_parse(e["observed_at_utc"],f"evidence[{i}].observed_at_utc")
    if observed_at<event_at:raise GateError(f"evidence[{i}] observed_at precedes event_at")
    valid=None
    if e["valid_until_utc"] is not None:
        valid=_parse(e["valid_until_utc"],f"evidence[{i}].valid_until_utc")
        if valid<event_at:raise GateError(f"evidence[{i}] valid_until precedes event_at")
    if e["kind"] in("ZERO_COST_CONFIRMED","PRICE_QUOTE") and valid is None:raise GateError(f"evidence[{i}] {e['kind']} requires valid_until_utc")
    if e["kind"]=="ZERO_COST_CONFIRMED" and amount!=0:raise GateError(f"evidence[{i}] ZERO_COST_CONFIRMED must have amount_minor=0")
    if e["kind"] in("CHARGE_PAID","CHARGE_FAILED") and amount<=0:raise GateError(f"evidence[{i}] {e['kind']} must have positive amount_minor")
    _text(e["source_ref"],f"evidence[{i}].source_ref");sha=_text(e["source_sha256"],f"evidence[{i}].source_sha256")
    if not _sha_re.fullmatch(sha):raise GateError(f"evidence[{i}].source_sha256 must be lowercase SHA-256 hex")
    if e["authority"] not in _authorities:raise GateError(f"evidence[{i}].authority must be one of {_authorities}")
    return dict(e)

def validate_snapshot(s:Any,_exact=_require_exact_keys,_req=_validate_request,_event=_validate_event,_schema=SNAPSHOT_SCHEMA)->dict[str,Any]:
    if not isinstance(s,dict):raise GateError("snapshot must be an object")
    _exact(s,{"schema","request","evidence"},"snapshot")
    if s["schema"]!=_schema:raise GateError(f"unsupported snapshot schema: {s['schema']!r}")
    req=_req(s["request"]);rows=s["evidence"]
    if not isinstance(rows,list):raise GateError("snapshot.evidence must be an array")
    if len(rows)>500:raise GateError("snapshot.evidence exceeds 500-event bound")
    out=[];seen=set()
    for i,raw in enumerate(rows):
        e=_event(raw,req,i)
        if e["event_id"] in seen:raise GateError(f"duplicate evidence event_id: {e['event_id']}")
        seen.add(e["event_id"]);out.append(e)
    # Evidence is a set keyed by unique event_id for semantic purposes.
    # Canonicalize only after validation/duplicate detection so receipt and
    # snapshot digests are invariant to caller list permutation.
    out.sort(key=lambda event: event["event_id"])
    return{"schema":_schema,"request":req,"evidence":out}
