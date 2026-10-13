"""Read-only audits of a player's selected joint action and visible observation."""
from collections import defaultdict
from collections.abc import Mapping, Sequence


def duplicate_harvest_targets(observation, action):
    """Return co-located existing actors assigned HARVEST on the same turn.

    Actor 0 is the farmer; actor n is hands[n - 1]. This is a structural
    conflict audit, not a yield or profitability prediction. Ready yield is
    reported only as the tile's observed value. Neither input is modified.
    Orders for actors absent from the observation are ignored because market
    hires occur after unit actions.
    """
    if not isinstance(observation, Mapping) or not isinstance(action, Mapping):
        return []
    farms = observation.get("farms", [])
    seat = observation.get("player", 0)
    if not isinstance(seat, int) or not 0 <= seat < len(farms):
        return []
    farm = farms[seat]
    positions = [farm.get("farmer"), *farm.get("hands", [])]
    hands = action.get("hands", [])
    if not isinstance(hands, list):
        hands = []
    orders = [action.get("farmer", []), *hands]
    groups = defaultdict(list)
    for actor, (position, order) in enumerate(zip(positions, orders)):
        if (isinstance(order, list) and order and order[0] == "HARVEST"
                and isinstance(position, Sequence) and len(position) == 2):
            groups[tuple(position)].append(actor)
    conflicts = []
    tiles = farm.get("tiles", [])
    for (x, y), actors in sorted(groups.items()):
        if len(actors) < 2:
            continue
        tile = tiles[y][x] if (isinstance(x, int) and isinstance(y, int)
            and 0 <= y < len(tiles) and 0 <= x < len(tiles[y])) else None
        conflicts.append({
            "position": [x, y], "actors": actors,
            "redundant_orders": len(actors) - 1,
            "visible_yield_units": tile.get("yield_units", 0) if isinstance(tile, Mapping) else 0,
            "tile_kind": tile.get("kind") if isinstance(tile, Mapping) else tile,
        })
    return conflicts
