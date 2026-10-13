#!/usr/bin/env python3
"""Source-bound custody witness for V233 FASTING wheat credit.

Consumes an immutable Kaggriculture engine source file. It authenticates the
expected official SHA-256, extracts the engine's actual inventory-drain function
from its AST and executes that exact function, then verifies the EOD source calls
that drain before hand/inventory reset. No candidate code or game is executed.
"""
from __future__ import annotations
import argparse, ast, hashlib, json
from pathlib import Path

ENGINE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"


def validate(path: Path):
    raw=path.read_bytes(); digest=hashlib.sha256(raw).hexdigest()
    if digest != ENGINE_SHA256:
        raise AssertionError(f"engine sha256 mismatch: {digest}")
    src=raw.decode('utf-8'); tree=ast.parse(src)
    funcs={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
    drain=funcs.get('_drop_inventories_to_shed'); eod=funcs.get('_end_of_day')
    if drain is None or eod is None: raise AssertionError('required engine functions missing')
    # Execute only the exact standalone drain function from the authenticated source.
    module=ast.Module(body=[drain],type_ignores=[]); ast.fix_missing_locations(module)
    ns={}; exec(compile(module,str(path),'exec'),ns,ns)
    private={'shed':{'WHEAT':3,'WOOL':1},'inventories':[{}, {'WHEAT':1}, {'WHEAT':1}]}
    ns['_drop_inventories_to_shed'](private,100)
    if private != {'shed':{'WHEAT':5,'WOOL':1},'inventories':[{}, {}, {}]}:
        raise AssertionError(f'unexpected nonfull drain: {private!r}')
    clipped={'shed':{'WOOL':99},'inventories':[{}, {'WHEAT':2}]}
    ns['_drop_inventories_to_shed'](clipped,100)
    if clipped != {'shed':{'WOOL':99,'WHEAT':1},'inventories':[{}, {}]}:
        raise AssertionError(f'unexpected full drain: {clipped!r}')
    eod_src=ast.get_source_segment(src,eod)
    order=['_drop_inventories_to_shed(private, shed_cap)', 'farm["hands"] = []', 'private["inventories"] = [{}]']
    positions=[eod_src.find(x) for x in order]
    if any(i < 0 for i in positions) or positions != sorted(positions):
        raise AssertionError(f'EOD custody order mismatch: {positions}')
    return {'schema':'titan.v4.v233-fasting-wheat-credit-engine/v1','engine_sha256':digest,
            'nonfull_saved_wheat_survives':2,'clipped_saved_wheat_survives':1,
            'eod_order':['drain_inventories_to_shed','dismiss_hands','reset_inventories'],
            'interpretation':'credit requires next-morning below-cap shed custody; full shed remains ambiguous/fail-closed'}


def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('engine',type=Path); a=p.parse_args(argv)
    print(json.dumps(validate(a.engine),sort_keys=True,separators=(',',':')))
    return 0
if __name__=='__main__': raise SystemExit(main())
