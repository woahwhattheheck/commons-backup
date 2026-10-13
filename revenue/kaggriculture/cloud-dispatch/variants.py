"""Reproducible behavior experiments on the frozen, licensed lean20 policy."""
from __future__ import annotations

import hashlib
from pathlib import Path

BASE_SHA256 = "d9487c031b50ede06a706acc8bcb40e0b5a681d9b5e92c1a1a96492b26c2dd62"
BASE_REF = "5d9fe82d288ee2933b38e8db8871602e688410af"
HERE = Path(__file__).resolve().parent

DISPATCH = '''    # All workers bid before any target is reserved. Select the strongest
    # worker/job pair globally, then remove its worker and claimed destination.
    # Stock is reserved only for an action that executes here this turn.
    while plans:
        offers = []
        for index, pos, candidates, near, d_home, carried_value in plans:
            for score, negd, target, action, key in candidates:
                if key in claims:
                    continue
                if tuple(pos) == tuple(target):
                    if action[0] == "PICKUP" and available_shed.get(action[1], 0) <= 0:
                        continue
                    if action[0] == "PLANT" and available_seeds.get(action[1], 0) <= 0:
                        continue
                offers.append((score, negd, -target[1], -target[0], str(action), -index,
                               index, pos, target, action, key))
        if not offers:
            for index, pos, candidates, near, d_home, carried_value in plans:
                if ending and carried_value:
                    actions[index] = ["DROP"] if d_home == 0 else toward(pos, near)
                else:
                    actions[index] = ["PASS"]
            break
        *_, index, pos, target, action, key = max(offers, key=lambda offer: offer[:6])
        claims.add(key)
        plans = [plan for plan in plans if plan[0] != index]
        if tuple(pos) != tuple(target):
            actions[index] = toward(pos, target)
        else:
            action = list(action)
            if action[0] == "PICKUP":
                action[2] = min(action[2], available_shed[action[1]])
                available_shed[action[1]] -= action[2]
            elif action[0] == "PLANT":
                available_seeds[action[1]] -= 1
            actions[index] = action
'''

DEPOSIT_SALES = '''    # Unit actions run before market orders. Include exactly the cargo from
    # planned on-depot DROPs in this turn's sales, keeping the existing feed
    # reserve. Avoid extra empty sales that would crowd out hires or purchases.
    deposits = {product: 0 for product in PRODUCTS}
    for index, action in enumerate(actions):
        if action == ["DROP"] and tuple(units[index]) in set(depot):
            for product in PRODUCTS:
                deposits[product] += inventories[index].get(product, 0)
    if any(deposits.values()) and not ending:
        existing = {order[1]: order[2] for order in orders if order[0] == "SELL"}
        sales = []
        for product in PRODUCTS:
            qty = existing.get(product, 0) + deposits[product]
            if qty:
                sales.append(["SELL", product, qty])
        orders = sales + [order for order in orders if order[0] != "SELL"]
'''


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError("Frozen source transformation no longer matches uniquely")
    return source.replace(old, new, 1)


def generate(source, name):
    if hashlib.sha256(source.encode()).hexdigest() != BASE_SHA256:
        raise ValueError("Expected the exact published lean20 source")
    if name not in {"lean20", "dispatch", "deposit_sales", "dispatch_sales"}:
        raise ValueError(f"Unknown candidate: {name}")
    if name == "lean20":
        return source
    if name.startswith("dispatch"):
        source = replace_once(source, "    actions = []\n", "    actions = [None] * len(units)\n    plans = []\n")
        source = replace_once(source,
            '            actions.append(["DROP"] if d_home == 0 else toward(pos, near))',
            '            actions[index] = ["DROP"] if d_home == 0 else toward(pos, near)')
        start = source.index("        if candidates:\n")
        end = source.index('    return {"farmer": actions[0]', start)
        source = source[:start] + "        plans.append((index, pos, candidates, near, d_home, carried_value))\n" + DISPATCH + source[end:]
    if name.endswith("sales"):
        source = replace_once(source, '    return {"farmer": actions[0]', DEPOSIT_SALES + '    return {"farmer": actions[0]')
    source = source.replace("# ASTRA-WORK bounded strategy variation; source license retained.",
        "# ASTRA-WORK lean20; ROWAN behavior variant " + name + "; source license retained.")
    compile(source, name + ".py", "exec")
    return source


def write_candidates(directory, source=None):
    source = source or (HERE.parent / "cloud-market" / "main.py").read_text()
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    result = {}
    for name in ("lean20", "dispatch", "deposit_sales", "dispatch_sales"):
        path = target / (name + ".py")
        path.write_text(generate(source, name))
        result[name] = path
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    for name, path in write_candidates(args.directory).items():
        print(name, hashlib.sha256(path.read_bytes()).hexdigest())
