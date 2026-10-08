from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

INPUT_SCHEMA = "commons.workfeed-poll-planner/input/v1"
OUTPUT_SCHEMA = "commons.workfeed-poll-planner/result/v1"
MAX_JSON_BYTES = 1_048_576
MAX_SURFACES = 256
MAX_INT = 9_007_199_254_740_991
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 8_192
MAX_STRING_CHARS = 262_144
SURFACE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
GENERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,159}$")
SURFACE_CLASSES = {
    "coordination",
    "hot_lead",
    "merge_queue",
    "build_demand",
    "work_feed",
    "archive",
}
CLASS_WEIGHT = {
    "coordination": 6_000_000,
    "hot_lead": 5_500_000,
    "merge_queue": 4_500_000,
    "build_demand": 4_000_000,
    "work_feed": 2_500_000,
    "archive": 500_000,
}
HIGH_FRESHNESS_CLASSES = {"coordination", "hot_lead"}
INPUT_KEYS = {
    "schema",
    "evaluation_utc",
    "request_budget",
    "evidence_ttl_seconds",
    "backoff_base_seconds",
    "backoff_cap_seconds",
    "surfaces",
}
SURFACE_KEYS = {
    "surface_id",
    "surface_class",
    "snapshot_generation",
    "snapshot_observed_utc",
    "last_success_utc",
    "last_throttle_utc",
    "retry_after_seconds",
    "consecutive_throttles",
    "min_poll_interval_seconds",
    "max_staleness_seconds",
    "unread_estimate",
    "backlog_estimate",
    "covered_by_generation",
}
AUTHORITY = {
    "network_io_performed": False,
    "provider_read_proven": False,
    "external_action_authorized": False,
    "payment_or_revenue_state_changed": False,
}


class PlannerError(ValueError):
    pass


def _reject_float(value: str) -> None:
    raise PlannerError("floating point values are not accepted")


def _reject_constant(value: str) -> None:
    raise PlannerError("non-finite numeric values are not accepted")


def _parse_int(text: str) -> int:
    value = int(text)
    if abs(value) > MAX_INT:
        raise PlannerError("integer exceeds safe bound")
    return value


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise PlannerError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_json_loads(raw: str | bytes) -> Any:
    if type(raw) not in (str, bytes):
        raise PlannerError("JSON input must be exact str or bytes")
    if type(raw) is bytes:
        if len(raw) > MAX_JSON_BYTES:
            raise PlannerError("JSON input exceeds byte limit")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PlannerError("JSON input is not UTF-8") from exc
    else:
        try:
            encoded = raw.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise PlannerError("JSON input contains invalid Unicode") from exc
        if len(encoded) > MAX_JSON_BYTES:
            raise PlannerError("JSON input exceeds byte limit")
        text = raw
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            parse_int=_parse_int,
        )
        _validate_json_tree(value)
        return value
    except PlannerError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise PlannerError("invalid JSON") from exc


