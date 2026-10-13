# SPDX-License-Identifier: Apache-2.0
"""Compose D4 into an existing native package without a legacy R04 materializer."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Exact method input hashes, filled from the authenticated b567 native package.
METHODS = {'features': {'class': 'Features', 'method': None, 'input': 'd3525d02f1b853aa1fd59a6f4a5d82f587868e6e7f79a936275362347e598f22', 'output': '9a3ffb1d010ec06f1f3671c8f760092e31246734365603626458d50ee327a1e3'}, 'initialize': {'class': 'TitanAgent', 'method': '_initialize', 'input': 'fc5e8ed590703bc9506b3b1a3e67873d60d2e56d7ab13789989c44be61296aee', 'output': 'bf366cd7dc0e4709dbbe3d88da0cc9ae3995cb61c4ca5e73a57d1b0f9ebe45fb'}, 'transform': {'class': 'FrozenSelected', 'method': 'transform', 'input': '593ef59a03a3e9a54d001ab12edc7c11ca0c803f20759f5b51b2c82d036457ea', 'output': '11d318269352bc894070e0007d7be6edddf1ed3cbd09fa6f7fa2c8f9959c52c9'}}
HELPER_SHA256 = '3ae9e172acd2693419f6c1636618830e41eabeb3dc8a728bc025cacae634d7ac'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def span(source, cls, method=None):
    rows = source.splitlines(keepends=True)
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    if method is not None:
        node = next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == method)
    return sum(map(len, rows[:node.lineno-1])), sum(map(len, rows[:node.end_lineno]))


FEATURE_FIELDS = """    # The preserved D4 key is native-only here; shipped OFF.
    r04_d4_strawberry_timing: bool = False
    r04_d4_strawberry_min_price: int = 180
"""
FEATURE_GUARD = """        if type(self.r04_d4_strawberry_timing) is not bool:
            raise ValueError('D4 enable must be an exact bool')
        if type(self.r04_d4_strawberry_min_price) is not int or self.r04_d4_strawberry_min_price < 2:
            raise ValueError('D4 minimum price must be an exact integer >= 2')
        if self.r04_d4_strawberry_timing and (self.consumer != 'frozen' or self.terminal_route):
            raise ValueError('D4 requires native nonterminal frozen SELL')
"""
INIT_FLAGS = """            self.consumer.r04_d4_strawberry_timing = f.r04_d4_strawberry_timing
            self.consumer.r04_d4_strawberry_min_price = f.r04_d4_strawberry_min_price
"""
TRANSFORM_SETUP = """        d4_end = None
        if getattr(self, 'r04_d4_strawberry_timing', False):
            from native_d4 import sale_horizon
            inherited_end = max(horizon['baseline_end'],
                horizon['service_dates'].get('STRAWBERRY', horizon['baseline_end']),
                horizon['unit_event'] or horizon['baseline_end'])
            d4 = sale_horizon(enabled=True, now=now, last=last, route=route,
                action=base, stock=shed.get('STRAWBERRY', 0),
                price=obs['market']['prices'].get('STRAWBERRY'),
                item_end=inherited_end, hard_end=horizon['hard_end'],
                max_orders=config.get('maxMarketOrdersPerTurn', 10),
                turns_per_day=config.get('turnsPerDay', 24),
                min_price=getattr(self, 'r04_d4_strawberry_min_price', 180))
            self.diagnostics['d4'] = d4
            d4_end = d4['due']
            if d4_end is not None:
                end = max(end, d4_end)
                horizon['extended'] = end > horizon['baseline_end']
"""
ITEM_END = """            reference_end = item_end
            if item == 'STRAWBERRY' and d4_end is not None:
                item_end = max(item_end, d4_end)
"""


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Native seam is missing or ambiguous')
    return source.replace(old, new, 1)


def patch_segment(key, segment):
    if key == 'features':
        segment = replace_once(segment, '    def __post_init__(self):\n',
                               FEATURE_FIELDS + '\n    def __post_init__(self):\n' + FEATURE_GUARD)
    elif key == 'initialize':
        segment = replace_once(segment, '            self.consumer = FrozenSelected()\n',
                               '            self.consumer = FrozenSelected()\n' + INIT_FLAGS)
    elif key == 'transform':
        segment = replace_once(segment, "        budget=self.cash_reserve(obs,config,base,end)\n",
                               TRANSFORM_SETUP + "        budget=self.cash_reserve(obs,config,base,end)\n")
        segment = replace_once(segment, '            dates=product_event_dates(item,now,item_end,shops,config)\n',
                               ITEM_END + '            dates=product_event_dates(item,now,item_end,shops,config)\n')
        # Extending candidate dates must not import a weaker late raw-tape
        # schedule into the reference. Keep exactly the incumbent reference
        # window, including its pending-plan clamp, for this item.
        segment = replace_once(segment, 'min(t,item_end),q));rem-=q',
                               'min(t,reference_end),q));rem-=q')
        segment = replace_once(segment, 'for t in range(now+1,item_end+1):',
                               'for t in range(now+1,reference_end+1):')
    else:
        raise ValueError('Unknown source seam')
    return segment


def compose_text(source, keys):
    for key in keys:
        pin = METHODS[key]
        a, b = span(source, pin['class'], pin['method'])
        piece = source[a:b]
        digest = sha(piece.encode())
        if digest == pin['output']:
            continue
        if digest != pin['input']:
            raise ValueError(f'Native {key} method drift: {digest}')
        changed = patch_segment(key, piece)
        if sha(changed.encode()) != pin['output']:
            raise ValueError('Composer output drift')
        source = source[:a] + changed + source[b:]
    return source


def compose(root, out):
    root, out = Path(root).resolve(), Path(out).resolve()
    if root == out:
        raise ValueError('Output must be a separate scratch directory')
    helper = (HERE/'native_d4.py').read_bytes()
    if sha(helper) != HELPER_SHA256:
        raise ValueError('D4 helper source mismatch')
    result = {}
    for name, keys in [('titan_runtime.py', ['features', 'initialize']),
                       ('frozen_selected.py', ['transform'])]:
        data = compose_text((root/name).read_text(), keys).encode()
        result[name] = data
    cfg = json.loads((root/'TITAN-CONFIG.json').read_text())
    # Never activate while composing. Explicit experiment configuration happens
    # separately, so assembling a source packet cannot silently promote it.
    if cfg.get('r04_d4_strawberry_timing', False) is not False:
        raise ValueError('Composition requires D4 OFF')
    cfg.setdefault('r04_d4_strawberry_timing', False)
    cfg.setdefault('r04_d4_strawberry_min_price', 180)
    result['TITAN-CONFIG.json'] = (json.dumps(cfg, indent=2, sort_keys=True)+'\n').encode()
    result['native_d4.py'] = helper
    for name, data in result.items():
        target = out/name
        if target.exists() and target.read_bytes() != data:
            raise ValueError(f'Would overwrite a different scratch file: {name}')
    out.mkdir(parents=True, exist_ok=True)
    for name, data in result.items():
        (out/name).write_bytes(data)
    return {name: sha(data) for name, data in result.items()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(compose(args.root, args.out), indent=2, sort_keys=True))
