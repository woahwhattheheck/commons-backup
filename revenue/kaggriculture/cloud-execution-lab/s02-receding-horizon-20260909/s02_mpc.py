# SPDX-License-Identifier: Apache-2.0
"""S02 fail-closed receding-horizon route evaluator.

The live Kaggriculture observation exposes both public farms but only the active
player's private inventory/seeds.  The official interpreter requires each
player's private packet to execute exact reacting future transitions.  This
module refuses to smuggle that missing rival state (or the hidden day RNG seed)
into an MPC score.  It therefore changes a route only when an exact rollout
packet can be certified from allowed inputs; ordinary competition observations
fall back to the incumbent route/action.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

HORIZONS = (6, 12, 24)
DECISION_STEPS = (226, 360, 433)
OBLIGATION_ITEMS = {
    'FEED': 'WHEAT',
    'FERTILIZE': 'FERTILIZER',
}


def _step(obs: dict[str, Any], cfg: dict[str, Any]) -> int:
    value = obs.get('step')
    if value is not None:
        return int(value)
    return int(obs.get('day', 0)) * int(cfg.get('turnsPerDay', 24)) + int(obs.get('hour', 0))


def prefix_compatible_routes(routes, current, now):
    """Return route ids with an exact action prefix through `now - 1`."""
    base = routes[current]
    return tuple(sorted(
        key for key, rows in routes.items()
        if key != current and len(rows) > now and len(base) > now
        and all(base[t] == rows[t] for t in range(now))
    ))


def _crosses_day_randomness(now: int, horizon: int, turns_per_day: int) -> bool:
    # The official interpreter invokes _end_of_day after transition t whenever
    # (t + 1) % turns_per_day == 0; weeds and periodic shop unlocks use env.info seed.
    return any((t + 1) % turns_per_day == 0 for t in range(now, now + horizon))


@dataclass(frozen=True)
class Certificate:
    exact: bool
    reasons: tuple[str, ...]
    horizon: int
    now: int


def visibility_certificate(obs, cfg, horizon: int) -> Certificate:
    """Certify whether an exact reacting official-engine rollout is observable.

    Injected ad-hoc keys such as rival_private are deliberately ignored.  Only
    the competition observation schema is admissible.
    """
    now = _step(obs, cfg)
    reasons = []
    if horizon not in HORIZONS:
        reasons.append('unsupported_horizon')
    farms = obs.get('farms') or []
    player = int(obs.get('player', 0))
    private = obs.get('private')
    if not isinstance(private, dict):
        reasons.append('missing_own_private')
    if len(farms) > 1:
        # Official interpreter state[i].observation.private is distinct for each
        # player. The live observation contains only the active player's packet.
        reasons.append('missing_rival_private_for_exact_reacting_transition')
    if not (0 <= player < len(farms)):
        reasons.append('missing_public_farm')
    turns = max(1, int(cfg.get('turnsPerDay', 24)))
    if horizon in HORIZONS and _crosses_day_randomness(now, horizon, turns):
        reasons.append('hidden_end_of_day_rng_seed')
    return Certificate(not reasons, tuple(reasons), int(horizon), now)


def _units(row):
    return [row.get('farmer') or ['PASS'], *(row.get('hands') or [])]


def would_strand_obligation(obs, candidate, route, horizon: int) -> bool:
    """Reject liquidation that consumes an owned input needed by the route suffix.

    This is intentionally one-sided: it never credits future purchases, rival
    inventory or replay suffix outcomes.  It is a safety gate, not a value model.
    """
    cfg = {'turnsPerDay': 24}
    now = _step(obs, cfg)
    private = obs.get('private') or {}
    shed = {k: max(0, int(v)) for k, v in (private.get('shed') or {}).items()}
    inventories = private.get('inventories') or []
    owned = dict(shed)
    for inv in inventories:
        for item, n in (inv or {}).items():
            owned[item] = owned.get(item, 0) + max(0, int(n))
    sold = {}
    for order in (candidate.get('market') or [])[:10]:
        if order and len(order) >= 3 and order[0] == 'SELL':
            sold[order[1]] = sold.get(order[1], 0) + max(0, int(order[2]))
    end = min(len(route), now + max(0, int(horizon)))
    need = {}
    for t in range(now + 1, end):
        row = route[t]
        for action in _units(row):
            if not action:
                continue
            item = OBLIGATION_ITEMS.get(action[0])
            if item:
                need[item] = need.get(item, 0) + 1
            elif action[0] == 'PLANT' and len(action) > 1:
                seed = 'SEED:' + str(action[1])
                need[seed] = need.get(seed, 0) + 1
    for item, n in need.items():
        if item.startswith('SEED:'):
            crop = item.split(':', 1)[1]
            have = max(0, int((private.get('seeds') or {}).get(crop, 0)))
            if have < n:
                return True
            continue
        if owned.get(item, 0) - sold.get(item, 0) < n:
            return True
    return False


class RecedingHorizonGate:
    """Fail-closed S02 gate. It never guesses hidden state."""
    def __init__(self, horizon: int):
        if horizon not in HORIZONS:
            raise ValueError('horizon must be one of 6/12/24')
        self.horizon = int(horizon)
        self.calls = 0
        self.fallbacks = 0
        self.last = None

    def inspect(self, obs, cfg, *, routes=None, current=None):
        self.calls += 1
        cert = visibility_certificate(obs, cfg, self.horizon)
        now = cert.now
        compat = () if routes is None or current is None else prefix_compatible_routes(routes, current, now)
        report = {
            'step': now,
            'horizon': self.horizon,
            'exact_rollout_certified': cert.exact,
            'reasons': list(cert.reasons),
            'prefix_compatible_routes': list(compat),
            'changed_route': False,
            'fallback': not cert.exact,
        }
        if not cert.exact:
            self.fallbacks += 1
        self.last = report
        return report
