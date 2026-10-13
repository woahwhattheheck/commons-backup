# SPDX-License-Identifier: Apache-2.0
"""Strict public facade for the TITAN P11 service-calendar certificate.

The original scheduler implementation is preserved byte-for-byte in
``_service_calendar_core.py``.  This facade closes a schema/parser mismatch:
the published JSON schema forbids unknown fields in state, obligation, and
reservation objects, while the original ``from_dict`` methods silently ignored
them.  Silent omission is unsafe for an admission certificate because a typo in
an economic or resource field can erase a constraint and turn a malformed route
into an admitted one.

Known-field behavior and all public names remain unchanged.  Only malformed
nested mappings now fail closed with ``CalendarInputError``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import _service_calendar_core as _core
from _service_calendar_core import *  # noqa: F401,F403


_RESERVATION_FIELDS = frozenset({"turn", "resource", "units"})
_STATE_FIELDS = frozenset(
    {
        "current_turn",
        "terminal_turn",
        "cash",
        "inventory",
        "room_used",
        "room_capacity",
        "actor_capacity",
        "machine_capacity",
        "actor_reservations",
        "machine_reservations",
        "completed",
        "phase_order",
    }
)
_OBLIGATION_FIELDS = frozenset(
    {
        "key",
        "kind",
        "earliest_turn",
        "latest_turn",
        "phase",
        "depends_on",
        "actor_demand",
        "machine_demand",
        "cash_delta",
        "inventory_delta",
        "room_delta",
        "settlement_lag",
    }
)


def _reject_unknown(value: Any, allowed: frozenset[str], name: str) -> None:
    """Reject extra mapping keys before the core parser can ignore them."""

    if not isinstance(value, Mapping):
        return  # Preserve the core parser's existing type-specific error.
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise CalendarInputError(f"{name} contains unknown fields: {', '.join(unknown)}")


# Patching the shared class objects keeps every public path strict, including
# direct ``Class.from_dict`` calls and the core module's internal adapters.  The
# marker makes importlib reloads idempotent instead of stacking wrappers.
if not getattr(_core, "_STRICT_NESTED_FIELDS_INSTALLED", False):
    _reservation_from_dict = Reservation.from_dict
    _state_from_dict = CalendarState.from_dict
    _obligation_from_dict = Obligation.from_dict

    def _strict_reservation_from_dict(
        cls: type[Reservation], value: Mapping[str, Any], name: str
    ) -> Reservation:
        _reject_unknown(value, _RESERVATION_FIELDS, name)
        return _reservation_from_dict(value, name)

    def _strict_state_from_dict(
        cls: type[CalendarState], value: Mapping[str, Any]
    ) -> CalendarState:
        _reject_unknown(value, _STATE_FIELDS, "state")
        return _state_from_dict(value)

    def _strict_obligation_from_dict(
        cls: type[Obligation], value: Mapping[str, Any], index: int = 0
    ) -> Obligation:
        _reject_unknown(value, _OBLIGATION_FIELDS, f"obligations[{index}]")
        return _obligation_from_dict(value, index)

    Reservation.from_dict = classmethod(_strict_reservation_from_dict)
    CalendarState.from_dict = classmethod(_strict_state_from_dict)
    Obligation.from_dict = classmethod(_strict_obligation_from_dict)
    _core._STRICT_NESTED_FIELDS_INSTALLED = True


__all__ = list(_core.__all__)
