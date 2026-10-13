#!/usr/bin/env python3
"""RouteScout compatibility facade and CLI entry point."""
from routescout_core import *  # noqa: F401,F403
from routescout_core.contracts import OFFICIAL_API_ORIGIN, _strict_json_load
from routescout_core.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
