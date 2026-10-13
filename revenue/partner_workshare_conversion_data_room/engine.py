#!/usr/bin/env python3
"""Deterministic compiler/verifier for the partner workshare data room."""
from __future__ import annotations

from typing import Any

from .schema import (
    AUTHORITY_CEILING, COMMERCIAL_STATE, COMPILER, PRIMARY, RISKY,
    CompiledBundle, PacketError, _canonical, _digest, _ts, load_strict_json,
)
from .contract import _normalize

def _derive(n):
    blockers=set(); now=_ts(n["evaluation_at_utc"],"evaluation_at_utc")
    if now>=_ts(n["opportunity"]["deadline_utc"],"opportunity.deadline_utc"): blockers.add("opportunity deadline is closed at retained evaluation time")
    eidx={x["id"]:x for x in n["evidence"]}; validity={}
    for e in n["evidence"]:
        if _ts(e["observed_at_utc"],"observed_at_utc")>now: validity[e["id"]]="FUTURE"; blockers.add(f"evidence {e['id']} is future-dated")
        elif e["expires_at_utc"] and _ts(e["expires_at_utc"],"expires_at_utc")<=now: validity[e["id"]]="EXPIRED"; blockers.add(f"evidence {e['id']} is expired")
        else: validity[e["id"]]="CURRENT"
    def primary(refs): return bool(refs) and all(eidx[r]["authority"] in PRIMARY for r in refs)
    claim_eval=[]; cidx={x["id"]:x for x in n["claims"]}
    for c in n["claims"]:
        reasons=[]
        if c["state"]!="SUPPORTED": reasons.append("claim is proposed, not supported")
        if c["state"]=="SUPPORTED" and not c["evidence_refs"]: reasons.append("supported claim lacks evidence")
        if any(validity[r]!="CURRENT" for r in c["evidence_refs"]): reasons.append("claim depends on non-current evidence")
        if c["kind"] in RISKY and not primary(c["evidence_refs"]): reasons.append("risk-bearing claim lacks primary retained authority")
        blockers.update(f"claim {c['id']}: {r}" for r in reasons); claim_eval.append({"id":c["id"],"ready":not reasons,"reasons":sorted(reasons)})
    cap_eval=[]
    for c in n["capability_slices"]:
        reasons=[f"claim {cid} is not supported" for cid in c["claim_ids"] if cidx[cid]["state"]!="SUPPORTED"]
        if not c["evidence_refs"]: reasons.append("capability has no retained evidence")
        if any(validity[r]!="CURRENT" for r in c["evidence_refs"]): reasons.append("capability depends on non-current evidence")
        blockers.update(f"capability {c['id']}: {r}" for r in reasons); cap_eval.append({"id":c["id"],"ready":not reasons,"reasons":sorted(reasons)})
    for a in n["assumptions"]:
        if a["required_for_ready"] and not a["evidence_refs"]: blockers.add(f"assumption {a['id']} requires retained evidence")
        elif a["required_for_ready"] and any(validity[r]!="CURRENT" for r in a["evidence_refs"]): blockers.add(f"assumption {a['id']} depends on non-current evidence")
    for s in n["security_access"]:
        if s["state"]!="PROVEN": blockers.add(f"security/access {s['id']} is {s['state']}")
        elif not primary(s["evidence_refs"]): blockers.add(f"security/access {s['id']} PROVEN state lacks primary retained authority")
        elif any(validity[r]!="CURRENT" for r in s["evidence_refs"]): blockers.add(f"security/access {s['id']} depends on non-current evidence")
    p=n["pricing_basis"]
    if p["status"]!=COMMERCIAL_STATE: blockers.add("pricing remains placeholder")
    elif not any(eidx[r]["kind"]=="OWNER_PRICING_AUTHORITY" and eidx[r]["authority"] in PRIMARY and validity[r]=="CURRENT" for r in p["evidence_refs"]): blockers.add("proposed pricing lacks current OWNER_PRICING_AUTHORITY evidence")
    decision="READY_FOR_OWNER_REVIEW" if not blockers else "HOLD"
    return decision,sorted(blockers),{"commercial_state":COMMERCIAL_STATE,"decision":decision,"blockers":sorted(blockers),"evidence_validity":[{"id":i,"state":validity[i]} for i in sorted(validity)],"claim_evaluation":sorted(claim_eval,key=lambda x:x["id"]),"capability_evaluation":sorted(cap_eval,key=lambda x:x["id"]),"authority_ceiling":dict(AUTHORITY_CEILING),"truth_note":"Internal owner-review evidence only; readiness never proves external send, acceptance, contract, payment, cash, or revenue."}

