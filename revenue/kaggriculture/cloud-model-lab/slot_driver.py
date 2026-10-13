"""E4B authors the OPEN slots of a real Arlene turn, under the same machinery.

The route's working slots carry the schedule and are not the model's to author.
What is open is the set of slots Arlene's own `_noop` predicate says the engine
will ignore. This asks E4B for those, and only those:

  state        the exact observation, through the existing typed-slot renderer
  constraint   `constraints.admissible` per unit, unchanged
  selection    `codec.slot_regex` built from that admissible set, so an accepted
               emission is legal by construction and PASS stays expressible
  decode       `codec.decode_slots`, strict; a rejection is recorded with its
               reason and never replaced by a claimed model decision

The OPEN SLOTS block states, per open slot, the engine rule that makes each
candidate pay and the cost when there is one -- HARVEST on a non-ongoing crop
destroys it. Those are facts read off the observation and the pinned rules, not a
recommendation: the block lists the reasons on both sides and the model chooses,
including choosing PASS.
"""

import time

import constraints
import codec
import slots


def opportunity_block(card, seat, ask_units=None):
    lines = ["OPEN SLOTS (the route is not using these; the engine would ignore what "
             "it plays there)"]
    by_unit = {}
    for o in card["opportunities"]:
        by_unit.setdefault(o["unit"], []).append(o)
    for u in sorted(set(card["idle_units"]) if ask_units is None else set(ask_units)):
        label = "farmer" if u == 0 else f"hand{u - 1}"
        opps = by_unit.get(u, [])
        if not opps:
            lines.append(f"  {label}: open, nothing on its tile pays right now")
            continue
        x, y = opps[0]["at"]
        lines.append(f"  {label} on t{x}{y}:")
        for o in opps:
            lines.append(f"    {' '.join(str(t) for t in o['op'])} -- {o['why']} "
                         f"[not covered again this {o['window']}]")
    lines.append("Choose one op per open slot from that slot's ALLOWED list above. "
                 "PASS is allowed and is the right answer when nothing pays.")
    return "\n".join(lines)


class SlotDriver:
    def __init__(self, runner, max_slots=4, render="slots"):
        self.r = runner
        self.max_slots = max_slots
        self.render = render
        self.log = []
        self.plan = None

    def act(self, card):
        obs, cfg, seat = card["observation"], card["configuration"], card["seat"]
        t0 = time.perf_counter()
        adm = constraints.admissible(obs, cfg, seat)
        hz = constraints.horizon(obs, cfg, seat)
        # Only slots with something live on their tile are asked about. An idle
        # slot whose tile offers nothing can only be PASS, so putting it in the
        # grammar buys nothing and costs decode tokens.
        offered = {o["unit"] for o in card["opportunities"]}
        idle = [u for u in card["idle_units"]
                if u < len(adm["units"]) and u in offered][:self.max_slots]
        t_constr = time.perf_counter() - t0

        t0 = time.perf_counter()
        text = slots.render({"observation": obs, "configuration": cfg, "seat": seat},
                            adm, hz, plan=self.plan,
                            tail_block=opportunity_block(card, seat, idle),
                            only_units=set(idle), show_market=False)
        rx = codec.slot_regex(adm, idle, max_slots=self.max_slots)
        t_prompt = time.perf_counter() - t0
        if rx is None:
            return None

        res = self.r.ask_regex(text, rx)

        t0 = time.perf_counter()
        decoded, rejected = None, None
        try:
            decoded = codec.decode_slots(res["output"], idle, max_slots=self.max_slots)
        except codec.Rejected as exc:
            rejected = exc.reason
        if decoded and decoded.get("plan"):
            self.plan = decoded["plan"]
        t_validate = time.perf_counter() - t0

        row = {
            "seed": card["seed"], "seat": seat, "step": card["step"],
            "day": card["day"], "hour": card["hour"],
            "idle_units": idle,
            "offered": [{"unit": o["unit"], "op": o["op"], "why": o["why"]}
                        for o in card["opportunities"] if o["unit"] in idle],
            "prompt": text, "raw_output": res["output"], "error": res["error"],
            "rejected": rejected,
            "slots": decoded["slots"] if decoded else None,
            "plan": decoded.get("plan") if decoded else None,
            "timing_s": {"constraint_calculation": round(t_constr, 4),
                         "prompt_build": round(t_prompt, 4),
                         "model_inference": round(res["wall_s"], 3),
                         "decode_validation": round(t_validate, 4)},
            "engine_counters": res["benchmark"],
        }
        self.log.append(row)
        return row
