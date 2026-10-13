# SPDX-License-Identifier: Apache-2.0
"""One live frozen SELL controller, with a prefix-compatible routing decision."""
import importlib.util
import json
from pathlib import Path
import sys
from features import extract, predict

HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Portfolio:
    """Select SELL or carrot-SELL at 360 without replacing controller state.

    The frozen carrot patch changes only _feature('px_CARROT'). The exact
    Arlene source reads that feature only at its step-360 compatible-tail
    decision. Before 360, both complete policies therefore execute one common
    SELL prefix. The original _switch_ok remains authoritative for route
    compatibility. All scheduler pending/planned/history state survives.
    """
    def __init__(self, tree, *, checkpoint=360, fixed=None):
        if checkpoint not in (0, 360):
            raise ValueError('Only source-proven checkpoints 0 and 360 are implemented')
        self.tree, self.checkpoint, self.fixed = tree, checkpoint, fixed
        vendor = HERE / 'vendor/t08/vendor/sell'
        sys.path.insert(0, str(vendor))
        self.scheduler_module = load(vendor / 'scheduler.py', 't14_frozen_scheduler')
        self.policy = self.scheduler_module.SellScheduler()
        self.selected = None
        self.selection = None
        self.last_step = -1

    def _select(self, obs):
        features = extract(obs)
        choice = self.fixed or predict(self.tree, features)
        if choice not in ('sell', 'carrot_sell'):
            raise ValueError('This prefix supports SELL and carrot-SELL only')
        if choice == 'carrot_sell':
            patch = HERE / 'vendor/t08/vendor/carrot/carrot_demand.py'
            # The same module owns the live Agent. No new parent, warm-up replay,
            # counterfactual action call, scheduler reset or state transplant.
            namespace = self.scheduler_module.parent.__dict__
            exec(compile(patch.read_bytes(), str(patch), 'exec'), namespace)
        self.selected = choice
        self.selection = {'step': int(obs['step']), 'policy': choice, 'features': features}

    def act(self, observation, configuration=None):
        step = int(observation['step'])
        if step != self.last_step + 1:
            raise ValueError('Portfolio requires one sequential observation per decision')
        if step == self.checkpoint:
            self._select(observation)
        self.last_step = step
        return self.policy.act(observation, configuration)


def make_agent(tree=None, *, checkpoint=360, fixed=None):
    state = None
    def agent(obs, cfg=None):
        nonlocal state
        if state is None or int(obs['step']) == 0:
            config = tree
            if config is None:
                config = json.loads((HERE / 'model.json').read_text())['tree']
            state = Portfolio(config, checkpoint=checkpoint, fixed=fixed)
            agent.portfolio = state
        return state.act(obs, cfg)
    return agent


agent = make_agent()
