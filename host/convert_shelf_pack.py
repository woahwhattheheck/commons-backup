#!/usr/bin/env python3
"""$49 convert-shelf pack recipe. Renders the one-page buy-CTA shelf template.

Hermetic --canary: renders sample/context.json against template.html and
validates the splice. The buyer's EXISTING checkout URL is the only link
spliced in. No minted Stripe. No invented payment URL. Autopsy SCRAPPED.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "packs" / "convert-shelf-49-20260917-01"
TEMPLATE_PATH = PACK / "template.html"
SAMPLE_CONTEXT_PATH = PACK / "sample" / "context.json"
SAMPLE_RENDERED_PATH = PACK / "sample" / "shelf.rendered.html"
CITE = "anvil-convert-shelf-49-20260917-01"
SKU = "convert-shelf-49"
WORK_ORDER = "WO-CONVERT-SHELF-49"
PRICE_USD = 49
CHECKOUT_STATUS = "NOT_MINTED"
MAILTO = "tokenjunkielabs@gmail.com"
TURNAROUND = "one business day"
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")
REQUIRED_KEYS = (
    "PRODUCT_NAME",
    "TAGLINE",
    "PRICE_LABEL",
    "PAYMENT_URL",
    "CTA_LABEL",
)
OPTIONAL_KEYS = (
    "BULLET_1",
    "BULLET_2",
    "BULLET_3",
    "PROOF_LINE",
    "FOOTER_CONTACT",
    "ACCENT",
)
ALLOWED_KEYS = REQUIRED_KEYS + OPTIONAL_KEYS
FORBIDDEN_PLACEHOLDER = "MISSING_FIELD"
AUTOPSY_PLINK_PATH = "4gM9AS3Ot8bfeOZ78S43S0g"
REQUIRED_PACK_FILES = (
    "README.md",
    "offer.md",
    "checkout.md",
    "instructions.md",
    "checklist.md",
    "intake.md",
    "sell-blurb.md",
    "door.html",
    "template.html",
    "sample/README.md",
    "sample/context.json",
    "sample/shelf.rendered.html",
)


def validate_context(context: dict[str, Any]) -> list[str]:
    """Reject unusable splice contexts. Returns a list of problems."""
    problems: list[str] = []
    if not isinstance(context, dict):
        return ["context is not an object"]
    for key in REQUIRED_KEYS:
        value = context.get(key)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"missing or empty required field {key}")
    for key, value in context.items():
        if key not in ALLOWED_KEYS:
            problems.append(f"unknown field {key}")
        elif not isinstance(value, str):
            problems.append(f"field {key} is not a string")
    payment_url = str(context.get("PAYMENT_URL", "")).strip()
    if payment_url:
        parsed = urlparse(payment_url)
        if parsed.scheme != "https":
            problems.append("PAYMENT_URL must be an https URL")
        if not parsed.netloc:
            problems.append("PAYMENT_URL has no host")
        if AUTOPSY_PLINK_PATH in payment_url:
            problems.append("PAYMENT_URL is the SCRAPPED Autopsy link")
    return problems


def render(template_text: str, context: dict[str, Any]) -> str:
    """Splice context into the template. Text fields are HTML-escaped.

    PAYMENT_URL is escaped for attribute use only (quotes), never rewritten.
    Unknown {{KEY}} markers left in the output are replaced by MISSING_FIELD
    so a half-filled splice can never ship looking complete.
    """
    problems = validate_context(context)
    if problems:
        raise ValueError("context rejected: " + "; ".join(problems))

    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        value = context.get(key)
        if value is None or not str(value).strip():
            return FORBIDDEN_PLACEHOLDER
        return html.escape(str(value).strip(), quote=True)

    return PLACEHOLDER_RE.sub(substitute, template_text)


def validate_rendered(rendered: str, context: dict[str, Any]) -> dict[str, Any]:
    """Check a rendered shelf: all placeholders resolved, splice present."""
    remaining = sorted(set(PLACEHOLDER_RE.findall(rendered)))
    payment_url = str(context.get("PAYMENT_URL", "")).strip()
    escaped_url = html.escape(payment_url, quote=True)
    return {
        "placeholders_left": remaining,
        "missing_field_markers": rendered.count(FORBIDDEN_PLACEHOLDER),
        "splice_present": f'href="{escaped_url}"' in rendered,
        "title_present": html.escape(str(context.get("PRODUCT_NAME", "")).strip(), quote=True)
        in rendered,
        "clean": not remaining
        and FORBIDDEN_PLACEHOLDER not in rendered
        and f'href="{escaped_url}"' in rendered,
    }


def list_pack_files() -> dict[str, Any]:
    missing = [name for name in REQUIRED_PACK_FILES if not (PACK / name).is_file()]
    return {"required": list(REQUIRED_PACK_FILES), "missing": missing}


def run_canary(root: Path = ROOT) -> dict[str, Any]:
    """Hermetic sample: render the shipped template with the sample context,
    write sample/shelf.rendered.html, and return a receipt dict."""
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    context = json.loads(SAMPLE_CONTEXT_PATH.read_text(encoding="utf-8"))
    rendered = render(template_text, context)
    check = validate_rendered(rendered, context)
    SAMPLE_RENDERED_PATH.write_text(rendered, encoding="utf-8")
    pack_files = list_pack_files()
    return {
        "cite": CITE,
        "sku": SKU,
        "work_order": WORK_ORDER,
        "price_usd": PRICE_USD,
        "checkout": CHECKOUT_STATUS,
        "cash_usd": 0,
        "buyer": None,
        "bryce_as_buyer": False,
        "invented_stripe": False,
        "autopsy_sold": False,
        "context_fields": sorted(context.keys()),
        "payment_url": context["PAYMENT_URL"],
        "rendered": check,
        "pack_missing": pack_files["missing"],
        "splice_only_existing_url": True,
        "turnaround": TURNAROUND,
    }


def _emit(obj: Any) -> None:
    data = (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(data)
        buffer.flush()
    else:
        sys.stdout.write(data.decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="convert-shelf-49 pack recipe")
    parser.add_argument("--canary", action="store_true", help="run hermetic sample render")
    parser.add_argument("--validate-context", metavar="JSON", help="validate a context JSON file")
    parser.add_argument("--render", metavar="JSON", help="render template.html with a context JSON file to stdout")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    if args.canary:
        receipt = run_canary(ROOT)
        if args.json:
            _emit(receipt)
        else:
            print(
                f"{receipt['cite']}: rendered {SAMPLE_RENDERED_PATH.name} "
                f"clean={receipt['rendered']['clean']} checkout={receipt['checkout']}"
            )
        return 0 if receipt["rendered"]["clean"] else 1

    if args.validate_context:
        context = json.loads(Path(args.validate_context).read_text(encoding="utf-8"))
        problems = validate_context(context)
        _emit({"problems": problems, "ok": not problems})
        return 0 if not problems else 1

    if args.render:
        context = json.loads(Path(args.render).read_text(encoding="utf-8"))
        rendered = render(TEMPLATE_PATH.read_text(encoding="utf-8"), context)
        sys.stdout.write(rendered)
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
