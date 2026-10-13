#!/usr/bin/env python3
"""Map Harborline's layout through TALLY's desk helper without rewriting either.

Harborline keeps door.html + instance.json (similar-not-clone). TALLY's
verifier defaults to index.html + manifest.json for Sidewalk Signal.
SCOUT asked this seat to compose against the shared helper rather than
minting a second one. The copy-only wrap host/harborline_desk_compose.py
already landed. This leftover maps the Harborline layout onto the TALLY
checks that apply across layouts. It does not call peer verify(), which
would fail closed on the Sidewalk filenames. It does not overwrite the
TALLY helper, Sidewalk Signal, Harborline instance files, or waitlist.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
PEER_HELPER = ROOT / "host" / "business_pack_desk_instance.py"
HARBORLINE = ROOT / "packs" / "desk-website-service-20260902-01"
WAITLIST_HREFS = ("../waitlist.html", "packs/waitlist.html")
BUYER_FACING = ("door.html", "offer.md", "outreach.md")
TEXT_SUFFIXES = (".md", ".html", ".txt")
DO_NOT_OVERWRITE = (
    "host/business_pack_desk_instance.py",
    "test_business_pack_desk_instance.py",
    "packs/sidewalk-signal-web-desk-20260902-01",
    "packs/desk-website-service-20260902-01/door.html",
    "packs/waitlist.html",
    "host/harborline_desk_compose.py",
)


def load_peer(path: Path | None = None) -> Any | None:
    target = path or PEER_HELPER
    if not target.is_file():
        return None
    spec = importlib.util.spec_from_file_location("business_pack_desk_instance", target)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def text_files(pack: Path) -> list[Path]:
    return sorted(
        path
        for path in pack.rglob("*")
        if path.is_file()
        and path.suffix in TEXT_SUFFIXES
        and path.name != "instance.json"
    )


def map_pack(peer_path: Path | None = None, pack_dir: Path | None = None) -> dict[str, Any]:
    folder = pack_dir or HARBORLINE
    peer = load_peer(peer_path)
    errors: list[str] = []
    door = folder / "door.html"
    instance_path = folder / "instance.json"
    checkout = folder / "checkout.md"
    door_text = _read(door) if door.is_file() else ""
    instance: dict[str, Any] = {}
    if instance_path.is_file():
        loaded = json.loads(_read(instance_path))
        if isinstance(loaded, dict):
            instance = loaded

    layout = {
        "tally_door": "index.html",
        "harborline_door": "door.html",
        "tally_manifest": "manifest.json",
        "harborline_manifest": "instance.json",
        "did_not_call_peer_verify": True,
        "similar_not_clone": True,
    }

    if peer is None:
        return {
            "kind": "HARBORLINE_TALLY_PACK_MAP",
            "gate": False,
            "commons_admission": False,
            "verdict": "PACK_MAP_PEER_MISSING",
            "peer_helper": "host/business_pack_desk_instance.py",
            "peer_helper_present": False,
            "shared_helper_single_owner": "tally",
            "harborline_instance": "packs/desk-website-service-20260902-01",
            "layout": layout,
            "errors": ["peer helper missing"],
            "do_not_overwrite": list(DO_NOT_OVERWRITE),
            "checkout": "NOT_MINTED",
            "agents_spend_ads": False,
        }

    if not door_text:
        errors.append("missing Harborline door.html")
    if "<form" in door_text.lower():
        errors.append("Harborline door must not carry a waitlist form")
    if "<script" in door_text.lower():
        errors.append("Harborline door must carry zero scripts")
    if not any(href in door_text for href in WAITLIST_HREFS):
        errors.append("Harborline door must href packs/waitlist.html")
    if "$200" not in door_text:
        errors.append("Harborline door must state the $200 pack price")
    if "NOT_MINTED" not in door_text and "OWNER_PASTE_REQUIRED" not in door_text:
        errors.append("Harborline door must show empty checkout")

    if str(instance.get("brand") or "").strip() != "Harborline Local Sites":
        errors.append("instance.json brand must stay Harborline Local Sites")
    if str(instance.get("door") or "") != "packs/desk-website-service-20260902-01/door.html":
        errors.append("instance.json door must point at Harborline door.html")
    if instance.get("unique_instance_sell") is not True:
        errors.append("instance.json unique_instance_sell must be true")
    if str(instance.get("checkout") or "") != "OWNER_PASTE_REQUIRED":
        errors.append("instance.json checkout must stay OWNER_PASTE_REQUIRED")
    if instance.get("ftc_437_customers_included") is not False:
        errors.append("instance.json must keep method-not-customers")
    if instance.get("agents_spend_ads") is not False:
        errors.append("instance.json agents_spend_ads must be false")

    checkout_text = _read(checkout) if checkout.is_file() else ""
    if "NOT_MINTED" not in checkout_text or "Owner pastes live Payment Link" not in checkout_text:
        errors.append("checkout.md must keep NOT_MINTED and the owner-paste sentence")

    unique = peer._load_unique() if hasattr(peer, "_load_unique") else None
    if unique is None:
        errors.append("peer helper has no _load_unique")
        copy_verdicts: dict[str, str] = {}
        sell_verdict = ""
    else:
        copy_verdicts = {}
        for path in text_files(folder):
            rel = path.relative_to(folder).as_posix()
            text = _read(path)
            copy_verdicts[rel] = unique.classify_copy(text)["verdict"]
            buyer = rel in BUYER_FACING
            # Internal docs (creative_brief Never say) name banned phrases.
            # Buyer-facing files stay fail-closed; the rest stay scored, not
            # errors. Matches host/business_pack_harborline_desk_instance.py.
            if buyer and copy_verdicts[rel] != "COPY_OK":
                errors.append(f"{rel}: {copy_verdicts[rel]}")
            if hasattr(peer, "STRIPE_RE") and peer.STRIPE_RE.search(text):
                errors.append(f"{rel}: invented Stripe URL")
            if hasattr(peer, "ODDS_RE") and peer.ODDS_RE.search(text):
                errors.append(f"{rel}: lottery or odds language")
            if buyer and hasattr(peer, "LEADS_RE") and peer.LEADS_RE.search(text):
                errors.append(f"{rel}: promises leads or customers")
            if rel in BUYER_FACING and hasattr(peer, "FRANCHISE_RE") and peer.FRANCHISE_RE.search(text):
                errors.append(f"{rel}: franchise vocabulary in buyer-facing copy")
            if rel in ("door.html", "offer.md") and hasattr(peer, "HELD_COPY_RE") and peer.HELD_COPY_RE.search(text):
                errors.append(f"{rel}: copy held until owner pastes slots")
        sell = unique.classify_sell_offer(
            {
                "unique_instance_sell": True,
                "brand": str(instance.get("brand") or ""),
                "door": str(instance.get("door") or ""),
            }
        )
        sell_verdict = str(sell.get("verdict") or "")
        if sell_verdict != "UNIQUE_INSTANCE_SELL_OK":
            errors.append(f"sell instance verdict {sell_verdict}")

    terms_slots: dict[str, Any] = {}
    if hasattr(peer, "terms_slots"):
        terms_slots = peer.terms_slots(folder)
        unset = getattr(getattr(peer, "_load_terms")(), "is_unset", None) if hasattr(peer, "_load_terms") else None
        share = terms_slots.get("profit_share_percent")
        fraction = terms_slots.get("partial_ownership_fraction")
        if terms_slots.get("owner_pasted"):
            errors.append("terms.md owner_pasted must stay false until Bryce pastes")
        if callable(unset):
            if not unset(share) or not unset(fraction):
                errors.append("terms.md share slots must stay OWNER_UNSET")
        else:
            if str(share or "").upper() != "OWNER_UNSET" or str(fraction or "").upper() != "OWNER_UNSET":
                errors.append("terms.md share slots must stay OWNER_UNSET")

    return {
        "kind": "HARBORLINE_TALLY_PACK_MAP",
        "gate": False,
        "commons_admission": False,
        "verdict": "PACK_MAP_OK" if not errors else "PACK_MAP_ERROR",
        "peer_helper": "host/business_pack_desk_instance.py",
        "peer_helper_present": True,
        "shared_helper_single_owner": "tally",
        "harborline_instance": "packs/desk-website-service-20260902-01",
        "waitlist_href": True if any(href in door_text for href in WAITLIST_HREFS) else False,
        "waitlist_form_on_harborline": "<form" in door_text.lower(),
        "sell_instance_verdict": sell_verdict,
        "copy_verdicts": copy_verdicts,
        "terms_slots": terms_slots,
        "layout": layout,
        "errors": errors,
        "do_not_overwrite": list(DO_NOT_OVERWRITE),
        "did_not_overwrite_peer": True,
        "did_not_remint_harborline_instance": True,
        "did_not_remint_compose_wrap": True,
        "checkout": "NOT_MINTED",
        "agents_spend_ads": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--peer", default="")
    parser.add_argument("--pack-dir", default="")
    args = parser.parse_args(argv)
    result = map_pack(
        peer_path=Path(args.peer) if args.peer else None,
        pack_dir=Path(args.pack_dir) if args.pack_dir else None,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verdict"] == "PACK_MAP_OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
