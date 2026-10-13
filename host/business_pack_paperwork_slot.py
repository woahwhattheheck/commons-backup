#!/usr/bin/env python3
"""Paperwork factory is a shared slot, not a pack instance.

Bryce hub 1788327816.150299: packs help the customer with required
paperwork. CLEAR cursor-plant-yard-greeting-pack-20260902-01 — LEAD
bc-23891c63 keeps LotRibbon paths. This helper does not write those
files or remint the landed checklist factory.

Not legal advice. Not a Commons gate. Slots stay OWNER_UNSET /
HOLD_COUNSEL. Checkout stays NOT_MINTED.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAW = ROOT / "ground" / "BUSINESS_PACK_PAPERWORK_SLOT.json"
SHARED_HOMES = ("factory", "shared", "slot", "template", "factory_shared_slot")
INSTANCE_HOMES = ("instance", "plant", "lotribbon", "owned_instance")
RESERVED_PLANT = (
    "packs/lotribbon-greetings-20260902-01/",
    "ground/BUSINESS_PACK_PLANT.json",
)
PEER_FACTORY = (
    "ground/BUSINESS_PACK_PAPERWORK.json",
    "ground/BUSINESS_PACK_PAPERWORK.md",
    "host/business_pack_paperwork.py",
    "test_business_pack_paperwork.py",
    "packs/_template/paperwork.md",
    "p/cursor-business-pack-paperwork-20260902-01.md",
)
FRANCHISE_RE = re.compile(r"(?i)\bfranchise(e|or|s|d)?\b")
EARNINGS_RE = re.compile(
    r"(?i)\bmake\s+\$\d|\bearn\s+\$\d|\bprofit\s+\$\d|"
    r"\bpayback\b|\bunrealistic result"
)


def load_law(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_LAW
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("law is not an object")
    return data


def _norm_path(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def reserved_plant_path(path: Any) -> bool:
    text = _norm_path(path)
    if text == "ground/BUSINESS_PACK_PLANT.json":
        return True
    return text.startswith("packs/lotribbon-greetings-20260902-01/")


def peer_factory_path(path: Any) -> bool:
    return _norm_path(path) in PEER_FACTORY


def _writes(pack: dict[str, Any]) -> list[str]:
    raw = pack.get("writes") or pack.get("paths") or []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return []


def classify_slot(pack: dict[str, Any] | None) -> dict[str, Any]:
    """Where paperwork lives. Instance ownership is flagged, not gated."""
    law = load_law()
    data = pack if isinstance(pack, dict) else {}
    home = str(data.get("paperwork_home") or data.get("home") or "").strip().lower()
    owns_factory = data.get("owns_factory") is True or data.get(
        "paperwork_is_instance_field"
    ) is True
    legal_advice = data.get("legal_advice") is True
    writes = _writes(data)
    plant_write = any(reserved_plant_path(item) for item in writes)
    factory_steal = any(peer_factory_path(item) for item in writes)
    blob = json.dumps(data, default=str)
    franchise = bool(FRANCHISE_RE.search(blob))
    earnings = bool(EARNINGS_RE.search(blob))
    if legal_advice:
        verdict = "LEGAL_ADVICE_CLAIM"
    elif plant_write:
        verdict = "PLANT_INSTANCE_EXCLUDED"
    elif factory_steal:
        verdict = "FACTORY_PATH_STOLEN"
    elif franchise:
        verdict = "FRANCHISE_VOCAB"
    elif earnings:
        verdict = "EARNINGS_COPY"
    elif owns_factory or home in INSTANCE_HOMES:
        verdict = "INSTANCE_OWNED"
    elif not home:
        verdict = "MISSING_HOME"
    elif home in SHARED_HOMES:
        verdict = "SHARED_SLOT_OK"
    else:
        verdict = "MISSING_HOME"
    return {
        "gate": False,
        "commons_admission": False,
        "verdict": verdict,
        "paperwork_home": home,
        "shared_slot": verdict == "SHARED_SLOT_OK",
        "not_instance": verdict == "SHARED_SLOT_OK",
        "plant_write": plant_write,
        "factory_steal": factory_steal,
        "legal_advice": False,
        "not_legal_advice": True,
        "hold_counsel": True,
        "not_a_commons_seat": True,
        "checkout": "NOT_MINTED",
        "cleared_claim": str(law.get("clear_claim") or ""),
        "lead_owner": str(law.get("lead_owner") or ""),
        "law_id": str(law.get("id") or ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-json", default="", help="JSON pack object")
    parser.add_argument("--law", default="", help="override law path")
    args = parser.parse_args(argv)
    if args.law:
        load_law(Path(args.law))
    pack: dict[str, Any] = {}
    if args.pack_json:
        loaded = json.loads(args.pack_json)
        if isinstance(loaded, dict):
            pack = loaded
    print(json.dumps(classify_slot(pack), indent=2))
    print("", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
