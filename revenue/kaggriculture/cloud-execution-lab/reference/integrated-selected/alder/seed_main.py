# SPDX-License-Identifier: Apache-2.0
"""T13 unused-seed repair over an unchanged frozen SELL or Arlene policy."""
_policy = None


def make_agent(root, sell=True, enabled=True):
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
    policy = scheduler.SellScheduler() if sell else scheduler.parent.Agent()
    controller = policy.controller if sell else policy
    budget = budget_module.SeedBudget(controller.R)
    def run(observation, configuration=None):
        config = dict(configuration or {})
        # One call only; projection below is deterministic owned unit mechanics.
        action = policy.act(observation, config) if sell else policy.act(observation)
        if not enabled or not any(o and o[0] == 'BUY_SEED' for o in action.get('market', [])):
            return action
        _, private = scheduler.post_units(observation, action, config)
        return budget.apply(action, private['seeds'], int(observation['step']), controller.cur,
                            int(config.get('maxMarketOrdersPerTurn', 10)))
    run.policy = policy
    run.controller = controller
    run.budget = budget
    return run


def agent(observation, configuration=None):
    global _policy
    if _policy is None or int(observation.get('step', 0)) == 0:
        from pathlib import Path
        path = globals().get('__file__') or (configuration or {}).get('__raw_path__')
        if not path:
            raise ValueError('Supply a module path or configuration.__raw_path__')
        _policy = make_agent(Path(path).resolve().parent)
    return _policy(observation, configuration)
