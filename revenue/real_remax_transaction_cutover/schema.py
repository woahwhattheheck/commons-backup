from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Iterable, Mapping, NoReturn, Sequence

SCHEMA_POLICY = "real-remax-cutover-policy/v1"
SCHEMA_SNAPSHOT = "real-remax-cutover-snapshot/v1"
SCHEMA_IDENTITY_MAP = "real-remax-cutover-identity-map/v1"
SCHEMA_REPORT = "real-remax-cutover-report/v1"

MAX_TEXT = 256
MAX_ITEMS = 100_000
MAX_FINDINGS = 10_000


class CutoverError(ValueError):
    pass


def _fail(message: str) -> NoReturn:
    raise CutoverError(message)


def _obj(value: Any, *, name: str, keys: Iterable[str]) -> Mapping[str, Any]:
    if type(value) is not dict:
        _fail(f"{name} must be an object")
    expected = set(keys)
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        _fail(f"{name} fields mismatch: missing={missing} extra={extra}")
    return value


def _list(value: Any, *, name: str, limit: int = MAX_ITEMS) -> list[Any]:
    if type(value) is not list:
        _fail(f"{name} must be an array")
    if len(value) > limit:
        _fail(f"{name} exceeds {limit} items")
    return value


def _text(value: Any, *, name: str, max_len: int = MAX_TEXT) -> str:
    if type(value) is not str:
        _fail(f"{name} must be a string")
    if not value or len(value) > max_len:
        _fail(f"{name} length must be 1..{max_len}")
    if any(ord(ch) < 0x20 for ch in value):
        _fail(f"{name} contains control characters")
    return value


