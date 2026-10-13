"""Strict normalization for partner workshare packets."""
import re
from .schema import (
    AUTHORITIES, CLAIM_KINDS, COMMERCIAL_STATE, FIELDS, SCHEMA, TOP, PacketError,
    _arr, _enum, _id, _ids, _index, _obj, _refs, _sha, _str, _texts, _ts, _url,
)

def _normalize(raw):
    root = _obj(raw, "packet", TOP)
    if root["schema_version"] != SCHEMA: raise PacketError(f"schema_version must be {SCHEMA}")
    evaluated = _ts(root["evaluation_at_utc"], "evaluation_at_utc")
    o = _obj(root["opportunity"], "opportunity", FIELDS["opportunity"])
    opp = {"id":_id(o["id"],"opportunity.id"), "title":_str(o["title"],"opportunity.title",300), "buyer":_str(o["buyer"],"opportunity.buyer",300), "source_generation":_id(o["source_generation"],"opportunity.source_generation"), "source_sha256":_sha(o["source_sha256"],"opportunity.source_sha256"), "deadline_utc":_str(o["deadline_utc"],"opportunity.deadline_utc",64)}; _ts(opp["deadline_utc"],"opportunity.deadline_utc")

    parties=[]
    for x in _arr(root["parties"],"parties"):
        x=_obj(x,"party",FIELDS["party"]); parties.append({"id":_id(x["id"],"party.id"),"display_name":_str(x["display_name"],"party.display_name",300),"role":_enum(x["role"],"party.role",{"PRIME","SPECIALIST"}),"evidence_refs":_ids(x["evidence_refs"],"party.evidence_refs")})
    parties.sort(key=lambda x:x["id"]); pidx=_index(parties,"party")
    if len(parties)<2: raise PacketError("at least two parties are required")

    evidence=[]
    for x in _arr(root["evidence"],"evidence"):
        x=_obj(x,"evidence",FIELDS["evidence"]); exp=x["expires_at_utc"]
        ev={"id":_id(x["id"],"evidence.id"),"kind":_id(x["kind"],"evidence.kind"),"subject":_id(x["subject"],"evidence.subject"),"source_uri":_url(x["source_uri"],"evidence.source_uri"),"sha256":_sha(x["sha256"],"evidence.sha256"),"observed_at_utc":_str(x["observed_at_utc"],"evidence.observed_at_utc",64),"expires_at_utc":None if exp is None else _str(exp,"evidence.expires_at_utc",64),"authority":_enum(x["authority"],"evidence.authority",AUTHORITIES),"summary":_str(x["summary"],"evidence.summary",1000)}
        _ts(ev["observed_at_utc"],"evidence.observed_at_utc"); ev["expires_at_utc"] and _ts(ev["expires_at_utc"],"evidence.expires_at_utc"); evidence.append(ev)
    evidence.sort(key=lambda x:x["id"]); eidx=_index(evidence,"evidence")
    if not evidence: raise PacketError("at least one evidence item is required")
    for p in parties: _refs(p["evidence_refs"],eidx,f"party {p['id']} evidence_refs")

    claims=[]
    for x in _arr(root["claims"],"claims"):
        x=_obj(x,"claim",FIELDS["claim"]); subject=_id(x["subject"],"claim.subject")
        if subject not in pidx and subject!=opp["id"]: raise PacketError(f"claim subject has no matching party/opportunity: {subject}")
        c={"id":_id(x["id"],"claim.id"),"subject":subject,"kind":_enum(x["kind"],"claim.kind",CLAIM_KINDS),"statement":_str(x["statement"],"claim.statement"),"state":_enum(x["state"],"claim.state",{"SUPPORTED","PROPOSED"}),"evidence_refs":_ids(x["evidence_refs"],"claim.evidence_refs")}; _refs(c["evidence_refs"],eidx,f"claim {c['id']} evidence_refs"); claims.append(c)
    claims.sort(key=lambda x:x["id"]); cidx=_index(claims,"claim")

    caps=[]
    for x in _arr(root["capability_slices"],"capability_slices"):
        x=_obj(x,"capability",FIELDS["capability"]); owner=_id(x["owner_party_id"],"capability.owner_party_id")
        if owner not in pidx: raise PacketError(f"unknown capability owner: {owner}")
        c={"id":_id(x["id"],"capability.id"),"title":_str(x["title"],"capability.title",300),"owner_party_id":owner,"claim_ids":_ids(x["claim_ids"],"capability.claim_ids"),"evidence_refs":_ids(x["evidence_refs"],"capability.evidence_refs"),"deliverables":_texts(x["deliverables"],"capability.deliverables",1),"acceptance_criteria":_texts(x["acceptance_criteria"],"capability.acceptance_criteria",1)}; _refs(c["claim_ids"],cidx,f"capability {c['id']} claim_ids"); _refs(c["evidence_refs"],eidx,f"capability {c['id']} evidence_refs"); caps.append(c)
    caps.sort(key=lambda x:x["id"]); capidx=_index(caps,"capability")
    if not caps: raise PacketError("at least one capability slice is required")

    work=[]; seen=set()
    for x in _arr(root["workshare"],"workshare"):
        x=_obj(x,"workshare",FIELDS["workshare"]); cap=_id(x["capability_id"],"workshare.capability_id"); owner=_id(x["owner_party_id"],"workshare.owner_party_id")
        if cap not in capidx or owner not in pidx: raise PacketError("workshare references unknown capability/owner")
        if cap in seen: raise PacketError(f"capability has multiple workshare assignments: {cap}")
        seen.add(cap)
        if capidx[cap]["owner_party_id"]!=owner: raise PacketError(f"workshare owner conflicts with capability owner for {cap}")
        work.append({"id":_id(x["id"],"workshare.id"),"capability_id":cap,"owner_party_id":owner,"status":_enum(x["status"],"workshare.status",{COMMERCIAL_STATE}),"dependencies":_texts(x["dependencies"],"workshare.dependencies")})
    work.sort(key=lambda x:x["id"]); _index(work,"workshare")
    if seen!=set(capidx): raise PacketError("workshare must assign every capability exactly once")

    assumptions=[]
    for x in _arr(root["assumptions"],"assumptions"):
        x=_obj(x,"assumption",FIELDS["assumption"])
        if type(x["required_for_ready"]) is not bool: raise PacketError("assumption.required_for_ready must be boolean")
        a={"id":_id(x["id"],"assumption.id"),"text":_str(x["text"],"assumption.text",1000),"required_for_ready":x["required_for_ready"],"evidence_refs":_ids(x["evidence_refs"],"assumption.evidence_refs")}; _refs(a["evidence_refs"],eidx,f"assumption {a['id']} evidence_refs"); assumptions.append(a)
    assumptions.sort(key=lambda x:x["id"]); _index(assumptions,"assumption")

    security=[]
    for x in _arr(root["security_access"],"security_access"):
        x=_obj(x,"security",FIELDS["security"]); s={"id":_id(x["id"],"security.id"),"requirement":_str(x["requirement"],"security.requirement",1000),"state":_enum(x["state"],"security.state",{"PROVEN","OWNER_INPUT","HOLD"}),"evidence_refs":_ids(x["evidence_refs"],"security.evidence_refs")}; _refs(s["evidence_refs"],eidx,f"security {s['id']} evidence_refs"); security.append(s)
    security.sort(key=lambda x:x["id"]); _index(security,"security")

    x=_obj(root["pricing_basis"],"pricing_basis",FIELDS["pricing"]); status=_enum(x["status"],"pricing_basis.status",{"PLACEHOLDER",COMMERCIAL_STATE}); refs=_ids(x["evidence_refs"],"pricing_basis.evidence_refs"); _refs(refs,eidx,"pricing_basis.evidence_refs")
    pricing={"status":status,"currency":None,"amount_minor":None,"basis":_str(x["basis"],"pricing_basis.basis",1000),"evidence_refs":refs}
    if status=="PLACEHOLDER":
        if x["currency"] is not None or x["amount_minor"] is not None: raise PacketError("PLACEHOLDER pricing cannot contain currency/amount")
    else:
        currency=_str(x["currency"],"pricing_basis.currency",3)
        if not re.fullmatch(r"[A-Z]{3}",currency): raise PacketError("pricing_basis.currency must be uppercase three-letter code")
        if type(x["amount_minor"]) is not int: raise PacketError("pricing_basis.amount_minor must be integer (bool is rejected)")
        if x["amount_minor"]<=0: raise PacketError("pricing_basis.amount_minor must be positive")
        pricing.update(currency=currency,amount_minor=x["amount_minor"])

    questions=[]
    for x in _arr(root["acceptance_questions"],"acceptance_questions"):
        x=_obj(x,"question",FIELDS["question"]); questions.append({"id":_id(x["id"],"question.id"),"question":_str(x["question"],"question.question",1000),"owner":_str(x["owner"],"question.owner",300)})
    questions.sort(key=lambda x:x["id"]); _index(questions,"question")
    if not questions: raise PacketError("at least one acceptance question is required")

    return {"schema_version":SCHEMA,"evaluation_at_utc":evaluated.isoformat().replace("+00:00","Z"),"opportunity":opp,"parties":parties,"evidence":evidence,"claims":claims,"capability_slices":caps,"workshare":work,"exclusions":_texts(root["exclusions"],"exclusions",1),"assumptions":assumptions,"security_access":security,"pricing_basis":pricing,"acceptance_questions":questions}

