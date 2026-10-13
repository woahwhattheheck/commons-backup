#!/usr/bin/env python3
"""Leftover finder for the Harborline desk instance layout. Not a Commons gate.

The sidewalk desk helper (host/business_pack_desk_instance.py) requires
manifest.json + index.html. Harborline lives at
packs/desk-website-service-20260902-01 with instance.json + door.html.
That miss is FINDER-FAILED on the sidewalk helper, not a silent 0.

This leftover finds the Harborline layout. It does not invent a
Harborline manifest.json. It does not write pack files. It does not
decide KEEP/SELL. Marketing stays Bryce. Checkout stays NOT_MINTED.

Cite cursor-claude-peer-check-desk-remeasure-20260902-01 (do not remint)
and wire-claude-peer-check-20260902-01.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_PACK = ROOT / "packs" / "desk-website-service-20260902-01"
HELPER_ID = "cursor-harborline-desk-finder-20260902-01"
REMEASURE_ID = "cursor-claude-peer-check-desk-remeasure-20260902-01"
WIRE_ID = "wire-claude-peer-check-20260902-01"
SIDEWALK_HELPER = HERE / "business_pack_desk_instance.py"

REQUIRED = (
    "instance.json",
    "door.html",
    "checkout.md",
    "offer.md",
    "terms.md",
    "keep-vs-sell.md",
    "instructions.md",
    "README.md",
    "assets.md",
    "week1.md",
)
TEXT_SUFFIXES = (".md", ".html", ".json", ".txt")
# Buyer-facing fail-closed. Internal briefs may quote banned phrases as "never say".
BUYER_FACING = ("door.html", "offer.md", "checkout.md", "outreach.md")
STRIPE_RE = re.compile(r"https://(buy|donate)\.stripe\.com/|plink_[A-Za-z0-9]+")
FRANCHISE_RE = re.compile(r"(?i)\bfranchis")
LEADS_RE = re.compile(
    r"(?i)\b(leads?|customers?|clients?|accounts?)\s+(are\s+)?"
    r"(included|provided|supplied|guaranteed)\b"
    r"|\bwe\s+(provide|bring|deliver)\s+(you\s+)?(the\s+)?"
    r"(leads?|customers?|clients?)\b"
)
TERMS_KEYS = {
    "tjlabs_profit_share_percent": "profit_share_percent",
    "tjlabs_partial_ownership_fraction": "partial_ownership_fraction",
    "owner_pasted": "owner_pasted",
    "counsel_cleared": "counsel_cleared",
}
DO_NOT_WRITE = (
    "host/business_pack_desk_instance.py",
    "packs/desk-website-service-20260902-01/instance.json",
    "packs/desk-website-service-20260902-01/door.html",
    "packs/desk-website-service-20260902-01/manifest.json",
    "packs/sidewalk-signal-web-desk-20260902-01/manifest.json",
    "packs/sidewalk-signal-web-desk-20260902-01/index.html",
    f"p/{REMEASURE_ID}.md",
    f"p/{WIRE_ID}.md",
    "ground/CLAUDE_PEER_CHECK.md",
)


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"host/{filename} is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def search_space(pack: Path) -> list[str]:
    paths = [str((pack / name).resolve()) for name in ("instance.json", "door.html")]
    paths.append(str((pack / "manifest.json").resolve()))
    return paths


def load_instance(pack: Path) -> dict[str, Any] | None:
    path = pack / "instance.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("instance.json is not an object")
    return data


def resolve_door(pack: Path, instance: dict[str, Any] | None) -> Path | None:
    declared = str((instance or {}).get("door") or "").strip()
    candidates: list[Path] = []
    if declared:
        candidates.append(ROOT / declared)
        candidates.append(pack / Path(declared).name)
        candidates.append(pack / declared)
    candidates.append(pack / "door.html")
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return resolved
    return None


def terms_slots(pack: Path) -> dict[str, Any]:
    slots: dict[str, Any] = {
        "profit_share_percent": None,
        "partial_ownership_fraction": None,
        "owner_pasted": None,
        "counsel_cleared": None,
    }
    path = pack / "terms.md"
    if not path.is_file():
        return slots
    for line in read_text(path).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key not in TERMS_KEYS:
            continue
        value = value.strip()
        mapped = TERMS_KEYS[key]
        if mapped in ("owner_pasted", "counsel_cleared"):
            slots[mapped] = value.lower() == "true"
        else:
            slots[mapped] = value
    return slots


def text_files(pack: Path) -> list[Path]:
    return sorted(
        path
        for path in pack.rglob("*")
        if path.is_file() and path.suffix in TEXT_SUFFIXES
    )


def known_present() -> dict[str, bool]:
    return {
        "ground/HEAD.md": (ROOT / "ground" / "HEAD.md").is_file(),
        "ground/CLAUDE_PEER_CHECK.md": (ROOT / "ground" / "CLAUDE_PEER_CHECK.md").is_file(),
        "host/business_pack_desk_instance.py": SIDEWALK_HELPER.is_file(),
    }


def finder_failed(pack: Path, miss: list[str], errors: list[str] | None = None) -> dict[str, Any]:
    rel = pack.relative_to(ROOT).as_posix() if pack.is_relative_to(ROOT) else str(pack)
    return {
        "kind": "HARBORLINE_DESK_INSTANCE_FIND",
        "gate": False,
        "commons_admission": False,
        "id": HELPER_ID,
        "pack": rel,
        "layout": "instance.json+door.html",
        "state": "FINDER-FAILED",
        "errors": errors or [],
        "miss": miss,
        "search_space": search_space(pack),
        "did_not_invent_manifest": True,
        "did_not_write_pack_files": True,
        "did_not_decide_keep_sell": True,
        "keep_or_sell_on_disk": "",
        "saleable": False,
        "terms_verdict": "",
        "sell_instance_verdict": "",
        "checkout": "NOT_MINTED",
        "marketing": "bryce_only",
        "known_present": known_present(),
        "do_not_write": list(DO_NOT_WRITE),
        "cite": [REMEASURE_ID, WIRE_ID],
    }


def verify(pack: Path) -> dict[str, Any]:
    miss: list[str] = []
    if not (pack / "instance.json").is_file():
        miss.append((pack / "instance.json").as_posix())
    if not (pack / "door.html").is_file() and not resolve_door(pack, None):
        miss.append((pack / "door.html").as_posix())
    if miss:
        return finder_failed(pack, miss)

    instance = load_instance(pack)
    if instance is None:
        return finder_failed(pack, [(pack / "instance.json").as_posix()])

    door = resolve_door(pack, instance)
    if door is None:
        return finder_failed(
            pack,
            [str(instance.get("door") or (pack / "door.html"))],
            errors=["door path not on disk"],
        )

    unique = _load("business_pack_unique", "business_pack_unique.py")
    terms = _load("tjlabs_pack_terms", "tjlabs_pack_terms.py")
    errors: list[str] = []
    for name in REQUIRED:
        path = pack / name
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            errors.append(f"missing or empty: {name}")

    brand = str(instance.get("brand") or "").strip()
    if not brand:
        errors.append("instance.brand is required")
    checkout = str(instance.get("checkout") or "").strip()
    if checkout != "OWNER_PASTE_REQUIRED":
        errors.append("instance.checkout must be OWNER_PASTE_REQUIRED")
    if instance.get("marketing") != "bryce_only":
        errors.append("instance.marketing must be bryce_only")
    if instance.get("agents_spend_ads") is not False:
        errors.append("instance.agents_spend_ads must be false")
    if instance.get("no_fake_stripe_urls") is not True:
        errors.append("instance.no_fake_stripe_urls must be true")
    if instance.get("ftc_437_customers_included") is not False:
        errors.append("instance.ftc_437_customers_included must be false")
    if instance.get("unique_instance_sell") is not True:
        errors.append("instance.unique_instance_sell must be true")
    if int(instance.get("tier_usd") or 0) != 200:
        errors.append("instance.tier_usd must be 200")

    sell = unique.classify_sell_offer(
        {
            "unique_instance_sell": True,
            "brand": brand,
            "door": str(instance.get("door") or door.as_posix()),
        }
    )
    slots = terms_slots(pack)
    terms_text = read_text(pack / "terms.md") if (pack / "terms.md").is_file() else ""
    terms_result = terms.classify_instance({**slots, "terms_text": terms_text})
    saleable = bool(terms_result.get("saleable"))
    if saleable and not (slots.get("owner_pasted") and slots.get("counsel_cleared")):
        errors.append("saleable cannot be true before owner paste and counsel clearance")
        saleable = False

    copy_verdicts: dict[str, str] = {}
    for path in text_files(pack):
        rel = path.relative_to(pack).as_posix()
        text = read_text(path)
        verdict = unique.classify_copy(text)["verdict"]
        copy_verdicts[rel] = verdict
        if STRIPE_RE.search(text):
            errors.append(f"{rel}: invented Stripe URL or plink id")
        if rel in BUYER_FACING:
            if verdict != "COPY_OK":
                errors.append(f"{rel}: {verdict}")
            if LEADS_RE.search(text):
                errors.append(f"{rel}: promises leads or customers")
            if FRANCHISE_RE.search(text):
                errors.append(f"{rel}: franchise vocabulary in buyer-facing copy")

    door_text = read_text(door)
    if "<script" in door_text.lower():
        errors.append("door must carry zero scripts")
    if "$200" not in door_text:
        errors.append("door must state the $200 pack price")
    if "OWNER_PASTE_REQUIRED" not in door_text:
        errors.append("door must show OWNER_PASTE_REQUIRED")
    if STRIPE_RE.search(door_text):
        errors.append("door: invented Stripe URL")

    checkout_text = read_text(pack / "checkout.md") if (pack / "checkout.md").is_file() else ""
    if "NOT_MINTED" not in checkout_text:
        errors.append("checkout.md must show NOT_MINTED")
    if "Owner pastes live Payment Link" not in checkout_text:
        errors.append("checkout.md must keep the owner-paste sentence")
    if "mailto:tokenjunkielabs@gmail.com" not in checkout_text:
        errors.append("checkout.md must keep the mailto fallback")

    unset = terms.is_unset
    if slots["profit_share_percent"] is None or slots["partial_ownership_fraction"] is None:
        errors.append("terms.md must carry both tjlabs slots")
    if not slots["owner_pasted"] and not (
        unset(slots["profit_share_percent"]) and unset(slots["partial_ownership_fraction"])
    ):
        errors.append("terms.md carries a number the owner did not paste")
    if terms_result.get("verdict") in ("FAKE_STRIPE_URL", "EARNINGS_CLAIM"):
        errors.append(f"terms.md: {terms_result['verdict']}")

    fingerprint = unique.content_fingerprint(
        {
            "sale_id": str(instance.get("sale_id") or pack.name),
            "assets": str(instance.get("assets") or ""),
            "brand": brand,
            "checkout": checkout,
            "instructions": str(instance.get("instructions") or ""),
            "ops": str(instance.get("ops") or ""),
        }
    )
    keep_on_disk = str(instance.get("keep_or_sell") or "").strip()
    rel = pack.relative_to(ROOT).as_posix() if pack.is_relative_to(ROOT) else str(pack)
    return {
        "kind": "HARBORLINE_DESK_INSTANCE_FIND",
        "gate": False,
        "commons_admission": False,
        "id": HELPER_ID,
        "pack": rel,
        "layout": "instance.json+door.html",
        "brand": brand,
        "sale_id": instance.get("sale_id"),
        "fingerprint": fingerprint,
        "sell_instance_verdict": sell["verdict"],
        "terms_verdict": terms_result.get("verdict", ""),
        "saleable": saleable,
        "keep_or_sell_on_disk": keep_on_disk,
        "did_not_decide_keep_sell": True,
        "did_not_invent_manifest": True,
        "did_not_write_pack_files": True,
        "copy_verdicts": copy_verdicts,
        "errors": errors,
        "miss": [],
        "search_space": search_space(pack),
        "state": "INSTANCE_OK" if not errors else "ERROR",
        "checkout": "NOT_MINTED",
        "marketing": "bryce_only",
        "known_present": known_present(),
        "do_not_write": list(DO_NOT_WRITE),
        "cite": [REMEASURE_ID, WIRE_ID],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pack", default=str(DEFAULT_PACK), help="Harborline instance directory")
    args = parser.parse_args(argv)
    pack = Path(args.pack).resolve()
    result = verify(pack)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["state"] == "INSTANCE_OK":
        return 0
    if result["state"] == "FINDER-FAILED":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
