# SPDX-License-Identifier: Apache-2.0
"""Research adapter: one existing canonical parent, then a bounded input trim."""
from pathlib import Path
import sys
import time
_here=Path(__file__).resolve().parent
_runtime=_here/'runtime'
if not (_runtime/'titan_runtime.py').is_file():
    _runtime=_here.parents[1]/'cloud-execution-lab'
sys.path.insert(0,str(_runtime))
from titan_runtime import TitanAgent, deadline
import scheduler
from input_budget import FinalInputBudget

class InputBudgetAgent:
    def __init__(self, parent=None, enabled=True):
        self.parent=parent if parent is not None else TitanAgent()
        self.enabled=enabled
        self.budget=FinalInputBudget(scheduler.m,scheduler.parent._noop,scheduler.post_units)
        self.diagnostics={}
    def act(self,obs,cfg=None):
        started=time.perf_counter()
        action=self.parent.act(obs,cfg)
        self.diagnostics={'changed':False}
        if not self.enabled or not self.parent.ready or self.parent.diagnostics.get('status')!='completed':return action
        if self.parent.features.consumer!='frozen' or self.parent.features.terminal_route:return action
        cfg=dict(cfg or {})
        observation=dict(obs)
        observation['step']=int(obs['step']) if obs.get('step') is not None else int(obs['day'])*int(cfg.get('turnsPerDay',24))+int(obs['hour'])
        if any(int(d[0])>observation['step'] for d in scheduler.parent.DECISIONS):return action
        remaining=self.parent.features.budget_seconds-self.parent.features.reserve_seconds-(time.perf_counter()-started)
        if remaining<=0:return action
        timer=deadline._DeadlineTimer(remaining)
        try:
            with timer:
                result=self.budget.transform(observation,cfg,action,self.parent.controller.R[self.parent.controller.cur])
            self.diagnostics={'changed':result!=action,'decision':self.budget.last.__dict__.copy()}
            return result
        except BaseException as exc:
            if exc is not timer.expired:raise
            self.diagnostics={'changed':False,'budget_expired':True}
            return action
    __call__=act

def make_agent(*,parent=None,enabled=True):return InputBudgetAgent(parent,enabled)

def _absolute_step(obs,cfg=None):
    if obs.get('step') is not None:
        return int(obs['step'])
    config=dict(cfg or {})
    return int(obs['day'])*int(config.get('turnsPerDay',24))+int(obs['hour'])

_policy=None
def agent(obs,cfg=None):
    global _policy
    if _policy is None or _absolute_step(obs,cfg)==0:_policy=make_agent()
    return _policy.act(obs,cfg)
