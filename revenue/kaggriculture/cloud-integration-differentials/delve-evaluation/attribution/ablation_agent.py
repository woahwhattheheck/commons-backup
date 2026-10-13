"""Targeted development interventions, not a general or promoted policy.

The existing funded agent and its rival stay responsive. Only two named market
decisions may change, after exactly one ordinary producer decision.
"""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import sys
import time

_INSTANCE = None
_ARM = None


def intervene(action: dict, step: int, arm: str, maximum: int = 10) -> tuple[dict, dict]:
    """Preserve current slots and all worker actions; report conditional activation."""
    if arm not in ("control", "suppress360", "due381", "joint"):
        raise ValueError("Unknown development treatment")
    out = copy.deepcopy(action)
    report = {"applied": False, "step": step, "arm": arm}
    orders = out.get("market", [])
    if step == 360 and arm in ("suppress360", "joint"):
        if orders and orders[0] == ["SELL", "MILK", 3]:
            orders[0] = []
            report.update(applied=True, operation="withhold_selected_milk3", slot=0)
        else:
            report["reason"] = "selected_current_queue_differs"
    if step == 381 and arm in ("due381", "joint"):
        if len(orders) < maximum:
            out.setdefault("market", []).append(["SELL", "MILK", 2])
            report.update(applied=True, operation="request_milk2", slot=len(out["market"])-1)
        else:
            report["reason"] = "no_remaining_market_slot"
    return out, report


def call(arm: str, observation: dict, configuration: dict | None = None) -> dict:
    global _INSTANCE, _ARM
    cfg = dict(configuration or {})
    initialization = None
    if _INSTANCE is None:
        t0 = time.perf_counter()
        setup = json.loads(Path(__file__).with_name("responsive-setup.json").read_text())
        root = Path(setup["package"])
        entry = root / "runtime/revenue/kaggriculture/cloud-integration-differentials/funded_main.py"
        sys.path.insert(0, str(entry.parent))
        spec = importlib.util.spec_from_file_location("delve_attr_funded", entry)
        if spec is None or spec.loader is None:
            raise ImportError(str(entry))
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _INSTANCE = module.make_agent(funded=True)
        _ARM = arm
        initialization = time.perf_counter() - t0
    if _ARM != arm:
        raise RuntimeError("Use a fresh actor process for every treatment")
    t0 = time.perf_counter()
    base = _INSTANCE.act(observation, cfg)
    elapsed = time.perf_counter() - t0
    step = observation["step"]
    out, change = intervene(base, step, arm, int(cfg.get("maxMarketOrdersPerTurn", 10)))
    record = {"arm": arm, "step": step, "base_action": base, "action": out,
              "intervention": change, "diagnostics": _INSTANCE.diagnostics,
              "decision_seconds": elapsed, "initialization_seconds": initialization}
    setup = json.loads(Path(__file__).with_name("responsive-setup.json").read_text())
    with open(setup["telemetry"], "a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    return out


def suppress360(obs, cfg=None):
    return call("suppress360", obs, cfg)


def due381(obs, cfg=None):
    return call("due381", obs, cfg)


def joint(obs, cfg=None):
    return call("joint", obs, cfg)
