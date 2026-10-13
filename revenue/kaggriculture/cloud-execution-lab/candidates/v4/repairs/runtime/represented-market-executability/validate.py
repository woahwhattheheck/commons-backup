# SPDX-License-Identifier: Apache-2.0
"""Run semantic fault controls and exact UNITFLOW composition without peer copies."""
from __future__ import annotations
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import types
import unittest
from compose import compose_source, git_blob

UNITFLOW_BLOB='e1127c4aad842278a9e617903b0718d21c00f348'
MUTATIONS={
    'free_variable_price':("price = m.market_price(item, inventory, market.get('params'))",'price = 0'),
    'ignore_shed_cap':("cap = int(config.get('shedCapacity', 100))\n    hire_mult",'cap = 10**6\n    hire_mult'),
    'illegal_product_purchase':("item not in ('WHEAT', 'FERTILIZER')",'item not in m.PRODUCTS'),
    'ignore_raw_prefix':('return orders[:limit] if isinstance(orders, list) else []',
                         'return orders if isinstance(orders, list) else []'),
    'prebuy_quote':("market['inventory'][item] - (op == 'BUY_PRODUCT')","market['inventory'][item]"),
    'skip_town_tick':("market['inventory'][item] -= absorption(item, step, shops, normalized)",
                     "market['inventory'][item] -= 0"),
    'skip_decay':('m._decay_plants(f,now)','pass  # mutant omits current decay'),
    'never_admit':('    config = config or {}\n','    return\n    config = config or {}\n'),
}


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--unitflow',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if git_blob(args.unitflow.read_bytes())!=UNITFLOW_BLOB:
        raise SystemExit('UNITFLOW dependency mismatch before import')
    unit=load(args.unitflow,'represented_unitflow')
    s=(args.package/'scheduler.py').read_text();f=(args.package/'frozen_selected.py').read_text()
    left=unit.compose_sources(s,compose_source(f))
    right=unit.compose_sources(s,f);right=(right[0],compose_source(right[1]))
    if left!=right:
        raise SystemExit('Composition does not commute byte-for-byte')
    result={'optimized':not __debug__,'unitflow_recipe_blob':UNITFLOW_BLOB,
            'commutes':True,'combined_scheduler_blob':git_blob(left[0].encode()),
            'combined_frozen_blob':git_blob(left[1].encode()),'mutants':{}}
    tests=load(Path(__file__).with_name('test_represented_market.py'),'represented_fault_tests')
    tests.ARGS=types.SimpleNamespace(package=args.package)
    for name,(old,new) in MUTATIONS.items():
        def changed(source,old=old,new=new):
            source=compose_source(source)
            if source.count(old)!=1:
                raise ValueError('Ambiguous fault injection')
            return source.replace(old,new,1)
        tests.compose_source=changed
        log=io.StringIO()
        with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
            run=unittest.TextTestRunner(stream=log).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(tests.MarketAdmission))
        result['mutants'][name]={'tests':run.testsRun,'failures':len(run.failures),
                               'errors':len(run.errors),
                               'assertion_rejected':len(run.failures)>0 and not run.errors}
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,sort_keys=True))
    if not all(x['assertion_rejected'] for x in result['mutants'].values()):
        raise SystemExit(1)


if __name__=='__main__':
    main()
