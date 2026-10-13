# SPDX-License-Identifier: Apache-2.0
"""Adaptive complete-sale recourse over one current IntegratedSelectedAgent.

The reusable AdaptiveTransform itself receives the supplied action, feasible
candidate plans and the existing selected-action ProjectionLedger. ASH performs
its existing continuation checks. There is one production call in Agent.act.
"""
from copy import deepcopy
from pathlib import Path
from threading import RLock
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
fills = load(HERE.parent.parent/'cloud-observed-fills/observed_fills.py', 't15_adaptive_fills')

# Capture is call-scoped: constructing another actor must not chain bound
# methods or retain earlier actors. The evaluator normally isolates processes;
# this reentrant lock also serializes parent calls made through this module.
_OPTIMIZE_LOT = sale.optimize_lot
_CAPTURE_LOCK = RLock()


_PRICE_FIELDS = ('base', 'I0', 'T', 'below_func', 'below_target',
                 'above_func', 'above_target')


def _economic_context(item, params, shops, cfg, now, end):
    """Detach the observable inputs that price the remaining complete lot.

    Inventory is deliberately not included: the existing causal branch owns
    that observation. Equal dated consumption is equivalent even when shop
    names/order or irrelevant configuration differ. Consumption after the
    final sale date cannot affect these complete-lot receipts.
    """
    for key in ('townShopSellInterval', 'townCenterSellInterval'):
        if key in cfg and int(cfg[key]) <= 0:
            raise ValueError(f"Invalid {key}: {cfg[key]}")
    price = (params or math.m.MARKET_PARAMS)[item]
    return {'version': 1, 'item': item, 'start': now, 'end': end,
            'price': {key: deepcopy(price[key]) for key in _PRICE_FIELDS},
            'absorption': [math.absorption(item, step, shops, cfg)
                           for step in range(now, end)]}


def _context_reason(tree, obs, cfg, item, end, *, admission=False):
    """Do not reuse an old table after its observable economics changed."""
    try:
        expected = tree['economic_context']
        now, start = int(obs['step']), expected['start']
        if (expected['version'] != 1 or expected['item'] != item
                or expected['end'] != end or not start <= now <= end
                or len(expected['absorption']) != end - start
                or (admission and start != now)):
            return 'market_context_unknown'
        current = _economic_context(
            item, obs['market'].get('params'), obs['town']['unlocked_shops'],
            cfg, now, end)
        if (current['price'] != expected['price']
                or current['absorption'] != expected['absorption'][now-start:]):
            return 'market_context_changed'
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError):
        return 'market_context_unknown'
    return None


