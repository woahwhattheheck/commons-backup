"""Compatibility launcher for the shared laundry browser console.

The original operator_console and web_console deliveries now use one server,
UI, session boundary and operation-recovery implementation. Keep the original
launcher default (an available port) while accepting its existing CLI flags.
"""
from __future__ import annotations

from web_console import main


if __name__ == "__main__":
    raise SystemExit(main(default_port=0))
