# SPDX-License-Identifier: Apache-2.0
"""Compose known-town consumption into the native funding trace, without activation.

Only the authenticated _funding_trace span changes. All other source bytes,
including FUNDING-PERF's four method spans, are preserved. Unknown dawns are
not forecasts: a multi-day trace fails into the existing baseline-sale fallback.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
from pathlib import Path

BEFORE = 'd9ca4d0737b5ab3344c0df588014a83a5c634464327fdd175b8ec862c2d7beb9'
AFTER = '88d315a8e16a7a3f1aa2e88d65e53bad827ce2cee4b7fbef65fe4d192cdfdff6'
INIT_ANCHOR = '    acquisitions = []\n    executed_sales = []\n'
INIT = '''    # Only observed shop instances are evidence. Native SELL horizons are
    # same-day; do not certify a future dawn's unknown new shop or farm reset.
    if end > now:
        turns_per_day = max(1, int(config.get('turnsPerDay', 24)))
        if now // turns_per_day != end // turns_per_day:
            raise ValueError('funding town trace cannot cross an unobserved dawn')
        shop_interval = max(1, int(config.get('townShopSellInterval', 4)))
        center_interval = max(1, int(config.get('townCenterSellInterval', 24)))
        shop_demand = {}
        for shop in obs.get('town', {}).get('unlocked_shops', []):
            products = m.SHOPS[shop]
            amount = 2 if len(products) == 1 else 1
            for product in products:
                shop_demand[product] = shop_demand.get(product, 0) + amount
'''
BUY_SCAN = "            if o and len(o) > 2 and o[0] == 'BUY_PRODUCT':\n"
BUY_SCAN_FIXED = "            if (o and len(o) > 2 and o[0] == 'BUY_PRODUCT'\n                    and o[1] in ('WHEAT', 'FERTILIZER')):\n"
BUY_BRANCH = "            elif op == 'BUY_PRODUCT' and len(order) > 2 and item in m.PRODUCTS:\n"
BUY_GUARD = '''                # The official per-unit quote stage rejects other products.
                # Keep the diagnostic raw-row zero, but invent no fill or cash use.
                if item not in ('WHEAT', 'FERTILIZER'):
                    acquisitions.append(((t, index, op, item), 0))
                    continue
'''
RETURN_ANCHOR = "    return {'cash': int(f['money']), 'acquisitions': acquisitions,\n"
TOWN = '''        # Official order is our market, then town, then the next callback.
        # The final town phase cannot change the requested market-fill receipt.
        # Preserve duplicate shop multiplicity and the fertilizer exclusion.
        if t < end:
            if t % shop_interval == 0:
                for product, amount in shop_demand.items():
                    inventory[product] -= amount
            if t % center_interval == 0:
                for product in m.TOWN_CENTER_PRODUCTS:
                    inventory[product] -= 1
'''


def span(source: str) -> tuple[int, int]:
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    nodes = [n for n in ast.parse(source).body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name == '_funding_trace']
    if len(nodes) != 1:
        raise ValueError('exactly one top-level _funding_trace is required')
    node = nodes[0]
    first = min([node.lineno] + [d.lineno for d in node.decorator_list])
    return offsets[first - 1], offsets[node.end_lineno]


def apply(source: str) -> str:
    """Return a fully validated composition; reject changed method preimages."""
    start, end = span(source)
    part = source[start:end]
    digest = hashlib.sha256(part.encode('utf-8')).hexdigest()
    if digest == AFTER:
        return source
    if digest != BEFORE:
        raise ValueError('funding trace changed; explicitly compose and revalidate its owners')
    if part.count(INIT_ANCHOR) != 1 or part.count(RETURN_ANCHOR) != 1:
        raise ValueError('town funding anchors are not unique')
    if part.count(BUY_SCAN) != 1 or part.count(BUY_BRANCH) != 1:
        raise ValueError('product eligibility anchors are not unique')
    part = part.replace(BUY_SCAN, BUY_SCAN_FIXED, 1)
    part = part.replace(BUY_BRANCH, BUY_BRANCH + BUY_GUARD, 1)
    part = part.replace(INIT_ANCHOR, INIT_ANCHOR + INIT, 1)
    part = part.replace(RETURN_ANCHOR, TOWN + RETURN_ANCHOR, 1)
    if hashlib.sha256(part.encode()).hexdigest() != AFTER:
        raise ValueError('unexpected town funding postimage')
    result = source[:start] + part + source[end:]
    compile(result, '<town-funding-composed>', 'exec')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('use a separate scratch output; source is never modified')
    result = apply(args.source.read_bytes().decode('utf-8')).encode('utf-8')
    # Exclusive creation: a failed pin or an existing file never destroys bytes.
    with args.output.open('xb') as handle:
        handle.write(result)
    print(hashlib.sha256(result).hexdigest())


if __name__ == '__main__':
    main()
