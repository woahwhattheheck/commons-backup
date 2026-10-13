#!/usr/bin/env python3
"""Export independently enumerated finite-pool inputs for another DP implementation.

No compiled solver, routing heuristic or reference DP is called by this exporter.
"""
from __future__ import annotations
import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
from test_temporal_dp import cases, exhaustive


def export(output: Path) -> dict:
    bank = cases()
    rows = []
    enumerated = 0
    for i, case in enumerate(bank):
        optimum, count = exhaustive(case)
        enumerated += count
        rows.append({'case_id': i, 'available': [[bool(x[0]) for x in row] for row in case['rows']],
                     'descending_loads': [[x[1] for x in row] for row in case['rows']],
                     'transition_costs': case['costs'], 'residual_budgets': case['budget'],
                     'expected_status': 'infeasible' if optimum is None else 'complete',
                     'expected_descending_loads': optimum})
    raw = b''.join((json.dumps(row, separators=(',', ':'), sort_keys=True)+'\n').encode() for row in rows)
    compressed = gzip.compress(raw, mtime=0)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(compressed)
    receipt = {'schema':'kestrel.temporal-oracle-bank.v1', 'generator_seed':41821,
               'cases':len(rows), 'enumerated_paths':enumerated,
               'feasible_cases':sum(r['expected_status']=='complete' for r in rows),
               'infeasible_cases':sum(r['expected_status']=='infeasible' for r in rows),
               'gzip_sha256':sha256(compressed).hexdigest(),'gzip_bytes':len(compressed),
               'decoded_sha256':sha256(raw).hexdigest(),'decoded_bytes':len(raw),
               'expected_value_source':'Exhaustive Python enumeration; no native DP or policy call',
               'limits':'Synthetic finite-menu algebra; arbitrary nonnegative transition matrices, not an official graph corpus.'}
    output.with_suffix('.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(export(args.output),indent=2))

if __name__=='__main__':main()
