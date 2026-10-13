# SPDX-License-Identifier: Apache-2.0
"""Canonical TITAN entrypoint. Feature choices are deterministic package data."""
_INSTANCE = None


def agent(observation, configuration=None):
    global _INSTANCE
    import time
    entry_started = time.perf_counter()
    from pathlib import Path
    import json
    import sys
    cfg = dict(configuration or {})
    path = globals().get('__file__') or cfg.get('__raw_path__')
    if not path:
        raise ValueError('Entrypoint path required')
    root = Path(path).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from titan_runtime import TitanAgent, Features
    step = observation.get('step')
    if step is None:
        step = int(observation['day'])*int(cfg.get('turnsPerDay', 24))+int(observation['hour'])
    if _INSTANCE is None or int(step) == 0:
        _INSTANCE = TitanAgent(Features(**json.loads((root/'TITAN-CONFIG.json').read_text())))
    action = _INSTANCE.act(observation, cfg, entry_started=entry_started)
    # Diagnostic causal arm only: buy the final quadrant at the retained
    # opportunity checkpoint. This is deliberately not the prospective policy.
    # Existing queue items execute first, and the cash buffer keeps another land
    # cost outside this one purchase for later input orders.
    farm = observation['farms'][int(observation['player'])]
    market = action.get('market', [])
    if (int(step) == 266 and len(farm.get('unlocked_quadrants', [])) == 3
            and float(farm.get('money', 0)) >= 8000
            and len(market) < int(cfg.get('maxMarketOrdersPerTurn', 10))
            and not any(order and order[0] == 'BUY_LAND' for order in market)):
        from copy import deepcopy
        action = deepcopy(action)
        action.setdefault('market', []).append(['BUY_LAND'])
    return action
