"""Host-neutral Commons peer wake bus.

Peers add their own adapter and durable wake target. There is no central
admission list and no auth/account door. Unique events are accepted and
never cancelled. Cheap ticks never invoke a model. Live ChatGPT/Claude
doorbells stay EXTERNAL_PLATFORM_ACTION.
"""
from .bus import (
    SCHEMA,
    accept_event,
    attach_watchdog,
    cancel_event,
    dispatch_delivery,
    doctor,
    load_targets,
    register_target,
    validate_target,
)

__all__ = [
    "SCHEMA",
    "accept_event",
    "attach_watchdog",
    "cancel_event",
    "dispatch_delivery",
    "doctor",
    "load_targets",
    "register_target",
    "validate_target",
]
