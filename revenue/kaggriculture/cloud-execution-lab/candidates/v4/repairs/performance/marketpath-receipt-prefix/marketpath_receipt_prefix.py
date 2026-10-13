# SPDX-License-Identifier: Apache-2.0
"""Bounded exact receipt-prefix reuse for the existing MarketPath class.

A source transformer, not a runtime installer. Only two pinned methods are
replaced, so unrelated scheduler-prefix repairs can compose without rollback.
No policy objective, plan ordering, configuration, or deadline is changed.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

# Filled from the exact current scheduler, not from an approximate reimplementation.
PREIMAGE_SINGLE = '41c9f5a278d7d3d18243c6ca5c02ff028ef5126fbe9984fbbf3072da9379a623'
PREIMAGE_JOINT = '9a42479d2bb22fdb2e77178e68e8c25156bc776aceed001256ea59f4960e08b4'

SERIES = '''    def _receipt_series(self, inv, quantity, stride, floating):
        # Private to one MarketPath; at most 64 origins/modes, 101 entries each.
        # Keep sequential float accumulation for the legacy single-stream API;
        # paired quotes accumulate integers. These are not interchangeable for
        # large customized prices even when every quote itself is an integer.
        cache = getattr(self, '_receipt_prefixes', None)
        if cache is None:
            cache = self._receipt_prefixes = {}
        key = (inv, stride, floating)
        rows = cache.get(key)
        if rows is None:
            if len(cache) >= 64:
                cache.pop(next(iter(cache)))
            rows = [(0.0 if floating else 0, inv)]
            cache[key] = rows
        while len(rows) <= quantity:
            cash, current = rows[-1]
            price = self.quote(current)
            if floating:
                price = receipt_math._number(price)
            rows.append((cash + price, current + stride if price > 1 else current))
        return rows[quantity]
'''

SINGLE_PREFIX = '''        if (type(inv) is int and abs(inv) <= 2**52
                and type(quantity) is int and 0 <= quantity <= 100):
            if quantity == 0:
                return 0, inv
            cash, end = self._receipt_series(inv, quantity, 1, True)
            return int(cash), end
'''

JOINT_PREFIX = '''        if type(own) is int and type(rival) is int and own == 0 and rival == 0:
            return 0, 0, inv
        if (type(inv) is int and abs(inv) <= 2**52
                and type(own) is int and type(rival) is int
                and 0 <= own <= 100 and 0 <= rival <= 100):
            if own == 0:
                cash, current = self._receipt_series(inv, rival, 1, False)
                return 0, cash, current
            if rival == 0:
                cash, current = self._receipt_series(inv, own, 1, False)
                return cash, 0, current
            shared, current = self._receipt_series(inv, min(own, rival), 2, False)
            tail, current = self._receipt_series(current, abs(own-rival), 1, False)
            if own >= rival:
                return shared + tail, shared, current
            return shared, shared + tail, current
'''


def digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def methods(source: str):
    """Find exactly one top-level MarketPath and its unique methods."""
    tree = ast.parse(source)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MarketPath']
    if len(classes) != 1:
        raise ValueError('expected exactly one top-level MarketPath')
    nodes = {}
    lines = source.splitlines(keepends=True)
    for node in classes[0].body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in nodes:
                raise ValueError('duplicate MarketPath method: ' + node.name)
            if node.decorator_list and node.name in ('_single', '_joint', '_receipt_series'):
                raise ValueError('decorated receipt method is not supported')
            nodes[node.name] = (node, ''.join(lines[node.lineno-1:node.end_lineno]))
    return nodes


def transform(source: str) -> str:
    """Fail closed on source drift; preserve every byte outside target methods."""
    nodes = methods(source)
    if '_single' not in nodes or '_joint' not in nodes:
        raise ValueError('missing MarketPath receipt methods')
    single, joint = nodes['_single'][1], nodes['_joint'][1]
    if '_receipt_series' in nodes:
        # Idempotence still authenticates the complete postimage of all methods.
        old_single = single.replace(SINGLE_PREFIX, '', 1)
        old_joint = joint.replace(JOINT_PREFIX, '', 1)
        if (single.count(SINGLE_PREFIX) == 1 and joint.count(JOINT_PREFIX) == 1
                and digest(old_single) == PREIMAGE_SINGLE
                and digest(old_joint) == PREIMAGE_JOINT
                and nodes['_receipt_series'][1] == SERIES):
            return source
        raise ValueError('unrecognized existing receipt-prefix implementation')
    if digest(single) != PREIMAGE_SINGLE or digest(joint) != PREIMAGE_JOINT:
        raise ValueError('MarketPath receipt preimage mismatch')
    line = single.index('\n') + 1
    new_single = single[:line] + SINGLE_PREFIX + single[line:]
    anchor = '        cash=other=0\n'
    if joint.count(anchor) != 1:
        raise ValueError('joint loop anchor is not unique')
    new_joint = joint.replace(anchor, JOINT_PREFIX + anchor)
    edits = [(nodes['_single'][0], SERIES + '\n' + new_single),
             (nodes['_joint'][0], new_joint)]
    lines = source.splitlines(keepends=True)
    for node, replacement in sorted(edits, key=lambda pair: pair[0].lineno, reverse=True):
        lines[node.lineno-1:node.end_lineno] = [replacement]
    result = ''.join(lines)
    compile(result, '<MarketPath receipt-prefix candidate>', 'exec')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('source and output must differ; this tool does not patch production in place')
    source = args.source.read_bytes().decode('utf-8')
    result = transform(source).encode('utf-8')
    # Exclusive creation prevents destroying an existing candidate or receipt.
    with args.output.open('xb') as handle:
        handle.write(result)
    print(hashlib.sha256(result).hexdigest())


if __name__ == '__main__':
    main()
