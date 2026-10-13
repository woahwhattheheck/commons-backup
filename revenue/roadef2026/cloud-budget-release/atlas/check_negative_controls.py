#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the actual native invariant suite against five deliberately bad headers."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from test_native_invariants import HEADER_BLOB, blob, sha


def alter(source, old, new):
    if source.count(old)!=1: raise ValueError('mutation anchor must be unique')
    return source.replace(old,new,1)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fleet-source',type=Path,required=True)
    p.add_argument('--header',type=Path,required=True)
    p.add_argument('--vendor',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cxx',default='g++')
    args=p.parse_args()
    source=args.header.read_bytes()
    if blob(source)!=HEADER_BLOB: raise ValueError('original header pin differs')
    text=source.decode()
    mutations={
        'only_first_slot':(alter(text,'for (int t = left; t <= right; ++t)',
                              'for (int t = left; t <= left; ++t)'),
                          'returned route changes exact ECMP flow'),
        'summed_budget_only':(alter(text,'worse |= after[t] > used[t] || after[t] < 0;',
                                       'worse |= after[t] < 0;'),
                             'a transition cost increased'),
        'ignore_flow_equality':(alter(text,'projected != flows[base + t]','false'),
                               'returned route changes exact ECMP flow'),
        'allow_no_budget_gain':(alter(text,'if (worse || !strict)', 'if (worse)'),
                               'budget did not strictly improve'),
    }
    late=alter(text,'                    if (stop()) { counts.stopped = true; return std::nullopt; }\n                }\n                if (!same)',
                    '                }\n                if (!same)')
    late=alter(late,'                if (stop()) { counts.stopped = true; return std::nullopt; }\n                return Proposal<Route>',
                    '                return Proposal<Route>')
    mutations['ignore_late_stop']=(late,'proposal returned after callback deadline')
    args.output.mkdir(parents=True,exist_ok=False)
    receipts=[]
    for name,(mutant,expected) in mutations.items():
        folder=args.output/name;folder.mkdir()
        header=folder/'budget_release.hpp';header.write_text(mutant)
        report=folder/'result.json'
        command=[sys.executable,str(Path(__file__).with_name('test_native_invariants.py')),
                 '--fleet-source',str(args.fleet_source.resolve()),'--header',str(header.resolve()),
                 '--expected-header-blob',blob(header.read_bytes()),'--vendor',str(args.vendor.resolve()),
                 '--report',str(report.resolve()),'--cxx',args.cxx]
        run=subprocess.run(command,capture_output=True,timeout=90)
        (folder/'stdout.log').write_bytes(run.stdout);(folder/'stderr.log').write_bytes(run.stderr)
        result=json.loads(report.read_bytes())
        passed=run.returncode==1 and result['tests_run']==12 and result['failures']>0 \
               and result['errors']==0 and expected.encode() in run.stderr
        row=dict(name=name,detected=passed,expected=expected,returncode=run.returncode,
                 header_blob=blob(header.read_bytes()),header_sha256=sha(header.read_bytes()),
                 tests_run=result['tests_run'],failures=result['failures'],errors=result['errors'])
        receipts.append(row);print(json.dumps(row),flush=True)
        if not passed: raise RuntimeError('control not detected for expected reason: '+name)
    (args.output/'summary.json').write_text(json.dumps(dict(successful=True,controls=receipts,
        original_header_blob=HEADER_BLOB,scope='deliberately altered algorithm fixtures, not production'),
        indent=2,sort_keys=True)+'\n')
if __name__=='__main__':main()
