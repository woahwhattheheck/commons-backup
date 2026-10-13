#!/usr/bin/env python3
"""Promote retained claims only after exact live-adapter source-byte custody."""
from __future__ import annotations
import argparse,json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any
from revenue.procurement_award_price_intelligence import adapters
from revenue.procurement_award_price_intelligence.comparable_corpus_20260916.assemble_corpus import load_bundle
from revenue.procurement_award_price_intelligence.comparable_corpus_20260916.validate_corpus import canonical,digest,validate
class HydrationError(ValueError): pass

def _request_for(source:dict[str,Any],records:list[dict[str,Any]],exclusions:list[dict[str,Any]])->dict[str,Any]:
    profile=source["profile"]
    if profile=="LEGISTAR_AWARD_HTML_V1":
        reviewed=[]; extraction={"mode":"LIVE_HTML","state":"EXACT","coverage":"COMPLETE_RECORD"}; allowed=["AWARD"]
    elif profile=="BUYER_BID_TABULATION_PDF_V1":
        extraction={"mode":"TABULAR_PDF_TEXT","state":"REVIEWED","coverage":"COMPLETE_TABLE"}; allowed=["BID"]; reviewed=[]
        for row in [*records,*exclusions]:
            if row["source_id"]!=source["id"]: continue
            reviewed.append({"record_id":row["id"],"claim_key":f"{row['opportunity_id']}:{row['vendor'].lower().replace(' ','-')}","opportunity_id":row["opportunity_id"],"vendor":row["vendor"],"amount_minor":row["amount_minor"],"currency":row["currency"],"basis":row["basis"],"unit":row["unit"],"term_months":row["term_months"],"event_date":row["event_date"],"disposition":row["source_disposition"]})
    else: raise HydrationError(f"unsupported profile {profile}")
    return {"schema":adapters.ADAPTER_INPUT,"dataset_id":f"comparable-corpus:{source['id']}","max_source_age_seconds":31536000,"truth_boundary":adapters.TRUTH_BOUNDARY,"source":{"profile":profile,"uri":source["uri"]},"lineage":{"relation":"ORIGINAL","sequence":0,"parent_source_sha256":None},"extraction":extraction,"records":reviewed,"target":{"target_id":f"comparable-corpus:{source['id']}","currency":"USD","basis":"CONTRACT_TOTAL","unit":None,"term_months":None,"allowed_price_kinds":allowed}}

def _key(row): return (row["observation_id"],row["opportunity_id"],row["vendor"],row["amount_minor"],row["currency"],row["basis"],row["unit"],row["term_months"],row["event_date"],row["price_kind"])
def _expected(row): return (row["id"],row["opportunity_id"],row["vendor"],row["amount_minor"],row["currency"],row["basis"],row["unit"],row["term_months"],row["event_date"],row["price_kind"])
def match_live_result(source,expected,normalized,receipt):
    if receipt.get("status")!="ADAPTER_READY": raise HydrationError(f"{source['id']}: adapter not ready: {receipt.get('status')}")
    raw_sha=receipt.get("source_sha256")
    if not isinstance(raw_sha,str) or len(raw_sha)!=64: raise HydrationError(f"{source['id']}: adapter receipt missing source SHA")
    if normalized.get("truth_boundary")!=adapters.TRUTH_BOUNDARY: raise HydrationError(f"{source['id']}: normalized truth boundary mismatch")
    live_sources=normalized.get("sources")
    if not isinstance(live_sources,list) or len(live_sources)!=1 or live_sources[0].get("sha256")!=raw_sha: raise HydrationError(f"{source['id']}: normalized/receipt source SHA mismatch")
    live_rows=normalized.get("observations")
    if not isinstance(live_rows,list) or {_key(r) for r in live_rows}!={_expected(r) for r in expected}: raise HydrationError(f"{source['id']}: live observations do not match retained claims")
    return raw_sha

def promote_source(corpus,source_id,raw_sha):
    result=deepcopy(corpus); source=next((r for r in result["sources"] if r["id"]==source_id),None)
    if source is None or source["raw_hash_state"]!="PENDING_LIVE_ADAPTER_FETCH": raise HydrationError(f"{source_id}: source is not pending")
    source["raw_hash_state"]="VERIFIED_LIVE_ADAPTER"; source["raw_source_sha256"]=raw_sha; source["snapshot_sha256"]=digest({k:v for k,v in source.items() if k!="snapshot_sha256"})
    for row in result["records"]:
        if row["source_id"]==source_id:
            row["promotability"]="LIVE_ADAPTER_READY"; row["claim_sha256"]=digest({k:v for k,v in row.items() if k!="claim_sha256"})
    sources={r["id"]:r for r in result["sources"]}; result["summary"]={"record_count":len(result["records"]),"source_count":len(result["sources"]),"exclusion_count":len(result["exclusions"]),"buyer_counts":dict(sorted(Counter(sources[r["source_id"]]["buyer"] for r in result["records"]).items())),"price_kind_counts":dict(sorted(Counter(r["price_kind"] for r in result["records"]).items())),"promotability_counts":dict(sorted(Counter(r["promotability"] for r in result["records"]).items())),"raw_hash_state_counts":dict(sorted(Counter(r["raw_hash_state"] for r in result["sources"]).items()))}; validate(result); return result

def main(argv=None)->int:
    p=argparse.ArgumentParser(); p.add_argument("--corpus",default="revenue/procurement_award_price_intelligence/comparable_corpus_20260916/manifest.json"); p.add_argument("--out-corpus",required=True); p.add_argument("--out-report",required=True); a=p.parse_args(argv)
    corpus=load_bundle(a.corpus); validate(corpus); working=deepcopy(corpus); report={"schema":"public-procurement-comparable-corpus-hydration/v1","source_operation":corpus["operation"],"sources":[],"authority":dict(corpus["authority"])}
    for source in corpus["sources"]:
        expected=[r for r in corpus["records"] if r["source_id"]==source["id"]]; request=_request_for(source,corpus["records"],corpus["exclusions"])
        try:
            normalized_bytes,receipt_bytes=adapters.compile_adapter(canonical(request)); normalized=json.loads(normalized_bytes); receipt=json.loads(receipt_bytes); raw_sha=match_live_result(source,expected,normalized,receipt); working=promote_source(working,source["id"],raw_sha); report["sources"].append({"source_id":source["id"],"status":"LIVE_ADAPTER_READY","source_sha256":raw_sha,"normalized_sha256":receipt["normalized_sha256"],"receipt_sha256":digest(receipt)})
        except Exception as exc: report["sources"].append({"source_id":source["id"],"status":"HOLD_LIVE_ADAPTER_FAILURE","error_type":type(exc).__name__,"error":str(exc)[:512]})
    validate(working); out_corpus=Path(a.out_corpus); out_report=Path(a.out_report)
    if out_corpus.exists() or out_report.exists(): raise HydrationError("output paths must not already exist")
    out_corpus.parent.mkdir(parents=True,exist_ok=True); out_report.parent.mkdir(parents=True,exist_ok=True); out_corpus.write_bytes(canonical(working)+b"\n"); out_report.write_bytes(canonical(report)+b"\n"); ready=sum(1 for r in report["sources"] if r["status"]=="LIVE_ADAPTER_READY"); print(json.dumps({"ready_sources":ready,"total_sources":len(report["sources"])},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
