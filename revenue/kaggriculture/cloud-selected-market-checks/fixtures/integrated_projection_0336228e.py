# SPDX-License-Identifier: Apache-2.0
# Exact pre-reuse IntegratedSelectedAgent._projection, Git blob0336228e.
def _projection(self, obs, cfg, selected, farm, private, plans):
    """Continue ATLAS primitives from the already executed current unit stage.

    Seed reduction occurs between units and market. Reusing a projection made
    with the old seed purchases would give future PLANT the wrong stock.
    """
    now = absolute_step(obs, cfg)
    tpd = int(cfg.get('turnsPerDay', 24)); board = int(cfg.get('boardSize', 10))
    cap = int(cfg.get('shedCapacity', 100)); maximum = int(cfg.get('maxMarketOrdersPerTurn', 10))
    last = int(cfg.get('episodeSteps', 720))-2
    end = min(now+self.execution.seller.horizon, last, (now//tpd+1)*tpd-1)
    route = self.controller.R[self.controller.cur]
    switches = {int(row[0]) for row in getattr(self.production.A, 'DECISIONS', ())}
    events, future, omissions = [], {}, []
    reached, reason = now, 'horizon'
    for step in range(now, end+1):
        if step == now:
            action = selected
        else:
            if step in switches or step >= len(route):
                reason = 'route_boundary'; break
            action = deepcopy(route[step])
            if any(o and o[0] == 'BUY_PRODUCT' for o in action.get('market', [])):
                reason = 'future_product_purchase_needs_cash_bound'; break
            units = [action.get('farmer', ['PASS']), *action.get('hands', [])]
            excluded = set()
            stop = False
            for worker, plan in list(plans.items()):
                pos = m._farmer_position(farm, worker)
                if pos is None or worker >= len(units) or units[worker] != ['PASS']:
                    stop = True; break
                if plan['steps'] >= self.production.max_steps:
                    stop = True; break
                op = self.production._next_op(plan, pos, m._farmer_inventory(private, worker), board)
                if op is None:
                    stop = True; break
                units[worker] = op
                plan['steps'] += 1
                if op[0] == 'HARVEST':
                    excluded.add((step, worker))
                    del plans[worker]
            if stop:
                reason = 'committed_continuation_boundary'; break
            action['farmer'], action['hands'] = units[0], units[1:]
            trial_farm, trial_private = deepcopy(farm), deepcopy(private)
            trial_events, trial_omissions = [], []
            try:
                atlas._units(m, trial_farm, trial_private, action, step, board, tpd, cap,
                             lossless=True, events=trial_events, excluded=excluded,
                             omissions=trial_omissions)
            except atlas.ProjectionError:
                reason = 'stock_dependent_pickup'; break
            farm, private = trial_farm, trial_private
            events.extend(trial_events); omissions.extend(trial_omissions)
            future[step] = atlas._market(action, maximum)
        reached = step
        atlas._full_market(m, farm, private, atlas._market(action, maximum), board,
                           int(cfg.get('farmHandCostMult', 1)))
        m._decay_plants(farm, step)
        if (step+1) % tpd == 0:
            # Refresh changes tiles, not the carried goods deposited here.
            for worker, inv in enumerate(private['inventories']):
                for item, q in inv.items():
                    atlas._record(events, step, 'after_market', worker, 'EOD', item, q)
    return {'observed_step':now, 'end_step':reached, 'stock_events':events,
            'future_market':future}, {'end_reason':reason, 'excluded_harvests':omissions}
