"""T04 service-only candidate: price a capped animal's CARE versus HARVEST.

The parent retains all capital, crop, movement, market and hiring decisions.
This is a research treatment, not a promoted TITAN policy.
"""
from copy import deepcopy
from oracle import Scenario, simulate_bundle


def make_policy(parent, engine, *, fork_parent, minimum_cash_gain=0.0):
    """Return an observation-only agent using the exact bundle cash oracle.

    fork_parent() must snapshot the parent after the current action and return
    an isolated callable. Speculative calls never advance the live parent.
    Forecast one intact-parent continuation, then preserve its worker/capital plan for each candidate while refreshing
    SELL quantities from that counterfactual's visible shed. Only one current CARE may become HARVEST. Unobserved
    rival flows/new shops/weeds are not supplied to the oracle.
    """
    def agent(observation, configuration=None):
        cfg = dict(configuration or {})
        tpd = max(1, int(cfg.get('turnsPerDay', 24)))
        episode = int(cfg.get('episodeSteps', 720))
        step = int(observation.get('step', 0))
        action = deepcopy(parent(deepcopy(observation)))
        # Leave the final day to the intact parent / separately owned T05 lane.
        if step // tpd >= (episode - 2) // tpd:
            return action
        farm = observation['farms'][observation['player']]
        positions = [farm['farmer'], *farm['hands']]
        units = [action.get('farmer', ['PASS']), *action.get('hands', [])]
        eligible = []
        for idx, unit in enumerate(units):
            if idx >= len(positions) or unit != ['CARE']:
                continue
            x, y = positions[idx]
            tile = farm['tiles'][y][x]
            if not isinstance(tile, dict) or 'animal' not in tile:
                continue
            spec = engine.ANIMALS[tile['animal']]
            if tile.get('yield_units', 0) >= spec['max_held'] and tile.get('fed_today'):
                eligible.append((idx, spec['interval']))
        if not eligible:
            return action
        end = min(episode - 2, (step // tpd + max(i for _, i in eligible) + 2) * tpd - 1)
        scenario = Scenario()
        forecast_parent = fork_parent()
        def continuation(obs):
            return deepcopy(action) if int(obs['step']) == step else forecast_parent(obs)
        control = simulate_bundle(engine, observation, cfg, continuation,
                                  end_step=end, scenario=scenario, record_actions=True)
        best, best_gain = action, float(minimum_cash_gain)
        for idx, _ in eligible:
            proposal = deepcopy(action)
            if idx == 0:
                proposal['farmer'] = ['HARVEST']
            else:
                proposal['hands'][idx-1] = ['HARVEST']
            sale_parent = fork_parent()
            def candidate_plan(obs):
                current = int(obs['step'])
                if current == step:
                    return deepcopy(proposal)
                # The parent clamps SALES to available stock. Freezing those
                # already-clamped quantities would price recovered output at
                # zero even when the intact controller would liquidate it.
                refreshed = sale_parent(obs)
                fixed = deepcopy(control['actions'][current])
                sales = iter(o for o in refreshed.get('market', []) if o and o[0] == 'SELL')
                orders = []
                for order in fixed.get('market', []):
                    if order and order[0] == 'SELL':
                        new = next(sales, None)
                        if new is not None: orders.append(new)
                    else:
                        orders.append(order)
                orders.extend(sales)
                fixed['market'] = orders[:int(cfg.get('maxMarketOrdersPerTurn', 10))]
                return fixed
            candidate = simulate_bundle(engine, observation, cfg, candidate_plan,
                                        end_step=end, scenario=scenario)
            gain = candidate['cash_gain'] - control['cash_gain']
            if gain > best_gain:
                best, best_gain = proposal, gain
        return best
    return agent
