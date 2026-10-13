# SPDX-License-Identifier: Apache-2.0
"""Compose admitted represented-market replay into the checked native V4 seller.

No legacy materializer, release/default changes, or whole-file donor replacement.
The replay is one passive-rival scenario, not a funding guarantee.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

NATIVE_BLOB = "fc7baf5c179818a55037f6a61d92984d81d1a21c"
MECHANICS_BLOB = "044a4f9c0a4a44dde10ada57563238bcaf82075d"
MARKET_BODY_SHA256 = "11d7c3c878d6f56d88500c9cd93978ca315627e5df0eaa5ab14fab498a5a2410"
REPLACEMENT = '''def represented_market_orders(orders, config):
    """Keep raw indexes, including malformed/empty slots, as the engine does."""
    limit = max(1, int(config.get('maxMarketOrdersPerTurn', 10)))
    return orders[:limit] if isinstance(orders, list) else []


def apply_represented_market(farm, private, orders, size, market=None, config=None):
    """Replay admitted own trades with no additional rival trades.

    Caller owns detached farm/private/market state. Fixed acquisitions require
    cash; products require a supplied market snapshot and real shed capacity.
    Without market context, SELL removes stock without granting unpriced cash,
    and variable-price buys do not execute. This is not a rival-proof forecast.
    """
    config = config or {}
    cap = int(config.get('shedCapacity', 100))
    hire_mult = int(config.get('farmHandCostMult', m.FARM_HAND_COST_MULT))
    for order in represented_market_orders(orders, config):
        if not isinstance(order, list) or not order:
            continue
        op = order[0]
        if op == 'HIRE':
            m._do_hire(farm, private, size, hire_mult)
            continue
        if op == 'BUY_LAND':
            m._do_buy_land(farm, size)
            continue
        if op not in ('SELL', 'BUY_PRODUCT', 'BUY_ANIMAL', 'BUY_SEED') or len(order) < 3:
            continue
        try:
            requested = int(order[2])
        except (TypeError, ValueError):
            continue
        item = order[1]
        if requested <= 0:
            continue
        if op == 'SELL' and item not in m.PRODUCTS:
            continue
        if op == 'BUY_PRODUCT' and item not in ('WHEAT', 'FERTILIZER'):
            continue
        if op == 'BUY_ANIMAL' and item not in m.ANIMALS:
            continue
        if op == 'BUY_SEED' and item not in m.CROPS:
            continue
        if market is None and op in ('SELL', 'BUY_PRODUCT'):
            if op == 'SELL':
                private['shed'][item] = max(0, private['shed'].get(item, 0) - requested)
            else:
                # Unpriced spend cannot finance later fixed acquisitions.
                farm['money'] = 0
            continue
        # The official engine's safety loop commits at most 99,999 units/order.
        for _ in range(min(requested, 99999)):
            if op in ('SELL', 'BUY_PRODUCT'):
                inventory = market['inventory'][item] - (op == 'BUY_PRODUCT')
                price = m.market_price(item, inventory, market.get('params'))
            elif op == 'BUY_ANIMAL':
                price = m.ANIMALS[item]['cost']
            else:
                price = m.CROPS[item]['seed']
            if not m._commit_unit(op, item, price, farm, private, market, cap):
                break


def advance_represented_market(market, step, shops, config):
    """Apply known post-market town demand to the detached scenario inventory."""
    if market is not None:
        normalized = dict(config)
        for key, default in (('townShopSellInterval', 4), ('townCenterSellInterval', 24)):
            normalized[key] = max(1, int(config.get(key, default)))
        for item in m.PRODUCTS:
            market['inventory'][item] -= absorption(item, step, shops, normalized)


'''


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError('Represented-market source anchor missing or ambiguous: ' + old[:80])
    return text.replace(old, new, 1)


def compose_source(source: str) -> str:
    """Patch exact method/callsite anchors; preserve unrelated peer seams."""
    tree = ast.parse(source)
    if 'def represented_market_orders(' in source:
        raise ValueError('Represented-market repair already/partly present')
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name == 'apply_represented_market']
    if len(nodes) != 1:
        raise ValueError('Native represented-market method missing/ambiguous')
    lines = source.splitlines(keepends=True)
    node = nodes[0]
    old = ''.join(lines[node.lineno-1:node.end_lineno])
    if hashlib.sha256(old.encode()).hexdigest() != MARKET_BODY_SHA256:
        raise ValueError('Represented-market method changed; review composition')
    source = replace_once(source, old, REPLACEMENT.rstrip() + '\n')
    source = replace_once(source, '                           current_market=None):',
                          '                           current_market=None, market=None, shops=()):')
    source = replace_once(source,
        "    apply_represented_market(f,p,current_market,size)\n",
        "    market = ({'inventory': dict(market['inventory']), 'params': market.get('params')}\n"
        "              if market is not None else None)\n"
        "    apply_represented_market(f,p,current_market,size,market,config)\n"
        "    advance_represented_market(market,now,shops,config)\n"
        "    m._decay_plants(f,now)\n")
    source = replace_once(source,
        "    turns_per_day=int(config.get('turnsPerDay',24))\n    for t in range(now+1,hard_end+1):",
        "    turns_per_day=int(config.get('turnsPerDay',24))\n"
        "    # Native horizon is same-day; do not fabricate unmodeled EOD state.\n"
        "    hard_end=min(hard_end,(now//turns_per_day+1)*turns_per_day-1)\n"
        "    for t in range(now+1,hard_end+1):")
    source = replace_once(source,
        "        apply_represented_market(f,p,action.get('market',[]),size)\n",
        "        apply_represented_market(f,p,action.get('market',[]),size,market,config)\n"
        "        advance_represented_market(market,t,shops,config)\n"
        "        m._decay_plants(f,t)\n")
    source = replace_once(source,
        "            base.get('market',[]))\n                    if targets else None)",
        "            base.get('market',[]),obs['market'],shops)\n                    if targets else None)")
    # Only the horizon's raw-slot test changes, not horizon lengths/objective.
    source = replace_once(source,
        "    max_orders=int(config.get('maxMarketOrdersPerTurn',10))\n    service_dates={}",
        "    max_orders=max(1,int(config.get('maxMarketOrdersPerTurn',10)))\n    service_dates={}")
    source = replace_once(source,
        "            orders=route[date].get('market',[]) if date<len(route) else []\n            has_slot=",
        "            orders=represented_market_orders(\n"
        "                route[date].get('market',[]) if date<len(route) else [],config)\n            has_slot=")
    compile(source, 'frozen_selected.py', 'exec')
    return source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frozen-blob', default=NATIVE_BLOB)
    parser.add_argument('--mechanics-blob', default=MECHANICS_BLOB)
    args = parser.parse_args()
    if git_blob((args.package / 'mechanics.py').read_bytes()) != args.mechanics_blob:
        raise SystemExit('Mechanics input differs from explicit pin; no output written')
    before = (args.package / 'frozen_selected.py').read_bytes()
    if git_blob(before) != args.frozen_blob:
        raise SystemExit('Input blob differs from explicit pin; no output written')
    after = compose_source(before.decode()).encode()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'frozen_selected.py').write_bytes(after)
    receipt = {'scope': 'same-day represented physical market scenario',
               'rival_assumption': 'no additional rival trades',
               'release_authorized': False,
               'before': git_blob(before), 'after': git_blob(after),
               'sha256': hashlib.sha256(after).hexdigest()}
    (args.output / 'REPRESENTED-MARKET.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    main()
