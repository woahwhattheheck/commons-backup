"""Deterministic evidence gate for agent tool calls.

The gate is deliberately side-effect free.  It verifies independently retained
policy, approval-authority, and replay-ledger generations and returns either
EXECUTE_ALLOWED or HOLD.  A caller still needs an atomic reservation + provider
consumer to make a real external mutation; this module never performs one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

POLICY_SCHEMA = "tjlabs.agent-toolcall-policy/v1"
REQUEST_SCHEMA = "tjlabs.agent-toolcall-request/v1"
AUTHORITY_SCHEMA = "tjlabs.agent-toolcall-approval-authority/v1"
LEDGER_SCHEMA = "tjlabs.agent-toolcall-ledger/v1"
RECEIPT_SCHEMA = "tjlabs.agent-toolcall-receipt/v1"
EVENT_SCHEMA = "tjlabs.agent-toolcall-ledger-event/v1"

EXECUTE_ALLOWED = "EXECUTE_ALLOWED"
HOLD = "HOLD"
GENESIS = "0" * 64
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_TEXT = 4096
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,255}$")


class GateError(ValueError):
    """Malformed or untrusted input boundary."""


def _fail(msg: str) -> None:
    raise GateError(msg)


def _pairs(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            _fail(f"duplicate JSON key: {k}")
        out[k] = v
    return out


def _constant(v: str) -> None:
    _fail(f"non-finite JSON constant forbidden: {v}")


def strict_loads(data: bytes) -> Any:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise GateError("JSON must be strict UTF-8") from exc
    try:
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except GateError:
        raise
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise GateError(f"invalid JSON: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode()
    except (TypeError, ValueError) as exc:
        raise GateError(f"cannot canonicalize: {exc}") from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def _dict(v: Any, where: str) -> dict[str, Any]:
    if type(v) is not dict:
        _fail(f"{where} must be object")
    return v


def _list(v: Any, where: str, *, max_len: int = 10000) -> list[Any]:
    if type(v) is not list:
        _fail(f"{where} must be array")
    if len(v) > max_len:
        _fail(f"{where} exceeds maximum length")
    return v


def _keys(o: Mapping[str, Any], where: str, required: Iterable[str], optional: Iterable[str] = ()) -> None:
    req = set(required)
    allowed = req | set(optional)
    missing = req - set(o)
    unknown = set(o) - allowed
    if missing:
        _fail(f"{where} missing keys: {sorted(missing)}")
    if unknown:
        _fail(f"{where} unknown keys: {sorted(unknown)}")


def _str(v: Any, where: str, *, max_len: int = MAX_TEXT, allow_empty: bool = False) -> str:
    if type(v) is not str:
        _fail(f"{where} must be string")
    if not allow_empty and not v:
        _fail(f"{where} must be nonempty")
    if len(v) > max_len or "\x00" in v:
        _fail(f"{where} invalid string")
    return v


def _id(v: Any, where: str) -> str:
    s = _str(v, where, max_len=256)
    if not ID_RE.fullmatch(s):
        _fail(f"{where} has invalid identifier syntax")
    return s


def _int(v: Any, where: str, *, minimum: int = 0) -> int:
    if type(v) is not int:
        _fail(f"{where} must be integer; bool forbidden")
    if v < minimum:
        _fail(f"{where} must be >= {minimum}")
    return v


def _sha(v: Any, where: str) -> str:
    s = _str(v, where, max_len=64)
    if not SHA_RE.fullmatch(s):
        _fail(f"{where} must be lowercase SHA-256")
    return s


def _time(v: Any, where: str) -> datetime:
    s = _str(v, where, max_len=64)
    candidate = s[:-1] + "+00:00" if s.endswith("Z") else s
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise GateError(f"{where} invalid timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        _fail(f"{where} must include timezone")
    return dt.astimezone(timezone.utc)


def _time_text(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _unique(values: Sequence[str], where: str) -> None:
    if len(values) != len(set(values)):
        _fail(f"{where} contains duplicates")


def _normalize_policy(v: Mapping[str, Any]) -> dict[str, Any]:
    o = _dict(v, "policy")
    _keys(o, "policy", ["schema", "policy_id", "generation", "effective_at", "expires_at", "request_max_age_seconds", "allowed_agents", "rules"])
    if _str(o["schema"], "policy.schema") != POLICY_SCHEMA:
        _fail("wrong policy schema")
    agents: list[dict[str, Any]] = []
    seen_agents: set[tuple[str, str]] = set()
    for i, raw in enumerate(_list(o["allowed_agents"], "policy.allowed_agents", max_len=1000)):
        a = _dict(raw, f"allowed_agents[{i}]")
        _keys(a, f"allowed_agents[{i}]", ["agent_id", "version", "roles"])
        roles = [_id(x, f"allowed_agents[{i}].roles") for x in _list(a["roles"], "roles", max_len=100)]
        _unique(roles, f"allowed_agents[{i}].roles")
        key = (_id(a["agent_id"], "agent_id"), _id(a["version"], "version"))
        if key in seen_agents:
            _fail("duplicate agent/version")
        seen_agents.add(key)
        agents.append({"agent_id": key[0], "version": key[1], "roles": sorted(roles)})
    rules: list[dict[str, Any]] = []
    seen_rules: set[str] = set()
    for i, raw in enumerate(_list(o["rules"], "policy.rules", max_len=5000)):
        r = _dict(raw, f"rules[{i}]")
        _keys(r, f"rules[{i}]", ["rule_id", "tool", "action", "roles", "resource_prefixes", "data_classes", "approval_kind", "max_cost_cents", "window_seconds", "max_calls_per_window", "max_cost_cents_per_window"])
        rid = _id(r["rule_id"], "rule_id")
        if rid in seen_rules:
            _fail("duplicate rule_id")
        seen_rules.add(rid)
        roles = [_id(x, "rule.roles") for x in _list(r["roles"], "rule.roles", max_len=100)]
        prefixes = [_str(x, "resource_prefix", max_len=1024) for x in _list(r["resource_prefixes"], "resource_prefixes", max_len=100)]
        classes = [_id(x, "data_class") for x in _list(r["data_classes"], "data_classes", max_len=100)]
        _unique(roles, "rule.roles"); _unique(prefixes, "resource_prefixes"); _unique(classes, "data_classes")
        approval = r["approval_kind"]
        if approval is not None:
            approval = _id(approval, "approval_kind")
        rules.append({
            "rule_id": rid,
            "tool": _id(r["tool"], "rule.tool"),
            "action": _id(r["action"], "rule.action"),
            "roles": sorted(roles),
            "resource_prefixes": sorted(prefixes),
            "data_classes": sorted(classes),
            "approval_kind": approval,
            "max_cost_cents": _int(r["max_cost_cents"], "max_cost_cents"),
            "window_seconds": _int(r["window_seconds"], "window_seconds", minimum=1),
            "max_calls_per_window": _int(r["max_calls_per_window"], "max_calls_per_window", minimum=1),
            "max_cost_cents_per_window": _int(r["max_cost_cents_per_window"], "max_cost_cents_per_window"),
        })
    effective = _time(o["effective_at"], "policy.effective_at")
    expires = _time(o["expires_at"], "policy.expires_at")
    if expires <= effective:
        _fail("policy expires_at must be after effective_at")
    return {
        "schema": POLICY_SCHEMA,
        "policy_id": _id(o["policy_id"], "policy_id"),
        "generation": _int(o["generation"], "policy.generation", minimum=1),
        "effective_at": _time_text(effective),
        "expires_at": _time_text(expires),
        "request_max_age_seconds": _int(o["request_max_age_seconds"], "request_max_age_seconds", minimum=1),
        "allowed_agents": sorted(agents, key=lambda x: (x["agent_id"], x["version"])),
        "rules": sorted(rules, key=lambda x: x["rule_id"]),
    }


def _normalize_request(v: Mapping[str, Any]) -> dict[str, Any]:
    o = _dict(v, "request")
    _keys(o, "request", ["schema", "request_id", "requested_at", "agent_id", "agent_version", "actor_role", "tool", "action", "resource", "data_class", "estimated_cost_cents", "operation_key", "trace_id", "approval_ids"])
    approvals = [_id(x, "approval_id") for x in _list(o["approval_ids"], "approval_ids", max_len=100)]
    _unique(approvals, "approval_ids")
    if _str(o["schema"], "request.schema") != REQUEST_SCHEMA:
        _fail("wrong request schema")
    return {
        "schema": REQUEST_SCHEMA,
        "request_id": _id(o["request_id"], "request_id"),
        "requested_at": _time_text(_time(o["requested_at"], "requested_at")),
        "agent_id": _id(o["agent_id"], "agent_id"),
        "agent_version": _id(o["agent_version"], "agent_version"),
        "actor_role": _id(o["actor_role"], "actor_role"),
        "tool": _id(o["tool"], "tool"),
        "action": _id(o["action"], "action"),
        "resource": _str(o["resource"], "resource", max_len=1024),
        "data_class": _id(o["data_class"], "data_class"),
        "estimated_cost_cents": _int(o["estimated_cost_cents"], "estimated_cost_cents"),
        "operation_key": _id(o["operation_key"], "operation_key"),
        "trace_id": _id(o["trace_id"], "trace_id"),
        "approval_ids": sorted(approvals),
    }


def request_scope_sha(request: Mapping[str, Any]) -> str:
    r = _normalize_request(request)
    scope = {k: r[k] for k in ("request_id", "agent_id", "agent_version", "actor_role", "tool", "action", "resource", "data_class", "estimated_cost_cents", "operation_key", "trace_id")}
    return canonical_sha(scope)


def _normalize_authority(v: Mapping[str, Any]) -> dict[str, Any]:
    o = _dict(v, "authority")
    _keys(o, "authority", ["schema", "authority_id", "generation", "approvals"])
    if _str(o["schema"], "authority.schema") != AUTHORITY_SCHEMA:
        _fail("wrong authority schema")
    approvals: list[dict[str, Any]] = []
    ids: list[str] = []
    for i, raw in enumerate(_list(o["approvals"], "approvals", max_len=5000)):
        a = _dict(raw, f"approvals[{i}]")
        _keys(a, f"approvals[{i}]", ["approval_id", "kind", "scope_sha256", "issued_at", "expires_at", "issuer"])
        aid = _id(a["approval_id"], "approval_id"); ids.append(aid)
        issued = _time(a["issued_at"], "issued_at"); expires = _time(a["expires_at"], "expires_at")
        if expires <= issued:
            _fail("approval expiry must follow issuance")
        approvals.append({"approval_id": aid, "kind": _id(a["kind"], "kind"), "scope_sha256": _sha(a["scope_sha256"], "scope_sha256"), "issued_at": _time_text(issued), "expires_at": _time_text(expires), "issuer": _id(a["issuer"], "issuer")})
    _unique(ids, "approval IDs")
    return {"schema": AUTHORITY_SCHEMA, "authority_id": _id(o["authority_id"], "authority_id"), "generation": _int(o["generation"], "authority.generation", minimum=1), "approvals": sorted(approvals, key=lambda x: x["approval_id"])}


def _event_body(event: Mapping[str, Any]) -> dict[str, Any]:
    return {k: event[k] for k in ("schema", "sequence", "prev_event_sha256", "operation_key", "trace_id", "request_sha256", "occurred_at", "actor_role", "tool", "action", "resource", "cost_cents", "outcome")}


def _normalize_event(raw: Any, index: int) -> dict[str, Any]:
    e = _dict(raw, f"events[{index}]")
    _keys(e, f"events[{index}]", ["schema", "sequence", "prev_event_sha256", "operation_key", "trace_id", "request_sha256", "occurred_at", "actor_role", "tool", "action", "resource", "cost_cents", "outcome", "event_sha256"])
    if _str(e["schema"], "event.schema") != EVENT_SCHEMA:
        _fail("wrong event schema")
    out = {
        "schema": EVENT_SCHEMA,
        "sequence": _int(e["sequence"], "sequence", minimum=1),
        "prev_event_sha256": _sha(e["prev_event_sha256"], "prev_event_sha256"),
        "operation_key": _id(e["operation_key"], "operation_key"),
        "trace_id": _id(e["trace_id"], "trace_id"),
        "request_sha256": _sha(e["request_sha256"], "request_sha256"),
        "occurred_at": _time_text(_time(e["occurred_at"], "occurred_at")),
        "actor_role": _id(e["actor_role"], "actor_role"),
        "tool": _id(e["tool"], "tool"),
        "action": _id(e["action"], "action"),
        "resource": _str(e["resource"], "resource", max_len=1024),
        "cost_cents": _int(e["cost_cents"], "cost_cents"),
        "outcome": _id(e["outcome"], "outcome"),
    }
    out["event_sha256"] = _sha(e["event_sha256"], "event_sha256")
    if canonical_sha(_event_body(out)) != out["event_sha256"]:
        _fail(f"events[{index}] event_sha256 mismatch")
    return out


def _normalize_ledger(v: Mapping[str, Any]) -> dict[str, Any]:
    o = _dict(v, "ledger")
    _keys(o, "ledger", ["schema", "ledger_id", "generation", "events"])
    if _str(o["schema"], "ledger.schema") != LEDGER_SCHEMA:
        _fail("wrong ledger schema")
    events = [_normalize_event(raw, i) for i, raw in enumerate(_list(o["events"], "events", max_len=100000))]
    expected_prev = GENESIS
    seen_ops: set[str] = set(); seen_traces: set[str] = set()
    for i, e in enumerate(events):
        if e["sequence"] != i + 1:
            _fail("ledger sequence gap")
        if e["prev_event_sha256"] != expected_prev:
            _fail("ledger chain mismatch")
        if e["operation_key"] in seen_ops:
            _fail("ledger itself repeats operation_key")
        if e["trace_id"] in seen_traces:
            _fail("ledger itself repeats trace_id")
        seen_ops.add(e["operation_key"]); seen_traces.add(e["trace_id"])
        expected_prev = e["event_sha256"]
    return {"schema": LEDGER_SCHEMA, "ledger_id": _id(o["ledger_id"], "ledger_id"), "generation": _int(o["generation"], "ledger.generation", minimum=1), "events": events}


def ledger_head(ledger: Mapping[str, Any]) -> str:
    l = _normalize_ledger(ledger)
    return l["events"][-1]["event_sha256"] if l["events"] else GENESIS


def _retained_root(normalized: Mapping[str, Any], expected_sha: str, where: str) -> None:
    expected = _sha(expected_sha, f"expected {where} sha")
    actual = canonical_sha(normalized)
    if actual != expected:
        _fail(f"{where} does not match independently retained root")


def _matching_rule(policy: Mapping[str, Any], req: Mapping[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    ta = [r for r in policy["rules"] if r["tool"] == req["tool"] and r["action"] == req["action"]]
    if not ta:
        return None, ["TOOL_ACTION_DISALLOWED"]
    role = [r for r in ta if req["actor_role"] in r["roles"] and any(req["resource"].startswith(p) for p in r["resource_prefixes"])]
    if not role:
        return None, ["ROLE_RESOURCE_MISMATCH"]
    data = [r for r in role if req["data_class"] in r["data_classes"]]
    if not data:
        return role[0], ["RESTRICTED_DATA_EXPOSURE"]
    if len(data) != 1:
        return None, ["POLICY_RULE_AMBIGUOUS"]
    return data[0], []


def evaluate(
    policy: Mapping[str, Any],
    request: Mapping[str, Any],
    authority: Mapping[str, Any],
    ledger: Mapping[str, Any],
    *,
    expected_policy_sha256: str,
    expected_authority_sha256: str,
    expected_ledger_head: str,
    _now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate one request against independently retained policy/authority/ledger roots.

    ``_now`` is a private deterministic test seam. Production callers omit it.
    """
    p = _normalize_policy(policy); r = _normalize_request(request); a = _normalize_authority(authority); l = _normalize_ledger(ledger)
    _retained_root(p, expected_policy_sha256, "policy")
    _retained_root(a, expected_authority_sha256, "authority")
    if ledger_head(l) != _sha(expected_ledger_head, "expected ledger head"):
        _fail("ledger head does not match independently retained head")
    now = _now if _now is not None else datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        _fail("verification clock must be timezone-aware")
    now = now.astimezone(timezone.utc)
    reasons: list[str] = []

    eff = _time(p["effective_at"], "effective_at"); exp = _time(p["expires_at"], "expires_at")
    if now < eff:
        reasons.append("POLICY_NOT_YET_EFFECTIVE")
    if now >= exp:
        reasons.append("STALE_POLICY")
    requested = _time(r["requested_at"], "requested_at")
    if requested > now + timedelta(seconds=5):
        reasons.append("REQUEST_FROM_FUTURE")
    if now - requested > timedelta(seconds=p["request_max_age_seconds"]):
        reasons.append("STALE_REQUEST")

    agent = next((x for x in p["allowed_agents"] if x["agent_id"] == r["agent_id"] and x["version"] == r["agent_version"]), None)
    if agent is None:
        reasons.append("AGENT_VERSION_DISALLOWED")
    elif r["actor_role"] not in agent["roles"]:
        reasons.append("AGENT_ROLE_DISALLOWED")

    rule, rule_reasons = _matching_rule(p, r)
    reasons.extend(rule_reasons)

    approval_evidence: list[dict[str, Any]] = []
    if rule is not None and not rule_reasons:
        if r["estimated_cost_cents"] > rule["max_cost_cents"]:
            reasons.append("BUDGET_RATE_BREACH")
        window_start = now - timedelta(seconds=rule["window_seconds"])
        recent = [e for e in l["events"] if e["actor_role"] == r["actor_role"] and e["tool"] == r["tool"] and e["action"] == r["action"] and window_start <= _time(e["occurred_at"], "occurred_at") <= now]
        if len(recent) + 1 > rule["max_calls_per_window"] or sum(e["cost_cents"] for e in recent) + r["estimated_cost_cents"] > rule["max_cost_cents_per_window"]:
            reasons.append("BUDGET_RATE_BREACH")
        if rule["approval_kind"] is not None:
            by_id = {x["approval_id"]: x for x in a["approvals"]}
            scope = request_scope_sha(r)
            candidates = [by_id[x] for x in r["approval_ids"] if x in by_id]
            valid = [x for x in candidates if x["kind"] == rule["approval_kind"] and x["scope_sha256"] == scope and _time(x["issued_at"], "issued_at") <= now < _time(x["expires_at"], "expires_at")]
            approval_evidence = [{"approval_id": x["approval_id"], "kind": x["kind"], "issuer": x["issuer"], "scope_sha256": x["scope_sha256"]} for x in valid]
            if not valid:
                if candidates and any(x["kind"] == rule["approval_kind"] and x["scope_sha256"] != scope for x in candidates):
                    reasons.append("APPROVAL_SCOPE_MISMATCH")
                else:
                    reasons.append("MISSING_APPROVAL")

    ops = {e["operation_key"] for e in l["events"]}; traces = {e["trace_id"] for e in l["events"]}
    if r["operation_key"] in ops or r["trace_id"] in traces:
        reasons.append("REPLAY_COLLISION")

    reasons = sorted(set(reasons))
    decision = HOLD if reasons else EXECUTE_ALLOWED
    req_sha = canonical_sha(r)
    p_sha = canonical_sha(p); a_sha = canonical_sha(a); l_head = ledger_head(l)
    evidence = {
        "policy": {"policy_id": p["policy_id"], "generation": p["generation"], "sha256": p_sha},
        "authority": {"authority_id": a["authority_id"], "generation": a["generation"], "sha256": a_sha, "approvals": approval_evidence},
        "ledger": {"ledger_id": l["ledger_id"], "generation": l["generation"], "head_sha256": l_head, "event_count": len(l["events"])},
        "request": {"request_id": r["request_id"], "sha256": req_sha, "operation_key": r["operation_key"], "trace_id": r["trace_id"]},
        "matched_rule_id": None if rule is None else rule["rule_id"],
    }
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "decision": decision,
        "reasons": reasons,
        "evaluated_at": _time_text(now),
        "evidence": evidence,
        "reservation": {
            "required_before_external_effect": decision == EXECUTE_ALLOWED,
            "operation_key": r["operation_key"],
            "trace_id": r["trace_id"],
            "expected_pre_reservation_ledger_head": l_head,
        },
        "authority_ceiling": {
            "local_preflight_allowed": decision == EXECUTE_ALLOWED,
            "external_mutation_performed": False,
            "buyer_acceptance_proven": False,
            "contract_proven": False,
            "payment_proven": False,
            "revenue_proven": False,
        },
    }
    receipt["receipt_sha256"] = canonical_sha(receipt)
    return receipt


