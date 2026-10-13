# SPDX-License-Identifier: Apache-2.0
"""Adaptive complete-sale recourse over one current IntegratedSelectedAgent.

The reusable AdaptiveTransform itself receives the supplied action, feasible
candidate plans and the existing selected-action ProjectionLedger. ASH performs
its existing continuation checks. There is one production call in Agent.act.
"""
from copy import deepcopy
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from dependencies import load
from selector import WholePlanSelector
from history_streams import bounded_history_streams
from recourse import compile_policy, choose_observed

LAB = HERE.parent.parent / 'cloud-execution-lab'
sys.path.insert(0, str(LAB))
import integrated_selected as integrated
import selected_action_sell as sale
import selected_sell_core as math

ash = load(HERE.parent.parent/'cloud-plan-continuation/continuation.py', 't15_adaptive_ash')
flow = load(HERE.parent.parent/'cloud-market-response/flow.py', 't15_adaptive_flow')
sorrel = load(HERE.parent.parent/'cloud-market-response/vendor/sorrel_adapter.py', 't15_adaptive_sorrel')


class AdaptiveTransform:
    def __init__(self, mode='adaptive'):
        if mode not in ('adaptive', 'fixed', 'static'): raise ValueError('Unknown arm')
        self.mode = mode
        self.selector = WholePlanSelector()
        self.continuation = ash.ContinuationPlanSelector(self.selector)
        self.tree = None; self.last = {}; self.branch_done = False
        self.counts = {'admissions':0, 'branches':0, 'economic_branches':0,
                       'unknown_states':0, 'aborts':0, 'changed_actions':0}

    @staticmethod
    def feasible(ledger, plan, item, slot, end):
        remaining = [(t,q) for t,q in plan['sales'] if t >= ledger.now]
        if end > ledger.end or sum(q for _,q in remaining) > ledger.shed.get(item,0): return False
        if not ledger.feasible(item, remaining): return False
        # Exact market slot stays fixed across plan rows and future dates.
        for t,q in remaining:
            if not q: continue
            queue = ledger.market(t, item, q, ledger.shed.get(item,0))
            if queue is None: return False
            own = [(i,o) for i,o in enumerate(queue) if sale._sell(o,item)]
            if own != [(slot,['SELL',item,q])]: return False
            if any(o and o[0] != 'SELL' for o in queue[slot+1:]): return False
        return True

    def abort(self, base, reason):
        if self.selector.active:
            self.selector.completed.add(self.selector.active['key'])
        self.selector.active = None; self.tree = None
        self.last = {'reason':reason}; self.counts['aborts'] += 1
        return deepcopy(base)

    def transform(self, obs, cfg, base, *, ledger, offers=()):
        now = int(obs['step']); self.last = {}
        active = self.selector.active
        if active and now > active['completion_step']:
            self.selector.completed.add(active['key']); self.selector.active = None
            self.tree = None; active = None
        if active and not self.branch_done and now >= self.tree['branch']:
            if now != self.tree['branch']:
                return self.abort(base, 'branch_date_skipped')
            index = choose_observed(self.tree, obs, active['item'])
            if index is None:
                self.counts['unknown_states'] += 1
                return self.abort(base, 'unmodelled_public_inventory')
            if self.mode != 'adaptive': index = active['plan_index']
            proposed = self.tree['plans'][index]
            if not self.feasible(ledger, proposed, active['item'], active['slot'], active['end']):
                return self.abort(base, 'new_suffix_infeasible')
            active['plan'] = deepcopy(proposed); active['plan_index'] = index
            active['completion_step'] = max(t for t,q in proposed['sales'] if q)
            self.branch_done = True; self.counts['branches'] += 1
            self.counts['economic_branches'] += int(index != 0)
            self.last = {'reason':'observed_branch', 'index':index, 'item':active['item'],
                         'observed_inventory':obs['market']['inventory'][active['item']],
                         'tree':deepcopy(self.tree), 'window':deepcopy(active)}
        if self.selector.active is None:
            for offer in offers:
                tree, item, quantity, end = offer['tree'], offer['item'], offer['quantity'], offer['end']
                if not tree['active']: continue
                slots=[i for i,o in enumerate(base.get('market',[])) if sale._sell(o,item)]
                if len(slots)>1: continue
                slot=slots[0] if slots else len(base.get('market',[]))
                if slot >= ledger.max_orders: continue
                if any(not self.feasible(ledger,p,item,slot,end) for p in tree['plans']): continue
                offered=sum(o[2] for o in base.get('market',[]) if sale._sell(o,item))
                if offered != dict(tree['prefix']).get(now,0): continue
                key=f'{now}:{item}:{quantity}:{end}'
                if key in self.selector.completed: continue
                index=tree['static_choice'] if self.mode=='static' else 0
                plan=tree['plans'][index]
                self.selector.active={'key':key, 'plan':deepcopy(plan), 'plan_index':index,
                    'weights':[str(int(i==index)) for i in range(len(tree['plans']))],
                    'solution':{'value':str(tree['worst_margin'])}, 'mode':self.mode,
                    'item':item,'quantity':quantity,'now':now,'end':end,'slot':slot,
                    'completion_step':max(t for t,q in plan['sales'] if q)}
                self.tree=deepcopy(tree); self.branch_done=False
                self.counts['admissions']+=1
                self.last={'reason':'admitted','tree':deepcopy(tree),
                           'window':deepcopy(self.selector.active)}
                break
        if self.selector.active is None: return deepcopy(base)
        def continuing(plan, context):
            return self.feasible(ledger,plan,context['item'],context['slot'],context['end'])
        out=self.continuation.transform(obs,cfg,base,post_unit_shed=ledger.shed,
                                       continuation_feasible=continuing)
        if self.selector.active is None:
            self.counts['aborts']+=1; self.tree=None
            self.last={'reason':'continuation_fallback','detail':self.continuation.last_decision}
        if out != base: self.counts['changed_actions']+=1
        return out


