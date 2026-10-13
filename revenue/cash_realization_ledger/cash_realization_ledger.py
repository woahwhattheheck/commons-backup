#!/usr/bin/env python3
"""Deterministic evidence ledger separating commercial progress from received cash."""
from __future__ import annotations
import argparse,csv,hashlib,io,json,re
from pathlib import Path
from typing import Any,Mapping
SCHEMA_VERSION=2; MAX_MINOR=9_000_000_000_000_000
ID_RE=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"); CUR_RE=re.compile(r"^[A-Z]{3}$"); SHA_RE=re.compile(r"^[0-9a-f]{64}$"); UTC_RE=re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
CLAIM_KINDS={"BOUNTY","CONTRACT","COMPETITION","PROJECT","OTHER"}; EVIDENCE_STATUS={"verified","pending","rejected"}
EVENT_KINDS={"OPPORTUNITY_RECORDED","ACCEPTED_EVIDENCE","AWARD_EVIDENCE","REQUESTED_OR_INVOICED_EVIDENCE","PAYMENT_PENDING_EVIDENCE","PAYMENT_RECEIVED_EVIDENCE","PAYMENT_REVERSED_EVIDENCE","RECONCILED_EVIDENCE"}
AUTHORITIES={"internal_record","owner_approved","counterparty_evidence","sponsor_evidence","public_award","payment_provider_evidence","bank_record"}
EVENT_AUTHORITIES={"OPPORTUNITY_RECORDED":{"internal_record","owner_approved"},"ACCEPTED_EVIDENCE":{"counterparty_evidence","sponsor_evidence"},"AWARD_EVIDENCE":{"sponsor_evidence","public_award"},"REQUESTED_OR_INVOICED_EVIDENCE":{"internal_record","counterparty_evidence"},"PAYMENT_PENDING_EVIDENCE":{"sponsor_evidence","payment_provider_evidence"},"PAYMENT_RECEIVED_EVIDENCE":{"payment_provider_evidence","bank_record"},"PAYMENT_REVERSED_EVIDENCE":{"payment_provider_evidence","bank_record"},"RECONCILED_EVIDENCE":{"owner_approved"}}
MONEY_EVENTS=EVENT_KINDS-{"OPPORTUNITY_RECORDED"}; PRE_CASH=("PAYMENT_PENDING_EVIDENCE","REQUESTED_OR_INVOICED_EVIDENCE","AWARD_EVIDENCE","ACCEPTED_EVIDENCE","OPPORTUNITY_RECORDED")
STATE_BY_EVENT={"PAYMENT_PENDING_EVIDENCE":"PAYMENT_PENDING","REQUESTED_OR_INVOICED_EVIDENCE":"REQUESTED_OR_INVOICED","AWARD_EVIDENCE":"AWARDED","ACCEPTED_EVIDENCE":"ACCEPTED","OPPORTUNITY_RECORDED":"OPPORTUNITY"}
PUBLIC_STATES={"OPPORTUNITY","ACCEPTED","AWARDED","REQUESTED_OR_INVOICED","PAYMENT_PENDING","PARTIALLY_RECEIVED","RECEIVED","REVERSED","RECONCILED","HOLD"}
def _canonical_bytes(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def _sha256(v): return hashlib.sha256(_canonical_bytes(v)).hexdigest()
def event_sha256(event):
 if type(event) is not dict: raise ValueError("event must be an object")
 return _sha256(event)
def _dict(v,c):
 if type(v) is not dict: raise ValueError(f"{c} must be an object")
 return v
def _list(v,c):
 if type(v) is not list: raise ValueError(f"{c} must be a list")
 return v
def _text(v,c,p=None):
 if type(v) is not str or not v or v!=v.strip(): raise ValueError(f"{c} must be non-empty text without surrounding whitespace")
 if p and not p.fullmatch(v): raise ValueError(f"{c} has invalid format")
 return v
def _id(v,c): return _text(v,c,ID_RE)
def _utc(v,c): return _text(v,c,UTC_RE)
def _digest(v,c): return _text(v,c,SHA_RE)
def _money(v,c,*,allow_zero=False):
 if type(v) is not int: raise ValueError(f"{c} must be an integer minor-unit amount")
 if not (0 if allow_zero else 1)<=v<=MAX_MINOR: raise ValueError(f"{c} outside safe bounds")
 return v
def _enum(v,allowed,c):
 x=_text(v,c)
 if x not in allowed: raise ValueError(f"{c}: invalid value {x!r}")
 return x
def _keys(o,req,opt,c):
 missing=req-set(o); unknown=set(o)-req-opt
 if missing: raise ValueError(f"{c}: missing fields {sorted(missing)}")
 if unknown: raise ValueError(f"{c}: unknown fields {sorted(unknown)}")
def _unique(rows,c):
 seen=set()
 for row in rows:
  x=_id(row.get("id"),f"{c}.id")
  if x in seen: raise ValueError(f"duplicate {c} id: {x}")
  seen.add(x)
def validate_packet(packet):
 r=_dict(packet,"packet"); _keys(r,{"schema_version","portfolio","claims","events","evidence"},set(),"packet")
 if type(r["schema_version"]) is not int or r["schema_version"]!=SCHEMA_VERSION: raise ValueError("schema_version must be integer 2; legacy v1 evidence is not event-bound and cannot establish current cash state")
 p=_dict(r["portfolio"],"portfolio"); _keys(p,{"name"},set(),"portfolio"); _text(p["name"],"portfolio.name")
 claims=[_dict(x,"claims[]") for x in _list(r["claims"],"claims")]; events=[_dict(x,"events[]") for x in _list(r["events"],"events")]; evs=[_dict(x,"evidence[]") for x in _list(r["evidence"],"evidence")]
 if not claims: raise ValueError("claims must contain at least one item")
 for rows,name in ((claims,"claim"),(events,"event"),(evs,"evidence")): _unique(rows,name)
 claim_ids=set(); claim_digests={}
 for c in claims:
  _keys(c,{"id","kind","counterparty_ref","currency","reference_amount_minor","created_at","source_ref","source_sha256"},set(),f"claim {c.get('id','?')}")
  cid=_id(c["id"],"claim.id"); claim_ids.add(cid); _enum(c["kind"],CLAIM_KINDS,f"claim {cid}.kind"); _id(c["counterparty_ref"],f"claim {cid}.counterparty_ref"); _text(c["currency"],f"claim {cid}.currency",CUR_RE); _money(c["reference_amount_minor"],f"claim {cid}.reference_amount_minor"); _utc(c["created_at"],f"claim {cid}.created_at"); _text(c["source_ref"],f"claim {cid}.source_ref"); _digest(c["source_sha256"],f"claim {cid}.source_sha256"); claim_digests[cid]=_sha256(c)
 event_digests={}; event_by_evidence={}
 for e in events:
  _keys(e,{"id","claim_id","claim_sha256","kind","occurred_at","evidence_id"},{"amount_minor"},f"event {e.get('id','?')}"); x=_id(e["id"],"event.id"); cid=_id(e["claim_id"],f"event {x}.claim_id")
  if cid not in claim_ids: raise ValueError(f"event {x}: unknown claim_id {cid}")
  if _digest(e["claim_sha256"],f"event {x}.claim_sha256")!=claim_digests[cid]: raise ValueError(f"event {x}: claim digest mismatch")
  kind=_enum(e["kind"],EVENT_KINDS,f"event {x}.kind"); _utc(e["occurred_at"],f"event {x}.occurred_at"); eid=_id(e["evidence_id"],f"event {x}.evidence_id")
  if kind in MONEY_EVENTS:
   if "amount_minor" not in e: raise ValueError(f"event {x}: amount_minor required")
   _money(e["amount_minor"],f"event {x}.amount_minor",allow_zero=kind=="RECONCILED_EVIDENCE")
  elif "amount_minor" in e: raise ValueError(f"event {x}: amount_minor not allowed for opportunity event")
  if eid in event_by_evidence: raise ValueError(f"evidence {eid}: referenced by multiple events {event_by_evidence[eid]} and {x}")
  event_by_evidence[eid]=x; event_digests[x]=event_sha256(e)
 evidence_ids=set(); sources={}; proofs={}
 for e in evs:
  _keys(e,{"id","status","authority","captured_at","reference","sha256","event_sha256"},set(),f"evidence {e.get('id','?')}"); eid=_id(e["id"],"evidence.id"); evidence_ids.add(eid); _enum(e["status"],EVIDENCE_STATUS,f"evidence {eid}.status"); authority=_enum(e["authority"],AUTHORITIES,f"evidence {eid}.authority"); _utc(e["captured_at"],f"evidence {eid}.captured_at"); ref=_text(e["reference"],f"evidence {eid}.reference"); source_sha=_digest(e["sha256"],f"evidence {eid}.sha256"); _digest(e["event_sha256"],f"evidence {eid}.event_sha256")
  source=source_sha
  if source in sources: raise ValueError(f"evidence source identity reused under multiple ids: {sources[source]} and {eid}")
  sources[source]=eid; proofs[eid]=e
 for eid in evidence_ids:
  if eid not in event_by_evidence: raise ValueError(f"evidence {eid}: not referenced by any event")
 for e in events:
  x=e["id"]; eid=e["evidence_id"]
  if eid not in evidence_ids: raise ValueError(f"event {x}: unknown evidence_id {eid}")
  if proofs[eid]["event_sha256"]!=event_digests[x]: raise ValueError(f"event {x}: evidence {eid} event digest mismatch")
 return r
def _event_result(e,proof,claim):
 kind=e["kind"]; amount=e.get("amount_minor"); status="VERIFIED"; reason=None
 if proof["event_sha256"]!=event_sha256(e): status,reason="EVIDENCE_EVENT_BINDING_MISMATCH","evidence does not bind exact event"
 elif proof["status"]!="verified": status,reason="EVIDENCE_NOT_VERIFIED",f"evidence status is {proof['status']}"
 elif proof["authority"] not in EVENT_AUTHORITIES[kind]: status,reason="AUTHORITY_MISMATCH",f"authority {proof['authority']} cannot satisfy {kind}"
 elif e["occurred_at"]<claim["created_at"]: status,reason="CHRONOLOGY_HOLD","event predates claim"
 elif proof["captured_at"]<e["occurred_at"]: status,reason="CHRONOLOGY_HOLD","evidence captured before represented event"
 elif amount is not None and amount>claim["reference_amount_minor"] and kind!="PAYMENT_REVERSED_EVIDENCE": status,reason="AMOUNT_HOLD","event amount exceeds claim reference amount"
 return {"event_id":e["id"],"event_kind":kind,"occurred_at":e["occurred_at"],"evidence_id":e["evidence_id"],"evidence_event_sha256":proof["event_sha256"],"status":status,"amount_minor":amount,"reason":reason}
def evaluate_claim(claim,events,proofs):
 cid=claim["id"]; rows=sorted((e for e in events if e["claim_id"]==cid),key=lambda e:(e["occurred_at"],e["id"])); results=[_event_result(e,proofs[e["evidence_id"]],claim) for e in rows]; blockers=[f"{x['event_id']}:{x['status']}" for x in results if x["status"]!="VERIFIED"]; verified=[x for x in results if x["status"]=="VERIFIED"]
 seen={}; arithmetic=[]
 for x in verified:
  k=(x["event_kind"],x["occurred_at"],x["amount_minor"])
  if k in seen: blockers.append(f"{x['event_id']}:DUPLICATE_SEMANTIC_EVENT")
  else: seen[k]=x["event_id"]; arithmetic.append(x)
 gross=rev=0; latest_cash=None
 for x in arithmetic:
  if x["event_kind"]=="PAYMENT_RECEIVED_EVIDENCE":
   gross+=x["amount_minor"] or 0; latest_cash=x["occurred_at"]
   if gross>claim["reference_amount_minor"]: blockers.append(f"{x['event_id']}:CUMULATIVE_RECEIPT_EXCEEDS_REFERENCE")
  elif x["event_kind"]=="PAYMENT_REVERSED_EVIDENCE":
   amount=x["amount_minor"] or 0
   if rev+amount>gross: blockers.append(f"{x['event_id']}:REVERSAL_EXCEEDS_RECEIVED")
   else: rev+=amount; latest_cash=x["occurred_at"]
 net=max(0,gross-rev); ref=claim["reference_amount_minor"]
 reconciliations=[x for x in verified if x["event_kind"]=="RECONCILED_EVIDENCE"]; rec=None
 if reconciliations:
  latest_at=reconciliations[-1]["occurred_at"]
  latest_reconciliations=[x for x in reconciliations if x["occurred_at"]==latest_at]
  if len({x["amount_minor"] for x in latest_reconciliations})>1:
   blockers.extend(f"{x['event_id']}:CONFLICTING_RECONCILIATIONS" for x in latest_reconciliations)
  else: rec=latest_reconciliations[-1]
 if rec:
  if rec["amount_minor"]!=net: blockers.append(f"{rec['event_id']}:RECONCILE_AMOUNT_MISMATCH")
  if latest_cash is None: blockers.append(f"{rec['event_id']}:RECONCILE_WITHOUT_RECEIPT")
  elif rec["occurred_at"]<latest_cash: blockers.append(f"{rec['event_id']}:STALE_RECONCILIATION")
 if blockers: state="HOLD"
 elif rec and rec["amount_minor"]==net and latest_cash and rec["occurred_at"]>=latest_cash: state="RECONCILED"
 elif rev: state="REVERSED"
 elif net==ref and net: state="RECEIVED"
 elif 0<net<ref: state="PARTIALLY_RECEIVED"
 else:
  kinds={x["event_kind"] for x in verified}; state=next((STATE_BY_EVENT[k] for k in PRE_CASH if k in kinds),"OPPORTUNITY")
 return {"claim_id":cid,"claim_kind":claim["kind"],"currency":claim["currency"],"reference_amount_minor":ref,"state":state,"gross_received_minor":gross,"reversed_minor":rev,"net_received_minor":net,"outstanding_reference_minor":max(0,ref-net),"event_results":results,"blockers":sorted(set(blockers)),"latest_verified_event_at":max((x["occurred_at"] for x in verified),default=None)}
def compile_ledger(packet):
 r=validate_packet(packet); proofs={e["id"]:e for e in r["evidence"]}; results=[evaluate_claim(c,r["events"],proofs) for c in sorted(r["claims"],key=lambda c:c["id"])]; buckets={}; states={s:0 for s in sorted(PUBLIC_STATES)}
 for x in results:
  states[x["state"]]+=1; b=buckets.setdefault(x["currency"],{"claim_count":0,"reference_amount_minor":0,"gross_received_minor":0,"reversed_minor":0,"net_received_minor":0,"outstanding_reference_minor":0}); b["claim_count"]+=1
  for k in ("reference_amount_minor","gross_received_minor","reversed_minor","net_received_minor","outstanding_reference_minor"): b[k]+=x[k]
 normalized={"schema_version":SCHEMA_VERSION,"portfolio":{"name":r["portfolio"]["name"]},"claims":sorted(r["claims"],key=lambda x:x["id"]),"events":sorted(r["events"],key=lambda x:x["id"]),"evidence":sorted(r["evidence"],key=lambda x:x["id"])}
 core={"schema_version":SCHEMA_VERSION,"portfolio":{"name":r["portfolio"]["name"]},"input_sha256":_sha256(normalized),"summary":{"claim_count":len(results),"state_counts":states,"currency_buckets":dict(sorted(buckets.items())),"cross_currency_total_prohibited":True,"cash_only_from_receipt_evidence":True,"evidence_bound_to_exact_event":True,"duplicate_external_source_identity_prohibited":True,"accounting_revenue_recognized":False,"debt_or_collectability_determined":False,"payment_action_authorized":False},"claims":results,"evidence_registry":[{k:e[k] for k in ("id","status","authority","captured_at","reference","sha256","event_sha256")} for e in sorted(r["evidence"],key=lambda x:x["id"])],"authority_boundary":{"acceptance_is_not_cash":True,"award_is_not_cash":True,"invoice_or_request_is_not_cash":True,"pending_payment_is_not_cash":True,"received_is_evidence_state_not_accounting_conclusion":True,"reconciliation_is_owner_review_not_bookkeeping_posting":True,"source_digest_does_not_authenticate_provider":True,"no_external_contact_or_money_movement":True}}
 out=dict(core); out["ledger_sha256"]=_sha256(core); return out
def render_markdown(ledger:Mapping[str,Any])->str:
 lines=["# Commercial cash-realization evidence ledger","",f"**Portfolio:** {ledger['portfolio']['name']}  ",f"**Input SHA-256:** `{ledger['input_sha256']}`  ",f"**Ledger SHA-256:** `{ledger['ledger_sha256']}`  ","","> Evidence control only. Acceptance, awards, invoices/requests and pending payouts are not cash. RECEIVED means exact-event-bound bank/payment-provider evidence exists under this model; it is not an accounting or legal conclusion.","","## Claims","","| Claim | Kind | Currency | Reference | State | Net received | Reversed | Outstanding reference | Blockers |","|---|---|---|---:|---|---:|---:|---:|---|"]
 for x in ledger["claims"]: lines.append(f"| {x['claim_id']} | {x['claim_kind']} | {x['currency']} | {x['reference_amount_minor']} | **{x['state']}** | {x['net_received_minor']} | {x['reversed_minor']} | {x['outstanding_reference_minor']} | {', '.join(x['blockers']) or '—'} |")
 lines += ["","## Currency buckets",""]
 for cur,b in ledger["summary"]["currency_buckets"].items(): lines.append(f"- **{cur}** — claims {b['claim_count']}; reference {b['reference_amount_minor']}; gross receipt evidence {b['gross_received_minor']}; reversals {b['reversed_minor']}; net receipt evidence {b['net_received_minor']}; outstanding reference {b['outstanding_reference_minor']}")
 lines += ["","## Authority boundary","","The ledger binds each evidence row to one exact canonical event and rejects duplicate external-source identity aliases. It does not authenticate a bank/provider merely because a caller supplied a digest or authority label. It never sends an invoice or payment request, contacts a buyer/sponsor, mutates a bank/payment provider, determines a legally enforceable debt, performs accounting/tax treatment, or recognizes revenue. Currency buckets are never combined with implicit FX.",""]; return "\n".join(lines)
def render_csv(ledger:Mapping[str,Any])->str:
 b=io.StringIO(newline=""); w=csv.writer(b,lineterminator="\n"); cols=["claim_id","claim_kind","currency","reference_amount_minor","state","gross_received_minor","reversed_minor","net_received_minor","outstanding_reference_minor","blockers"]; w.writerow(cols)
 for x in ledger["claims"]: w.writerow([x[k] if k!="blockers" else ";".join(x[k]) for k in cols])
 return b.getvalue()
def verify_ledger(packet,candidate):
 ok=type(candidate) is dict and candidate==compile_ledger(packet); return ok,"verified" if ok else "candidate ledger does not match deterministic recomputation"
def _load_json_strict(path):
 def pairs(rows):
  out={}
  for k,v in rows:
   if k in out: raise ValueError(f"duplicate JSON key: {k}")
   out[k]=v
  return out
 with Path(path).open("r",encoding="utf-8") as f: return json.load(f,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(f"invalid JSON constant {x}")))
