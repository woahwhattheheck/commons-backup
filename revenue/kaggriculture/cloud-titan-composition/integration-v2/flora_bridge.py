# SPDX-License-Identifier: MIT
"""Selected-action/arrival bridge over unchanged FLORA 87aed426 source.

No second Arlene controller is constructed or called. This is an integration
adapter, not a replacement for FLORA's allocation or GPT's SELL optimizer.
"""
import copy
import hashlib
import importlib.util
from pathlib import Path

HERE=Path(__file__).resolve().parent
PIN='87aed426f965e8ac542c32b748b7d58847ced19b2681c862c10820b698c46ee7'

class FloraBridge:
    def __init__(self,base_owner):
        path=HERE.parent/'vendor/flora/candidate.py'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=PIN:
            raise ValueError('FLORA source does not match the admitted pin')
        spec=importlib.util.spec_from_file_location('flora_selected_action',path)
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.module._A=base_owner
        self.selected=None;self.consumed=False;self.last_step=None
        self.blocked_targets=set();self.prior={}
        self.module._EH_BASE_AGENT=self._take_selected
        jobs=self.module._eh_incremental_jobs
        self.module._eh_incremental_jobs=lambda obs,end:[j for j in jobs(obs,end)
            if tuple(j['target']) not in self.blocked_targets]

    def owned_workers(self,obs):
        """Other unit overlays must exclude these currently leased workers."""
        return {int(r['hand_index'])+1 for r in self.module._EH_RESERVATIONS.get(int(obs['player']),[])
                if int(r['day'])==int(obs['day'])}

    def _take_selected(self,obs):
        if self.consumed or self.selected is None:
            raise RuntimeError('FLORA must consume exactly one selected base action')
        self.consumed=True
        return copy.deepcopy(self.selected)

    def transform(self,obs,selected_action,*,blocked_targets=()):
        """Append FLORA's optional hand to the already selected base action.

        Caller excludes existing FLORA-owned workers from every other unit
        overlay before this stage. blocked_targets excludes other producers'
        pending targets when FLORA chooses a new rescue. This does not authorize
        combining unadapted cap worker ownership with FLORA.
        """
        now=int(obs['step'])
        if self.last_step is not None and now<=self.last_step:
            raise RuntimeError('Use one bridge per match and one transform per step')
        self.selected=copy.deepcopy(selected_action);self.consumed=False
        self.blocked_targets={tuple(t) for t in blocked_targets}
        out=self.module.agent(obs)
        if not self.consumed:
            raise RuntimeError('FLORA did not consume the selected action')
        self.last_step=now
        return out

    def producer_snapshot(self,obs,selected_action):
        """Export current FLORA row facts, including whole-harvest obligations.

        Call after transform; for SELL capacity reconciliation pass the exact
        own post-unit observation produced by the caller's deterministic unit
        transition. That removes newly carried harvest from pending reservation
        before projecting its EOD deposit. A raw pre-unit observation is also a
        valid snapshot, but must not be mixed with a post-unit stock projection.

        Dedicated hired workers start empty. Once any product is carried, the
        frozen executor PASSes and does no further harvest; unrealized remainder
        of the old planned quantity is cancelled, not retained as a ghost lot.
        Incremental units retain FLORA's conditional valuation, not a measured
        counterfactual cash claim.
        """
        now=int(obs['step']);day=int(obs['day']);seat=int(obs['player'])
        if self.last_step!=now:
            raise RuntimeError('Snapshot requires this step\'s selected-action transform')
        farm=obs['farms'][seat];invs=obs['private'].get('inventories',[])
        rows=self.module._EH_RESERVATIONS.get(seat,[])
        hires=[i for i,o in enumerate(selected_action.get('market',[])) if o and o[0]=='HIRE']
        nworkers=1+len(farm.get('hands',[]));plans=[];present={}
        for row in rows:
            eid=str(row['id']);present[eid]=row
            if int(row['day'])!=day:
                plans.append({'errand_id':eid,'status':'aborted'});continue
            worker=int(row['hand_index'])+1;product=row['product']
            carried=max(0,int(invs[worker].get(product,0))) if worker<len(invs) else 0
            total=carried if carried else int(row['harvest_units'])
            fact={'errand_id':eid,'worker_index':worker,'target':list(row['target']),
                'product':product,'units_total':total,
                'units_incremental':min(total,int(row['economic_units'])),
                'arrival_step':(day+1)*24-1,'arrival_kind':'eod_auto',
                'no_forced_sale_date':True,'status':'carried' if carried else 'pending',
                'observed_carried_units':carried,
                'original_planned_units_total':int(row['harvest_units']),
                'cancelled_unrealized_units':max(0,int(row['harvest_units'])-carried) if carried else 0,
                'incremental_basis':'FLORA conditional economic_units, not measured cash'}
            if worker>=nworkers:
                ordinal=worker-nworkers
                if ordinal<len(hires):fact['hire_order_index']=hires[ordinal]
                else:fact={'errand_id':eid,'status':'aborted'}
            plans.append(fact)
        for eid in self.prior:
            if eid not in present:plans.append({'errand_id':eid,'status':'aborted'})
        self.prior=copy.deepcopy(present)
        return {'owner':'flora','observed_step':now,'plans':plans}
