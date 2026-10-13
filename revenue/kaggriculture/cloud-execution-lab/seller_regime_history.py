# SPDX-License-Identifier: Apache-2.0
"""Bounded public-only regime evidence for experimental SELL scheduling.

This helper does not infer hidden rival stock or assign probabilities.  It keeps
canonical short-memory harvest evidence, permits a repeated-event long-memory
stress signal, and forgets pre-change evidence only after a public production
mix change persists across consecutive observations.
"""
from __future__ import annotations

from collections import defaultdict
from math import ceil


class PublicRegimeHistory:
    """Finite public evidence with conservative ambiguity handling.

    `harvests` records only yield decreases on the same still-visible producer.
    `flows` records only a lower bound on rival admitted market supply after
    known town absorption and the full requested own SELL quantity are removed.
    The two streams are never added together when converted to a stress size.
    """

    def __init__(self, *, short_window=8, long_window=24, minimum_repeat=2,
                 change_confirmations=2, capacity=100):
        self.short_window = max(1, int(short_window))
        self.long_window = max(self.short_window, int(long_window))
        self.minimum_repeat = max(2, int(minimum_repeat))
        self.change_confirmations = max(2, int(change_confirmations))
        self.capacity = max(1, int(capacity))
        self.harvests = defaultdict(list)
        self.flows = defaultdict(list)
        self.stable_mix = None
        self.candidate_mix = None
        self.candidate_streak = 0
        self.regime_step = 0
        self.mix_observed_step = None
        self.last_diagnostics = {}

    @staticmethod
    def _identity(tile):
        if not isinstance(tile, dict):
            return None
        return (tile.get('kind'), tile.get('crop'), tile.get('animal'))

    @staticmethod
    def _requested_sales(action, products, slots):
        result = {p: 0 for p in products}
        if action is None:
            return None
        for order in action.get('market', [])[:slots]:
            if order and len(order) >= 3 and order[0] == 'SELL' and order[1] in result:
                result[order[1]] += max(0, int(order[2]))
        return result

    def _mix(self, farm, products, product_of):
        counts = {p: 0 for p in products}
        for row in farm.get('tiles', []):
            for tile in row:
                product = product_of(tile)
                if product in counts:
                    counts[product] += 1
        return tuple((p, counts[p]) for p in products)

    def _seed_mix(self, now, mix, *, clear_evidence=False):
        if clear_evidence:
            self.harvests.clear()
            self.flows.clear()
        self.stable_mix = mix
        self.candidate_mix = None
        self.candidate_streak = 0
        self.regime_step = now
        self.mix_observed_step = now

    def _update_mix(self, now, mix):
        changed = False
        if self.stable_mix is None or self.mix_observed_step is None:
            self._seed_mix(now, mix)
            return changed

        # Retry callbacks may repeat the exact same public step.  Persistence is
        # evidence across distinct observations in time, not callback count.  A
        # same-step replacement may revise the candidate, but never advances it.
        if now == self.mix_observed_step:
            if mix == self.stable_mix:
                self.candidate_mix = None
                self.candidate_streak = 0
            elif mix != self.candidate_mix:
                self.candidate_mix = mix
                self.candidate_streak = 1
            return changed

        # A strictly backward observation is a new-game/rewind boundary for this
        # bounded helper.  Old evidence cannot safely be attributed across it.
        if now < self.mix_observed_step:
            self._seed_mix(now, mix, clear_evidence=True)
            return changed

        self.mix_observed_step = now
        if mix == self.stable_mix:
            self.candidate_mix = None
            self.candidate_streak = 0
            return changed
        if mix == self.candidate_mix:
            self.candidate_streak += 1
        else:
            self.candidate_mix = mix
            self.candidate_streak = 1
        if self.candidate_streak >= self.change_confirmations:
            self.stable_mix = mix
            self.candidate_mix = None
            self.candidate_streak = 0
            self.regime_step = now
            changed = True
        return changed

    def _prune(self, now):
        cutoff = max(self.regime_step, now - self.long_window)
        for store in (self.harvests, self.flows):
            for product in list(store):
                store[product] = [(t, q) for t, q in store[product]
                                  if t >= cutoff and q > 0]
                if not store[product]:
                    del store[product]

    def observe(self, previous, current, previous_action, configuration, *,
                products, product_of, absorption):
        """Consume one adjacent public observation transition.

        `absorption(product, step, shops, configuration)` must return the known
        town/shop removal for the prior market step.  When the previous returned
        action is unavailable, residual market flow remains unknown rather than
        being treated as rival supply.
        """
        now = int(current['step'])
        player = int(current['player'])
        rival = current['farms'][1 - player]
        mix_changed = self._update_mix(now, self._mix(rival, products, product_of))
        harvest_added = {}
        flow_added = {}

        if previous is not None and int(previous.get('player', player)) == player:
            prior_step = int(previous['step'])
            if now == prior_step + 1:
                old_tiles = previous['farms'][1 - player].get('tiles', [])
                new_tiles = rival.get('tiles', [])
                for y, row in enumerate(old_tiles):
                    if y >= len(new_tiles):
                        continue
                    for x, tile in enumerate(row):
                        if x >= len(new_tiles[y]):
                            continue
                        later = new_tiles[y][x]
                        product = product_of(tile)
                        if product not in products:
                            continue
                        # Removal/replacement is a production-regime signal, not
                        # automatically a harvest receipt.
                        if self._identity(tile) != self._identity(later):
                            continue
                        before_yield = max(0, int(tile.get('yield_units', 0)))
                        after_yield = max(0, int(later.get('yield_units', 0)))
                        if before_yield > after_yield:
                            quantity = before_yield - after_yield
                            self.harvests[product].append((now, quantity))
                            harvest_added[product] = harvest_added.get(product, 0) + quantity

                slots = max(1, int(configuration.get('maxMarketOrdersPerTurn', 10)))
                own_sales = self._requested_sales(previous_action, products, slots)
                if own_sales is not None:
                    shops = previous.get('town', {}).get('unlocked_shops', [])
                    old_market = previous.get('market', {}).get('inventory', {})
                    new_market = current.get('market', {}).get('inventory', {})
                    for product in products:
                        if product not in old_market or product not in new_market:
                            continue
                        consumed = max(0, int(absorption(product, prior_step, shops,
                                                        configuration)))
                        admitted = int(new_market[product]) - int(old_market[product]) + consumed
                        # Requested own SELL is an upper bound on own admitted
                        # supply.  Anything beyond it is a conservative rival
                        # lower bound. Negative residuals remain ambiguous.
                        lower = max(0, admitted - own_sales.get(product, 0))
                        if lower:
                            self.flows[product].append((now, lower))
                            flow_added[product] = lower

        self._prune(now)
        self.last_diagnostics = {
            'step': now,
            'regime_step': self.regime_step,
            'mix_changed': mix_changed,
            'mix_candidate_streak': self.candidate_streak,
            'harvest_added': harvest_added,
            'rival_supply_lower_added': flow_added,
        }
        return dict(self.last_diagnostics)

    def signal(self, now, product, *, visible=0):
        """Return bounded short/long scenario magnitudes, never probabilities."""
        now = int(now)
        visible = max(0, int(visible))
        short_cutoff = max(self.regime_step, now - self.short_window)
        long_cutoff = max(self.regime_step, now - self.long_window)
        harvest = [(t, q) for t, q in self.harvests.get(product, []) if t >= long_cutoff]
        flows = [(t, q) for t, q in self.flows.get(product, []) if t >= long_cutoff]
        harvest_short = sum(q for t, q in harvest if t >= short_cutoff)
        flow_short = sum(q for t, q in flows if t >= short_cutoff)
        short = max(harvest_short, flow_short)
        # Repeat admission is stream-local. A large old harvest and one tiny
        # later residual-flow observation are two different public explanations,
        # not evidence that either explanation repeated. Mixing their timestamps
        # would let cross-stream noise resurrect an old outlier.
        harvest_support = len({t for t, _ in harvest})
        flow_support = len({t for t, _ in flows})
        harvest_total = sum(q for _, q in harvest)
        flow_total = sum(q for _, q in flows)
        harvest_long_rate = 0
        flow_long_rate = 0
        if harvest_support >= self.minimum_repeat and harvest_total:
            harvest_long_rate = ceil(harvest_total * self.short_window / self.long_window)
        if flow_support >= self.minimum_repeat and flow_total:
            flow_long_rate = ceil(flow_total * self.short_window / self.long_window)
        long_rate = max(harvest_long_rate, flow_long_rate)
        support = max(harvest_support, flow_support)
        stress = min(self.capacity, max(visible, short, long_rate))
        return {
            'product': product,
            'visible': visible,
            'short': short,
            'long_rate': long_rate,
            'repeat_support': support,
            'harvest_repeat_support': harvest_support,
            'flow_repeat_support': flow_support,
            'stress': stress,
            'regime_step': self.regime_step,
            'interpretation': 'bounded public stress sizes; no calibrated probability or hidden stock',
        }