class Agent:
    def __init__(self, mode='adaptive'):
        self.parent=integrated.IntegratedSelectedAgent()
        self.transformer=AdaptiveTransform(mode) if mode!='baseline' else None
        self.original=sale.optimize_lot; sale.optimize_lot=self.capture
        self.records=[]; self.history=flow.FlowHistory()
        self.previous=None; self.previous_sales={}; self.last={}; self.calls=0
        self.counts={'tables':0,'positive_trees':0,'feasible_candidate_windows':0}

    def capture(self, **kw):
        frozen,info=self.original(**kw)
        now,q,end=kw['now'],kw['quantity'],kw['dates'][-1]
        first=dict(frozen).get(now,0); remainder=q-first
        if info.get('feasible') and sum(n for _,n in frozen)==q and remainder>0 and end>now+1:
            prefix=[(now,first)] if first else []
            raw=[tuple((t,n) for t,n in frozen if n)]
            dates=sorted(set([now+1,end,*[t for t in kw['dates'] if t>now]]))
            for t in dates: raw.append(tuple(prefix+[(t,remainder)]))
            if remainder>1:
                raw.append(tuple(prefix+[(now+1,remainder//2),(end,remainder-remainder//2)]))
            plans=[]; seen=set()
            for p in raw:
                if p in seen: continue
                seen.add(p)
                if kw['capacity_ok'] and not kw['capacity_ok'](p): continue
                plans.append({'id':f'p{len(plans)}','sales':[list(x) for x in p]})
            if plans and tuple(map(tuple,plans[0]['sales']))==raw[0] and len(plans)>1:
                self.records.append((dict(kw),plans))
                self.counts['feasible_candidate_windows']+=1
        return frozen,info

    def observe(self,obs,cfg):
        if self.previous is None: return
        own=self.previous_sales
        receipt=sorrel.infer_rival_flow(self.previous,obs,
            [['SELL',p,q] for p,q in own.items() if q],cfg,
            quote=lambda p,i:math.m.market_price(p,i,self.previous['market'].get('params')),
            shops=math.m.SHOPS,center_products=math.m.TOWN_CENTER_PRODUCTS,own_sale_units=own)
        for item,r in receipt.get('products',{}).items():
            if item not in sale.PRODUCTS or r['status']!='identified_interval': continue
            lo,hi=r['rival_sale_units_range'];a,b=r['rival_market_supply_units_range']
            self.history.add(flow.FlowInterval(int(self.previous['step']),item,lo,hi,a,b,
                'floor_censored' if r['floor_nonadmission_possible'] else 'identified'))

    def streams(self,kw,slot):
        now,end,q=kw['now'],kw['dates'][-1],kw['quantity']
        align=('paired','after') if slot==0 else ('before','paired','after')
        rows=[('quiet',(),'paired')]
        for r in sorted({q,min(100,2*q)}):
            for t in sorted({now,now+1,end}):
                for a in align: rows.append((f'guard:{r}:{t}:{a}',((t,r),),a))
        for t in (now+1,end):
            for a in ('paired','after'):
                r=min(q,50);rows.append((f'correlated:{r}:{t}:{a}',((now,r),(t,r)),a))
        historical,_=self.history.scenarios(kw['item'],now,end,capacity=100)
        rows += bounded_history_streams(historical,32-len(rows))
        return rows

    def act(self,obs,cfg=None):
        cfg=dict(cfg or {}); self.calls+=1; self.records=[]; self.last={}
        self.observe(obs,cfg)
        base=self.parent.act(obs,cfg)  # Exactly one existing production call.
        packet=self.parent.last_packet
        out=base
        if self.transformer and packet and packet['projection']['observed_step']==obs['step']:
            try:
                ledger=sale.ProjectionLedger(obs,cfg,base,packet['post_unit_observation']['private']['shed'],
                    packet['projection'],packet['arrival_contract'],None,8)
                offers=[]
                if self.transformer.selector.active is None:
                    for kw,plans in self.records:
                        slots=[i for i,o in enumerate(base.get('market',[])) if sale._sell(o,kw['item'])]
                        if len(slots)>1: continue
                        slot=slots[0] if slots else len(base.get('market',[]))
                        streams=self.streams(kw,slot)
                        model=math.MarketPath(kw['item'],kw['inventory'],kw['params'],kw['shops'],cfg,kw['now'],kw['dates'][-1])
                        tree=compile_policy(model,plans,kw['quantity'],streams,kw['now']+1,math.absorption)
                        self.counts['tables']+=1;self.counts['positive_trees']+=int(tree['active'])
                        tree['streams']=streams;tree['market_params']=deepcopy(kw['params'])
                        offers.append({'tree':tree,'item':kw['item'],'quantity':kw['quantity'],'end':kw['dates'][-1]})
                out=self.transformer.transform(obs,cfg,base,ledger=ledger,offers=offers)
                self.last=deepcopy(self.transformer.last)
            except (ValueError,KeyError,TypeError,IndexError) as e:
                out=self.transformer.abort(base,type(e).__name__)
                self.last=deepcopy(self.transformer.last)
        elif self.transformer and self.transformer.selector.active:
            out=self.transformer.abort(base,'current_projection_unavailable')
        shed=packet['post_unit_observation']['private']['shed'] if packet else obs['private']['shed']
        available=dict(shed); sales={}
        for o in out.get('market',[])[:int(cfg.get('maxMarketOrdersPerTurn',10))]:
            if sale._sell(o) and o[1] in sale.PRODUCTS:
                p=o[1];q=min(max(0,int(o[2])),available.get(p,0));available[p]=available.get(p,0)-q
                sales[p]=sales.get(p,0)+q
        self.previous=deepcopy(obs);self.previous_sales=sales
        return out
