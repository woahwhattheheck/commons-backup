#!/usr/bin/env python3
"""CCPA Do Not Sell blocks thanks-door pixels. Compose leftover, not a remint.

Waitlist demand: opt-out also blocks pack-door pixels. Empty pixel slots
already load nothing. This leftover composes host/pack_waitlist.py
pixel_allowed with host/pack_thanks_pixel.py channel classification.
It does not overwrite waitlist.html, thanks.html, either helper, Harborline,
TALLY, LotRibbon, catalog pointers, or the Harborline pack map.
Sends stay 0. Agents do not mint a pixel ID or spend ads.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
WAITLIST_HELPER = ROOT / "host" / "pack_waitlist.py"
THANKS_HELPER = ROOT / "host" / "pack_thanks_pixel.py"
DO_NOT_OVERWRITE = (
    "packs/waitlist.html",
    "host/pack_waitlist.py",
    "packs/thanks.html",
    "ground/BUSINESS_PACK_THANKS.json",
    "host/business_pack_thanks.py",
    "host/pack_thanks_pixel.py",
    "packs/desk-website-service-20260902-01/door.html",
    "host/harborline_tally_pack_map.py",
    "host/business_pack_desk_instance.py",
    "packs/lotribbon-greetings-20260902-01",
    "packs/sidewalk-signal-web-desk-20260902-01",
)


def _load(path: Path, name: str) -> Any | None:
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ccpa_opt_out(records: list[dict[str, Any]], email: str) -> bool:
    """Last JSONL row for the address wins. Result never includes the address."""
    wanted = str(email or "").strip().lower()
    latest: dict[str, Any] | None = None
    for row in records:
        if str(row.get("email") or "").strip().lower() == wanted:
            latest = row
    if latest is None:
        return False
    kind = str(latest.get("kind") or "").strip().lower()
    return kind == "opt_out" or latest.get("ccpa_do_not_sell") is True


def gate(
    *,
    ccpa_do_not_sell: bool | None = None,
    email: str = "",
    jsonl_path: Path | None = None,
    overrides: dict[str, str] | None = None,
    value: str | float | None = None,
    waitlist_path: Path | None = None,
    thanks_path: Path | None = None,
) -> dict[str, Any]:
    waitlist = _load(waitlist_path or WAITLIST_HELPER, "pack_waitlist")
    thanks = _load(thanks_path or THANKS_HELPER, "pack_thanks_pixel")
    opted = bool(ccpa_do_not_sell)
    if jsonl_path is not None and email and waitlist is not None and hasattr(waitlist, "read_jsonl"):
        opted = opted or ccpa_opt_out(waitlist.read_jsonl(jsonl_path), email)
    if waitlist is None or thanks is None:
        return {
            "kind": "WAITLIST_PIXEL_GATE",
            "gate": False,
            "commons_admission": False,
            "verdict": "PIXEL_GATE_HELPER_MISSING",
            "waitlist_helper_present": waitlist is not None,
            "thanks_helper_present": thanks is not None,
            "purchases": [],
            "would_load_script": [],
            "sends": 0,
            "do_not_overwrite": list(DO_NOT_OVERWRITE),
            "checkout": "NOT_MINTED",
            "agents_mint_pixel_id": False,
            "agents_spend_ads": False,
        }

    channels = thanks.classify_channels(overrides=overrides, value=value)
    sample_id = ""
    if overrides:
        sample_id = next((str(v or "") for v in overrides.values() if str(v or "").strip()), "")
    allowed = bool(waitlist.pixel_allowed(opted, sample_id))
    if opted or not allowed:
        purchases: list[dict[str, Any]] = []
        would_load: list[str] = []
        verdict = "PIXEL_GATE_BLOCKED"
    else:
        purchases = list(channels.get("purchases") or [])
        would_load = list(channels.get("would_load_script") or [])
        verdict = "PIXEL_GATE_FIRE" if purchases else "PIXEL_GATE_EMPTY"

    dumped = json.dumps({"purchases": purchases, "would_load_script": would_load, "verdict": verdict})
    if "@" in dumped:
        raise RuntimeError("pixel gate leaked an address")
    return {
        "kind": "WAITLIST_PIXEL_GATE",
        "gate": False,
        "commons_admission": False,
        "verdict": verdict,
        "ccpa_do_not_sell": opted,
        "pixel_allowed": allowed,
        "purchases": purchases,
        "purchase_count": len(purchases),
        "would_load_script": would_load,
        "empty_slots_load_nothing": True,
        "sends": 0,
        "waitlist_helper": "host/pack_waitlist.py",
        "thanks_helper": "host/pack_thanks_pixel.py",
        "did_not_overwrite_waitlist_door": True,
        "did_not_overwrite_thanks_door": True,
        "do_not_overwrite": list(DO_NOT_OVERWRITE),
        "checkout": "NOT_MINTED",
        "agents_mint_pixel_id": False,
        "agents_spend_ads": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opt-out", action="store_true")
    parser.add_argument("--email", default="")
    parser.add_argument("--jsonl", default="")
    parser.add_argument("--x", default="")
    parser.add_argument("--tiktok", default="")
    parser.add_argument("--meta", default="")
    parser.add_argument("--value", default="")
    args = parser.parse_args(argv)
    overrides = {
        name: value
        for name, value in (("x", args.x), ("tiktok", args.tiktok), ("meta", args.meta))
        if value
    }
    result = gate(
        ccpa_do_not_sell=args.opt_out,
        email=args.email,
        jsonl_path=Path(args.jsonl) if args.jsonl else None,
        overrides=overrides or None,
        value=args.value or None,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
