# SPDX-License-Identifier: Apache-2.0
"""Receipt tables and bounded pair selection; no history estimation."""
from fractions import Fraction
from itertools import combinations
from solver import solve_table


def receipt_table(model, plans, quantity, streams):
    """Same complete rival stream, own slot and total lot across each row.

    MarketPath alignment encodes a rival slot relative to a FIXED own slot.
    The caller must omit 'before' when its own slot is zero.
    """
    receipts=[[model.score(tuple(map(tuple,p['sales'])),quantity,r,a,True)
               for _,r,a in streams] for p in plans]
    reference=receipts[0]
    deltas=[[int(x[0]-b[0]) for x,b in zip(row,reference)] for row in receipts]
    return deltas,receipts


def best_pair(plans,deltas,*,mode='mixed',learned_start=0):
    """Best exact two-alternative table within at most nine supplied plans.

    This is a restricted support search, not an unrestricted many-plan LP.
    Return the original row indices so no feasibility or provenance is lost.
    """
    if len(plans)>9:raise ValueError('At most nine complete plans per decision')
    best=None;value=Fraction(0)
    for i,j in combinations(range(1,len(plans)),2):
        rows=[deltas[0],deltas[i],deltas[j]]
        if mode=='pure':
            eligible=[r for r in (1,2) if rows[r][learned_start:] and min(rows[r])>=0 and min(rows[r][learned_start:])>0]
            score=max((Fraction(min(rows[r][learned_start:])) for r in eligible),default=Fraction(0))
        else:
            if any(max(a,b)<=0 for a,b in zip(rows[1],rows[2])):
                continue
            score=Fraction(solve_table(rows)['value'])
        if score>value:
            value=score;best=([plans[0],plans[i],plans[j]],rows,[0,i,j])
    return best
