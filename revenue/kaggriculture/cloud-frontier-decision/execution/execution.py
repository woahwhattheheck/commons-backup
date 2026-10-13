# SPDX-License-Identifier: Apache-2.0
"""SORREL: game adaptation of Hummingbot depth sizing and budget reservation.
New implementation; see NOTICE. No exchange, hidden seed, or optimizer dependency.
"""
from collections import Counter
from math import floor

ELIGIBLE = {'CARROT', 'TOMATO', 'STRAWBERRY', 'MELON', 'EGG', 'MILK', 'WOOL'}


def marginal_receipt(item, inventory, quantity, quote):
    """Conditional own stream; floor-aware, no rival priority assumption."""
    cash = supplied = 0
    for _ in range(quantity):
        price = quote(item, inventory)
        cash += price
        if price > 1:
            supplied += 1
            inventory += 1
    return {'sale_units': quantity, 'market_supply_units': supplied,
            'cash': cash, 'inventory_after': inventory}


def capped_quantity(item, inventory, stock, remaining, quote, *, theta=.05,
                    alpha=.5, depth_limit=100):
    """D(theta) is sequential marginal depth within a current-quote price band.

    The synthetic depth is bounded by physical shed capacity, including at floor.
    Returned receipt is conditional on no concurrent opponent orders.
    """
    if not 0 <= theta <= 1 or not 0 < alpha <= 1:
        raise ValueError('theta in [0,1], alpha in (0,1] required')
    threshold = quote(item, inventory) * (1-theta)
    inv = inventory
    depth = 0
    for _ in range(max(0, int(depth_limit))):
        price = quote(item, inv)
        if price < threshold:
            break
        depth += 1
        if price > 1:
            inv += 1
    qty = max(0, min(int(stock), int(remaining), floor(alpha*depth)))
    return qty, dict(depth=depth, threshold=threshold,
                     **marginal_receipt(item, inventory, qty, quote))


