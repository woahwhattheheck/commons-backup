"""Independent evaluation baselines plus Euler's requested isolated compact ablation."""
import random

MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}


def seeded_walk(obs, configuration=None):
    """Seeded random walk using the worker's separate RNG, never the world seed."""
    player = obs.get("player", 0)
    farms = obs.get("farms", [])
    if not farms:
        return {}
    farm, private = farms[player], obs.get("private", {})
    x, y = farm["farmer"]
    tile = farm["tiles"][y][x]
    seeds = private.get("seeds", {})
    market = [["SELL", item, count] for item, count in private.get("shed", {}).items()
              if count > 0 and item not in ("GOOSE", "COW", "SHEEP")]
    if seeds.get("WHEAT", 0) < 2 and farm["money"] >= 20:
        market.append(["BUY_SEED", "WHEAT", 2])
    options = [["PASS"]]
    for move, (dx, dy) in MOVES.items():
        nx, ny = x + dx, y + dy
        if 0 <= ny < len(farm["tiles"]) and 0 <= nx < len(farm["tiles"][ny]) and farm["tiles"][ny][nx] != "LOCKED":
            options.append([move])
    if tile is None and seeds.get("WHEAT", 0) > 0:
        options.append(["PLANT", "WHEAT"])
    if isinstance(tile, dict):
        options.extend([["WATER"], ["HARVEST"]] if tile.get("kind") == "PLANT" else [["DIG"]])
    return {"farmer": random.choice(options), "hands": [], "market": market}


def crop_patrol(obs, configuration=None):
    """A single farmer tends a 2x2 wheat plot near the shed, without animals/hiring."""
    farm = obs["farms"][obs["player"]]
    private, day = obs["private"], obs["day"]
    x, y = farm["farmer"]
    half = len(farm["tiles"]) // 2
    plot = [(half - 1, half - 1), (half - 2, half - 1),
            (half - 2, half - 2), (half - 1, half - 2)]
    shed, seeds = private.get("shed", {}), private.get("seeds", {})
    market = [["SELL", item, count] for item, count in shed.items() if count > 0]
    if seeds.get("WHEAT", 0) < 4 and farm["money"] >= 40:
        market.append(["BUY_SEED", "WHEAT", 4])
    candidates = []
    for tx, ty in plot:
        tile = farm["tiles"][ty][tx]
        if isinstance(tile, dict) and tile.get("kind") == "PLANT":
            age = day - tile["planted_day"]
            if age >= 4:
                priority, action = 0, ["HARVEST"]
            elif not tile.get("watered_today"):
                priority, action = 1, ["WATER"]
            else:
                continue
        elif isinstance(tile, dict) and tile.get("kind") == "WEED":
            priority, action = 2, ["DIG"]
        elif tile is None and seeds.get("WHEAT", 0) > 0:
            priority, action = 3, ["PLANT", "WHEAT"]
        else:
            continue
        candidates.append((priority, abs(tx - x) + abs(ty - y), tx, ty, action))
    action = ["PASS"]
    if candidates:
        _, _, tx, ty, action = min(candidates)
        if tx != x:
            action = ["EAST" if tx > x else "WEST"]
        elif ty != y:
            action = ["SOUTH" if ty > y else "NORTH"]
    return {"farmer": action, "hands": [], "market": market}


_COMPACT = None


def compact_no_expansion(obs, configuration=None):
    """Euler-requested ablation; changes only its own worker's imported module."""
    global _COMPACT
    if _COMPACT is None:
        import importlib.util
        from pathlib import Path
        path = Path(__file__).resolve().parent.parent / "20260907-offline-agent" / "main.py"
        spec = importlib.util.spec_from_file_location("compact_opponent", path)
        _COMPACT = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_COMPACT)
        _COMPACT.POLICY.update(animal_cap=22, expansion=False, max_hands=9)
    return _COMPACT.agent(obs, configuration)
