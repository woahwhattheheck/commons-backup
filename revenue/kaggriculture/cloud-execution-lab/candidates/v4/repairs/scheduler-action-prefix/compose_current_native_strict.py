#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Strict list-only semantic successor for the current-native PREFIX composer.

This module deliberately has no filesystem materializer or production activation
surface. It consumes the already-authenticated current PREFIX composer, refuses
base-composer drift, then closes the remaining places where projection code could
coerce a tuple/other non-list ``market`` value into executable rows even though
the official interpreter normalizes every non-list market queue to ``[]``.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import types
from typing import Any


BASE_PATH = Path(__file__).with_name("compose_current_native.py")
BASE_COMPOSER_BLOBS = {
    "2d68fcda0d9433072735f718cdd420f19036c9e7": "prefix-current-native-hardened",
    "6f80447da0250ab120695ddc6871be1c9a3581ce": "prefix-current-native-custody-only",
}
STRICT_MARKER = "PREFIX_LIST_ONLY_STRICT = True"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _load_base(snapshot: bytes):
    """Execute exactly the authenticated byte snapshot; never reopen BASE_PATH."""
    module = types.ModuleType("_titan_prefix_current_base")
    module.__file__ = str(BASE_PATH)
    code = compile(snapshot.decode("utf-8"), str(BASE_PATH), "exec")
    exec(code, module.__dict__)
    return module


def _once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one occurrence, got {count}")
    return text.replace(old, new, 1)


def _exact_count(text: str, old: str, new: str, expected: int, label: str) -> str:
    count = text.count(old)
    if count != expected:
        raise ValueError(f"{label}: expected {expected} occurrences, got {count}")
    return text.replace(old, new)


def _patch_materialize(part: str) -> str:
    return _once(
        part,
        "    market=[];remaining=dict(current);available=dict(shed)\n",
        "    # Official interpreter: non-list market is an empty executable queue.\n"
        "    if not isinstance(orders,list):\n"
        "        return []\n"
        "    market=[];remaining=dict(current);available=dict(shed)\n",
        "materialize list-only gate",
    )


def _patch_sale_quantities(part: str) -> str:
    return _once(
        part,
        "    for o in orders:\n",
        "    for o in (orders if isinstance(orders,list) else []):\n",
        "sale quantities list-only gate",
    )


def _patch_market_prefix_state(part: str) -> str:
    return _once(
        part,
        "    stop=min(int(stop),len(orders)-1)\n"
        "    for index,order in enumerate(orders[:stop+1]):\n",
        "    queue=orders if isinstance(orders,list) else []\n"
        "    stop=min(int(stop),len(queue)-1)\n"
        "    for index,order in enumerate(queue[:stop+1]):\n",
        "market prefix state list-only gate",
    )


def _patch_fund_same_turn(part: str) -> str:
    return _once(
        part,
        "    original=copy.deepcopy(orders)\n",
        "    if not isinstance(orders,list):\n"
        "        return [],{'applied':False,'reason':'non-list-market'}\n"
        "    original=copy.deepcopy(orders)\n",
        "same-turn funding list-only gate",
    )


def _patch_funding_trace(part: str) -> str:
    old = (
        "        orders = current_market if t == now else "
        "(route[t].get('market', []) if t < len(route) else [])\n"
    )
    new = old + "        orders = orders if isinstance(orders,list) else []\n"
    return _exact_count(part, old, new, 2, "funding trace list-only gates")


def _patch_joint_resource(part: str) -> str:
    part = _once(
        part,
        "    def orders_at(t):\n"
        "        return base['market'] if t==now else route[t].get('market',[]) if t<len(route) else []\n",
        "    def orders_at(t):\n"
        "        rows=base['market'] if t==now else route[t].get('market',[]) if t<len(route) else []\n"
        "        return (rows if isinstance(rows,list) else [])[:max_orders]\n",
        "joint resource callback normalization",
    )
    return _once(
        part,
        "        for order in list(orders_at(t))[:max_orders]:\n",
        "        for order in orders_at(t):\n",
        "joint resource executable rows",
    )