def _write_exclusive(path,text):
 p=Path(path)
 if p.is_symlink(): raise FileExistsError(f"refusing symlink output: {p}")
 with p.open("x",encoding="utf-8",newline="") as f: f.write(text)
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__); s=p.add_subparsers(dest="command",required=True); c=s.add_parser("compile"); c.add_argument("--input",required=True); c.add_argument("--json-out",required=True); c.add_argument("--markdown-out"); c.add_argument("--csv-out"); c.add_argument("--fail-on-hold",action="store_true"); v=s.add_parser("verify"); v.add_argument("--input",required=True); v.add_argument("--ledger",required=True); a=p.parse_args(argv)
 if a.command=="compile":
  ledger=compile_ledger(_load_json_strict(a.input)); _write_exclusive(a.json_out,json.dumps(ledger,indent=2,sort_keys=True,ensure_ascii=False)+"\n")
  if a.markdown_out: _write_exclusive(a.markdown_out,render_markdown(ledger))
  if a.csv_out: _write_exclusive(a.csv_out,render_csv(ledger))
  return 2 if a.fail_on_hold and ledger["summary"]["state_counts"]["HOLD"] else 0
 ok,msg=verify_ledger(_load_json_strict(a.input),_load_json_strict(a.ledger)); print(msg); return 0 if ok else 3
if __name__=="__main__": raise SystemExit(main())
