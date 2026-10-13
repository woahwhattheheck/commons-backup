# SPDX-License-Identifier: Apache-2.0
"""Numeric features from the observation at an explicit routing checkpoint."""
from collections import Counter

PRODUCTS = ('WHEAT', 'CARROT', 'TOMATO', 'STRAWBERRY', 'MELON', 'EGG', 'MILK', 'WOOL', 'FERTILIZER')
SHOPS = ('BAKERY', 'PIZZA_SHOP', 'BRUNCH_SPOT', 'YARN_STORE', 'ICE_CREAM_SHOP', 'PET_CAFE', 'SMOOTHIE_SHOP', 'FARMERS_MARKET')


def extract(observation):
    """No configuration, seed, opponent label, terminal score or future rows."""
    obs = observation
    seat = int(obs['player'])
    own, rival = obs['farms'][seat], obs['farms'][1 - seat]
    market, private = obs.get('market', {}), obs.get('private', {})
    shops = Counter(obs.get('town', {}).get('unlocked_shops', []))
    features = {'seat': seat, 'shop_count': sum(shops.values())}
    for shop in SHOPS:
        features['shop_' + shop] = shops[shop]
    for product in PRODUCTS:
        for label, values in [('price', market.get('prices', {})), ('inventory', market.get('inventory', {})),
                              ('shed', private.get('shed', {}))]:
            value = values.get(product)
            features[label + '_' + product] = float(value) if isinstance(value, (int, float)) else None
    for label, farm in [('own', own), ('rival', rival)]:
        features[label + '_money'] = float(farm['money'])
        features[label + '_hands'] = len(farm.get('hands', []))
        features[label + '_land'] = len(farm.get('unlocked_quadrants', []))
        tiles = [t for row in farm.get('tiles', []) for t in row if isinstance(t, dict)]
        for product in PRODUCTS:
            selected = [t for t in tiles if t.get('crop') == product]
            features[label + '_crop_' + product] = len(selected)
            features[label + '_held_' + product] = sum(t.get('yield_units', 0) for t in selected)
        for animal in ('GOOSE', 'COW', 'SHEEP'):
            selected = [t for t in tiles if t.get('animal') == animal]
            features[label + '_' + animal] = len(selected)
            features[label + '_held_' + animal] = sum(t.get('yield_units', 0) for t in selected)
    return features


def predict(tree, features):
    """A deterministic small tree; missing values follow the frozen missing arm."""
    while 'feature' in tree:
        value = features.get(tree['feature'])
        key = tree.get('missing', 'left') if value is None else ('left' if value <= tree['threshold'] else 'right')
        tree = tree[key]
    return tree['policy']
