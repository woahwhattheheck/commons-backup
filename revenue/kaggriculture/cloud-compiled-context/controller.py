# SPDX-License-Identifier: MIT OR CC-BY-4.0
"""Bounded observable strategic state, not a language model or model compression.

Pure JSON interface: select_context -> advance -> constrain_orders.
Call advance once per distinct observation and retain the returned state.
Unit scheduling remains the caller's responsibility. No engine/random access.
"""
from copy import deepcopy

OBJECTIVE = "maximize terminal bank cash"
ANIMAL_FIRST = {"GOOSE": 4, "COW": 8, "SHEEP": 6}
CROP_FIRST = {"WHEAT": 2, "CARROT": 2, "MELON": 10,
              "TOMATO": 8, "STRAWBERRY": 10}
COST = {"GOOSE": 300, "COW": 400, "SHEEP": 500,
        "WHEAT": 10, "CARROT": 20, "MELON": 80,
        "TOMATO": 50, "STRAWBERRY": 100}
DEFAULTS = {"daily_animals": 8, "daily_crops": 4, "animal_cap": 20,
            "crop_cap": 6, "max_attempts": 6, "pipeline_cap": 3, "labor_reserve": 150,
            "installation_actions": 6, "animal_daily_actions": 5.5,
            "crop_daily_actions": 2, "max_hands": 8}


def _get(cfg, key, default):
    return cfg.get(key, default) if isinstance(cfg, dict) else getattr(cfg, key, default)


