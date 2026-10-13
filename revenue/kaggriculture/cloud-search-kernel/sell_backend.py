# SPDX-License-Identifier: Apache-2.0
"""Optional search backend for the existing, unchanged TITAN SELL scheduler.

Reuses its exact MarketPath and SORREL receipt primitive. Does not rewrite unit
routes, service logic, purchase order slots, feasibility, or scenario weighting.
The search state carries a dated common plan, own stock, shared market inventory,
and both cash receipts. No hypothetical rival stock is read from an observation.
"""
from dataclasses import asdict
from search_kernel import Model, Limits, Infeasible, search


def make_optimizer(scheduler, *, seconds=0.03, max_transitions=3500,
                   cache=True, ordering=True, iterative=True):
    original = scheduler.optimize_lot

    def optimize_lot(*, item, quantity, inventory, params, shops, config, now,
                     dates, reference, rival_quantity, minimum_now=0,
                     capacity_ok=None, last=718):
        dates = tuple(dates)
        if not dates or dates[0] != now or tuple(sorted(set(dates))) != dates or dates[-1] > last:
            raise ValueError('dates must be unique, ascending, start now and end by last sale')
        incoming_reference = tuple(reference)
        # The legacy optimizer is a real, already working capability. Complete it
        # first and keep its entire plan/receipt as the incumbent. The bounded
        # search is an opt-in augmentation, not a cheaper replacement for it.
        incumbent_plan, incumbent_info = original(
            item=item, quantity=quantity, inventory=inventory, params=params,
            shops=shops, config=config, now=now, dates=dates,
            reference=incoming_reference, rival_quantity=rival_quantity,
            minimum_now=minimum_now, capacity_ok=capacity_ok, last=last)
        reference = tuple(incumbent_plan)
        if not incumbent_info.get('feasible') or incumbent_info.get('forced_feasibility'):
            incumbent_info['search'] = {'status': 'legacy_feasibility_recovery'}
            return incumbent_plan, incumbent_info
        end = dates[-1]
        path = scheduler.MarketPath(item, inventory, params, shops, config, now, end)
        scenarios = [('no_rival', 0, 'paired'),
                     ('observed_paired', rival_quantity, 'paired'),
                     ('observed_later_order', rival_quantity, 'after')]
        if end > now:
            scenarios.append(('observed_next_turn', ((now + 1, rival_quantity),), 'paired'))
        if end > now + 2:
            scenarios.append(('observed_before_delayed_batch', ((end - 1, rival_quantity),), 'paired'))
        baselines = {name: path.score(reference, quantity, rival, alignment, end == last)
                     for name, rival, alignment in scenarios}
        # State: date index, stock, market inventory, own cash, rival cash, dated plan.
        initial = (0, quantity, inventory, 0, 0, ())

        def candidates(state):
            index, remaining, *_ = state
            if index == len(dates):
                return ()
            lower = minimum_now if index == 0 else 0
            inherited = min(remaining, max(0, dict(reference).get(dates[index], 0)))
            return tuple(sorted({q for q in (lower, inherited, remaining // 4,
                                             remaining // 2, remaining * 3 // 4, remaining)
                                 if lower <= q <= remaining}))

        def transition(state, amount, scenario):
            index, remaining, inv, own_cash, rival_cash, plan = state
            if index >= len(dates) or amount not in candidates(state):
                raise Infeasible('amount outside feasible bundle candidates')
            date = dates[index]
            next_date = dates[index + 1] if index + 1 < len(dates) else end + 1
            _, rival, alignment = scenario
            orders = dict(rival) if isinstance(rival, tuple) else {now: rival}
            for tick in range(date, next_date):
                a, b, inv = path.joint(inv, amount if tick == date else 0,
                                       max(0, orders.get(tick, 0)), alignment)
                own_cash += a
                rival_cash += b
                inv -= scheduler.absorption(item, tick, shops, config)
            plan = plan + ((date, amount),)
            if index + 1 == len(dates) and capacity_ok and not capacity_ok(plan):
                raise Infeasible('joint receipt/capacity schedule rejected by incumbent checker')
            return index + 1, remaining - amount, inv, own_cash, rival_cash, plan

        def evaluate(state, scenario):
            index, remaining, inv, own_cash, rival_cash, _ = state
            # Unsold stock has zero game-end reward. Before that, cash opportunity
            # cost uses the incumbent's exact declining-price liquidation value.
            carry = 0 if index == len(dates) and end == last else path.single(inv, remaining)[0]
            return own_cash + carry - rival_cash - baselines[scenario[0]][0]

        model = Model(candidates, transition, evaluate, state_key=lambda s: s,
                      scenario_key=lambda s: s, action_key=lambda a: a,
                      order=lambda state, q: q)
        result = search(model, [initial] * len(scenarios), scenarios,
                        min(quantity, max(minimum_now, dict(reference).get(now, 0))),
                        limits=Limits(seconds=seconds, max_transitions=max_transitions,
                                      max_depth=len(dates), candidate_limit=8),
                        warm_start=[dict(reference).get(t, 0) for t in dates],
                        cache=cache, ordering=ordering, iterative=iterative)
        plan = reference
        # Partial horizons do not justify changing the incumbent's complete plan.
        if result.completed_depth == len(dates) and min(result.values) > 0:
            plan = tuple(zip(dates, result.principal_variation))
        info = dict(incumbent_info)
        if plan != reference:
            scores = [path.score(plan, quantity, rival, alignment, end == last)
                      for _, rival, alignment in scenarios]
            original_baselines = [path.score(incoming_reference, quantity, rival, alignment, end == last)
                                  for _, rival, alignment in scenarios]
            info.update(plan=list(plan), scenarios={
                name: {'reference_relative_value': b[0], 'relative_value': score[0],
                       'own_receipts': score[1], 'rival_receipts': score[2], 'carry_units': score[3]}
                for (name, _, _), b, score in zip(scenarios, original_baselines, scores)},
                worst_relative_gain=min(score[0] - b[0] for b, score in zip(original_baselines, scores)))
        info.update(search=asdict(result), incumbent_plan=list(reference),
                    incremental_gain=min(result.values) if plan != reference else 0.0,
                    comparison='augments completed seller incumbent; strict all-scenario improvement',
                    budget_scope='kernel only; existing optimizer and receipt bookkeeping additional')
        return plan, info

    return optimize_lot
