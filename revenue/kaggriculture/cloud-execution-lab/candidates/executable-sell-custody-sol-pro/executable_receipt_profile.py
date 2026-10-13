# SPDX-License-Identifier: Apache-2.0
"""Candidate-local executable-prefix view for TITAN's receipt profile.

The canonical capacity callback is inherited from ``scheduler.SellScheduler``.
It projects every raw represented market row, while the preserved official
engine executes only the first ``maxMarketOrdersPerTurn`` rows.  This module
installs a subclass of the exact current ``frozen_selected.FrozenSelected`` and
feeds the unchanged inherited callback shallow, non-mutating action views whose
market queues are truncated to that same executable prefix.

No active-prefix order, quantity, affordability, capacity, price, optimizer,
emitter, or seller-ledger rule is changed here.  The deliberately narrow factor
is only whether engine-inactive suffix rows are allowed to affect the capacity
projection.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any

EXPECTED_FROZEN_SELECTED_GIT_BLOB = "fc7baf5c179818a55037f6a61d92984d81d1a21c"
EXPECTED_SCHEDULER_GIT_BLOB = "a483b24dd72b580d7d8811636b54d2d44f391575"
_MARKER = "_sol_quoin_executable_receipt_profile_v1"


def git_blob_sha1(path: str | Path) -> str:
    """Return Git's SHA-1 object id for one regular file."""
    data = Path(path).read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def executable_market_prefix(action: Any, max_orders: int) -> Any:
    """Return a shallow action view with only the engine-executable market rows.

    Non-dict actions and non-list market payloads are preserved for the inherited
    callback to handle exactly as before.  Nested order rows are never mutated by
    that callback, so a list slice is enough to isolate the outer queue.
    """
    if not isinstance(action, dict):
        return action
    viewed = dict(action)
    market = action.get("market", [])
    if isinstance(market, list):
        viewed["market"] = list(market[:max_orders])
    return viewed


def _route_view(controller: Any, max_orders: int) -> Any:
    """Build the minimal controller view consumed by ``receipt_profile``."""
    routes = list(controller.R)
    cur = controller.cur
    route = controller.R[cur]
    routes[cur] = [executable_market_prefix(action, max_orders) for action in route]
    return SimpleNamespace(R=routes, cur=cur)


def install(
    frozen_selected_module: Any,
    *,
    expected_frozen_blob: str = EXPECTED_FROZEN_SELECTED_GIT_BLOB,
    expected_scheduler_blob: str = EXPECTED_SCHEDULER_GIT_BLOB,
) -> dict[str, Any]:
    """Install the one-factor receipt-profile subclass exactly once.

    Both the class call site and inherited method implementation are pinned by
    exact Git blob ids.  Drift fails before canonical TITAN construction.
    """
    base = getattr(frozen_selected_module, "FrozenSelected")
    prior = getattr(base, _MARKER, None)
    if prior is not None:
        if (
            prior.get("frozen_selected_git_blob") != expected_frozen_blob
            or prior.get("scheduler_git_blob") != expected_scheduler_blob
        ):
            raise RuntimeError("receipt-profile patch already installed for different source bytes")
        return {**prior, "installed": False, "idempotent": True}

    frozen_path = Path(getattr(frozen_selected_module, "__file__", "")).resolve()
    if not frozen_path.is_file():
        raise RuntimeError("frozen_selected source path is unavailable")
    actual_frozen_blob = git_blob_sha1(frozen_path)
    if actual_frozen_blob != expected_frozen_blob:
        raise RuntimeError(
            "frozen_selected source drift: "
            f"expected {expected_frozen_blob}, got {actual_frozen_blob}"
        )

    original = getattr(base, "receipt_profile")
    scheduler_source = inspect.getsourcefile(original)
    if not scheduler_source:
        raise RuntimeError("receipt_profile source path is unavailable")
    scheduler_path = Path(scheduler_source).resolve()
    actual_scheduler_blob = git_blob_sha1(scheduler_path)
    if actual_scheduler_blob != expected_scheduler_blob:
        raise RuntimeError(
            "scheduler source drift: "
            f"expected {expected_scheduler_blob}, got {actual_scheduler_blob}"
        )

    class ExecutableReceiptProfileFrozenSelected(base):
        """Exact FrozenSelected with inactive market suffixes hidden from capacity."""

        def receipt_profile(self, obs, selected, farm, private, end, item, config):
            cfg = dict(config or {})
            max_orders = max(1, int(cfg.get("maxMarketOrdersPerTurn", 10)))

            selected_view = executable_market_prefix(selected, max_orders)
            shadow = copy.copy(self)
            shadow.controller = _route_view(self.controller, max_orders)
            return original(
                shadow, obs, selected_view, farm, private, end, item, config
            )

    ExecutableReceiptProfileFrozenSelected.__name__ = (
        "ExecutableReceiptProfileFrozenSelected"
    )
    ExecutableReceiptProfileFrozenSelected.__qualname__ = (
        "ExecutableReceiptProfileFrozenSelected"
    )
    ExecutableReceiptProfileFrozenSelected.__module__ = base.__module__
    receipt = {
        "installed": True,
        "idempotent": False,
        "target": "frozen_selected.FrozenSelected.receipt_profile",
        "factor": "engine-inactive market suffix exclusion",
        "frozen_selected_git_blob": actual_frozen_blob,
        "scheduler_git_blob": actual_scheduler_blob,
        "original": f"{original.__module__}.{original.__qualname__}",
        "replacement": (
            f"{ExecutableReceiptProfileFrozenSelected.__module__}."
            f"{ExecutableReceiptProfileFrozenSelected.__qualname__}"
        ),
    }
    setattr(ExecutableReceiptProfileFrozenSelected, _MARKER, dict(receipt))
    frozen_selected_module.FrozenSelected = ExecutableReceiptProfileFrozenSelected
    return receipt
