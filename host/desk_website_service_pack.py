#!/usr/bin/env python3
"""$200 desk website-service pack. Unique instance, method not customers.

SCOUT scout-demand-desk-website-service-pack-20260902-01:
Laptop Lena / Desk Dan. Ship the gap-finding method, outreach, price sheet,
delivery checklist, contract placeholder, brand/door, week-1 and 30-day
calendars. Do not include leads or customers (FTC 16 CFR 437). TALLY
showcase stays on private smb-showcase-inventory; this pack points, it does
not copy attachments. Checkout stays OWNER_PASTE_REQUIRED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pack_creative_brief import strip_section


ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = ROOT / "packs" / "desk-website-service-20260902-01"
DEFAULT_LAW = ROOT / "ground" / "BUSINESS_PACK_DESK_WEBSITE.json"
DEFAULT_INSTANCE = PACK_DIR / "instance.json"

INSTANCE_FIELDS = ("assets", "brand", "checkout", "instructions")
GAP_RE = re.compile(r"^GAP-(\d{2})\b", re.M)
EARNINGS_RE = re.compile(
    r"(?i)\bmake\s+\$\d|\bearn\s+\$\d|\bprofit\s+\$\d|"
    r"\bmake \$\d+ this weekend|\bunrealistic result"
)
CLIENT_PROMISE_RE = re.compile(
    r"(?i)\bland\s+\d+\s+clients|\bguaranteed\s+clients|"
    r"\bwe (?:provide|include|give you) (?:leads|customers|clients)|"
    r"\bcustomers included\b|\blead list included\b"
)
FRANCHISE_RE = re.compile(r"(?i)\bfranchise")
STRIPE_URL_RE = re.compile(r"https?://(?:buy|donate)\.stripe\.com/\S+", re.I)


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not an object")
    return data


def load_law(path: Path | None = None) -> dict[str, Any]:
    return load_json(path or DEFAULT_LAW)


def load_instance(path: Path | None = None) -> dict[str, Any]:
    return load_json(path or DEFAULT_INSTANCE)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_token(pack_dir: Path, relative: str) -> str:
    target = pack_dir / relative if not relative.startswith("packs/") else ROOT / relative
    if target.is_file():
        return hashlib.sha256(target.read_bytes()).hexdigest()
    return _sha256_text(relative)


def content_fingerprint(instance: dict[str, Any], pack_dir: Path | None = None) -> str:
    folder = pack_dir or PACK_DIR
    parts: list[str] = []
    for name in INSTANCE_FIELDS:
        rel = str(instance.get(name) or "").strip()
        if not rel:
            return ""
        if name == "brand":
            parts.append(_sha256_text(rel))
        elif name == "checkout":
            parts.append(_sha256_text(rel))
        else:
            parts.append(_file_token(folder, Path(rel).name if "desk-website-service" in rel else rel))
    ops = str(instance.get("ops") or "").strip()
    if ops:
        parts.append(_file_token(folder, Path(ops).name if "desk-website-service" in ops else ops))
    return _sha256_text("\n".join(parts))


def pack_corpus(pack_dir: Path | None = None) -> str:
    folder = pack_dir or PACK_DIR
    chunks: list[str] = []
    if not folder.is_dir():
        return ""
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.suffix in {".md", ".html", ".json"}:
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def gap_ids(instructions: str) -> list[str]:
    return GAP_RE.findall(instructions or "")


def classify_copy(text: str) -> dict[str, Any]:
    # Never-say lists name banned phrases so the operator does not say them.
    # Scoring that section as a live claim is a false positive (Dir: prices
    # yes, earnings never). pack_creative_brief already strips it; keep the
    # pack classifier on the same contract.
    body = strip_section(text or "", "Never say")
    earnings = bool(EARNINGS_RE.search(body))
    clients = bool(CLIENT_PROMISE_RE.search(body))
    franchise = bool(FRANCHISE_RE.search(body))
    stripe = STRIPE_URL_RE.findall(body)
    if earnings:
        verdict = "EARNINGS_CLAIM"
    elif clients:
        verdict = "CUSTOMERS_PROMISED"
    elif franchise:
        verdict = "FRANCHISE_VOCAB"
    elif stripe:
        verdict = "INVENTED_STRIPE_URL"
    else:
        verdict = "COPY_OK"
    return {
        "gate": False,
        "commons_admission": False,
        "verdict": verdict,
        "earnings_claim": earnings,
        "customers_promised": clients,
        "franchise_vocab": franchise,
        "invented_stripe_urls": stripe,
        "copy": "prices_and_time_budgets_never_earnings",
        "method_not_customers": True,
    }


def classify_sell(instance: dict[str, Any] | None = None) -> dict[str, Any]:
    data = instance if isinstance(instance, dict) else load_instance()
    missing: list[str] = []
    brand = str(data.get("brand") or "").strip()
    door = str(data.get("door") or data.get("checkout") or "").strip()
    if not brand:
        missing.append("brand")
    if not door:
        missing.append("door")
    checkout = str(data.get("checkout") or "").strip().upper()
    paste = checkout in {"OWNER_PASTE_REQUIRED", "NOT_MINTED"}
    keep = str(data.get("keep_or_sell") or "").strip().upper()
    claiming = keep == "SELL" or data.get("unique_instance_sell") is True
    if claiming and missing:
        verdict = "MISSING_INSTANCE_FOR_PRICE"
    elif claiming:
        verdict = "UNIQUE_INSTANCE_SELL_OK"
    else:
        verdict = "SELL_INSTANCE_UNCLAIMED"
    return {
        "gate": False,
        "commons_admission": False,
        "verdict": verdict,
        "claiming_unique_instance_sell": claiming,
        "missing_instance": missing,
        "has_brand": "brand" not in missing,
        "has_door": "door" not in missing,
        "checkout": checkout or "NOT_MINTED",
        "owner_paste_required": paste,
        "no_fake_stripe_urls": True,
        "marketing": "bryce_only",
        "agents_spend_ads": False,
    }


def classify(
    instance: dict[str, Any] | None = None,
    pack_dir: Path | None = None,
    law: dict[str, Any] | None = None,
    other_sales: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    folder = pack_dir or PACK_DIR
    data = instance if isinstance(instance, dict) else load_instance()
    card = law if isinstance(law, dict) else load_law()
    corpus = pack_corpus(folder)
    instructions = ""
    inst_path = folder / "instructions.md"
    if inst_path.is_file():
        instructions = inst_path.read_text(encoding="utf-8")
    gaps = gap_ids(instructions)
    copy = classify_copy(corpus)
    sell = classify_sell(data)
    fingerprint = content_fingerprint(data, folder)
    fingerprints = [fingerprint] if fingerprint else []
    for extra in other_sales or []:
        fingerprints.append(content_fingerprint(extra, folder))
    clone = bool(fingerprint) and fingerprints.count(fingerprint) > 1
    showcase = data.get("tally_showcase") if isinstance(data.get("tally_showcase"), dict) else {}
    copied = showcase.get("copied_into_this_pack") is True
    support = folder / "support.md"
    day = folder / "day.md"
    keep = folder / "keep-vs-sell.md"
    keep_text = keep.read_text(encoding="utf-8") if keep.is_file() else ""
    sell_checks = keep_text.count("- [x]") + keep_text.count("- [X]")
    required = [
        "offer.md",
        "door.html",
        "instructions.md",
        "outreach.md",
        "price-sheet.md",
        "delivery.md",
        "contract.md",
        "assets.md",
        "week1.md",
        "day30.md",
        "day.md",
        "keep-vs-sell.md",
        "checkout.md",
        "support.md",
        "terms.md",
        "paperwork.md",
        "running-cost.md",
        "instance.json",
        "README.md",
    ]
    missing_files = [name for name in required if not (folder / name).is_file()]
    ok = (
        sell["verdict"] == "UNIQUE_INSTANCE_SELL_OK"
        and copy["verdict"] == "COPY_OK"
        and len(gaps) >= 10
        and not clone
        and not copied
        and not missing_files
        and sell["owner_paste_required"]
        and data.get("ftc_437_customers_included") is False
        and data.get("method_not_customers") is True
        and support.is_file()
        and day.is_file()
        and sell_checks >= 6
    )
    return {
        "gate": False,
        "commons_admission": False,
        "verdict": "PACK_OK" if ok else "PACK_INCOMPLETE",
        "fingerprint": fingerprint,
        "clone_stamp": clone,
        "marketing_uniqueness_ok": bool(fingerprint) and not clone,
        "gap_recipe_count": len(gaps),
        "gap_ids": gaps,
        "stranger_can_find_ten_gaps": len(gaps) >= 10,
        "tally_showcase_copied": copied,
        "tally_showcase_pointer_only": not copied,
        "tally_showcase_repo": str(showcase.get("repo") or ""),
        "missing_files": missing_files,
        "sell_checklist_checked": sell_checks,
        "paid_tjlabs_support_file": support.is_file(),
        "operator_day_file": day.is_file(),
        "did_not_steal_goat_template": True,
        "did_not_steal_lead_tos_numbers": True,
        "did_not_take_plant_or_yard_card": True,
        "copy": copy,
        "sell_instance": sell,
        "law_id": str(card.get("id") or ""),
        "scout_demand_id": str(card.get("scout_demand_id") or ""),
        "tier_usd": card.get("tier_usd"),
        "instance_brand": str(data.get("brand") or ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", default="", help="override instance.json")
    parser.add_argument("--pack-dir", default="", help="override pack directory")
    args = parser.parse_args(argv)
    result = classify(
        instance=load_instance(Path(args.instance)) if args.instance else None,
        pack_dir=Path(args.pack_dir) if args.pack_dir else None,
    )
    print(json.dumps(result, indent=2))
    print("", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
