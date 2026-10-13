"""Strict schemas, normalization, collision identities, and filesystem guards."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .catalog import (
    ALLOWED_AUTHORITIES,
    ALLOWED_DEADLINE_AUTHORITIES,
    ALLOWED_MODULES,
    ALLOWED_TARGET_BASIS,
    MANIFEST_SCHEMA,
)

_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9._:/-]{2,119}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_URL_RE = re.compile(r"^https://[^\s]{1,500}$")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_symlink_ancestors(path: Path) -> None:
    for ancestor in (path.parent, *path.parent.parents):
        if ancestor.exists() and ancestor.is_symlink():
            raise ValueError("path ancestor cannot be a symlink")


def load_json_strict(path: str | os.PathLike[str], *, max_bytes: int = 1_000_000) -> Any:
    p = Path(path)
    _reject_symlink_ancestors(p)
    st = p.lstat()
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise ValueError("input must be a regular non-symlink file")
    if st.st_size > max_bytes:
        raise ValueError("input exceeds size bound")
    try:
        text = p.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("input must be UTF-8") from exc
    return json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_obj(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def exact_keys(obj: dict[str, Any], expected: set[str], where: str) -> None:
    got = set(obj)
    if got != expected:
        raise ValueError(f"{where} keys mismatch missing={sorted(expected-got)} extra={sorted(got-expected)}")


def text(value: Any, where: str, *, max_len: int = 500) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len or _CTRL_RE.search(value):
        raise ValueError(f"invalid text at {where}")
    return value


def identifier(value: Any, where: str) -> str:
    value = text(value, where, max_len=120)
    if not _ID_RE.fullmatch(value):
        raise ValueError(f"invalid identifier at {where}")
    return value


def sha(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise ValueError(f"invalid sha256 at {where}")
    return value


def parse_utc(value: Any, where: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z") or "." in value:
        raise ValueError(f"{where} must be canonical whole-second UTC")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(f"invalid UTC timestamp at {where}") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError(f"non-canonical UTC timestamp at {where}")
    return parsed


def parse_date(value: Any, where: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"invalid date at {where}")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid date at {where}") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"non-canonical date at {where}")
    return parsed


def _ordered_unique(values: Any, where: str, *, allowed: set[str] | None = None, max_items: int = 50) -> list[str]:
    if not isinstance(values, list) or len(values) > max_items:
        raise ValueError(f"invalid list at {where}")
    out: list[str] = []
    for i, raw in enumerate(values):
        value = text(raw, f"{where}[{i}]", max_len=600)
        if allowed is not None and value not in allowed:
            raise ValueError(f"unsupported value {value!r} at {where}")
        if value in out:
            raise ValueError(f"duplicate value {value!r} at {where}")
        out.append(value)
    return sorted(out)


def _source(raw: Any, where: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{where} must be object")
    base = {"source_id", "url", "authority", "observed_facts"}
    if set(raw) not in (base, base | {"source_record_sha256"}):
        exact_keys(raw, base, where)
    source_id = identifier(raw["source_id"], f"{where}.source_id")
    url = text(raw["url"], f"{where}.url", max_len=500)
    if not _URL_RE.fullmatch(url):
        raise ValueError(f"invalid HTTPS URL at {where}")
    authority = text(raw["authority"], f"{where}.authority", max_len=40)
    if authority not in ALLOWED_AUTHORITIES:
        raise ValueError(f"unsupported authority at {where}")
    facts = _ordered_unique(raw["observed_facts"], f"{where}.observed_facts", max_items=30)
    record = {"source_id": source_id, "url": url, "authority": authority, "observed_facts": facts}
    computed = sha256_obj(record)
    if "source_record_sha256" in raw and sha(raw["source_record_sha256"], f"{where}.source_record_sha256") != computed:
        raise ValueError(f"source record digest mismatch at {where}")
    record["source_record_sha256"] = computed
    return record


def _deadline(raw: Any, where: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{where} must be object")
    exact_keys(raw, {"date", "time_local", "timezone", "authority"}, where)
    deadline_date = parse_date(raw["date"], f"{where}.date")
    time_local = raw["time_local"]
    if time_local is not None and (not isinstance(time_local, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_local)):
        raise ValueError(f"invalid local time at {where}")
    tz = text(raw["timezone"], f"{where}.timezone", max_len=80)
    authority = text(raw["authority"], f"{where}.authority", max_len=40)
    if authority not in ALLOWED_DEADLINE_AUTHORITIES:
        raise ValueError(f"unsupported deadline authority at {where}")
    return {"date": deadline_date.isoformat(), "time_local": time_local, "timezone": tz, "authority": authority}


def _target(raw: Any, where: str, source_ids: set[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{where} must be object")
    exact_keys(raw, {"organization", "basis", "basis_source_id", "current_bidder_status", "route_state"}, where)
    organization = text(raw["organization"], f"{where}.organization", max_len=160)
    basis = text(raw["basis"], f"{where}.basis", max_len=60)
    if basis not in ALLOWED_TARGET_BASIS:
        raise ValueError(f"unsupported target basis at {where}")
    source_id = identifier(raw["basis_source_id"], f"{where}.basis_source_id")
    if source_id not in source_ids:
        raise ValueError(f"unknown basis source at {where}")
    if raw["current_bidder_status"] != "UNKNOWN":
        raise ValueError("current bidder status must remain UNKNOWN without current bidder evidence")
    if raw["route_state"] != "NOT_ACQUIRED":
        raise ValueError("static pack cannot self-mint a contact route")
    return {"organization": organization, "basis": basis, "basis_source_id": source_id, "current_bidder_status": "UNKNOWN", "route_state": "NOT_ACQUIRED"}


def normalize_manifest(manifest: Any, as_of_utc: str) -> tuple[dict[str, Any], datetime]:
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be object")
    exact_keys(manifest, {"schema", "captured_at_utc", "opportunities"}, "manifest")
    if manifest["schema"] != MANIFEST_SCHEMA:
        raise ValueError("unsupported manifest schema")
    captured_at = parse_utc(manifest["captured_at_utc"], "manifest.captured_at_utc")
    as_of = parse_utc(as_of_utc, "as_of_utc")
    if captured_at > as_of:
        raise ValueError("manifest capture time is in the future")
    raw_ops = manifest["opportunities"]
    if not isinstance(raw_ops, list) or not raw_ops or len(raw_ops) > 50:
        raise ValueError("manifest opportunities must be a bounded non-empty list")
    normalized_ops: list[dict[str, Any]] = []
    seen_ops: set[str] = set()
    for i, raw in enumerate(raw_ops):
        where = f"manifest.opportunities[{i}]"
        if not isinstance(raw, dict):
            raise ValueError(f"{where} must be object")
        exact_keys(raw, {"opportunity_id", "buyer", "solicitation", "deadline", "source_evidence", "allowed_modules", "workshare_wedge", "prime_owned", "target_candidates"}, where)
        op_id = identifier(raw["opportunity_id"], f"{where}.opportunity_id")
        if op_id in seen_ops:
            raise ValueError(f"duplicate opportunity_id: {op_id}")
        seen_ops.add(op_id)
        deadline = _deadline(raw["deadline"], f"{where}.deadline")
        sources_raw = raw["source_evidence"]
        if not isinstance(sources_raw, list) or not sources_raw or len(sources_raw) > 20:
            raise ValueError(f"invalid source evidence at {where}")
        sources = [_source(source, f"{where}.source_evidence[{j}]") for j, source in enumerate(sources_raw)]
        source_ids = {source["source_id"] for source in sources}
        if len(source_ids) != len(sources):
            raise ValueError(f"duplicate source_id in {op_id}")
        if not any(source["authority"] in {"OFFICIAL_BUYER", "OFFICIAL_PORTAL"} for source in sources):
            raise ValueError(f"{op_id} requires at least one official source")
        modules = _ordered_unique(raw["allowed_modules"], f"{where}.allowed_modules", allowed=ALLOWED_MODULES, max_items=4)
        if not modules:
            raise ValueError(f"{op_id} needs at least one workshare module")
        targets_raw = raw["target_candidates"]
        if not isinstance(targets_raw, list) or len(targets_raw) > 30:
            raise ValueError(f"invalid target candidates at {where}")
        targets = [_target(target, f"{where}.target_candidates[{j}]", source_ids) for j, target in enumerate(targets_raw)]
        if len({target["organization"].casefold() for target in targets}) != len(targets):
            raise ValueError(f"duplicate target organization in {op_id}")
        normalized_ops.append({
            "opportunity_id": op_id,
            "buyer": text(raw["buyer"], f"{where}.buyer", max_len=180),
            "solicitation": text(raw["solicitation"], f"{where}.solicitation", max_len=240),
            "deadline": deadline,
            "source_evidence": sorted(sources, key=lambda row: row["source_id"]),
            "allowed_modules": modules,
            "workshare_wedge": _ordered_unique(raw["workshare_wedge"], f"{where}.workshare_wedge", max_items=12),
            "prime_owned": _ordered_unique(raw["prime_owned"], f"{where}.prime_owned", max_items=20),
            "target_candidates": sorted(targets, key=lambda row: row["organization"].casefold()),
        })
    return {"schema": MANIFEST_SCHEMA, "captured_at_utc": captured_at.strftime("%Y-%m-%dT%H:%M:%SZ"), "opportunities": sorted(normalized_ops, key=lambda row: row["opportunity_id"])}, as_of


def collision_key(opportunity_id: str, target_company: str, route_fingerprint_sha256: str) -> str:
    """Build a privacy-safe exclusion key. It grants no claim/send authority."""
    return sha256_obj({
        "opportunity_id": identifier(opportunity_id, "opportunity_id"),
        "target_company": text(target_company, "target_company", max_len=160).casefold(),
        "route_fingerprint_sha256": sha(route_fingerprint_sha256, "route_fingerprint_sha256"),
    })


def write_exclusive(path: str | os.PathLike[str], data: bytes) -> None:
    p = Path(path)
    if p.exists() or p.is_symlink():
        raise FileExistsError(str(p))
    _reject_symlink_ancestors(p)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(p, flags, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
