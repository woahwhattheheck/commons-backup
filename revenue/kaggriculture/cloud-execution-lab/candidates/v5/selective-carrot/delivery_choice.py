# SPDX-License-Identifier: Apache-2.0
"""Replace displaced feed after carrot delivery; settle only observed purchases."""
from copy import deepcopy
from selective_carrot import CropChoice


class DeliveryChoice(CropChoice):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.debts = []
        self.purchase = None

    def observe(self, obs):
        now = int(obs['step'])
        if now == self.last_step:
            return
        if now < self.last_step:
            self.debts = []
            self.purchase = None
        purchase = self.purchase
        self.purchase = None
        if purchase and now == purchase['step'] + 1:
            # Replacement is never issued at EOD or beside another wheat buy.
            # Units have already run at the recorded stock boundary; neither
            # town consumption nor crop growth changes this private shed.
            gained = obs['private']['shed'].get('WHEAT', 0) - purchase['stock_before']
            remaining = min(purchase['quantity'], max(0, gained))
            for debt in self.debts:
                if debt['due'] > purchase['step']:
                    continue
                take = min(debt['quantity'], remaining)
                debt['quantity'] -= take
                remaining -= take
            self.debts = [debt for debt in self.debts if debt['quantity']]
        prior = [dict(lot) for lot in self.lots if lot['status'] == 'harvest_returned']
        super().observe(obs)
        farm = obs['farms'][obs['player']]
        for lot in prior:
            x, y = lot['site']
            tile = farm['tiles'][y][x]
            same = (isinstance(tile, dict) and tile.get('crop') == 'CARROT'
                    and tile.get('planted_day') == lot['planted_day'])
            if not same:
                # Baseline wheat yield, not any incidental carrot yield bonus.
                self.debts.append({'due': lot['sale_step'], 'quantity': lot['quantity']})

    def market(self, obs, cfg, selected, route, route_id, post):
        harvested = [lot for lot in self.lots if lot['status'] == 'harvest_returned']
        for lot in harvested:
            lot['status'] = 'harvest_pending_delivery'
        try:
            out = super().market(obs, cfg, selected, route, route_id, post)
        finally:
            for lot in harvested:
                lot['status'] = 'harvest_returned'
        now = int(obs['step'])
        due = sum(debt['quantity'] for debt in self.debts if debt['due'] <= now)
        orders = out.get('market', [])
        if not due or now % 24 == 23 or len(orders) >= 10:
            return out
        # An adjacent authored purchase makes the next shed receipt ambiguous.
        if any(order[:2] == ['BUY_PRODUCT', 'WHEAT'] for order in orders):
            return out
        stock = dict(post['private']['shed'])
        for order in orders:
            if len(order) < 3:
                continue
            op, item, q = order[:3]
            q = max(0, int(q))
            if op == 'SELL':
                stock[item] = max(0, stock.get(item, 0) - q)
            elif op in ('BUY_PRODUCT', 'BUY_ANIMAL'):
                stock[item] = stock.get(item, 0) + q
        room = max(0, int(cfg.get('shedCapacity', 100)) - sum(stock.values()))
        quantity = min(due, room)
        inventory = obs['market']['inventory']['WHEAT']
        cost = sum(self.quote('WHEAT', inventory - 101 - k, obs['market'].get('params'))
                   for k in range(quantity))
        if not quantity or obs['farms'][obs['player']]['money'] < cost + 1000:
            return out
        out = deepcopy(out)
        out.setdefault('market', []).append(['BUY_PRODUCT', 'WHEAT', quantity])
        self.report.update(replacement_wheat=quantity, replacement_due=due,
                           replacement_slot=len(out['market']) - 1,
                           replacement_stock_before=stock.get('WHEAT', 0))
        return out

    def commit(self, obs, returned):
        super().commit(obs, returned)
        quantity = self.report.get('replacement_wheat', 0)
        slot = self.report.get('replacement_slot')
        if (quantity and slot is not None and returned.get('market', [])[slot:slot + 1]
                == [['BUY_PRODUCT', 'WHEAT', quantity]]):
            self.purchase = {'step': int(obs['step']), 'quantity': quantity,
                             'stock_before': self.report['replacement_stock_before']}