def make_ledger_event(receipt: Mapping[str, Any], request: Mapping[str, Any], *, outcome: str, occurred_at: datetime, sequence: int, prev_event_sha256: str) -> dict[str, Any]:
    """Build, but do not persist, a ledger event after a caller's atomic reservation/provider outcome."""
    rr = _dict(receipt, "receipt"); r = _normalize_request(request)
    if rr.get("decision") != EXECUTE_ALLOWED:
        _fail("cannot create execution event from HOLD receipt")
    if rr.get("evidence", {}).get("request", {}).get("sha256") != canonical_sha(r):
        _fail("receipt/request mismatch")
    event = {
        "schema": EVENT_SCHEMA,
        "sequence": _int(sequence, "sequence", minimum=1),
        "prev_event_sha256": _sha(prev_event_sha256, "prev_event_sha256"),
        "operation_key": r["operation_key"], "trace_id": r["trace_id"], "request_sha256": canonical_sha(r),
        "occurred_at": _time_text(occurred_at), "actor_role": r["actor_role"], "tool": r["tool"], "action": r["action"], "resource": r["resource"], "cost_cents": r["estimated_cost_cents"], "outcome": _id(outcome, "outcome"),
    }
    event["event_sha256"] = canonical_sha(_event_body(event))
    return event


