#!/usr/bin/env python3
"""Generic X / TikTok / Meta pixel slots. Compose leftover, not a door remint.

Peer already shipped packs/thanks.html + ground/BUSINESS_PACK_THANKS.json +
host/business_pack_thanks.py (cursor-business-pack-thanks-pixel-20260902-01).
This helper does not overwrite those paths.

SCOUT (hub, TikTok added as a channel): pixel slots are generic. X, TikTok,
and Meta IDs are each independently empty-by-default. Empty loads nothing.
One Purchase per platform whose ID is present. Event value comes from the
tier query param. Agents do not mint a pixel ID or spend ads.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent.parent
PEER_LAW = ROOT / "ground" / "BUSINESS_PACK_THANKS.json"
PEER_DOOR = ROOT / "packs" / "thanks.html"
PEER_HELPER = ROOT / "host" / "business_pack_thanks.py"
CHANNELS_LAW = ROOT / "ground" / "BUSINESS_PACK_THANKS_CHANNELS.json"

DO_NOT_OVERWRITE = (
    "packs/thanks.html",
    "ground/BUSINESS_PACK_THANKS.json",
    "host/business_pack_thanks.py",
)

CHANNEL_ORDER = ("x", "tiktok", "meta")
THIRD_PARTY_SRC = (
    "ads-twitter.com",
    "static.ads-twitter.com",
    "analytics.tiktok.com",
    "facebook.net",
    "connect.facebook.net",
    "googletagmanager.com",
    "google-analytics.com",
    "doubleclick.net",
)
SRC_RE = re.compile(r"""\bsrc\s*=\s*['\"]([^'\"]+)['\"]""", re.I)
EARNINGS_RE = re.compile(
    r"(?i)\bmake\s+\$\d|\bearn\s+\$\d|\bprofit\s+\$\d|"
    r"\bmake \$\d+ this weekend|\bunrealistic result"
)


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not an object")
    return data


def load_channels(path: Path | None = None) -> dict[str, Any]:
    return load_json(path or CHANNELS_LAW)


def third_party_script_srcs(html: str) -> list[str]:
    found: list[str] = []
    for match in SRC_RE.finditer(html or ""):
        src = match.group(1)
        lowered = src.lower()
        if any(marker in lowered for marker in THIRD_PARTY_SRC):
            found.append(src)
    return found


def purchase_value(query: str | None = None, url: str = "") -> float | None:
    raw = query
    if raw is None and url:
        raw = parse_qs(urlparse(url).query).get("value", [None])[0]
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = float(str(raw).strip())
    except ValueError:
        return None
    if value < 0:
        return None
    return value


def _channel_slot(raw: Any) -> dict[str, str]:
    data = raw if isinstance(raw, dict) else {}
    return {
        "pixel_id": str(data.get("pixel_id") or "").strip(),
        "script_src_when_filled": str(data.get("script_src_when_filled") or "").strip(),
        "event": str(data.get("event") or "Purchase").strip() or "Purchase",
    }


