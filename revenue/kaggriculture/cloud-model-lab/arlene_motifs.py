"""Selective motif overlay on the INTACT Arlene baseline.

Arlene replays route tapes and already carries the two things this needs:

  `_noop(act, tile, inv, seeds, x, y)`  its own predicate for a slot the engine
      will ignore. It reuses such a slot for exactly one purpose today -- a wasted
      turn spent standing on a weed becomes a DIG. This extends that same notion
      of a free slot to compiled, economically live components.

  `future_sells(item, step)`  how much of each product the REST of the route still
      intends to sell. The reservation contract below is the same idea widened to
      every resource the remaining tape consumes, read off the tape itself rather
      than off one turn.

The baseline is not modified. `Overlay` calls Arlene for the whole turn, keeps its
farmer, hands and market exactly as returned, and only writes into slots Arlene's
own predicate marks free. Every write must survive:

  route reservation   the op may not consume a seed, a shed item or a carried item
                      the remaining tape still plans to use, nor a product the rest
                      of the route intends to sell
  prefix compatibility the merged unit phase, replayed with the pinned transition,
                      must leave every WORKING slot's exact outcome unchanged --
                      effect, final position, full carried inventory, tile beneath
  engine effect       the op must be one the interpreter acts on in context, and
                      never `destroyed_plant` or `removed_structure`
  destructive harvest HARVEST on a non-ongoing crop DESTROYS it (467-468), so it is
                      allowed only once the crop can grow no further, or on the
                      last day when nothing further can be sold anyway

A costly proposal is not banned. It is admitted when the compiled evidence says the
op pays and the reservation says the tape does not need what it spends; whether
that is worth cash is decided by full-game own cash and own-minus-rival margin, not
by any counter here.
"""

import copy

import native_motifs as NM

MAX_FILLS = 4
# How long an op needs before its value can actually be realised, in DAYS.
#
# FEED and CARE set daily flags the end-of-day refresh reads: the product appears
# at that refresh, then still has to be HARVESTed by a later worker turn and SOLD.
# On the last day none of that can happen, and FEED additionally burns a carried
# WHEAT for nothing -- the overlay did exactly that at d28h23 and paid for it.
# WATER feeds plant growth that has to reach a harvest window and a sale.
# HARVEST and COLLECT_FERTILIZER put stock in hand the same turn, so they stay
# available right up to the terminal settlement.
# Measured, not guessed: a FEED at d28h23 passed a one-day gate and cost exactly
# $41 -- the ledger shows one WHEAT that was never sold and no other change on
# either seat. A consuming op needs the WHOLE chain to fit, refresh then a worker
# turn to harvest then a sale, and the route may not revisit that tile at all. So
# an op that SPENDS something needs two clear days; a free op needs one.
REALISATION_DAYS = {"FEED": 2, "PLACE": 2, "PLANT": 2,
                    "CARE": 1, "WATER": 1,
                    "HARVEST": 0, "COLLECT_FERTILIZER": 0}
# The four resources a route tape can consume, and the ops that consume each.
SEED_OPS = ("PLANT",)
SHED_OPS = ("PICKUP",)
CARRY_OPS = ("PLACE", "FEED", "FERTILIZE", "DROP")


def route_reservation(agent, step):
    """What the REST of the current tape still needs, read off the tape.

    Positions are live, so a tape step cannot be bound to a tile; what it CAN be
    bound to is the resource it names. Seeds, shed withdrawals, carried items and
    planned sales are all named in the tape, so the remaining suffix gives an exact
    lower bound on what must not be spent out from under it.
    """
    route = agent.R[agent.cur]
    seeds, shed, carry, sells = {}, {}, {}, {}
    for t in range(step + 1, len(route)):
        entry = route[t] or {}
        units = [entry.get("farmer") or ["PASS"]] + list(entry.get("hands") or [])
        for op in units:
            if not op:
                continue
            if op[0] in SEED_OPS and len(op) > 1:
                seeds[op[1]] = seeds.get(op[1], 0) + 1
            elif op[0] in SHED_OPS and len(op) > 1:
                n = int(op[2]) if len(op) > 2 else 1
                shed[op[1]] = shed.get(op[1], 0) + n
            elif op[0] == "PLACE" and len(op) > 1:
                n = int(op[2]) if len(op) > 2 else 1
                carry[op[1]] = carry.get(op[1], 0) + n
            elif op[0] == "FEED":
                carry["WHEAT"] = carry.get("WHEAT", 0) + 1
            elif op[0] == "FERTILIZE":
                carry["FERTILIZER"] = carry.get("FERTILIZER", 0) + 1
        for o in (entry.get("market") or []):
            if o and o[0] == "SELL" and len(o) > 2:
                sells[o[1]] = sells.get(o[1], 0) + int(o[2])
    return {"seeds": seeds, "shed": shed, "carry": carry, "sells": sells}


def harvest_is_destructive(tile, day, K):
    """True when HARVEST here removes a crop that would still have grown.

    Animals and ongoing crops survive HARVEST (469-472, 467). A non-ongoing crop is
    removed, so harvesting it early forfeits every unit it had left to accrue.
    """
    if not isinstance(tile, dict) or tile.get("animal") is not None:
        return False
    if tile.get("kind") != "PLANT":
        return False
    cd = K.CROPS.get(tile.get("crop"))
    if not cd or cd["ongoing"]:
        return False
    age = int(day) - int(tile.get("planted_day", day))
    grown = int(tile.get("yield_units", 0)) >= int(cd["max_yield"])
    return not (grown or age >= int(cd["max_yield_day"]))