def _open_dir(path: str) -> int:
    absolute = os.path.abspath(path); flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(os.sep, flags)
    try:
        for part in [x for x in absolute.split(os.sep) if x]:
            nfd = os.open(part, flags | getattr(os, "O_NOFOLLOW", 0), dir_fd=fd)
            os.close(fd); fd = nfd
        return fd
    except Exception:
        os.close(fd); raise


def read_json_file(path: str) -> dict[str, Any]:
    absolute = os.path.abspath(path); parent, name = os.path.split(absolute)
    try:
        pfd = _open_dir(parent or os.sep)
    except OSError as exc:
        raise GateError(f"{path} parent cannot be opened safely: {exc.strerror or exc}") from exc
    try:
        try:
            fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), dir_fd=pfd)
        except OSError as exc:
            raise GateError(f"{path} cannot be opened safely: {exc.strerror or exc}") from exc
        try:
            st1 = os.fstat(fd)
            if not stat.S_ISREG(st1.st_mode) or st1.st_size > MAX_JSON_BYTES:
                _fail(f"{path} must be bounded regular file")
            data = b""
            while len(data) < st1.st_size:
                chunk = os.read(fd, min(1024 * 1024, st1.st_size - len(data)))
                if not chunk:
                    _fail(f"{path} changed during read")
                data += chunk
            if os.read(fd, 1): _fail(f"{path} grew during read")
            st2 = os.fstat(fd)
            if (st1.st_dev, st1.st_ino, st1.st_size, st1.st_mtime_ns, st1.st_ctime_ns) != (st2.st_dev, st2.st_ino, st2.st_size, st2.st_mtime_ns, st2.st_ctime_ns):
                _fail(f"{path} changed during read")
        finally:
            os.close(fd)
    finally:
        os.close(pfd)
    return _dict(strict_loads(data), path)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Agent tool-call evidence gate (no provider side effects)")
    ap.add_argument("--policy", required=True); ap.add_argument("--request", required=True); ap.add_argument("--authority", required=True); ap.add_argument("--ledger", required=True)
    ap.add_argument("--policy-sha256", required=True); ap.add_argument("--authority-sha256", required=True); ap.add_argument("--ledger-head", required=True)
    args = ap.parse_args(argv)
    try:
        receipt = evaluate(read_json_file(args.policy), read_json_file(args.request), read_json_file(args.authority), read_json_file(args.ledger), expected_policy_sha256=args.policy_sha256, expected_authority_sha256=args.authority_sha256, expected_ledger_head=args.ledger_head)
    except GateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2
    print(canonical_bytes(receipt).decode(), end="")
    return 0 if receipt["decision"] == EXECUTE_ALLOWED else 3


if __name__ == "__main__":
    raise SystemExit(main())
