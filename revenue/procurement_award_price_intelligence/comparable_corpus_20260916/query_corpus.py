#!/usr/bin/env python3
"""Read-only exact-class query/demo for the retained corpus."""
from __future__ import annotations
import argparse
from collections import defaultdict
from decimal import Decimal
try:
    from .assemble_corpus import load_bundle
    from .validate_corpus import validate
except ImportError:
    from assemble_corpus import load_bundle
    from validate_corpus import validate

def money(minor:int,currency:str)->str: return f"{currency} {Decimal(minor)/Decimal(100):,.2f}"
def main(argv=None)->int:
    p=argparse.ArgumentParser(); p.add_argument("--corpus",default="revenue/procurement_award_price_intelligence/comparable_corpus_20260916/manifest.json"); p.add_argument("--buyer"); p.add_argument("--price-kind",choices=["AWARD","BID","OPTION","RENEWAL"]); p.add_argument("--ready-only",action="store_true"); a=p.parse_args(argv)
    corpus=load_bundle(a.corpus); validate(corpus); sources={r["id"]:r for r in corpus["sources"]}; rows=[]
    for row in corpus["records"]:
        buyer=sources[row["source_id"]]["buyer"]
        if a.buyer and buyer!=a.buyer: continue
        if a.price_kind and row["price_kind"]!=a.price_kind: continue
        if a.ready_only and row["promotability"]!="LIVE_ADAPTER_READY": continue
        rows.append((buyer,row))
    if not rows: print("NO_READY_COMPARABLES" if a.ready_only else "NO_MATCHES"); return 0
    groups=defaultdict(list)
    for buyer,row in rows: groups[(row["currency"],row["basis"],row["unit"],row["term_months"],row["price_kind"],row["promotability"])].append((buyer,row))
    for key in sorted(groups,key=str):
        currency,basis,unit,term,kind,readiness=key; print(f"class currency={currency} basis={basis} unit={unit} term_months={term} price_kind={kind} readiness={readiness}")
        for buyer,row in sorted(groups[key],key=lambda x:(x[0],x[1]["event_date"],x[1]["id"])): print(f"  {row['event_date']} | {buyer} | {row['opportunity_id']} | {row['vendor']} | {money(row['amount_minor'],currency)} | {row['id']}")
        if readiness=="LIVE_ADAPTER_READY":
            amounts=[r["amount_minor"] for _,r in groups[key]]; print(f"  READY_RANGE count={len(amounts)} min={money(min(amounts),currency)} max={money(max(amounts),currency)}")
        else: print("  RANGE_WITHHELD: raw buyer-source SHA is not yet bound by a live adapter receipt")
    return 0
if __name__=="__main__": raise SystemExit(main())
