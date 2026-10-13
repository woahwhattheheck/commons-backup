# SPDX-License-Identifier: Apache-2.0
"""Evaluator-only envelope; removed before the official interpreter receives it."""
import importlib.util
from pathlib import Path
import sys

_INSTANCE=None


def call(mode, obs, cfg):
    global _INSTANCE
    if _INSTANCE is None:
        here=Path(__file__).resolve().parent;sys.path.insert(0,str(here))
        spec=importlib.util.spec_from_file_location('t15_recourse_runtime',here/'runtime.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        _INSTANCE=module.Agent(mode)
    action=_INSTANCE.act(obs,cfg)
    stats=dict(_INSTANCE.counts,calls=_INSTANCE.calls)
    if _INSTANCE.transformer:stats.update(_INSTANCE.transformer.counts)
    meta={'counts':stats,'decision':_INSTANCE.last}
    if _INSTANCE.last.get('reason') in ('admitted','observed_branch'):
        meta['packet']=_INSTANCE.parent.last_packet
    return dict(action,__adaptive_evaluation__=meta)


def adaptive(obs,cfg):return call('adaptive',obs,cfg)
def fixed(obs,cfg):return call('fixed',obs,cfg)
def static(obs,cfg):return call('static',obs,cfg)
def baseline(obs,cfg):return call('baseline',obs,cfg)