class SellExecution:
    def __init__(self, mode='cap', theta=.05, alpha=.5):
        if mode not in ('baseline','cap','demand'):
            raise ValueError(mode)
        self.mode, self.theta, self.alpha = mode, theta, alpha
        self.lots = {}
        self.pending = None
        self.receipts = []
        self.stats = Counter()
        self.last = -1

    def observe_fills(self, step, shed):
        """Only reconcile exact pure-SELL/non-EOD previous turns.

        post_unit_shed - next observed shed is actual own fill quantity, regardless
        of rival price impact. Cash and market supply are NOT inferred from that.
        Missing/nonconsecutive observations leave fills unknown and reconcile lots
        conservatively against observed available stock, never claimed completion.
        """
        if self.pending and self.pending['step']+1 == step:
            for item, sent in self.pending['sent'].items():
                delta = self.pending['post_unit_shed'].get(item,0)-shed.get(item,0)
                valid = 0 <= delta <= sent
                filled = delta if valid else None
                self.receipts.append({'step':self.pending['step'], 'product':item,
                                      'requested_units':sent,'actual_sale_units':filled,
                                      'cash':None,'market_supply_units':None})
                if valid and item in self.lots:
                    self.lots[item]['remaining'] = max(0,self.lots[item]['remaining']-filled)
                    self.stats['observed_fill_units'] += filled
                elif not valid:
                    self.stats['unknown_fill_receipts'] += 1
        self.pending = None
        self.lots = {p:l for p,l in self.lots.items() if l['remaining']>0}
        self.receipts = self.receipts[-32:]

    def transform(self, obs, cfg, action, post_unit_shed, carried, quote,
                  public_demand, future_actions):
        """Preserve all unit actions and inherited market slots/order.

        future_actions is this controller's own selected baseline plan only, never
        opponent trace or future observations. All dependency overrides bypass cap.
        public_demand(product, phase_step) reads CURRENT shop copies and config.
        """
        step = int(obs['step']); turns = int(cfg.get('turnsPerDay',24))
        last = int(cfg.get('episodeSteps',720))-2
        capacity = int(cfg.get('shedCapacity',100)); max_orders=int(cfg.get('maxMarketOrdersPerTurn',10))
        shed=obs['private'].get('shed',{})
        if step <= self.last:
            self.lots={}; self.pending=None
        self.observe_fills(step,shed); self.last=step
        if self.mode=='baseline': return action
        out={**action,'market':[list(o) for o in action.get('market',[])]}
        orders=out['market']
        requested=Counter()
        for o in orders:
            if o and o[0]=='SELL': requested[o[1]]+=max(0,int(o[2]))
        # Existing demand replaces overlap with outstanding parent lot; repeated
        # baseline offers of the same held stock do not manufacture new units.
        for p,n in requested.items():
            if p not in ELIGIBLE: continue
            if p not in self.lots: self.lots[p]={'remaining':0,'opened':step}
            self.lots[p]['remaining']=min(post_unit_shed.get(p,0),max(n,self.lots[p]['remaining']))
        mixed=any(o and o[0]!='SELL' for o in orders)
        # Never alter inherited non-SELL queues; finance/input timing stays intact.
        # Flush one turn BEFORE any selected-plan market purchase/hire/land action.
        next_dependency=any(o and o[0]!='SELL' for a in future_actions[:1] for o in a.get('market',[]))
        carried_total=sum(max(0,n) for inv in carried for n in inv.values())
        farm=obs['farms'][obs['player']]
        held=sum(max(0,int(t.get('yield_units',0))) for row in farm['tiles'] for t in row if isinstance(t,dict))
        # Conservative upper bound: all visible held yield/carried goods could
        # reach shed. Protect capacity before deposits, not after lost overflow.
        capacity_risk=sum(post_unit_shed.values())+carried_total+held>=capacity
        deadline=step>=last or step%turns>=turns-2
        global_flush=next_dependency or capacity_risk or deadline
        if mixed:
            self.stats['mixed_queue_preserved']+=1
            return action
        present=set(requested)
        for p,lot in self.lots.items():
            if p not in present and lot['remaining']>0 and post_unit_shed.get(p,0)>0 and len(orders)<max_orders:
                orders.append(['SELL',p,min(lot['remaining'],post_unit_shed[p])])
        available=dict(post_unit_shed)
        market_inv=dict(obs['market']['inventory'])
        sent=Counter(); depth_spent=Counter(); turn_budget={}
        for o in orders:
            if not o or o[0]!='SELL': continue
            p=o[1]; have=max(0,available.get(p,0)); inherited=max(0,int(o[2]))
            lot=self.lots.get(p)
            flush=global_flush or (lot and step-lot['opened']>=4)
            remaining=max(0,(lot['remaining'] if lot else inherited)-sent[p])
            q=min(have,inherited)
            if p in ELIGIBLE and lot:
                # A single per-product turn budget: splitting orders cannot reset
                # either synthetic depth or stock reservations.
                if p not in turn_budget:
                    turn_budget[p]=capped_quantity(p,market_inv[p],have,remaining,quote,
                        theta=self.theta,alpha=self.alpha,depth_limit=capacity)[0]
                if not flush:
                    q=min(q,remaining,max(0,turn_budget[p]-depth_spent[p]))
                    if self.mode=='demand':
                        event=next((t for t in range(step,min(step+4,last)) if public_demand(p,t)>0),None) if 'release' not in lot else None
                        if event is not None and event+1<=last:
                            # Wait for a public consumption phase only if its
                            # counterfactual no-rival quote improves. Reobserve next
                            # turn; this is not guaranteed recovery or a forecast.
                            demand=sum(public_demand(p,t) for t in range(step,event+1))
                            if quote(p,market_inv[p]-demand)>quote(p,market_inv[p]):
                                lot['release']=event+1
                        if step < lot.get('release',step):
                            q=0
                else:
                    q=min(have,max(inherited,remaining))
                    self.stats['override_orders']+=1
            depth_spent[p]+=q; available[p]=have-q; sent[p]+=q
            receipt=marginal_receipt(p,market_inv[p],q,quote)
            market_inv[p]=receipt['inventory_after']
            if q!=inherited:
                self.stats['resized_orders']+=1
                self.stats['withheld_units']+=max(0,inherited-q)
            o[2]=q  # Keep even a zero-quantity slot to preserve queue alignment.
        if step%turns!=turns-1:
            self.pending={'step':step,'post_unit_shed':dict(post_unit_shed),'sent':dict(sent)}
        self.stats['turns']+=1
        return out
