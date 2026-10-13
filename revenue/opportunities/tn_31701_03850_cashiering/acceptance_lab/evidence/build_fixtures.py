"""Rebuild clearly synthetic examples; never contains State or customer data."""
import copy
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
scope = dict(agency="DEMO_AGENCY", business_unit="BU01", department="DEPT01", location="DEMO_OFFICE", bank_account="DEMO_BANK", currency="USD")

def batch(bid, opening, counted, net):
    return dict(id=bid, **scope, cashier="DEMO_USER", opened_at="2026-09-16T08:00:00-05:00", closed_at="2026-09-16T16:00:00-05:00", opening_cash_minor=opening, counted_cash_minor=counted, retained_cash_minor=opening, declared_total_minor=net, variance_reason=None)

def tx(tid, bid, time, original, rounding, collected, tenders, allocations, kind="RECEIPT", original_id=None):
    return dict(id=tid, batch_id=bid, kind=kind, timestamp=f"2026-09-16T{time}:00-05:00", original_id=original_id, original_minor=original, rounding_minor=rounding, collected_minor=collected, tenders=[dict(type=k,amount_minor=v) for k,v in tenders.items()], allocations=[dict(account_id=k,amount_minor=v) for k,v in allocations.items()], evidence_ref=f"SYNTHETIC_ROW_{tid}")

clean = dict(schema="cashiering-acceptance/1",case_id="SYNTHETIC_CLEAN",period=dict(start="2026-09-16T00:00:00-05:00",end="2026-09-17T00:00:00-05:00"),currency_scale=dict(USD=2),variance_reason_threshold_minor=20,
    batches=[batch("B1",10000,18500,12500),batch("B2",5000,9000,4000)],
    transactions=[tx("T1","B1","09:00",10002,-2,10000,dict(CASH=6000,CARD=4000),dict(FEES=8000,SERVICES=2000)),tx("T2","B1","10:00",3000,0,3000,dict(CASH=3000),dict(FEES=3000)),tx("T3","B1","11:00",-500,0,-500,dict(CASH=-500),dict(FEES=-500),"REFUND","T1"),tx("T4","B2","10:00",4001,-1,4000,dict(CASH=4000),dict(FEES=4000))],
    deposits=[dict(id="D_CASH",**scope,tender="CASH",batch_ids=["B1","B2"],observed_minor=12500,variance_reason=None,evidence_ref="SYNTHETIC_DEPOSIT_CASH"),dict(id="D_CARD",**scope,tender="CARD",batch_ids=["B1"],observed_minor=4000,variance_reason=None,evidence_ref="SYNTHETIC_DEPOSIT_CARD")])
exceptions = copy.deepcopy(clean)
exceptions["case_id"] = "SYNTHETIC_EXCEPTIONS"
exceptions["batches"][0]["counted_cash_minor"] -= 25
exceptions["batches"][0]["declared_total_minor"] += 50
exceptions["deposits"][0]["observed_minor"] -= 50
exceptions["transactions"][1]["allocations"][0]["amount_minor"] -= 100
for name, obj in (("clean",clean),("exceptions",exceptions)):
    (ROOT / "examples" / f"{name}.json").write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