def _int(value: Any, *, name: str, minimum: int = 0, maximum: int = 2**63 - 1) -> int:
    if type(value) is not int:
        _fail(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        _fail(f"{name} must be in [{minimum}, {maximum}]")
    return value


def _sha(value: Any, *, name: str) -> str:
    text = _text(value, name=name, max_len=64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        _fail(f"{name} must be lowercase sha256 hex")
    return text


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise CutoverError(f"value is not canonical JSON: {exc}") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _unique_index(rows: Sequence[Mapping[str, Any]], key: str, *, name: str) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        value = _text(row[key], name=f"{name}.{key}")
        if value in out:
            _fail(f"duplicate {name} {key}: {value}")
        out[value] = row
    return out


def _validate_policy(policy: Any) -> Mapping[str, Any]:
    p = _obj(
        policy,
        name="policy",
        keys=(
            "schema",
            "policy_id",
            "generation",
            "source_system",
            "target_system",
            "active_source_stages",
            "stage_map",
            "status_map",
            "required_relationship_roles",
        ),
    )
    if p["schema"] != SCHEMA_POLICY:
        _fail("unsupported policy schema")
    _text(p["policy_id"], name="policy.policy_id")
    _int(p["generation"], name="policy.generation", minimum=1)
    _text(p["source_system"], name="policy.source_system")
    _text(p["target_system"], name="policy.target_system")

    active = _list(p["active_source_stages"], name="policy.active_source_stages", limit=64)
    if not active:
        _fail("policy.active_source_stages must not be empty")
    active_values = [_text(v, name="policy.active_source_stages[]") for v in active]
    if len(active_values) != len(set(active_values)):
        _fail("policy.active_source_stages contains duplicates")

    for field in ("stage_map", "status_map"):
        mapping = p[field]
        if type(mapping) is not dict or not mapping:
            _fail(f"policy.{field} must be a nonempty object")
        if len(mapping) > 128:
            _fail(f"policy.{field} is too large")
        seen_values: set[str] = set()
        for raw_k, raw_v in mapping.items():
            k = _text(raw_k, name=f"policy.{field} key")
            v = _text(raw_v, name=f"policy.{field}[{k}]")
            if v in seen_values:
                _fail(f"policy.{field} must be one-to-one; repeated target value {v}")
            seen_values.add(v)

    roles = _list(p["required_relationship_roles"], name="policy.required_relationship_roles", limit=32)
    role_values = [_text(v, name="policy.required_relationship_roles[]") for v in roles]
    if len(role_values) != len(set(role_values)):
        _fail("policy.required_relationship_roles contains duplicates")
    return p


def _validate_relationship(row: Any, *, name: str) -> Mapping[str, Any]:
    r = _obj(row, name=name, keys=("role", "agent_id", "split_bps", "commission_cents"))
    _text(r["role"], name=f"{name}.role")
    _text(r["agent_id"], name=f"{name}.agent_id")
    _int(r["split_bps"], name=f"{name}.split_bps", maximum=10_000)
    _int(r["commission_cents"], name=f"{name}.commission_cents")
    return r


def _validate_snapshot(snapshot: Any, *, name: str, expected_system: str) -> Mapping[str, Any]:
    s = _obj(
        snapshot,
        name=name,
        keys=("schema", "snapshot_id", "generation", "system", "offices", "agents", "transactions"),
    )
    if s["schema"] != SCHEMA_SNAPSHOT:
        _fail(f"unsupported {name} schema")
    _text(s["snapshot_id"], name=f"{name}.snapshot_id")
    _int(s["generation"], name=f"{name}.generation", minimum=1)
    if _text(s["system"], name=f"{name}.system") != expected_system:
        _fail(f"{name}.system does not match policy")

    offices = _list(s["offices"], name=f"{name}.offices")
    parsed_offices: list[Mapping[str, Any]] = []
    for i, raw in enumerate(offices):
        office = _obj(raw, name=f"{name}.offices[{i}]", keys=("office_id", "name"))
        _text(office["office_id"], name=f"{name}.offices[{i}].office_id")
        _text(office["name"], name=f"{name}.offices[{i}].name")
        parsed_offices.append(office)
    office_index = _unique_index(parsed_offices, "office_id", name=f"{name}.office")

    agents = _list(s["agents"], name=f"{name}.agents")
    parsed_agents: list[Mapping[str, Any]] = []
    for i, raw in enumerate(agents):
        agent = _obj(raw, name=f"{name}.agents[{i}]", keys=("agent_id", "office_id"))
        _text(agent["agent_id"], name=f"{name}.agents[{i}].agent_id")
        office_id = _text(agent["office_id"], name=f"{name}.agents[{i}].office_id")
        if office_id not in office_index:
            _fail(f"{name} agent references unknown office: {office_id}")
        parsed_agents.append(agent)
    agent_index = _unique_index(parsed_agents, "agent_id", name=f"{name}.agent")

    transactions = _list(s["transactions"], name=f"{name}.transactions")
    if len(offices) + len(agents) + len(transactions) > MAX_ITEMS:
        _fail(f"{name} exceeds aggregate {MAX_ITEMS} row limit")
    parsed_transactions: list[Mapping[str, Any]] = []
    relationship_count = 0
    for i, raw in enumerate(transactions):
        txn = _obj(
            raw,
            name=f"{name}.transactions[{i}]",
            keys=("transaction_id", "stage", "status", "gross_commission_cents", "relationships"),
        )
        _text(txn["transaction_id"], name=f"{name}.transactions[{i}].transaction_id")
        _text(txn["stage"], name=f"{name}.transactions[{i}].stage")
        _text(txn["status"], name=f"{name}.transactions[{i}].status")
        gross = _int(txn["gross_commission_cents"], name=f"{name}.transactions[{i}].gross_commission_cents")
        rels = _list(txn["relationships"], name=f"{name}.transactions[{i}].relationships", limit=64)
        relationship_count += len(rels)
        if len(offices) + len(agents) + len(transactions) + relationship_count > MAX_ITEMS:
            _fail(f"{name} exceeds aggregate {MAX_ITEMS} row limit")
        parsed_rels = [_validate_relationship(rel, name=f"{name}.transactions[{i}].relationships[{j}]") for j, rel in enumerate(rels)]
        role_agent = [(rel["role"], rel["agent_id"]) for rel in parsed_rels]
        if len(role_agent) != len(set(role_agent)):
            _fail(f"{name} transaction has duplicate role+agent relationship")
        if any(rel["agent_id"] not in agent_index for rel in parsed_rels):
            _fail(f"{name} transaction references unknown agent")
        if sum(int(rel["commission_cents"]) for rel in parsed_rels) != gross:
            _fail(f"{name} transaction relationship commission cents do not sum to gross")
        if sum(int(rel["split_bps"]) for rel in parsed_rels) != 10_000:
            _fail(f"{name} transaction split_bps do not sum to 10000")
        parsed_transactions.append(txn)
    _unique_index(parsed_transactions, "transaction_id", name=f"{name}.transaction")
    return s


def _parse_map_rows(value: Any, *, name: str, source_key: str, target_key: str) -> dict[str, str]:
    rows = _list(value, name=name)
    source_to_target: dict[str, str] = {}
    target_seen: set[str] = set()
    for i, raw in enumerate(rows):
        row = _obj(raw, name=f"{name}[{i}]", keys=(source_key, target_key))
        source = _text(row[source_key], name=f"{name}[{i}].{source_key}")
        target = _text(row[target_key], name=f"{name}[{i}].{target_key}")
        if source in source_to_target:
            _fail(f"{name} duplicates source id {source}")
        if target in target_seen:
            _fail(f"{name} maps multiple sources to target id {target}")
        source_to_target[source] = target
        target_seen.add(target)
    return source_to_target


def _validate_identity_map(identity_map: Any, source_snapshot: Mapping[str, Any], target_snapshot: Mapping[str, Any]) -> tuple[Mapping[str, Any], dict[str, str], dict[str, str], dict[str, str]]:
    m = _obj(identity_map, name="identity_map", keys=("schema", "source_snapshot_id", "target_snapshot_id", "offices", "agents", "transactions"))
    if m["schema"] != SCHEMA_IDENTITY_MAP:
        _fail("unsupported identity map schema")
    if _text(m["source_snapshot_id"], name="identity_map.source_snapshot_id") != source_snapshot["snapshot_id"]:
        _fail("identity map source snapshot id mismatch")
    if _text(m["target_snapshot_id"], name="identity_map.target_snapshot_id") != target_snapshot["snapshot_id"]:
        _fail("identity map target snapshot id mismatch")
    office_rows = _list(m["offices"], name="identity_map.offices")
    agent_rows = _list(m["agents"], name="identity_map.agents")
    txn_rows = _list(m["transactions"], name="identity_map.transactions")
    if len(office_rows) + len(agent_rows) + len(txn_rows) > MAX_ITEMS:
        _fail(f"identity_map exceeds aggregate {MAX_ITEMS} row limit")
    office_map = _parse_map_rows(office_rows, name="identity_map.offices", source_key="source_office_id", target_key="target_office_id")
    agent_map = _parse_map_rows(agent_rows, name="identity_map.agents", source_key="source_agent_id", target_key="target_agent_id")
    txn_map = _parse_map_rows(txn_rows, name="identity_map.transactions", source_key="source_transaction_id", target_key="target_transaction_id")
    return m, office_map, agent_map, txn_map
