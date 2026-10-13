"""Seed recovery x committed producer envelope: a 2x2 over ONE production parent.

Two additive switches over a single intact selected parent, so the four arms differ
only by which switches are on:

  seed       T13's `SeedBudget` (cloud-hosted-loss-response/seed_budget.py, imported
             unmodified) applied to the emitted action's BUY_SEED slots.
  committed  the capacity envelope built from THIS producer's committed arrivals
             (`committed_envelope.make_committed_sell`) instead of T08's speculative
             `possible_extra_deposits` upper bound.

The production layer, the parent call, the optimizer and the opponent are identical
in all four arms. Nothing in T08's or T13's tree is edited; both are imported.

ONE PARENT ACTION. `PlanOverlay.act` calls intact Arlene exactly once per turn, and
the SELL execution consumes that already-selected action through T08's
`SelectedAction` proxy, which raises if it is asked for a second one. `post_units`
is the engine's own deterministic unit stage on a copy, not a policy call.

DECLARED OWNERSHIP of the emitted action, disjoint by construction:

  farmer/hands slots   PlanOverlay's cap overlay, and only inside a literal-PASS
                       window read off the parent's tape.
  market SELL slots    the SELL execution layer.
  market BUY_SEED      SeedBudget, reduction only, index preserving.
  arrivals             PlanOverlay's `producer_snapshot`; the committed envelope is
                       the only consumer.

T13's demand contract says its bound is for intact Arlene/SELL routes and must not
be stacked with an overlay that adds PLANT requests or rewrites routes. The cap
overlay does neither -- `conserve.py` in this directory checks both on real games
rather than asserting it.
"""

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
T13 = os.path.realpath(os.path.join(HERE, "..", "cloud-hosted-loss-response"))
T08 = os.path.realpath(os.path.join(HERE, "..", "cloud-titan-composition"))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def seed_budget_module():
    """T13's frozen budget, byte-for-byte from its owner's path."""
    return _load("t13_seed_budget", os.path.join(T13, "seed_budget.py"))


def normalise(obs, seat=None):
    """Supply the absolute clock and seat the engine leaves off seat 1.

    Third consumer of this gap after `build_arrival_contract` and the frozen
    scheduler: T13's `seed_main.agent` also indexes `observation['step']`
    directly and raises KeyError on a seat-1 observation. Normalised in the
    harness only; no policy under test is modified.
    """
    o = dict(obs)
    if o.get("step") is None:
        o["step"] = int(o["day"]) * 24 + int(o["hour"])
    if seat is not None:
        o.setdefault("player", seat)
    else:
        o.setdefault("player", 0)
    return o


class Arm:
    """One production parent, two independent switches."""

    def __init__(self, seed=False, committed=False, route_aware=True, trace=None,
                 overlay=True):
        import arlene_plan
        import arrival_facts
        import committed_envelope
        import native_motifs as NM
        import route_cards

        A, self.arlene_id = route_cards.load_arlene()
        # `overlay=False` drops the cap production layer entirely, leaving the bare
        # intact parent. That is T13's OWN parent, and running the seed switch on
        # both is how "does stacking change T13's behaviour" gets measured instead
        # of assumed. The committed envelope needs a producer, so it is refused here.
        self.overlay_on = bool(overlay)
        if not self.overlay_on:
            if committed:
                raise ValueError("the committed envelope needs a producer snapshot; "
                                 "it cannot run with overlay=False")
            self.production = None
            self.parent = A.Agent()
        else:
            chooser = (arrival_facts.RouteAwareCapChooser(NM.engine())
                       if route_aware else arlene_plan.CapChooser(NM.engine()))
            self.production = arlene_plan.PlanOverlay(A, chooser, one_way=True)
            if hasattr(chooser, "agent"):
                chooser.agent = self.production.agent
            self.parent = self.production.agent      # the intact Arlene Agent
        self._snapshot = {"plans": []}

        conserved = committed_envelope._t08()
        self.conserved = conserved
        if committed:
            self.execution = committed_envelope.make_committed_sell(
                self.parent, lambda: self._snapshot)
        else:
            self.execution = conserved.DatedSelectedActionSell(self.parent)

        import scheduler as sell_scheduler       # T08's frozen vendor/sell
        self.scheduler = sell_scheduler
        self.budget = seed_budget_module().SeedBudget(self.parent.R) if seed else None
        self.seed_on, self.committed_on = bool(seed), bool(committed)
        self.trace = trace                       # optional conservation recorder
        self.parent_calls = 0
        self.last_base = None
        self._wrap_parent()

    def _wrap_parent(self):
        """Count parent decisions so 'exactly one parent action' is measured."""
        inner = self.parent.act

        def counted(obs):
            self.parent_calls += 1
            self.last_base = inner(obs)
            return self.last_base

        self.parent.act = counted

    def act(self, obs, cfg=None):
        before = self.parent_calls
        o = normalise(obs)
        if self.production is None:
            selected = self.parent.act(obs)
        else:
            selected = self.production.act(obs)
            self._snapshot = self.production.producer_snapshot(o, selected)
        action = self.execution.transform(o, cfg, selected)
        pre_budget = action
        if self.budget is not None and any(
                x and x[0] == "BUY_SEED" for x in action.get("market", [])):
            _, private = self.scheduler.post_units(o, action, dict(cfg or {}))
            action = self.budget.apply(
                action, private["seeds"], int(o["step"]), self.parent.cur,
                int((cfg or {}).get("maxMarketOrdersPerTurn", 10)))
        if self.trace is not None:
            self.trace.record(o, self.last_base, selected, pre_budget, action,
                              self.parent_calls - before, self.parent)
        return action


ARMS = {
    "baseline":  dict(seed=False, committed=False),
    "seed":      dict(seed=True,  committed=False),
    "committed": dict(seed=False, committed=True),
    "combined":  dict(seed=True,  committed=True),
    # compatibility references: the same switch without this lab's production layer
    "bare":      dict(seed=False, committed=False, overlay=False),
    "bare_seed": dict(seed=True,  committed=False, overlay=False),
}


def make(name, **kw):
    return Arm(**dict(ARMS[name], **kw))
