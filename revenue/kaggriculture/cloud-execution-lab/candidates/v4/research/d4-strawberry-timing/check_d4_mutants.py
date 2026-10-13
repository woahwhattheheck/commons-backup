# SPDX-License-Identifier: Apache-2.0
"""Behavioral broken-variant checks; infrastructure errors never count as kills."""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path
import sys
import types
import unittest

import test_native_d4 as tests

HERE=Path(__file__).resolve().parent


def suite():
    result=unittest.TestSuite()
    for cls in (tests.HorizonTests,tests.NativeEngineTests):
        result.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
    return result


def execute():
    stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream,verbosity=0).run(suite())
    return dict(tests=result.testsRun,failures=[t.id()for t,_ in result.failures],
                errors=[t.id()for t,_ in result.errors],skips=len(result.skipped),log=stream.getvalue())


def run():
    source=(HERE/'native_d4.py').read_text()
    original=tests.d4
    good=execute()
    if good['failures']or good['errors']or good['skips']:
        raise AssertionError('Unmodified behavioral control is not green')
    faults={
        'day_window':('if not 12 * 24 <= now < 19 * 24 or now >= last:', 'if now >= last:'),
        'raw_prefix':('for order in orders[:cap]:','for order in orders:'),
        'checkpoint':('stop = min(last, hard_end, (now // 24 + 1) * 24 - 1)','stop = min(last, (now // 24 + 1) * 24 - 1)'),
        'pickup':('if command[:2] == ["PICKUP", ITEM]:','if command[:2] == ["NOT_PICKUP", ITEM]:'),
        'price':('if type(price) is not int or price < min_price:','if type(price) is not int or price < 2:'),
        'stock_bound':('"represented_units": min(stock, quantity),','"represented_units": quantity,'),
        'current_capacity':('if current and len(orders) >= cap:','if False:'),
        'incumbent_sale':('if quantity and due <= item_end:','if False:'),
    }
    rows=[]
    for name,(old,new)in faults.items():
        if source.count(old)!=1:raise AssertionError('Mutation seam changed: '+name)
        module=types.ModuleType('native_d4');module.__file__=str(HERE/'native_d4.py')
        exec(compile(source.replace(old,new,1),module.__file__,'exec'),module.__dict__)
        sys.modules['native_d4']=module;tests.d4=module
        result=execute();result['fault']=name
        rows.append(result)
        sys.modules['native_d4']=original;tests.d4=original
        if result['errors']or result['skips']or not result['failures']:
            raise AssertionError('Fault did not die by a behavioral assertion: '+name)
    prior=tests.candidate
    tests.candidate=tests.unanchored_control()
    result=execute();result['fault']='unanchored_counterfactual';rows.append(result)
    tests.candidate=prior
    if result['errors']or result['skips']or not result['failures']:
        raise AssertionError('Unanchored counterfactual was not assertion-rejected')
    return {'green_control':good,'faults':rows}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();result=run();a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'green_tests':result['green_control']['tests'],'faults_rejected':len(result['faults']),
        'infrastructure_errors':sum(len(r['errors'])for r in result['faults'])},sort_keys=True))
