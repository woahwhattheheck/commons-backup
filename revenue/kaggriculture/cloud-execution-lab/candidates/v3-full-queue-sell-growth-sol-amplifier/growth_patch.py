# SPDX-License-Identifier: Apache-2.0
"""One-factor full-queue same-product SELL expansion for TITAN's frozen seller.

The selected seller already owns a positive SELL row for the product.  At the
raw queue limit, increasing that row consumes no additional position.  Current
V3 nevertheless rejects quantities above the inherited total and its emitter
caps every inherited row to its original quantity.  This module changes those
two halves together while preserving the exact selected ``transform`` code
object and all unrelated module globals.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import builtins as _builtins
import copy
import functools
import types
from typing import Any, Callable, Mapping, Sequence

_OPERATION = "titan-v3-full-queue-same-product-sell-growth-20260909-sol-amplifier-01"
_CLASS_MARKER = "_sol_amplifier_full_queue_sell_growth"
_INSTANCE_MARKER = "_sol_amplifier_full_queue_sell_growth_attachment"


class _TraceState:
    """Per-transform activation receipt without cross-thread/global leakage."""

    def __init__(self) -> None:
        self._current: ContextVar[dict[str, Any] | None] = ContextVar(
            "sol_amplifier_full_queue_growth_trace", default=None
        )

    @contextmanager
    def capture(self):
        receipt: dict[str, Any] = {
            "operation": _OPERATION,
            "planner_relaxations": 0,
            "emitter_expansions": 0,
            "extra_units_materialized": 0,
            "examples": [],
        }
        token = self._current.set(receipt)
        try:
            yield receipt
        finally:
            self._current.reset(token)

    def record(self, kind: str, **event: Any) -> None:
        receipt = self._current.get()
        if receipt is None:
            return
        if kind == "planner":
            receipt["planner_relaxations"] += 1
        elif kind == "emitter":
            receipt["emitter_expansions"] += 1
            receipt["extra_units_materialized"] += max(
                0, int(event.get("extra_units", 0))
            )
        else:
            raise ValueError(f"unknown activation kind: {kind}")
        if len(receipt["examples"]) < 8:
            receipt["examples"].append({"kind": kind, **event})


def _positive_sell_quantity(row: Any, item: str) -> int:
    if not row or len(row) <= 2 or row[0] != "SELL" or row[1] != item:
        return 0
    try:
        return max(0, int(row[2]))
    except (TypeError, ValueError):
        return 0


def _closure_values(function: Callable[..., Any]) -> dict[str, Any] | None:
    """Read the exact nested-feasible closure; return None on source drift."""
    code = getattr(function, "__code__", None)
    cells = getattr(function, "__closure__", None) or ()
    if code is None or len(code.co_freevars) != len(cells):
        return None
    values: dict[str, Any] = {}
    try:
        for name, cell in zip(code.co_freevars, cells):
            values[name] = cell.cell_contents
    except ValueError:
        return None
    required = {"base", "config", "item", "now", "receipt_feasible", "route"}
    if not required.issubset(values):
        return None
    if not callable(values["receipt_feasible"]):
        return None
    if not isinstance(values["base"], Mapping):
        return None
    if not isinstance(values["config"], Mapping):
        return None
    if not isinstance(values["item"], str):
        return None
    return values


def _orders_at(context: Mapping[str, Any], step: int) -> Sequence[Any]:
    if step == int(context["now"]):
        orders = context["base"].get("market", [])
        return orders if isinstance(orders, Sequence) else ()
    route = context["route"]
    try:
        action = route[step] if 0 <= step < len(route) else {}
    except (TypeError, IndexError):
        return ()
    if not isinstance(action, Mapping):
        return ()
    orders = action.get("market", [])
    return orders if isinstance(orders, Sequence) else ()


def _build_optimizer(
    original: Callable[..., Any], state: _TraceState
) -> Callable[..., Any]:
    """Relax only the saturated existing-row constraint in capacity_ok."""

    @functools.wraps(original)
    def optimize_lot(*args: Any, **kwargs: Any):
        canonical_capacity = kwargs.get("capacity_ok")
        requested_item = kwargs.get("item")
        if not callable(canonical_capacity) or not isinstance(requested_item, str):
            return original(*args, **kwargs)
        context = _closure_values(canonical_capacity)
        if context is None or context["item"] != requested_item:
            return original(*args, **kwargs)
        limit = int(context["config"].get("maxMarketOrdersPerTurn", 10))
        if limit <= 0:
            return original(*args, **kwargs)
        receipt_feasible = context["receipt_feasible"]

        @functools.wraps(canonical_capacity)
        def growth_capacity(plan: Sequence[Sequence[Any]]) -> bool:
            if canonical_capacity(plan):
                return True
            relaxed_rows: list[dict[str, int]] = []
            for pair in plan:
                if len(pair) < 2:
                    return False
                step, raw_quantity = int(pair[0]), int(pair[1])
                if raw_quantity <= 0:
                    continue
                orders = _orders_at(context, step)
                if len(orders) < limit:
                    # The inherited callback could only have failed its receipt
                    # predicate here; this one-factor patch cannot overturn it.
                    continue
                offered = sum(
                    _positive_sell_quantity(row, requested_item) for row in orders
                )
                if raw_quantity <= offered:
                    continue
                # More-than-limit queues involve inactive suffix ownership and
                # later queue transforms; do not broaden this exact-10-row seam.
                if len(orders) != limit or offered <= 0:
                    return False
                relaxed_rows.append(
                    {
                        "step": step,
                        "requested": raw_quantity,
                        "inherited": offered,
                        "extra": raw_quantity - offered,
                    }
                )
            if not relaxed_rows or not receipt_feasible(plan):
                return False
            state.record(
                "planner",
                item=requested_item,
                rows=relaxed_rows,
                max_orders=limit,
            )
            return True

        changed = dict(kwargs)
        changed["capacity_ok"] = growth_capacity
        return original(*args, **changed)

    return optimize_lot


def _build_materializer(
    original: Callable[..., Any], state: _TraceState
) -> Callable[..., Any]:
    """Add selected excess to the first positive same-product row in place."""

    @functools.wraps(original)
    def materialize_sales(
        orders: Sequence[Any],
        current: Mapping[str, Any],
        shed: Mapping[str, Any],
        targets: Mapping[str, Any] | Sequence[str] | set[str],
        max_orders: int,
    ):
        limit = int(max_orders)
        if limit <= 0 or len(orders) != limit:
            return original(orders, current, shed, targets, max_orders)
        adjusted: list[Any] | None = None
        pending_events: list[dict[str, int | str]] = []
        for item in sorted(targets):
            desired = min(
                max(0, int(current.get(item, 0))),
                max(0, int(shed.get(item, 0))),
            )
            matches = [
                index
                for index, row in enumerate(orders)
                if _positive_sell_quantity(row, item) > 0
            ]
            inherited = sum(
                _positive_sell_quantity(orders[index], item) for index in matches
            )
            if not matches or desired <= inherited:
                continue
            extra = desired - inherited
            if adjusted is None:
                adjusted = copy.deepcopy(list(orders))
            index = matches[0]
            row = list(adjusted[index])
            row[2] = max(0, int(row[2])) + extra
            adjusted[index] = row
            pending_events.append(
                {
                    "item": item,
                    "index": index,
                    "inherited": inherited,
                    "desired": desired,
                    "extra_units": extra,
                    "max_orders": limit,
                }
            )
        if adjusted is None:
            return original(orders, current, shed, targets, max_orders)
        result = original(adjusted, current, shed, targets, max_orders)
        for event in pending_events:
            item = str(event["item"])
            emitted = sum(
                _positive_sell_quantity(row, item) for row in result
            )
            canonical_cap = min(
                int(event["inherited"]),
                int(event["desired"]),
                max(0, int(shed.get(item, 0))),
            )
            extra = max(0, emitted - canonical_cap)
            if extra:
                state.record("emitter", **{**event, "extra_units": extra})
        return result

    return materialize_sales


def _clone_function(
    function: types.FunctionType, globals_patch: Mapping[str, Any]
) -> types.FunctionType:
    namespace = dict(function.__globals__)
    namespace.update(globals_patch)
    clone = types.FunctionType(
        function.__code__,
        namespace,
        name=function.__name__,
        argdefs=function.__defaults__,
        closure=function.__closure__,
    )
    clone.__kwdefaults__ = function.__kwdefaults__
    clone.__annotations__ = dict(getattr(function, "__annotations__", {}))
    clone.__dict__.update(getattr(function, "__dict__", {}))
    clone.__doc__ = function.__doc__
    clone.__module__ = function.__module__
    clone.__qualname__ = function.__qualname__
    return clone


def build_frozen_selected(frozen_selected_module: Any):
    """Build an isolated subclass using the canonical transform code object."""
    base = getattr(frozen_selected_module, "FrozenSelected")
    prior = getattr(base, _CLASS_MARKER, None)
    if prior is not None:
        return base, dict(prior)
    base_transform = getattr(base, "transform")
    if not isinstance(base_transform, types.FunctionType):
        raise TypeError("FrozenSelected.transform must be a Python function")
    state = _TraceState()
    private_transform = _clone_function(
        base_transform,
        {
            "optimize_lot": _build_optimizer(
                getattr(frozen_selected_module, "optimize_lot"), state
            ),
            "materialize_sales": _build_materializer(
                getattr(frozen_selected_module, "materialize_sales"), state
            ),
        },
    )

    def transform(self, obs, config, selected):
        with state.capture() as activation:
            result = private_transform(self, obs, config, selected)
        if activation["planner_relaxations"] or activation["emitter_expansions"]:
            diagnostics = dict(getattr(self, "diagnostics", {}) or {})
            diagnostics["full_queue_same_product_sell_growth"] = activation
            self.diagnostics = diagnostics
        return result

    class GrowthFrozenSelected(base):
        pass

    GrowthFrozenSelected.transform = transform
    GrowthFrozenSelected.__name__ = "GrowthFrozenSelected"
    GrowthFrozenSelected.__qualname__ = "GrowthFrozenSelected"
    GrowthFrozenSelected.__module__ = base.__module__
    receipt = {
        "operation": _OPERATION,
        "target": "frozen_selected.FrozenSelected.transform",
        "canonical_code_object_reused": private_transform.__code__ is base_transform.__code__,
        "private_globals": ["materialize_sales", "optimize_lot"],
        "base": f"{base.__module__}.{base.__qualname__}",
        "replacement": (
            f"{GrowthFrozenSelected.__module__}."
            f"{GrowthFrozenSelected.__qualname__}"
        ),
        "global_class_mutation_persistent": False,
    }
    setattr(GrowthFrozenSelected, _CLASS_MARKER, dict(receipt))
    setattr(GrowthFrozenSelected, "_sol_amplifier_private_transform", private_transform)
    setattr(GrowthFrozenSelected, "_sol_amplifier_trace_state", state)
    return GrowthFrozenSelected, receipt


def _private_import_builtins(
    function: types.FunctionType, frozen_selected_module: Any, growth: type
) -> tuple[dict[str, Any], types.ModuleType]:
    """Return builtins whose sole import override is ``frozen_selected``.

    ``TitanAgent._initialize`` performs ``from frozen_selected import
    FrozenSelected``.  A function-local builtins table lets the exact canonical
    code object resolve a private module view without changing ``sys.modules``
    or the canonical module's class binding, even transiently.
    """
    source = function.__globals__.get("__builtins__", _builtins.__dict__)
    if isinstance(source, types.ModuleType):
        private_builtins = dict(vars(source))
    elif isinstance(source, Mapping):
        private_builtins = dict(source)
    else:
        raise TypeError("canonical initialize builtins must be a module or mapping")
    delegate = private_builtins.get("__import__")
    if not callable(delegate):
        raise TypeError("canonical initialize has no callable __import__")
    view = types.ModuleType("_sol_amplifier_frozen_selected_view")
    view.__dict__.update(vars(frozen_selected_module))
    view.FrozenSelected = growth

    def isolated_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and name == "frozen_selected":
            return view
        return delegate(name, globals, locals, fromlist, level)

    private_builtins["__import__"] = isolated_import
    return private_builtins, view


def attach(instance: Any, frozen_selected_module: Any) -> dict[str, Any]:
    """Give one instance a private exact-code lazy initializer and seller."""
    prior = getattr(instance, _INSTANCE_MARKER, None)
    if prior is not None:
        return {**dict(prior), "attached": False, "idempotent": True}
    base = getattr(frozen_selected_module, "FrozenSelected")
    growth, class_receipt = build_frozen_selected(frozen_selected_module)
    original_initialize = instance._initialize
    function = getattr(original_initialize, "__func__", None)
    if not isinstance(function, types.FunctionType):
        raise TypeError("instance._initialize must be a bound Python method")
    private_builtins, view = _private_import_builtins(
        function, frozen_selected_module, growth
    )
    private_initialize = _clone_function(
        function, {"__builtins__": private_builtins}
    )
    instance._initialize = types.MethodType(private_initialize, instance)
    receipt = {
        **class_receipt,
        "attached": True,
        "idempotent": False,
        "canonical_initialize_code_object_reused": (
            private_initialize.__code__ is function.__code__
        ),
        "private_import_view": view.__name__,
        "module_class_binding_mutated": False,
        "sys_modules_mutated": False,
    }
    setattr(instance, _INSTANCE_MARKER, dict(receipt))
    return receipt
