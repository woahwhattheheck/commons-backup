# SPDX-License-Identifier: Apache-2.0
"""TITAN L02 candidate entrypoint: one canonical producer plus one selected overlay."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]


def _install_isolated_source_roots(lab: Path) -> list[str]:
    """Make archive-mapped root modules importable in stripped official workers.

    Official evaluator workers insert only the agent parent. Root modules that
    ``build_integrated.source_files`` maps from outside the lab
    (``observed_clone``, ``seller_snapshot``, …) must be on ``sys.path`` before
    canonical ``main`` loads. Complements the panel evaluator PYTHONPATH forward.
    """
    lab = lab.resolve()
    if str(lab) not in sys.path:
        sys.path.insert(0, str(lab))
    from build_integrated import source_files
    ordered = [str(lab)]
    seen = {lab}
    for member, source in source_files().items():
        if Path(member).parent != Path("."):
            continue
        origin = (lab / source).resolve()
        if not origin.is_file():
            raise FileNotFoundError(
                f"mapped root module {member} missing at {origin}")
        parent = origin.parent
        if parent not in seen:
            seen.add(parent)
            ordered.append(str(parent))
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
    return ordered


if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
_install_isolated_source_roots(LAB)

from ledger_tranche import install


def _load_canonical():
    spec = importlib.util.spec_from_file_location("_l02_canonical_entry", LAB / "main.py")
    if spec is None or spec.loader is None:
        raise ImportError("cannot load canonical TITAN entrypoint")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CANONICAL = _load_canonical()
_INSTANCE = None


def agent(observation, configuration=None):
    """Construct exactly one configured TitanAgent and install L02 before first act."""
    global _INSTANCE
    entry_started = time.perf_counter()
    cfg = dict(configuration or {})
    step = observation.get("step")
    if step is None:
        step = (int(observation["day"]) * int(cfg.get("turnsPerDay", 24))
                + int(observation["hour"]))
    if _INSTANCE is None or int(step) == 0:
        feature_data = json.loads((LAB / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        _INSTANCE = _CANONICAL._new_instance(LAB, feature_data)
        install(_INSTANCE)
    return _INSTANCE.act(observation, cfg, entry_started=entry_started)
