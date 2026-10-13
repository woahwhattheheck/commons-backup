"""Fail-closed owner handoff manifests for verified opportunity portfolios."""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import json, re
from typing import Any
from revenue.opportunity_portfolio.portfolio import PortfolioError, RECEIPT_SCHEMA as UPSTREAM_SCHEMA, verify_receipt as verify_portfolio

SCHEMA="commons-portfolio-execution-handoff/v1"
RECEIPT_SCHEMA="commons-portfolio-execution-handoff-receipt/v1"
SHA=re.compile(r"^[0-9a-f]{64}$"); ID=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
SLACK=re.compile(r"^slack://C[A-Z0-9]{8,}/[0-9]{10,}\.[0-9]{6}$")
GH=re.compile(r"^github://[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/(?:issues|pull)/[1-9][0-9]*#(?:issuecomment|discussion_r|pullrequestreview)-[1-9][0-9]*$")
ACTIONS={"BUILD","QUALIFY","REVIEW","REPLY_PREP","SUBMISSION_PREP","INTEGRATE","DELIVERY_PREP","COLLECT_EVIDENCE"}
SECRET=[re.compile(x,re.I) for x in [r"-----BEGIN .*PRIVATE KEY-----",r"\bgh[pousr]_[A-Za-z0-9]{20,}\b",r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b",r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b",r"\bAKIA[0-9A-Z]{16}\b"]]
PII=[re.compile(x,re.I) for x in [r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)",r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"]]
class HandoffError(ValueError): pass
def canon(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def digest(v): return sha256(canon(v)).hexdigest()
def obj(v,f):
    if type(v) is not dict: raise HandoffError(f"{f}: expected object")
    return v
def arr(v,f):
    if type(v) is not list: raise HandoffError(f"{f}: expected array")
    return v
def text(v,f,pat=None):
    if type(v) is not str or not v or len(v)>512 or (pat and not pat.fullmatch(v)): raise HandoffError(f"{f}: invalid string")
    return v
def integer(v,f,lo=0):
    if type(v) is not int or v<lo: raise HandoffError(f"{f}: invalid integer")
    return v
def utc(v,f):
    s=text(v,f)
    if not s.endswith("Z"): raise HandoffError(f"{f}: UTC Z required")
    try: d=datetime.fromisoformat(s[:-1]+"+00:00")
    except ValueError as e: raise HandoffError(f"{f}: invalid timestamp") from e
    if d.microsecond or d.utcoffset()!=timezone.utc.utcoffset(d): raise HandoffError(f"{f}: canonical UTC required")
    return d
def scan(v,f="$"):
    if type(v) is str:
        if any(p.search(v) for p in SECRET): raise HandoffError(f"{f}: secret-shaped material refused")
        if any(p.search(v) for p in PII): raise HandoffError(f"{f}: PII-shaped material refused")
    elif type(v) is list:
        for i,x in enumerate(v): scan(x,f"{f}[{i}]")
    elif type(v) is dict:
        for k,x in v.items():
            if type(k) is not str: raise HandoffError(f"{f}: non-string key")
            scan(x,f"{f}.{k}")
def sha(v,f): return text(v,f,SHA)
def exact(o,keys,f):
    extra=set(o)-set(keys)
    if extra: raise HandoffError(f"{f}: unknown fields {sorted(extra)}")
def ref(v,f):
    r=obj(v,f); exact(r,{"kind","ref","evidenceSha256"},f); k=text(r.get("kind"),f+".kind"); s=text(r.get("ref"),f+".ref")
    if k=="SLACK_MESSAGE":
        if not SLACK.fullmatch(s): raise HandoffError(f"{f}.ref: exact Slack message required")
    elif k=="GITHUB_COMMENT":
        if not GH.fullmatch(s): raise HandoffError(f"{f}.ref: exact GitHub comment required")
    else: raise HandoffError(f"{f}.kind: unsupported reference class")
    return {"kind":k,"ref":s,"evidenceSha256":sha(r.get("evidenceSha256"),f+".evidenceSha256")}
def norm_handoff(v,i):
    f=f"handoffs[{i}]"; h=obj(v,f); exact(h,{"opportunityId","ownerSeat","custody","nextAction","expiresAt"},f)
    c=obj(h.get("custody"),f+".custody"); exact(c,{"state","claim","claimedAt","generation"},f+".custody")
    state=text(c.get("state"),f+".custody.state")
    if state not in {"ACTIVE","RELEASED"}: raise HandoffError(f"{f}.custody.state: invalid")
    a=obj(h.get("nextAction"),f+".nextAction"); exact(a,{"class","summary","destination","evidenceSha256"},f+".nextAction")
    cls=text(a.get("class"),f+".nextAction.class")
    if cls not in ACTIONS: raise HandoffError(f"{f}.nextAction.class: unsupported")
    return {"opportunityId":text(h.get("opportunityId"),f+".opportunityId",ID),"ownerSeat":text(h.get("ownerSeat"),f+".ownerSeat",ID),
      "custody":{"state":state,"claim":ref(c.get("claim"),f+".custody.claim"),"claimedAt":text(c.get("claimedAt"),f+".custody.claimedAt"),"generation":integer(c.get("generation"),f+".custody.generation",1)},
      "nextAction":{"class":cls,"summary":text(a.get("summary"),f+".nextAction.summary"),"destination":ref(a.get("destination"),f+".nextAction.destination"),"evidenceSha256":sha(a.get("evidenceSha256"),f+".nextAction.evidenceSha256")},
      "expiresAt":text(h.get("expiresAt"),f+".expiresAt")}
def normalize(payload):
    scan(payload); r=obj(payload,"$"); exact(r,{"schema","portfolioReceipt","handoffs"},"$")
    if r.get("schema")!=SCHEMA: raise HandoffError("wrong input schema")
    p=obj(r.get("portfolioReceipt"),"portfolioReceipt")
    if p.get("schema")!=UPSTREAM_SCHEMA: raise HandoffError("wrong portfolio schema")
    try: verify_portfolio(p)
    except (PortfolioError,ValueError,TypeError) as e: raise HandoffError(f"portfolio verification failed: {e}") from e
    hs=[norm_handoff(x,i) for i,x in enumerate(arr(r.get("handoffs"),"handoffs"))]
    if len(hs)>64: raise HandoffError("too many handoffs")
    ids=[x["opportunityId"] for x in hs]
    if len(ids)!=len(set(ids)): raise HandoffError("duplicate opportunityId")
    return {"schema":SCHEMA,"portfolioReceipt":p,"handoffs":sorted(hs,key=lambda x:x["opportunityId"])}
def portfolio_contract(p):
    a=obj(p.get("authority"),"portfolio.authority")
    for k in ["externalActionsAuthorized","outreachAuthorized","submissionAuthorized","spendAuthorized","contractAuthorized","paymentAuthorized","revenueRecognized"]:
        if a.get(k) is not False: raise HandoffError(f"portfolio authority {k} must be false")
    if a.get("strongestState")!="PORTFOLIO_READY_FOR_HUMAN_EXECUTION_REVIEW": raise HandoffError("portfolio not review-ready")
    n=obj(p.get("normalizedInput"),"portfolio.normalizedInput"); actor=text(n.get("actorSeat"),"portfolio.actorSeat",ID)
    by={x["id"]:x for x in arr(n.get("opportunities"),"portfolio.opportunities")}
    selected=arr(p.get("portfolio"),"portfolio.portfolio"); ss=set(selected)
    if len(ss)!=len(selected): raise HandoffError("duplicate selected id")
    dec={x["id"]:x["status"] for x in arr(p.get("decisions"),"portfolio.decisions")}
    if {k for k,v in dec.items() if v=="EXECUTE_NOW"}!=ss or not ss.issubset(by): raise HandoffError("portfolio selection/decision mismatch")
    return by,ss,actor
def compile_handoff(payload:Any,*,trusted_as_of:str)->dict[str,Any]:
    n=normalize(payload); now=utc(trusted_as_of,"trusted_as_of"); p=n["portfolioReceipt"]; ptime=utc(p.get("trustedAsOf"),"portfolio.trustedAsOf")
    if now<ptime: raise HandoffError("trusted_as_of predates portfolio")
    by,selected,actor=portfolio_contract(p); hm={x["opportunityId"]:x for x in n["handoffs"]}; supplied=set(hm)
    holds=[f"MISSING_HANDOFF:{x}" for x in sorted(selected-supplied)]+[f"UNSELECTED_HANDOFF:{x}" for x in sorted(supplied-selected)]
    rows=[]
    for oid in sorted(selected&supplied):
        h=hm[oid]; o=by[oid]; reasons=[]; owner=obj(o.get("owner"),oid+".owner"); ost=owner.get("status")
        if ost=="OWNED_BY_THIS_SEAT":
            if owner.get("seat")!=actor or h["ownerSeat"]!=actor: reasons.append("OWNER_MISMATCH")
        elif ost!="AVAILABLE": reasons.append(f"PORTFOLIO_OWNER_NOT_HANDOFFABLE:{ost}")
        claim=utc(h["custody"]["claimedAt"],oid+".claimedAt"); exp=utc(h["expiresAt"],oid+".expiresAt"); deadline=utc(o.get("deadline"),oid+".deadline"); fresh=utc(o.get("freshUntil"),oid+".freshUntil"); observed=utc(obj(o.get("source"),oid+".source").get("observedAt"),oid+".observedAt")
        if h["custody"]["state"]!="ACTIVE": reasons.append("CUSTODY_NOT_ACTIVE")
        if claim>now: reasons.append("CLAIM_IN_FUTURE")
        if claim>exp: reasons.append("CLAIM_AFTER_EXPIRY")
        if now>exp: reasons.append("HANDOFF_EXPIRED")
        if (exp-claim).total_seconds()>86400: reasons.append("HANDOFF_LIFETIME_EXCEEDS_24H")
        if observed>now: reasons.append("SOURCE_OBSERVED_IN_FUTURE")
        if now>fresh: reasons.append("SOURCE_STALE")
        if now>=deadline: reasons.append("DEADLINE_CLOSED")
        if exp>deadline: reasons.append("HANDOFF_EXPIRES_AFTER_DEADLINE")
        rows.append({"opportunityId":oid,"ownerSeat":h["ownerSeat"],"generation":h["custody"]["generation"],"status":"HOLD" if reasons else "READY_FOR_OWNER_REVIEW","reasons":sorted(reasons),"sourceDigestSha256":o["source"]["digestSha256"],"claim":h["custody"]["claim"],"nextAction":h["nextAction"],"expiresAt":h["expiresAt"]})
    if any(x["status"]=="HOLD" for x in rows): holds.append("HANDOFF_ROW_HOLD")
    auth={k:False for k in ["externalActionsAuthorized","outreachAuthorized","submissionAuthorized","spendAuthorized","contractAuthorized","providerMutationAuthorized","paymentAuthorized","revenueRecognized"]}
    auth["strongestState"]="HOLD" if holds else "READY_FOR_OWNER_HANDOFF_REVIEW"
    out={"schema":RECEIPT_SCHEMA,"trustedAsOf":trusted_as_of,"sourcePortfolio":{"receiptDigestSha256":sha(p.get("receiptDigestSha256"),"portfolio.digest"),"trustedAsOf":p.get("trustedAsOf"),"actorSeat":actor,"selectedOpportunityIds":sorted(selected)},"inputDigestSha256":digest(n),"normalizedInput":n,"globalHolds":sorted(holds),"handoffs":rows,"authority":auth}
    out["receiptDigestSha256"]=digest(out); return out
def verify_receipt(r:Any,*,trusted_as_of:str|None=None)->bool:
    scan(r)
    if type(r) is not dict or r.get("schema")!=RECEIPT_SCHEMA: raise HandoffError("wrong receipt schema")
    claimed=r.get("receiptDigestSha256")
    if type(claimed) is not str or not SHA.fullmatch(claimed): raise HandoffError("invalid receipt digest")
    u=dict(r); u.pop("receiptDigestSha256",None)
    if digest(u)!=claimed or digest(r.get("normalizedInput"))!=r.get("inputDigestSha256"): raise HandoffError("receipt digest mismatch")
    if canon(compile_handoff(r["normalizedInput"],trusted_as_of=r["trustedAsOf"]))!=canon(r): raise HandoffError("deterministic recompilation mismatch")
    if trusted_as_of and compile_handoff(r["normalizedInput"],trusted_as_of=trusted_as_of)["authority"]["strongestState"]!="READY_FOR_OWNER_HANDOFF_REVIEW": raise HandoffError("receipt no longer review-ready")
    return True
def render_markdown(r:dict[str,Any])->str:
    verify_receipt(r); lines=["# Portfolio Execution Handoff","",f"- Trusted as-of: `{r['trustedAsOf']}`",f"- Source portfolio: `{r['sourcePortfolio']['receiptDigestSha256']}`",f"- State: `{r['authority']['strongestState']}`","- External action authority: **false**","","## Owner handoffs"]
    lines += [f"- `{x['opportunityId']}` → `{x['ownerSeat']}` / `{x['nextAction']['class']}`: **{x['status']}**"+(f" — {', '.join(x['reasons'])}" if x["reasons"] else "") for x in r["handoffs"]] or ["- None"]
    return "\n".join(lines+["","This artifact is human-review evidence only; it authorizes no outreach, submission, spend, contract, provider mutation, payment, acceptance, or revenue."])+"\n"
