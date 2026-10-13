from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from typing import Any, Iterable

SCHEMA_VERSION = 1
REQUIRED_PATHWAYS = (
    "manufacturing",
    "construction",
    "logistics",
    "healthcare",
    "business_operations",
)
DELIVERY_MODES = {"live_remote", "in_person"}
SERVICES = {"A", "B"}
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class BundleError(ValueError):
    pass


def _pairs_no_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise BundleError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_bytes(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BundleError("input must be UTF-8 JSON") from exc
    try:
        return json.loads(text, object_pairs_hook=_pairs_no_duplicates)
    except BundleError:
        raise
    except json.JSONDecodeError as exc:
        raise BundleError(f"invalid JSON: {exc.msg}") from exc


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_ID_RE.fullmatch(value))


def _aware_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _list_of_nonempty_strings(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and item.strip() for item in value)


def _curriculum_valid(name: str, item: Any, errors: list[str]) -> None:
    if not isinstance(item, dict):
        errors.append(f"{name} must be an object")
        return
    if not _list_of_nonempty_strings(item.get("objectives")):
        errors.append(f"{name}.objectives must be a non-empty string list")
    minutes = item.get("delivery_minutes")
    if not _is_int(minutes) or minutes <= 0:
        errors.append(f"{name}.delivery_minutes must be a positive integer")
    if not _list_of_nonempty_strings(item.get("accessibility")):
        errors.append(f"{name}.accessibility must be a non-empty string list")
    if not _list_of_nonempty_strings(item.get("hands_on_exercises")):
        errors.append(f"{name}.hands_on_exercises must be a non-empty string list")


def _report(
    bundle: Any,
    errors: list[str],
    warnings: list[str],
    *,
    stats: dict[str, Any] | None = None,
    coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        evidence_bytes = _canonical_bytes(bundle)
        evidence_sha256 = _sha256(evidence_bytes)
    except (TypeError, ValueError):
        evidence_sha256 = None
    report = {
        "schema_version": SCHEMA_VERSION,
        "ok": not errors,
        "errors": sorted(errors),
        "warnings": sorted(warnings),
        "evidence_sha256": evidence_sha256,
        "stats": stats or {},
        "coverage": coverage or {},
        "authority": {
            "buyer_acceptance": False,
            "partner_commitment": False,
            "proposal_submission": False,
            "award_or_payment": False,
        },
    }
    report["report_sha256"] = _sha256(_canonical_bytes(report))
    return report

