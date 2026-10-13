# SPDX-License-Identifier: Apache-2.0
"""Conditional exact quotes for T11/T12 scenario composition; no forecasting.

These quantities describe a scenario, never unseen orders supplied to an agent.
No probability is assigned. Both players fill their stated quantities in slot0;
ours sells q then rebuys q in slot1, rival has no later action in this product.
Cash, capacity, operating inventory and other orders remain caller constraints.
"""
from market_math import market_price


def sell_rebuy_quote(item, inventory, quantity, rival_quantity, *, rival_direction='SELL', params=None):
    q,r=quantity,rival_quantity
    if item not in ('WHEAT','FERTILIZER') or any(type(v) is not int or v<0 for v in (q,r)):
        raise ValueError('Require a purchasable product and nonnegative integer quantities')
    if rival_direction not in ('SELL','BUY_PRODUCT'):
        raise ValueError('Require SELL or BUY_PRODUCT scenario')
    sign=1 if rival_direction=='SELL' else -1
    p=lambda stock:market_price(item,stock,params)
    our_sale=[p(inventory+j+sign*min(j,r)) for j in range(q)]
    our_buy=[p(inventory+q+sign*r-j-1) for j in range(q)]
    if sign==1:
        rival_actual=[p(inventory+j+min(j,q)) for j in range(r)]
        rival_control=[p(inventory+j) for j in range(r)]
    else:
        rival_actual=[p(inventory-j+min(j,q)-1) for j in range(r)]
        rival_control=[p(inventory-j-1) for j in range(r)]
    # The inventory-sum identity requires admission of every sale.
    sale_prices=our_sale+(rival_actual+rival_control if sign==1 else [])
    if any(price<=1 for price in sale_prices):
        raise ValueError('Use official paired transitions at the sale-admission floor')
    own=sum(our_sale)-sum(our_buy)
    rival=sign*(sum(rival_actual)-sum(rival_control))
    return {'own_cash_delta':own,'rival_cash_delta':rival,'margin_delta':own-rival,
            'own_sale_receipts':our_sale,'own_buy_costs':our_buy,
            'rival_actual_quotes':rival_actual,'rival_control_quotes':rival_control,
            'final_inventory':inventory+sign*r,'probability':None,
            'conditions':'Full fills, no floor-priced sale, no later rival same-product action; operating reservations remain separate.'}
