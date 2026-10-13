"""Extract unchanged Apache-2.0 engine primitives for a dependency-free policy."""
import ast
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'reference/engine/kaggriculture.py'
ENGINE_SHA256 = 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e'
NAMES = {'CROPS','ANIMALS','PRODUCTS','MARKET_I0','PRICE_FLOOR','MARKET_PARAMS','HINGE_GAIN',
         'FARMER_MOVES','LAND_ORDER','LAND_PRICES','FARM_HAND_COST_MULT','SHOPS','TOWN_CENTER_PRODUCTS',
         '_shape','_resolve_market_params','get','market_price','_new_plant','_new_animal',
         '_shed_access_tiles','_is_shed_adjacent','_default_spawn','_quadrant_of',
         '_farmer_position','_set_farmer_position','_farmer_inventory','_inv_add','_inv_take',
         '_apply_unit_action','_drop_inventories_to_shed','_daily_refresh_plants','_daily_refresh_animals',
         '_decay_plants','_fib','_hire_cost','_spawn_hand','_do_hire','_do_buy_land','_commit_unit'}


def _pinned_source():
    """Return the exact reviewed engine source, including under optimized Python."""
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if digest != ENGINE_SHA256:
        raise RuntimeError(
            f'engine source hash mismatch: expected {ENGINE_SHA256}, got {digest}'
        )
    return SOURCE.read_text()


def main():
    source=_pinned_source()
    blocks=[]
    for node in ast.parse(source).body:
        names={node.name} if isinstance(node,(ast.FunctionDef,ast.ClassDef)) else {t.id for t in node.targets if isinstance(t,ast.Name)} if isinstance(node,ast.Assign) else set()
        if names & NAMES:
            blocks.append(ast.get_source_segment(source,node))
    header='''# SPDX-License-Identifier: Apache-2.0
# Mechanically extracted, unmodified definitions from Kaggle/kaggle-environments
# commit28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c kaggriculture.py.
# Full license: reference/engine/LICENSE. Extraction: build_mechanics.py.
# Only observable deterministic primitives; no initialization, RNG or interpreter.
import math

'''
    (HERE/'mechanics.py').write_text(header+'\n\n\n'.join(blocks)+'\n')
    print('mechanics.py',hashlib.sha256((HERE/'mechanics.py').read_bytes()).hexdigest())


def terminal_market():
    """Add exact native market definitions without changing frozen mechanics."""
    source=_pinned_source()
    names={'_process_market','_parse_order','_refresh_prices'}
    blocks=[ast.get_source_segment(source,n) for n in ast.parse(source).body
            if isinstance(n,ast.FunctionDef) and n.name in names]
    header='# SPDX-License-Identifier: Apache-2.0\n# Exact official engine 28b6d8af definitions; see reference/engine/LICENSE.\nimport mechanics as _base\nglobals().update({k:v for k,v in vars(_base).items() if not k.startswith("__")})\n\n'
    (HERE/'reference/titan-history/terminal_mechanics.py').write_text(header+'\n\n'.join(blocks)+'\n')

if __name__=='__main__':
    import sys
    terminal_market() if '--terminal-market' in sys.argv else main()
