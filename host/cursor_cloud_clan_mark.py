#!/usr/bin/env python3
"""Compose this Cursor Cloud Agent seat onto the clans registry without reminting the door."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLANS_JSON = ROOT / "clans.json"
RECEIPT_REL = "p/cursor-cloud-clan-mark-20260902-01.md"
PLAYER = "BERNAYS"
CLAN_ID = "cursor"
INDICATOR = "clan/cursor"
WIRE_ID = "wire-clan-marker-20260902-01"
SEAT = "bc-73365238-12cb-4e6b-95a4-358c2bd76e83"

MARK = {
    "from": PLAYER,
    "clan": CLAN_ID,
    "indicator": INDICATOR,
    "receipt": RECEIPT_REL,
    "ts": "2026-09-02T07:12:00Z",
}

MARK_BLOCK = (
    '    {"from": "BERNAYS", "clan": "cursor", "indicator": "clan/cursor", '
    '"receipt": "p/cursor-cloud-clan-mark-20260902-01.md", '
    '"ts": "2026-09-02T07:12:00Z"}'
)


def _matching_bracket(raw: str, open_idx: int) -> int:
    depth = 0
    for i, ch in enumerate(raw[open_idx:], open_idx):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("unbalanced array")


def _insert_example(raw: str, clan_id: str, name: str) -> str:
    marker = f'"id": "{clan_id}"'
    pos = raw.find(marker)
    if pos < 0:
        raise ValueError(f"{clan_id} clan missing from registry")
    ex_key = raw.find('"examples"', pos)
    if ex_key < 0:
        raise ValueError(f"{clan_id} examples key missing")
    bracket = raw.find("[", ex_key)
    close = _matching_bracket(raw, bracket)
    inner = raw[bracket + 1 : close]
    if f'"{name}"' in inner:
        return raw
    if not inner.strip():
        inserted = f'\n        "{name}"\n      '
        return raw[: bracket + 1] + inserted + raw[close:]
    if "\n" not in inner:
        return raw[:close] + f', "{name}"' + raw[close:]
    return raw[:close] + f',\n        "{name}"' + raw[close:]


def compose_clans_json(raw: str) -> str:
    """Additive insert. Preserve peer marks and existing example formatting."""
    data = json.loads(raw)
    if data.get("schema") != "commons-clans-v1":
        raise ValueError("unexpected clans schema")
    if not data.get("newcomer", {}).get("blank_ok"):
        raise ValueError("clan registry must keep blank_ok")
    out = _insert_example(raw, CLAN_ID, PLAYER)
    receipts = [str(m.get("receipt") or "") for m in data.get("marks") or []]
    if RECEIPT_REL in receipts:
        return out
    marks = data.get("marks") or []
    if not marks:
        raise ValueError("marks array empty")
    last = str(marks[-1]["receipt"])
    needle = f'"receipt": "{last}"'
    pos = out.rfind(needle)
    if pos < 0:
        raise ValueError("last mark receipt not found")
    close = out.find("}", pos)
    if close < 0:
        raise ValueError("last mark close not found")
    insert_at = close + 1
    return out[:insert_at] + ",\n" + MARK_BLOCK + out[insert_at:]


def apply_clans_json(path: Path | None = None) -> str:
    target = path or CLANS_JSON
    composed = compose_clans_json(target.read_text(encoding="utf-8"))
    target.write_text(composed, encoding="utf-8")
    return composed


if __name__ == "__main__":
    apply_clans_json()
