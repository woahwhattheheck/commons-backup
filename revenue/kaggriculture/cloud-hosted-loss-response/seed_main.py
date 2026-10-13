# SPDX-License-Identifier: Apache-2.0
"""T13 unused-seed repair over an unchanged frozen SELL or Arlene policy."""
_policy = None


def _absolute_step(observation, configuration):
    """Resolve the same public clock before actor dispatch or reset decisions."""
    step = observation.get('step')
    if step is not None:
        return int(step)
    return int(observation['day']) * int((configuration or {}).get('turnsPerDay', 24)) + int(observation['hour'])


def make_agent(root, sell=True, enabled=True, *, seed_queue_selector=None,
               policy=None, controller=None):
    """Keep one existing policy; optionally select cash-coupled seed proposals.

    The selector has the same post-unit callback contract as the integrated
    agent. None retains this module's original, demand-only seed behavior.
    A supplied policy/controller pair reuses that actor and its live route; the
    caller must keep its worker actions prefix-compatible with controller.R.
    """
    if (policy is None) != (controller is None):
        raise ValueError('Supply policy and its controller together')
    from copy import deepcopy
    import importlib.util
    from pathlib import Path
    import sys
    root = Path(root).resolve()
    vendor = root / 'vendor/sell'
    if not vendor.is_dir():
        vendor = root.parent / 'cloud-titan-composition/vendor/sell'
    sys.path.insert(0, str(vendor))
    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    scheduler = load('alder_seed_scheduler', vendor / 'scheduler.py')
    budget_module = load('alder_seed_budget', root / 'seed_budget.py')
    if policy is None:
        policy = scheduler.SellScheduler() if sell else scheduler.parent.Agent()
        controller = policy.controller if sell else policy
    budget = budget_module.SeedBudget(controller.R)
    def run(observation, configuration=None):
        config = dict(configuration or {})
        observation = dict(observation)
        observation['step'] = _absolute_step(observation, config)
        run.seed_funding = None
        # One call only; projection below is deterministic owned unit mechanics.
        action = policy.act(observation, config) if sell else policy.act(observation)
        if not enabled or not any(o and o[0] == 'BUY_SEED' for o in action.get('market', [])):
            return action
        farm, private = scheduler.post_units(observation, action, config)
        proposed = budget.apply(action, private['seeds'], int(observation['step']), controller.cur,
                                int(config.get('maxMarketOrdersPerTurn', 10)))
        if seed_queue_selector is None:
            return proposed
        edits = [i for i, (a, b) in enumerate(zip(action.get('market', []),
                                                 proposed.get('market', []))) if a != b]
        dependent = any(o and o[0] in ('HIRE', 'BUY_LAND', 'BUY_PRODUCT', 'BUY_ANIMAL')
                        for i in edits for o in action['market'][i + 1:])
        if not dependent:
            return proposed
        post = deepcopy(observation)
        post['farms'][int(observation['player'])] = farm
        post['private'] = private
        chosen, report = seed_queue_selector(
            scheduler.m, post, deepcopy(action), deepcopy(proposed), deepcopy(config))
        if not isinstance(chosen, dict) or not isinstance(report, dict):
            raise TypeError('seed_queue_selector must return (action dict, report dict)')
        run.seed_funding = deepcopy(report)
        return deepcopy(chosen)
    run.policy = policy
    run.controller = controller
    run.budget = budget
    run.seed_funding = None
    return run


def agent(observation, configuration=None):
    global _policy
    if _policy is None or _absolute_step(observation, configuration) == 0:
        from pathlib import Path
        path = (globals().get('__file__') or (configuration or {}).get('__raw_path__')
                or agent.__code__.co_filename)
        _policy = make_agent(Path(path).resolve().parent)
    return _policy(observation, configuration)
