"""Reproducible synthetic throughput measurement, not a production capacity claim."""
from __future__ import annotations
import argparse
import hashlib
import json
import platform
from pathlib import Path
import random
import resource
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cashiering_lab.artifacts import bundle, write_bundle, verify

p=argparse.ArgumentParser(); p.add_argument('--transactions',type=int,default=1000); args=p.parse_args()
if not 1 <= args.transactions <= 15000: p.error('transactions must be 1..15000')
data=json.loads((ROOT/'examples/clean.json').read_bytes()); data['case_id']=f'SYNTHETIC_BENCH_{args.transactions}'; data['batches']=data['batches'][:1]; data['transactions']=[]; data['deposits']=[]
b=data['batches'][0]; total=cash=card=0; rng=random.Random(20260917)
for i in range(args.transactions):
    amount=rng.randint(100,100000); cm=rng.randint(0,amount); adjustment=rng.randint(-4,4); a=rng.randint(0,amount)
    data['transactions'].append(dict(id=f'R{i:05}',batch_id='B1',kind='RECEIPT',timestamp='2026-09-16T09:00:00-05:00',original_id=None,original_minor=amount-adjustment,rounding_minor=adjustment,collected_minor=amount,tenders=[dict(type='CASH',amount_minor=cm),dict(type='CARD',amount_minor=amount-cm)],allocations=[dict(account_id='A',amount_minor=a),dict(account_id='B',amount_minor=amount-a)],evidence_ref=f'SYNTHETIC_ROW_{i:05}'))
    total+=amount;cash+=cm;card+=amount-cm
b['declared_total_minor']=total;b['counted_cash_minor']=b['opening_cash_minor']+cash
for tender,amount in [('CASH',cash),('CARD',card)]:
    data['deposits'].append(dict(id=f'D_{tender}',**{k:b[k] for k in ('agency','business_unit','department','location','bank_account','currency')},tender=tender,batch_ids=['B1'],observed_minor=amount,variance_reason=None,evidence_ref=f'SYNTHETIC_DEPOSIT_{tender}'))
raw=(json.dumps(data,sort_keys=True,separators=(',',':'))+'\n').encode()
start=time.perf_counter(); artifacts=bundle(raw); compile_s=time.perf_counter()-start
with tempfile.TemporaryDirectory() as td:
    target=Path(td)/'review';start=time.perf_counter();write_bundle(target,artifacts);write_s=time.perf_counter()-start
    start=time.perf_counter();result=verify(target);verify_s=time.perf_counter()-start
if result['findings_count'] != 0: raise SystemExit('unexpected finding in benchmark')
print(json.dumps(dict(label='SYNTHETIC_SINGLE_PROCESS_NOT_PRODUCTION_QUALIFICATION',transactions=args.transactions,input_bytes=len(raw),output_bytes=sum(map(len,artifacts.values())),compile_seconds=round(compile_s,6),write_seconds=round(write_s,6),verify_seconds=round(verify_s,6),peak_rss_kib_linux=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,python=platform.python_version(),platform=platform.platform(),input_sha256=hashlib.sha256(raw).hexdigest(),source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'cashiering_lab').glob('*.py'))},verification=result['verification']),sort_keys=True))
