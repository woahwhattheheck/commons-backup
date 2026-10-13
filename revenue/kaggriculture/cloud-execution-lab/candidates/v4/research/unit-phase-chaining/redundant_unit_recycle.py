# SPDX-License-Identifier: Apache-2.0
"""Fail-closed admission for recycling strict same-target unit no-ops.

This is research/default-OFF logic for TITAN V4's existing unit-phase-chaining
family.  It never moves or rewrites the successful predecessor.  The first
admitted subset is deliberately narrow: a later redundant animal HARVEST or
COLLECT_FERTILIZER may become CARE when the pre-callback animal is already fed
and not yet cared.  The conversion is inventory-neutral and keeps the earlier
actor's harvest/fertilizer cargo exactly where the parent action put it.

No runtime wiring or promotion authority lives here.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha1
from pathlib import Path
from typing import Any, Mapping

ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
ANIMALS = frozenset({"GOOSE", "COW", "SHEEP"})
REDUNDANT_SOURCE_OPS = frozenset({"COLLECT_FERTILIZER", "HARVEST"})


def git_blob_sha1(data: bytes) -> str:
    return sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def verify_engine_file(path: str | Path) -> bool:
    """Return True only for the exact official engine source this theorem pins."""
    try:
        data = Path(path).read_bytes()
    except (OSError, TypeError, ValueError):
        return False
    return git_blob_sha1(data) == ENGINE_GIT_BLOB


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _coord(value: Any, n: int) -> tuple[int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    x, y = value
    if not (_is_int(x) and _is_int(y)):
        return None
    if not (0 <= x < n and 0 <= y < n):
        return None
    return x, y


def _op(row: Any) -> str | None:
    if not isinstance(row, list) or not row or not isinstance(row[0], str):
        return None
    return row[0]


def _strict_surface(action: Any, farm: Any) -> tuple[list[list[Any]], list[tuple[int, int]], list[list[Any]]] | None:
    """Validate only the surfaces needed to make a whole-action atomic decision."""
    if not isinstance(action, Mapping) or not isinstance(farm, Mapping):
        return None
    tiles = farm.get("tiles")
    if not isinstance(tiles, list) or not tiles:
        return None
    n = len(tiles)
    if any(not isinstance(row, list) or len(row) != n for row in tiles):
        return None

    hands_pos = farm.get("hands")
    if not isinstance(hands_pos, list):
        return None
    farmer_pos = _coord(farm.get("farmer"), n)
    if farmer_pos is None:
        return None
    positions = [farmer_pos]
    for raw in hands_pos:
        pos = _coord(raw, n)
        if pos is None:
            return None
        positions.append(pos)

    farmer_row = action.get("farmer")
    hands_rows = action.get("hands")
    if not isinstance(farmer_row, list) or not isinstance(hands_rows, list):
        return None
    if len(hands_rows) != len(hands_pos):
        return None
    rows = [farmer_row] + list(hands_rows)
    # We intentionally fail closed on malformed represented rows instead of
    # partially mutating an otherwise malformed action vector.
    if any(not isinstance(row, list) for row in rows):
        return None
    return rows, positions, tiles


def _animal_admission(tile: Any, source_op: str) -> bool:
    if not isinstance(tile, Mapping):
        return False
    animal = tile.get("animal")
    if animal not in ANIMALS:
        return False
    # Exact booleans only.  CARE itself is legal before FEED, but requiring the
    # animal already fed gives the replacement an immediate valid service basis
    # and prevents claiming arbitrary speculative CARE work.
    if tile.get("fed_today") is not True or tile.get("cared_today") is not False:
        return False
    if source_op == "COLLECT_FERTILIZER":
        return tile.get("fertilizer_available") is True
    if source_op == "HARVEST":
        units = tile.get("yield_units")
        return _is_int(units) and units > 0
    return False


def recycle_redundant_unit_rows(
    action: Any,
    farm: Any,
    *,
    enabled: bool = False,
) -> tuple[Any, dict[str, Any]]:
    """Replace a proved-later no-op with CARE, or return exact parent identity.

    Admitted pattern for actor ``i``:
      * actor ``j < i`` is at the exact same tile with the exact same source op;
      * the pre-callback animal state proves actor j's source op succeeds;
      * that success makes actor i's identical source op a strict engine no-op;
      * no earlier CARE (or prior conversion) owns the tile;
      * the animal is already fed and uncared, so CARE is immediately legal.

    The successful predecessor is never changed.  At most one replacement per
    tile is made in a callback, avoiding cross-op self-interference.
    """
    report: dict[str, Any] = {
        "schema": "titan-v4-unitrecycle/v1",
        "enabled": enabled is True,
        "strict_candidates": 0,
        "replacements": 0,
        "from_ops": {"COLLECT_FERTILIZER": 0, "HARVEST": 0},
    }
    if enabled is not True:
        return action, report

    surface = _strict_surface(action, farm)
    if surface is None:
        return action, report
    rows, positions, tiles = surface

    replacements: list[int] = []
    owned_tiles: set[tuple[int, int]] = set()
    for i in range(1, len(rows)):
        source_op = _op(rows[i])
        if source_op not in REDUNDANT_SOURCE_OPS:
            continue
        pos = positions[i]
        x, y = pos
        tile = tiles[y][x]
        if not _animal_admission(tile, source_op):
            continue

        predecessor = None
        for j in range(i):
            if positions[j] == pos and _op(rows[j]) == source_op:
                predecessor = j
                break
        if predecessor is None:
            continue
        report["strict_candidates"] += 1

        # An authored earlier CARE would make our replacement redundant, and a
        # previous conversion on this tile would do the same.
        if pos in owned_tiles or any(positions[j] == pos and _op(rows[j]) == "CARE" for j in range(i)):
            continue
        replacements.append(i)
        owned_tiles.add(pos)

    if not replacements:
        return action, report

    out = deepcopy(action)
    for i in replacements:
        source_op = _op(rows[i])
        if source_op is None:  # defensive; source surface was already validated
            return action, {**report, "replacements": 0}
        out["hands"][i - 1] = ["CARE"]
        report["replacements"] += 1
        report["from_ops"][source_op] += 1

    return out, report
