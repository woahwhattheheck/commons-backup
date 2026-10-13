# SPDX-License-Identifier: Apache-2.0
"""Research bridge: one accepted T12/SELL parent, then supplied-action transform.

T12 supplies its unchanged causal history. Capturing optimizer inputs does not
construct or invoke another production controller. Frozen source is unedited.
"""
import copy
from pathlib import Path

from dependencies import HERE, load
from selector import WholePlanSelector
from tables import best_pair, receipt_table
from history_streams import bounded_history_streams


class MarketGameTheory:
    def __init__(self,mode='mixed'):
        t12=load(HERE.parent/'cloud-market-response/policy.py','t15_t12_policy')
        self.parent=t12.ResponsePolicy(enabled=False)
        self.source=self.parent.source
        self.original=self.parent.original_optimizer
        self.source.optimize_lot=self.capture
        self.mode=mode;self.selector=WholePlanSelector();self.records=[]
        self.counts={'calls':0,'eligible_windows':0,'tables':0,'activations':0,'aborts':0}
        self.last={};self.attempted=set()

    def capture(self,**kw):
        frozen,info=self.original(**kw)
        q=kw['quantity'];now=kw['now'];end=kw['dates'][-1]
        if info.get('feasible') and sum(n for t,n in frozen)==q and end>now:
            candidates={tuple((t,n) for t,n in frozen if n)}
            for t in kw['dates']:candidates.add(((t,q),))
            for first in sorted({1,q//4,q//2,3*q//4,q-1}):
                if 0<first<q:candidates.add(((now,first),(end,q-first)))
            reference=tuple((t,n) for t,n in frozen if n)
            ordered=[reference]+[p for p in sorted(candidates) if p!=reference]
            # Feasibility closures are evaluated inside the authoritative
            # scheduler's current loop iteration, before their captures change.
            plans=[]
            for p in ordered:
                if dict(p).get(now,0)<kw['minimum_now']:continue
                if kw['capacity_ok'] and not kw['capacity_ok'](p):continue
                plans.append({'id':'p'+str(len(plans)),'sales':[list(x) for x in p]})
            if plans and plans[0]['sales']==[list(x) for x in reference]:
                self.records.append((dict(kw),plans[:9]))
        return frozen,info

    def _streams(self,kw,slot):
        now,end,q=kw['now'],kw['dates'][-1],kw['quantity']
        historical,prediction=self.parent.history.scenarios(kw['item'],now,end,
                                            capacity=int(kw['config'].get('shedCapacity',100)))
        if not historical:return [],0,prediction
        alignment=('paired','after') if slot==0 else ('before','paired','after')
        guards=[('quiet',(),'paired')]
        cap=int(kw['config'].get('shedCapacity',100))
        for r in sorted({1,q,min(cap,2*q)}):
            for date in sorted({now,min(now+2,end),end}):
                for a in alignment:
                    guards.append((f'stress_{r}_{date}_{a}',((date,r),),a))
        # The bounded additional rows are complete unshifted paired windows
        # emitted by T12, in its existing newest-lag order. No iid hourly mix.
        remaining=32-len(guards)
        rows=bounded_history_streams(historical,remaining)
        return guards+rows,len(guards),prediction

    def act(self,obs,cfg=None):
        cfg=dict(cfg or {});self.records=[];self.counts['calls']+=1
        base=self.parent.act(obs,cfg)  # The sole production/controller call.
        _,private=self.source.post_units(obs,base,cfg)
        now=int(obs['step']);out=base
        if self.selector.active and now<=self.selector.active['end']:
            out=self.selector.transform(obs,cfg,base,post_unit_shed=private['shed'])
        elif self.mode!='baseline':
            if self.selector.active:
                self.selector.transform(obs,cfg,base,post_unit_shed=private['shed'])
            for kw,plans in self.records:
                if len(plans)<3:continue
                item=kw['item'];end=kw['dates'][-1]
                key=f'{now}:{item}:{kw["quantity"]}:{end}'
                if key in self.attempted:continue
                self.attempted.add(key)
                orders=base.get('market',[])
                positions=[i for i,o in enumerate(orders) if o and len(o)>=3 and o[:2]==['SELL',item]]
                if len(positions)>1:continue
                slot=positions[0] if positions else len(orders)
                if slot>=int(cfg.get('maxMarketOrdersPerTurn',10)):continue
                offered=sum(o[2] for o in orders if o and len(o)>=3 and o[:2]==['SELL',item])
                if offered!=dict(plans[0]['sales']).get(now,0):continue
                route=self.parent.scheduler.controller.R[self.parent.scheduler.controller.cur]
                def future_slots(plan):
                    for t,q in plan['sales']:
                        queue=orders if t==now else route[t].get('market',[]) if t<len(route) else []
                        if q and slot<len(queue) and queue[slot] and not (
                                len(queue[slot])>=3 and queue[slot][:2]==['SELL',item]):return False
                    return True
                plans=[p for p in plans if future_slots(p)]
                if len(plans)<3 or plans[0]['id']!='p0':continue
                cash=self.parent.scheduler.cash_reserve(obs,cfg,base,end)
                if obs['farms'][obs['player']]['money']<cash:continue
                self.counts['eligible_windows']+=1
                streams,learned_start,prediction=self._streams(kw,slot)
                if not streams:continue
                model=self.source.MarketPath(item,kw['inventory'],kw['params'],kw['shops'],cfg,now,end)
                deltas,receipts=receipt_table(model,plans,kw['quantity'],streams)
                self.counts['tables']+=1
                chosen=best_pair(plans,deltas,mode=self.mode,learned_start=learned_start)
                if chosen is None:continue
                subset,table,indices=chosen
                window={'key':key,'item':item,'quantity':kw['quantity'],'now':now,'end':end,
                        'slot':slot,'plans':subset,'deltas':table,'learned_start':learned_start}
                valid={p['id'] for p in plans}
                out=self.selector.transform(obs,cfg,base,window=window,post_unit_shed=private['shed'],
                    reservations={'cash':cash},feasible=lambda p:p['id'] in valid,mode=self.mode)
                if self.selector.active:
                    self.counts['activations']+=1
                    self.last={'window':window,'streams':streams,'prediction':prediction,
                        'receipt_rows':[receipts[i] for i in indices],
                        'commitment':copy.deepcopy(self.selector.active)}
                    break
        if self.selector.last_decision.get('reason')=='commitment_aborted':self.counts['aborts']+=1
        # T12's next causal flow inference uses our actually returned sales.
        available=dict(private['shed']);sales={}
        for order in out.get('market',[])[:int(cfg.get('maxMarketOrdersPerTurn',10))]:
            if order and len(order)>=3 and order[0]=='SELL' and order[1] in self.source.PRODUCTS:
                item=order[1];q=min(max(0,int(order[2])),max(0,available.get(item,0)))
                available[item]=available.get(item,0)-q;sales[item]=sales.get(item,0)+q
        self.parent.previous_sales=sales
        return out
