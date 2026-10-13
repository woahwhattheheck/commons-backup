"""Deterministic, authority-bound pursuit portfolio capacity allocation.

Portfolio callers may express owner priority/capacity choices, but they cannot
assert upstream readiness. READY/CURABLE/HOLD/TERMINAL comes only from a
separately supplied upstream authority generation whose canonical SHA-256 is
pinned out of band by the caller of :func:`compile_portfolio`.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INPUT_SCHEMA = "pursuit-portfolio-allocation/input/v2"
RESULT_SCHEMA = "pursuit-portfolio-allocation/result/v2"
RECEIPT_SCHEMA = "pursuit-portfolio-allocation/receipt/v2"
POLICY_SCHEMA = "pursuit-portfolio-allocation/policy/v1"
AUTHORITY_SCHEMA = "pursuit-portfolio-allocation/upstream-authority/v1"
UPSTREAM_STATES = {"READY", "CURABLE", "HOLD", "TERMINAL"}
OUTPUT_STATES = (
    "ALLOCATED_READY",
    "CURABLE_RECOVERY_ALLOCATED",
    "DEFERRED_CAPACITY",
    "HOLD_UPSTREAM",
    "TERMINAL",
    "DEADLINE_BUFFER_BREACHED",
    "HOLD",
)
MAX_TOTAL_OPPORTUNITIES = 64
MAX_ALLOCATABLE = 20
MAX_POOLS = 8
MAX_FILE_BYTES = 2_000_000
SAFE_INT = 9_000_000_000_000_000
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_FORBIDDEN_REF = re.compile(r"(?:@|mailto:|https?://|password|secret|bearer|api[_-]?key|token=)", re.I)


class PortfolioError(ValueError):
    """Fail-closed validation, optimization, publication, or verification error."""


@dataclass(frozen=True)
class CompiledPortfolio:
    result: dict[str, Any]
    result_bytes: bytes
    markdown_bytes: bytes
    receipt: dict[str, Any]
    receipt_bytes: bytes


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in items:
        if key in out:
            raise PortfolioError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _bad_number(value: str) -> None:
    raise PortfolioError(f"non-finite JSON number forbidden: {value}")


def _bad_float(value: str) -> None:
    raise PortfolioError(f"floating-point JSON number forbidden: {value}")


def load_json_bytes(raw: bytes, label: str = "input") -> dict[str, Any]:
    if not isinstance(raw, (bytes, bytearray)):
        raise PortfolioError(f"{label}: bytes required")
    if len(raw) > MAX_FILE_BYTES:
        raise PortfolioError(f"{label}: exceeds {MAX_FILE_BYTES} byte bound")
    if bytes(raw).startswith(b"\xef\xbb\xbf"):
        raise PortfolioError(f"{label}: UTF-8 BOM forbidden")
    try:
        value = json.loads(
            bytes(raw).decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_bad_number,
            parse_float=_bad_float,
        )
    except PortfolioError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise PortfolioError(f"{label}: invalid JSON/UTF-8") from exc
    if not isinstance(value, dict):
        raise PortfolioError(f"{label}: top level must be an object")
    return value


def _open_regular_fd(path: str | Path, label: str) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(os.fspath(path), flags)
    except OSError as exc:
        raise PortfolioError(f"{label}: cannot open regular non-symlink file") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise PortfolioError(f"{label}: regular non-symlink file required")
        if info.st_size > MAX_FILE_BYTES:
            raise PortfolioError(f"{label}: exceeds {MAX_FILE_BYTES} byte bound")
        return fd, info
    except Exception:
        os.close(fd)
        raise


def _read_fd_bounded(fd: int, expected: os.stat_result, label: str) -> bytes:
    chunks: list[bytes] = []
    remaining = MAX_FILE_BYTES + 1
    while remaining:
        chunk = os.read(fd, min(131072, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    raw = b"".join(chunks)
    if len(raw) > MAX_FILE_BYTES:
        raise PortfolioError(f"{label}: exceeds {MAX_FILE_BYTES} byte bound")
    after = os.fstat(fd)
    if (after.st_dev, after.st_ino) != (expected.st_dev, expected.st_ino):
        raise PortfolioError(f"{label}: descriptor generation changed")
    if after.st_size != len(raw):
        raise PortfolioError(f"{label}: changed while reading")
    return raw


def read_regular_bytes(path: str | Path, label: str = "input") -> bytes:
    fd, info = _open_regular_fd(path, label)
    try:
        return _read_fd_bounded(fd, info, label)
    finally:
        os.close(fd)


def load_regular_json(path: str | Path, label: str = "input") -> dict[str, Any]:
    return load_json_bytes(read_regular_bytes(path, label), label)


def _json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _keys(value: Any, expected: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PortfolioError(f"{where}: object required")
    got = set(value)
    if got != expected:
        raise PortfolioError(f"{where}: keys mismatch missing={sorted(expected-got)} extra={sorted(got-expected)}")
    return value


def _text(value: Any, where: str, *, limit: int = 128, token: bool = False) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise PortfolioError(f"{where}: non-empty string <= {limit} chars required")
    if any(ord(ch) < 32 for ch in value):
        raise PortfolioError(f"{where}: control characters forbidden")
    if token and not _TOKEN.fullmatch(value):
        raise PortfolioError(f"{where}: invalid token")
    return value


def _opaque(value: Any, where: str) -> str:
    value = _text(value, where, limit=128, token=True)
    if _FORBIDDEN_REF.search(value):
        raise PortfolioError(f"{where}: PII/secret/network-shaped durable ref forbidden")
    return value


def _sha(value: Any, where: str) -> str:
    value = _text(value, where, limit=64)
    if not _SHA.fullmatch(value):
        raise PortfolioError(f"{where}: lowercase SHA-256 required")
    return value


def _int(value: Any, where: str, lo: int = 0, hi: int = SAFE_INT) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PortfolioError(f"{where}: integer required (bool forbidden)")
    if not lo <= value <= hi:
        raise PortfolioError(f"{where}: integer out of range [{lo}, {hi}]")
    return value


def _dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _ts(value: Any, where: str) -> str:
    value = _text(value, where, limit=20)
    try:
        if not _TS.fullmatch(value):
            raise ValueError
        _dt(value)
    except ValueError as exc:
        raise PortfolioError(f"{where}: canonical RFC3339 UTC-second timestamp required") from exc
    return value


def _canonical_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _effort(raw: Any, where: str) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_POOLS:
        raise PortfolioError(f"{where}: 1..{MAX_POOLS} effort rows required")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, value in enumerate(raw):
        row_where = f"{where}[{idx}]"
        value = _keys(value, {"pool_id", "units"}, row_where)
        pool_id = _opaque(value["pool_id"], f"{row_where}.pool_id")
        if pool_id in seen:
            raise PortfolioError(f"{where}: duplicate pool_id {pool_id}")
        seen.add(pool_id)
        rows.append({"pool_id": pool_id, "units": _int(value["units"], f"{row_where}.units", 1, 10**9)})
    return sorted(rows, key=lambda x: x["pool_id"])


def _opportunity(raw: Any, idx: int) -> dict[str, Any]:
    where = f"opportunities[{idx}]"
    raw = _keys(raw, {
        "opportunity_id", "revision", "source_sha256", "upstream_receipt_sha256",
        "evidence_ref", "response_deadline", "priority_units", "effort", "min_buffer_minutes",
    }, where)
    deadline_raw = raw["response_deadline"]
    deadline = "NO_DEADLINE" if deadline_raw == "NO_DEADLINE" else _ts(deadline_raw, f"{where}.response_deadline")
    return {
        "effort": _effort(raw["effort"], f"{where}.effort"),
        "evidence_ref": _opaque(raw["evidence_ref"], f"{where}.evidence_ref"),
        "min_buffer_minutes": _int(raw["min_buffer_minutes"], f"{where}.min_buffer_minutes", 0, 525600),
        "opportunity_id": _opaque(raw["opportunity_id"], f"{where}.opportunity_id"),
        "priority_units": _int(raw["priority_units"], f"{where}.priority_units", 1, 10**9),
        "response_deadline": deadline,
        "revision": _int(raw["revision"], f"{where}.revision", 1, 10**9),
        "source_sha256": _sha(raw["source_sha256"], f"{where}.source_sha256"),
        "upstream_receipt_sha256": _sha(raw["upstream_receipt_sha256"], f"{where}.upstream_receipt_sha256"),
    }


def _policy(raw: Any) -> dict[str, Any]:
    raw = _keys(raw, {"schema", "revision", "policy_sha256", "horizon_start", "horizon_end", "evidence_max_age_seconds", "pools"}, "policy")
    if raw["schema"] != POLICY_SCHEMA:
        raise PortfolioError("policy.schema: unsupported schema")
    pools_raw = raw["pools"]
    if not isinstance(pools_raw, list) or not 1 <= len(pools_raw) <= MAX_POOLS:
        raise PortfolioError(f"policy.pools: 1..{MAX_POOLS} rows required")
    pools: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, value in enumerate(pools_raw):
        where = f"policy.pools[{idx}]"
        value = _keys(value, {"pool_id", "available_units", "reserve_units"}, where)
        pool_id = _opaque(value["pool_id"], f"{where}.pool_id")
        if pool_id in seen:
            raise PortfolioError(f"policy.pools: duplicate pool_id {pool_id}")
        seen.add(pool_id)
        available = _int(value["available_units"], f"{where}.available_units", 0, 10**9)
        reserve = _int(value["reserve_units"], f"{where}.reserve_units", 0, 10**9)
        if reserve > available:
            raise PortfolioError(f"{where}: reserve_units exceeds available_units")
        pools.append({"available_units": available, "pool_id": pool_id, "reserve_units": reserve})
    start = _ts(raw["horizon_start"], "policy.horizon_start")
    end = _ts(raw["horizon_end"], "policy.horizon_end")
    if _dt(end) <= _dt(start):
        raise PortfolioError("policy: horizon_end must be after horizon_start")
    normalized = {
        "evidence_max_age_seconds": _int(raw["evidence_max_age_seconds"], "policy.evidence_max_age_seconds", 1, 31536000),
        "horizon_end": end,
        "horizon_start": start,
        "pools": sorted(pools, key=lambda x: x["pool_id"]),
        "revision": _int(raw["revision"], "policy.revision", 1, 10**9),
        "schema": POLICY_SCHEMA,
    }
    claimed = _sha(raw["policy_sha256"], "policy.policy_sha256")
    if claimed != _digest(_json(normalized)):
        raise PortfolioError("policy.policy_sha256: does not bind normalized policy bytes")
    return {**normalized, "policy_sha256": claimed}


def normalize_input(value: dict[str, Any]) -> dict[str, Any]:
    value = _keys(value, {"schema", "portfolio_id", "policy", "opportunities"}, "input")
    if value["schema"] != INPUT_SCHEMA:
        raise PortfolioError("input.schema: unsupported schema")
    policy = _policy(value["policy"])
    raw_opportunities = value["opportunities"]
    if not isinstance(raw_opportunities, list) or not 1 <= len(raw_opportunities) <= MAX_TOTAL_OPPORTUNITIES:
        raise PortfolioError(f"input.opportunities: 1..{MAX_TOTAL_OPPORTUNITIES} rows required")
    opportunities = [_opportunity(raw, idx) for idx, raw in enumerate(raw_opportunities)]
    seen: dict[str, dict[str, Any]] = {}
    for opp in opportunities:
        ident = opp["opportunity_id"]
        if ident in seen:
            prior = seen[ident]
            if prior["revision"] == opp["revision"] and (prior["source_sha256"] != opp["source_sha256"] or prior["upstream_receipt_sha256"] != opp["upstream_receipt_sha256"]):
                raise PortfolioError(f"input.opportunities: changed bytes under {ident}@{opp['revision']}")
            raise PortfolioError(f"input.opportunities: duplicate opportunity_id {ident}")
        seen[ident] = opp
    return {"opportunities": sorted(opportunities, key=lambda x: x["opportunity_id"]), "policy": policy, "portfolio_id": _opaque(value["portfolio_id"], "input.portfolio_id"), "schema": INPUT_SCHEMA}


def _authority_row(raw: Any, idx: int) -> dict[str, Any]:
    where = f"upstream_authority.rows[{idx}]"
    raw = _keys(raw, {"opportunity_id", "revision", "source_sha256", "upstream_receipt_sha256", "upstream_state", "evidence_captured_at"}, where)
    state = _text(raw["upstream_state"], f"{where}.upstream_state", token=True)
    if state not in UPSTREAM_STATES:
        raise PortfolioError(f"{where}.upstream_state: unsupported state")
    return {
        "evidence_captured_at": _ts(raw["evidence_captured_at"], f"{where}.evidence_captured_at"),
        "opportunity_id": _opaque(raw["opportunity_id"], f"{where}.opportunity_id"),
        "revision": _int(raw["revision"], f"{where}.revision", 1, 10**9),
        "source_sha256": _sha(raw["source_sha256"], f"{where}.source_sha256"),
        "upstream_receipt_sha256": _sha(raw["upstream_receipt_sha256"], f"{where}.upstream_receipt_sha256"),
        "upstream_state": state,
    }


def normalize_upstream_authority(value: dict[str, Any]) -> dict[str, Any]:
    value = _keys(value, {"schema", "revision", "generated_at", "rows"}, "upstream_authority")
    if value["schema"] != AUTHORITY_SCHEMA:
        raise PortfolioError("upstream_authority.schema: unsupported schema")
    rows_raw = value["rows"]
    if not isinstance(rows_raw, list) or len(rows_raw) > MAX_TOTAL_OPPORTUNITIES:
        raise PortfolioError(f"upstream_authority.rows: 0..{MAX_TOTAL_OPPORTUNITIES} rows required")
    rows = [_authority_row(row, idx) for idx, row in enumerate(rows_raw)]
    seen: set[str] = set()
    for row in rows:
        if row["opportunity_id"] in seen:
            raise PortfolioError(f"upstream_authority.rows: duplicate opportunity_id {row['opportunity_id']}")
        seen.add(row["opportunity_id"])
    return {
        "generated_at": _ts(value["generated_at"], "upstream_authority.generated_at"),
        "revision": _int(value["revision"], "upstream_authority.revision", 1, 10**9),
        "rows": sorted(rows, key=lambda x: x["opportunity_id"]),
        "schema": AUTHORITY_SCHEMA,
    }


def upstream_authority_sha256(value: dict[str, Any]) -> str:
    return _digest(_json(normalize_upstream_authority(value)))


def _validated_authority(value: dict[str, Any], trusted_sha256: str) -> tuple[dict[str, Any], str]:
    trusted = _sha(trusted_sha256, "trusted_upstream_authority_sha256")
    normalized = normalize_upstream_authority(value)
    actual = _digest(_json(normalized))
    if actual != trusted:
        raise PortfolioError("upstream authority: trusted SHA-256 mismatch")
    return normalized, actual


def _validate_evaluation_time(source: dict[str, Any], evaluated_at: str) -> None:
    policy = source["policy"]
    if not (_dt(policy["horizon_start"]) <= _dt(evaluated_at) < _dt(policy["horizon_end"])):
        raise PortfolioError("evaluated_at: outside owner planning horizon")


def _authority_for(opp: dict[str, Any], authority_map: dict[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, list[str]]:
    row = authority_map.get(opp["opportunity_id"])
    if row is None:
        return None, ["UPSTREAM_AUTHORITY_MISSING"]
    for key in ("revision", "source_sha256", "upstream_receipt_sha256"):
        if row[key] != opp[key]:
            return None, [f"UPSTREAM_AUTHORITY_BINDING_MISMATCH:{key}"]
    return row, []


def _preclassify(opp: dict[str, Any], authority_row: dict[str, Any] | None, authority_reasons: list[str], policy: dict[str, Any], evaluated_at: str) -> tuple[str, list[str], str]:
    if authority_row is None:
        return "HOLD", authority_reasons, "UNBOUND"
    state = authority_row["upstream_state"]
    if state == "TERMINAL":
        return "TERMINAL", ["UPSTREAM_TERMINAL"], state
    if state == "HOLD":
        return "HOLD_UPSTREAM", ["UPSTREAM_HOLD"], state
    age = int((_dt(evaluated_at) - _dt(authority_row["evidence_captured_at"])).total_seconds())
    if age < 0:
        return "HOLD", ["FUTURE_UPSTREAM_EVIDENCE"], state
    if age > policy["evidence_max_age_seconds"]:
        return "HOLD", ["STALE_UPSTREAM_EVIDENCE"], state
    pool_ids = {p["pool_id"] for p in policy["pools"]}
    missing = sorted(row["pool_id"] for row in opp["effort"] if row["pool_id"] not in pool_ids)
    if missing:
        return "HOLD", [f"MISSING_CAPACITY_POOL:{pool_id}" for pool_id in missing], state
    deadline = opp["response_deadline"]
    if deadline != "NO_DEADLINE":
        remaining = int((_dt(deadline) - _dt(evaluated_at)).total_seconds())
        if remaining <= 0 or remaining < opp["min_buffer_minutes"] * 60:
            return "DEADLINE_BUFFER_BREACHED", ["DEADLINE_OR_MINIMUM_BUFFER_BREACHED"], state
    return "ELIGIBLE", [], state


def _objective_better(priority: int, ids: tuple[str, ...], total_effort: int, best_priority: int, best_ids: tuple[str, ...], best_effort: int) -> bool:
    if priority != best_priority:
        return priority > best_priority
    if len(ids) != len(best_ids):
        return len(ids) > len(best_ids)
    if total_effort != best_effort:
        return total_effort < best_effort
    return ids < best_ids


def _solve_exact(eligible: list[dict[str, Any]], usable: dict[str, int]) -> tuple[tuple[str, ...], dict[str, int], int, int]:
    if len(eligible) > MAX_ALLOCATABLE:
        raise PortfolioError(f"exact solver bound exceeded: {len(eligible)} allocatable candidates > {MAX_ALLOCATABLE}; split planning horizon or reduce candidates")
    candidates = sorted(eligible, key=lambda x: x["opportunity_id"])
    suffix_priority = [0] * (len(candidates) + 1)
    for idx in range(len(candidates) - 1, -1, -1):
        suffix_priority[idx] = suffix_priority[idx + 1] + candidates[idx]["priority_units"]
    best_priority = -1
    best_ids: tuple[str, ...] = ()
    best_effort = SAFE_INT
    best_used = {pool_id: 0 for pool_id in usable}
    nodes = 0

    def dfs(idx: int, priority: int, ids: tuple[str, ...], total_effort: int, used: dict[str, int]) -> None:
        nonlocal best_priority, best_ids, best_effort, best_used, nodes
        nodes += 1
        if priority + suffix_priority[idx] < best_priority:
            return
        if priority + suffix_priority[idx] == best_priority and len(ids) + (len(candidates) - idx) < len(best_ids):
            return
        if idx == len(candidates):
            if _objective_better(priority, ids, total_effort, best_priority, best_ids, best_effort):
                best_priority, best_ids, best_effort, best_used = priority, ids, total_effort, dict(used)
            return
        candidate = candidates[idx]
        effort_map = {row["pool_id"]: row["units"] for row in candidate["effort"]}
        if all(used.get(pool_id, 0) + units <= usable[pool_id] for pool_id, units in effort_map.items()):
            next_used = dict(used)
            for pool_id, units in effort_map.items():
                next_used[pool_id] += units
            dfs(idx + 1, priority + candidate["priority_units"], ids + (candidate["opportunity_id"],), total_effort + sum(effort_map.values()), next_used)
        dfs(idx + 1, priority, ids, total_effort, used)

    dfs(0, 0, (), 0, {pool_id: 0 for pool_id in usable})
    if best_priority < 0:
        raise PortfolioError("exact solver failed to certify a solution")
    return best_ids, best_used, best_priority, nodes


def _md(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def render_markdown(result: dict[str, Any]) -> bytes:
    lines = [
        "# Pursuit Portfolio Allocation", "",
        f"- Portfolio: `{_md(result['portfolio_id'])}`",
        f"- Evaluated at: `{result['evaluated_at']}`",
        f"- Upstream authority: `{result['upstream_authority_sha256']}`",
        f"- Policy revision: `{result['policy_revision']}` / `{result['policy_sha256']}`",
        f"- Selected owner-priority units: `{result['selected_priority_units']}`",
        f"- Exact solver candidates / search nodes: `{result['solver']['candidate_count']}` / `{result['solver']['search_nodes']}`",
        "- Authority: **owner review only; no contact, submission, pricing, staffing, scheduling, spend, payment, award, probability, or revenue authority**",
        "", "## Capacity pools", "",
        "| Pool | Available | Reserve | Usable | Allocated | Headroom |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in result["capacity"]:
        lines.append(f"| {_md(row['pool_id'])} | {row['available_units']} | {row['reserve_units']} | {row['usable_units']} | {row['allocated_units']} | {row['headroom_units']} |")
    lines += ["", "## Opportunity review", "", "| Opportunity | Upstream | Priority | State | Reasons / limiting capacity |", "|---|---|---:|---|---|"]
    for row in result["opportunities"]:
        reasons = row["reasons"] + [f"LIMIT:{x['pool_id']}+{x['additional_units']}" for x in row["individual_fit_counterfactual"]]
        lines.append(f"| {_md(row['opportunity_id'])} | {row['upstream_state']} | {row['priority_units']} | {row['allocation_state']} | {_md(', '.join(reasons) or '—')} |")
    lines += ["", "## Interpretation boundary", "", "`ALLOCATED_READY` and `CURABLE_RECOVERY_ALLOCATED` are possible only when the opportunity identity is exactly bound by the separately pinned upstream authority generation. Allocation means owner-capacity fit only; it does not grant external action authority.", ""]
    return "\n".join(lines).encode("utf-8")


def compile_portfolio(value: dict[str, Any], *, upstream_authority: dict[str, Any], trusted_upstream_authority_sha256: str, evaluated_at: str | None = None) -> CompiledPortfolio:
    source = normalize_input(value)
    authority, authority_sha = _validated_authority(upstream_authority, trusted_upstream_authority_sha256)
    evaluated_at = _canonical_now() if evaluated_at is None else _ts(evaluated_at, "evaluated_at")
    _validate_evaluation_time(source, evaluated_at)
    input_sha = _digest(_json(source))
    policy = source["policy"]
    authority_map = {row["opportunity_id"]: row for row in authority["rows"]}
    capacity_base: dict[str, dict[str, int]] = {}
    usable: dict[str, int] = {}
    for pool in policy["pools"]:
        usable_units = pool["available_units"] - pool["reserve_units"]
        capacity_base[pool["pool_id"]] = {"available_units": pool["available_units"], "reserve_units": pool["reserve_units"], "usable_units": usable_units}
        usable[pool["pool_id"]] = usable_units

    statuses: dict[str, tuple[str, list[str], str, str | None]] = {}
    eligible: list[dict[str, Any]] = []
    for opp in source["opportunities"]:
        auth_row, auth_reasons = _authority_for(opp, authority_map)
        state, reasons, upstream_state = _preclassify(opp, auth_row, auth_reasons, policy, evaluated_at)
        captured = auth_row["evidence_captured_at"] if auth_row else None
        statuses[opp["opportunity_id"]] = (state, reasons, upstream_state, captured)
        if state == "ELIGIBLE":
            eligible.append(opp)

    selected_ids, used, selected_priority, search_nodes = _solve_exact(eligible, usable)
    selected = set(selected_ids)
    rows: list[dict[str, Any]] = []
    for opp in source["opportunities"]:
        pre_state, pre_reasons, upstream_state, captured = statuses[opp["opportunity_id"]]
        counterfactual: list[dict[str, Any]] = []
        if pre_state != "ELIGIBLE":
            allocation_state, reasons = pre_state, list(pre_reasons)
        elif opp["opportunity_id"] in selected:
            allocation_state = "ALLOCATED_READY" if upstream_state == "READY" else "CURABLE_RECOVERY_ALLOCATED"
            reasons = []
        else:
            allocation_state, reasons = "DEFERRED_CAPACITY", ["NOT_IN_EXACT_OPTIMAL_SUBSET"]
            effort_map = {row["pool_id"]: row["units"] for row in opp["effort"]}
            for pool_id in sorted(effort_map):
                headroom = usable[pool_id] - used[pool_id]
                if effort_map[pool_id] > headroom:
                    counterfactual.append({"additional_units": effort_map[pool_id] - headroom, "pool_id": pool_id})
            if not counterfactual:
                reasons.append("OBJECTIVE_DISPLACEMENT_WITHOUT_RESIDUAL_POOL_SHORTFALL")
        rows.append({
            "allocation_state": allocation_state,
            "evidence_captured_at": captured,
            "individual_fit_counterfactual": counterfactual,
            "min_buffer_minutes": opp["min_buffer_minutes"],
            "opportunity_id": opp["opportunity_id"],
            "priority_units": opp["priority_units"],
            "reasons": reasons,
            "response_deadline": opp["response_deadline"],
            "revision": opp["revision"],
            "source_sha256": opp["source_sha256"],
            "upstream_receipt_sha256": opp["upstream_receipt_sha256"],
            "upstream_state": upstream_state,
        })

    capacity: list[dict[str, Any]] = []
    for pool_id in sorted(capacity_base):
        base = capacity_base[pool_id]
        capacity.append({**base, "allocated_units": used[pool_id], "headroom_units": base["usable_units"] - used[pool_id], "pool_id": pool_id})

    result = {
        "authority": {key: False for key in ("award_claim", "buyer_contact", "contract_or_signature", "expected_revenue_or_probability", "external_submission", "payment_or_bank_action", "pricing_commitment", "scheduling_or_staffing", "spending")},
        "capacity": capacity,
        "evaluated_at": evaluated_at,
        "input_sha256": input_sha,
        "normalized_input": source,
        "normalized_upstream_authority": authority,
        "opportunities": rows,
        "policy_revision": policy["revision"],
        "policy_sha256": policy["policy_sha256"],
        "portfolio_id": source["portfolio_id"],
        "schema": RESULT_SCHEMA,
        "selected_opportunity_ids": list(selected_ids),
        "selected_priority_units": selected_priority,
        "solver": {"candidate_count": len(eligible), "exact": True, "max_candidates": MAX_ALLOCATABLE, "objective": "MAX_PRIORITY_THEN_COUNT_THEN_MIN_EFFORT_THEN_LEXICOGRAPHIC_IDS", "search_nodes": search_nodes},
        "upstream_authority_sha256": authority_sha,
    }
    result_raw = _json(result)
    markdown_raw = render_markdown(result)
    base = {
        "authority": "OWNER_PORTFOLIO_REVIEW_ONLY",
        "evaluated_at": evaluated_at,
        "input_sha256": input_sha,
        "markdown_sha256": _digest(markdown_raw),
        "policy_sha256": policy["policy_sha256"],
        "portfolio_id": source["portfolio_id"],
        "result_sha256": _digest(result_raw),
        "schema": RECEIPT_SCHEMA,
        "selected_opportunity_ids": list(selected_ids),
        "selected_priority_units": selected_priority,
        "upstream_authority_sha256": authority_sha,
    }
    receipt = {**base, "receipt_sha256": _digest(_json(base))}
    return CompiledPortfolio(result, result_raw, markdown_raw, receipt, _json(receipt))


def verify_compiled(result_raw: bytes, markdown_raw: bytes, receipt_raw: bytes, *, trusted_upstream_authority_sha256: str) -> dict[str, Any]:
    result = load_json_bytes(result_raw, "result")
    receipt = load_json_bytes(receipt_raw, "receipt")
    if result.get("schema") != RESULT_SCHEMA or receipt.get("schema") != RECEIPT_SCHEMA:
        raise PortfolioError("result/receipt: unsupported schema")
    source = result.get("normalized_input")
    authority = result.get("normalized_upstream_authority")
    evaluated_at = result.get("evaluated_at")
    if not isinstance(source, dict) or not isinstance(authority, dict) or not isinstance(evaluated_at, str):
        raise PortfolioError("result: missing embedded normalized input/authority/evaluation time")
    expected = compile_portfolio(source, upstream_authority=authority, trusted_upstream_authority_sha256=trusted_upstream_authority_sha256, evaluated_at=evaluated_at)
    if result_raw != expected.result_bytes:
        raise PortfolioError("result: bytes or semantics do not match deterministic recompile")
    if markdown_raw != expected.markdown_bytes:
        raise PortfolioError("markdown: bytes do not match deterministic recompile")
    if receipt_raw != expected.receipt_bytes:
        raise PortfolioError("receipt: bytes or commitments do not match deterministic recompile")
    base = dict(receipt)
    claimed = base.pop("receipt_sha256", None)
    if claimed != _digest(_json(base)):
        raise PortfolioError("receipt: self commitment mismatch")
    return {
        "input_sha256": expected.result["input_sha256"],
        "markdown_sha256": expected.receipt["markdown_sha256"],
        "receipt_sha256": expected.receipt["receipt_sha256"],
        "result_sha256": expected.receipt["result_sha256"],
        "selected_opportunity_ids": expected.result["selected_opportunity_ids"],
        "selected_priority_units": expected.result["selected_priority_units"],
        "upstream_authority_sha256": expected.receipt["upstream_authority_sha256"],
        "verified": True,
    }


def _directory_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _open_parent_generation(dest: Path) -> tuple[int, str]:
    parent = dest.parent if dest.parent != Path("") else Path(".")
    try:
        fd = os.open(os.fspath(parent), _directory_flags())
    except OSError as exc:
        raise PortfolioError(f"output parent: ordinary existing directory required: {parent}") from exc
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode):
        os.close(fd)
        raise PortfolioError("output parent: directory required")
    return fd, dest.name


def _same_generation(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _write_exclusive_at(dir_fd: int, name: str, data: bytes) -> tuple[int, int]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(name, flags, 0o600, dir_fd=dir_fd)
    try:
        opened = os.fstat(fd)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError(errno.EIO, "short write")
            view = view[written:]
        os.fsync(fd)
        visible = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        if not _same_generation(opened, visible):
            raise PortfolioError(f"output {name}: visible pathname generation changed during write")
        return opened.st_dev, opened.st_ino
    finally:
        os.close(fd)


def _stat_visible_generation(dir_fd: int, name: str) -> tuple[int, int]:
    info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    return info.st_dev, info.st_ino


def write_compiled(source: dict[str, Any], out_dir: str | Path, *, upstream_authority: dict[str, Any], trusted_upstream_authority_sha256: str, evaluated_at: str | None = None) -> CompiledPortfolio:
    dest = Path(out_dir)
    if not dest.name or dest.name in {".", ".."}:
        raise PortfolioError("output directory: unsafe final component")
    compiled = compile_portfolio(source, upstream_authority=upstream_authority, trusted_upstream_authority_sha256=trusted_upstream_authority_sha256, evaluated_at=evaluated_at)
    parent_fd, name = _open_parent_generation(dest)
    dest_fd = -1
    try:
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError as exc:
            raise PortfolioError(f"output directory already exists or is a symlink: {dest}") from exc
        except OSError as exc:
            raise PortfolioError(f"output directory: cannot create {dest}") from exc
        os.fsync(parent_fd)
        dest_fd = os.open(name, _directory_flags(), dir_fd=parent_fd)
        dest_info = os.fstat(dest_fd)
        visible_dest = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(dest_info.st_mode) or not _same_generation(dest_info, visible_dest):
            raise PortfolioError("output directory: visible generation changed after creation")

        published = {
            "portfolio.json": _write_exclusive_at(dest_fd, "portfolio.json", compiled.result_bytes),
            "portfolio.md": _write_exclusive_at(dest_fd, "portfolio.md", compiled.markdown_bytes),
            "receipt.json": _write_exclusive_at(dest_fd, "receipt.json", compiled.receipt_bytes),
        }
        os.fsync(dest_fd)
        for child, generation in published.items():
            if _stat_visible_generation(dest_fd, child) != generation:
                raise PortfolioError(f"output {child}: visible pathname generation changed after publication")
        visible_dest = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not _same_generation(dest_info, visible_dest):
            raise PortfolioError("output directory: visible generation changed during publication")
        direct = os.stat(dest, follow_symlinks=False)
        if not _same_generation(dest_info, direct):
            raise PortfolioError("output directory: path no longer resolves to retained generation")
        os.fsync(parent_fd)
        return compiled
    except PortfolioError:
        raise
    except Exception as exc:
        raise PortfolioError("output publication failed; partial publication preserved") from exc
    finally:
        if dest_fd >= 0:
            os.close(dest_fd)
        os.close(parent_fd)


def read_compiled_directory(root: str | Path) -> tuple[bytes, bytes, bytes]:
    path = Path(root)
    try:
        dir_fd = os.open(os.fspath(path), _directory_flags())
    except OSError as exc:
        raise PortfolioError("verify: ordinary non-symlink directory required") from exc
    try:
        info = os.fstat(dir_fd)
        if not stat.S_ISDIR(info.st_mode):
            raise PortfolioError("verify: ordinary directory required")
        parts: list[bytes] = []
        for name in ("portfolio.json", "portfolio.md", "receipt.json"):
            flags = os.O_RDONLY
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                fd = os.open(name, flags, dir_fd=dir_fd)
            except OSError as exc:
                raise PortfolioError(f"{name}: cannot open regular non-symlink file") from exc
            try:
                child = os.fstat(fd)
                if not stat.S_ISREG(child.st_mode):
                    raise PortfolioError(f"{name}: regular non-symlink file required")
                parts.append(_read_fd_bounded(fd, child, name))
            finally:
                os.close(fd)
        return parts[0], parts[1], parts[2]
    finally:
        os.close(dir_fd)
