# SPDX-License-Identifier: MIT OR CC-BY-4.0
"""Extract exact pricing definitions and reuse pinned ROWAN temporal contracts."""
import ast
import hashlib
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ENGINE_BLOB = '3c202c7ee921da239356789e266b694635103fc4'
ROWAN_SHA256 = '000a7f5a4285942c6616a05786e0831f757fb69ba6e5fff51a65cb3e914b6d69'


def build(engine_path):
    raw = Path(engine_path).read_bytes()
    if hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest() != ENGINE_BLOB:
        raise ValueError('Official engine pin mismatch')
    rowan = (HERE.parent/'cloud-frontier-trace/events.py').read_bytes()
    if hashlib.sha256(rowan).hexdigest() != ROWAN_SHA256:
        raise ValueError('ROWAN contract changed; review and repin explicitly')
    source = raw.decode()
    names = {'CROPS','PRODUCTS','MARKET_I0','PRICE_FLOOR','MARKET_PARAMS','HINGE_GAIN',
             '_shape','market_price','SHOPS','TOWN_CENTER_PRODUCTS'}
    chunks=[]
    for node in ast.parse(source).body:
        name = node.name if isinstance(node,ast.FunctionDef) else (
            node.targets[0].id if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) else None)
        if name in names:
            chunks.append(ast.get_source_segment(source,node))
    # ROWAN has its own CROPS/ANIMALS tuple tables. Isolate their globals by module,
    # rather than accidentally replacing the engine's exact dictionaries.
    (HERE/'forecast_market_mechanics.py').write_text('# Exact selected definitions from Kaggle engine @28b6d8af; Apache-2.0.\nimport math\n\n'+'\n\n'.join(chunks)+'\n')
    (HERE/'forecast_events.py').write_bytes(rowan)


if __name__ == '__main__':
    build(sys.argv[1])
