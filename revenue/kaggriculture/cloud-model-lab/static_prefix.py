"""The stable static prefix: rules and economy that never change within an episode.

Kept separate from live state so it is one reusable block, identical every turn.
Every number is read from the pinned engine's own tables, not transcribed.
"""

from constraints import engine


def build(config):
    K = engine()
    tpd = int(config.get("turnsPerDay", 24) or 24)
    cap = int(config.get("shedCapacity", 100) or 100)
    steps = int(config.get("episodeSteps", 720) or 720)
    maxo = int(config.get("maxMarketOrdersPerTurn", 10) or 10)
    lines = ["KAGGRICULTURE STATIC RULES AND ECONOMY (same every turn)"]
    lines.append(f"score = your CASH at the end. Stock left in the shed scores 0. "
                 f"{steps - 1} decisions per episode, {tpd} turns per day, "
                 f"shed holds {cap}, at most {maxo} market orders per turn.")

    lines.append("crops (seed cost | first yield | max yield | ongoing):")
    for c, d in K.CROPS.items():
        og = (f"ongoing, +1 every {d['interval']}d for {d['max_yield']} events"
              if d["ongoing"] else f"one harvest, best watered age{(d['max_yield_day'] + 1) // 2}-{d['max_yield_day']}d")
        lines.append(f"  {c:11s} seed ${d['seed']:3d}  first yield age{d['first_yield_day']:2d}d  "
                     f"cap {d['max_yield']}  {og}")
    lines.append("animals (cost | structure | product | first yield | every):")
    for a, d in K.ANIMALS.items():
        lines.append(f"  {a:6s} ${d['cost']:3d}  needs {d['structure']:7s}  gives {d['product']:5s}  "
                     f"first age{d['first_yield_day']}d  every {d['interval']}d  hold {d['max_held']}")
    lines.append("  an animal produces at the daily refresh. FEED costs 1 WHEAT carried by "
                 "the unit standing on it. CARE alone does nothing: the care bonus is only "
                 "granted if the animal was FED that same day. Buying a seed is not feed -- "
                 "seeds are planted, never eaten.")
    lines.append("  PLACE <animal> INSTALLS it only when the unit stands on an empty matching "
                 "structure; otherwise it just deposits the animal into the shed as stock. Two "
                 "units on the same structure cannot both install.")
    lines.append("base sell prices: " + ", ".join(
        f"{k} {v['base']}" for k, v in K.MARKET_PARAMS.items()))
    lines.append("price moves with market inventory: selling a lot pushes a price down, "
                 "and only WHEAT and FERTILIZER can be bought back from the market.")
    lines.append("town shops and what each unlocked copy consumes every "
                 f"{int(config.get('townShopSellInterval', 4) or 4)} turns:")
    for s, items in K.SHOPS.items():
        lines.append(f"  {s:15s} {', '.join(items)}"
                     + ("  (single-product shops pull 2x)" if len(items) == 1 else ""))
    lines.append(f"land: NW is free; then {', '.join(K.LAND_ORDER)} at "
                 f"${K.LAND_PRICES[0]}, ${K.LAND_PRICES[1]}, ${K.LAND_PRICES[2]}. "
                 "HIRE costs 1,1,2,3,5,... per extra hand that day and hands are "
                 "released at the end of every day.")
    lines.append("a plant dies at the daily refresh once it has gone 2 days unwatered, "
                 "and a newly planted tile already counts its planting day as unwatered.")
    return "\n".join(lines)
