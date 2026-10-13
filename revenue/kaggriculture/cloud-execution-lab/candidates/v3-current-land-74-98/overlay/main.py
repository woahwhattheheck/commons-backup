# SPDX-License-Identifier: Apache-2.0
"""TITAN current archive entrypoint with the isolated land-74/98 overlay."""
_INSTANCE = None


def agent(observation, configuration=None):
    global _INSTANCE
    import json
    import sys
    import time
    from pathlib import Path

    entry_started = time.perf_counter()
    cfg = dict(configuration or {})
    path = globals().get("__file__") or cfg.get("__raw_path__")
    if not path:
        raise ValueError("Entrypoint path required")
    root = Path(path).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    step = observation.get("step")
    if step is None:
        step = int(observation["day"]) * int(cfg.get("turnsPerDay", 24)) + int(observation["hour"])
    if _INSTANCE is None or int(step) == 0:
        from canonical_main import _new_instance
        from land_overlay import wrap

        feature_data = json.loads((root / "TITAN-CONFIG.json").read_text())
        _INSTANCE = _new_instance(root, feature_data)
        wrap(_INSTANCE, max_orders=int(cfg.get("maxMarketOrdersPerTurn", 10)))
    return _INSTANCE.act(observation, cfg, entry_started=entry_started)
