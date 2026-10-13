#!/usr/bin/env python3
"""$99 CI-red fix pack recipe. Hermetic fail→green canary. No invented Stripe."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "packs" / "ci-fix-99-20260917-01"
FIXTURE = PACK / "sample" / "fixture"
CITE = "latch-ci-fix-pack-99-20260917-01"
CHECKOUT_WIRE_CITE = "latch-ci-fix-pack-99-checkout-wire-20260919-01"
SKU = "ci-fix-pack-99"
WORK_ORDER = "WO-CI-FIX-PACK-99"
PRICE_USD = 99
CHECKOUT_STATUS = "LIVE_PAYMENT_LINK"
BUY_URL = "https://buy.stripe.com/6oU9ASfxb6374alfFo43S0A"
PLINK_ID = "plink_1UHCnTATH4EDE7XDKQlMOnLh"
MAILTO = "tokenjunkielabs@gmail.com"
TURNAROUND = "one business day"
AUTOPSY_PLINK_PATH = "4gM9AS3Ot8bfeOZ78S43S0g"
BUY_URL_RE = re.compile(r"https://buy\.stripe\.com/[A-Za-z0-9]+")
FAIL_RE = re.compile(r"^FAIL:\s+(\S+)", re.M)
ASSERT_RE = re.compile(r"AssertionError:.*", re.M)
MODULE_RE = re.compile(r"ModuleNotFoundError: No module named '([^']+)'")
EXIT_RE = re.compile(r"Process completed with exit code (\d+)")
CANARY_PATCH = {
    "path": "health.py",
    "old": "return 500",
    "new": "return 200",
    "class_id": "unittest_assertion",
}
REQUIRED_PACK_FILES = (
    "README.md",
    "offer.md",
    "checkout.md",
    "instructions.md",
    "checklist.md",
    "pr-body.md",
    "receipt-skeleton.md",
    "intake.md",
    "sell-blurb.md",
    "door.html",
    "sample/README.md",
    "sample/fixture/health.py",
    "sample/fixture/test_health.py",
    "sample/fixture/workflow.yml",
    "sample/fixture/actions-log-red.txt",
)


def classify_log(text: str) -> dict[str, Any]:
    """Name the CI-red class from a unittest or Actions log. No network."""
    fails = FAIL_RE.findall(text or "")
    asserts = ASSERT_RE.findall(text or "")
    modules = MODULE_RE.findall(text or "")
    exits = EXIT_RE.findall(text or "")
    if fails or asserts:
        class_id = "unittest_assertion"
    elif modules:
        class_id = "module_not_found"
    elif exits and exits[-1] != "0":
        class_id = "exit_nonzero"
    else:
        class_id = "unclassified"
    return {
        "class_id": class_id,
        "fails": fails,
        "assertions": asserts,
        "missing_modules": modules,
        "exit_codes": [int(code) for code in exits],
        "in_scope": class_id in {"unittest_assertion", "module_not_found", "exit_nonzero"},
    }


def run_unittest(cwd: Path) -> dict[str, Any]:
    """Run the fixture job the sample workflow would run."""
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "test_health.py", "-v"],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
        "combined": combined,
        "green": proc.returncode == 0,
        "classification": classify_log(combined),
    }


def apply_canary_patch(cwd: Path) -> dict[str, Any]:
    """Thin registered sample patch: health probe 500 → 200."""
    path = cwd / CANARY_PATCH["path"]
    text = path.read_text(encoding="utf-8")
    if CANARY_PATCH["old"] not in text:
        raise ValueError("canary patch target missing")
    path.write_text(
        text.replace(CANARY_PATCH["old"], CANARY_PATCH["new"], 1),
        encoding="utf-8",
    )
    return {
        "path": CANARY_PATCH["path"],
        "old": CANARY_PATCH["old"],
        "new": CANARY_PATCH["new"],
        "applied": True,
        "class_id": CANARY_PATCH["class_id"],
    }


def fill_pr_body(
    diagnosis: dict[str, Any],
    patch: dict[str, Any],
    root: Path | None = None,
) -> str:
    """Fill the pack PR template from a classified red + applied thin patch."""
    pack = (root or ROOT) / "packs" / "ci-fix-99-20260917-01"
    template = (pack / "pr-body.md").read_text(encoding="utf-8")
    replacements = {
        "{{CHECK_NAME}}": "test",
        "{{CLASS_ID}}": str(diagnosis.get("class_id") or "unclassified"),
        "{{FAILS}}": ", ".join(diagnosis.get("fails") or []) or "test_health.HealthTests.test_status_ok",
        "{{PATCH_PATH}}": str(patch.get("path") or ""),
        "{{PATCH_OLD}}": str(patch.get("old") or ""),
        "{{PATCH_NEW}}": str(patch.get("new") or ""),
        "{{CITE}}": CITE,
        "{{WORK_ORDER}}": WORK_ORDER,
    }
    body = template
    for key, value in replacements.items():
        body = body.replace(key, value)
    return body


def run_canary(root: Path | None = None) -> dict[str, Any]:
    """Copy the red fixture, patch once, prove green. No GitHub API. No cash."""
    base = root or ROOT
    fixture = base / "packs" / "ci-fix-99-20260917-01" / "sample" / "fixture"
    log_text = (fixture / "actions-log-red.txt").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "job"
        shutil.copytree(fixture, dest)
        red = run_unittest(dest)
        if red["green"]:
            raise AssertionError("canary fixture must start red")
        diagnosis = classify_log(red["combined"] + "\n" + log_text)
        patch = apply_canary_patch(dest)
        green = run_unittest(dest)
        if not green["green"]:
            raise AssertionError("canary must finish green after the thin patch")
        pr_body = fill_pr_body(diagnosis, patch, root=base)
        return {
            "kind": "CI_FIX_PACK_99_RECEIPT",
            "cite": CITE,
            "work_order": WORK_ORDER,
            "sku": SKU,
            "price_usd": PRICE_USD,
            "checkout": CHECKOUT_STATUS,
            "checkout_url": BUY_URL,
            "plink": PLINK_ID,
            "stripe_ask": False,
            "invented_stripe": False,
            "autopsy_sold": False,
            "cash_usd": 0,
            "buyer": None,
            "bryce_as_buyer": False,
            "sample": True,
            "sample_mode": "hermetic_canary",
            "turnaround": TURNAROUND,
            "mailto": MAILTO,
            "red": {
                "returncode": red["returncode"],
                "fails": red["classification"]["fails"],
                "green": False,
            },
            "diagnosis": diagnosis,
            "patch": patch,
            "green": {
                "returncode": green["returncode"],
                "green": True,
            },
            "pr_body_has_class": diagnosis["class_id"] in pr_body,
            "deliverable": (
                "thin PR that greens the failing unittest the Actions job runs, plus a receipt"
            ),
        }


def _unexpected_buy_urls(text: str) -> list[str]:
    """Any buy.stripe.com URL other than the existing ci-fix-pack-99 PL."""
    return sorted({url for url in BUY_URL_RE.findall(text or "") if url != BUY_URL})


def manifest(root: Path | None = None) -> dict[str, Any]:
    base = root or ROOT
    pack = base / "packs" / "ci-fix-99-20260917-01"
    door = (pack / "door.html").read_text(encoding="utf-8") if (pack / "door.html").is_file() else ""
    checkout = (pack / "checkout.md").read_text(encoding="utf-8") if (pack / "checkout.md").is_file() else ""
    return {
        "kind": "CI_FIX_PACK_99",
        "cite": CITE,
        "checkout_wire_cite": CHECKOUT_WIRE_CITE,
        "work_order": WORK_ORDER,
        "sku": SKU,
        "price_usd": PRICE_USD,
        "checkout": CHECKOUT_STATUS,
        "checkout_url": BUY_URL,
        "plink": PLINK_ID,
        "mailto": MAILTO,
        "pack": str(pack.relative_to(base)).replace("\\", "/"),
        "required": list(REQUIRED_PACK_FILES),
        "missing": [
            name for name in REQUIRED_PACK_FILES if not (pack / name).is_file()
        ],
        "door_has_mailto": MAILTO in door,
        "door_has_live_buy": BUY_URL in door and 'id="checkout"' in door,
        "door_invents_stripe": bool(_unexpected_buy_urls(door) or _unexpected_buy_urls(checkout)),
        "autopsy_plink_present": AUTOPSY_PLINK_PATH in door or AUTOPSY_PLINK_PATH in checkout,
        "checkout_live": CHECKOUT_STATUS in checkout and BUY_URL in checkout and PLINK_ID in checkout,
        "gate": False,
        "login": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CI-fix $99 pack recipe")
    parser.add_argument("--canary", action="store_true", help="run the hermetic fail→green sample")
    parser.add_argument("--manifest", action="store_true", help="print pack file inventory")
    parser.add_argument("--classify-log", default="", help="classify a saved Actions/unittest log")
    parser.add_argument("--json", action="store_true", help="JSON stdout")
    args = parser.parse_args(argv)
    if args.classify_log:
        text = Path(args.classify_log).read_text(encoding="utf-8")
        payload: dict[str, Any] = classify_log(text)
    elif args.manifest:
        payload = manifest()
    else:
        payload = run_canary()
    if args.json or True:
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
