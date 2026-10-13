# SPDX-License-Identifier: Apache-2.0
"""Final-day fertilizer purchase trimming using a supplied intact worker route.

Own-state physical projection only; this is not a market-return forecast. The
existing parent is called by the caller, never here. Trade order positions and
all authored worker actions are preserved. No engine seed or rival state is read.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json

@dataclass(frozen=True)
class BudgetDecision:
    reason: str
    slot: int = -1
    requested: int = 0
    retained: int = 0
    projections: int = 0

class FinalInputBudget:
    def __init__(self, mechanics, noop, post_units):
        self.m = mechanics
        self.noop = noop
        self.post_units = post_units
        self.last = BudgetDecision('not_applicable')

    def _units(self, row, farm, private, board):
        acts = deepcopy([row.get('farmer', ['PASS']), *row.get('hands', [])])
        positions = [farm['farmer'], *farm['hands']]
        for i, (x, y) in enumerate(positions[:len(acts)]):
            tile = farm['tiles'][y][x]
            if isinstance(tile,dict) and tile.get('kind')=='WEED' and self.noop(
                    acts[i], tile, private['inventories'][i], private['seeds'], x, y, board):
                acts[i]=['DIG']
        return acts

    def _project(self, farm, private, route, now, end, cfg, extra):
        farm,private=deepcopy(farm),deepcopy(private)
        private['shed']['FERTILIZER']=private['shed'].get('FERTILIZER',0)+extra
        board=len(farm['tiles']);day=now//int(cfg.get('turnsPerDay',24))
        hasher=hashlib.sha256()
        for step in range(now+1,end+1):
            acts=self._units(route[step],farm,private,board)
            demands={}
            for a in acts:
                if a and a[0]=='PLANT' and len(a)>1:demands[a[1]]=demands.get(a[1],0)+1
            blocked={crop for crop,n in demands.items() if n>private['seeds'].get(crop,0)}
            for i,a in enumerate(acts):
                if a and a[0]=='PLANT' and a[1] in blocked:a=['PASS']
                positions=[farm['farmer'],*farm['hands']]
                if i >= len(positions):continue
                x,y=positions[i]
                inv_before=dict(private['inventories'][i])
                self.m._apply_unit_action(farm,private,i,a,board,day,int(cfg.get('turnsPerDay',24)),int(cfg.get('shedCapacity',100)))
                inv_after=private['inventories'][i]
                other_delta={p:inv_after.get(p,0)-inv_before.get(p,0)
                             for p in inv_after.keys()|inv_before.keys() if p!='FERTILIZER'
                             and inv_after.get(p,0)!=inv_before.get(p,0)}
                # Retain intermediate effects: FERTILIZE -> WATER -> HARVEST
                # by three workers can otherwise erase a yield difference
                # before the end-of-turn farm snapshot (the plant is removed).
                hasher.update(json.dumps([i,farm['tiles'][y][x],other_delta],sort_keys=True,separators=(',',':')).encode())
            self.m._decay_plants(farm,step)
            # With no further pickups or purchases, market sales cannot alter
            # farm/worker positions, service flags, harvests or seed consumption.
            # Cash and surplus depot stock are deliberately NOT compared here.
            physical={k:v for k,v in farm.items() if k!='money'}
            hasher.update(json.dumps([step,acts,physical,private['seeds']],sort_keys=True,separators=(',',':')).encode())
        return hasher.hexdigest()

    def transform(self, obs, cfg, action, route):
        self.last=BudgetDecision('not_applicable')
        now=int(obs['step']); end=int(cfg.get('episodeSteps',720))-2; turns=int(cfg.get('turnsPerDay',24))
        if turns<=1 or now%turns or now//turns!=end//turns or now+1>end or len(route)<=end:
            return action
        queue=action.get('market',[]); limit=int(cfg.get('maxMarketOrdersPerTurn',10))
        buys=[i for i,o in enumerate(queue[:limit]) if o and o[0]=='BUY_PRODUCT' and len(o)>=3 and o[1]=='FERTILIZER' and isinstance(o[2],int) and not isinstance(o[2],bool) and 0<o[2]<=100]
        if len(buys)!=1:return action
        slot=buys[0];q=queue[slot][2]
        if any(o for o in queue[slot+1:limit]):return action
        # A new worker roster must be deterministically funded before this buy.
        # Earlier non-fertilizer sales may add cash/free room; neither is needed
        # or assumed in this lower-bound reconstruction.
        for o in queue[:slot]:
            if o and o[0]!='HIRE' and not(o[0]=='SELL' and len(o)>1 and o[1]!='FERTILIZER'):
                return action
        # No later cash-sensitive purchases, no future depot reads after the
        # immediate pickup stage, and no branching to an alternate worker tape.
        for step in range(now+1,end+1):
            row=route[step]
            if any(o and o[0]!='SELL' for o in row.get('market',[])):return action
            units=[row.get('farmer',['PASS']),*row.get('hands',[])]
            if any(a and a[0]=='PICKUP' and (step!=now+1 or len(a)<2 or a[1]!='FERTILIZER') for a in units):return action
        farm,private=self.post_units(obs,action,cfg)
        for o in queue[:slot]:
            if o and o[0]=='HIRE':
                before=len(farm['hands'])
                self.m._do_hire(farm,private,len(farm['tiles']),int(cfg.get('farmHandCostMult',1)))
                if len(farm['hands'])!=before+1:
                    self.last=BudgetDecision('uncertain_hires',slot,q,q);return action
        initial=self._project(farm,private,route,now,end,cfg,q)
        retained=q; projections=1
        # Preserve physical effects for EVERY possible higher baseline fill.
        # Stop at first changed service/action; no monotonicity assumption is
        # used to skip a failed quantity or jump over a harmful alternative.
        for n in range(q-1,-1,-1):
            projections+=1
            if self._project(farm,private,route,now,end,cfg,n)!=initial:break
            retained=n
        self.last=BudgetDecision('trimmed' if retained<q else 'all_units_needed',slot,q,retained,projections)
        if retained==q:return action
        result=deepcopy(action)
        result['market'][slot]=['BUY_PRODUCT','FERTILIZER',retained] if retained else []
        return result