def _markdown(p):
    o=p["opportunity"]; lines=[f"# Partner workshare data room — {o['title']}","",f"- Opportunity: `{o['id']}`",f"- Buyer: {o['buyer']}",f"- Evaluation: `{p['evaluation_at_utc']}`",f"- Deadline: `{o['deadline_utc']}`",f"- Decision: **{p['derived']['decision']}**",f"- Commercial state: **{COMMERCIAL_STATE}**","","> Internal owner-review packet only. No external send, partner/buyer acceptance, bid submission, contract, invoice, payment, cash, or revenue authority is conveyed by this artifact.","","## Parties"]
    lines += [f"- **{x['display_name']}** (`{x['id']}`) — {x['role']}" for x in p["parties"]]; lines += ["","## Capability slices / proposed workshare"]
    w={x["capability_id"]:x for x in p["workshare"]}
    for c in p["capability_slices"]:
        ws=w[c["id"]]; lines += [f"### {c['title']} (`{c['id']}`)",f"Owner: `{c['owner_party_id']}` · status: **{ws['status']}**","Deliverables:"]+[f"- {x}" for x in c["deliverables"]]+["Acceptance criteria:"]+[f"- {x}" for x in c["acceptance_criteria"]]
        if ws["dependencies"]: lines += ["Dependencies:"]+[f"- {x}" for x in ws["dependencies"]]
        lines.append("")
    pr=p["pricing_basis"]; lines += ["## Pricing basis", f"- **{pr['currency']} {pr['amount_minor']/100:,.2f} — {COMMERCIAL_STATE}**" if pr["status"]==COMMERCIAL_STATE else "- **PLACEHOLDER — owner pricing authority still required**",f"- Basis: {pr['basis']}","","## Exclusions"]+[f"- {x}" for x in p["exclusions"]]+["","## Security / access"]+[f"- `{x['id']}` **{x['state']}** — {x['requirement']}" for x in p["security_access"]]+["","## Acceptance questions"]+[f"- `{x['id']}` ({x['owner']}): {x['question']}" for x in p["acceptance_questions"]]+["","## Blockers"]
    lines += [f"- {x}" for x in p["derived"]["blockers"]] if p["derived"]["blockers"] else ["- None under the retained internal evidence contract."]
    lines += ["","## Authority ceiling"]+[f"- `{k}` = `{str(v).lower()}`" for k,v in sorted(AUTHORITY_CEILING.items())]+[""]
    return "\n".join(lines)

def compile_packet(candidate: Any) -> CompiledBundle:
    n=_normalize(candidate); decision,blockers,derived=_derive(n); packet=dict(n); packet["derived"]=derived; pj=_canonical(packet); pm=_markdown(packet)
    receipt={"schema_version":"tjlabs-partner-workshare-data-room-receipt/v1","compiler":COMPILER,"packet_input_sha256":_digest(_canonical(n)),"packet_json_sha256":_digest(pj),"packet_markdown_sha256":_digest(pm),"decision":decision,"commercial_state":COMMERCIAL_STATE,"authority_ceiling":dict(AUTHORITY_CEILING)}; rj=_canonical(receipt)
    return CompiledBundle(pj,pm,rj,decision,tuple(blockers))

def verify_bundle(candidate: Any, packet_json: str, packet_markdown: str, receipt_json: str) -> bool:
    e=compile_packet(candidate)
    if packet_json!=e.packet_json: raise PacketError("packet JSON does not match semantic recompile")
    if packet_markdown!=e.packet_markdown: raise PacketError("packet Markdown does not match semantic recompile")
    if receipt_json!=e.receipt_json: raise PacketError("receipt does not match semantic recompile")
    r=load_strict_json(receipt_json)
    if r.get("packet_json_sha256")!=_digest(packet_json) or r.get("packet_markdown_sha256")!=_digest(packet_markdown): raise PacketError("output digest mismatch")
    return True
