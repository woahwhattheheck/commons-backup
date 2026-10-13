"""Decision, receipt, verification and CLI for the post-delivery gate."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime as _stdlib_datetime, timezone as _stdlib_timezone
from pathlib import Path
from types import FunctionType as _FunctionType
from typing import Any

from . import common as _common_module, model as _model_module
from ._trusted_runtime import (
    get_or_build_current_api as _get_or_build_current_api,
    trusted_builtins_copy as _trusted_builtins_copy,
)
from .common import (
    RECEIPT_SCHEMA, READY, HOLD_ACCEPTANCE, HOLD_PAYMENT, HOLD_WINDOW, HOLD_EVIDENCE, DNR, STATES, GateError, _ts, _dt, digest, authority_flags, canonical_json, load_json
)
from .model import _normalize


def _commercial_generation(normalized: dict[str, Any]) -> int:
    approved = [x["generation"] for x in normalized["change_orders"] if x["status"] == "APPROVED"]
    return max([normalized["baseline"]["generation"], *approved])


def _expected_total(normalized: dict[str, Any], *, _error=GateError) -> int:
    total = normalized["baseline"]["accepted_total_cents"]
    for row in normalized["change_orders"]:
        if row["status"] == "APPROVED":
            total += row["delta_cents"]
    if total < 0:
        raise _error("commercial lineage: approved total cannot be negative")
    return total


def _decision(normalized: dict[str, Any], now: str, *, _commercial_generation_fn=_commercial_generation, _expected_total_fn=_expected_total, _dt_fn=_dt) -> tuple[str, list[str]]:
    reasons: list[str] = []
    route = normalized["route_control"]
    if route["state"] == "DNR":
        return DNR, ["ROUTE_DNR"]
    baseline = normalized["baseline"]
    if baseline["status"] != "ACCEPTED":
        return HOLD_ACCEPTANCE, ["BASELINE_NOT_ACCEPTED"]
    pending_changes = [x["change_order_id"] for x in normalized["change_orders"] if x["status"] == "PENDING"]
    if pending_changes:
        return HOLD_EVIDENCE, [f"PENDING_CHANGE_ORDER:{x}" for x in pending_changes]
    commercial_generation = _commercial_generation_fn(normalized)
    bad_milestones = []
    for row in normalized["milestones"]:
        if row["commercial_generation"] != commercial_generation:
            bad_milestones.append(f"MILESTONE_GENERATION_MISMATCH:{row['milestone_id']}")
        elif row["status"] != "BUYER_HUMAN_ACCEPTED" or row["accepted_at"] is None:
            bad_milestones.append(f"MILESTONE_NOT_BUYER_HUMAN_ACCEPTED:{row['milestone_id']}")
    if bad_milestones:
        return HOLD_ACCEPTANCE, bad_milestones
    expected = _expected_total_fn(normalized)
    payment = normalized["payment"]
    payment_bad = (
        payment["commercial_generation"] != commercial_generation
        or payment["state"] != "SETTLED"
        or payment["evidence_class"] not in {"PROVIDER_SETTLEMENT", "BANK_SETTLEMENT"}
        or payment["disputed"]
        or payment["refunded_cents"] != 0
        or payment["settled_cents"] < expected
    )
    if payment_bad:
        return HOLD_PAYMENT, ["PAYMENT_NOT_FINAL_EXACT_COMMERCIAL_LINEAGE"]
    now_dt = _dt_fn(now)
    window = normalized["renewal_window"]
    if now_dt < _dt_fn(window["opens_at"]):
        return HOLD_WINDOW, ["RENEWAL_WINDOW_NOT_OPEN"]
    if now_dt > _dt_fn(window["closes_at"]):
        return HOLD_WINDOW, ["RENEWAL_WINDOW_CLOSED"]
    evidence_reasons = []
    for row in normalized["support_findings"]:
        if row["status"] == "OPEN" and row["severity"] in {"HIGH", "BLOCKING"}:
            evidence_reasons.append(f"OPEN_SUPPORT_FINDING:{row['finding_id']}")
    for row in normalized["security_data_gaps"]:
        if row["blocking"] and row["status"] == "OPEN":
            evidence_reasons.append(f"OPEN_BLOCKING_SECURITY_DATA_GAP:{row['gap_id']}")
    for row in normalized["expansion_hypotheses"]:
        if row["commercial_state"] != "PROPOSED_NOT_ACCEPTED":
            evidence_reasons.append(f"HYPOTHESIS_STATE_NOT_PROPOSED_NOT_ACCEPTED:{row['hypothesis_id']}")
        if any(row[key] for key in ("buyer_interest_claimed", "roi_claimed", "savings_claimed", "usage_claimed", "urgency_claimed", "expansion_approved_claimed")):
            evidence_reasons.append(f"HYPOTHESIS_UNSUPPORTED_CLAIM:{row['hypothesis_id']}")
    if evidence_reasons:
        return HOLD_EVIDENCE, sorted(evidence_reasons)
    return READY, []


def _compile(packet: dict[str, Any], now: str, *, _ts_fn=_ts, _normalize_fn=_normalize, _decision_fn=_decision, _commercial_generation_fn=_commercial_generation, _expected_total_fn=_expected_total, _digest_fn=digest, _authority_flags_fn=authority_flags, _receipt_schema=RECEIPT_SCHEMA) -> dict[str, Any]:
    now = _ts_fn(now, "trusted_now")
    normalized = _normalize_fn(packet, now)
    state, reasons = _decision_fn(normalized, now)
    commercial_generation = _commercial_generation_fn(normalized)
    result = {
        "schema": _receipt_schema,
        "case_id": normalized["case_id"],
        "evaluated_at": now,
        "state": state,
        "reasons": reasons,
        "commercial_generation": commercial_generation,
        "effective_total_cents": _expected_total_fn(normalized),
        "currency": normalized["baseline"]["currency"],
        "input_digest": _digest_fn(normalized),
        "commercial_lineage_digest": _digest_fn({"baseline": normalized["baseline"], "change_orders": normalized["change_orders"]}),
        "baseline_id": normalized["baseline"]["baseline_id"],
        "accepted_milestone_ids": [x["milestone_id"] for x in normalized["milestones"] if x["status"] == "BUYER_HUMAN_ACCEPTED"],
        "proposed_expansion_hypothesis_ids": [x["hypothesis_id"] for x in normalized["expansion_hypotheses"]],
        "route": {"route_id": normalized["route_control"]["route_id"], "collision_key": normalized["route_control"]["collision_key"], "muse_key": normalized["route_control"]["muse_key"], "state": normalized["route_control"]["state"]},
        "truth": {"expansion_hypotheses_remain": "PROPOSED_NOT_ACCEPTED", "buyer_signal_required_for_this_state": False, "ready_means": "OWNER_REVIEW_ONLY"},
        "authority": _authority_flags_fn(),
    }
    result["receipt_digest"] = _digest_fn(result)
    return result


def _build_current_api(*, _datetime_cls=_stdlib_datetime, _timezone_obj=_stdlib_timezone, _compiler=_compile, _decision_source=_decision, _commercial_generation_source=_commercial_generation, _expected_total_source=_expected_total, _function_type=_FunctionType, _common=_common_module, _model=_model_module, _trusted_builtins_fn=_trusted_builtins_copy, _receipt_schema=RECEIPT_SCHEMA, _state_values=STATES, _gate_error=GateError, _hold_evidence=HOLD_EVIDENCE):
    """Build the process-first-load current semantic API/error generation."""
    sealed_builtins = _trusted_builtins_fn()
    trusted_dict = sealed_builtins["dict"]
    trusted_vars = sealed_builtins["vars"]
    trusted_globals = sealed_builtins["globals"]
    trusted_getattr = sealed_builtins["getattr"]
    trusted_frozenset = sealed_builtins["frozenset"]
    trusted_tuple = sealed_builtins["tuple"]

    def _clone_function(fn, private_globals):
        clone = _function_type(fn.__code__, private_globals, fn.__name__, fn.__defaults__, fn.__closure__)
        clone.__kwdefaults__ = trusted_dict(fn.__kwdefaults__ or {})
        return clone

    common_globals = trusted_dict(trusted_vars(_common))
    common_globals["__builtins__"] = trusted_dict(sealed_builtins)
    common_helpers = ("_keys", "_string", "_bool", "_int", "_enum", "_sha", "_ts", "_dt", "_age", "_uri", "_source")
    for name in common_helpers:
        common_globals[name] = _clone_function(trusted_getattr(_common, name), common_globals)
    model_globals = trusted_dict(trusted_vars(_model))
    model_globals["__builtins__"] = trusted_dict(sealed_builtins)
    for name in common_helpers:
        model_globals[name] = common_globals[name]
    for name in ("BASELINE_STATES", "CHANGE_STATES", "MILESTONE_STATES", "PAYMENT_STATES", "PAYMENT_CLASSES", "SUPPORT_SEVERITIES", "FINDING_STATES", "GAP_STATES", "ROUTE_STATES", "HYPOTHESIS_BASES"):
        model_globals[name] = trusted_frozenset(model_globals[name])
    sealed_normalize = _clone_function(_model._normalize, model_globals)
    engine_globals = trusted_dict(trusted_globals())
    engine_globals["__builtins__"] = trusted_dict(sealed_builtins)
    sealed_commercial_generation = _clone_function(_commercial_generation_source, engine_globals)
    sealed_expected_total = _clone_function(_expected_total_source, engine_globals)
    decision_globals = trusted_dict(engine_globals)
    sealed_decision = _clone_function(_decision_source, decision_globals)
    sealed_decision.__kwdefaults__.update({"_commercial_generation_fn": sealed_commercial_generation, "_expected_total_fn": sealed_expected_total, "_dt_fn": common_globals["_dt"]})

    json_dumps = _common.json.dumps
    sha256 = _common.hashlib.sha256
    authority_keys = trusted_tuple(_common.authority_flags())
    states = trusted_frozenset(_state_values)
    builtin_type = sealed_builtins["type"]
    builtin_dict = sealed_builtins["dict"]
    builtin_list = sealed_builtins["list"]
    builtin_str = sealed_builtins["str"]
    builtin_int = sealed_builtins["int"]
    builtin_bool = sealed_builtins["bool"]
    builtin_enumerate = sealed_builtins["enumerate"]
    builtin_len = sealed_builtins["len"]
    max_abs_integer = 10**15
    max_plain_nodes = 10_000
    max_plain_chars = 2_000_000
    max_plain_bytes = 8_000_000

    def _canonical(value: Any) -> bytes:
        return (json_dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")

    def _digest_fn(value: Any) -> str:
        return sha256(_canonical(value)).hexdigest()

    def _authority_flags_fn() -> dict[str, bool]:
        return {key: False for key in authority_keys}

    def _checked_text(value: str, label: str) -> str:
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise _gate_error(f"{label}: valid UTF-8 text required") from None
        return value

    def _freeze_plain_json(value: Any, label: str) -> Any:
        """Bounded copy of one exact built-in JSON tree before semantic reads."""
        budget = {"nodes": 0, "chars": 0, "bytes": 0}

        def spend(nodes: int = 0, chars: int = 0, bytes_: int = 0) -> None:
            if budget["nodes"] + nodes > max_plain_nodes:
                raise _gate_error(f"{label}: node budget exceeded")
            if budget["chars"] + chars > max_plain_chars:
                raise _gate_error(f"{label}: character budget exceeded")
            if budget["bytes"] + bytes_ > max_plain_bytes:
                raise _gate_error(f"{label}: byte budget exceeded")
            budget["nodes"] += nodes
            budget["chars"] += chars
            budget["bytes"] += bytes_

        def freeze(current: Any, where: str, depth: int) -> Any:
            if depth > 64:
                raise _gate_error(f"{where}: nesting too deep")
            spend(nodes=1)
            kind = builtin_type(current)
            if kind is builtin_dict:
                child_count = builtin_len(current)
                if child_count > max_plain_nodes - budget["nodes"]:
                    raise _gate_error(f"{where}: node budget exceeded")
                spend(bytes_=2 + (child_count - 1 if child_count else 0))
                frozen: dict[str, Any] = {}
                for key, item in current.items():
                    if builtin_type(key) is not builtin_str:
                        raise _gate_error(f"{where}: string object keys required")
                    key_chars = builtin_len(key)
                    if key_chars > max_plain_chars - budget["chars"]:
                        raise _gate_error(f"{where}: character budget exceeded")
                    spend(chars=key_chars)
                    _checked_text(key, f"{where}: object key")
                    key_bytes = json_dumps(key, ensure_ascii=False).encode("utf-8")
                    spend(bytes_=builtin_len(key_bytes) + 1)
                    frozen[key] = freeze(item, f"{where}.<field>", depth + 1)
                return frozen
            if kind is builtin_list:
                child_count = builtin_len(current)
                if child_count > max_plain_nodes - budget["nodes"]:
                    raise _gate_error(f"{where}: node budget exceeded")
                spend(bytes_=2 + (child_count - 1 if child_count else 0))
                frozen = []
                for index, item in builtin_enumerate(current):
                    frozen.append(freeze(item, f"{where}[{index}]", depth + 1))
                return frozen
            if current is None:
                spend(bytes_=4)
                return current
            if kind is builtin_bool:
                spend(bytes_=4 if current else 5)
                return current
            if kind is builtin_str:
                text_chars = builtin_len(current)
                if text_chars > max_plain_chars - budget["chars"]:
                    raise _gate_error(f"{where}: character budget exceeded")
                spend(chars=text_chars)
                _checked_text(current, where)
                text_bytes = json_dumps(current, ensure_ascii=False).encode("utf-8")
                spend(bytes_=builtin_len(text_bytes))
                return current
            if kind is builtin_int:
                if current < -max_abs_integer or current > max_abs_integer:
                    raise _gate_error(f"{where}: integer outside supported range")
                spend(bytes_=builtin_len(builtin_str(current)))
                return current
            raise _gate_error(f"{where}: exact built-in plain-JSON value required")

        return freeze(value, label, 0)

    def _project(receipt: dict[str, Any]) -> dict[str, Any]:
        projected = builtin_dict(receipt)
        projected.pop("evaluated_at", None)
        projected.pop("receipt_digest", None)
        return projected

    def _sealed_compile(packet: dict[str, Any], now: str) -> dict[str, Any]:
        return _compiler(packet, now, _ts_fn=common_globals["_ts"], _normalize_fn=sealed_normalize, _decision_fn=sealed_decision, _commercial_generation_fn=sealed_commercial_generation, _expected_total_fn=sealed_expected_total, _digest_fn=_digest_fn, _authority_flags_fn=_authority_flags_fn, _receipt_schema=_receipt_schema)

    def _clock_text() -> str:
        return _datetime_cls.now(_timezone_obj.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def compile_current(packet: dict[str, Any]) -> dict[str, Any]:
        frozen_packet = _freeze_plain_json(packet, "packet")
        return _sealed_compile(frozen_packet, _clock_text())

    def verify_receipt(packet: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
        """Authenticate exact historical semantics, then re-evaluate at current UTC."""
        frozen_packet = _freeze_plain_json(packet, "packet")
        supplied = _freeze_plain_json(receipt, "receipt")
        claimed = supplied.get("receipt_digest")
        unsigned = builtin_dict(supplied)
        unsigned.pop("receipt_digest", None)
        if builtin_type(claimed) is not builtin_str or claimed != _digest_fn(unsigned):
            raise _gate_error("receipt: digest mismatch")
        if supplied.get("schema") != _receipt_schema or supplied.get("state") not in states:
            raise _gate_error("receipt: unsupported schema/state")
        evaluated_at = supplied.get("evaluated_at")
        if builtin_type(evaluated_at) is not builtin_str:
            raise _gate_error("receipt: evaluated_at required")
        try:
            historical = _sealed_compile(frozen_packet, evaluated_at)
        except _gate_error as exc:
            raise _gate_error(f"receipt: historical recompile failed: {exc}") from exc
        if _canonical(historical) != _canonical(supplied):
            raise _gate_error("receipt: semantic mismatch")
        current_now = _clock_text()
        if common_globals["_dt"](evaluated_at) > common_globals["_dt"](current_now):
            raise _gate_error("receipt: evaluated_at is in the future")
        try:
            current = _sealed_compile(frozen_packet, current_now)
        except _gate_error as exc:
            return {"integrity_valid": True, "prior_state": historical["state"], "current_state": _hold_evidence, "current_reasons": [f"CURRENT_REEVALUATION_FAILED:{exc}"], "current_receipt_digest": None, "still_current": False}
        return {"integrity_valid": True, "prior_state": historical["state"], "current_state": current["state"], "current_reasons": current["reasons"], "current_receipt_digest": current["receipt_digest"], "still_current": _canonical(_project(historical)) == _canonical(_project(current))}

    return compile_current, verify_receipt, _gate_error


compile_current, verify_receipt, GateError = _get_or_build_current_api(_build_current_api)
del _build_current_api
del _get_or_build_current_api
del _trusted_builtins_copy
del _FunctionType
del _common_module
del _model_module
del _stdlib_datetime
del _stdlib_timezone


def _read(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise GateError(f"{path}: regular file required")
    try:
        return load_json(path.read_bytes(), str(path))
    except ValueError as exc:
        raise GateError(str(exc)) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_compile = sub.add_parser("compile")
    p_compile.add_argument("packet")
    p_compile.add_argument("--output")
    p_verify = sub.add_parser("verify")
    p_verify.add_argument("packet")
    p_verify.add_argument("receipt")
    args = parser.parse_args(argv)
    try:
        packet = _read(Path(args.packet))
        if args.cmd == "compile":
            receipt = compile_current(packet)
            raw = canonical_json(receipt)
            if args.output:
                out = Path(args.output)
                if out.exists() or out.is_symlink():
                    raise GateError("output: refusing overwrite")
                out.write_bytes(raw)
            else:
                print(raw.decode("utf-8"), end="")
            return 0 if receipt["state"] == READY else 2
        result = verify_receipt(packet, _read(Path(args.receipt)))
        print(canonical_json(result).decode("utf-8"), end="")
        return 0 if result["still_current"] else 2
    except (GateError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