def classify_channels(
    law: dict[str, Any] | None = None,
    overrides: dict[str, str] | None = None,
    value: str | float | None = None,
) -> dict[str, Any]:
    """Independent empty-by-default slots. One Purchase per present platform."""
    data = law if isinstance(law, dict) else load_channels()
    channels_in = data.get("channels") if isinstance(data.get("channels"), dict) else {}
    filled: dict[str, Any] = {}
    purchases: list[dict[str, Any]] = []
    would_load: list[str] = []
    empty_ids: list[str] = []
    amount = purchase_value(query=None if value is None else str(value))
    for name in CHANNEL_ORDER:
        slot = _channel_slot(channels_in.get(name))
        if overrides and name in overrides:
            slot["pixel_id"] = str(overrides[name] or "").strip()
        present = bool(slot["pixel_id"])
        entry = {
            "channel": name,
            "pixel_id_present": present,
            "empty_loads_nothing": not present,
            "script_src_when_filled": slot["script_src_when_filled"],
            "event": slot["event"],
        }
        filled[name] = entry
        if not present:
            empty_ids.append(name)
            continue
        payload: dict[str, Any] = {
            "channel": name,
            "event": slot["event"],
        }
        if amount is not None:
            payload["value"] = amount
            payload["currency"] = "USD"
        purchases.append(payload)
        if slot["script_src_when_filled"]:
            would_load.append(slot["script_src_when_filled"])
    all_empty = len(empty_ids) == len(CHANNEL_ORDER)
    if all_empty:
        verdict = "CHANNELS_ALL_EMPTY"
    elif empty_ids:
        verdict = "CHANNELS_PARTIAL"
    else:
        verdict = "CHANNELS_ALL_FILLED"
    return {
        "gate": False,
        "commons_admission": False,
        "verdict": verdict,
        "channels": filled,
        "purchases": purchases,
        "purchase_count": len(purchases),
        "one_purchase_per_platform_present": True,
        "empty_independently_loads_nothing": True,
        "would_load_script": would_load,
        "agents_mint_pixel_id": False,
        "agents_spend_ads": False,
        "checkout": str(data.get("checkout") or "NOT_MINTED"),
        "did_not_overwrite_peer_door": True,
        "do_not_overwrite": list(DO_NOT_OVERWRITE),
        "law_id": str(data.get("id") or ""),
        "scout_demand_id": str(data.get("scout_demand_id") or ""),
        "did_not_remint_scout_demand": True,
    }


def classify_peer_door(
    html: str | None = None,
    law: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read-only check of the peer thanks door. Does not write it."""
    missing: list[str] = []
    if law is None:
        if not PEER_LAW.is_file():
            missing.append("ground/BUSINESS_PACK_THANKS.json")
            peer = {}
        else:
            peer = load_json(PEER_LAW)
    else:
        peer = law
    if html is None:
        if not PEER_DOOR.is_file():
            missing.append("packs/thanks.html")
            door_html = ""
        else:
            door_html = PEER_DOOR.read_text(encoding="utf-8")
    else:
        door_html = html
    scripts = third_party_script_srcs(door_html)
    slot = str(peer.get("pixel_id") or "").strip()
    empty = slot == ""
    return {
        "gate": False,
        "present": not missing,
        "missing": missing,
        "peer_id": str(peer.get("id") or ""),
        "pixel_id_empty": empty,
        "static_third_party_scripts": scripts,
        "empty_loads_zero_third_party_scripts": empty and not scripts,
        "earnings_claim": bool(EARNINGS_RE.search(door_html)),
        "fetches_peer_json": "BUSINESS_PACK_THANKS.json" in door_html,
        "no_static_script_src": "<script src=" not in door_html.lower(),
        "did_not_overwrite": True,
        "peer_helper_present": PEER_HELPER.is_file(),
    }


def classify(
    channels: dict[str, Any] | None = None,
    overrides: dict[str, str] | None = None,
    value: str | float | None = None,
    peer_html: str | None = None,
    peer_law: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = classify_channels(law=channels, overrides=overrides, value=value)
    result["peer_door"] = classify_peer_door(html=peer_html, law=peer_law)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--x", default=None, help="override X pixel id (tests only)")
    parser.add_argument("--tiktok", default=None, help="override TikTok pixel id")
    parser.add_argument("--meta", default=None, help="override Meta pixel id")
    parser.add_argument("--value", default="", help="Purchase value query (tier price)")
    parser.add_argument("--channels", default="", help="override channels JSON path")
    args = parser.parse_args(argv)
    law = load_channels(Path(args.channels) if args.channels else None)
    overrides = {
        name: value
        for name, value in (("x", args.x), ("tiktok", args.tiktok), ("meta", args.meta))
        if value is not None
    }
    result = classify(
        channels=law,
        overrides=overrides or None,
        value=args.value or None,
    )
    print(json.dumps(result, indent=2))
    print("", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
