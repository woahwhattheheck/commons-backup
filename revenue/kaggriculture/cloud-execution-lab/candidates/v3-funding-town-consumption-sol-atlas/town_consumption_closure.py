# SPDX-License-Identifier: Apache-2.0
"""Exact-source carrier for deterministic town consumption in funding traces.

The current funding trace replays future market orders but omits the official
engine's public town-consumption stage. This module materializes a minimal patch
against one byte-pinned ``frozen_selected.py`` source. The patch is exact while
the public shop set is stable and fails closed across any day boundary, where a
new random shop can unlock before a later acquisition.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

EXPECTED_SOURCE_BLOB_SHA1 = "fc7baf5c179818a55037f6a61d92984d81d1a21c"
EXPECTED_ENGINE_BLOB_SHA1 = "3c202c7ee921da239356789e266b694635103fc4"

_FUNCTION_ANCHOR = (
    "def _funding_trace(obs, config, farm, private, route, now, end, current_market,\n"
    "                   stress_units=0):"
)
_RETURN_ANCHOR = (
    "    return {'cash': int(f['money']), 'acquisitions': acquisitions,\n"
    "            'executed_sales': executed_sales}"
)

_HELPER_SOURCE = '''def _funding_require_static_shop_lifecycle(now, end, config):
    """Fail closed before an end-of-day shop unlock can change future quotes."""
    raw=config.get('turnsPerDay',24)
    if isinstance(raw,bool):
        raise TypeError('turnsPerDay must be a positive integer')
    try:
        turns=int(raw)
    except (TypeError,ValueError,OverflowError) as exc:
        raise ValueError('turnsPerDay must be a positive integer') from exc
    if turns<=0 or (isinstance(raw,float) and not raw.is_integer()):
        raise ValueError('turnsPerDay must be a positive integer')
    if int(now)//turns != int(end)//turns:
        raise RuntimeError('funding horizon crosses day-close shop evolution')


def _funding_apply_town_consumption(inventory, shops, config, step):
    """Apply the official public town stage after one projected market stage."""
    shop_interval=max(1,int(config.get('townShopSellInterval',4)))
    center_interval=max(1,int(config.get('townCenterSellInterval',24)))
    if step % shop_interval == 0:
        for shop_name in shops:
            products=m.SHOPS[shop_name]
            multiplier=2 if len(products)==1 else 1
            for item in products:
                inventory[item]-=multiplier
    if step % center_interval == 0:
        for item in m.PRODUCTS:
            if item!='FERTILIZER':
                inventory[item]-=1'''

_GUARD_CALL_SOURCE = "    _funding_require_static_shop_lifecycle(now, end, config)"
_CALL_SOURCE = '''        _funding_apply_town_consumption(
            inventory, obs.get('town', {}).get('unlocked_shops', ()),
            config, t)
'''


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_blob_sha1(text: str) -> str:
    """Return Git's canonical SHA-1 object id for one UTF-8 text blob."""
    payload = text.encode("utf-8")
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def _positive_turns_per_day(config: Mapping[str, Any]) -> int:
    raw = config.get("turnsPerDay", 24)
    if isinstance(raw, bool):
        raise TypeError("turnsPerDay must be a positive integer")
    try:
        turns = int(raw)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("turnsPerDay must be a positive integer") from exc
    if turns <= 0 or (isinstance(raw, float) and not raw.is_integer()):
        raise ValueError("turnsPerDay must be a positive integer")
    return turns


def require_static_shop_lifecycle(
    now: int, end: int, config: Mapping[str, Any]
) -> None:
    """Oracle for the injected fail-closed shop-lifecycle boundary."""
    turns = _positive_turns_per_day(config)
    if int(now) // turns != int(end) // turns:
        raise RuntimeError("funding horizon crosses day-close shop evolution")


def apply_public_town_consumption(
    inventory: MutableMapping[str, int],
    shops: Sequence[str],
    config: Mapping[str, Any],
    step: int,
    *,
    shop_products: Mapping[str, Sequence[str]],
    products: Sequence[str],
) -> None:
    """Pure oracle equivalent to the injected helper and official engine stage."""
    shop_interval = max(1, int(config.get("townShopSellInterval", 4)))
    center_interval = max(1, int(config.get("townCenterSellInterval", 24)))
    if step % shop_interval == 0:
        for shop_name in shops:
            sold = shop_products[shop_name]
            multiplier = 2 if len(sold) == 1 else 1
            for item in sold:
                inventory[item] -= multiplier
    if step % center_interval == 0:
        for item in products:
            if item != "FERTILIZER":
                inventory[item] -= 1


