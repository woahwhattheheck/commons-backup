"""Committed capacity envelope: real producer arrivals instead of a speculative bound.

T08's dated envelope protects capacity for deposits that *could* arrive, built by
`possible_extra_deposits`, which deliberately enumerates an upper bound -- every
worker against every animal, "even ones the cap chooser will reject". The fixed-
state ablation showed that envelope is what gates a sale the optimizer has already
valued: at case 669 all arms price SELL STRAWBERRY 3 at the same ~552, and only
the dated arm plans it.

That leaves one thing unseparated, and it is the thing that matters for the held
regression. The dated envelope could be winning because it is ACCURATE -- it dates
arrivals correctly -- or because it is LOOSE -- a bound that happens to release
capacity the base projection withheld. Those predict opposite outcomes.

This substitutes the actually committed arrivals for the speculative bound and
changes nothing else. The events come from `PlanOverlay.producer_snapshot`: whole
lots, at the exact phase the contract assigns them, only for errands this producer
has really committed to. Same selected action, same valuation, same price and
rival assumptions, same conserved inventory, same optimizer.

If accuracy is doing the work the committed envelope should hold the gain. If
looseness is, it should lose it.

T08's `conserved_sell_adapter.py` is imported and reused unmodified; the event
source is swapped for the duration of one call rather than its logic rewritten,
so the comparison isolates the envelope and not an accidental reimplementation.
"""

import os
import sys

T08 = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "cloud-titan-composition"))


def _t08():
    for p in (os.path.join(T08, "vendor", "sell"), T08):
        if p not in sys.path:
            sys.path.insert(0, p)
    import conserved_sell_adapter as conserved
    return conserved


def committed_events(snapshot, now, end, turns_per_day=24):
    """Producer arrivals as capacity events, in `possible_extra_deposits` shape.

    One event per errand that has capacity still to arrive, carrying the WHOLE
    remaining lot at the exact phase the arrival contract assigns:

      eod_auto        the automatic end-of-day deposit, which lands AFTER market
      worker_deposit  an explicit DROP/PLACE, which lands BEFORE market

    A lot already carried contributes nothing here: the profile's own state
    projection already holds it, and counting it twice is what an upper bound does.
    An aborted errand reserves nothing at all.
    """
    close = (now // turns_per_day + 1) * turns_per_day - 1
    events = []
    for plan in snapshot.get("plans", []):
        if plan.get("status") not in ("pending", "carried"):
            continue
        pending = int(plan.get("units_total", 0)) - int(
            plan.get("observed_carried_units", 0))
        if pending <= 0:
            continue
        arrival = int(plan.get("arrival_step", close))
        kind = plan.get("arrival_kind")
        if kind == "eod_auto":
            date, phase = min(arrival, close), "after"
        elif kind == "worker_deposit":
            date, phase = min(arrival, close), "before"
        else:
            continue                      # never infer a travel-only deposit
        if date <= end:
            events.append((date, phase, pending, "committed-cap",
                           plan["product"]))
    return sorted(events)


def make_committed_sell(base_owner, snapshot_provider):
    """A dated seller whose envelope is the committed arrivals.

    `snapshot_provider()` must return the producer snapshot for the SAME
    observation the transform is about to be called on.
    """
    conserved = _t08()

    class CommittedEnvelopeSell(conserved.DatedSelectedActionSell):
        """Reuses T08's dated feasibility logic with the event source swapped."""

        def receipt_profile(self, obs, base, farm, private, end, item, config):
            snap = snapshot_provider() or {"plans": []}
            now = int(obs["step"])
            original = conserved.possible_extra_deposits
            conserved.possible_extra_deposits = (
                lambda f, p, n, e, turns_per_day=24:
                committed_events(snap, n, e, turns_per_day))
            try:
                return super().receipt_profile(obs, base, farm, private, end,
                                               item, config)
            finally:
                conserved.possible_extra_deposits = original

    return CommittedEnvelopeSell(base_owner)


class CommittedCapSell:
    """Cap producer plus the committed-envelope seller, as one callable.

    The cap overlay authors the unit actions and publishes what it committed; the
    seller reserves capacity against exactly that. One parent controller, one
    production pass, the producer's own arrivals.
    """

    def __init__(self, route_aware=True):
        import arlene_plan
        import arrival_facts
        import native_motifs as NM
        import route_cards
        A, self.arlene_id = route_cards.load_arlene()
        chooser = (arrival_facts.RouteAwareCapChooser(NM.engine())
                   if route_aware else arlene_plan.CapChooser(NM.engine()))
        self.production = arlene_plan.PlanOverlay(A, chooser, one_way=True)
        if hasattr(chooser, "agent"):
            chooser.agent = self.production.agent
        self._snapshot = {"plans": []}
        self.execution = make_committed_sell(self.production.agent,
                                             lambda: self._snapshot)

    def act(self, obs, cfg=None):
        selected = self.production.act(obs)
        o = dict(obs)
        o.setdefault("step", int(obs["day"]) * 24 + int(obs["hour"]))
        o.setdefault("player", int(obs.get("player", 0)))
        self._snapshot = self.production.producer_snapshot(o, selected)
        return self.execution.transform(o, cfg, selected)


_INSTANCE = None


def agent(obs, cfg=None):
    global _INSTANCE
    step = obs.get("step")
    step = (int(step) if step is not None
            else int(obs.get("day", 0)) * 24 + int(obs.get("hour", 0)))
    if _INSTANCE is None or step == 0:
        _INSTANCE = CommittedCapSell()
    return _INSTANCE.act(obs, cfg)
