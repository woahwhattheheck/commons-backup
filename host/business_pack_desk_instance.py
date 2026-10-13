#!/usr/bin/env python3
"""Verify one Business Pack instance directory against the pack laws. Not a Commons gate.

Instance: packs/sidewalk-signal-web-desk-20260902-01 (TALLY, answering SCOUT's
`scout-demand-desk-website-service-pack-20260902-01`). Reusable for any
instance directory copied from packs/_template/ that carries a manifest.json.

What it checks (fail closed, exit 1 on any error):
  - every template file is present and non-empty; the door exists;
  - manifest.json hashes equal the bytes on disk (assets, instructions, ops);
  - the instance fingerprint from host/business_pack_unique.py is present and
    a byte-identical second sale would be CLONE_STAMP;
  - brand + door -> classify_sell_offer == UNIQUE_INSTANCE_SELL_OK;
  - every text file -> classify_copy == COPY_OK (no earnings claims);
  - no invented Stripe URLs, no plink_ ids, no lottery/odds language;
  - buyer-facing copy (door, offer, outreach) never says "franchise";
  - the door has zero <script> tags, states the tier price, shows NOT_MINTED,
    and carries the mailto fallback;
  - checkout is OWNER_PASTE_REQUIRED with an empty URL, marketing bryce_only,
    no ad peer, no spend, cash 0, no invented buyers, no leads included.

`--write` refreshes the computed fields in manifest.json from disk.
Marketing stays Bryce. This script never mints, sends, or spends.
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
DEFAULT_PACK = ROOT / "packs" / "sidewalk-signal-web-desk-20260902-01"

TEMPLATE_FILES = ("offer.md", "assets.md", "instructions.md", "week1.md", "checkout.md", "keep-vs-sell.md", "terms.md", "README.md")
# Shared factory slots (paperwork, running cost, employee day). Optional for an instance; non-empty and honest when present.
SLOT_FILES = ("paperwork.md", "running-cost.md", "day.md", "rating.md")
# SCOUT scout-demand-door-sold-once-badge-20260902-01: the door badge is rendered from this verifier's own verdict.
SOLD_ONCE_LINE = "Instance 1 of 1. This brand, this domain, this door are sold once."
SAME_METHOD_LINE = "Built from the same method as our sold instances."
BADGE_OPEN = "<!-- sold-once-badge -->"
BADGE_CLOSE = "<!-- /sold-once-badge -->"
ANCHOR_SLOT_RE = re.compile(r'<code data-slot="anchor_line">(.*?)</code>', re.S)
# Door copy that the paperwork / running-cost / ToS laws hold back until the owner pastes the slots.
HELD_COPY_RE = re.compile(
    r"(?i)we handle your legal paperwork|we set up your llc|compliance guaranteed|paperwork included|with the paperwork done"
    r"|we filed your llc|become a business owner|your own employee and employer|for this price|we did most of the work"
)
TERMS_KEYS = {
    "tjlabs_profit_share_percent": "profit_share_percent",
    "tjlabs_partial_ownership_fraction": "partial_ownership_fraction",
    "owner_pasted": "owner_pasted",
    "counsel_cleared": "counsel_cleared",
}
DOOR = "index.html"
OPS_FILES = ("week1.md", "assets/days-8-30.md")
BUYER_FACING = ("index.html", "offer.md", "assets/outreach-script.md", "assets/brand.md")
TEXT_SUFFIXES = (".md", ".html", ".json", ".txt", ".csv")

STRIPE_RE = re.compile(r"https://(buy|donate)\.stripe\.com/|plink_[A-Za-z0-9]+")
# Affirmative lottery framing and invented odds only; "Not a lottery" (the template's own line) stays legal.
ODDS_RE = re.compile(
    r"(?i)\b(chance to win|enter to win|win a prize|prize draw|sweepstakes|raffle|jackpot)\b"
    r"|\b\d+(\.\d+)?\s*%\s*(odds|chance|probability)\b|\b(odds|chance)\s*(of|=|:)\s*\d"
)
FRANCHISE_RE = re.compile(r"(?i)\bfranchis")
LEADS_RE = re.compile(r"(?i)\b(leads?|customers?|clients?|accounts?)\s+(are\s+)?(included|provided|supplied|guaranteed)\b|\bwe\s+(provide|bring|deliver)\s+(you\s+)?(the\s+)?(leads?|customers?|clients?)\b")
TIERS = {20, 100, 200, 1000, 10000}


def _load_unique():
    spec = importlib.util.spec_from_file_location("business_pack_unique", HERE / "business_pack_unique.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("host/business_pack_unique.py is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_terms():
    spec = importlib.util.spec_from_file_location("tjlabs_pack_terms", HERE / "tjlabs_pack_terms.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("host/tjlabs_pack_terms.py is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def terms_slots(pack: Path) -> dict[str, Any]:
    """Read the four owner slots out of the instance's terms.md (ground/TJLABS_PACK_TERMS law)."""
    slots: dict[str, Any] = {"profit_share_percent": None, "partial_ownership_fraction": None, "owner_pasted": None, "counsel_cleared": None}
    path = pack / "terms.md"
    if not path.is_file():
        return slots
    for line in read_text(path).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key in TERMS_KEYS:
            value = value.strip()
            if TERMS_KEYS[key] in ("owner_pasted", "counsel_cleared"):
                slots[TERMS_KEYS[key]] = value.lower() == "true"
            else:
                slots[TERMS_KEYS[key]] = value
    return slots


