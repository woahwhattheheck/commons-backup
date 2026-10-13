from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping


class GateError(ValueError):
    pass


ROOT = Path(__file__).resolve().parent
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
RESOURCE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}/[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
DATA_CLASS_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
PAIR_RE = re.compile(r"^[A-Za-z0-9_.-]{1,40}:[A-Za-z0-9_.-]{1,40}$")

ENVELOPE_KEYS = {
    "schema", "environment", "evaluated_at", "run_id", "call_id", "agent",
    "actor", "request", "approval", "idempotency_key", "trace", "source",
}
AGENT_KEYS = {"id", "version"}
ACTOR_KEYS = {"role"}
REQUEST_KEYS = {
    "tool", "action", "target_resource", "data_class", "arguments_sha256",
    "estimated_cost_minor", "effect",
}
APPROVAL_KEYS = {
    "approval_id", "call_id", "decision", "approved_by_role", "approved_at",
    "expires_at",
}
TRACE_KEYS = {"requested_at", "dispatched_at", "observed_at", "completed_at", "outcome"}
SOURCE_KEYS = {"fixture", "source_sha256"}
POLICY_KEYS = {
    "schema", "policy_id", "version", "environment", "allowed_tool_actions",
    "role_resource_prefixes", "restricted_data_classes",
    "human_approval_required_for_actions", "human_approval_roles",
    "max_approval_age_seconds", "max_future_skew_seconds",
    "max_cost_minor_by_tool_action", "retry_semantics", "authority",
}
EXPECTED_AUTHORITY = {
    "production_tool_call_authorized": False,
    "network_provider_mutation_authorized": False,
    "credential_use_authorized": False,
    "customer_data_access_authorized": False,
    "deployment_authorized": False,
    "insurance_decision_authorized": False,
    "financial_decision_authorized": False,
    "payment_authorized": False,
    "revenue_claimed": False,
}
DECISION_SCOPE = "SYNTHETIC_POLICY_EVALUATION_ONLY_NOT_PRODUCTION_EXECUTION"
EVALUATION_TIME_AUTHORITY = "CALLER_SUPPLIED_REPLAY_ONLY_NOT_CURRENT"
RETRY_MODES = {"SAFE_RETRY", "IDEMPOTENCY_REQUIRED", "NO_RETRY"}


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise GateError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                GateError(f"non-finite JSON number: {token}")
            ),
        )
    except GateError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise GateError(f"invalid JSON: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise GateError(f"{label} must be object")
    actual = set(value)
    if actual != keys:
        raise GateError(
            f"{label} keys mismatch missing={sorted(keys-actual)} extra={sorted(actual-keys)}"
        )
    return value


def _strict_int(value: Any, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise GateError(f"{label} must be integer >= {minimum}")
    return value


def _strict_bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise GateError(f"{label} must be boolean")
    return value


def _string(value: Any, label: str, pattern: re.Pattern[str] = ID_RE) -> str:
    if type(value) is not str or not pattern.fullmatch(value):
        raise GateError(f"{label} invalid")
    return value


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or not SHA_RE.fullmatch(value):
        raise GateError(f"{label} must be lowercase sha256")
    return value


def _time(value: Any, label: str) -> datetime:
    if type(value) is not str:
        raise GateError(f"{label} must be timestamp string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise GateError(f"{label} invalid ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GateError(f"{label} must be offset-aware")
    return parsed


def _optional_time(value: Any, label: str) -> datetime | None:
    return None if value is None else _time(value, label)


def _distinct_strings(value: Any, label: str) -> list[str]:
    if type(value) is not list or not value or any(type(item) is not str for item in value):
        raise GateError(f"{label} must be non-empty string array")
    if len(set(value)) != len(value):
        raise GateError(f"{label} must not contain duplicates")
    return value


def _validate_policy(raw: Mapping[str, Any]) -> dict[str, Any]:
    policy = _exact(deepcopy(dict(raw)), POLICY_KEYS, "policy")
    if policy["schema"] != "agent-toolcall-policy/v1":
        raise GateError("unsupported policy schema")
    if policy["environment"] != "SYNTHETIC_NONPRODUCTION_ONLY":
        raise GateError("policy environment must stay synthetic/nonproduction")
    _string(policy["policy_id"], "policy.policy_id")
    _string(policy["version"], "policy.version")
    if policy["authority"] != EXPECTED_AUTHORITY:
        raise GateError("policy authority must be exact all-false contract")

    allowed = policy["allowed_tool_actions"]
    roles = policy["role_resource_prefixes"]
    costs = policy["max_cost_minor_by_tool_action"]
    retries = policy["retry_semantics"]
    if not all(type(item) is dict for item in (allowed, roles, costs, retries)):
        raise GateError("policy map fields must be objects")
    if not allowed or not roles:
        raise GateError("policy tools and roles must be non-empty")

    allowed_pairs: set[str] = set()
    allowed_actions: set[str] = set()
    for tool, actions in allowed.items():
        _string(tool, "policy tool")
        _distinct_strings(actions, f"policy.allowed_tool_actions[{tool}]")
        for action in actions:
            _string(action, "policy action")
            allowed_actions.add(action)
            allowed_pairs.add(f"{tool}:{action}")

    for role, prefixes in roles.items():
        _string(role, "policy role")
        _distinct_strings(prefixes, f"policy.role_resource_prefixes[{role}]")
        for prefix in prefixes:
            if not re.fullmatch(r"^[a-z][a-z0-9_-]{0,31}/$", prefix):
                raise GateError("policy resource prefix invalid")

    restricted = _distinct_strings(policy["restricted_data_classes"], "policy.restricted_data_classes")
    for data_class in restricted:
        _string(data_class, "restricted data class", DATA_CLASS_RE)

    approval_actions = _distinct_strings(
        policy["human_approval_required_for_actions"],
        "policy.human_approval_required_for_actions",
    )
    if not set(approval_actions).issubset(allowed_actions):
        raise GateError("approval-required action must be an allowed action")
    _distinct_strings(policy["human_approval_roles"], "policy.human_approval_roles")

    _strict_int(policy["max_approval_age_seconds"], "policy.max_approval_age_seconds", 1)
    _strict_int(policy["max_future_skew_seconds"], "policy.max_future_skew_seconds", 0)

    if set(costs) != allowed_pairs:
        raise GateError("policy cost map must exactly cover allowed tool/action pairs")
    for pair, limit in costs.items():
        _string(pair, "policy cost pair", PAIR_RE)
        _strict_int(limit, f"policy cost {pair}")

    if set(retries) != allowed_actions:
        raise GateError("policy retry map must exactly cover allowed actions")
    for action, mode in retries.items():
        _string(action, "policy retry action")
        if mode not in RETRY_MODES:
            raise GateError("policy retry mode invalid")
    return policy


def load_policy(path: Path | None = None) -> dict[str, Any]:
    target = path or ROOT / "policy.json"
    return _validate_policy(loads_strict(target.read_text(encoding="utf-8")))


def _normalize_envelope(envelope: Mapping[str, Any]) -> dict[str, Any]:
    value = _exact(dict(envelope), ENVELOPE_KEYS, "envelope")
    if value["schema"] != "agent-toolcall-envelope/v1":
        raise GateError("unsupported envelope schema")
    if value["environment"] != "SYNTHETIC_NONPRODUCTION":
        raise GateError("only synthetic/nonproduction evidence is admitted")
    _time(value["evaluated_at"], "evaluated_at")
    _string(value["run_id"], "run_id")
    _string(value["call_id"], "call_id")

    agent = _exact(value["agent"], AGENT_KEYS, "agent")
    _string(agent["id"], "agent.id")
    _string(agent["version"], "agent.version")
    actor = _exact(value["actor"], ACTOR_KEYS, "actor")
    _string(actor["role"], "actor.role")

    request = _exact(value["request"], REQUEST_KEYS, "request")
    _string(request["tool"], "request.tool")
    _string(request["action"], "request.action")
    _string(request["target_resource"], "request.target_resource", RESOURCE_RE)
    _string(request["data_class"], "request.data_class", DATA_CLASS_RE)
    _sha(request["arguments_sha256"], "request.arguments_sha256")
    _strict_int(request["estimated_cost_minor"], "request.estimated_cost_minor")
    if request["effect"] not in {"READ_ONLY", "MUTATING"}:
        raise GateError("request.effect invalid")

    approval = value["approval"]
    if approval is not None:
        approval = _exact(approval, APPROVAL_KEYS, "approval")
        _string(approval["approval_id"], "approval.approval_id")
        _string(approval["call_id"], "approval.call_id")
        if approval["decision"] != "APPROVED":
            raise GateError("approval.decision must be APPROVED when present")
        _string(approval["approved_by_role"], "approval.approved_by_role")
        _time(approval["approved_at"], "approval.approved_at")
        _time(approval["expires_at"], "approval.expires_at")

    idem = value["idempotency_key"]
    if idem is not None:
        _string(idem, "idempotency_key")

    trace = _exact(value["trace"], TRACE_KEYS, "trace")
    _time(trace["requested_at"], "trace.requested_at")
    for key in ("dispatched_at", "observed_at", "completed_at"):
        _optional_time(trace[key], f"trace.{key}")
    if trace["outcome"] not in {"NOT_DISPATCHED", "UNKNOWN", "SUCCESS", "FAILED"}:
        raise GateError("trace.outcome invalid")

    source = _exact(value["source"], SOURCE_KEYS, "source")
    if not _strict_bool(source["fixture"], "source.fixture"):
        raise GateError("source.fixture must be true")
    _sha(source["source_sha256"], "source.source_sha256")
    return deepcopy(value)


def _identity(envelope: Mapping[str, Any], policy_sha: str) -> dict[str, Any]:
    request = envelope["request"]
    return {
        "run_id": envelope["run_id"], "call_id": envelope["call_id"],
        "agent_id": envelope["agent"]["id"], "agent_version": envelope["agent"]["version"],
        "actor_role": envelope["actor"]["role"], "tool": request["tool"],
        "action": request["action"], "target_resource": request["target_resource"],
        "data_class": request["data_class"], "arguments_sha256": request["arguments_sha256"],
        "effect": request["effect"], "idempotency_key": envelope["idempotency_key"],
        "policy_sha256": policy_sha, "source_sha256": envelope["source"]["source_sha256"],
    }


def _evaluate_normalized(
    envelope: dict[str, Any], policy: dict[str, Any], policy_sha: str,
    seen_calls: set[str], seen_idempotency: set[str],
) -> dict[str, Any]:
    reasons: set[str] = set()
    request = envelope["request"]
    actor_role = envelope["actor"]["role"]
    tool, action = request["tool"], request["action"]
    pair = f"{tool}:{action}"

    allowed_pair = action in policy["allowed_tool_actions"].get(tool, [])
    if not allowed_pair:
        reasons.add("DISALLOWED_TOOL_ACTION")

    prefixes = policy["role_resource_prefixes"].get(actor_role, [])
    if not any(request["target_resource"].startswith(prefix) for prefix in prefixes):
        reasons.add("ROLE_RESOURCE_MISMATCH")
    if request["data_class"] in set(policy["restricted_data_classes"]):
        reasons.add("RESTRICTED_DATA_EXPOSURE")
    if allowed_pair and request["estimated_cost_minor"] > policy["max_cost_minor_by_tool_action"][pair]:
        reasons.add("BUDGET_RATE_BREACH")

    required_mutating = action in set(policy["human_approval_required_for_actions"])
    if allowed_pair and required_mutating and request["effect"] != "MUTATING":
        reasons.add("EFFECT_CLASSIFICATION_MISMATCH")
    if allowed_pair and not required_mutating and request["effect"] != "READ_ONLY":
        reasons.add("EFFECT_CLASSIFICATION_MISMATCH")

    evaluated = _time(envelope["evaluated_at"], "evaluated_at")
    skew = timedelta(seconds=policy["max_future_skew_seconds"])
    trace = envelope["trace"]
    requested = _time(trace["requested_at"], "trace.requested_at")
    dispatched = _optional_time(trace["dispatched_at"], "trace.dispatched_at")
    observed = _optional_time(trace["observed_at"], "trace.observed_at")
    completed = _optional_time(trace["completed_at"], "trace.completed_at")

    timestamps = [requested, dispatched, observed, completed]
    if any(ts is not None and ts > evaluated + skew for ts in timestamps):
        reasons.add("FUTURE_EVIDENCE")
    present = [ts for ts in timestamps if ts is not None]
    if present != sorted(present):
        reasons.add("UNSAFE_LIFECYCLE")
    if observed is not None and dispatched is None:
        reasons.add("UNSAFE_LIFECYCLE")
    if completed is not None and observed is None:
        reasons.add("UNSAFE_LIFECYCLE")

    if dispatched is None:
        if trace["outcome"] != "NOT_DISPATCHED":
            reasons.add("UNKNOWN_OUTCOME")
    elif completed is None:
        reasons.add("UNKNOWN_OUTCOME")
    elif trace["outcome"] not in {"SUCCESS", "FAILED"}:
        reasons.add("UNKNOWN_OUTCOME")

    approval = envelope["approval"]
    if allowed_pair and required_mutating:
        if approval is None:
            reasons.add("MISSING_HUMAN_APPROVAL")
        else:
            approved = _time(approval["approved_at"], "approval.approved_at")
            expires = _time(approval["expires_at"], "approval.expires_at")
            if (
                approval["call_id"] != envelope["call_id"]
                or approval["approved_by_role"] not in set(policy["human_approval_roles"])
                or approved > evaluated + skew
                or expires < evaluated
                or evaluated - approved > timedelta(seconds=policy["max_approval_age_seconds"])
            ):
                reasons.add("STALE_OR_CROSS_CALL_APPROVAL")

    retry_mode = policy["retry_semantics"].get(action) if allowed_pair else None
    if retry_mode == "IDEMPOTENCY_REQUIRED" and envelope["idempotency_key"] is None:
        reasons.add("MISSING_IDEMPOTENCY_KEY")

    if envelope["call_id"] in seen_calls:
        reasons.add("CONFLICTING_DUPLICATE_CALL_ID")
    else:
        seen_calls.add(envelope["call_id"])
    idem = envelope["idempotency_key"]
    if idem is not None:
        if idem in seen_idempotency:
            reasons.add("REPLAY_IDEMPOTENCY_COLLISION")
        else:
            seen_idempotency.add(idem)

    identity = _identity(envelope, policy_sha)
    receipt = {
        "schema": "agent-toolcall-gate-receipt/v2",
        "decision": "HOLD" if reasons else "EXECUTE_ALLOWED",
        "reasons": sorted(reasons),
        "evaluated_at": envelope["evaluated_at"],
        "environment": "SYNTHETIC_NONPRODUCTION",
        "decision_scope": DECISION_SCOPE,
        "evaluation_time_authority": EVALUATION_TIME_AUTHORITY,
        "current_execution_authority_claimed": False,
        "envelope_sha256": sha256_json(envelope),
        "policy_sha256": policy_sha,
        "identity_sha256": sha256_json(identity),
        "identity": identity,
        "trace_state": {
            "requested": True,
            "dispatched": dispatched is not None,
            "observed": observed is not None,
            "completed": completed is not None,
            "outcome": trace["outcome"],
        },
        "authority": deepcopy(EXPECTED_AUTHORITY),
    }
    receipt["receipt_sha256"] = sha256_json(receipt)
    return receipt


def compile_batch(
    envelopes: Iterable[Mapping[str, Any]], policy: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    active_policy = load_policy() if policy is None else _validate_policy(policy)
    policy_sha = sha256_json(active_policy)
    normalized = [_normalize_envelope(item) for item in envelopes]
    normalized.sort(key=lambda item: (item["trace"]["requested_at"], item["call_id"]))
    seen_calls: set[str] = set()
    seen_idempotency: set[str] = set()
    return [
        _evaluate_normalized(item, active_policy, policy_sha, seen_calls, seen_idempotency)
        for item in normalized
    ]


def compile_one(envelope: Mapping[str, Any], policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return compile_batch([envelope], policy)[0]


def verify_batch(
    envelopes: Iterable[Mapping[str, Any]], receipts: Iterable[Mapping[str, Any]],
    policy: Mapping[str, Any] | None = None,
) -> bool:
    try:
        expected = compile_batch(envelopes, policy)
        supplied = [dict(item) for item in receipts]
        return canonical_bytes(expected) == canonical_bytes(supplied)
    except (GateError, TypeError, ValueError):
        return False


def receipt_markdown(receipt: Mapping[str, Any]) -> str:
    value = dict(receipt)
    reasons = ", ".join(value["reasons"]) if value["reasons"] else "none"
    identity = value["identity"]
    return (
        "# Agent Tool-Call Evidence Receipt\n\n"
        f"- Decision: `{value['decision']}`\n- Reasons: `{reasons}`\n"
        f"- Scope: `{value['decision_scope']}`\n"
        f"- Evaluation-time authority: `{value['evaluation_time_authority']}`\n"
        f"- Current execution authority claimed: `{value['current_execution_authority_claimed']}`\n"
        f"- Run / call: `{identity['run_id']}` / `{identity['call_id']}`\n"
        f"- Agent: `{identity['agent_id']}@{identity['agent_version']}`\n"
        f"- Tool/action: `{identity['tool']}:{identity['action']}`\n"
        f"- Target: `{identity['target_resource']}`\n- Data class: `{identity['data_class']}`\n"
        f"- Identity SHA-256: `{value['identity_sha256']}`\n"
        f"- Envelope SHA-256: `{value['envelope_sha256']}`\n"
        f"- Policy SHA-256: `{value['policy_sha256']}`\n"
        f"- Receipt SHA-256: `{value['receipt_sha256']}`\n\n"
        "Authority: synthetic/nonproduction replay evaluation only; no current or production tool-call, "
        "provider mutation, credential/customer-data access, payment, or revenue authority.\n"
    )


def build_ledger(receipts: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    previous = "0" * 64
    for sequence, raw in enumerate(receipts, start=1):
        receipt = deepcopy(dict(raw))
        claimed = receipt.pop("receipt_sha256", None)
        if claimed != sha256_json(receipt):
            raise GateError("receipt digest mismatch")
        receipt["receipt_sha256"] = claimed
        entry = {
            "schema": "agent-toolcall-ledger-entry/v1",
            "sequence": sequence,
            "previous_entry_sha256": previous,
            "receipt": receipt,
        }
        entry["entry_sha256"] = sha256_json(entry)
        previous = entry["entry_sha256"]
        entries.append(entry)
    return entries


def verify_ledger(entries: Iterable[Mapping[str, Any]]) -> bool:
    previous = "0" * 64
    sequence = 1
    try:
        for raw in entries:
            entry = deepcopy(dict(raw))
            claimed = entry.pop("entry_sha256", None)
            if entry.get("schema") != "agent-toolcall-ledger-entry/v1":
                return False
            if entry.get("sequence") != sequence or entry.get("previous_entry_sha256") != previous:
                return False
            receipt = deepcopy(entry.get("receipt"))
            if type(receipt) is not dict:
                return False
            receipt_claimed = receipt.pop("receipt_sha256", None)
            if receipt_claimed != sha256_json(receipt) or claimed != sha256_json(entry):
                return False
            previous = claimed
            sequence += 1
    except (GateError, TypeError, ValueError):
        return False
    return True


def _merkle_root(hashes: list[str]) -> str:
    if not hashes:
        return hashlib.sha256(b"").hexdigest()
    layer = list(hashes)
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])
        layer = [
            hashlib.sha256(bytes.fromhex(layer[i]) + bytes.fromhex(layer[i + 1])).hexdigest()
            for i in range(0, len(layer), 2)
        ]
    return layer[0]


def daily_root_manifest(entries: Iterable[Mapping[str, Any]], day: str) -> dict[str, Any]:
    if type(day) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise GateError("day must be YYYY-MM-DD")
    try:
        materialized = [deepcopy(dict(raw)) for raw in entries]
    except (TypeError, ValueError) as exc:
        raise GateError("ledger entries must be objects") from exc
    if not verify_ledger(materialized):
        raise GateError("ledger must fully verify before daily root construction")

    selected: list[dict[str, Any]] = []
    for entry in materialized:
        receipt = entry.get("receipt", {})
        evaluated_at = receipt.get("evaluated_at") if type(receipt) is dict else None
        if type(evaluated_at) is str and evaluated_at[:10] == day:
            selected.append(entry)
    hashes = [entry["entry_sha256"] for entry in selected]
    manifest = {
        "schema": "agent-toolcall-daily-root/v2",
        "day": day,
        "entry_count": len(selected),
        "first_sequence": selected[0]["sequence"] if selected else None,
        "last_sequence": selected[-1]["sequence"] if selected else None,
        "merkle_root_sha256": _merkle_root(hashes),
        "ledger_verified_before_root": True,
        "authority": deepcopy(EXPECTED_AUTHORITY),
    }
    manifest["manifest_sha256"] = sha256_json(manifest)
    return manifest


def verify_root(manifest: Mapping[str, Any], entries: Iterable[Mapping[str, Any]]) -> bool:
    try:
        supplied = dict(manifest)
        day = supplied.get("day")
        if type(day) is not str:
            return False
        expected = daily_root_manifest(entries, day)
        return canonical_bytes(expected) == canonical_bytes(supplied)
    except (GateError, KeyError, TypeError, ValueError):
        return False
