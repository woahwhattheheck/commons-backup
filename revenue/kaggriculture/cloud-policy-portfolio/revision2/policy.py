# SPDX-License-Identifier: Apache-2.0
"""One SELL controller with an observation-based economic choice at step360."""
from copy import deepcopy
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime import Portfolio, load
from continuation import compatible, evaluate_continuations, market_kernel, scenario_windows

flow = load(Path(__file__).resolve().parent/'vendor/t12/flow.py', 't14_r2_flow')


class EconomicPolicy:
    def __init__(self, fixed=None):
        self.base = Portfolio({}, checkpoint=360, fixed='sell')
        self.scheduler = self.base.policy
        self.source = self.base.scheduler_module
        self.parent = self.source.parent
        self.controller = self.scheduler.controller
        self.history = flow.FlowHistory()
        self.kernel = market_kernel(self.source.m)
        self.previous = self.previous_sales = None
        self.last_step = -1
        self.fixed = fixed
        self.decision = None
        # The full staged route is fixed before the first game action. At the
        # day boundary the source engine resets workers; physical stock persists.
        self.staged = 't14_r2_staged_day16'
        self.controller.R[self.staged] = (self.controller.R[self.parent.YARN][:384]
                                         + self.controller.R[self.parent.YARN_CARROT][384:])
        self.parent.DECISIONS = tuple(d for d in self.parent.DECISIONS if d[0] != 360)

    def observe(self, obs, cfg):
        if self.previous is not None:
            for p in self.source.PRODUCTS:
                self.history.add(flow.infer_flow(self.previous, obs, self.previous_sales, p, cfg,
                                                 self.source.m, self.source.absorption))

    def select(self, obs, cfg):
        current = self.controller.cur
        baseline = current
        carrot = self.parent.YARN_CARROT
        if self.controller._switch_ok(carrot, 360) and self.parent._feature(obs, 'px_CARROT') >= 42:
            baseline = carrot
        options = {'retain': current, 'replace': carrot, 'staged': self.staged}
        options = {n: target for n, target in options.items()
                   if compatible(self.controller.R, current, target, 360)}
        baseline_name = next(n for n, target in options.items() if target == baseline)
        if len(options) == 1:
            self.decision = {'selected': baseline_name, 'reason': 'no_compatible_alternative'}
        elif self.fixed:
            self.decision = {'selected': self.fixed if self.fixed in options else baseline_name, 'reason': 'fixed_control'}
        else:
            scenarios = scenario_windows(self.history, 360, 718, self.source.PRODUCTS)
            if all(s['training_start'] is None for s in scenarios):
                self.decision = {'selected': baseline_name, 'reason': 'no_identified_joint_history'}
            else:
                self.decision = evaluate_continuations(obs, cfg,
                    {name: self.controller.R[target] for name, target in options.items()}, scenarios,
                    baseline=baseline_name, mechanics=self.source.m, kernel=self.kernel, repair=self.parent._noop)
        chosen = options[self.decision['selected']]
        if not compatible(self.controller.R, current, chosen, 360):
            raise ValueError('Chosen continuation lacks the complete played prefix')
        # This is the same authoritative cur transition used by the source Agent.
        # All pending/planned sales, caches and prior observations remain owned by it.
        self.controller.cur = chosen

    def act(self, obs, configuration=None):
        cfg = dict(configuration or {})
        step = int(obs['step'])
        if step != self.last_step+1:
            raise ValueError('Sequential observations are required')
        self.observe(obs, cfg)
        if step == 360:
            self.select(obs, cfg)
        action = self.scheduler.act(obs, cfg)
        _, private = self.source.post_units(obs, action, cfg)
        available = dict(private['shed']); sales = {}
        for order in action.get('market', [])[:cfg.get('maxMarketOrdersPerTurn', 10)]:
            if len(order) > 2 and order[0] == 'SELL' and order[1] in self.source.PRODUCTS:
                p = order[1]; q = min(max(0, int(order[2])), max(0, available.get(p, 0)))
                sales[p] = sales.get(p, 0)+q; available[p] = available.get(p, 0)-q
        self.previous = deepcopy({k: obs[k] for k in ('step', 'market', 'town')})
        self.previous_sales = sales
        self.last_step = step
        return action


def make_agent(fixed=None):
    state = None
    def agent(obs, cfg=None):
        nonlocal state
        if state is None or int(obs['step']) == 0:
            state = EconomicPolicy(fixed)
            agent.policy = state
        return state.act(obs, cfg)
    return agent
