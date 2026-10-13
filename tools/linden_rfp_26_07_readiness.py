#!/usr/bin/env python3
"""Fail-closed Linden RFP 26-07 readiness compiler.

Local JSON can describe an internal candidate but cannot authenticate the
controlling portal package, owner authorization, or Muse election. Terminal
readiness therefore stays false until a separately reviewed provider boundary
exists.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

SOURCE_SCHEMA="commons/procurement-source-register/v1"
STATE_SCHEMA="commons/procurement-readiness-state/v1"
REPORT_SCHEMA="commons/procurement-readiness-report/v2"
PACKAGE_SOURCE_ID="controlling_rfp_package_26_07"
SOLICITATION_ID="26-07"
AGENCY="Housing Authority of the City of Linden"
TITLE="AI Automation, Resident Communication & Operational Support Services"
PORTAL_URL="https://ha.internationaleprocurement.com/"
QUESTIONS_DEADLINE="2026-09-21T15:30:00-04:00"
PROPOSAL_DEADLINE="2026-10-09T14:30:00-04:00"
PACKAGE_AUTH_BLOCKER="provider.controlling_package_authentication_unavailable"
MUSE_AUTH_BLOCKER="provider.muse_election_authentication_unavailable"
OWNER_AUTH_BLOCKER="provider.owner_authorization_authentication_unavailable"
SHA256_RE=re.compile(r"^[0-9a-f]{64}$")
MAX_JSON_BYTES=1_048_576

PACKAGE_BOOL_GATES=("addenda_current","requirements_extracted","evaluation_extracted","forms_extracted","insurance_extracted","contract_terms_extracted","pricing_fields_mapped","security_privacy_extracted")
PORTAL_BOOL_GATES=("vendor_registration_verified","legal_company_identity_verified","authorized_site_administrator_verified","authorized_agent_for_vendor_agreement_verified","company_information_truthfulness_attested","submission_session_verified")
RESPONSE_BOOL_GATES=("minimum_qualifications_satisfied","required_references_satisfied","required_staffing_satisfied","insurance_satisfied","mandatory_forms_complete","technical_response_complete","pricing_complete","package_addenda_acknowledged")
SUBMISSION_AUTHORITY_GATES=("owner_authorized_pricing_commitment","owner_authorized_submission")
REGISTRATION_AUTHORITY_GATES=("owner_authorized_portal_registration",)
AUTHORITY_KEYS={"owner_authorized_portal_registration","owner_authorized_buyer_question","owner_authorized_pricing_commitment","owner_authorized_submission","muse_outbound_clearance"}
PACKAGE_KEYS={"status","sha256",*PACKAGE_BOOL_GATES}
PORTAL_KEYS={"support_route_conflict_resolved",*PORTAL_BOOL_GATES}
RESPONSE_KEYS=set(RESPONSE_BOOL_GATES)
DEADLINE_KEYS={"questions_deadline","proposal_deadline"}

class ReadinessError(ValueError): pass

def _pairs(pairs:Iterable[Tuple[str,Any]])->Dict[str,Any]:
    out={}
    for k,v in pairs:
        if k in out: raise ReadinessError("duplicate JSON key: %s"%k)
        out[k]=v
    return out

def _canonical(v:Any)->bytes:
    return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def _sha(v:Any)->str: return hashlib.sha256(_canonical(v)).hexdigest()

def load_json_bytes(raw:bytes)->Dict[str,Any]:
    if type(raw) is not bytes: raise ReadinessError("JSON input must be bytes")
    if len(raw)>MAX_JSON_BYTES: raise ReadinessError("JSON input exceeds 1 MiB")
    try:
        v=json.loads(raw.decode("utf-8"),object_pairs_hook=_pairs,parse_constant=lambda x:(_ for _ in ()).throw(ReadinessError("non-finite JSON constant: %s"%x)))
    except (UnicodeDecodeError,json.JSONDecodeError) as e:
        raise ReadinessError("invalid UTF-8 JSON: %s"%e) from e
    if type(v) is not dict: raise ReadinessError("top-level JSON must be an object")
    return v

def load_json(path:Path)->Dict[str,Any]: return load_json_bytes(path.read_bytes())

def _dict(v:Any,n:str)->Dict[str,Any]:
    if type(v) is not dict: raise ReadinessError("%s must be an object"%n)
    return v

def _list(v:Any,n:str)->List[Any]:
    if type(v) is not list: raise ReadinessError("%s must be a list"%n)
    return v

def _bool(v:Any,n:str)->bool:
    if type(v) is not bool: raise ReadinessError("%s must be a JSON boolean"%n)
    return v

def _dt(v:Any,n:str)->datetime:
    if type(v) is not str: raise ReadinessError("%s must be an ISO-8601 string"%n)
    try: d=datetime.fromisoformat(v)
    except ValueError as e: raise ReadinessError("%s must be valid ISO-8601"%n) from e
    if d.tzinfo is None or d.utcoffset() is None: raise ReadinessError("%s must include an explicit UTC offset"%n)
    return d

def _keys(v:Dict[str,Any],expected:set[str],n:str)->None:
    if set(v)!=expected: raise ReadinessError("%s keys changed"%n)

def validate_source_register(source:Dict[str,Any])->Dict[str,Any]:
    if source.get("schema")!=SOURCE_SCHEMA: raise ReadinessError("unexpected source-register schema")
    sol=_dict(source.get("solicitation"),"solicitation")
    if (sol.get("agency"),sol.get("solicitation_id"),sol.get("title"))!=(AGENCY,SOLICITATION_ID,TITLE): raise ReadinessError("solicitation identity changed")
    rows=_list(source.get("sources"),"sources")
    if len(rows)>64: raise ReadinessError("too many source rows")
    by_id={}
    for i,raw in enumerate(rows):
        row=_dict(raw,"sources[%d]"%i); sid=row.get("source_id")
        if type(sid) is not str or not sid: raise ReadinessError("source_id must be non-empty text")
        if sid in by_id: raise ReadinessError("duplicate source_id: %s"%sid)
        by_id[sid]=row
    pkg=by_id.get(PACKAGE_SOURCE_ID)
    if pkg is None: raise ReadinessError("controlling package source is missing")
    if (pkg.get("kind"),pkg.get("url"),pkg.get("acquisition"),pkg.get("controls_package_requirements"))!=("CONTROLLING_RFP_PACKAGE",PORTAL_URL,"REGISTERED_VENDOR_PORTAL_REQUIRED",True): raise ReadinessError("controlling package boundary changed")
    status,sha=pkg.get("status"),pkg.get("sha256")
    if status=="MISSING_PACKAGE":
        if sha is not None: raise ReadinessError("missing package may not carry a sha256")
    elif status=="VERIFIED_PACKAGE":
        if type(sha) is not str or not SHA256_RE.fullmatch(sha): raise ReadinessError("verified package requires lowercase sha256")
    else: raise ReadinessError("unsupported controlling package status")
    notices=[r for r in rows if r.get("kind")=="PUBLIC_NOTICE"]
    if not notices: raise ReadinessError("public notice source required")
    if any(r.get("controls_package_requirements") is not False for r in notices): raise ReadinessError("public notice may not control package requirements")
    notice=_dict(source.get("public_notice_facts"),"public_notice_facts")
    if notice.get("questions_deadline")!=QUESTIONS_DEADLINE or notice.get("proposal_deadline")!=PROPOSAL_DEADLINE: raise ReadinessError("verified deadline changed")
    if notice.get("portal_url")!=PORTAL_URL or notice.get("submission_method")!="PORTAL_ONLY" or notice.get("pricing_route")!="DESIGNATED_MARKETPLACE_FIELDS_ONLY": raise ReadinessError("public notice route changed")
    if _bool(notice.get("hard_copy_allowed"),"hard_copy_allowed") is not False: raise ReadinessError("hard-copy rule changed")
    package_only=_dict(source.get("package_only_truth"),"package_only_truth")
    if status=="MISSING_PACKAGE" and any(v!="MISSING_PACKAGE" for v in package_only.values()): raise ReadinessError("package-only facts promoted without package")
    support=_dict(source.get("support_route_observations"),"support_route_observations")
    obs=_list(support.get("observed"),"support observations")
    phones={r.get("phone") for r in obs if type(r) is dict and r.get("phone")}
    if len(phones)>1 and (support.get("status")!="CONFLICT_OBSERVED" or support.get("do_not_guess_operational_phone") is not True): raise ReadinessError("support-phone conflict must fail closed")
    boundaries=_dict(source.get("truth_boundaries"),"truth_boundaries")
    for k in ("public_notice_is_controlling_package","marketplace_signup_is_package_acquisition","portal_registration_authorized","buyer_contact_authorized","pricing_commitment_authorized","submission_authorized","contract_acceptance_authorized","revenue_recognition_authorized"):
        if _bool(boundaries.get(k),"truth_boundaries.%s"%k): raise ReadinessError("truth boundary must stay false: %s"%k)
    return {"package_status":status,"package_sha256":sha,"questions_deadline":_dt(QUESTIONS_DEADLINE,"questions deadline"),"proposal_deadline":_dt(PROPOSAL_DEADLINE,"proposal deadline"),"support_phone_conflict":len(phones)>1}

def validate_state(state:Dict[str,Any])->Dict[str,Any]:
    if state.get("schema")!=STATE_SCHEMA or state.get("solicitation_id")!=SOLICITATION_ID: raise ReadinessError("unexpected readiness state")
    package=_dict(state.get("package"),"package"); portal=_dict(state.get("portal"),"portal"); response=_dict(state.get("response"),"response"); authority=_dict(state.get("authority"),"authority"); deadlines=_dict(state.get("known_deadlines"),"known_deadlines")
    _keys(package,PACKAGE_KEYS,"package"); _keys(portal,PORTAL_KEYS,"portal"); _keys(response,RESPONSE_KEYS,"response"); _keys(authority,AUTHORITY_KEYS,"authority"); _keys(deadlines,DEADLINE_KEYS,"known_deadlines")
    for k in PACKAGE_BOOL_GATES: _bool(package.get(k),"package.%s"%k)
    for k in PORTAL_BOOL_GATES: _bool(portal.get(k),"portal.%s"%k)
    _bool(portal.get("support_route_conflict_resolved"),"portal.support_route_conflict_resolved")
    for k in RESPONSE_BOOL_GATES: _bool(response.get(k),"response.%s"%k)
    for k in AUTHORITY_KEYS: _bool(authority.get(k),"authority.%s"%k)
    status,sha=package.get("status"),package.get("sha256")
    if status=="MISSING_PACKAGE":
        if sha is not None or any(package[k] for k in PACKAGE_BOOL_GATES) or any(response[k] for k in RESPONSE_BOOL_GATES): raise ReadinessError("missing package cannot carry derived truth")
    elif status=="VERIFIED_PACKAGE":
        if type(sha) is not str or not SHA256_RE.fullmatch(sha): raise ReadinessError("verified readiness package requires lowercase sha256")
    else: raise ReadinessError("unsupported readiness package status")
    if deadlines.get("questions_deadline")!=QUESTIONS_DEADLINE or deadlines.get("proposal_deadline")!=PROPOSAL_DEADLINE: raise ReadinessError("state deadline changed")
    actions=_list(state.get("next_actions"),"next_actions")
    if len(actions)>64: raise ReadinessError("too many next actions")
    for row in actions:
        if type(row) is not dict or type(row.get("priority")) is not int or type(row.get("priority")) is bool: raise ReadinessError("invalid next action")
    return {"as_of":_dt(state.get("as_of"),"state.as_of"),"package":package,"portal":portal,"response":response,"authority":authority,"questions_deadline":_dt(QUESTIONS_DEADLINE,"questions deadline"),"proposal_deadline":_dt(PROPOSAL_DEADLINE,"proposal deadline")}

def _missing(section:Dict[str,Any],keys:Iterable[str],prefix:str)->List[str]:
    return ["%s.%s"%(prefix,k) for k in keys if section.get(k) is not True]

def build_report(source:Dict[str,Any],state:Dict[str,Any],*,as_of_override:Optional[str]=None)->Dict[str,Any]:
    sv=validate_source_register(source); st=validate_state(state); as_of=st["as_of"] if as_of_override is None else _dt(as_of_override,"as_of_override")
    if sv["package_status"]!=st["package"]["status"] or sv["package_sha256"]!=st["package"]["sha256"]: raise ReadinessError("source/state package mismatch")
    questions_open=as_of<sv["questions_deadline"]; proposal_open=as_of<sv["proposal_deadline"]
    rb=[]
    for k in ("legal_company_identity_verified","authorized_site_administrator_verified","authorized_agent_for_vendor_agreement_verified","company_information_truthfulness_attested"):
        if st["portal"].get(k) is not True: rb.append("portal.%s"%k)
    rb+=_missing(st["authority"],REGISTRATION_AUTHORITY_GATES,"authority")
    sb=[]
    if not proposal_open: sb.append("proposal_deadline_passed")
    if st["package"]["status"]!="VERIFIED_PACKAGE": sb.append("package.status")
    if not st["package"]["sha256"]: sb.append("package.sha256")
    sb+=_missing(st["package"],PACKAGE_BOOL_GATES,"package")+_missing(st["portal"],PORTAL_BOOL_GATES,"portal")+_missing(st["response"],RESPONSE_BOOL_GATES,"response")+_missing(st["authority"],SUBMISSION_AUTHORITY_GATES,"authority")
    qb=[]
    if not questions_open: qb.append("questions_deadline_passed")
    if st["package"]["status"]!="VERIFIED_PACKAGE": qb.append("package.status")
    if st["package"].get("requirements_extracted") is not True: qb.append("package.requirements_extracted")
    if st["authority"].get("owner_authorized_buyer_question") is not True: qb.append("authority.owner_authorized_buyer_question")
    if st["authority"].get("muse_outbound_clearance") is not True: qb.append("authority.muse_outbound_clearance")
    actions=_list(state.get("next_actions"),"next_actions"); rec=next((r for r in sorted(actions,key=lambda x:x.get("priority",999999)) if r.get("status")!="DONE"),None)
    core={"schema":REPORT_SCHEMA,"solicitation_id":SOLICITATION_ID,"as_of":as_of.isoformat(),"questions_window_open":questions_open,"proposal_window_open":proposal_open,"support_phone_conflict_observed":sv["support_phone_conflict"],"portal_registration_candidate_ready":not rb,"portal_registration_candidate_blockers":sorted(set(rb)),"portal_registration_ready":False,"portal_registration_blockers":sorted(set(rb+[OWNER_AUTH_BLOCKER])),"buyer_question_candidate_ready":not qb,"buyer_question_candidate_blockers":sorted(set(qb)),"buyer_question_ready":False,"buyer_question_blockers":sorted(set(qb+[PACKAGE_AUTH_BLOCKER,MUSE_AUTH_BLOCKER,OWNER_AUTH_BLOCKER])),"submission_candidate_ready":not sb,"submission_candidate_blockers":sorted(set(sb)),"submission_ready":False,"submission_blockers":sorted(set(sb+[PACKAGE_AUTH_BLOCKER,OWNER_AUTH_BLOCKER])),"recommended_next_action":rec,"authority":{"this_report_authorizes_portal_registration":False,"this_report_authorizes_buyer_contact":False,"this_report_authorizes_pricing_commitment":False,"this_report_authorizes_submission":False,"this_report_authorizes_contract_acceptance":False,"this_report_authorizes_payment_or_revenue_claim":False}}
    core["receipt"]={"input_sha256":_sha({"source":source,"state":state,"as_of_override":as_of_override}),"report_core_sha256":_sha(core),"provider_authenticated_package":False,"provider_authenticated_owner_authorization":False,"provider_authenticated_muse_election":False}
    return core

def verify_report(source:Dict[str,Any],state:Dict[str,Any],report:Dict[str,Any],*,as_of_override:Optional[str]=None)->bool:
    if type(report) is not dict: return False
    try: return report==build_report(source,state,as_of_override=as_of_override)
    except (ReadinessError,ValueError,TypeError): return False

def main(argv:Optional[List[str]]=None)->int:
    p=argparse.ArgumentParser(); p.add_argument("--sources",type=Path,required=True); p.add_argument("--state",type=Path,required=True); p.add_argument("--as-of"); p.add_argument("--expect-not-ready",action="store_true"); a=p.parse_args(argv)
    try: report=build_report(load_json(a.sources),load_json(a.state),as_of_override=a.as_of)
    except (OSError,ReadinessError,ValueError) as e:
        print(json.dumps({"error":str(e)},sort_keys=True)); return 2
    print(json.dumps(report,indent=2,sort_keys=True))
    return 3 if a.expect_not_ready and report["submission_ready"] else 0

if __name__=="__main__": raise SystemExit(main())
