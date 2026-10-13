# SPDX-License-Identifier: Apache-2.0
"""Factories for coherent frozen controls. Each actor constructs only its arm."""
import copy
from pathlib import Path
import sys
from runtime import HERE, load, make_agent


def engine():
    evaluator = load(HERE / 'vendor/cloud-eval/evaluate.py', 't14_eval_loader')
    return evaluator.get_engine(HERE / 'vendor/engine')[0]


def factory(name, cfg):
    base_path = HERE / 'vendor/t08/vendor/base/arlene.py'
    if name in ('sell', 'carrot_sell'):
        return make_agent({'policy': name}, checkpoint=0, fixed=name)
    if name == 'router':
        return make_agent()
    if name == 'apex':
        return load(HERE / 'vendor/apex/main.py', 't14_apex').agent
    base = load(base_path, 't14_control_arlene')
    if name == 'arlene':
        return base.agent
    if name == 'service':
        sys.path.insert(0, str(HERE / 'vendor/service'))
        service = load(HERE / 'vendor/service/policy.py', 't14_service')
        return service.make_policy(base.agent, engine(), fork_parent=lambda: copy.copy(base._A).act)
    if name == 'labor':
        labor = load(HERE / 'vendor/labor/labor_capital.py', 't14_labor')
        agent = labor.HiringAgent(base.Agent(), engine(), mode='reserve', configuration=cfg)
        return lambda obs, cfg=None: agent.act(obs)
    if name == 'terminal':
        planner = load(HERE / 'vendor/terminal/terminal.py', 't14_terminal').Planner()
        parent = base.Agent()
        def terminal(obs, cfg=None):
            action = parent.act(obs)
            return planner.act(obs, action, cfg, own_future_actions=parent.R[parent.cur][int(obs['step']):int((cfg or {}).get('episodeSteps', 720))-1])
        return terminal
    if name == 'recovery_sell':
        scheduler_dir = HERE / 'vendor/t08/vendor/sell'
        sys.path.insert(0, str(scheduler_dir))
        scheduler = load(scheduler_dir / 'scheduler.py', 't14_recovery_scheduler')
        recovery = load(HERE / 'vendor/recovery/recovery.py', 't14_recovery')
        policy = scheduler.SellScheduler()
        policy.controller = recovery.RecoveryController(policy.controller, scheduler.parent, scheduler.m, True)
        policy.controller.configuration = dict(cfg or {})
        return policy.act
    if name in ('sale_cadence', 'crop_demand', 'labor_cadence'):
        variants = load(HERE / 'vendor/league/variants.py', 't14_variants')
        shops = engine().SHOPS
        return lambda obs, cfg=None: variants.transform(base.agent(obs), obs, name, shops, cfg)
    raise ValueError('Unknown policy: ' + name)


def entry(name):
    policy = None
    def agent(obs, cfg=None):
        nonlocal policy
        if policy is None or int(obs['step']) == 0:
            policy = factory(name, cfg)
        return policy(obs, cfg) if name != 'arlene' else policy(obs)
    return agent


sell = entry('sell')
carrot_sell = entry('carrot_sell')
arlene = entry('arlene')
apex = entry('apex')
service = entry('service')
labor = entry('labor')
terminal = entry('terminal')
recovery_sell = entry('recovery_sell')
sale_cadence = entry('sale_cadence')
crop_demand = entry('crop_demand')
labor_cadence = entry('labor_cadence')
router = entry('router')