def _validate_json_tree(value: Any) -> None:
    nodes = 0

    def visit(item: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise PlannerError("JSON node limit exceeded")
        if depth > MAX_JSON_DEPTH:
            raise PlannerError("JSON depth limit exceeded")
        if item is None or type(item) in (bool, int):
            return
        if type(item) is str:
            if len(item) > MAX_STRING_CHARS:
                raise PlannerError("JSON string limit exceeded")
            if any(0xD800 <= ord(ch) <= 0xDFFF for ch in item):
                raise PlannerError("JSON contains lone surrogate")
            return
        if type(item) is list:
            for child in item:
                visit(child, depth + 1)
            return
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise PlannerError("JSON object key must be text")
                visit(key, depth + 1)
                visit(child, depth + 1)
            return
        raise PlannerError("JSON contains unsupported value type")

    visit(value, 0)


def _require_exact_keys(obj: dict[str, Any], expected: set[str], label: str) -> None:
    extras = set(obj) - expected
    missing = expected - set(obj)
    if extras or missing:
        raise PlannerError(
            f"{label} keys mismatch: missing={sorted(missing)} extra={sorted(extras)}"
        )


def _bounded_int(value: Any, label: str, low: int, high: int) -> int:
    if type(value) is not int:
        raise PlannerError(f"{label} must be an integer")
    if not low <= value <= high:
        raise PlannerError(f"{label} out of range")
    return value


def _text(value: Any, label: str, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or not pattern.fullmatch(value):
        raise PlannerError(f"{label} has invalid shape")
    return value


def _utc(value: Any, label: str) -> tuple[str, int]:
    if type(value) is not str:
        raise PlannerError(f"{label} must be UTC text")
    if not value.endswith("Z") or len(value) != 20:
        raise PlannerError(f"{label} must use YYYY-MM-DDTHH:MM:SSZ")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise PlannerError(f"{label} is not a valid UTC timestamp") from exc
    normalized = parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
    if normalized != value:
        raise PlannerError(f"{label} is not canonical UTC")
    return normalized, calendar.timegm(parsed.utctimetuple())


def _optional_utc(value: Any, label: str) -> tuple[str | None, int | None]:
    if value is None:
        return None, None
    return _utc(value, label)


def _format_utc(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


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
        raise PlannerError("value is not canonically serializable") from exc


def _validate_packet(packet: Any) -> dict[str, Any]:
    if type(packet) is not dict:
        raise PlannerError("top-level packet must be an object")
    _require_exact_keys(packet, INPUT_KEYS, "packet")
    if packet["schema"] != INPUT_SCHEMA:
        raise PlannerError("unsupported input schema")
    evaluation_utc, evaluation_epoch = _utc(
        packet["evaluation_utc"], "evaluation_utc"
    )
    request_budget = _bounded_int(packet["request_budget"], "request_budget", 0, 256)
    evidence_ttl = _bounded_int(
        packet["evidence_ttl_seconds"], "evidence_ttl_seconds", 1, 604_800
    )
    backoff_base = _bounded_int(
        packet["backoff_base_seconds"], "backoff_base_seconds", 1, 3_600
    )
    backoff_cap = _bounded_int(
        packet["backoff_cap_seconds"], "backoff_cap_seconds", backoff_base, 86_400
    )
    surfaces = packet["surfaces"]
    if type(surfaces) is not list or not 1 <= len(surfaces) <= MAX_SURFACES:
        raise PlannerError("surfaces must be a non-empty bounded array")

    normalized_surfaces: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_surface in enumerate(surfaces):
        label = f"surfaces[{index}]"
        if type(raw_surface) is not dict:
            raise PlannerError(f"{label} must be an object")
        _require_exact_keys(raw_surface, SURFACE_KEYS, label)
        surface_id = _text(raw_surface["surface_id"], f"{label}.surface_id", SURFACE_ID_RE)
        if surface_id in seen_ids:
            raise PlannerError(f"duplicate surface_id: {surface_id}")
        seen_ids.add(surface_id)
        surface_class = raw_surface["surface_class"]
        if type(surface_class) is not str or surface_class not in SURFACE_CLASSES:
            raise PlannerError(f"{label}.surface_class is unsupported")
        generation = _text(
            raw_surface["snapshot_generation"],
            f"{label}.snapshot_generation",
            GENERATION_RE,
        )
        observed_utc, observed_epoch = _utc(
            raw_surface["snapshot_observed_utc"],
            f"{label}.snapshot_observed_utc",
        )
        if observed_epoch > evaluation_epoch:
            raise PlannerError(f"{label}.snapshot_observed_utc is in the future")
        last_success_utc, last_success_epoch = _optional_utc(
            raw_surface["last_success_utc"], f"{label}.last_success_utc"
        )
        last_throttle_utc, last_throttle_epoch = _optional_utc(
            raw_surface["last_throttle_utc"], f"{label}.last_throttle_utc"
        )
        for event_label, event_epoch in (
            ("last_success_utc", last_success_epoch),
            ("last_throttle_utc", last_throttle_epoch),
        ):
            if event_epoch is not None and event_epoch > evaluation_epoch:
                raise PlannerError(f"{label}.{event_label} is in the future")
            if event_epoch is not None and event_epoch > observed_epoch:
                raise PlannerError(f"{label}.{event_label} postdates retained snapshot")

        retry_after = _bounded_int(
            raw_surface["retry_after_seconds"],
            f"{label}.retry_after_seconds",
            0,
            86_400,
        )
        throttle_count = _bounded_int(
            raw_surface["consecutive_throttles"],
            f"{label}.consecutive_throttles",
            0,
            32,
        )
        if last_throttle_epoch is None and (retry_after or throttle_count):
            raise PlannerError(f"{label} throttle details require last_throttle_utc")
        if last_throttle_epoch is not None and throttle_count == 0:
            raise PlannerError(f"{label} last_throttle_utc requires throttle count")
        if (
            last_success_epoch is not None
            and last_throttle_epoch is not None
            and last_success_epoch > last_throttle_epoch
        ):
            raise PlannerError(
                f"{label} throttle state conflicts with later successful read"
            )
        min_interval = _bounded_int(
            raw_surface["min_poll_interval_seconds"],
            f"{label}.min_poll_interval_seconds",
            0,
            86_400,
        )
        max_staleness = _bounded_int(
            raw_surface["max_staleness_seconds"],
            f"{label}.max_staleness_seconds",
            1,
            604_800,
        )
        unread = _bounded_int(
            raw_surface["unread_estimate"], f"{label}.unread_estimate", 0, 1_000_000
        )
        backlog = _bounded_int(
            raw_surface["backlog_estimate"],
            f"{label}.backlog_estimate",
            0,
            1_000_000,
        )
        covered = raw_surface["covered_by_generation"]
        if covered is not None:
            covered = _text(
                covered, f"{label}.covered_by_generation", GENERATION_RE
            )

        normalized_surfaces.append(
            {
                "surface_id": surface_id,
                "surface_class": surface_class,
                "snapshot_generation": generation,
                "snapshot_observed_utc": observed_utc,
                "_snapshot_observed_epoch": observed_epoch,
                "last_success_utc": last_success_utc,
                "_last_success_epoch": last_success_epoch,
                "last_throttle_utc": last_throttle_utc,
                "_last_throttle_epoch": last_throttle_epoch,
                "retry_after_seconds": retry_after,
                "consecutive_throttles": throttle_count,
                "min_poll_interval_seconds": min_interval,
                "max_staleness_seconds": max_staleness,
                "unread_estimate": unread,
                "backlog_estimate": backlog,
                "covered_by_generation": covered,
            }
        )
    return {
        "schema": INPUT_SCHEMA,
        "evaluation_utc": evaluation_utc,
        "_evaluation_epoch": evaluation_epoch,
        "request_budget": request_budget,
        "evidence_ttl_seconds": evidence_ttl,
        "backoff_base_seconds": backoff_base,
        "backoff_cap_seconds": backoff_cap,
        "surfaces": normalized_surfaces,
    }


def _backoff_seconds(base: int, cap: int, count: int) -> int:
    if count <= 0:
        return 0
    exponent = min(count - 1, 20)
    return min(cap, base * (1 << exponent))


def _priority_score(surface: dict[str, Any], evaluation_epoch: int) -> tuple[int, int]:
    last_success = surface["_last_success_epoch"]
    max_staleness = surface["max_staleness_seconds"]
    if last_success is None:
        age = max_staleness * 8
    else:
        age = max(0, evaluation_epoch - last_success)
    age_points = min(8_000_000, age * 1_000_000 // max_staleness)
    starvation = 4_000_000 if age >= max_staleness * 4 else 0
    unread_bonus = min(250_000, surface["unread_estimate"] * 2_000)
    backlog_bonus = min(250_000, surface["backlog_estimate"] * 1_000)
    score = (
        CLASS_WEIGHT[surface["surface_class"]]
        + age_points
        + starvation
        + unread_bonus
        + backlog_bonus
    )
    return score, age


def _needs_poll(surface: dict[str, Any], age_since_success: int) -> bool:
    if surface["_last_success_epoch"] is None:
        return True
    if surface["unread_estimate"] or surface["backlog_estimate"]:
        return True
    threshold = surface["max_staleness_seconds"]
    if surface["surface_class"] in HIGH_FRESHNESS_CLASSES:
        threshold = max(1, threshold // 2)
    return age_since_success >= threshold


def compile_plan(packet: Any) -> dict[str, Any]:
    normalized = _validate_packet(packet)
    now = normalized["_evaluation_epoch"]
    ttl = normalized["evidence_ttl_seconds"]
    base = normalized["backoff_base_seconds"]
    cap = normalized["backoff_cap_seconds"]

    rows: list[dict[str, Any]] = []
    runnable: list[dict[str, Any]] = []
    stale_evidence = False
    rate_blocked_required = False

    for surface in normalized["surfaces"]:
        score, age_success = _priority_score(surface, now)
        evidence_age = now - surface["_snapshot_observed_epoch"]
        is_stale_evidence = evidence_age > ttl
        stale_evidence = stale_evidence or is_stale_evidence

        min_until = (
            surface["_last_success_epoch"] + surface["min_poll_interval_seconds"]
            if surface["_last_success_epoch"] is not None
            else 0
        )
        throttle_until = 0
        if surface["_last_throttle_epoch"] is not None:
            wait = max(
                surface["retry_after_seconds"],
                _backoff_seconds(base, cap, surface["consecutive_throttles"]),
            )
            throttle_until = surface["_last_throttle_epoch"] + wait
        next_safe = max(min_until, throttle_until)
        # A covered snapshot is redundant only while the source evidence is fresh.
        # Once its TTL expires, the ordinary poll/backoff gates must run again.
        redundant = (
            not is_stale_evidence
            and surface["covered_by_generation"] is not None
            and surface["covered_by_generation"] == surface["snapshot_generation"]
        )
        needed = _needs_poll(surface, age_success)
        row = {
            "surface_id": surface["surface_id"],
            "surface_class": surface["surface_class"],
            "snapshot_generation": surface["snapshot_generation"],
            "decision": "",
            "reason": "",
            "next_safe_utc": _format_utc(max(next_safe, now)),
            "evidence_age_seconds": evidence_age,
            "evidence_stale": is_stale_evidence,
            "age_since_success_seconds": age_success,
            "priority_score": score,
            "request_allocated": False,
        }

        if redundant:
            row["decision"] = "SKIP_REDUNDANT"
            row["reason"] = "snapshot_generation_already_covered"
        elif throttle_until > now:
            row["decision"] = "HOLD_THROTTLED"
            row["reason"] = "retained_rate_limit_backoff"
            if needed:
                rate_blocked_required = True
        elif min_until > now:
            row["decision"] = "POLL_LATER"
            row["reason"] = "minimum_poll_interval"
        elif not needed:
            row["decision"] = "POLL_LATER"
            row["reason"] = "retained_evidence_fresh_enough"
        else:
            row["decision"] = "PENDING_BUDGET"
            row["reason"] = "eligible_for_budget"
            runnable.append(row)
        rows.append(row)

    runnable.sort(key=lambda row: (-row["priority_score"], row["surface_id"]))
    budget = normalized["request_budget"]
    allocated = 0
    budget_degraded = len(runnable) > budget
    for row in runnable:
        if allocated < budget:
            row["decision"] = "POLL_NOW"
            row["reason"] = "selected_by_priority_and_fairness"
            row["request_allocated"] = True
            allocated += 1
        else:
            row["decision"] = "POLL_LATER"
            row["reason"] = "request_budget_exhausted"
            budget_degraded = True

    if stale_evidence:
        coverage = "DEGRADED_STALE_EVIDENCE"
    elif rate_blocked_required:
        coverage = "DEGRADED_RATE_LIMIT"
    elif budget_degraded:
        coverage = "DEGRADED_BUDGET"
    else:
        coverage = "COMPLETE"

    rows.sort(key=lambda row: row["surface_id"])
    payload = {
        "schema": OUTPUT_SCHEMA,
        "evaluation_utc": normalized["evaluation_utc"],
        "request_budget": budget,
        "allocated_requests": allocated,
        "coverage": coverage,
        "surfaces": rows,
        "authority": dict(AUTHORITY),
    }
    payload["receipt_sha256"] = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    return payload


def verify_plan(packet: Any, plan: Any) -> bool:
    if type(plan) is not dict:
        return False
    try:
        expected = compile_plan(packet)
    except PlannerError:
        return False
    return canonical_bytes(expected) == canonical_bytes(plan)


def render_markdown(plan: Any) -> str:
    if type(plan) is not dict or plan.get("schema") != OUTPUT_SCHEMA:
        raise PlannerError("expected a compiled plan")
    lines = [
        "# Work-feed polling plan",
        "",
        f"- Evaluation: {plan['evaluation_utc']}",
        f"- Coverage: **{plan['coverage']}**",
        f"- Request budget: {plan['request_budget']}",
        f"- Allocated now: {plan['allocated_requests']}",
        f"- Receipt: {plan['receipt_sha256']}",
        "",
        "| Surface | Class | Decision | Reason | Next safe | Score |",
        "|---|---|---|---|---|---:|",
    ]
    for row in plan["surfaces"]:
        lines.append(
            f"| {row['surface_id']} | {row['surface_class']} | "
            f"{row['decision']} | {row['reason']} | {row['next_safe_utc']} | "
            f"{row['priority_score']} |"
        )
    lines.extend(
        [
            "",
            "This plan is derived from retained observations only. It does not prove that any provider read occurred.",
            "",
        ]
    )
    return "\n".join(lines)


def _read_json(path: str) -> Any:
    try:
        return strict_json_loads(Path(path).read_bytes())
    except OSError as exc:
        raise PlannerError(f"cannot read {path}") from exc


def _write_exclusive(path: str, data: bytes) -> None:
    try:
        with Path(path).open("xb") as handle:
            handle.write(data)
            handle.flush()
    except OSError as exc:
        raise PlannerError(f"cannot create output {path}") from exc


def _compile_command(args: argparse.Namespace) -> int:
    packet = _read_json(args.input)
    plan = compile_plan(packet)
    _write_exclusive(args.output, canonical_bytes(plan) + b"\n")
    if args.markdown:
        _write_exclusive(args.markdown, render_markdown(plan).encode("utf-8"))
    return 0


def _verify_command(args: argparse.Namespace) -> int:
    packet = _read_json(args.input)
    plan = _read_json(args.plan)
    return 0 if verify_plan(packet, plan) else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline work-feed polling planner")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_parser = sub.add_parser("compile")
    compile_parser.add_argument("input")
    compile_parser.add_argument("output")
    compile_parser.add_argument("--markdown")
    compile_parser.set_defaults(func=_compile_command)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("input")
    verify_parser.add_argument("plan")
    verify_parser.set_defaults(func=_verify_command)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        return int(args.func(args))
    except PlannerError as exc:
        parser.exit(2, f"workfeed-poll-planner: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
