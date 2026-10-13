# SPDX-License-Identifier: Apache-2.0
"""S03 shadow UCT wrapper. Returns canonical action unchanged."""
from __future__ import annotations
import hashlib, json, os
import main as _canonical
import mechanics as _mechanics
from s03_uct import DECISION_STEPS, run_uct

SIMULATIONS=int(os.environ.get('S03_SIMS','64'))
BUDGET_MS=float(os.environ.get('S03_BUDGET_MS','40'))

def _emit(row):
 path=os.environ.get('S03_TRACE_PATH') or f'/tmp/s03-shadow-{os.getpid()}.jsonl'
 with open(path,'a',encoding='utf-8') as f:f.write(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n')

def agent(observation,configuration=None):
 cfg=dict(configuration or {});out=_canonical.agent(observation,cfg);step=int(observation.get('step',0))
 inst=getattr(_canonical,'_INSTANCE',None);ctl=getattr(inst,'controller',None)
 if step in DECISION_STEPS and ctl is not None and getattr(ctl,'cur',None) in getattr(ctl,'R',{}):
  report=run_uct(ctl.R,ctl.cur,step,observation,cfg,_mechanics,SIMULATIONS,BUDGET_MS)
  _emit({'kind':'uct','mode':'shadow','step':step,'simulations':SIMULATIONS,**report})
  _emit({'kind':'action','step':step,'sha256':hashlib.sha256(json.dumps(out,sort_keys=True,separators=(',',':')).encode()).hexdigest()})
 return out
