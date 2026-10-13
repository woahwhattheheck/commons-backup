# SPDX-License-Identifier: Apache-2.0
"""Optional bounded whole-tail alternative to the original late scalar recheck.

Uses the existing RILL/T04 owned-state model with a copied Arlene producer, NOT
an additional simulator or a copy of the frozen SELL optimizer. The actual live
SELL actor runs exactly once after the route choice. No model is a forecast of
unknown rival trades, future shops, weeds, realized cash, or win probability.
"""
from __future__ import annotations
from copy import deepcopy
import math
from time import perf_counter

from late_milk import CHECKPOINT, MAIN, MILK_EXIT, LateMilkChoice


class ModelMilkChoice(LateMilkChoice):
    """At 577 compare the two existing complete tails; otherwise retain parent.

    ``evaluate(controller, observation, configuration)`` is the existing RILL
    replay consumer bound to T04, the official mechanics and one explicit
    scenario. It must execute independent controller copies; the live actor
    must not be used for speculation. Use ``wrap_model_sell`` for that binding.
    No pure-plan score is inferred from incomplete physical model execution.
    """
    def __init__(self,call,controller,evaluate,*,enabled=True):
        super().__init__(call,controller,enabled=enabled)
        if not callable(evaluate):
            raise TypeError('Supply the existing complete-tail model consumer')
        self.evaluate=evaluate
        self.last_model=None

    def reconsider(self,observation,configuration=None):
        cfg=configuration or {}
        step=observation.get('step')
        if step is None:
            step=int(observation['day'])*int(cfg.get('turnsPerDay',24))+int(observation['hour'])
        if type(step) is not int or step!=CHECKPOINT or self.attempted:
            return deepcopy(self.last_choice)
        self.attempted=True
        current=self.controller.cur
        report={'step':step,'before':current,'after':current,'changed':False,
                'reason':'disabled' if not self.enabled else 'incumbent',
                'objective':'modeled terminal own cash',
                'model':'existing Arlene-only RILL/T04; observed shops, no external flows',
                'cash':{},'model_wall_seconds':None,'model_decisions':0,
                'rival_cash':None,'calibrated':False}
        self.last_choice=report
        if not self.enabled:return deepcopy(report)
        if (int(cfg.get('turnsPerDay',24))!=24 or int(cfg.get('episodeSteps',720))!=720):
            report['reason']='other_configuration';return deepcopy(report)
        if current not in (MAIN,MILK_EXIT):
            report['reason']='other_route';return deepcopy(report)
        other=MILK_EXIT if current==MAIN else MAIN
        if other not in self.controller.R or not self.controller._switch_ok(other,step):
            report['reason']='program_prefix_differs';return deepcopy(report)
        started=perf_counter()
        def apply_model():
            model=self.evaluate(self.controller,observation,cfg)
            self.last_model=model
            report['model_decisions']=model.get('decisions_executed',0)
            if model.get('complete') is not True:
                report['reason']='model_incomplete';return
            cases=model['cases']
            if len(cases)!=2 or {c['offered_route'] for c in cases}!={MAIN,MILK_EXIT}:
                report['reason']='model_routes_differ';return
            if model.get('start_step')!=step or model.get('end_step')!=718:
                report['reason']='model_horizon_differs';return
            for case in cases:
                value=case.get('final_cash')
                if (case.get('status')!='complete' or type(value) not in (int,float)
                        or not math.isfinite(value)):
                    report['reason']='model_cash_unavailable';return
                report['cash'][case['offered_route']]=value
            report['modeled_advantage']=report['cash'][other]-report['cash'][current]
            if report['modeled_advantage']>0:
                self.controller.cur=other
                report.update(after=other,changed=True,reason='whole_tail_cash_choice')
        try:
            apply_model()
        except Exception:
            # Do not expose arbitrary dependency exception context in telemetry.
            report['reason']='model_unavailable'
        finally:
            report['model_wall_seconds']=perf_counter()-started
        return deepcopy(report)



def wrap_model_sell(actor,engine,simulate_bundle,scenario_factory,replay_routes,
                    limits_type,*,enabled=True,seconds=0.6):
    """Bind the SAME existing actor to the existing owned-state continuation model.

    The cooperative budget covers both 142-decision tails. One dependency call
    can overrun it; this is not a hard whole-agent deadline. T04's zero-external-
    flow scenario still executes currently visible buyers and own production.
    Arlene's dynamic future route decisions remain live inside each copy.
    """
    if not math.isfinite(seconds) or not 0<=seconds<=0.8:
        raise ValueError('Use a finite nonnegative modeling budget at most0.8s')
    def evaluate(controller,observation,configuration):
        return replay_routes(controller,[MAIN,MILK_EXIT],observation,configuration,
            engine,simulate_bundle,scenarios={'observed_shops_only':scenario_factory()},
            end_step=718,limits=limits_type(seconds=seconds,decisions=284))
    return ModelMilkChoice(actor.act,actor.controller,evaluate,enabled=enabled)