def verify_official_engine(engine_source: str) -> str:
    """Verify the exact official interpreter and the stage boundary we mirror."""
    if not isinstance(engine_source, str):
        raise TypeError("engine_source must be text")
    engine_blob = git_blob_sha1(engine_source)
    if engine_blob != EXPECTED_ENGINE_BLOB_SHA1:
        raise ValueError(
            f"engine drift: expected Git blob {EXPECTED_ENGINE_BLOB_SHA1}, "
            f"got {engine_blob}"
        )
    stage_anchor = (
        "    _process_market(state, env)\n"
        "    _town_consume(env, state, step)\n"
        "    for farm in obs0.farms:\n"
        "        _decay_plants(farm, step)"
    )
    if engine_source.count(stage_anchor) != 1:
        raise ValueError("official market->town->decay stage anchor drift")
    if engine_source.count("def _town_consume(env, state, step):") != 1:
        raise ValueError("official town-consumption function anchor drift")
    compile(engine_source, "<official-kaggriculture-engine>", "exec")
    return engine_blob


def materialize(source: str, *, require_expected_source: bool = True) -> str:
    """Return a compiled source postimage or raise on any closure drift."""
    if not isinstance(source, str):
        raise TypeError("source must be text")
    source_blob = git_blob_sha1(source)
    if require_expected_source and source_blob != EXPECTED_SOURCE_BLOB_SHA1:
        raise ValueError(
            f"source drift: expected Git blob {EXPECTED_SOURCE_BLOB_SHA1}, "
            f"got {source_blob}"
        )
    if source.count(_FUNCTION_ANCHOR) != 1:
        raise ValueError("funding trace function anchor count is not exactly one")
    if source.count(_RETURN_ANCHOR) != 1:
        raise ValueError("funding trace return anchor count is not exactly one")
    if "def _funding_apply_town_consumption(" in source:
        raise ValueError("town-consumption helper already present")
    if "def _funding_require_static_shop_lifecycle(" in source:
        raise ValueError("shop-lifecycle guard already present")

    patched = source.replace(
        _FUNCTION_ANCHOR,
        _HELPER_SOURCE
        + "\n\n\n"
        + _FUNCTION_ANCHOR
        + "\n"
        + _GUARD_CALL_SOURCE,
        1,
    )
    patched = patched.replace(_RETURN_ANCHOR, _CALL_SOURCE + _RETURN_ANCHOR, 1)
    if patched.count("def _funding_apply_town_consumption(") != 1:
        raise ValueError("town-consumption helper insertion failed")
    if patched.count("def _funding_require_static_shop_lifecycle(") != 1:
        raise ValueError("shop-lifecycle guard insertion failed")
    if patched.count("    _funding_require_static_shop_lifecycle(now, end, config)\n") != 1:
        raise ValueError("shop-lifecycle call insertion failed")
    if patched.count("        _funding_apply_town_consumption(\n") != 1:
        raise ValueError("funding-loop town call insertion failed")
    compile(patched, "<frozen_selected-town-consumption>", "exec")
    return patched


def receipt(source: str, patched: str, engine_source: str) -> dict[str, Any]:
    engine_blob = verify_official_engine(engine_source)
    return {
        "schema": "titan-v3-funding-town-consumption/v2",
        "complete": True,
        "source_blob_sha1": git_blob_sha1(source),
        "expected_source_blob_sha1": EXPECTED_SOURCE_BLOB_SHA1,
        "source_sha256": sha256_text(source),
        "engine_blob_sha1": engine_blob,
        "engine_sha256": sha256_text(engine_source),
        "patched_source_sha256": sha256_text(patched),
        "town_helper_count": patched.count("def _funding_apply_town_consumption("),
        "town_call_count": patched.count("        _funding_apply_town_consumption(\n"),
        "lifecycle_guard_count": patched.count(
            "def _funding_require_static_shop_lifecycle("
        ),
        "lifecycle_call_count": patched.count(
            "    _funding_require_static_shop_lifecycle(now, end, config)\n"
        ),
        "shop_lifecycle_policy": "same-day exact; cross-day fail-closed",
        "official_stage_order": "unit_actions->market->town_consume->decay->day_close",
        "canonical_runtime_modified": False,
        "hosted_strength_claim": False,
        "release_selection_claim": False,
    }


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()

    source = args.source.read_text(encoding="utf-8")
    engine_source = args.engine.read_text(encoding="utf-8")
    verify_official_engine(engine_source)
    patched = materialize(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(patched, encoding="utf-8")
    data = receipt(source, patched, engine_source)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(
        json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(data, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