def _patch_joint_queue(part: str) -> str:
    part = _once(
        part,
        "    max_orders=max(1,int(max_orders))\n"
        "    committed={p:list(rows) for p,rows in planned.items()}\n",
        "    max_orders=max(1,int(max_orders))\n"
        "    def executable_orders(step):\n"
        "        rows=orders_at(step)\n"
        "        return (rows if isinstance(rows,list) else [])[:max_orders]\n"
        "    committed={p:list(rows) for p,rows in planned.items()}\n",
        "joint queue normalized callback",
    )
    part = _once(
        part,
        "        raw=sale_quantities(list(orders_at(t))[:max_orders])\n",
        "        raw=sale_quantities(executable_orders(t))\n",
        "joint queue raw prefix",
    )
    part = _once(
        part,
        "        market=materialize_sales(orders_at(t),wanted,stock,targets,max_orders)\n",
        "        market=materialize_sales(executable_orders(t),wanted,stock,targets,max_orders)\n",
        "joint queue materializer input",
    )
    return _once(
        part,
        "    return shared_slot_ledger(all_plans,orders_at,max_orders)\n",
        "    return shared_slot_ledger(all_plans,executable_orders,max_orders)\n",
        "joint queue shared-slot callback",
    )


def _harden_frozen(source: str, base: Any) -> str:
    if STRICT_MARKER in source:
        raise ValueError("strict list-only PREFIX repair already applied")
    text = _once(
        source,
        "from selected_sell_core import optimize_lot, joint_plan_metrics, shared_slot_ledger\n",
        "from selected_sell_core import optimize_lot, joint_plan_metrics, shared_slot_ledger\n\n"
        + STRICT_MARKER + "\n",
        "strict marker",
    )
    text = base._patch_span(text, "materialize_sales", _patch_materialize)
    text = base._patch_span(text, "sale_quantities", _patch_sale_quantities)
    text = base._patch_span(text, "_market_prefix_state", _patch_market_prefix_state)
    text = base._patch_span(text, "fund_same_turn_acquisition", _patch_fund_same_turn)
    text = base._patch_span(text, "_funding_trace", _patch_funding_trace)
    text = base._patch_span(text, "joint_resource_bound", _patch_joint_resource)
    text = base._patch_span(text, "joint_queue_ledger", _patch_joint_queue)

    forbidden = (
        "for order in list(orders_at(t))[:max_orders]:",
        "sale_quantities(list(orders_at(t))[:max_orders])",
        "shared_slot_ledger(all_plans,orders_at,max_orders)",
    )
    present = [pattern for pattern in forbidden if pattern in text]
    if present:
        raise ValueError("strict list-only PREFIX left coercing consumers: " + repr(present))
    if text.count("orders = orders if isinstance(orders,list) else []") != 2:
        raise ValueError("strict funding trace normalization count mismatch")
    compile(text, "<frozen-prefix-current-strict>", "exec")
    return text


def compose_pair(scheduler: bytes, frozen: bytes):
    base_snapshot = BASE_PATH.read_bytes()
    base_blob = git_blob(base_snapshot)
    profile = BASE_COMPOSER_BLOBS.get(base_blob)
    if profile is None:
        raise ValueError(
            "current PREFIX base composer drift: expected reviewed blob, got " + base_blob
        )
    base = _load_base(base_snapshot)
    scheduler_out, frozen_base, receipt = base.compose_pair(scheduler, frozen)
    frozen_out = _harden_frozen(frozen_base.decode("utf-8"), base).encode("utf-8")

    strict_receipt = dict(receipt)
    strict_receipt["schema"] = "titan-v4-scheduler-prefix-current/v2-list-only-strict"
    strict_receipt["base_composer"] = {
        "profile": profile,
        "git_blob": base_blob,
    }
    strict_receipt["frozen_selected"] = dict(receipt["frozen_selected"])
    strict_receipt["frozen_selected"]["base_after_git_blob"] = git_blob(frozen_base)
    strict_receipt["frozen_selected"]["after_git_blob"] = git_blob(frozen_out)
    strict_receipt["frozen_selected"]["after_sha256"] = hashlib.sha256(frozen_out).hexdigest()
    strict_receipt["list_only_market_normalization"] = True
    strict_receipt["production_activation"] = False
    strict_receipt["graph_registration"] = False
    return scheduler_out, frozen_out, strict_receipt
