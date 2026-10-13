"""Official random agent, kaggle-environments 1.32.7, Apache-2.0.
Copied from kaggriculture.py random_agent without strategy change.
"""
import random
CROPS = {"WHEAT":{"seed":10},"CARROT":{"seed":20},"TOMATO":{"seed":50},"STRAWBERRY":{"seed":100},"MELON":{"seed":200}}
def agent(obs, config=None):
    rng = random.Random()
    farms = obs.get("farms", [])
    player = obs.get("player", 0)
    private = obs.get("private", {}) or {}
    farm = farms[player] if farms and player < len(farms) else None
    if farm is None:
        return {"farmer": ["PASS"], "hands": [], "market": []}
    farmer_ops = ["NORTH", "SOUTH", "EAST", "WEST", "WATER", "HARVEST", "PASS"]
    market = []
    seeds = private.get("seeds", {})
    affordable = [c for c in CROPS if CROPS[c]["seed"] <= farm["money"]]
    if affordable and rng.random() < 0.1:
        market.append(["BUY_SEED", rng.choice(affordable), 1])
    available_seeds = [c for c, n in seeds.items() if n > 0]
    if available_seeds and rng.random() < 0.3:
        farmer = ["PLANT", rng.choice(available_seeds)]
    else:
        farmer = [rng.choice(farmer_ops)]
    hands_actions = [[rng.choice(farmer_ops)] for _ in farm.get("hands", [])]
    return {"farmer": farmer, "hands": hands_actions, "market": market}
