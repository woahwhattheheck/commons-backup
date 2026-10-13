from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

SCHEMA_VERSION = 1
OUTPUT_VERSION = 1
ROUTES = {"PRIME", "TEAMING", "PARTNER_REQUIRED", "HOLD", "NO_BID"}
CATEGORIES = {
    "PORTAL", "LEGAL", "FINANCE", "TAX", "SIGNATURE", "TEAM", "PARTNER",
    "SITE", "COST_SHARE", "PRICING", "INSURANCE", "REFERENCE", "SUBMISSION", "OTHER"
}
STATUSES = {"PROVEN", "MISSING", "HOLD", "PENDING_EXTERNAL", "NOT_APPLICABLE"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
OPAQUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$")
ACTION_KEY = re.compile(r"^[A-Z0-9][A-Z0-9_.:/-]{0,95}$")


class ValidationError(ValueError):
    pass


def _dup_reject(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValidationError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_bytes(raw: bytes) -> Any:
    if not isinstance(raw, (bytes, bytearray)):
        raise ValidationError("JSON input must be bytes")
    if len(raw) > 2_000_000:
        raise ValidationError("JSON input exceeds 2 MB")
    try:
        text = bytes(raw).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("JSON must be UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_dup_reject,
            parse_constant=lambda x: (_ for _ in ()).throw(ValidationError(f"non-finite number: {x}")),
        )
    except ValidationError:
        raise
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON: {exc.msg}") from exc


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValidationError("value is not canonical-JSON serializable") from exc


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _exact_keys(obj: dict, expected: set[str], where: str) -> None:
    if type(obj) is not dict:
        raise ValidationError(f"{where} must be an object")
    got = set(obj)
    if got != expected:
        extra = sorted(got - expected)
        missing = sorted(expected - got)
        raise ValidationError(f"{where} keys mismatch; missing={missing} extra={extra}")


def _str(value: Any, where: str, *, max_len: int = 128, pattern=None) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        raise ValidationError(f"{where} must be a non-empty string <= {max_len}")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ValidationError(f"{where} contains control characters")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise ValidationError(f"{where} has invalid format")
    return value


def _label(value: Any, where: str) -> str:
    value = _str(value, where, max_len=180)
    if "\n" in value or "\r" in value:
        raise ValidationError(f"{where} must be one line")
    return value


def _bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise ValidationError(f"{where} must be boolean")
    return value


def _int(value: Any, where: str, *, minimum: int = 0, maximum: int = 10_000_000) -> int:
    if type(value) is not int:
        raise ValidationError(f"{where} must be integer (bool is not accepted)")
    if not (minimum <= value <= maximum):
        raise ValidationError(f"{where} out of range")
    return value


def _hash(value: Any, where: str) -> str:
    return _str(value, where, max_len=64, pattern=HEX64)


def parse_utc(value: Any, where: str) -> datetime:
    value = _str(value, where, max_len=32)
    if not value.endswith("Z"):
        raise ValidationError(f"{where} must use UTC Z")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValidationError(f"{where} invalid UTC") from exc
    if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
        raise ValidationError(f"{where} must be UTC")
    if dt.microsecond:
        raise ValidationError(f"{where} must use whole seconds")
    return dt.astimezone(timezone.utc)


def format_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValidationError("evaluation time must be timezone-aware")
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_policy(policy: Any) -> dict:
    _exact_keys(policy, {"max_source_age_minutes", "critical_window_minutes", "high_window_minutes"}, "policy")
    out = {
        "max_source_age_minutes": _int(policy["max_source_age_minutes"], "policy.max_source_age_minutes", minimum=1, maximum=525_600),
        "critical_window_minutes": _int(policy["critical_window_minutes"], "policy.critical_window_minutes", minimum=1, maximum=525_600),
        "high_window_minutes": _int(policy["high_window_minutes"], "policy.high_window_minutes", minimum=1, maximum=525_600),
    }
    if out["high_window_minutes"] < out["critical_window_minutes"]:
        raise ValidationError("policy.high_window_minutes must be >= critical_window_minutes")
    return out


def _normalize_evidence(value: Any, where: str) -> list[dict]:
    if type(value) is not list or len(value) > 64:
        raise ValidationError(f"{where} must be a list <= 64")
    seen = set()
    out = []
    for idx, row in enumerate(value):
        w = f"{where}[{idx}]"
        _exact_keys(row, {"ref", "sha256"}, w)
        ref = _str(row["ref"], f"{w}.ref", max_len=128, pattern=OPAQUE)
        digest = _hash(row["sha256"], f"{w}.sha256")
        if ref in seen:
            raise ValidationError(f"duplicate evidence ref: {ref}")
        seen.add(ref)
        out.append({"ref": ref, "sha256": digest})
    return sorted(out, key=lambda x: (x["ref"], x["sha256"]))


def _normalize_gate(value: Any, opp_id: str, where: str) -> dict:
    expected = {"id", "action_key", "action_label", "requirement_sha256", "generation", "category", "status", "blocking", "owner_required", "evidence", "prerequisites"}
    _exact_keys(value, expected, where)
    gate_id = _str(value["id"], f"{where}.id", max_len=128, pattern=OPAQUE)
    action_key = _str(value["action_key"], f"{where}.action_key", max_len=96, pattern=ACTION_KEY)
    action_label = _label(value["action_label"], f"{where}.action_label")
    requirement_sha = _hash(value["requirement_sha256"], f"{where}.requirement_sha256")
    generation = _int(value["generation"], f"{where}.generation", minimum=1, maximum=1_000_000)
    category = _str(value["category"], f"{where}.category", max_len=32)
    if category not in CATEGORIES:
        raise ValidationError(f"{where}.category unsupported")
    status = _str(value["status"], f"{where}.status", max_len=32)
    if status not in STATUSES:
        raise ValidationError(f"{where}.status unsupported")
    blocking = _bool(value["blocking"], f"{where}.blocking")
    owner_required = _bool(value["owner_required"], f"{where}.owner_required")
    evidence = _normalize_evidence(value["evidence"], f"{where}.evidence")
    prerequisites = value["prerequisites"]
    if type(prerequisites) is not list or len(prerequisites) > 64:
        raise ValidationError(f"{where}.prerequisites must be list <= 64")
    norm_pre = [_str(ref, f"{where}.prerequisites[{i}]", max_len=128, pattern=OPAQUE) for i, ref in enumerate(prerequisites)]
    if len(norm_pre) != len(set(norm_pre)):
        raise ValidationError(f"{where}.prerequisites contains duplicates")
    if gate_id in norm_pre:
        raise ValidationError(f"{where} cannot depend on itself")
    if status == "PROVEN" and not evidence:
        raise ValidationError(f"{where} PROVEN requires evidence")
    if status == "NOT_APPLICABLE" and blocking:
        raise ValidationError(f"{where} NOT_APPLICABLE cannot be blocking")
    return {
        "id": gate_id,
        "opportunity_id": opp_id,
        "action_key": action_key,
        "action_label": action_label,
        "requirement_sha256": requirement_sha,
        "generation": generation,
        "category": category,
        "status": status,
        "blocking": blocking,
        "owner_required": owner_required,
        "evidence": evidence,
        "prerequisites": sorted(norm_pre),
    }


def normalize_packet(packet: Any, *, as_of: datetime) -> dict:
    _exact_keys(packet, {"schema_version", "snapshot_id", "opportunities"}, "packet")
    if _int(packet["schema_version"], "packet.schema_version", minimum=1, maximum=1) != SCHEMA_VERSION:
        raise ValidationError("unsupported schema_version")
    snapshot_id = _str(packet["snapshot_id"], "packet.snapshot_id", max_len=128, pattern=OPAQUE)
    opportunities = packet["opportunities"]
    if type(opportunities) is not list or not opportunities or len(opportunities) > 500:
        raise ValidationError("packet.opportunities must be non-empty list <= 500")

    normalized = []
    global_gate_ids = set()
    opp_ids = set()
    as_of = as_of.astimezone(timezone.utc).replace(microsecond=0)

    for i, opp in enumerate(opportunities):
        where = f"packet.opportunities[{i}]"
        _exact_keys(opp, {"id", "owner_ref", "route_state", "deadline_utc", "source", "gates"}, where)
        opp_id = _str(opp["id"], f"{where}.id", max_len=128, pattern=OPAQUE)
        if opp_id in opp_ids:
            raise ValidationError(f"duplicate opportunity id: {opp_id}")
        opp_ids.add(opp_id)
        owner_ref = _str(opp["owner_ref"], f"{where}.owner_ref", max_len=128, pattern=OPAQUE)
        route = _str(opp["route_state"], f"{where}.route_state", max_len=32)
        if route not in ROUTES:
            raise ValidationError(f"{where}.route_state unsupported")
        deadline = opp["deadline_utc"]
        deadline_dt = None if deadline is None else parse_utc(deadline, f"{where}.deadline_utc")
        deadline_norm = None if deadline_dt is None else format_utc(deadline_dt)

        source = opp["source"]
        _exact_keys(source, {"packet_id", "packet_sha256", "captured_at", "complete"}, f"{where}.source")
        source_id = _str(source["packet_id"], f"{where}.source.packet_id", max_len=128, pattern=OPAQUE)
        source_sha = _hash(source["packet_sha256"], f"{where}.source.packet_sha256")
        source_captured = parse_utc(source["captured_at"], f"{where}.source.captured_at")
        if source_captured > as_of:
            raise ValidationError(f"{where}.source.captured_at is in the future")
        source_complete = _bool(source["complete"], f"{where}.source.complete")

        gates_raw = opp["gates"]
        if type(gates_raw) is not list or len(gates_raw) > 500:
            raise ValidationError(f"{where}.gates must be list <= 500")
        gates = []
        local_ids = set()
        for j, gate_raw in enumerate(gates_raw):
            gate = _normalize_gate(gate_raw, opp_id, f"{where}.gates[{j}]")
            if gate["id"] in global_gate_ids:
                raise ValidationError(f"duplicate global gate id: {gate['id']}")
            global_gate_ids.add(gate["id"])
            local_ids.add(gate["id"])
            gates.append(gate)

        for gate in gates:
            missing = [p for p in gate["prerequisites"] if p not in local_ids]
            if missing:
                raise ValidationError(f"gate {gate['id']} prerequisite outside opportunity: {missing}")

        graph = {g["id"]: g["prerequisites"] for g in gates}
        temp, perm = set(), set()

        def visit(node: str):
            if node in perm:
                return
            if node in temp:
                raise ValidationError(f"dependency cycle at {node}")
            temp.add(node)
            for parent in graph[node]:
                visit(parent)
            temp.remove(node)
            perm.add(node)

        for gid in sorted(graph):
            visit(gid)

        by_id = {g["id"]: g for g in gates}
        for gate in gates:
            if gate["status"] != "PROVEN":
                continue
            unmet = [p for p in gate["prerequisites"] if by_id[p]["status"] != "PROVEN"]
            if unmet:
                raise ValidationError(f"gate {gate['id']} PROVEN with unmet prerequisites: {unmet}")

        normalized.append({
            "id": opp_id,
            "owner_ref": owner_ref,
            "route_state": route,
            "deadline_utc": deadline_norm,
            "source": {"packet_id": source_id, "packet_sha256": source_sha, "captured_at": format_utc(source_captured), "complete": source_complete},
            "gates": sorted(gates, key=lambda g: g["id"]),
        })

    return {"schema_version": SCHEMA_VERSION, "snapshot_id": snapshot_id, "opportunities": sorted(normalized, key=lambda o: o["id"])}


def _minutes_until(deadline_utc: str | None, as_of: datetime) -> int | None:
    if deadline_utc is None:
        return None
    return int((parse_utc(deadline_utc, "normalized deadline") - as_of).total_seconds() // 60)


def _source_state(opp: dict, policy: dict, as_of: datetime) -> tuple[bool, list[str]]:
    reasons = []
    if not opp["source"]["complete"]:
        reasons.append("SOURCE_SET_INCOMPLETE")
    captured = parse_utc(opp["source"]["captured_at"], "source captured_at")
    age = as_of - captured
    if age > timedelta(minutes=policy["max_source_age_minutes"]):
        reasons.append("SOURCE_STALE")
    return (not reasons, reasons)


def _gate_classification(gate: dict, by_id: dict[str, dict]) -> tuple[str, list[str]]:
    status = gate["status"]
    if status == "PROVEN":
        return "NO_ACTION_PROVEN", ["GATE_PROVEN"]
    if status == "NOT_APPLICABLE":
        return "NO_ACTION_PROVEN", ["GATE_NOT_APPLICABLE"]
    if status == "HOLD":
        return "HOLD", ["GATE_HOLD"]
    if status == "PENDING_EXTERNAL":
        return "WAIT_EXTERNAL", ["PENDING_EXTERNAL"]
    unmet = [p for p in gate["prerequisites"] if by_id[p]["status"] != "PROVEN"]
    if unmet:
        return "DEPENDENCY_BLOCKED", ["UNMET_PREREQUISITE"]
    if gate["owner_required"]:
        return "OWNER_ACTION_NOW", ["OWNER_REQUIRED_MISSING"]
    return "OWNER_PREP_REQUIRED", ["PREP_MISSING"]


def _choose_group_state(states: list[str]) -> str:
    if "OWNER_ACTION_NOW" in states:
        return "OWNER_ACTION_NOW"
    if "HOLD" in states:
        return "HOLD"
    if "DEPENDENCY_BLOCKED" in states:
        return "DEPENDENCY_BLOCKED"
    if "OWNER_PREP_REQUIRED" in states:
        return "OWNER_PREP_REQUIRED"
    if "WAIT_EXTERNAL" in states:
        return "WAIT_EXTERNAL"
    return "NO_ACTION_PROVEN"


def _priority_band(state: str, minutes: int | None, affected_count: int, blocking_count: int, policy: dict) -> str:
    if state in {"TERMINAL", "NO_ACTION_PROVEN"}:
        return "TERMINAL"
    if state in {"HOLD", "WAIT_EXTERNAL", "DEPENDENCY_BLOCKED"} and minutes is None:
        return "HOLD"
    if minutes is not None and minutes <= policy["critical_window_minutes"]:
        return "CRITICAL"
    if (minutes is not None and minutes <= policy["high_window_minutes"]) or affected_count >= 3 or blocking_count >= 2:
        return "HIGH"
    if state in {"HOLD", "WAIT_EXTERNAL", "DEPENDENCY_BLOCKED"}:
        return "HOLD"
    return "NORMAL"


def _sort_key(row: dict) -> tuple:
    band_rank = {"CRITICAL": 0, "HIGH": 1, "NORMAL": 2, "HOLD": 3, "TERMINAL": 4}
    state_rank = {"SOURCE_REFRESH_REQUIRED": 0, "OWNER_ACTION_NOW": 1, "OWNER_PREP_REQUIRED": 2, "DEPENDENCY_BLOCKED": 3, "WAIT_EXTERNAL": 4, "HOLD": 5, "NO_ACTION_PROVEN": 6, "TERMINAL": 7}
    minutes = row["minutes_remaining"]
    minutes_key = 10**15 if minutes is None else minutes
    return (band_rank[row["priority_band"]], state_rank[row["state"]], minutes_key, -len(row["affected_opportunity_ids"]), -row["blocking_gate_count"], row["row_id"])


def compile_cockpit(packet: Any, policy: Any, *, as_of: datetime) -> dict:
    if as_of.tzinfo is None:
        raise ValidationError("as_of must be timezone-aware")
    as_of = as_of.astimezone(timezone.utc).replace(microsecond=0)
    norm_policy = normalize_policy(policy)
    norm = normalize_packet(packet, as_of=as_of)

    rows: list[dict] = []
    grouped: dict[tuple, list[tuple[dict, dict, str, list[str]]]] = defaultdict(list)
    action_variants: dict[str, set[tuple]] = defaultdict(set)
    identity_labels: dict[tuple, str] = {}

    for opp in norm["opportunities"]:
        minutes = _minutes_until(opp["deadline_utc"], as_of)
        if opp["route_state"] == "NO_BID" or (minutes is not None and minutes < 0):
            reason = "ROUTE_NO_BID" if opp["route_state"] == "NO_BID" else "DEADLINE_EXPIRED"
            rows.append({
                "row_id": f"terminal:{opp['id']}", "action_key": "TERMINAL", "action_label": "No live owner action", "category": "OTHER",
                "requirement_sha256": "0" * 64, "generation": 1, "state": "TERMINAL", "priority_band": "TERMINAL", "reason_codes": [reason],
                "affected_opportunity_ids": [opp["id"]], "gate_ids": [], "evidence_refs": [], "prerequisite_gate_ids": [], "blocking_gate_count": 0,
                "earliest_deadline_utc": opp["deadline_utc"], "minutes_remaining": minutes, "source_packet_ids": [opp["source"]["packet_id"]],
            })
            continue

        source_ok, source_reasons = _source_state(opp, norm_policy, as_of)
        if not source_ok:
            band = _priority_band("SOURCE_REFRESH_REQUIRED", minutes, 1, 1, norm_policy)
            rows.append({
                "row_id": f"source:{opp['id']}", "action_key": "SOURCE_REFRESH", "action_label": "Refresh authoritative blocker packet", "category": "OTHER",
                "requirement_sha256": opp["source"]["packet_sha256"], "generation": 1, "state": "SOURCE_REFRESH_REQUIRED", "priority_band": band,
                "reason_codes": source_reasons, "affected_opportunity_ids": [opp["id"]], "gate_ids": [], "evidence_refs": [], "prerequisite_gate_ids": [],
                "blocking_gate_count": 1, "earliest_deadline_utc": opp["deadline_utc"], "minutes_remaining": minutes, "source_packet_ids": [opp["source"]["packet_id"]],
            })
            continue

        by_id = {g["id"]: g for g in opp["gates"]}
        for gate in opp["gates"]:
            state, reasons = _gate_classification(gate, by_id)
            variant = (gate["requirement_sha256"], gate["generation"], gate["category"])
            action_variants[gate["action_key"]].add(variant)
            label_identity = (gate["action_key"],) + variant
            prior_label = identity_labels.get(label_identity)
            if prior_label is not None and prior_label != gate["action_label"]:
                raise ValidationError(f"action label drift for {gate['action_key']} requirement {gate['requirement_sha256']}")
            identity_labels[label_identity] = gate["action_label"]
            key = (gate["action_key"], gate["requirement_sha256"], gate["generation"], gate["category"], gate["action_label"])
            grouped[key].append((opp, gate, state, reasons))

    for key in sorted(grouped):
        action_key, req_sha, generation, category, action_label = key
        items = grouped[key]
        group_state = _choose_group_state([item[2] for item in items])
        # Completed peers cannot inflate live breadth, urgency, or lineage.
        # Retain their membership only when the entire group is non-actionable.
        if group_state != "NO_ACTION_PROVEN":
            items = [item for item in items if item[2] != "NO_ACTION_PROVEN"]
        opp_ids = sorted({item[0]["id"] for item in items})
        deadlines = [parse_utc(item[0]["deadline_utc"], "deadline") for item in items if item[0]["deadline_utc"] is not None]
        earliest = min(deadlines) if deadlines else None
        earliest_text = None if earliest is None else format_utc(earliest)
        minutes = None if earliest is None else int((earliest - as_of).total_seconds() // 60)
        gate_ids = sorted(item[1]["id"] for item in items)
        prereqs = sorted({p for item in items for p in item[1]["prerequisites"]})
        evidence = sorted({(ev["ref"], ev["sha256"]) for item in items for ev in item[1]["evidence"]})
        blocking_count = sum(1 for item in items if item[1]["blocking"] and item[1]["status"] != "PROVEN")
        reasons = sorted({r for item in items for r in item[3]})
        if len(action_variants[action_key]) > 1:
            reasons.append("INCOMPATIBLE_ACTION_VARIANTS_EXIST")
        band = _priority_band(group_state, minutes, len(opp_ids), blocking_count, norm_policy)
        rows.append({
            "row_id": f"action:{action_key}:{category}:{generation}:{req_sha}", "action_key": action_key, "action_label": action_label, "category": category,
            "requirement_sha256": req_sha, "generation": generation, "state": group_state, "priority_band": band, "reason_codes": sorted(set(reasons)),
            "affected_opportunity_ids": opp_ids, "gate_ids": gate_ids, "evidence_refs": [{"ref": r, "sha256": s} for r, s in evidence],
            "prerequisite_gate_ids": prereqs, "blocking_gate_count": blocking_count, "earliest_deadline_utc": earliest_text, "minutes_remaining": minutes,
            "source_packet_ids": sorted({item[0]["source"]["packet_id"] for item in items}),
        })

    rows.sort(key=_sort_key)
    category_projection = {}
    for category in sorted(CATEGORIES):
        ids = [row["row_id"] for row in rows if row["category"] == category]
        if ids:
            category_projection[category] = ids

    payload = {
        "output_version": OUTPUT_VERSION,
        "snapshot_id": norm["snapshot_id"],
        "evaluated_at": format_utc(as_of),
        "policy": norm_policy,
        "authority": {"owner_decision_support_only": True, "external_actions_authorized": False, "submission_authorized": False, "signature_authorized": False, "payment_or_revenue_authorized": False},
        "rows": rows,
        "category_projection": category_projection,
        "summary": {
            "opportunity_count": len(norm["opportunities"]),
            "queue_row_count": len(rows),
            "owner_action_now_count": sum(r["state"] == "OWNER_ACTION_NOW" for r in rows),
            "source_refresh_count": sum(r["state"] == "SOURCE_REFRESH_REQUIRED" for r in rows),
            "terminal_count": sum(r["state"] == "TERMINAL" for r in rows),
            "affected_live_opportunity_count": len({oid for r in rows if r["state"] not in {"TERMINAL", "NO_ACTION_PROVEN"} for oid in r["affected_opportunity_ids"]}),
        },
        "normalized_input_sha256": sha256_bytes(canonical_json_bytes(norm)),
    }
    payload["receipt_sha256"] = sha256_bytes(canonical_json_bytes(payload))
    return payload


def _semantic_projection(compiled: dict) -> list[tuple]:
    return [(row["row_id"], row["state"], row["priority_band"], tuple(row["reason_codes"]), tuple(row["affected_opportunity_ids"]), row["blocking_gate_count"]) for row in compiled["rows"]]


def verify_cockpit(packet: Any, policy: Any, compiled: Any, *, current_as_of: datetime) -> bool:
    if type(compiled) is not dict:
        raise ValidationError("compiled output must be object")
    expected_top = {"output_version", "snapshot_id", "evaluated_at", "policy", "authority", "rows", "category_projection", "summary", "normalized_input_sha256", "receipt_sha256"}
    _exact_keys(compiled, expected_top, "compiled")
    if compiled["output_version"] != OUTPUT_VERSION:
        raise ValidationError("unsupported output_version")
    receipt = _hash(compiled["receipt_sha256"], "compiled.receipt_sha256")
    unsigned = dict(compiled)
    unsigned.pop("receipt_sha256")
    if sha256_bytes(canonical_json_bytes(unsigned)) != receipt:
        return False
    historical_time = parse_utc(compiled["evaluated_at"], "compiled.evaluated_at")
    historical = compile_cockpit(packet, policy, as_of=historical_time)
    if canonical_json_bytes(historical) != canonical_json_bytes(compiled):
        return False
    if current_as_of.tzinfo is None:
        raise ValidationError("current_as_of must be timezone-aware")
    current_as_of = current_as_of.astimezone(timezone.utc).replace(microsecond=0)
    if current_as_of < historical_time:
        return False
    current = compile_cockpit(packet, policy, as_of=current_as_of)
    return _semantic_projection(current) == _semantic_projection(compiled)


def render_markdown(compiled: dict) -> str:
    rows = compiled.get("rows")
    if type(rows) is not list:
        raise ValidationError("compiled rows missing")
    lines = [
        "# Bid Owner Action Cockpit", "", f"- Snapshot: `{compiled['snapshot_id']}`", f"- Evaluated at: `{compiled['evaluated_at']}`",
        f"- Receipt: `{compiled['receipt_sha256']}`", "- Authority: owner decision support only; no external action, signature, submission, payment, or revenue authority.", "",
        "| Priority | State | Action | Category | Opportunities | Deadline | Reasons |", "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        opps = ", ".join(f"`{x}`" for x in row["affected_opportunity_ids"])
        deadline = row["earliest_deadline_utc"] or "—"
        reasons = ", ".join(row["reason_codes"]) or "—"
        label = row["action_label"].replace("|", "\\|")
        lines.append(f"| {row['priority_band']} | {row['state']} | {label} | {row['category']} | {opps} | {deadline} | {reasons} |")
    lines.extend(["", "## Category index", ""])
    for category, row_ids in compiled["category_projection"].items():
        lines.append(f"- **{category}**: " + ", ".join(f"`{rid}`" for rid in row_ids))
    lines.append("")
    return "\n".join(lines)
