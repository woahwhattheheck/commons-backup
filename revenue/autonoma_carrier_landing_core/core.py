# SPDX-License-Identifier: MIT
"""Deterministic offline admission and landing receipts for parallel-agent carriers.

This module deliberately does *not* invoke git, GitHub, CI, network services, or
customer systems. It turns bounded branch evidence into a fail-closed landing
plan and applies that plan to an in-memory idempotency state. A provider adapter
may consume verified MERGE intents, but live provider authority stays outside
this core.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable


SCHEMA_VERSION = 1
_HEX = frozenset("0123456789abcdef")
_ALLOWED_BATCH_KEYS = {
    "schema_version", "batch_id", "base_sha", "carrier_prefix", "branches"
}
_ALLOWED_BRANCH_KEYS = {
    "branch_id", "order", "base_sha", "manifest", "manifest_sha256",
    "observed_paths", "premerge_tests", "postmerge_tests", "candidate_tree_sha",
}
_ALLOWED_MANIFEST_KEYS = {"paths", "purpose"}
_ALLOWED_TEST_KEYS = {"status", "suite_sha256"}
_ALLOWED_REASON_CODES = {
    "FORBIDDEN_PATH", "STALE_BASE", "MANIFEST_MISMATCH",
    "TEST_FAILURE", "OWNERSHIP_COLLISION",
}
_PLAN_KEYS = {
    "schema_version", "batch_id", "base_sha", "carrier_prefix", "input_sha256",
    "landing_order", "branches", "provider_intents", "receipt_sha256",
}
_DECISION_KEYS = {
    "branch_id", "order", "disposition", "reason_codes", "manifest_sha256",
    "observed_paths", "candidate_tree_sha", "premerge_suite_sha256",
    "postmerge_suite_sha256",
}


class LandingInputError(ValueError):
    """Raised when evidence is malformed enough that no plan can be trusted."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require_object(value: Any, *, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LandingInputError(f"{where} must be an object")
    return value


def _require_exact_keys(value: dict[str, Any], allowed: set[str], *, where: str) -> None:
    missing = sorted(allowed - set(value))
    extra = sorted(set(value) - allowed)
    if missing:
        raise LandingInputError(f"{where} is missing fields: {','.join(missing)}")
    if extra:
        raise LandingInputError(f"{where} has unknown fields: {','.join(extra)}")


def _require_text(value: Any, *, where: str) -> str:
    if type(value) is not str or not value.strip():
        raise LandingInputError(f"{where} must be non-empty text")
    if value != value.strip():
        raise LandingInputError(f"{where} must not have surrounding whitespace")
    return value


def _require_sha(value: Any, *, where: str) -> str:
    text = _require_text(value, where=where)
    if (
        len(text) != 64
        or text != text.lower()
        or any(ch not in _HEX for ch in text)
    ):
        raise LandingInputError(f"{where} must be a 64-character lowercase SHA-256")
    return text