class Overlay:
    def __init__(self, arlene_mod, table, max_fills=MAX_FILLS, last_day=29):
        self.A = arlene_mod
        self.agent = arlene_mod.Agent()
        self.motifs = [m for m in table.get("motifs", []) if m.get("proposable")]
        self.meta = dict(table.get("meta", {}))
        self.max_fills = max_fills
        self.last_day = last_day
        self.K = NM.engine()
        self._cache = {}
        self.fills = []

    def _candidates(self, facts):
        """Coarse cached set, then a fresh `holds()` against this slot's facts."""
        key = NM.coarse_key(facts)
        coarse = self._cache.get(key)
        if coarse is None:
            coarse = sorted(self.motifs,
                            key=lambda m: (-m["support"]["total"], m["id"]))
            self._cache[key] = coarse
        out = []
        for m in coarse:
            if NM.holds(m["when"], m["op"], facts):
                out.append(m)
            if len(out) >= NM.MAX_SLOT_CANDIDATES:
                break
        return out

    def _reserved(self, op, facts, res):
        c = NM.consumption(op, facts)
        for item, n in c["seeds"].items():
            if n > facts["seeds"].get(item, 0) - res["seeds"].get(item, 0):
                return f"seed {item} is reserved by the remaining route"
        for item, n in c["shed"].items():
            free = facts["shed"].get(item, 0) - max(res["shed"].get(item, 0),
                                                    res["sells"].get(item, 0))
            if n > free:
                return f"shed {item} is reserved by the remaining route"
        for item, n in c["carry"].items():
            if n > facts["carry"].get(item, 0) - res["carry"].get(item, 0):
                return f"carried {item} is reserved by the remaining route"
        return None

    def act(self, obs):
        base = self.agent.act(obs)
        if not self.motifs:
            return base
        s = obs.get("step")
        step = int(s) if s is not None else int(obs.get("day", 0)) * 24 + int(obs.get("hour", 0))
        seat = int(obs.get("player", 0))
        farm, priv = obs["farms"][seat], obs["private"]
        tiles = farm["tiles"]
        board = len(tiles) or self.A.BOARD
        seeds = priv.get("seeds") or {}
        invs = priv.get("inventories") or []
        day = int(obs.get("day", step // 24))
        units = [list(base["farmer"])] + [list(h) for h in base["hands"]]
        pos = [farm["farmer"]] + list(farm.get("hands", []))
        # The tape's hands list can be longer than the farm's actual hands. The
        # engine only applies ops for units that exist, so the simulation must see
        # the same set; the surplus entries are carried through untouched.
        tail = units[len(pos):]
        units = units[:len(pos)]

        idle = []
        for i, op in enumerate(units):
            if i >= len(pos):
                continue
            x, y = int(pos[i][0]), int(pos[i][1])
            if not (0 <= x < board and 0 <= y < board):
                continue
            inv = invs[i] if i < len(invs) else {}
            if self.A._noop(op, tiles[y][x], inv, seeds, x, y, board):
                idle.append(i)
        if not idle:
            return base

        res = route_reservation(self.agent, step)
        cfg = {"boardSize": board, "turnsPerDay": 24, "shedCapacity": self.A.SHED_CAP}
        sim_obs = {"farms": obs["farms"], "private": priv, "day": day}
        before = NM.simulate(self.K, sim_obs, cfg, seat, units)
        filled = 0
        for i in idle:
            if filled >= self.max_fills:
                break
            pre = NM.simulate(self.K, sim_obs, cfg, seat, units, upto=i)
            f_farm = pre["farm"] if i else obs["farms"][seat]
            f_priv = pre["priv"] if i else priv
            facts = NM.unit_facts(f_farm, f_priv, cfg, i)
            for m in self._candidates(facts):
                op = list(m["op"])
                if op == units[i] or op[0] == "PASS":
                    continue
                need = REALISATION_DAYS.get(op[0], 1)
                if day + need > self.last_day:
                    continue      # no time left for this op's value to be realised
                if op[0] == "HARVEST" and day < self.last_day and \
                        harvest_is_destructive(f_farm["tiles"][facts["at"][1]]
                                               [facts["at"][0]], day, self.K):
                    continue
                bad = self._reserved(op, facts, res)
                if bad:
                    continue
                trial = list(units)
                trial[i] = op
                if NM.seed_blocked(trial, seeds):
                    continue
                after = NM.simulate(self.K, sim_obs, cfg, seat, trial)
                g = after["slots"][i]
                if g["kind"] in NM.FORBIDDEN_EFFECTS:
                    continue
                if any((after["slots"][j]["kind"], after["slots"][j]["pos"],
                        after["slots"][j]["carry"], after["slots"][j]["tile"]) !=
                       (before["slots"][j]["kind"], before["slots"][j]["pos"],
                        before["slots"][j]["carry"], before["slots"][j]["tile"])
                       for j in range(len(units)) if j != i):
                    continue
                units[i] = op
                before = after
                filled += 1
                self.fills.append({"step": step, "day": day,
                                   "hour": int(obs.get("hour", step % 24)),
                                   "unit": i, "at": list(facts["at"]),
                                   "displaced": list(base["farmer"]) if i == 0
                                   else list(base["hands"][i - 1]),
                                   "op": op, "motif": m["id"],
                                   "effect": g["kind"],
                                   "support": m["support"],
                                   "provenance": m["provenance"]})
                break
        if not filled:
            return base
        out = dict(base)
        out["farmer"] = units[0]
        out["hands"] = units[1:] + tail
        return out
