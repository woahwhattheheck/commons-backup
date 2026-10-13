# SPDX-License-Identifier: Apache-2.0
"""S03 one-action UCT proposer through the existing canonical transform chain."""
from __future__ import annotations
import hashlib, json, os
import main as _canonical
import mechanics as _mechanics
from s03_uct import DECISION_STEPS, run_uct

SIMULATIONS=int(os.environ.get('S03_SIMS','64'))
BUDGET_MS=float(os.environ.get('S03_BUDGET_MS','40'))
_LAST_CFG={};_SWITCH=None

def _emit(row):
 path=os.environ.get('S03_TRACE_PATH') or f'/tmp/s03-prior-{os.getpid()}.jsonl'
 with open(path,'a',encoding='utf-8') as f:f.write(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n')

def _install():
 inst=getattr(_canonical,'_INSTANCE',None);ctl=getattr(inst,'controller',None)
 if ctl is None or getattr(ctl,'_s03_uct_installed',False):return
 original=ctl.act;globs=type(ctl).act.__globals__;decisions=tuple(globs.get('DECISIONS',()))
 def uct_act(obs):
  global _SWITCH
  step=int(obs.get('step',0));before=ctl.cur
  if step not in DECISION_STEPS:return original(obs)
  baseline=before;feature=globs.get('_feature')
  if feature is not None:
   for turn,feat,thr,target in decisions:
    if turn==step and target!=baseline:
     a,b=ctl.R[baseline],ctl.R[target]
     if all(a[t]==b[t] for t in range(turn)) and feature(obs,feat)>=thr:baseline=target
  report=run_uct(ctl.R,baseline,step,obs,_LAST_CFG,_mechanics,SIMULATIONS,BUDGET_MS)
  winner=report.get('winner',baseline)
  if report.get('changed_recommendation') and winner!=baseline:
   a,b=ctl.R[baseline],ctl.R[winner]
   if all(a[t]==b[t] for t in range(step)):
    old=globs.get('DECISIONS',());ctl.cur=winner;globs['DECISIONS']=tuple(d for d in old if int(d[0])!=step)
    try:out=original(obs)
    finally:globs['DECISIONS']=old
    _SWITCH={'step':step,'before':before,'baseline':baseline,'winner':winner,'report':report,'completed_route_before':getattr(inst,'_completed_route',None)}
    _emit({'kind':'uct','mode':'prior','step':step,'simulations':SIMULATIONS,**report})
    return out
  _emit({'kind':'uct','mode':'prior','step':step,'simulations':SIMULATIONS,**report}) if step in DECISION_STEPS else None
  return original(obs)
 ctl.act=uct_act;ctl._s03_uct_installed=True

def agent(observation,configuration=None):
 global _LAST_CFG,_SWITCH
 _LAST_CFG=dict(configuration or {});_install();out=_canonical.agent(observation,_LAST_CFG);_install()
 if _SWITCH is not None and _SWITCH['step']==int(observation.get('step',0)):
  p=_SWITCH;_SWITCH=None;inst=getattr(_canonical,'_INSTANCE',None);ctl=getattr(inst,'controller',None)
  if ctl is not None:ctl.cur=p['baseline']
  if inst is not None and hasattr(inst,'_completed_route'):inst._completed_route=p['completed_route_before']
  _emit({'kind':'one_action_restore','step':p['step'],'baseline':p['baseline'],'winner':p['winner'],'action_sha256':hashlib.sha256(json.dumps(out,sort_keys=True,separators=(',',':')).encode()).hexdigest()})
 return out
