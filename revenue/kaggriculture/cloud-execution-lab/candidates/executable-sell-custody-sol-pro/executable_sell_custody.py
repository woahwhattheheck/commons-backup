# SPDX-License-Identifier: Apache-2.0
"""Bind TITAN's seller transform to the official executable market prefix.

The preserved engine normalizes ``maxMarketOrdersPerTurn`` to at least one and
executes only the first N market rows.  Exact current ``FrozenSelected.transform``
still lets later raw rows influence baseline quantities, future references,
cash/capacity projections, sale admission, materialization, and pending-stock
retirement.

This candidate installs one source-pinned subclass.  It runs the unchanged
transform against shallow, non-mutating views containing only the engine-
executable prefix, then reattaches the original engine-inactive suffix byte-for-
byte.  Every active-prefix row and every non-market action remains under the
unchanged current implementation.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
from pathlib import Path
from typing import Any

EXPECTED_FROZEN_SELECTED_GIT_BLOB = "fc7baf5c179818a55037f6a61d92984d81d1a21c"
EXPECTED_SCHEDULER_GIT_BLOB = "a483b24dd72b580d7d8811636b54d2d44f391575"
_MARKER = "_sol_pro_executable_sell_custody_v1"


def git_blob_sha1(path: str | Path) -> str:
    """Return Git's SHA-1 object id for one regular file."""
    data = Path(path).read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def executable_limit(config: Any) -> int:
    """Match the official engine's schema floor and queue-slice boundary."""
    cfg = dict(config or {})
    return max(1, int(cfg.get("maxMarketOrdersPerTurn", 10)))


def executable_market_view(action: Any, limit: int) -> Any:
    """Shallow-copy one action and hide only its engine-inactive market suffix."""
    if not isinstance(action, dict):
        raise RuntimeError("seller action must be a mapping")
    market = action.get("market", [])
    if not isinstance(market, list):
        raise RuntimeError("seller market queue must be a list")
    viewed = dict(action)
    viewed["market"] = list(market[:limit])
    return viewed


def controller_view(controller: Any, limit: int) -> Any:
    """Copy the represented controller while truncating only the selected route."""
    routes = copy.copy(controller.R)
    current = controller.cur
    try:
        route = controller.R[current]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("selected controller route is unavailable") from exc
    if not isinstance(route, list):
        raise RuntimeError("selected controller route must be a list")
    routes[current] = [executable_market_view(action, limit) for action in route]
    viewed = copy.copy(controller)
    viewed.R = routes
    viewed.cur = current
    return viewed


def reattach_inert_suffix(original: Any, transformed: Any, limit: int) -> dict[str, Any]:
    """Restore the untouched suffix without moving its row indexes."""
    if not isinstance(original, dict) or not isinstance(transformed, dict):
        raise RuntimeError("seller transform must consume and return mappings")
    before = original.get("market", [])
    after = transformed.get("market", [])
    if not isinstance(before, list) or not isinstance(after, list):
        raise RuntimeError("seller market queue must remain a list")
    if len(after) > limit:
        raise RuntimeError("seller transform escaped the executable market prefix")
    if len(before) >= limit and len(after) != limit:
        raise RuntimeError("seller transform changed executable-prefix cardinality")
    merged = copy.deepcopy(transformed)
    merged["market"] = copy.deepcopy(after) + copy.deepcopy(before[limit:])
    return merged


def install(
    frozen_selected_module: Any,
    *,
    expected_frozen_blob: str = EXPECTED_FROZEN_SELECTED_GIT_BLOB,
    expected_scheduler_blob: str = EXPECTED_SCHEDULER_GIT_BLOB,
) -> dict[str, Any]:
    """Install the executable-prefix custody subclass exactly once."""
    base = getattr(frozen_selected_module, "FrozenSelected")
    prior = getattr(base, _MARKER, None)
    if prior is not None:
        if (
            prior.get("frozen_selected_git_blob") != expected_frozen_blob
            or prior.get("scheduler_git_blob") != expected_scheduler_blob
        ):
            raise RuntimeError("sell-custody patch already installed for different source bytes")
        return {**prior, "installed": False, "idempotent": True}

    frozen_path = Path(getattr(frozen_selected_module, "__file__", "")).resolve()
    if not frozen_path.is_file() or frozen_path.is_symlink():
        raise RuntimeError("frozen_selected source path is unavailable")
    actual_frozen_blob = git_blob_sha1(frozen_path)
    if actual_frozen_blob != expected_frozen_blob:
        raise RuntimeError(
            "frozen_selected source drift: "
            f"expected {expected_frozen_blob}, got {actual_frozen_blob}"
        )

    original_transform = getattr(base, "transform")
    scheduler_source = inspect.getsourcefile(getattr(base, "cash_reserve"))
    if not scheduler_source:
        raise RuntimeError("scheduler source path is unavailable")
    scheduler_path = Path(scheduler_source).resolve()
    actual_scheduler_blob = git_blob_sha1(scheduler_path)
    if actual_scheduler_blob != expected_scheduler_blob:
        raise RuntimeError(
            "scheduler source drift: "
            f"expected {expected_scheduler_blob}, got {actual_scheduler_blob}"
        )

    class ExecutableSellCustodyFrozenSelected(base):
        """Exact current selected seller with inert queue suffixes quarantined."""

        def transform(self, obs, config, selected):
            limit = executable_limit(config)
            selected_view = executable_market_view(selected, limit)
            original_controller = self.controller
            self.controller = controller_view(original_controller, limit)
            try:
                config_view = dict(config or {})
                config_view["maxMarketOrdersPerTurn"] = limit
                transformed = original_transform(self, obs, config_view, selected_view)
            finally:
                self.controller = original_controller

            result = reattach_inert_suffix(selected, transformed, limit)
            diagnostics = getattr(self, "diagnostics", None)
            if isinstance(diagnostics, dict):
                original_market = selected.get("market", [])
                diagnostics["executable_sell_custody"] = {
                    "limit": limit,
                    "represented_rows": len(original_market),
                    "executed_rows": min(limit, len(original_market)),
                    "inert_suffix_rows": max(0, len(original_market) - limit),
                    "suffix_preserved": True,
                }
            return result

    ExecutableSellCustodyFrozenSelected.__name__ = "ExecutableSellCustodyFrozenSelected"
    ExecutableSellCustodyFrozenSelected.__qualname__ = "ExecutableSellCustodyFrozenSelected"
    ExecutableSellCustodyFrozenSelected.__module__ = base.__module__
    receipt = {
        "installed": True,
        "idempotent": False,
        "target": "frozen_selected.FrozenSelected.transform",
        "factor": "engine-inactive market suffix quarantine",
        "frozen_selected_git_blob": actual_frozen_blob,
        "scheduler_git_blob": actual_scheduler_blob,
        "original": f"{original_transform.__module__}.{original_transform.__qualname__}",
        "replacement": (
            f"{ExecutableSellCustodyFrozenSelected.__module__}."
            f"{ExecutableSellCustodyFrozenSelected.__qualname__}"
        ),
    }
    setattr(ExecutableSellCustodyFrozenSelected, _MARKER, dict(receipt))
    frozen_selected_module.FrozenSelected = ExecutableSellCustodyFrozenSelected
    return receipt
