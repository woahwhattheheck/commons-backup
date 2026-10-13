# SPDX-License-Identifier: Apache-2.0
"""S05 shadow macro-prior wrapper. Returns canonical TITAN action unchanged."""
from __future__ import annotations
import copy, hashlib, json, os
from pathlib import Path
import main as _canonical
from s05_event_macros import DECISION_STEPS, build_library, execution_preserved, index_library, precondition, rank_prefix_beam, revalidate

_LIB=None; _IDX=None; _PENDING=[]; _LAST_STEP=None

def _ensure():
    global _LIB,_IDX
    if _LIB is None:
        root=Path(__file__).resolve().parent
        _LIB=build_library(root/'reference/next-panel/vendor/arlene.py'); _IDX=index_library(_LIB)

def _emit(payload):
    path=os.environ.get('S05_TRACE_PATH') or f'/tmp/s05-shadow-{os.getppid()}.jsonl'
    with open(path,'a',encoding='utf-8') as f:
        f.write(json.dumps(payload,sort_keys=True,separators=(',',':'))+'\n')

def agent(observation, configuration=None):
    global _PENDING,_LAST_STEP
    _ensure(); cfg=dict(configuration or {}); step=int(observation.get('step',0))
    if step==0 or (_LAST_STEP is not None and step<=_LAST_STEP): _PENDING=[]
    if _PENDING:
        for macro,info,prior in _PENDING:
            ok,detail=revalidate(macro,info,prior,observation,cfg)
            _emit({'kind':'revalidation','step':step,'macro':macro['id'],'family':macro['family'],'ok':bool(ok),'detail':detail})
        _PENDING=[]
    returned=_canonical.agent(observation,cfg)
    inst=getattr(_canonical,'_INSTANCE',None); ctl=getattr(inst,'controller',None)
    route=getattr(ctl,'cur',None)
    if ctl is not None and route in ctl.R:
        fired=[]
        for macro in _IDX.get((route,step),()):
            ok,info=precondition(macro,observation,cfg)
            if ok:
                preserved=execution_preserved(macro,returned)
                _emit({'kind':'candidate','step':step,'route':route,'macro':macro['id'],'family':macro['family'],'preserved':preserved,'info':info})
                if preserved:
                    fired.append((macro,info)); _emit({'kind':'fire','step':step,'route':route,'macro':macro['id'],'family':macro['family'],'info':info})
        _PENDING=[(m,i,copy.deepcopy(observation)) for m,i in fired if m['family']!='settlement']
        if step in DECISION_STEPS:
            report=rank_prefix_beam(ctl.R,route,step,observation,cfg,_IDX)
            _emit({'kind':'beam','step':step,**report})
    _emit({'kind':'action','step':step,'sha256':hashlib.sha256(json.dumps(returned,sort_keys=True,separators=(',',':')).encode()).hexdigest()}) if step in DECISION_STEPS else None
    _LAST_STEP=step
    return returned
