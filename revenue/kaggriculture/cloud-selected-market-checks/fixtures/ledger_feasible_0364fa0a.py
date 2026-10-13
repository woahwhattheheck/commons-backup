# SPDX-License-Identifier: Apache-2.0
# Exact dedented ProjectionLedger.feasible from seller Git blob
# 0364fa0ab6c3f0d7cc93569efb14d3f5af66da72 (PR9964). Test reference only.
def feasible(self, item, plan):
    stock = dict(self.shed)
    farm = self.obs['farms'][int(self.obs['player'])]
    cash = int(farm['money'])
    hires = int(farm.get('hires_today', 0))
    land = len(farm.get('unlocked_quadrants', ['NW'])) - 1
    inv = dict(self.obs['market']['inventory'])
    params = self.obs['market'].get('params')
    tpd = int(self.config.get('turnsPerDay', 24))
    orders = dict(plan)
    def phase_ok(t, phase):
        for product, delta in self.events.get((t, phase), []):
            stock[product] = stock.get(product, 0) + delta
            # Worker transfers are ordered: a later withdrawal cannot
            # recover an earlier spill or fund an earlier pickup.
            if stock[product] < 0 or sum(stock.values()) > self.capacity:
                return False
        if any(q < self.stock_min.get(p, 0) for p, q in stock.items()):
            return False
        if any(stock.get(p, 0) < q for p, q in self.stock_min.items()):
            return False
        if sum(stock.values()) + self.pending_units(t, phase) > self.capacity:
            return False
        return cash >= self.cash_min.get((t, phase), 0)
    for t in range(self.now, self.end + 1):
        if t > self.now and t % tpd == 0:
            hires = 0
        if not phase_ok(t, 'before_market'):
            return False
        market = (copy.deepcopy(self.future.get(t, [])) if item is None else
                  self.market(t, item, orders.get(t, 0), stock.get(item, 0)))
        if market is None:
            return False
        for slot, order in enumerate(market[:self.max_orders]):
            if not order:
                continue
            op = order[0]
            if op == 'HIRE':
                cost = m._hire_cost(hires, int(self.config.get('farmHandCostMult', 1)))
                if cash < cost: return False
                cash -= cost; hires += 1
            elif op == 'BUY_LAND':
                if land < len(m.LAND_PRICES):
                    cost = m.LAND_PRICES[land]
                    if cash < cost: return False
                    cash -= cost; land += 1
            elif len(order) >= 3:
                product, q = order[1], max(0, _count(order[2]))
                if op == 'SELL':
                    sold = min(q, stock.get(product, 0))
                    stock[product] = stock.get(product, 0) - sold
                    # $1 per sold unit is a guaranteed operating-cash lower
                    # bound. Economic selection still uses exact scenario quotes.
                    cash += sold
                elif op in ('BUY_PRODUCT', 'BUY_SEED', 'BUY_ANIMAL'):
                    if op == 'BUY_PRODUCT':
                        if product not in ('WHEAT', 'FERTILIZER'): return False
                        cost = 0
                        for _ in range(q):
                            inv[product] -= 1
                            cost += m.market_price(product, inv[product], params)
                        bound = self.cost_bounds[(t, slot)]
                        if bound < cost:
                            return False
                        cost = bound
                    else:
                        catalog = m.CROPS if op == 'BUY_SEED' else m.ANIMALS
                        field = 'seed' if op == 'BUY_SEED' else 'cost'
                        if product not in catalog: return False
                        cost = q * catalog[product][field]
                    if cash < cost: return False
                    cash -= cost
                    if op != 'BUY_SEED':
                        stock[product] = stock.get(product, 0) + q
                        if sum(stock.values()) + self.pending_units(t, 'before_market') > self.capacity:
                            return False
        # Actual final EOD has no sale window and imposes no salvage claim.
        if t == self.last:
            return (all(stock.get(p, 0) >= q for p, q in self.stock_min.items())
                    and cash >= self.cash_min.get((t, 'after_market'), 0))
        if not phase_ok(t, 'after_market'):
            return False
        for product in inv:
            inv[product] -= absorption(product, t, self.obs.get('town', {}).get('unlocked_shops', []), self.config)
    return True