def _require_int(value: Any, *, where: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise LandingInputError(f"{where} must be an integer >= {minimum}")
    return value


def _require_path(value: Any, *, where: str) -> str:
    path = _require_text(value, where=where)
    if path.startswith("/") or path.endswith("/"):
        raise LandingInputError(f"{where} must be a relative file path")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise LandingInputError(f"{where} contains an unsafe path segment")
    if "\\" in path or "\x00" in path:
        raise LandingInputError(f"{where} must use safe POSIX separators")
    return path


def _require_paths(value: Any, *, where: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise LandingInputError(f"{where} must be a non-empty list")
    paths = [
        _require_path(item, where=f"{where}[{index}]")
        for index, item in enumerate(value)
    ]
    if len(paths) != len(set(paths)):
        raise LandingInputError(f"{where} contains duplicate paths")
    return paths


def _normalize_prefix(value: Any) -> str:
    prefix = _require_text(value, where="carrier_prefix")
    if prefix.startswith("/") or "\\" in prefix or "\x00" in prefix:
        raise LandingInputError("carrier_prefix must be a safe relative prefix")
    if not prefix.endswith("/"):
        prefix += "/"
    _require_path(prefix[:-1], where="carrier_prefix")
    return prefix


def _normalize_tests(value: Any, *, where: str) -> dict[str, str]:
    obj = _require_object(value, where=where)
    _require_exact_keys(obj, _ALLOWED_TEST_KEYS, where=where)
    status = _require_text(obj["status"], where=f"{where}.status")
    if status not in {"PASS", "FAIL"}:
        raise LandingInputError(f"{where}.status must be PASS or FAIL")
    return {
        "status": status,
        "suite_sha256": _require_sha(
            obj["suite_sha256"], where=f"{where}.suite_sha256"
        ),
    }


def _normalize_branch(value: Any, *, index: int) -> dict[str, Any]:
    where = f"branches[{index}]"
    obj = _require_object(value, where=where)
    _require_exact_keys(obj, _ALLOWED_BRANCH_KEYS, where=where)
    manifest = _require_object(obj["manifest"], where=f"{where}.manifest")
    _require_exact_keys(manifest, _ALLOWED_MANIFEST_KEYS, where=f"{where}.manifest")
    normalized_manifest = {
        "paths": _require_paths(
            manifest["paths"], where=f"{where}.manifest.paths"
        ),
        "purpose": _require_text(
            manifest["purpose"], where=f"{where}.manifest.purpose"
        ),
    }
    return {
        "branch_id": _require_text(obj["branch_id"], where=f"{where}.branch_id"),
        "order": _require_int(obj["order"], where=f"{where}.order"),
        "base_sha": _require_sha(obj["base_sha"], where=f"{where}.base_sha"),
        "manifest": normalized_manifest,
        "manifest_sha256": _require_sha(
            obj["manifest_sha256"], where=f"{where}.manifest_sha256"
        ),
        "observed_paths": _require_paths(
            obj["observed_paths"], where=f"{where}.observed_paths"
        ),
        "premerge_tests": _normalize_tests(
            obj["premerge_tests"], where=f"{where}.premerge_tests"
        ),
        "postmerge_tests": _normalize_tests(
            obj["postmerge_tests"], where=f"{where}.postmerge_tests"
        ),
        "candidate_tree_sha": _require_sha(
            obj["candidate_tree_sha"], where=f"{where}.candidate_tree_sha"
        ),
    }


def normalize_batch(payload: Any) -> dict[str, Any]:
    """Return canonical batch evidence or raise before any plan is produced."""
    batch = _require_object(payload, where="batch")
    _require_exact_keys(batch, _ALLOWED_BATCH_KEYS, where="batch")
    if batch["schema_version"] != SCHEMA_VERSION:
        raise LandingInputError(f"schema_version must be {SCHEMA_VERSION}")
    branches_raw = batch["branches"]
    if not isinstance(branches_raw, list) or not branches_raw:
        raise LandingInputError("branches must be a non-empty list")
    branches = [
        _normalize_branch(item, index=index)
        for index, item in enumerate(branches_raw)
    ]
    ids = [branch["branch_id"] for branch in branches]
    orders = [branch["order"] for branch in branches]
    if len(ids) != len(set(ids)):
        raise LandingInputError("branch_id values must be unique")
    if len(orders) != len(set(orders)):
        raise LandingInputError("branch order values must be unique")
    return {
        "schema_version": SCHEMA_VERSION,
        "batch_id": _require_text(batch["batch_id"], where="batch_id"),
        "base_sha": _require_sha(batch["base_sha"], where="base_sha"),
        "carrier_prefix": _normalize_prefix(batch["carrier_prefix"]),
        "branches": sorted(branches, key=lambda item: (item["order"], item["branch_id"])),
    }


def manifest_sha256(manifest: dict[str, Any]) -> str:
    """Compute the digest a carrier must publish for its declared manifest."""
    return _digest(manifest)


def _inside_carrier(path: str, carrier_prefix: str) -> bool:
    return path.startswith(carrier_prefix) and len(path) > len(carrier_prefix)


def _branch_reasons(
    branch: dict[str, Any], *, batch_base_sha: str, carrier_prefix: str
) -> list[str]:
    reasons: list[str] = []
    declared = branch["manifest"]["paths"]
    observed = branch["observed_paths"]
    if any(not _inside_carrier(path, carrier_prefix) for path in observed):
        reasons.append("FORBIDDEN_PATH")
    if branch["base_sha"] != batch_base_sha:
        reasons.append("STALE_BASE")
    if (
        branch["manifest_sha256"] != manifest_sha256(branch["manifest"])
        or declared != observed
    ):
        reasons.append("MANIFEST_MISMATCH")
    if (
        branch["premerge_tests"]["status"] != "PASS"
        or branch["postmerge_tests"]["status"] != "PASS"
    ):
        reasons.append("TEST_FAILURE")
    return reasons


def build_plan(payload: Any) -> dict[str, Any]:
    """Build a deterministic fail-closed landing receipt from bounded evidence."""
    batch = normalize_batch(payload)
    decisions: list[dict[str, Any]] = []
    landing_order: list[str] = []
    claimed_paths: set[str] = set()

    for branch in batch["branches"]:
        reasons = _branch_reasons(
            branch,
            batch_base_sha=batch["base_sha"],
            carrier_prefix=batch["carrier_prefix"],
        )
        if not reasons and any(path in claimed_paths for path in branch["observed_paths"]):
            reasons.append("OWNERSHIP_COLLISION")
        disposition = "LAND" if not reasons else "HOLD"
        if disposition == "LAND":
            landing_order.append(branch["branch_id"])
            claimed_paths.update(branch["observed_paths"])
        decisions.append(
            {
                "branch_id": branch["branch_id"],
                "order": branch["order"],
                "disposition": disposition,
                "reason_codes": reasons,
                "manifest_sha256": branch["manifest_sha256"],
                "observed_paths": list(branch["observed_paths"]),
                "candidate_tree_sha": branch["candidate_tree_sha"],
                "premerge_suite_sha256": branch["premerge_tests"]["suite_sha256"],
                "postmerge_suite_sha256": branch["postmerge_tests"]["suite_sha256"],
            }
        )

    body = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch["batch_id"],
        "base_sha": batch["base_sha"],
        "carrier_prefix": batch["carrier_prefix"],
        "input_sha256": _digest(batch),
        "landing_order": landing_order,
        "branches": decisions,
        "provider_intents": [
            {
                "operation": "MERGE",
                "branch_id": branch_id,
                "force": False,
                "delete_branch": False,
            }
            for branch_id in landing_order
        ],
    }
    body["receipt_sha256"] = _digest(body)
    return body


def _validate_decisions(
    branches: Any, *, carrier_prefix: str
) -> list[str]:
    if not isinstance(branches, list) or not branches:
        raise LandingInputError("plan.branches must be a non-empty list")
    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    claimed_paths: set[str] = set()
    expected_landing: list[str] = []
    last_order = -1

    for index, raw in enumerate(branches):
        where = f"plan.branches[{index}]"
        row = _require_object(raw, where=where)
        _require_exact_keys(row, _DECISION_KEYS, where=where)
        branch_id = _require_text(row["branch_id"], where=f"{where}.branch_id")
        order = _require_int(row["order"], where=f"{where}.order")
        if branch_id in seen_ids or order in seen_orders:
            raise LandingInputError("plan branch ids and orders must be unique")
        if order <= last_order:
            raise LandingInputError("plan branches must remain in declared order")
        seen_ids.add(branch_id)
        seen_orders.add(order)
        last_order = order
        _require_sha(row["manifest_sha256"], where=f"{where}.manifest_sha256")
        _require_sha(row["candidate_tree_sha"], where=f"{where}.candidate_tree_sha")
        _require_sha(
            row["premerge_suite_sha256"], where=f"{where}.premerge_suite_sha256"
        )
        _require_sha(
            row["postmerge_suite_sha256"], where=f"{where}.postmerge_suite_sha256"
        )
        paths = _require_paths(row["observed_paths"], where=f"{where}.observed_paths")
        disposition = _require_text(row["disposition"], where=f"{where}.disposition")
        reasons = row["reason_codes"]
        if not isinstance(reasons, list) or not all(type(code) is str for code in reasons):
            raise LandingInputError(f"{where}.reason_codes must be a list of strings")
        if len(reasons) != len(set(reasons)) or any(
            code not in _ALLOWED_REASON_CODES for code in reasons
        ):
            raise LandingInputError(f"{where}.reason_codes are not canonical")
        if disposition == "LAND":
            if reasons:
                raise LandingInputError(f"{where} cannot LAND with hold reasons")
            if any(not _inside_carrier(path, carrier_prefix) for path in paths):
                raise LandingInputError(f"{where} LAND escapes the carrier prefix")
            if any(path in claimed_paths for path in paths):
                raise LandingInputError(f"{where} LAND overlaps an earlier carrier")
            claimed_paths.update(paths)
            expected_landing.append(branch_id)
        elif disposition == "HOLD":
            if not reasons:
                raise LandingInputError(f"{where} HOLD requires at least one reason")
        else:
            raise LandingInputError(f"{where}.disposition must be LAND or HOLD")
    return expected_landing


def verify_plan(plan: Any) -> dict[str, Any]:
    """Verify digest *and semantics* before a provider adapter may consume a plan."""
    obj = _require_object(plan, where="plan")
    _require_exact_keys(obj, _PLAN_KEYS, where="plan")
    expected_digest = _digest(
        {key: value for key, value in obj.items() if key != "receipt_sha256"}
    )
    if obj["receipt_sha256"] != expected_digest:
        raise LandingInputError("plan receipt digest mismatch")
    if obj["schema_version"] != SCHEMA_VERSION:
        raise LandingInputError(f"plan.schema_version must be {SCHEMA_VERSION}")
    _require_text(obj["batch_id"], where="plan.batch_id")
    _require_sha(obj["base_sha"], where="plan.base_sha")
    _require_sha(obj["input_sha256"], where="plan.input_sha256")
    _require_sha(obj["receipt_sha256"], where="plan.receipt_sha256")
    carrier_prefix = _normalize_prefix(obj["carrier_prefix"])
    if carrier_prefix != obj["carrier_prefix"]:
        raise LandingInputError("plan.carrier_prefix is not canonical")

    expected_landing = _validate_decisions(
        obj["branches"], carrier_prefix=carrier_prefix
    )
    landing_order = obj["landing_order"]
    if not isinstance(landing_order, list) or not all(
        type(branch_id) is str for branch_id in landing_order
    ):
        raise LandingInputError("plan.landing_order must be a list of strings")
    if landing_order != expected_landing:
        raise LandingInputError("plan.landing_order does not match LAND dispositions")

    expected_intents = [
        {
            "operation": "MERGE",
            "branch_id": branch_id,
            "force": False,
            "delete_branch": False,
        }
        for branch_id in expected_landing
    ]
    if obj["provider_intents"] != expected_intents:
        raise LandingInputError("provider intents do not match canonical landing order")
    return copy.deepcopy(obj)


@dataclass(frozen=True)
class ApplyResult:
    receipt: dict[str, Any]
    new_merges: int
    merge_events: tuple[dict[str, Any], ...]
    state: dict[str, Any]


def apply_plan(plan: Any, state: Any) -> ApplyResult:
    """Apply a verified receipt to an in-memory idempotency state."""
    receipt = verify_plan(plan)
    current = _require_object(state, where="state")
    allowed_state_keys = {"completed_receipts", "landed_branches", "main_green"}
    _require_exact_keys(current, allowed_state_keys, where="state")
    completed = current["completed_receipts"]
    landed = current["landed_branches"]
    if not isinstance(completed, list) or not all(type(v) is str for v in completed):
        raise LandingInputError("state.completed_receipts must be a list of strings")
    if not isinstance(landed, list) or not all(type(v) is str for v in landed):
        raise LandingInputError("state.landed_branches must be a list of strings")
    if len(completed) != len(set(completed)) or len(landed) != len(set(landed)):
        raise LandingInputError("state completion and branch lists must not contain duplicates")
    if type(current["main_green"]) is not bool:
        raise LandingInputError("state.main_green must be boolean")
    if not current["main_green"]:
        raise LandingInputError("main must be green before landing begins")

    next_state = {
        "completed_receipts": list(completed),
        "landed_branches": list(landed),
        "main_green": True,
    }
    receipt_sha = receipt["receipt_sha256"]
    if receipt_sha in next_state["completed_receipts"]:
        return ApplyResult(receipt=receipt, new_merges=0, merge_events=(), state=next_state)

    events: list[dict[str, Any]] = []
    for branch_id in receipt["landing_order"]:
        if branch_id in next_state["landed_branches"]:
            raise LandingInputError(f"branch {branch_id} was already landed outside this receipt")
        next_state["landed_branches"].append(branch_id)
        events.append(
            {
                "operation": "MERGE",
                "branch_id": branch_id,
                "force": False,
                "delete_branch": False,
                "main_green_after": True,
            }
        )
    next_state["completed_receipts"].append(receipt_sha)
    return ApplyResult(
        receipt=receipt,
        new_merges=len(events),
        merge_events=tuple(events),
        state=next_state,
    )


def empty_state() -> dict[str, Any]:
    return {"completed_receipts": [], "landed_branches": [], "main_green": True}


def make_branch(
    *,
    branch_id: str,
    order: int,
    base_sha: str,
    paths: Iterable[str],
    purpose: str,
    candidate_tree_sha: str,
    premerge_status: str = "PASS",
    postmerge_status: str = "PASS",
    observed_paths: Iterable[str] | None = None,
    manifest_digest_override: str | None = None,
) -> dict[str, Any]:
    """Small fixture helper used by deterministic acceptance generators."""
    manifest = {"paths": list(paths), "purpose": purpose}
    observed = list(manifest["paths"] if observed_paths is None else observed_paths)
    return {
        "branch_id": branch_id,
        "order": order,
        "base_sha": base_sha,
        "manifest": manifest,
        "manifest_sha256": manifest_digest_override or manifest_sha256(manifest),
        "observed_paths": observed,
        "premerge_tests": {
            "status": premerge_status,
            "suite_sha256": hashlib.sha256(f"pre:{branch_id}".encode()).hexdigest(),
        },
        "postmerge_tests": {
            "status": postmerge_status,
            "suite_sha256": hashlib.sha256(f"post:{branch_id}".encode()).hexdigest(),
        },
        "candidate_tree_sha": candidate_tree_sha,
    }
