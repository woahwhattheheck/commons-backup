# SPDX-License-Identifier: Apache-2.0
"""Evaluator-only diagnostics envelope, removed before official game execution.

Production main.py/pure.py never import this file. The parent evaluator strips
the envelope before the action reaches the engine. It never sends future or
rival-private data into the policy.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from dependencies import HERE, load

_modules={}
_counts={}


def evaluated(name,obs,cfg):
    if name not in _modules:
        _modules[name]=load(HERE/name,'t15_measured_'+name[:-3])
    module=_modules[name]
    action=module.agent(obs,cfg)
    instance=module._INSTANCE
    metadata={'counts':dict(instance.counts),'decision':instance.selector.last_decision}
    count=instance.counts['activations']
    if count!=_counts.get(name,0):
        metadata['activation']=instance.last
    _counts[name]=count
    return dict(action,__t15_evaluation__=metadata)


def mixed(obs,cfg):return evaluated('main.py',obs,cfg)
def pure(obs,cfg):return evaluated('pure.py',obs,cfg)
