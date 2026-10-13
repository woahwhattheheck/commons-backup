#!/usr/bin/env python3
"""GrokBot account-pool registry (corpus ids only - no invented kebabs)."""

from __future__ import annotations

import os
from typing import Any

# clans.json clan id for the Grok Bot quota pool.
DEFAULT_POOL_ID = "grokbot"
HARNESS = "grokbot"
MODEL = "Grok"

# Owner cite p/cursor-lead-two-grokbot-accounts-cite-20260902-01.md:
# two Grok Bot accounts exist and are not the same clan; kebab ids for the
# second account are NOT minted here. Supply an extra pool id only via
# GROKBOT_CONTROL_POOLS (comma-separated) when Bryce/WIRE name it.
_ENV_POOLS = "GROKBOT_CONTROL_POOLS"


def list_pools() -> list[str]:
    raw = (os.environ.get(_ENV_POOLS) or "").strip()
    if not raw:
        return [DEFAULT_POOL_ID]
    pools: list[str] = []
    for part in raw.split(","):
        name = part.strip()
        if name and name not in pools:
            pools.append(name)
    if DEFAULT_POOL_ID not in pools:
        pools.insert(0, DEFAULT_POOL_ID)
    return pools


def require_pool(pool_id: Any) -> str:
    name = str(pool_id or "").strip()
    if not name:
        raise ValueError("pool_id must be nonempty")
    known = list_pools()
    if name not in known:
        raise ValueError(
            "unknown pool_id %r; known=%s (second Grok Bot account kebab "
            "is not invented - set GROKBOT_CONTROL_POOLS when owner names it)"
            % (name, known)
        )
    return name


def attribution(
    *,
    pool_id: str,
    seat: str,
    model: str | None = None,
) -> dict[str, str]:
    return {
        "pool_id": pool_id,
        "seat": seat,
        "harness": HARNESS,
        "model": model or MODEL,
    }