def select_context(obs, configuration=None):
    """Select own observable stock/capacity and public deadlines, never future shops.

    remaining_actions includes this action. First-production dates are feasibility
    bounds, not yield forecasts; ROWAN's event interface may refine them downstream.
    Work estimates below are policy costs, not source-defined game constants.
    """
    turns = _get(configuration, "turnsPerDay", 24)
    steps = _get(configuration, "episodeSteps", 720)
    day, hour = obs.get("day", 0), obs.get("hour", 0)
    step = obs.get("step", day * turns + hour)
    farm = obs["farms"][obs["player"]]
    private = obs["private"]
    inventories = private["inventories"]
    stock = {k: private["shed"].get(k, 0) + sum(i.get(k, 0) for i in inventories)
             for k in (*ANIMAL_FIRST, "WHEAT")}
    animals, crops, vacant = [], [], 0
    for row in farm["tiles"]:
        for tile in row:
            if isinstance(tile, dict) and "animal" in tile:
                animals.append(tile)
            elif isinstance(tile, dict) and tile.get("kind") == "PLANT":
                crops.append(tile)
            elif tile is None or isinstance(tile, dict) and tile.get("kind") in ("WEED", "COOP", "PASTURE"):
                vacant += 1
    size = len(farm["tiles"])
    depot = [(x, y) for x in (size//2-1, size//2) for y in (size//2-1, size//2)]
    positions = [farm["farmer"], *farm.get("hands", [])]
    home = [min(abs(p[0]-q[0])+abs(p[1]-q[1]) for q in depot) for p in positions]
    remaining = max(0, steps - 1 - step)
    end_day = (steps - 2) // turns
    pending = sum(stock[a] for a in ANIMAL_FIRST)
    return {"schema": 1, "objective": OBJECTIVE, "player": obs["player"],
            "step": step, "day": day, "hour": hour, "turns_per_day": turns,
            "remaining_actions": remaining, "remaining_days": max(0, end_day-day),
            "cash": farm["money"], "prices": dict(obs["market"]["prices"]),
            "animals": len(animals), "crops": len(crops), "pending": pending,
            "stock": stock, "seed_stock": dict(private["seeds"]),
            "unfed": sum(not a["fed_today"] for a in animals),
            "workers": len(positions), "vacant": vacant, "hires_today": farm.get("hires_today", 0),
            "hire_multiplier": _get(configuration, "farmHandCostMult", 1),
            "worker_actions_left": len(positions) * min(turns-hour, remaining),
            "liquidation_distance": max(home, default=0),
            "animal_horizon": {a: end_day-day-first-1 for a, first in ANIMAL_FIRST.items()},
            "crop_horizon": {c: end_day-day-first-1 for c, first in CROP_FIRST.items()},
            "seed_total": sum(private["seeds"].values()),
            "goods_value": sum(n * obs["market"]["prices"].get(p, 0)
                               for inv in [private["shed"], *inventories] for p, n in inv.items()
                               if p not in ANIMAL_FIRST and p != "WHEAT")}


def advance(obs, configuration=None, previous=None, options=None):
    """Create/reconcile a daily commitment using observed progress, with bounded memory.

    Completion = installation/crop targets reached AND livestock backlog cleared.
    Expiry ends the old plan, records its unmet target and replans from actual stock.
    BUY proposals never count as installed assets. Same-step calls are idempotent.
    """
    c = select_context(obs, configuration)
    o = {**DEFAULTS, **(options or {})}
    s = deepcopy(previous) if previous else None
    if s and s["player"] == c["player"] and s["step"] == c["step"]:
        return s
    if s and (s["player"] != c["player"] or c["step"] < s["step"]):
        s = None
    prior_jobs = s.get("installation_jobs", []) if s and s["day"] == c["day"] else []
    jobs, job_outcomes = installation_jobs(obs, prior_jobs)
    history = list(s["feedback"]) if s else []
    history.extend(job_outcomes)
    bank = list(s.get("bank", [])) if s else []
    completed_count = s.get("completed_count", 0) if s else 0
    expired_count = s.get("expired_count", 0) if s else 0
    if s:
        delta = {k: c[k]-s["observed"][k] for k in ("animals", "crops", "pending", "cash")}
        s["last_outcome"] = delta
        if s["status"] == "active" and c["animals"] >= s["installation_target"] and c["crops"] >= s["crop_target"] and c["pending"] == 0:
            s["status"] = "completed"
            completed_count += 1
            gain = (c["animals"]-s["start_animals"]) + (c["crops"]-s["start_crops"])
            if gain > 0:
                bank.append({"situation": s["situation"], "day": s["day"],
                             "plan": {"animals": s["installation_target"]-s["start_animals"],
                                      "crops": s["crop_target"]-s["start_crops"]},
                             "outcome": {"advancement_score": gain,
                                         "cash_delta": c["cash"]-s["start_cash"]}})
            history.append({"day": s["day"], "step": c["step"], "outcome": "completed"})
        if c["day"] != s["day"] and s["status"] == "active":
            expired_count += 1
            history.append({"day": s["day"], "step": c["step"], "outcome": "expired",
                            "uninstalled": max(0, s["installation_target"]-c["animals"]),
                            "unplanted": max(0, s["crop_target"]-c["crops"])})
    if not s or c["day"] != s["day"]:
        situation = ("backlog" if c["pending"] else "growth") + (":late" if c["remaining_days"] < 12 else ":early")
        examples = []
        seen = set()
        for row in reversed(bank):
            shape = (row["plan"]["animals"], row["plan"]["crops"])
            if row["situation"] == situation and shape not in seen:
                examples.append(row)
                seen.add(shape)
            if len(examples) == 2:
                break
        # Today's currently hired labor plus affordable opening-hour cheap hires.
        # Work reservations are explicitly estimates, not a promise of execution.
        potential = c["workers"]
        if c["hour"] < 3:
            hire_a, hire_b = 1, 1
            for _ in range(c["hires_today"]):
                hire_a, hire_b = hire_b, hire_a+hire_b
            hiring_cash = max(0, c["cash"]-30-max(0, c["unfed"]-c["stock"]["WHEAT"])*(c["prices"]["WHEAT"]+1))
            while potential < o["max_hands"]+1 and hiring_cash >= hire_a*c["hire_multiplier"]:
                hiring_cash -= hire_a*c["hire_multiplier"]
                hire_a, hire_b = hire_b, hire_a+hire_b
                potential += 1
        budget = potential * (c["turns_per_day"]-c["hour"])
        service = c["animals"]*o["animal_daily_actions"] + c["crops"]*o["crop_daily_actions"]
        free_work = max(0, budget-service-c["pending"]*o["installation_actions"])
        animal_allowance = min(o["daily_animals"], max(0, o["animal_cap"]-c["animals"]-c["pending"]),
                               max(0, c["vacant"]-c["pending"]-2), int(free_work/o["installation_actions"]))
        if c["pending"] or max(c["animal_horizon"].values()) <= 0:
            animal_allowance = 0
        crop_allowance = min(o["daily_crops"], max(0, o["crop_cap"]-c["crops"]),
                            max(0, c["vacant"]-c["pending"]-animal_allowance-2),
                            int(max(0, free_work-animal_allowance*o["installation_actions"])/4))
        if max(c["crop_horizon"].values()) <= 0:
            crop_allowance = 0
        s = {"schema": 1, "objective": OBJECTIVE, "player": c["player"], "day": c["day"],
             "status": "active", "situation": situation, "examples": examples,
             "start_animals": c["animals"], "start_crops": c["crops"], "start_cash": c["cash"],
             "installation_target": c["animals"]+c["pending"]+animal_allowance,
             "crop_target": c["crops"]+crop_allowance, "animal_allowance": animal_allowance,
             "seed_allowance": max(0, crop_allowance-c["seed_total"]),
             "animal_attempts": 0, "seed_attempts": 0, "last_outcome": {},
             "last_proposed": [], "options": o, "budget_actions": budget,
             "reserved_service_actions": service}
    feed = max(0, c["unfed"]+c["pending"]-c["stock"]["WHEAT"])
    terminal = c["remaining_actions"] <= c["turns_per_day"]
    s.update(step=c["step"], observed={k:c[k] for k in ("animals", "crops", "pending", "cash")},
             backlog=c["pending"], feed_needed=0 if terminal else feed,
             cash_reserve=0 if terminal else o["labor_reserve"]+feed*(c["prices"]["WHEAT"]+1),
             phase="liquidate" if terminal else "install" if c["pending"] else "maintain" if s["status"] == "completed" else "develop",
             installation_jobs=jobs, feedback=history[-8:], bank=bank[-8:], completed_count=completed_count, expired_count=expired_count)
    return s


def constrain_orders(action, context, state):
    """Apply preconditions and priority to baseline market proposals, no unit rewrite.

    Priority: observed-inventory sales, labor/feed, then growth. Growth uses current
    cash only (future sales are not assumed). Returned state records proposals;
    next advance records outcomes. Retry attempts are bounded even after rejection.
    """
    c, s = context, deepcopy(state)
    o = s["options"]
    result = {"farmer": list(action["farmer"]), "hands": deepcopy(action["hands"]), "market": []}
    cash = c["cash"]
    orders = sorted(action["market"], key=lambda x: 0 if x[0] == "SELL" else 1 if x[0] in ("HIRE", "BUY_PRODUCT") else 2)
    proposed = []
    hire_a, hire_b = 1, 1
    for _ in range(c["hires_today"]):
        hire_a, hire_b = hire_b, hire_a+hire_b
    for order in orders:
        order = list(order)
        op = order[0]
        if op == "BUY_ANIMAL":
            a = order[1]
            missing = max(0, s["installation_target"]-c["animals"]-c["pending"])
            qty = min(order[2], missing, s["animal_allowance"], max(0, o["pipeline_cap"]-c["pending"]), max(0, int((cash-s["cash_reserve"])/COST[a])))
            if s["phase"] == "liquidate" or s["status"] == "completed" or s["animal_attempts"] >= o["max_attempts"] or c["animal_horizon"].get(a, 0) <= 0 or qty <= 0:
                continue
            order[2] = qty
            s["animal_attempts"] += 1
            cash -= qty*COST[a]
        elif op == "BUY_SEED":
            crop = order[1]
            qty = min(order[2], max(0, s["crop_target"]-c["crops"]-c["seed_total"]), s["seed_allowance"], max(0, int((cash-s["cash_reserve"])/COST[crop])))
            if s["phase"] == "liquidate" or s["seed_attempts"] >= o["max_attempts"] or c["crop_horizon"].get(crop, 0) <= 0 or qty <= 0:
                continue
            order[2] = qty
            s["seed_attempts"] += 1
            cash -= qty*COST[crop]
        elif op == "BUY_LAND":
            continue  # FLORA owns productive expansion; this adapter makes no land plan.
        elif op == "HIRE":
            cash -= hire_a*c["hire_multiplier"]
            hire_a, hire_b = hire_b, hire_a+hire_b
        elif op == "BUY_PRODUCT":
            cash -= order[2]*(c["prices"][order[1]]+1)
        result["market"].append(order)
        if op in ("BUY_ANIMAL", "BUY_SEED"):
            proposed.append(order)
    result["market"] = result["market"][:10]
    s["last_proposed"] = proposed
    return result, s


def situation_packet(context, state):
    """At most two own completed advancing plan examples, immediately before live state.

    This is a new plan-level analog of the LDA screen/action bank, not LDA's scored
    model-action corpus. Advancement is local asset progress, NOT terminal profit.
    Consumers must recheck current preconditions; examples are never replay scripts.
    """
    return [{"example": deepcopy(row)} for row in state["examples"]] + [
        {"live_state": deepcopy(context), "plan": {k: deepcopy(state[k]) for k in
         ("objective", "phase", "status", "installation_target", "crop_target", "backlog", "feed_needed", "cash_reserve")}}]


def installation_jobs(obs, previous=None):
    """Own carried-stock intents; commit through DIG/BUILD/PLACE, observe completion.

    New deterministic design. Each carried animal reserves one vacant
    compatible tile. Persistent worker identities last one day only; caller resets
    at EOD. Output is advisory data for FLORA; no peer scheduling code is imported.
    """
    farm = obs["farms"][obs["player"]]
    tiles, day, hour = farm["tiles"], obs.get("day", 0), obs.get("hour", 0)
    units = [farm["farmer"], *farm.get("hands", [])]
    inventories = obs["private"]["inventories"]
    prior = {j["worker"]: j for j in (previous or [])}
    reserved, jobs, feedback = set(), [], []
    for worker, pos in enumerate(units):
        inv = inventories[worker] if worker < len(inventories) else {}
        animal = next((a for a in ANIMAL_FIRST if inv.get(a, 0)), None)
        old = prior.get(worker)
        if old:
            x, y = old["target"]
            tile = tiles[y][x]
            if isinstance(tile, dict) and tile.get("animal") == old["animal"]:
                feedback.append({"day": day, "step": obs.get("step", 0),
                                 "outcome": "installation_completed", "worker": worker,
                                 "animal": old["animal"], "target": [x,y]})
                old = None
        if not animal:
            continue
        kind = "COOP" if animal == "GOOSE" else "PASTURE"
        choices = []
        for y, row in enumerate(tiles):
            for x, tile in enumerate(row):
                if (x,y) in reserved:
                    continue
                if tile is None:
                    action, operations = "BUILD_"+kind, 2
                elif isinstance(tile, dict) and tile.get("kind") == "WEED":
                    action, operations = "DIG", 3
                elif isinstance(tile, dict) and tile.get("kind") == kind and "animal" not in tile:
                    action, operations = "PLACE", 1
                else:
                    continue
                dist = abs(pos[0]-x)+abs(pos[1]-y)
                metric = dist+operations
                stale = (old.get("stale", 0)+1 if old and old["target"] == [x,y] and metric >= old["metric"] else 0)
                keep = old and old["animal"] == animal and old["target"] == [x,y] and stale < 8
                choices.append((0 if keep else 1, metric, y, x, action, stale))
        if not choices:
            continue
        _, metric, y, x, action, stale = min(choices)
        if old and old["target"] != [x,y]:
            feedback.append({"day": day, "step": obs.get("step", 0),
                             "outcome": "installation_replanned", "worker": worker,
                             "previous_target": old["target"], "target": [x,y]})
        reserved.add((x,y))
        jobs.append({"worker": worker, "animal": animal, "target": [x,y],
                     "next_operation": [action, animal] if action == "PLACE" else [action],
                     "metric": metric, "stale": stale,
                     "precondition": "own carried animal and vacant compatible target"})
    return jobs, feedback
