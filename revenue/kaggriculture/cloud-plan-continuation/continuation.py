# SPDX-License-Identifier: Apache-2.0
"""Optional continuation-aware consumer of T15's existing WholePlanSelector.

This adapter changes no optimizer, controller, probability, or source freeze.
It checks the selected plan's remaining schedule against current caller facts.
An emitted order is NOT a fill receipt. Optional injected observed-fill
reconciliation binds final actions separately; the caller owns real feasibility.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping

Validator = Callable[[dict[str, Any], dict[str, Any]], bool | None]


class ContinuationPlanSelector:
    """Wrap one fresh T15 selector for one actor/match; use it exclusively.

    ``continuation_feasible(remaining_plan, context)`` must return exactly True
    for a feasible continuation, False for infeasible, or None for unknown.
    Its inputs are detached copies. The context contains the current supplied
    observation, post-unit shed, reservations, configuration and lot metadata.
    The validator must use current caller-visible facts, not future truth.

    Only original ``feasible`` validates every constituent at commitment. This
    adapter additionally validates the selected remaining plan at every call.
    It neither infers fill receipts nor guarantees the supplied fallback legal.
    Supply fill_ledger and fill_verdict together to consume the existing own-fill
    component. After each returned due sale, call record_final with the actual
    final action and its exact post-unit snapshots. No injection preserves the
    original behavior and imports no new dependency.
    """

    def __init__(self, selector: Any, *, fill_ledger: Any = None,
                 fill_verdict: Callable[[Mapping[str, Any], int, int], bool | None] | None = None):
        if (fill_ledger is None) != (fill_verdict is None):
            raise ValueError('Supply both the observed-fill ledger and its verdict callable')
        self.selector = selector
        self.last_decision: dict[str, Any] = {'reason': 'not_called'}
        self._key: Any = None
        self._last_step: int | None = None
        self._emitted: set[int] = set()
        self._emitted_orders: dict[int, tuple[str, int, int]] = {}
        self._fill_ledger, self._fill_verdict = fill_ledger, fill_verdict
        self._fill_due: dict[str, Any] | None = None
        self._fill_error: str | None = None
        self.last_fill: dict[str, Any] = {'status': 'disabled' if fill_ledger is None else 'idle'}

    def record_final(self, observation: Mapping[str, Any], configuration: Any,
                     final_action: Any, *, post_unit_shed: Any,
                     post_unit_inventories: Any = None) -> dict[str, Any]:
        """Bind the selected due sale AFTER every final action transform.

        Pass the exact final unit-stage snapshots to the existing injected
        ObservedFillLedger. Same-step replacements require a new record. This
        records evidence; it neither changes nor submits the supplied action.
        """
        due = self._fill_due
        if self._fill_ledger is None or due is None:
            return {'status': 'disabled' if self._fill_ledger is None else 'no_due_sale'}
        try:
            now = self._step(observation, configuration or {})
            queue = final_action.get('market', [])
            order = queue[due['slot']]
            if (now != due['step'] or observation.get('player') != due['player']
                    or not isinstance(order, list)
                    or order[:3] != ['SELL', due['item'], due['quantity']]):
                raise ValueError('Final queue does not contain this plan emission')
            binding = self._fill_ledger.record(
                observation, configuration, final_action,
                post_unit_shed=post_unit_shed,
                post_unit_inventories=post_unit_inventories)
            if (binding.get('status') != 'recorded'
                    or binding.get('step') != due['step']
                    or binding.get('player') != due['player']):
                raise ValueError('Different action binding')
            due['binding'] = {k: binding[k] for k in ('step', 'player', 'action_sha256')}
            due.pop('record_error', None)
            self.last_fill = {'status': 'recorded', 'key': due['key'],
                              'slot': due['slot'], 'item': due['item'],
                              'quantity': due['quantity'], 'binding': deepcopy(due['binding'])}
        except Exception:
            # A later matching same-step record can replace this record attempt.
            due.pop('binding', None)
            due['record_error'] = 'final_sale_not_recorded'
            self.last_fill = {'status': 'unknown', 'reason': due['record_error'],
                              'key': due['key'], 'step': due['step']}
        return deepcopy(self.last_fill)

    def observe_fills(self, observation: Mapping[str, Any], configuration: Any = None) -> dict[str, Any]:
        """Consume the next own pre-unit observation, also usable at game end.

        Called automatically by transform before any suffix can advance. Only
        the injected quantity verdict is consumed, never cash or payoff claims.
        Failure is retained for transform's next fallback; no action is chosen
        by this method. A same-step read stays pending and does not consume it.
        """
        due = self._fill_due
        if self._fill_ledger is None or due is None:
            return deepcopy(self.last_fill)
        result = None
        reason, verdict = 'previous_fill_unknown', None
        try:
            now = self._step(observation, configuration or {'turnsPerDay': due['tpd']})
            if now == due['step'] and observation.get('player') == due['player']:
                return {'status': 'pending', 'key': due['key'], 'step': due['step']}
            if 'binding' not in due:
                reason = due.get('record_error', 'final_sale_not_recorded')
            elif now != due['step'] + 1 or observation.get('player') != due['player']:
                reason = 'fill_observation_not_adjacent'
            else:
                result = self._fill_ledger.observe(observation)
                if result.get('binding') != due['binding']:
                    reason = 'fill_binding_mismatch'
                else:
                    row = next((r for r in result.get('orders', [])
                                if r.get('slot') == due['slot']), None)
                    if row is not None and row.get('item') == due['item']:
                        verdict = self._fill_verdict(result, due['slot'], due['quantity'])
                    if verdict is False:
                        reason = 'previous_sale_short_fill'
                    elif verdict is True:
                        reason = 'previous_sale_filled'
        except Exception:
            reason, verdict = 'fill_observation_error', None
        self.last_fill = {'status': 'filled' if verdict is True else 'short_fill' if verdict is False else 'unknown',
                          'reason': reason, 'key': due['key'], 'step': due['step'],
                          'player': due['player'], 'item': due['item'], 'slot': due['slot'],
                          'quantity': due['quantity'], 'verdict': verdict,
                          'result': deepcopy(result)}
        self._fill_due = None
        if verdict is not True:
            self._fill_error = reason
            self.selector.completed.add(due['key'])
        return deepcopy(self.last_fill)

    @property
    def draws(self) -> int:
        return self.selector.draws

    @property
    def active(self) -> dict[str, Any] | None:
        return deepcopy(self.selector.active)

    @staticmethod
    def _step(observation: Mapping[str, Any], configuration: Mapping[str, Any]) -> int:
        if 'step' in observation:
            return int(observation['step'])
        return (int(observation.get('day', 0))
                * int(configuration.get('turnsPerDay', 24))
                + int(observation.get('hour', 0)))

    def _abort(self, reason: str, now: int, base_action: Any,
               **details: Any) -> Any:
        active = self.selector.active
        key = active['key'] if active is not None else self._key
        if active is not None:
            self.selector.completed.add(key)
            self.selector.active = None
        self.last_decision = {'reason': reason, 'key': key, 'step': now,
                              'fallback_preserved': True, **details}
        self.selector.last_decision = deepcopy(self.last_decision)
        self._key, self._last_step, self._emitted = None, None, set()
        self._emitted_orders = {}
        self._fill_due, self._fill_error = None, None
        return deepcopy(base_action)

    @staticmethod
    def _check(active: dict[str, Any], now: int, observation: Mapping[str, Any],
               configuration: Mapping[str, Any], post_unit_shed: Any,
               reservations: Any, validator: Validator | None) -> str | None:
        if validator is None:
            return 'continuation_unknown'
        remaining = deepcopy(active['plan'])
        remaining['sales'] = [[t, q] for t, q in remaining['sales'] if t >= now]
        context = deepcopy({
            'key': active['key'], 'item': active['item'], 'slot': active['slot'],
            'original_quantity': active['quantity'],
            'remaining_quantity': sum(q for t, q in remaining['sales']),
            'now': now, 'end': active['end'], 'decision_step': active['now'],
            'plan_index': active['plan_index'],
            'observation': observation, 'configuration': configuration,
            'post_unit_shed': post_unit_shed, 'reservations': reservations or {},
        })
        try:
            verdict = validator(remaining, context)
        except Exception:
            # Do not expose arbitrary callback exception text in public traces.
            return 'continuation_error'
        if verdict is True:
            return None
        if verdict is False:
            return 'continuation_infeasible'
        if verdict is None:
            return 'continuation_unknown'
        return 'continuation_invalid_verdict'

    def transform(self, observation: Mapping[str, Any], configuration: Any,
                  base_action: Any, *, continuation_feasible: Validator | None,
                  window: Any = None, post_unit_shed: Any = None,
                  reservations: Any = None, feasible: Any = None,
                  mode: str = 'mixed') -> Any:
        """Return one action; preserve fallback and retire invalidated keys.

        A repeat at the same decision step emits the same committed choice,
        subject to current feasibility, without another random draw. Missing
        a positive-quantity due date or going backward abandons the old window.
        Skipping dates with no due sale is allowed. No catch-up sale is invented.
        """
        cfg = configuration or {}
        now = self._step(observation, cfg)
        if self._fill_ledger is not None:
            self.observe_fills(observation, cfg)
            if self._fill_error is not None:
                return self._abort(self._fill_error, now, base_action)
        before = self.selector.active
        checked_key = object()  # None is a valid caller key.
        if before is not None:
            key = before['key']
            if self._key == key and self._last_step is not None and now < self._last_step:
                return self._abort('decision_time_reversed', now, base_action)
            emitted = self._emitted if self._key == key else set()
            missing = [t for t, q in before['plan']['sales']
                       if q > 0 and t < now and t not in emitted]
            if missing:
                return self._abort('due_step_not_emitted', now, base_action,
                                   missing_steps=missing)
            if self._key == key:
                # A new observed suffix may change future dates, never the
                # product, fixed slot or quantity already emitted before now.
                prefix = sorted((t, before['item'], before['slot'], q)
                                for t, q in before['plan']['sales'] if q > 0 and t < now)
                emitted_prefix = sorted((t, *order) for t, order in self._emitted_orders.items()
                                        if t < now)
                if prefix != emitted_prefix:
                    return self._abort('emitted_prefix_changed', now, base_action)
            if any(q > 0 and t >= now for t, q in before['plan']['sales']):
                reason = self._check(before, now, observation, cfg, post_unit_shed,
                                     reservations, continuation_feasible)
                if reason:
                    return self._abort(reason, now, base_action)
                checked_key = key
        elif continuation_feasible is None:
            self.last_decision = {'reason': 'continuation_unknown', 'step': now,
                                  'fallback_preserved': True}
            return deepcopy(base_action)

        out = self.selector.transform(
            observation, configuration, base_action, window=window,
            post_unit_shed=post_unit_shed, reservations=reservations,
            feasible=feasible, mode=mode)
        active = self.selector.active
        if active is not None:
            key = active['key']
            if checked_key != key:
                reason = self._check(active, now, observation, cfg, post_unit_shed,
                                     reservations, continuation_feasible)
                if reason:
                    return self._abort(reason, now, base_action)
            if self._key != key:
                self._key, self._last_step, self._emitted = key, None, set()
                self._emitted_orders = {}
            self._last_step = now
            decision = self.selector.last_decision
            if decision.get('reason') == 'executed' and decision.get('due', 0) > 0:
                self._emitted.add(now)
                self._emitted_orders[now] = (active['item'], active['slot'], decision['due'])
                if self._fill_ledger is not None:
                    self._fill_due = {'key': key, 'step': now,
                                      'player': observation.get('player'),
                                      'tpd': int(cfg.get('turnsPerDay', 24)),
                                      'item': active['item'], 'slot': active['slot'],
                                      'quantity': decision['due']}
        else:
            self._key, self._last_step, self._emitted = None, None, set()
            self._emitted_orders = {}
            if self.selector.last_decision.get('reason') == 'commitment_aborted':
                out = deepcopy(base_action)
        self.last_decision = deepcopy(self.selector.last_decision)
        return out
