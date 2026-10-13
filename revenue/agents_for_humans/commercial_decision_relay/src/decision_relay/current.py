from __future__ import annotations

from typing import Any

from .core import DecisionRelayError, RelayEngine as HistoricalRelayEngine
from .core import reconcile as _reconcile_historical_primitive


def _trusted_time(evaluated_at: str | None) -> str:
    if evaluated_at is None:
        raise DecisionRelayError(
            "trusted_time_required",
            "current reconciliation requires caller-supplied trusted evaluated_at",
        )
    return evaluated_at


def reconcile_current(
    batch: dict[str, Any],
    *,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    """Reconcile current state only at an out-of-band caller-supplied instant."""
    return _reconcile_historical_primitive(
        batch,
        evaluated_at=_trusted_time(evaluated_at),
    )


def reconcile_historical(batch: dict[str, Any]) -> dict[str, Any]:
    """Explicit historical replay using the batch's authenticated snapshot instant."""
    return _reconcile_historical_primitive(batch)


class CurrentRelayEngine(HistoricalRelayEngine):
    """Production/user-facing engine whose reconciliation cannot choose snapshot time."""

    def reconcile(self, *, evaluated_at: str | None = None) -> dict[str, Any]:
        return super().reconcile(evaluated_at=_trusted_time(evaluated_at))