def _slot_value(text: str, label: str, anywhere: bool = False) -> str | None:
    """Value after ``label`` on the first line that starts with it (or contains it when ``anywhere``)."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(label) or (anywhere and label in stripped):
            value = stripped.split(label, 1)[1].strip()
            return value.strip("`").split("`")[0].strip() if value else ""
    return None


def slot_status(pack: Path) -> dict[str, Any]:
    """Owner slots from the shared factory files; every value stays OWNER_UNSET until the owner pastes."""
    status: dict[str, Any] = {}
    paperwork = pack / "paperwork.md"
    if paperwork.is_file():
        text = read_text(paperwork)
        status["paperwork_state"] = _slot_value(text, "State:")
        status["paperwork_city"] = _slot_value(text, "City:")
        status["formation_partner_link"] = _slot_value(text, "Link:")
    running = pack / "running-cost.md"
    if running.is_file():
        text = read_text(running)
        status["running_cost_amount"] = _slot_value(text, "Amount:")
        status["running_cost_owner_pasted"] = _slot_value(text, "Owner pasted:")
    day = pack / "day.md"
    if day.is_file():
        status["support_subscription_price"] = _slot_value(read_text(day), "Price:", anywhere=True)
    rating = pack / "rating.md"
    if rating.is_file():
        text = read_text(rating)
        status["rating_badge_url"] = _slot_value(text, "Badge URL:")
        status["rating_report_url"] = _slot_value(text, "Report URL:")
        status["rating_partner_name"] = _slot_value(text, "Partner name:")
        status["rating_bulk_price"] = _slot_value(text, "Bulk price:")
        status["rating_owner_pasted"] = _slot_value(text, "Owner pasted:")
    return status


def terms_verdict(pack: Path) -> dict[str, Any]:
    terms = _load_terms()
    slots = terms_slots(pack)
    text = read_text(pack / "terms.md") if (pack / "terms.md").is_file() else ""
    result = terms.classify_instance({**slots, "terms_text": text})
    return {"terms": slots, "terms_verdict": result["verdict"], "saleable": bool(result["saleable"])}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    # Normalise line endings so a CRLF checkout does not change the fingerprint.
    return sha256_bytes(path.read_bytes().replace(b"\r\n", b"\n"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def load_manifest(pack: Path) -> dict[str, Any]:
    data = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest.json is not an object")
    return data


def asset_rows(pack: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted((pack / "assets").glob("*")):
        if path.is_file():
            rel = path.relative_to(pack).as_posix()
            rows.append({"path": rel, "bytes": len(path.read_bytes().replace(b"\r\n", b"\n")), "sha256": sha256_file(path)})
    return rows


def assets_sha256(rows: list[dict[str, Any]]) -> str:
    return sha256_bytes("\n".join(f"{row['path']}:{row['sha256']}" for row in rows).encode("utf-8"))


def ops_sha256(pack: Path) -> str:
    return sha256_bytes("\n".join(f"{name}:{sha256_file(pack / name)}" for name in OPS_FILES if (pack / name).is_file()).encode("utf-8"))


def checkout_token(manifest: dict[str, Any]) -> str:
    checkout = manifest.get("checkout") if isinstance(manifest.get("checkout"), dict) else {}
    url = str(checkout.get("url") or "").strip()
    if url:
        return url
    return f"{checkout.get('state') or 'OWNER_PASTE_REQUIRED'}:{manifest.get('slug') or ''}"


def text_files(pack: Path) -> list[Path]:
    return sorted(path for path in pack.rglob("*") if path.is_file() and path.suffix in TEXT_SUFFIXES and path.name != "manifest.json")


def compute(pack: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    unique = _load_unique()
    rows = asset_rows(pack)
    fields = {
        "assets_sha256": assets_sha256(rows),
        "brand": str(manifest.get("brand") or "").strip(),
        "checkout": checkout_token(manifest),
        "instructions_sha256": sha256_file(pack / "instructions.md") if (pack / "instructions.md").is_file() else "",
        "ops_sha256": ops_sha256(pack),
    }
    sale = {"sale_id": str(manifest.get("slug") or "instance"), **fields}
    fingerprint = unique.content_fingerprint(sale)
    twin = dict(sale, sale_id=sale["sale_id"] + "-twin")
    clone_check = unique.classify_sales([sale, twin])
    sell = unique.classify_sell_offer(
        {
            "unique_instance_sell": True,
            "brand": fields["brand"],
            "door": str(manifest.get("door") or ""),
        }
    )
    copy_verdicts = {}
    for path in text_files(pack):
        copy_verdicts[path.relative_to(pack).as_posix()] = unique.classify_copy(read_text(path))["verdict"]
    # Sold once: this instance's fingerprint is UNIQUE among the sales the owner has recorded on the manifest,
    # and the named-SELL rule (brand + door) holds. No number is invented; a recorded clone flips the badge.
    recorded = [dict(row) for row in (manifest.get("sales") or []) if isinstance(row, dict)]
    ledger = unique.classify_sales(recorded + [sale])
    own = next((row for row in ledger["sales"] if row["sale_id"] == sale["sale_id"]), {"verdict": "MISSING_FINGERPRINT"})
    sold_once = own["verdict"] == "UNIQUE" and sell["verdict"] == "UNIQUE_INSTANCE_SELL_OK"
    return {
        "sold_once": sold_once,
        "badge_line": SOLD_ONCE_LINE if sold_once else SAME_METHOD_LINE,
        "assets": rows,
        "instance_fields": fields,
        "fingerprint": fingerprint,
        "twin_sale_verdict": next((row["verdict"] for row in clone_check["sales"] if row["sale_id"] == twin["sale_id"]), ""),
        "sell_instance_verdict": sell["verdict"],
        "copy_verdicts": copy_verdicts,
        "slots": slot_status(pack),
        **terms_verdict(pack),
    }


def verify(pack: Path, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    errors: list[str] = []
    manifest = manifest if manifest is not None else load_manifest(pack)
    for name in TEMPLATE_FILES + (DOOR,):
        path = pack / name
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            errors.append(f"missing or empty: {name}")
    computed = compute(pack, manifest) if not errors else None

    if manifest.get("kind") != "BUSINESS_PACK_INSTANCE":
        errors.append("kind must be BUSINESS_PACK_INSTANCE")
    if manifest.get("schema_version") != "commons-business-pack-instance/v1":
        errors.append("schema_version must be commons-business-pack-instance/v1")
    if manifest.get("tier_usd") not in TIERS:
        errors.append("tier_usd must be one of the five tiers")
    if manifest.get("marketing") != "bryce_only":
        errors.append("marketing must be bryce_only")
    if manifest.get("ad_peer"):
        errors.append("ad_peer is forbidden")
    if int(manifest.get("marketing_spend_usd") or 0) != 0:
        errors.append("marketing_spend_usd must be 0")
    if int(manifest.get("cash_usd") or 0) != 0:
        errors.append("cash_usd must be 0 until a dated receipt exists")
    if manifest.get("buyers_invented") is True:
        errors.append("buyers_invented is forbidden")
    if manifest.get("leads_included") is not False or manifest.get("customers_provided") is not False:
        errors.append("leads_included and customers_provided must be false (16 CFR 437 posture: method, not customers)")
    if manifest.get("scaffold_owned_by") != "GOAT":
        errors.append("scaffold_owned_by must stay GOAT")
    if manifest.get("slack_channel_id") != "C0BU7JAPUH3":
        errors.append("slack_channel_id must be C0BU7JAPUH3")
    if manifest.get("gate") is not False or manifest.get("requires_login") is not False or manifest.get("open_door") is not True:
        errors.append("gate must be false, requires_login false, open_door true")
    checkout = manifest.get("checkout") if isinstance(manifest.get("checkout"), dict) else {}
    if checkout.get("state") != "OWNER_PASTE_REQUIRED":
        errors.append("checkout.state must be OWNER_PASTE_REQUIRED until the owner pastes a proven rail")
    if str(checkout.get("url") or "").strip():
        errors.append("checkout.url must stay empty; owner pastes live Payment Link")
    if checkout.get("status") != "NOT_MINTED":
        errors.append("checkout.status must be NOT_MINTED")
    if not str(manifest.get("brand") or "").strip():
        errors.append("brand is required (named unique-instance SELL needs a name)")
    door = str(manifest.get("door") or "")
    if not door or not (ROOT / door).is_file():
        errors.append("door must point at an existing file (named unique-instance SELL needs a door)")

    for name in SLOT_FILES:
        path = pack / name
        if path.is_file() and not path.read_text(encoding="utf-8").strip():
            errors.append(f"empty slot file: {name}")

    if computed:
        for key in ("assets", "instance_fields", "fingerprint", "twin_sale_verdict", "sell_instance_verdict", "copy_verdicts", "slots", "terms", "terms_verdict", "saleable", "sold_once", "badge_line"):
            if manifest.get(key) != computed[key]:
                errors.append(f"manifest.{key} is stale; run --write")
        door_text = read_text(pack / DOOR)
        rendered = door_badge(door_text)
        if rendered is None:
            errors.append("door must carry the sold-once badge block (<!-- sold-once-badge --> ... <!-- /sold-once-badge -->)")
        elif rendered != badge_html(computed["badge_line"]):
            errors.append("door badge disagrees with the verifier verdict; run --write")
        anchor = ANCHOR_SLOT_RE.search(door_text)
        anchor_line = str(manifest.get("anchor_line") or "OWNER_UNSET")
        if anchor is None:
            errors.append('door must carry the owner-paste anchor slot <code data-slot="anchor_line">')
        elif anchor.group(1).strip() != anchor_line:
            errors.append("door anchor slot disagrees with manifest.anchor_line")
        if anchor_line != "OWNER_UNSET" and _load_unique().classify_copy(anchor_line)["verdict"] != "COPY_OK":
            errors.append("anchor_line carries an earnings claim")
        slots = computed["slots"]
        link = str(slots.get("formation_partner_link") or "")
        if re.search(r"(?i)https?://", link):
            errors.append("paperwork.md formation partner link must stay OWNER_UNSET until the owner pastes it")
        amount = str(slots.get("running_cost_amount") or "")
        pasted = str(slots.get("running_cost_owner_pasted") or "").lower()
        if amount and amount.upper() != "OWNER_UNSET" and pasted != "yes":
            errors.append("running-cost.md carries an amount the owner did not paste")
        price = str(slots.get("support_subscription_price") or "")
        if price and price.upper() != "OWNER_UNSET" and not price.upper().startswith("OWNER_UNSET"):
            errors.append("day.md support subscription price must stay OWNER_UNSET until the owner pastes it")
        rating_pasted = str(slots.get("rating_owner_pasted") or "").lower()
        for key in ("rating_badge_url", "rating_report_url"):
            value = str(slots.get(key) or "")
            if re.search(r"(?i)https?://", value) and rating_pasted != "yes":
                errors.append(f"rating.md {key} carries a URL the owner did not paste")
        bulk = str(slots.get("rating_bulk_price") or "")
        if bulk and bulk.upper() != "OWNER_UNSET" and rating_pasted != "yes":
            errors.append("rating.md bulk price must stay OWNER_UNSET until the owner pastes it")
        for rel in ("index.html", "offer.md"):
            if (pack / rel).is_file() and HELD_COPY_RE.search(read_text(pack / rel)):
                errors.append(f"{rel}: copy held back by the paperwork / running-cost / ToS laws until the owner pastes the slots")
        terms = computed["terms"]
        unset = _load_terms().is_unset
        if terms["profit_share_percent"] is None or terms["partial_ownership_fraction"] is None:
            errors.append("terms.md must carry both tjlabs slots (profit share percent, partial ownership fraction)")
        if not terms["owner_pasted"] and not (unset(terms["profit_share_percent"]) and unset(terms["partial_ownership_fraction"])):
            errors.append("terms.md carries a number the owner did not paste; slots stay OWNER_UNSET until Bryce fills them")
        if computed["terms_verdict"] in ("FAKE_STRIPE_URL", "EARNINGS_CLAIM"):
            errors.append(f"terms.md: {computed['terms_verdict']}")
        if computed["saleable"] and not (terms["owner_pasted"] and terms["counsel_cleared"]):
            errors.append("saleable cannot be true before owner paste and counsel clearance")
        if computed["sell_instance_verdict"] != "UNIQUE_INSTANCE_SELL_OK":
            errors.append(f"sell instance verdict {computed['sell_instance_verdict']}")
        if computed["twin_sale_verdict"] != "CLONE_STAMP":
            errors.append("a byte-identical second sale must classify as CLONE_STAMP")
        if not computed["fingerprint"]:
            errors.append("fingerprint is empty")
        for rel, verdict in computed["copy_verdicts"].items():
            if verdict != "COPY_OK":
                errors.append(f"{rel}: {verdict}")
        for path in text_files(pack):
            rel = path.relative_to(pack).as_posix()
            text = read_text(path)
            if STRIPE_RE.search(text):
                errors.append(f"{rel}: invented Stripe URL or plink id")
            if ODDS_RE.search(text):
                errors.append(f"{rel}: lottery or odds language")
            if LEADS_RE.search(text):
                errors.append(f"{rel}: promises leads or customers")
            if rel in BUYER_FACING and FRANCHISE_RE.search(text) and rel != "assets/brand.md":
                errors.append(f"{rel}: franchise vocabulary in buyer-facing copy")
        door_text = read_text(pack / DOOR)
        if "<script" in door_text.lower():
            errors.append("door must carry zero scripts")
        if f"${manifest.get('tier_usd')}" not in door_text:
            errors.append("door must state the tier price")
        if "NOT_MINTED" not in door_text:
            errors.append("door must show NOT_MINTED until the owner pastes a Payment Link")
        if "mailto:tokenjunkielabs@gmail.com" not in door_text:
            errors.append("door must keep the mailto fallback")
        checkout_text = read_text(pack / "checkout.md")
        if "Owner pastes live Payment Link" not in checkout_text or "NOT_MINTED" not in checkout_text:
            errors.append("checkout.md must keep the exact placeholder sentence and NOT_MINTED")
        instructions = read_text(pack / "instructions.md")
        for signal in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"):
            if f"| {signal} |" not in instructions:
                errors.append(f"instructions.md must carry signal {signal}")
        if "ten" not in instructions.lower():
            errors.append("instructions.md must name the ten-business target")

    return {
        "kind": "BUSINESS_PACK_INSTANCE_VERIFY",
        "gate": False,
        "commons_admission": False,
        "pack": pack.relative_to(ROOT).as_posix() if pack.is_relative_to(ROOT) else str(pack),
        "id": manifest.get("id"),
        "fingerprint": (computed or {}).get("fingerprint", ""),
        "sell_instance_verdict": (computed or {}).get("sell_instance_verdict", ""),
        "terms_verdict": (computed or {}).get("terms_verdict", ""),
        "saleable": (computed or {}).get("saleable", False),
        "marketing": "bryce_only",
        "checkout": "NOT_MINTED",
        "errors": errors,
        "state": "INSTANCE_OK" if not errors else "ERROR",
    }


def badge_html(badge_line: str) -> str:
    return f'<p class="badge">{badge_line}</p>'


def door_badge(door_text: str) -> str | None:
    """The rendered badge between the markers, or None when the block is missing."""
    start = door_text.find(BADGE_OPEN)
    end = door_text.find(BADGE_CLOSE)
    if start < 0 or end < 0 or end < start:
        return None
    return door_text[start + len(BADGE_OPEN):end].strip()


def write_door_badge(pack: Path, badge_line: str) -> bool:
    """Rewrite the marked badge block in the door from the verdict; True when the door changed."""
    path = pack / DOOR
    text = read_text(path)
    if door_badge(text) is None:
        return False
    start = text.find(BADGE_OPEN) + len(BADGE_OPEN)
    end = text.find(BADGE_CLOSE)
    updated = text[:start] + badge_html(badge_line) + text[end:]
    if updated != text:
        path.write_text(updated, encoding="utf-8", newline="\n")
        return True
    return False


def write_manifest(pack: Path) -> dict[str, Any]:
    manifest = load_manifest(pack)
    manifest.setdefault("anchor_line", "OWNER_UNSET")
    manifest.update(compute(pack, manifest))
    write_door_badge(pack, manifest["badge_line"])
    # The door is an asset-free file, but its bytes are not part of the fingerprint; recompute nothing else.
    (pack / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pack", default=str(DEFAULT_PACK), help="instance directory (default: the Sidewalk Signal instance)")
    parser.add_argument("--write", action="store_true", help="refresh computed fields in manifest.json from disk")
    args = parser.parse_args(argv)
    pack = Path(args.pack).resolve()
    if args.write:
        write_manifest(pack)
    result = verify(pack)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["state"] == "INSTANCE_OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
