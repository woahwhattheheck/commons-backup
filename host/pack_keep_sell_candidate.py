#!/usr/bin/env python3
"""Validate KEEP vs SELL business-pack candidates.

This is one candidate loader, not GOAT's factory scaffold. It refuses
invented checkout URLs, agent ad spend, and fake cash. Marketing stays
with Bryce. A checkout URL is legal only when it is already a proven
public rail on the checkout-capability snapshot, or when it is blank
so the owner can paste a live Payment Link later.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any

ROOT_DEFAULT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATE_DIR = os.path.join("revenue", "pack_keep_sell_candidates")
TIERS = frozenset({20, 100, 200, 1000, 10000})
DECISIONS = frozenset({"UNDECIDED", "KEEP", "SELL"})
CHECKOUT_STATES = frozenset({"OWNER_PASTE_REQUIRED", "PROVEN_PUBLIC_RAIL"})
CHANNEL_ID = "C0BU7JAPUH3"


class CandidateError(ValueError):
    pass


def _read(root: str, rel: str) -> str:
    path = os.path.join(root, rel)
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _load(root: str, rel: str) -> Any:
    return json.loads(_read(root, rel))


def proven_public_urls(root: str) -> set[str]:
    import importlib.util

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "checkout_capability.py")
    spec = importlib.util.spec_from_file_location("checkout_capability", path)
    if spec is None or spec.loader is None:
        raise CandidateError("checkout_capability.py is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    row = module.measure_root(root)
    return {
        str(rail["url"])
        for rail in (row.get("projected") or {}).get("public_rails") or []
        if rail.get("url") and rail.get("chargeable") is True
    }


def validate_manifest(root: str, rel: str, manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    pack_id = str(manifest.get("id") or "")
    if not pack_id:
        errors.append("id is required")
    if manifest.get("kind") != "BUSINESS_PACK_CANDIDATE":
        errors.append("kind must be BUSINESS_PACK_CANDIDATE")
    if manifest.get("schema_version") != "commons-pack-keep-sell-candidate/v1":
        errors.append("schema_version is invalid")
    if manifest.get("decision") not in DECISIONS:
        errors.append("decision must be UNDECIDED, KEEP, or SELL")
    if manifest.get("tier_usd") not in TIERS:
        errors.append("tier_usd must be one of %s" % sorted(TIERS))
    if manifest.get("marketing") != "bryce_only":
        errors.append("marketing must be bryce_only")
    if manifest.get("ad_peer"):
        errors.append("ad_peer is forbidden")
    if int(manifest.get("marketing_spend_usd") or 0) != 0:
        errors.append("marketing_spend_usd must be 0")
    if int(manifest.get("cash_usd") or 0) != 0:
        errors.append("cash_usd must be 0 until a receipt exists")
    if manifest.get("buyers_invented") is True:
        errors.append("buyers_invented is forbidden")
    if manifest.get("slack_channel_id") != CHANNEL_ID:
        errors.append("slack_channel_id must be %s" % CHANNEL_ID)
    if manifest.get("scaffold_owned_by") != "GOAT":
        errors.append("scaffold_owned_by must stay GOAT")
    checkout = manifest.get("checkout") if isinstance(manifest.get("checkout"), dict) else {}
    state = checkout.get("state")
    url = checkout.get("url")
    if state not in CHECKOUT_STATES:
        errors.append("checkout.state must be OWNER_PASTE_REQUIRED or PROVEN_PUBLIC_RAIL")
    if url not in (None, ""):
        if not isinstance(url, str):
            errors.append("checkout.url must be a string")
        elif state != "PROVEN_PUBLIC_RAIL":
            errors.append("nonempty checkout.url requires PROVEN_PUBLIC_RAIL")
        elif url not in proven_public_urls(root):
            errors.append("invented checkout URL is forbidden: %s" % url)
    elif state == "PROVEN_PUBLIC_RAIL":
        errors.append("PROVEN_PUBLIC_RAIL requires a measured public rail URL")
    assets = manifest.get("assets") if isinstance(manifest.get("assets"), list) else []
    if not assets:
        errors.append("assets must list at least one file")
    runbook = str(manifest.get("runbook") or "")
    if not runbook:
        errors.append("runbook is required")
    else:
        runbook_path = os.path.join(root, os.path.dirname(rel), runbook)
        if not os.path.isfile(runbook_path):
            errors.append("runbook file missing: %s" % runbook)
    pack_dir = os.path.dirname(rel)
    for asset in assets:
        if not isinstance(asset, str) or not asset:
            errors.append("asset paths must be nonempty strings")
            continue
        if not os.path.isfile(os.path.join(root, pack_dir, asset)):
            errors.append("asset missing: %s" % asset)
    title = manifest.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("title is required")
    return errors


def list_manifests(root: str) -> list[str]:
    base = os.path.join(root, CANDIDATE_DIR)
    if not os.path.isdir(base):
        return []
    found: list[str] = []
    for name in sorted(os.listdir(base)):
        rel = os.path.join(CANDIDATE_DIR, name, "manifest.json")
        if os.path.isfile(os.path.join(root, rel)):
            found.append(rel)
    return found


def measure_root(root: str) -> dict[str, Any]:
    rows = []
    errors: list[str] = []
    for rel in list_manifests(root):
        try:
            manifest = _load(root, rel)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append("%s: %s" % (rel, exc))
            continue
        if not isinstance(manifest, dict):
            errors.append("%s: manifest must be an object" % rel)
            continue
        row_errors = validate_manifest(root, rel, manifest)
        errors.extend("%s: %s" % (rel, item) for item in row_errors)
        rows.append(
            {
                "id": manifest.get("id"),
                "path": rel,
                "decision": manifest.get("decision"),
                "tier_usd": manifest.get("tier_usd"),
                "checkout_state": (manifest.get("checkout") or {}).get("state")
                if isinstance(manifest.get("checkout"), dict)
                else None,
            }
        )
    return {
        "kind": "PACK_KEEP_SELL_CANDIDATE_MEASURE",
        "candidate_count": len(rows),
        "candidates": rows,
        "errors": errors,
        "state": "INTEGRATED" if rows and not errors else "ERROR",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=ROOT_DEFAULT)
    args = parser.parse_args(argv)
    payload = measure_root(args.root)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["state"] == "INTEGRATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