class AdaptiveTransform:
    def __init__(self, mode='adaptive'):
        if mode not in ('adaptive', 'fixed', 'static'): raise ValueError('Unknown arm')
        self.mode = mode
        self.selector = WholePlanSelector()
        self.continuation = ash.ContinuationPlanSelector(self.selector)
        self.tree = None; self.last = {}; self.branch_done = False
        self.counts = {'admissions':0, 'branches':0, 'economic_branches':0,
                       'unknown_states':0, 'aborts':0, 'changed_actions':0,
                       'projection_fallbacks':0}

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
            self.counts['aborts'] += 1
        self.selector.active = None; self.tree = None
        self.last = {'reason':reason}
        return deepcopy(base)

    def expire(self, now):
        """Retire a finished window before deciding whether to capture offers.

        The completion date itself still owes its final sale. This is also
        called by transform so direct consumers retain the same lifecycle.
        """
        active = self.selector.active
        if active and now > active['completion_step']:
            self.selector.completed.add(active['key']); self.selector.active = None
            self.tree = None

    def transform(self, obs, cfg, base, *, ledger, offers=()):
        now = int(obs['step']); self.last = {}
        self.expire(now)
        active = self.selector.active
        if active:
            reason = _context_reason(self.tree, obs, cfg, active['item'], active['end'])
            if reason:
                return self.abort(base, reason)
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
            active['weights'] = [str(int(i==index)) for i in range(len(self.tree['plans']))]
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
                reason = _context_reason(tree, obs, cfg, item, end, admission=True)
                if reason:
                    self.last = {'reason': reason, 'item': item}
                    continue
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
        self.original=_OPTIMIZE_LOT
        self.records=[]; self.history=flow.FlowHistory()
        self.previous=None; self.previous_sales={}; self.last={}; self.calls=0
        self.previous_action={}; self.previous_cfg={}; self.fill_ledger=None
        self.last_fill={}; self.last_flow={}; self._history_observed=False
        self.counts={'tables':0,'positive_trees':0,'feasible_candidate_windows':0}
        self._reset_offer_work()

    def _parent_action(self, obs, cfg):
        # Only a new admission consumes offers. Baseline and already-active
        # plans still run the same optimizer, without unused offer collection.
        collecting = (self.transformer is not None
                      and self.transformer.selector.active is None)
        with _CAPTURE_LOCK:
            previous = sale.optimize_lot
            sale.optimize_lot = self.capture if collecting else self.original
            try:
                return self.parent.act(obs, cfg)
            finally:
                sale.optimize_lot = previous

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

    @staticmethod
    def _exact_fills(result, order_type):
        """Only singleton counts for EVERY same-product slot become receipts.

        Marginal interval endpoints are correlated. An ambiguous slot prevents
        an exact aggregate for that product, even if another slot is exact.
        """
        if result.get('status') not in ('reconciled', 'ambiguous'): return {}
        totals={}; unknown=set()
        for row in result.get('orders', ()):
            if row.get('type') != order_type or row.get('item') is None: continue
            item=row['item']; low=row.get('fill_min'); high=row.get('fill_max')
            if low is None or low != high:
                unknown.add(item)
            else:
                totals[item]=totals.get(item,0)+low
        return {p:q for p,q in totals.items() if p not in unknown}

    def _remember_action(self, obs, cfg, action, packet):
        """Bind final queue and SAME-stage known stock; never reuse a stale packet."""
        self.previous=deepcopy(obs); self.previous_action=deepcopy(action)
        self.previous_cfg=deepcopy(cfg); self.previous_sales={}
        self.fill_ledger=None; self._history_observed=False
        try:
            post=packet['post_unit_observation']
            if (packet['projection']['observed_step'] != obs['step']
                    or post['step'] != obs['step'] or post['player'] != obs['player']):
                return
            # The adaptive transform changes only market slots. Its final queue
            # shares this already-executed unit stage; no controller/projection
            # call is needed. Bounded uncertainty must not become a guessed fill.
            ledger=fills.ObservedFillLedger(max_states=512, max_transitions=4096)
            ledger.record(obs,cfg,action,post_unit_shed=post['private']['shed'],
                          post_unit_inventories=post['private'].get('inventories'))
            self.fill_ledger=ledger
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError):
            # Requests still enter the flow model as bounds, not zero receipts.
            pass

    def observe(self,obs,cfg):
        if self.previous is None or self._history_observed: return
        before=self.previous
        if obs.get('step') == before.get('step'): return
        self.previous_sales={}
        self.last_fill={'status':'unknown','reason':'current_post_unit_snapshot_unavailable'}
        self.last_flow={'status':'unknown','reason':'nonadjacent_or_different_actor','products':{}}
        try:
            if (obs['step'] != before['step']+1 or before.get('player') not in (0,1)
                    or obs.get('player') != before['player']): return
            self._history_observed=True
            if self.fill_ledger is not None:
                self.last_fill=self.fill_ledger.observe(obs)
            own=self._exact_fills(self.last_fill,'SELL')
            bought=self._exact_fills(self.last_fill,'BUY_PRODUCT')
            # Preserve BUY_PRODUCT, duplicate orders and original positions.
            # Empty receipt mappings deliberately leave requested fills unknown.
            receipt=sorrel.infer_rival_flow(before,obs,
                self.previous_action.get('market',[]),self.previous_cfg,
                quote=lambda p,i:math.m.market_price(p,i,before['market'].get('params')),
                shops=math.m.SHOPS,center_products=math.m.TOWN_CENTER_PRODUCTS,
                own_sale_units=own,own_buy_units=bought)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError):
            self.last_flow={'status':'unknown','reason':'invalid_flow_inputs','products':{}}
            return
        self.previous_sales=own; self.last_flow=receipt
        for item,r in receipt.get('products',{}).items():
            if item not in sale.PRODUCTS or r['status']!='identified_interval': continue
            lo,hi=r['rival_sale_units_range'];a,b=r['rival_market_supply_units_range']
            self.history.add(flow.FlowInterval(int(before['step']),item,lo,hi,a,b,
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

    def _reset_offer_work(self):
        self.offer_work = {'captured_windows': 0, 'inspected_windows': 0,
                           'compiled_windows': 0, 'admitted_index': None}
        self._offered_index = None

    def _offers(self, cfg, base):
        """Compile in capture order, stopping when the consumer accepts a lot.

        Only reached compilation errors enter the existing fallback. An unused
        later window is not evaluated and cannot invalidate an earlier choice.
        No plans, streams or admission tests are removed from a reached window.
        """
        for index, (kw, plans) in enumerate(self.records):
            self.offer_work['inspected_windows'] += 1
            slots=[i for i,o in enumerate(base.get('market',[])) if sale._sell(o,kw['item'])]
            if len(slots)>1: continue
            slot=slots[0] if slots else len(base.get('market',[]))
            streams=self.streams(kw,slot)
            model=math.MarketPath(kw['item'],kw['inventory'],kw['params'],kw['shops'],cfg,kw['now'],kw['dates'][-1])
            tree=compile_policy(model,plans,kw['quantity'],streams,kw['now']+1,math.absorption)
            self.counts['tables']+=1;self.counts['positive_trees']+=int(tree['active'])
            self.offer_work['compiled_windows'] += 1
            tree['streams']=streams;tree['market_params']=deepcopy(kw['params'])
            tree['economic_context'] = _economic_context(
                kw['item'], kw['params'], kw['shops'], cfg, kw['now'], kw['dates'][-1])
            self._offered_index = index
            yield {'tree':tree,'item':kw['item'],'quantity':kw['quantity'],'end':kw['dates'][-1]}

    def act(self,obs,cfg=None):
        cfg=dict(cfg or {}); self.calls+=1; self.records=[]; self.last={}
        self._reset_offer_work()
        self.observe(obs,cfg)
        if self.transformer:
            self.transformer.expire(int(obs['step']))
        base=self._parent_action(obs,cfg)  # Exactly one existing production call.
        packet=self.parent.last_packet
        self.offer_work['captured_windows'] = len(self.records)
        out=base
        if self.transformer and packet and packet['projection']['observed_step']==obs['step']:
            try:
                ledger=sale.ProjectionLedger(obs,cfg,base,packet['post_unit_observation']['private']['shed'],
                    packet['projection'],packet['arrival_contract'],None,8)
                offers = (self._offers(cfg, base)
                          if self.transformer.selector.active is None else ())
                admissions = self.transformer.counts['admissions']
                try:
                    out=self.transformer.transform(obs,cfg,base,ledger=ledger,offers=offers)
                finally:
                    if self.transformer.counts['admissions'] > admissions:
                        self.offer_work['admitted_index'] = self._offered_index
                self.last=deepcopy(self.transformer.last)
            except (ValueError,KeyError,TypeError,IndexError) as e:
                self.transformer.counts['projection_fallbacks']+=1
                out=self.transformer.abort(base,type(e).__name__)
                self.last=deepcopy(self.transformer.last)
        elif self.transformer and self.transformer.selector.active:
            out=self.transformer.abort(base,'current_projection_unavailable')
        self._remember_action(obs,cfg,out,packet)
        return out
