"""Runnable T03 joint-route variant composed with intact Arlene and the T04 oracle.

The first policy version begins after Arlene's final branch decision (day 19).
It preserves portfolio/hiring orders and does not implement T05's final-day
collector. Once active, every day's operations are target jobs executed from
observations; it never rejoins an old movement-tape offset after a route change.
"""
from __future__ import annotations

from copy import copy
import time
import json
from scheduler import JointPlan, decode_day, remaining, search, capital_signature


def fork_parent(parent):
    out = copy(parent)
    # Route rows are immutable inputs. Private lists permit a temporary current
    # row substitution for the parent's existing sell/cap/terminal logic only.
    out.R = {key: list(rows) for key, rows in parent.R.items()}
    return out


def market_with_workers(parent, obs, workers):
    """Recompute inherited sells for these actual actions and visible inventories."""
    step = int(obs["step"])
    rows = parent.R[parent.cur]
    saved = rows[step]
    rows[step] = {**saved, "farmer": workers[0], "hands": workers[1:]}
    try:
        computed = parent.act(obs)
    finally:
        rows[step] = saved
    return {"farmer": workers[0], "hands": workers[1:], "market": computed.get("market", [])}


class Continuation:
    """An independent callable multi-day joint plan for exact own-state replay."""
    def __init__(self, parent, day_cache, queues, start_step, *, turns_per_day=24):
        self.parent = fork_parent(parent)
        self.cache = day_cache
        self.day = start_step // turns_per_day
        self.plan = JointPlan(queues)
        self.turns_per_day = turns_per_day
        self.missed = []
        self.checkpoints = {}

    def __call__(self, obs):
        day = int(obs["step"]) // self.turns_per_day
        if day != self.day:
            for visits in self.plan.pending().values():
                self.missed.extend(v.id for v in visits)
            self.missed.extend(self.plan.missed)
            self.day = day
            key = (self.parent.cur, day)
            if key not in self.cache:
                self.cache[key] = decode_day(self.parent.R[self.parent.cur], day)
            self.plan = JointPlan(self.cache[key])
        if int(obs["step"]) % self.turns_per_day in (0, 2):
            self.checkpoints[int(obs["step"])] = capital_signature(
                obs["farms"][int(obs["player"])], obs["private"])
        workers = self.plan.actions(obs)
        return market_with_workers(self.parent, obs, workers)


class RollingAgent:
    """Stateful policy factory; instantiate once per game, never across games."""
    def __init__(self, arlene_module, engine, oracle, *, first_day=19,
                 max_candidates=2, budget_seconds=.72):
        self.parent = fork_parent(arlene_module.Agent())
        self.engine, self.oracle = engine, oracle
        self.first_day = first_day
        self.max_candidates, self.budget_seconds = max_candidates, budget_seconds
        self.cache = {}
        self.day, self.plan = None, None
        self.events = []

    def act(self, obs, configuration):
        step = int(obs["step"])
        day, hour = divmod(step, 24)
        inherited = self.parent.act(obs)
        if day < self.first_day:
            return inherited
        if day != self.day:
            self.day = day
            key = (self.parent.cur, day)
            if key not in self.cache:
                self.cache[key] = decode_day(self.parent.R[self.parent.cur], day)
            self.plan = JointPlan(remaining(self.cache[key], step, len(self.cache[key])))
        # The daily workforce is in place after the normal two hiring decisions.
        # All actually existing workers participate; no arbitrary worker-count cap.
        if hour == 2 and day < 29:
            queues = self.plan.pending()
            workers = 1 + len(obs["farms"][int(obs["player"])] .get("hands", []))
            queues = {i: queues.get(i, ()) for i in range(workers)}
            horizon = 718  # Full nominal continuation: actual final cash, no inventory liquidation proxy.
            # Remove only attribute-access dict subclasses; repeated deepcopy of
            # the official wrapper costs substantially more than plain JSON data.
            plain_observation = json.loads(json.dumps(obs, allow_nan=False))
            plain_configuration = dict(configuration)
            def evaluate(proposal):
                controller = Continuation(self.parent, self.cache, proposal, step)
                result = self.oracle.simulate_bundle(self.engine, plain_observation, plain_configuration,
                                                     controller, end_step=horizon)
                result["missed_jobs"] = list(controller.missed) + [v.id for row in controller.plan.pending().values() for v in row]
                result["capital_checkpoints"] = controller.checkpoints
                return result
            found = search(queues, obs, evaluate, max_candidates=self.max_candidates,
                           budget_seconds=self.budget_seconds)
            self.plan = JointPlan(found.queues)
            self.events.append({"step": step, "workers": workers, "selection": found.label,
                                "evaluated": found.evaluated, "rejected": found.rejected,
                                "nominal_cash_gain": found.value, "seconds": found.elapsed_seconds,
                                "budget_exhausted": found.exhausted, "horizon": horizon})
        return market_with_workers(self.parent, obs, self.plan.actions(obs))
