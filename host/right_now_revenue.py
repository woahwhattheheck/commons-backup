#!/usr/bin/env python3
"""Canonical right-now revenue compiler with credential-host Stripe authority.

The frozen core preserves the historical compiler and replay contracts. Current
checkout truth is authorized only by a fresh Stripe readback emitted by a fixed,
host-owned collector outside the repository trust domain. Repository-retained
receipts remain audit evidence only and cannot mint current provider truth.
Human reply and scope-acceptance truth is captured from one canonical source
generation and bound into the final control manifest.
"""

from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host import right_now_human_authority
from host import right_now_revenue_core as _core


for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)


# Hostile tests exec this wrapper under distinct module names in one process.
# Preserve the true core functions and a shared re-entrant lock exactly once
# so later copies cannot capture a sibling wrapper as historical, recurse
# through an unmocked collector, or race hook assignment.
# Pin names match the existing unwrapped-core sentinels on main.
_SENTINEL_CATALOG = "_UNWRAPPED_VALIDATE_CATALOG"
_SENTINEL_BUILD = "_UNWRAPPED_BUILD_CONTROL"
_SENTINEL_LOCK = "_commons_right_now_build_lock"
if not hasattr(_core, _SENTINEL_CATALOG):
    setattr(_core, _SENTINEL_CATALOG, _core.validate_catalog)
if not hasattr(_core, _SENTINEL_BUILD):
    setattr(_core, _SENTINEL_BUILD, _core.build_control)
if not hasattr(_core, _SENTINEL_LOCK):
    setattr(_core, _SENTINEL_LOCK, threading.RLock())

_HISTORICAL_VALIDATE_CATALOG = getattr(_core, _SENTINEL_CATALOG)
_ORIGINAL_BUILD_CONTROL = getattr(_core, _SENTINEL_BUILD)
_CORE_BUILD_LOCK = getattr(_core, _SENTINEL_LOCK)


def _current_utc() -> datetime:
    """Return the production freshness clock; callers cannot supply it."""

    return datetime.now(timezone.utc)


def validate_catalog(
    catalog: dict[str, Any],
) -> dict[str, Any]:
    """Validate catalog truth. No live public checkout exists (retired)."""

    return _HISTORICAL_VALIDATE_CATALOG(catalog)


def _compose_human_outcome_authority(control: dict[str, Any]) -> dict[str, Any]:
    """Bind one captured reply generation into the already-bound core control."""

    truth = control.get("truth")
    blockers = control.get("blockers")
    receipts = control.get("source_receipts")
    if not isinstance(truth, dict) or not isinstance(blockers, list) or not isinstance(receipts, list):
        raise ControlError("right-now control shape drift before human authority composition")

    # The frozen core already consumed and receipt-bound the catalog generation.
    # Do not re-read CATALOG_PATH here: its two human counters are assertions
    # carried forward from that already-built control generation.
    catalog_assertions = {
        "verified_positive_replies": truth.get("verified_positive_replies"),
        "accepted_scopes": truth.get("accepted_scopes"),
    }
    try:
        human_truth = right_now_human_authority.capture_human_truth(catalog_assertions)
    except right_now_human_authority.HumanOutcomeAuthorityError as error:
        raise ControlError(f"human outcome authority failed closed: {error}") from error

    buyer_acceptance = [
        row for row in blockers
        if isinstance(row, dict) and row.get("id") == "BUYER_ACCEPTANCE"
    ]
    if len(buyer_acceptance) != 1:
        raise ControlError("right-now control must contain exactly one BUYER_ACCEPTANCE blocker")

    existing: dict[str, dict[str, Any]] = {}
    for row in receipts:
        if not isinstance(row, dict):
            raise ControlError("right-now source receipt must be an object")
        path_text = row.get("path")
        digest = row.get("sha256")
        if not isinstance(path_text, str) or not isinstance(digest, str):
            raise ControlError("right-now source receipt fields are malformed")
        if path_text in existing:
            raise ControlError(f"duplicate right-now source receipt: {path_text}")
        existing[path_text] = row

    human_receipts = human_truth.get("source_receipts")
    if not isinstance(human_receipts, list) or not human_receipts:
        raise ControlError("human outcome authority returned no source receipts")
    pending: list[dict[str, str]] = []
    seen_human: set[str] = set()
    for row in human_receipts:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise ControlError("human outcome source receipt fields are malformed")
        relative = row["path"]
        digest = row["sha256"]
        if not isinstance(relative, str) or not relative or not isinstance(digest, str):
            raise ControlError("human outcome source receipt fields are malformed")
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ControlError("human outcome source receipt digest is malformed")
        if relative in seen_human:
            raise ControlError(f"duplicate human outcome source receipt: {relative}")
        seen_human.add(relative)
        previous = existing.get(relative)
        if previous is not None:
            if previous["sha256"] != digest:
                raise ControlError(f"human outcome source digest drift: {relative}")
            continue
        pending.append({"path": relative, "sha256": digest})

    # Mutate only after the entire captured generation and manifest reconcile.
    receipts.extend(pending)
    truth["verified_positive_replies"] = human_truth["verified_positive_replies"]
    truth["accepted_scopes"] = human_truth["accepted_scopes"]
    buyer_acceptance[0]["current"] = human_truth["accepted_scopes"]
    control["as_of"] = _latest_as_of(control.get("as_of"), human_truth["as_of"])
    return control


def _compile_core_control() -> dict[str, Any]:
    """Run the frozen core with this module's authority hooks in isolation."""

    with _CORE_BUILD_LOCK:
        previous_catalog = _core.validate_catalog
        try:
            _core.validate_catalog = validate_catalog
            return _ORIGINAL_BUILD_CONTROL()
        finally:
            _core.validate_catalog = previous_catalog


def build_control() -> dict[str, Any]:
    """Compile current checkout truth and canonical human-response authority."""

    return _compose_human_outcome_authority(_compile_core_control())


with _CORE_BUILD_LOCK:
    _core.validate_catalog = validate_catalog
    _core.build_control = build_control


if __name__ == "__main__":
    raise SystemExit(_core.main())
