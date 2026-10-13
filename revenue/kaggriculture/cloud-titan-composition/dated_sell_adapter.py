# SPDX-License-Identifier: Apache-2.0
"""T08 dated capacity envelope over ASTRA's unchanged finite-horizon optimizer.

receipt_profile projection adapted from frozen scheduler.py (ASTRA, Apache-2.0).
New design: protect possible extra deposits at their earliest physically possible
date/phase, instead of subtracting all visible yield from capacity immediately.
An upper envelope is not predicted production, stock, probability or sale.
"""
import copy
from controller import Titan
from sell_adapter import SelectedActionSell
from scheduler import m, parent

def possible_extra_deposits(farm, private, now, end, turns_per_day=24):
    board=len(farm['tiles']);h=board//2
    access=((h-1,h-1),(h,h-1),(h-1,h),(h,h))
    positions=[farm['farmer'],*farm.get('hands',[])]
    dist=lambda a,b:abs(a[0]-b[0])+abs(a[1]-b[1])
    depot=lambda pos:min(dist(pos,p) for p in access)
    close=(now//turns_per_day+1)*turns_per_day-1
    events=[]
    def add(earliest,quantity,reason):
        date=min(earliest,close)
        phase='after' if earliest>close else 'before'
        if date<=end and quantity>0:
            events.append((date,phase,int(quantity),reason))
    # Carried stock already appears in the reference route. Counting it again at
    # its earliest alternate arrival protects timing differences conservatively.
    for pos,inv in zip(positions,private.get('inventories',[])):
        add(now+max(1,depot(pos)),sum(max(0,int(n)) for n in inv.values()),'carried-earlier')
    # The frozen cap policy does no harvesting on the final day.
    if now//turns_per_day>=29:return events
    for y,row in enumerate(farm['tiles']):
        for x,tile in enumerate(row):
            if not isinstance(tile,dict) or tile.get('animal') is None:continue
            qty=max(0,int(tile.get('yield_units',0)))
            harvest=now+min(dist(p,(x,y)) for p in positions)+1
            if harvest>close:continue
            # Allow every worker and every animal, even ones the cap chooser will
            # reject. This is deliberately an upper envelope. No future care or
            # animal refresh can add carried output before this same-day horizon.
            add(harvest+depot((x,y)),qty,'held-animal')
    return sorted(events)

class DatedSelectedActionSell(SelectedActionSell):
    def receipt_profile(self,obs,base,farm,private,end,item,config):
        now=int(obs['step']);cap=int(config.get('shedCapacity',100))
        extra=possible_extra_deposits(farm,private,now,end)
        f,p=copy.deepcopy(farm),copy.deepcopy(private)
        for o in base['market']:
            if o and o[0]=='SELL' and len(o)>2 and o[1]!=item:
                p['shed'][o[1]]=max(0,p['shed'].get(o[1],0)-int(o[2]))
        profile=[];route=self.controller.R[self.controller.cur]
        for t in range(now,end+1):
            if t>now:
                act=route[t] if t<len(route) else parent.PASS
                acts=[act.get('farmer',['PASS']),*act.get('hands',[])]
                for i,a in enumerate(acts):
                    m._apply_unit_action(f,p,i,a,len(f['tiles']),t//24,24,10**6)
            profile.append((t,'before',sum(p['shed'].values())))
            orders=base['market'] if t==now else (route[t].get('market',[]) if t<len(route) else [])
            for o in orders:
                if not o:continue
                if o[0]=='SELL' and t>now and o[1]!=item:
                    p['shed'][o[1]]=max(0,p['shed'].get(o[1],0)-int(o[2]))
                elif o[0] in ('BUY_PRODUCT','BUY_ANIMAL') and len(o)>2:
                    p['shed'][o[1]]=p['shed'].get(o[1],0)+int(o[2])
                elif o[0]=='HIRE':
                    f['hands'].append(m._spawn_hand(f,len(f['tiles'])));p['inventories'].append({})
            if t%24==23:
                m._drop_inventories_to_shed(p,10**6)
                profile.append((t,'after',sum(p['shed'].values())))
                break
            profile.append((t,'after',sum(p['shed'].values())))
        def feasible(plan):
            sold=0;orders=dict(plan)
            for t,phase,total in profile:
                if phase=='after':sold+=orders.get(t,0)
                if t==now and phase=='before':continue
                reserve=sum(q for d,p,q,_ in extra if d<t or (d==t and (p=='before' or phase=='after')))
                if total+reserve-sold>cap-1:return False
            return True
        return feasible

class DatedCapSell:
    def __init__(self):
        self.production=Titan(carrot=True,cap=True)
        self.execution=DatedSelectedActionSell(self.production.base)
    def act(self,obs,cfg=None):
        selected=self.production.act(obs,cfg)
        return self.execution.transform(obs,cfg,selected)

_INSTANCE=None
def agent(obs,cfg=None):
    global _INSTANCE
    if _INSTANCE is None or obs.get('step',-1)==0:_INSTANCE=DatedCapSell()
    return _INSTANCE.act(obs,cfg)
