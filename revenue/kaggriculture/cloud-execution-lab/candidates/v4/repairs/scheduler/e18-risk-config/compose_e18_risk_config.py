# SPDX-License-Identifier: Apache-2.0
"""Fail-closed scratch composer for the E18 finite risk-config repair."""
from pathlib import Path
import argparse

OLD_WEIGHTS="""def _scenario_weights(names, config):
    raw=(config or {}).get('sellScenarioWeights',{})
    weights=[]
    if isinstance(raw,dict):
        for name in names:
            try:weights.append(max(0.0,float(raw.get(name,0.0))))
            except (TypeError,ValueError):weights.append(0.0)
    if len(weights)!=len(names) or sum(weights)<=0:
        weights=[1.0 for _ in names]
    total=sum(weights)
    return {name:weight/total for name,weight in zip(names,weights)}"""
NEW_WEIGHTS="""def _e18_nonnegative_finite(value):
    \"\"\"Use the existing zero fallback for invalid or non-finite risk inputs.\"\"\"
    from math import isfinite
    try:
        number=float(value)
    except (TypeError,ValueError,OverflowError):
        return 0.0
    return max(0.0,number) if isfinite(number) else 0.0


def _scenario_weights(names, config):
    from math import isfinite
    raw=(config or {}).get('sellScenarioWeights',{})
    weights=[]
    if isinstance(raw,dict):
        for name in names:
            weights.append(_e18_nonnegative_finite(raw.get(name,0.0)))
    total=sum(weights)
    if len(weights)!=len(names) or total<=0:
        weights=[1.0 for _ in names]
        total=sum(weights)
    elif not isfinite(total):
        scale=max(weights)
        weights=[weight/scale for weight in weights]
        total=sum(weights)
    return {name:weight/total for name,weight in zip(names,weights)}"""
OLD_BOUND="""    try:downside_bound=max(0.0,float((config or {}).get('sellDownsideBound',0.0)))
    except (TypeError,ValueError):downside_bound=0.0"""
NEW_BOUND="""    downside_bound=_e18_nonnegative_finite((config or {}).get('sellDownsideBound',0.0))"""

def compose(text):
    if text.count(OLD_WEIGHTS)!=1 or text.count(OLD_BOUND)!=1:
        raise SystemExit('source pin mismatch: expected untouched predecessor blocks exactly once')
    if '_e18_nonnegative_finite' in text:
        raise SystemExit('mixed/already-repaired source refused')
    return text.replace(OLD_WEIGHTS,NEW_WEIGHTS).replace(OLD_BOUND,NEW_BOUND)

def main():
    p=argparse.ArgumentParser(); p.add_argument('source'); p.add_argument('output'); a=p.parse_args()
    src,out=Path(a.source),Path(a.output)
    if out.exists(): raise SystemExit('refusing to overwrite output')
    out.write_text(compose(src.read_text()),encoding='utf-8')

if __name__=='__main__': main()
