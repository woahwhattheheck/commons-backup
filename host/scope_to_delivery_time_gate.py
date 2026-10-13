#!/usr/bin/env python3
"""Compatibility surface for Commons scope-to-delivery trusted-time authority.

The authoritative implementation lives in ``scope_to_delivery_time_authority``.
Keeping this path stable preserves existing imports and CLI callers while the
current-work kernel remains isolated from historical helper rebinding.
"""
from __future__ import annotations

try:
    from host.scope_to_delivery_time_authority import *  # noqa: F401,F403
    from host.scope_to_delivery_time_authority import __all__, main
except ModuleNotFoundError:  # direct ``python host/...`` execution
    from scope_to_delivery_time_authority import *  # type: ignore # noqa: F401,F403
    from scope_to_delivery_time_authority import __all__, main  # type: ignore


if __name__ == "__main__":
    raise SystemExit(main())
