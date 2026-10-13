"""Deterministic provider-free release evidence gate for synthetic property configuration changes."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

SCHEMA = "choice-skytouch-release-evidence/v1"
RECEIPT_SCHEMA = "choice-skytouch-release-receipt/v1"
EFFECT_STATE_SCHEMA = "choice-skytouch-effect-ledger/v1"
MAX_BUNDLE_BYTES = 1_048_576
MAX_ITEMS = 512
MAX_TEXT = 256
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_PATH_SEG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class ReleaseEvidenceError(ValueError):
    """Fail-closed validation error."""


@dataclass(frozen=True)
class GateResult:
    receipt: dict[str, Any]
    receipt_sha256: str


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _fail(code: str, detail: str = "") -> None:
    suffix = f":{detail}" if detail else ""
    raise ReleaseEvidenceError(f"{code}{suffix}")


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("EXPECTED_OBJECT", name)
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    got = set(value)
    if got != expected:
        missing = sorted(expected - got)
        extra = sorted(got - expected)
        _fail("SCHEMA_KEYS", f"{name}:missing={missing}:extra={extra}")


def _text(value: Any, name: str, *, identifier: bool = False) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT:
        _fail("INVALID_TEXT", name)
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        _fail("CONTROL_CHARACTER", name)
    if identifier and not _ID_RE.fullmatch(value):
        _fail("INVALID_IDENTIFIER", name)
    return value


def _revision(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("INVALID_REVISION", name)
    return value


def _json_scalar(value: Any, name: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str):
            _text(value, name)
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            _fail("NONFINITE_NUMBER", name)
        # Normalize through decimal text so -0.0 / 1.00 style aliases cannot drift the hash.
        try:
            dec = Decimal(str(value))
        except InvalidOperation:
            _fail("INVALID_NUMBER", name)
        return int(dec) if dec == dec.to_integral_value() else format(dec.normalize(), "f")
    _fail("NON_SCALAR_CONFIG_VALUE", name)


def _path(value: Any, name: str) -> str:
    text = _text(value, name)
    parts = text.split(".")
    if not parts or len(parts) > 12 or any(not _PATH_SEG_RE.fullmatch(part) for part in parts):
        _fail("INVALID_CONFIG_PATH", name)
    return ".".join(parts)


def _snapshot(value: Any, name: str) -> dict[str, Any]:
    row = _object(value, name)
    _exact_keys(row, {"property_id", "revision", "config"}, name)
    property_id = _text(row["property_id"], f"{name}.property_id", identifier=True)
    revision = _revision(row["revision"], f"{name}.revision")
    config = _object(row["config"], f"{name}.config")
    if len(config) > MAX_ITEMS:
        _fail("TOO_MANY_CONFIG_VALUES", name)
    normalized: dict[str, Any] = {}
    for raw_path, raw_value in config.items():
        path = _path(raw_path, f"{name}.config.path")
        if path in normalized:
            _fail("DUPLICATE_CONFIG_PATH", path)
        normalized[path] = _json_scalar(raw_value, f"{name}.config.{path}")
    return {"property_id": property_id, "revision": revision, "config": normalized}


def _changes(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > MAX_ITEMS:
        _fail("INVALID_CHANGES")
    rows: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for index, raw in enumerate(value):
        row = _object(raw, f"changes[{index}]")
        _exact_keys(row, {"path", "before", "after", "effect_kind"}, f"changes[{index}]")
        path = _path(row["path"], f"changes[{index}].path")
        if path in seen_paths:
            _fail("DUPLICATE_DECLARED_PATH", path)
        seen_paths.add(path)
        effect_kind = _text(row["effect_kind"], f"changes[{index}].effect_kind", identifier=True)
        rows.append(
            {
                "path": path,
                "before": _json_scalar(row["before"], f"changes[{index}].before"),
                "after": _json_scalar(row["after"], f"changes[{index}].after"),
                "effect_kind": effect_kind,
            }
        )
    return sorted(rows, key=lambda item: item["path"])


def _invariants(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > MAX_ITEMS:
        _fail("INVALID_INVARIANTS")
    rows: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for index, raw in enumerate(value):
        row = _object(raw, f"invariants[{index}]")
        _exact_keys(row, {"name", "path", "expected"}, f"invariants[{index}]")
        name = _text(row["name"], f"invariants[{index}].name", identifier=True)
        if name in seen_names:
            _fail("DUPLICATE_INVARIANT", name)
        seen_names.add(name)
        rows.append(
            {
                "name": name,
                "path": _path(row["path"], f"invariants[{index}].path"),
                "expected": _json_scalar(row["expected"], f"invariants[{index}].expected"),
            }
        )
    return sorted(rows, key=lambda item: item["name"])


def _normalize_bundle(bundle: Any) -> dict[str, Any]:
    if len(canonical_json(bundle)) > MAX_BUNDLE_BYTES:
        _fail("BUNDLE_TOO_LARGE")
    root = _object(bundle, "bundle")
    _exact_keys(
        root,
        {
            "schema",
            "release_id",
            "base_snapshot_sha256",
            "baseline",
            "candidate",
            "changes",
            "invariants",
        },
        "bundle",
    )
    if root["schema"] != SCHEMA:
        _fail("UNSUPPORTED_SCHEMA")
    release_id = _text(root["release_id"], "release_id", identifier=True)
    expected_base = _text(root["base_snapshot_sha256"], "base_snapshot_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_base):
        _fail("INVALID_BASE_DIGEST")
    baseline = _snapshot(root["baseline"], "baseline")
    candidate = _snapshot(root["candidate"], "candidate")
    changes = _changes(root["changes"])
    invariants = _invariants(root["invariants"])
    return {
        "schema": SCHEMA,
        "release_id": release_id,
        "base_snapshot_sha256": expected_base,
        "baseline": baseline,
        "candidate": candidate,
        "changes": changes,
        "invariants": invariants,
    }


def snapshot_sha256(snapshot: Any) -> str:
    return _digest(_snapshot(snapshot, "snapshot"))


def evaluate(bundle: Any) -> GateResult:
    """Evaluate a synthetic release bundle and return a deterministic fail-closed receipt."""

    normalized = _normalize_bundle(bundle)
    baseline = normalized["baseline"]
    candidate = normalized["candidate"]
    release_id = normalized["release_id"]

    failures: list[dict[str, str]] = []

    actual_base_digest = _digest(baseline)
    if normalized["base_snapshot_sha256"] != actual_base_digest:
        failures.append({"code": "STALE_BASE", "detail": "base_snapshot_sha256"})

    if baseline["property_id"] != candidate["property_id"]:
        failures.append({"code": "PROPERTY_ID_DRIFT", "detail": candidate["property_id"]})
    if candidate["revision"] <= baseline["revision"]:
        failures.append({"code": "NONADVANCING_REVISION", "detail": str(candidate["revision"])})

    declared_by_path = {row["path"]: row for row in normalized["changes"]}
    base_config = baseline["config"]
    target_config = candidate["config"]
    all_paths = sorted(set(base_config) | set(target_config))
    actual_changes = {
        path
        for path in all_paths
        if base_config.get(path, object()) != target_config.get(path, object())
    }
    declared_paths = set(declared_by_path)

    for path in sorted(actual_changes - declared_paths):
        failures.append({"code": "UNDECLARED_MUTATION", "detail": path})
    for path in sorted(declared_paths - actual_changes):
        failures.append({"code": "DECLARED_CHANGE_NOT_APPLIED", "detail": path})

    for path in sorted(declared_paths & actual_changes):
        row = declared_by_path[path]
        if path not in base_config:
            failures.append({"code": "DECLARED_BASE_PATH_MISSING", "detail": path})
            continue
        if path not in target_config:
            failures.append({"code": "DECLARED_TARGET_PATH_MISSING", "detail": path})
            continue
        if base_config[path] != row["before"]:
            failures.append({"code": "DECLARED_BEFORE_MISMATCH", "detail": path})
        if target_config[path] != row["after"]:
            failures.append({"code": "DECLARED_AFTER_MISMATCH", "detail": path})

    invariant_results: list[dict[str, Any]] = []
    for invariant in normalized["invariants"]:
        path = invariant["path"]
        present = path in target_config
        observed = target_config.get(path)
        passed = present and observed == invariant["expected"]
        invariant_results.append(
            {
                "name": invariant["name"],
                "path": path,
                "passed": passed,
                "observed": observed if present else None,
                "expected": invariant["expected"],
            }
        )
        if not passed:
            failures.append({"code": "INVARIANT_FAILED", "detail": invariant["name"]})

    bundle_sha = _digest(normalized)
    candidate_sha = _digest(candidate)

    effect_intents: list[dict[str, str]] = []
    for row in normalized["changes"]:
        logical_material = {
            "release_id": release_id,
            "property_id": baseline["property_id"],
            "path": row["path"],
            "effect_kind": row["effect_kind"],
        }
        logical_effect_id = _digest(logical_material)
        fingerprint = _digest(
            {
                **logical_material,
                "bundle_sha256": bundle_sha,
                "before": row["before"],
                "after": row["after"],
            }
        )
        effect_intents.append(
            {
                "logical_effect_id": logical_effect_id,
                "fingerprint": fingerprint,
                "path": row["path"],
                "effect_kind": row["effect_kind"],
            }
        )

    failures = sorted(failures, key=lambda row: (row["code"], row["detail"]))
    status = "PASS" if not failures else "HOLD"
    payload: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "status": status,
        "release_id": release_id,
        "property_id": baseline["property_id"],
        "base_revision": baseline["revision"],
        "candidate_revision": candidate["revision"],
        "base_snapshot_sha256": actual_base_digest,
        "candidate_snapshot_sha256": candidate_sha,
        "bundle_sha256": bundle_sha,
        "declared_change_count": len(normalized["changes"]),
        "actual_change_count": len(actual_changes),
        "invariants": invariant_results,
        "failures": failures,
        "effect_intents": effect_intents if status == "PASS" else [],
        "external_effect_authorized": False,
        "buyer_acceptance_claimed": False,
        "revenue_claimed": False,
    }
    receipt_sha = _digest(payload)
    receipt = {**payload, "receipt_sha256": receipt_sha}
    return GateResult(receipt=receipt, receipt_sha256=receipt_sha)


def verify_receipt(receipt: Any) -> bool:
    try:
        row = _object(receipt, "receipt")
    except ReleaseEvidenceError:
        return False
    if row.get("schema") != RECEIPT_SCHEMA:
        return False
    digest = row.get("receipt_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        return False
    payload = dict(row)
    payload.pop("receipt_sha256", None)
    try:
        return _digest(payload) == digest
    except (TypeError, ValueError):
        return False


def _normalize_prior_effects(prior_effects: Any) -> dict[str, str]:
    if prior_effects is None:
        return {}
    if isinstance(prior_effects, dict) and prior_effects.get("schema") == EFFECT_STATE_SCHEMA:
        _exact_keys(prior_effects, {"schema", "effects"}, "prior_effects")
        effects = prior_effects["effects"]
    else:
        effects = prior_effects
    mapping = _object(effects, "prior_effects.effects")
    if len(mapping) > MAX_ITEMS * 8:
        _fail("TOO_MANY_PRIOR_EFFECTS")
    normalized: dict[str, str] = {}
    for raw_id, raw_fp in mapping.items():
        effect_id = _text(raw_id, "prior_effects.effect_id")
        fingerprint = _text(raw_fp, "prior_effects.fingerprint")
        if not re.fullmatch(r"[0-9a-f]{64}", effect_id) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            _fail("INVALID_PRIOR_EFFECT")
        normalized[effect_id] = fingerprint
    return normalized


def plan_effect_replay(receipt: Any, prior_effects: Any = None) -> dict[str, Any]:
    """Produce a deterministic provider-free replay plan without performing effects."""

    if not verify_receipt(receipt):
        _fail("INVALID_RECEIPT")
    row = _object(receipt, "receipt")
    if row.get("status") != "PASS":
        _fail("RECEIPT_NOT_PASS")
    if row.get("external_effect_authorized") is not False:
        _fail("RECEIPT_AUTHORITY_DRIFT")
    prior = _normalize_prior_effects(prior_effects)
    new_intents: list[dict[str, str]] = []
    collapsed: list[str] = []
    next_effects = dict(prior)

    intents = row.get("effect_intents")
    if not isinstance(intents, list) or len(intents) > MAX_ITEMS:
        _fail("INVALID_EFFECT_INTENTS")
    seen: set[str] = set()
    for index, raw in enumerate(intents):
        intent = _object(raw, f"effect_intents[{index}]")
        _exact_keys(intent, {"logical_effect_id", "fingerprint", "path", "effect_kind"}, f"effect_intents[{index}]")
        effect_id = _text(intent["logical_effect_id"], f"effect_intents[{index}].logical_effect_id")
        fingerprint = _text(intent["fingerprint"], f"effect_intents[{index}].fingerprint")
        if effect_id in seen:
            _fail("DUPLICATE_EFFECT_INTENT", effect_id)
        seen.add(effect_id)
        if effect_id in prior:
            if prior[effect_id] != fingerprint:
                _fail("EFFECT_REPLAY_CONFLICT", effect_id)
            collapsed.append(effect_id)
            continue
        new_intents.append(dict(intent))
        next_effects[effect_id] = fingerprint

    new_intents.sort(key=lambda item: item["logical_effect_id"])
    collapsed.sort()
    result = {
        "schema": EFFECT_STATE_SCHEMA,
        "source_receipt_sha256": row["receipt_sha256"],
        "new_effect_intents": new_intents,
        "collapsed_effect_ids": collapsed,
        "effect_state": {"schema": EFFECT_STATE_SCHEMA, "effects": dict(sorted(next_effects.items()))},
        "external_effects_performed": False,
    }
    result["plan_sha256"] = _digest(result)
    return result


def load_strict_json(text: str) -> Any:
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_BUNDLE_BYTES:
        _fail("JSON_TOO_LARGE")

    def no_dupes(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail("DUPLICATE_JSON_KEY", key)
            result[key] = value
        return result

    try:
        return json.loads(
            text,
            object_pairs_hook=no_dupes,
            parse_constant=lambda token: _fail("NONFINITE_JSON_NUMBER", token),
        )
    except ReleaseEvidenceError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        _fail("INVALID_JSON", str(exc))


__all__ = [
    "EFFECT_STATE_SCHEMA",
    "GateResult",
    "RECEIPT_SCHEMA",
    "ReleaseEvidenceError",
    "SCHEMA",
    "canonical_json",
    "evaluate",
    "load_strict_json",
    "plan_effect_replay",
    "snapshot_sha256",
    "verify_receipt",
]
