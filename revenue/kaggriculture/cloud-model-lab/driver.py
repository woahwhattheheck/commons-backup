"""The playable model driver: E4B authors farmer, hands and market for a real turn.

Per turn: derive the applicable constraint from the observation, build the operator
surface + state + horizon, decode under THIS card's admissible-set grammar, and
return the decoded action.

The model authors the action. Python supplies state and constraints and decodes; it
does not choose the op. A decode that fails is recorded as a rejection and the turn
falls back to the engine's own default PASS -- that fallback is counted as a
rejection, never reported as a model decision.
"""

import time

import codec
import constraints
import exemplars
import exemplar_bank as EB
import farmmap
import prompt as prompt_mod
import slots
import static_prefix

DEFAULT = {"farmer": ["PASS"], "hands": [], "market": []}


class ModelDriver:
    def __init__(self, runner, surfaces, max_market=3, constrained=True,
                 examples="pairs", bank=None, render="verbose"):
        self.r = runner
        self.examples = examples
        self.bank = bank
        # "verbose": the original renderer. "slots": every fact declared once with a
        # typed id, opcode semantics stated once, admissible lists referencing ids.
        self.render = render
        # "pairs": the six concatenated operator surfaces, cue last.
        # "bank":  1-2 class-matched, action-deduplicated advancing demonstrations
        #          placed immediately before the live state (the ported mechanism).
        self.head = exemplars.composed_pattern(surfaces) if examples == "pairs" else ""
        self.max_market = max_market
        self.constrained = constrained
        self.log = []
        self.plan = None
        self._static = None

    def act(self, obs, config, seat):
        t0 = time.perf_counter()
        hz = constraints.horizon(obs, config, seat)
        adm = constraints.admissible(obs, config, seat)
        t_constr = time.perf_counter() - t0

        card = {"observation": obs, "configuration": config, "seat": seat}
        t0 = time.perf_counter()
        if self._static is None:
            self._static = static_prefix.build(config)
        fmap = farmmap.build(obs, config, seat)
        bank_block, self._last_rows = "", []
        if self.examples == "bank" and self.bank is not None:
            cls = EB.situation_class(obs, config, seat, adm)
            live_lean = EB.structured_state(obs, config, seat)
            rows = self.bank.for_class(cls, EB.context_of(obs), n=2,
                                       exclude_state=live_lean,
                                       n_hands=len(adm["units"]) - 1)
            self._last_rows = rows
            bank_block = EB.block(rows)
            self._last_cls = cls
        if self.render == "slots":
            text = slots.render(card, adm, hz, plan=self.plan,
                                bank_block=bank_block, head=self.head or None)
        else:
            text = prompt_mod.build(card, adm, self.head, hz=hz, plan=self.plan,
                                    static=self._static, farm_map=fmap,
                                    bank_block=bank_block)
        rx = codec.card_regex(adm, max_market=self.max_market) if self.constrained else None
        t_prompt = time.perf_counter() - t0

        res = self.r.ask_regex(text, rx) if rx else self.r.ask(text)

        t0 = time.perf_counter()
        action, rejected = DEFAULT, None
        try:
            action = codec.decode_turn(res["output"])
        except codec.Rejected as exc:
            rejected = exc.reason
        if action.get("plan"):
            self.plan = action["plan"]      # model-authored, carried, never engine input
        verdict = codec.legality(action, adm)
        t_validate = time.perf_counter() - t0

        self.log.append({
            "day": int(obs["day"]), "hour": int(obs["hour"]),
            "prompt": text, "raw_output": res["output"], "error": res["error"],
            "rejected": rejected, "action": action, "plan": self.plan,
            "legal": verdict["legal"], "violations": verdict["violations"],
            "joint_blocks": verdict["joint_blocks"],
            "timing_s": {
                "constraint_calculation": round(t_constr, 4),
                "prompt_build": round(t_prompt, 4),
                "model_inference": round(res["wall_s"], 3),
                "prefill_ttft": res["benchmark"].get("time_to_first_token_in_second"),
                "decode_validation": round(t_validate, 4),
            },
            "engine_counters": res["benchmark"],
            "admissible_farmer_ops": [" ".join(str(t) for t in o) for o in adm["units"][0]],
            "_pending": True,
            "examples_mode": self.examples,
            "render": self.render,
            "situation_class": getattr(self, "_last_cls", None),
            "examples_used": [{"provenance": r["provenance"], "action": r["action"]}
                              for r in getattr(self, "_last_rows", [])],
        })
        return codec.engine_action(action)
