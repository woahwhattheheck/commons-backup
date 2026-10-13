# SPDX-License-Identifier: Apache-2.0
"""S05 executable event-macro prior with one-action revalidation.

A source-compatible alternate route may be selected only for a strict exact
macro-prior improvement.  The existing controller and all downstream canonical
transforms still produce the action.  Before the next action the macro is
revalidated against the new observation; a failed or transformed-away event
rolls back to the baseline route before any further action is emitted.
"""
from __future__ import annotations
import copy, json, os
from pathlib import Path
import main as _canonical
from s05_event_macros import WEIGHTS, build_library, execution_preserved, index_library, precondition, rank_prefix_beam, revalidate

_LIB=None;_IDX=None;_LAST_CFG={};_PENDING=None

def _ensure():
 global _LIB,_IDX
 if _LIB is None:
  root=Path(__file__).resolve().parent;_LIB=build_library(root/'reference/next-panel/vendor/arlene.py');_IDX=index_library(_LIB)

def _emit(x):
 p=f'/tmp/s05-prior-{os.getppid()}.jsonl'
 with open(p,'a',encoding='utf-8') as f:f.write(json.dumps(x,sort_keys=True,separators=(',',':'))+'\n')

def _restore_baseline(pending,reason,detail=None):
 inst=getattr(_canonical,'_INSTANCE',None);ctl=getattr(inst,'controller',None)
 if ctl is not None:
  ctl.cur=pending['baseline']
  if hasattr(inst,'_completed_route'): inst._completed_route=pending['baseline']
 _emit({'kind':'rollback','step':pending['step']+1,'baseline':pending['baseline'],'winner':pending['winner'],'reason':reason,'detail':detail or {}})

def _consume_pending(observation,cfg):
 global _PENDING
 if _PENDING is None:return
 p=_PENDING;_PENDING=None
 ok,detail=revalidate(p['macro'],p['info'],p['prior_obs'],observation,cfg)
 ok=bool(ok and p.get('preserved',False))
 _emit({'kind':'prior_revalidation','step':int(observation.get('step',p['step']+1)),'macro':p['macro']['id'],'family':p['macro']['family'],'ok':ok,'preserved':bool(p.get('preserved')),'detail':detail})
 if not ok:_restore_baseline(p,'postcondition_failed_or_transformed',detail)

def _install():
 _ensure();inst=getattr(_canonical,'_INSTANCE',None);ctl=getattr(inst,'controller',None)
 if ctl is None or getattr(ctl,'_s05_prior_installed',False):return
 original=ctl.act;globs=type(ctl).act.__globals__;decisions=tuple(globs.get('DECISIONS',()))
 def prior_act(obs):
  global _PENDING
  step=int(obs.get('step',0));before=ctl.cur;baseline=before;feature=globs.get('_feature')
  for turn,feat,thr,target in decisions:
   if turn!=step or target==baseline:continue
   a,b=ctl.R[baseline],ctl.R[target]
   if all(a[t]==b[t] for t in range(turn)) and feature(obs,feat)>=thr:baseline=target
  report=rank_prefix_beam(ctl.R,baseline,step,obs,_LAST_CFG,_IDX)
  if report['changed_recommendation']:
   winner=report['winner'];a,b=ctl.R[before],ctl.R[winner]
   if all(a[t]==b[t] for t in range(step)):
    fired=[]
    for macro in _IDX.get((winner,step),()):
     ok,info=precondition(macro,obs,_LAST_CFG)
     if ok:fired.append((WEIGHTS[macro['family']],macro,info))
    if fired:
     _,macro,info=max(fired,key=lambda x:(x[0],x[1]['id']))
     old=globs['DECISIONS'];ctl.cur=winner;globs['DECISIONS']=tuple(d for d in old if int(d[0])!=step)
     try:out=original(obs)
     finally:globs['DECISIONS']=old
     preserved=execution_preserved(macro,out)
     _PENDING={'step':step,'baseline':baseline,'winner':winner,'macro':macro,'info':info,'prior_obs':copy.deepcopy(obs),'preserved':preserved}
     _emit({'kind':'prior_switch','step':step,'before':before,'baseline':baseline,'winner':winner,'macro':macro['id'],'family':macro['family'],'preserved_after_controller':preserved,'beam':report})
     return out
  return original(obs)
 ctl.act=prior_act;ctl._s05_prior_installed=True

def agent(observation,configuration=None):
 global _LAST_CFG,_PENDING
 _LAST_CFG=dict(configuration or {});step=int(observation.get('step',0))
 if step==0:_PENDING=None
 _install();_consume_pending(observation,_LAST_CFG)
 out=_canonical.agent(observation,_LAST_CFG)
 _install()
 if _PENDING is not None and _PENDING['step']==step:
  _PENDING['preserved']=bool(_PENDING['preserved'] and execution_preserved(_PENDING['macro'],out))
 return out
