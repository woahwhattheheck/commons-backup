"""Linux AT-SPI adapter re-export.

The live hand is `linux_atspi.LinuxHandsServer` (PR 3715 on main). This module
keeps the leftover `linux.py` import path without pretending the adapter is
unwritten. Missing bus or libraries return TRANSPORT_UNCONFIGURED.

Cite: p/coil-titan-hands-linux-atspi-20260826-01.md
Do not remint that receipt. Do not undo the AT-SPI adapter.
"""

from __future__ import annotations

from typing import Any, Mapping

from host.titan_hands.linux_atspi import LINUX_ACTIONS, LinuxHandsServer, ROLE_MAP

ATSPI_SKETCH = {
    "platform": "linux",
    "status": "live",
    "adapter": "at-spi",
    "observation": "at-spi2 accessibility tree",
    "actuation": "AT-SPI actions plus toolkit patterns",
    "pixels": "explicit compositor capture only",
    "missing_bus": "TRANSPORT_UNCONFIGURED",
    "delta": "same DeltaUI added/updated/removed contract as Windows and Android",
    "role_map": dict(ROLE_MAP),
    "action_map": {name: name for name in LINUX_ACTIONS},
}


def linux_capabilities() -> dict[str, Any]:
    server = LinuxHandsServer()
    try:
        return server.handle({"op": "capabilities"})
    finally:
        server.close()


def handle_linux(request: Mapping[str, Any]) -> dict[str, Any]:
    server = LinuxHandsServer()
    try:
        return server.handle(request)
    finally:
        server.close()


__all__ = [
    "ATSPI_SKETCH",
    "LinuxHandsServer",
    "handle_linux",
    "linux_capabilities",
]
