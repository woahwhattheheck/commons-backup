"""Process-current receipt sealing and historical integrity verification."""
from __future__ import annotations
from datetime import datetime as _DateTime, timezone as _Timezone
from typing import Any
from .codec import IMPLEMENTATION_CONTRACT,RECEIPT_SCHEMA,SCOPES,STATES,GateError,_SHA256_RE,_format_ts,_parse_ts,_require_bool,_require_exact_keys,_require_text,_sha256_value
from .evaluator import _evaluate_snapshot


def _validate_receipt_shape(receipt:Any,_exact=_require_exact_keys,_parse=_parse_ts,_text=_require_text,_bool=_require_bool,_hash=_sha256_value,_schema=RECEIPT_SCHEMA,_contract=IMPLEMENTATION_CONTRACT,_states=STATES,_scopes=SCOPES,_sha_re=_SHA256_RE)->dict[str,Any]:
    if not isinstance(receipt,dict):raise GateError("receipt must be an object")
    keys={"schema","implementation_contract","evaluation_mode","evaluated_at_utc","state","target_scope","request_sha256","snapshot_sha256","trusted_provider_evidence_manifest_sha256","controlling_event_ids","account_billing_event_ids","reasons","free_only_requested","free_only_satisfied","provider_session_authorized","spend_authorized","external_side_effects_authorized","receipt_sha256"};_exact(receipt,keys,"receipt")
    if receipt["schema"]!=_schema or receipt["implementation_contract"]!=_contract:raise GateError("unsupported receipt contract")
    if receipt["evaluation_mode"]!="CURRENT_PROCESS_UTC":raise GateError("unsupported receipt evaluation mode")
    _parse(receipt["evaluated_at_utc"],"receipt.evaluated_at_utc")
    if receipt["state"] not in _states:raise GateError("receipt.state is invalid")
    if receipt["target_scope"] not in _scopes:raise GateError("receipt.target_scope is invalid")
    for key in("request_sha256","snapshot_sha256","trusted_provider_evidence_manifest_sha256","receipt_sha256"):
        value=_text(receipt[key],f"receipt.{key}")
        if not _sha_re.fullmatch(value):raise GateError(f"receipt.{key} is not lowercase SHA-256 hex")
    for key in("controlling_event_ids","account_billing_event_ids","reasons"):
        value=receipt[key]
        if not isinstance(value,list):raise GateError(f"receipt.{key} must be an array of non-empty strings")
        normalized=[]
        for i,item in enumerate(value):normalized.append(_text(item,f"receipt.{key}[{i}]"))
        if normalized!=sorted(set(normalized)):raise GateError(f"receipt.{key} must be sorted and duplicate-free")
    for key in("free_only_requested","free_only_satisfied","provider_session_authorized","spend_authorized","external_side_effects_authorized"):_bool(receipt[key],f"receipt.{key}")
    if receipt["provider_session_authorized"] or receipt["spend_authorized"] or receipt["external_side_effects_authorized"]:raise GateError("receipt authority ceiling violated")
    if receipt["free_only_satisfied"]!=(receipt["free_only_requested"] and receipt["state"]=="ZERO_COST_VERIFIED"):raise GateError("receipt free_only_satisfied is semantically inconsistent")
    unsigned=dict(receipt);claimed=unsigned.pop("receipt_sha256")
    if _hash(unsigned)!=claimed:raise GateError("receipt_sha256 mismatch")
    return dict(receipt)


def _construct_api(_evaluate=_evaluate_snapshot,_clock_cls:type[_DateTime]=_DateTime,_utc=_Timezone.utc,_validator=_validate_receipt_shape,_parse=_parse_ts,_format=_format_ts,_hash=_sha256_value,_schema=RECEIPT_SCHEMA,_contract=IMPLEMENTATION_CONTRACT,_error=GateError):
    def _seal(snapshot:Any,now:_DateTime)->dict[str,Any]:
        receipt={"schema":_schema,"implementation_contract":_contract,"evaluation_mode":"CURRENT_PROCESS_UTC","evaluated_at_utc":_format(now),**_evaluate(snapshot,now)};receipt["receipt_sha256"]=_hash(receipt);return receipt
    def _compile_current(snapshot:Any)->dict[str,Any]:
        return _seal(snapshot,_clock_cls.now(_utc).replace(microsecond=0))
    def _verify_receipt(snapshot:Any,receipt:Any)->bool:
        checked=_validator(receipt);at=_parse(checked["evaluated_at_utc"],"receipt.evaluated_at_utc")
        if _seal(snapshot,at)!=checked:raise _error("receipt semantic replay mismatch")
        return True
    return _compile_current,_verify_receipt


compile_current,verify_receipt=_construct_api()
# Eliminate the ordinary module-global caller-time CURRENT_PROCESS_UTC sealer.
del _construct_api
