# SPDX-License-Identifier: Apache-2.0
"""TEST ONLY: selected R04 collaborators, not a router or production entrypoint.

Verbatim FarmView, projected_shed and evening_flush bodies from canonical donor
r04_full_router.py Git blob a3e2fe87c717d128e43c9b65bae2265f40d1d76d.
Only their referenced constants are included. This deliberately omits all tape,
policy, install, scheduler and current-runtime composition. Tests using this
slice establish helper-phase behavior, NOT a full-router/package/ABI gate.
The lifecycle test can compare the selected ASTs against --router from checkout.
"""
TURNS_PER_DAY = 24
LAST_STEP = 718
SHED_CAPACITY = 100
MAX_ORDERS = 10
PRODUCTS = (
    "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
    "EGG", "MILK", "WOOL", "FERTILIZER",
)
ANIMALS = {"GOOSE", "COW", "SHEEP"}
FLUSH_ITEMS = ("WOOL", "MILK", "STRAWBERRY", "MELON")
FLUSH_HOURS = (21, 22, 23)


class FarmView:
    """Only the current own farm, private inventory, and public prices."""

    def __init__(self, observation):
        farm = observation["farms"][observation["player"]]
        private = observation["private"]
        self.tiles = farm["tiles"]
        self.positions = [farm["farmer"], *farm["hands"]]
        self.inventories = private["inventories"]
        self.shed = {item: max(0, int(qty)) for item, qty in private["shed"].items()}
        self.prices = observation["market"]["prices"]

    def inventory(self, worker):
        return self.inventories[worker] if worker < len(self.inventories) else {}

    def beside_shed(self, position):
        center = len(self.tiles) // 2
        return position[0] in (center - 1, center) and position[1] in (center - 1, center)


def projected_shed(action, view):
    """Estimate stock after this turn's nearby PICKUP, DROP and PLACE actions.

    Preserve worker and inventory order: limited shed capacity can make it matter.
    This is the qualified lightweight estimate, not a full game simulation.
    """
    stock = {item: view.shed.get(item, 0) for item in PRODUCTS}
    stock.update(view.shed)
    total = sum(stock.values())
    workers = [action.get("farmer") or ["PASS"], *(action.get("hands") or [])]
    for worker in range(min(len(workers), len(view.positions))):
        if not view.beside_shed(view.positions[worker]):
            continue
        work = workers[worker]
        operation = work[0] if work else "PASS"
        inventory = view.inventory(worker)
        if operation == "PICKUP" and len(work) >= 2 and work[1] in stock:
            quantity = max(0, int(work[2]) if len(work) >= 3 else 1)
            taken = min(stock[work[1]], quantity)
            stock[work[1]] -= taken
            total -= taken
        elif operation == "DROP":
            for item, held in inventory.items():
                added = min(max(0, int(held)), max(0, SHED_CAPACITY - total))
                if added > 0:
                    stock[item] = stock.get(item, 0) + added
                    total += added
        elif operation == "PLACE" and len(work) >= 2 and work[1] not in ANIMALS:
            item = work[1]
            quantity = max(0, int(work[2]) if len(work) >= 3 else 1)
            added = min(quantity, max(0, int(inventory.get(item, 0))),
                        max(0, SHED_CAPACITY - total))
            if added > 0:
                stock[item] = stock.get(item, 0) + added
                total += added
    return stock


def evening_flush(observation, action):
    step = int(observation["step"])
    if step >= LAST_STEP or step < 24 or step % 24 not in FLUSH_HOURS:
        return action
    view = FarmView(observation)
    stock = projected_shed(action, view)
    market = [list(o) for o in action.get("market") or [] if o]
    selling = {}
    for order in market:
        if order[0] == "SELL" and len(order) >= 3:
            selling[order[1]] = selling.get(order[1], 0) + max(0, int(order[2]))
    extra = []
    for item in FLUSH_ITEMS:
        quantity = int(stock.get(item, 0)) - selling.get(item, 0)
        if quantity > 0 and int(view.prices.get(item, 0)) >= 2:
            extra.append(["SELL", item, quantity])
    room = MAX_ORDERS - len(market)
    if not extra or room <= 0:
        return action
    extra.sort(key=lambda order: -int(view.prices.get(order[1], 0)) * order[2])
    action = dict(action)
    action["market"] = extra[:room] + market
    return action
