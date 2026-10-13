"""Compose installed-connector metadata, the Jev ledger, and action-loop plans.

The module is transport-free. Callers supply the raw-private-text-free connector metadata
accepted by ``jev_connector_projection`` plus a typed result from the existing Jev client.
Only a fresh, complete selected source may produce an action plan. Provider execution and
readback remain connector/controller responsibilities.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from integrations.command_center import jev_action_loop as action_loop
from integrations.command_center import jev_connector_projection as connector_projection
from integrations.command_center import jev_event_ledger as event_ledger

BUNDLE_SCHEMA = "commons.jev_routing_pipeline.bundle/v1"
MAX_BYTES = 8 * 1024 * 1024
MAX_ROUTES = 256
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/#@+-]{0,255}\Z")
UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
HEX64_RE = re.compile(r"[0-9a-f]{64}\Z")
AUTHORITY = {
    "connector_read_authority": False,
    "jev_call_authority": False,
    "provider_write_authority": False,
    "claim_authority": False,
    "merge_authority": False,
    "payment_authority": False,
    "raw_private_text_included": False,
}


class RoutingPipelineError(ValueError):
    """Malformed, ambiguous, privacy-unsafe, or cross-generation routing input."""


def _canonical(value: Any) -> bytes:
    try:
        data = json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise RoutingPipelineError("not canonical JSON data") from exc
    if len(data) > MAX_BYTES:
        raise RoutingPipelineError("routing bundle byte limit exceeded")
    return data


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _exact(value: Any, fields: set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        raise RoutingPipelineError(f"{where}: unexpected or missing fields")
    return value


def _token(value: Any, where: str) -> str:
    if type(value) is not str or TOKEN_RE.fullmatch(value) is None:
        raise RoutingPipelineError(f"{where}: invalid identifier")
    return value


def _stamp(value: Any, where: str) -> str:
    if type(value) is not str or UTC_RE.fullmatch(value) is None:
        raise RoutingPipelineError(f"{where}: timestamp must be RFC3339 UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise RoutingPipelineError(f"{where}: invalid timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise RoutingPipelineError(f"{where}: timestamp is not UTC")
    return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _confidence_ppm(value: Any) -> int:
    if type(value) not in {int, float} or type(value) is bool:
        raise RoutingPipelineError("jev lane confidence must be numeric")
    if isinstance(value, float) and not math.isfinite(value):
        raise RoutingPipelineError("jev lane confidence must be finite")
    try:
        dec = Decimal(str(value))
    except InvalidOperation as exc:
        raise RoutingPipelineError("jev lane confidence is invalid") from exc
    if not Decimal("0") <= dec <= Decimal("1"):
        raise RoutingPipelineError("jev lane confidence must be in [0,1]")
    return int((dec * Decimal(1_000_000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _normalize_ref(raw: Any) -> dict[str, str]:
    row = dict(_exact(
        raw,
        {"source_id", "provider_event_id", "resource_scope", "event_type"},
        "selected_record",
    ))
    row["source_id"] = _token(row["source_id"], "selected_record.source_id")
    if type(row["provider_event_id"]) is not str or not row["provider_event_id"]:
        raise RoutingPipelineError("selected_record.provider_event_id: invalid opaque id")
    row["resource_scope"] = _token(row["resource_scope"], "selected_record.resource_scope")
    row["event_type"] = _token(row["event_type"], "selected_record.event_type")
    return row


def _latest_observation(records: list[dict[str, Any]], where: str) -> dict[str, Any]:
    """Select the latest read while retaining one immutable event identity."""
    if not records:
        raise RoutingPipelineError(f"{where} is absent")
    identity = None
    latest = records[0]
    latest_at = ""
    for record in records:
        semantic = dict(record)
        observed_at = _stamp(semantic.pop("observed_at", None), f"{where}.observed_at")
        semantic["provider_event_time"] = _stamp(
            semantic.get("provider_event_time"), f"{where}.provider_event_time"
        )
        if identity is None:
            identity = semantic
        elif semantic != identity:
            raise RoutingPipelineError(f"{where} has contradictory event metadata")
        if observed_at > latest_at:
            latest = record
            latest_at = observed_at
    return latest


def _find_raw_record(packet: dict[str, Any], ref: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    if type(packet) is not dict or type(packet.get("sources")) is not list:
        raise RoutingPipelineError("connector packet is not source-shaped")
    sources = [row for row in packet["sources"] if type(row) is dict and row.get("source_id") == ref["source_id"]]
    if len(sources) != 1:
        raise RoutingPipelineError("selected_record source_id is absent or ambiguous")
    source = sources[0]
    records = source.get("records")
    if type(records) is not list:
        raise RoutingPipelineError("selected_record source has no records")
    matches = [
        row for row in records
        if type(row) is dict
        and row.get("provider_event_id") == ref["provider_event_id"]
        and row.get("resource_scope") == ref["resource_scope"]
        and row.get("event_type") == ref["event_type"]
    ]
    return source, _latest_observation(matches, "selected_record")


def _selected_event_id(source: dict[str, Any], ref: dict[str, str]) -> str:
    provider = source.get("provider")
    if type(provider) is not str or not provider:
        raise RoutingPipelineError("selected_record source provider is invalid")
    material = (
        f"{provider}\0{ref['resource_scope']}\0{ref['event_type']}\0"
        f"{ref['provider_event_id']}"
    ).encode("utf-8")
    return "evt-" + hashlib.sha256(material).hexdigest()


def _route_table(raw: Any) -> dict[str, dict[str, Any]]:
    if type(raw) is not dict or not 1 <= len(raw) <= MAX_ROUTES:
        raise RoutingPipelineError("route_map: invalid count")
    result: dict[str, dict[str, Any]] = {}
    for raw_lane, raw_target in raw.items():
        lane = _token(raw_lane, "route_map lane")
        target = dict(_exact(
            raw_target,
            {"action", "provider", "destination_id", "thread_id"},
            f"route_map.{lane}",
        ))
        if target["provider"] not in action_loop.PROVIDERS:
            raise RoutingPipelineError(f"route_map.{lane}: unsupported provider")
        target["destination_id"] = _token(target["destination_id"], f"route_map.{lane}.destination_id")
        if target["thread_id"] is not None:
            target["thread_id"] = _token(target["thread_id"], f"route_map.{lane}.thread_id")
        if target["action"] == "ROUTE_SLACK" and target["provider"] != "slack":
            raise RoutingPipelineError(f"route_map.{lane}: ROUTE_SLACK requires slack provider")
        result[lane] = target
    return result


def _jev_projection(raw: Any) -> dict[str, Any]:
    row = dict(_exact(raw, {"surface", "model", "answers", "error", "decided_at"}, "jev_result"))
    row["surface"] = _token(row["surface"], "jev_result.surface")
    row["model"] = _token(row["model"], "jev_result.model")
    row["decided_at"] = _stamp(row["decided_at"], "jev_result.decided_at")
    if row["error"] is not None:
        if (type(row["error"]) is not str or not row["error"] or len(row["error"]) > 512
                or any(ord(ch) < 32 for ch in row["error"])):
            raise RoutingPipelineError("jev_result.error is invalid")
    if type(row["answers"]) is not dict:
        raise RoutingPipelineError("jev_result.answers must be an object")
    _canonical(row["answers"])
    return row


def _lane_answer(jev: dict[str, Any]) -> tuple[str, int]:
    lane = jev["answers"].get("lane")
    if type(lane) is not dict or set(lane) - {"choice", "confidence", "probabilities"}:
        raise RoutingPipelineError("jev_result.answers.lane is invalid")
    return (
        _token(lane.get("choice"), "jev_result.answers.lane.choice"),
        _confidence_ppm(lane.get("confidence")),
    )


def _source_is_complete(source: dict[str, Any]) -> bool:
    coverage = source.get("coverage")
    return (
        source.get("status") == "OK"
        and source.get("freshness") == "FRESH"
        and type(coverage) is dict
        and coverage.get("complete") is True
        and coverage.get("has_more") is False
    )


def compile_bundle(
    connector_packet: dict[str, Any],
    *,
    selected_record: dict[str, Any],
    jev_result: dict[str, Any],
    route_map: dict[str, Any],
    provider_status: str,
    prior_receipts: list[dict[str, Any]] | None = None,
    evaluated_at: str | None = None,
    min_confidence_ppm: int = 700_000,
) -> dict[str, Any]:
    """Compile one exact connector event into a Jev-selected action-loop generation."""
    ref = _normalize_ref(selected_record)
    raw_source, raw_record = _find_raw_record(connector_packet, ref)
    projected = connector_projection.project(copy.deepcopy(connector_packet))
    report = event_ledger.compile_ledger(projected, evaluated_at=evaluated_at)
    if not event_ledger.verify_report(report):
        raise RoutingPipelineError("landed event-ledger report verification failed")

    selected_event_id = _selected_event_id(raw_source, ref)
    projected_events = [
        row for row in projected["events"]
        if row["event_id"] == selected_event_id and row["source_id"] == ref["source_id"]
    ]
    ledger_events = [row for row in report["events"] if row["event_id"] == selected_event_id]
    sources = [row for row in report["sources"] if row["source_id"] == ref["source_id"]]
    if len(ledger_events) != 1 or len(sources) != 1:
        raise RoutingPipelineError("selected provider event/source is absent or ambiguous")
    projected_event = _latest_observation(projected_events, "selected projected event")
    event = ledger_events[0]
    source = sources[0]
    if projected_event["source_url"] not in event["source_urls"]:
        raise RoutingPipelineError("selected provider event source URL drifted")

    jev = _jev_projection(jev_result)
    routes = _route_table(route_map)
    observation = {
        "provider": raw_source.get("provider"),
        "scope": ref["resource_scope"],
        "resource_id": raw_record.get("work_id") or selected_event_id,
        "event_id": selected_event_id,
        "status": provider_status,
        "provider_event_at": event["provider_event_time"],
        "observed_at": event["last_observed_at"],
        "source_url": projected_event["source_url"],
    }
    # Validate provider status/resource syntax even for non-action holds.
    action_loop.reconcile_observations([observation])

    base = {
        "schema": BUNDLE_SCHEMA,
        "connector_projection": projected,
        "connector_projection_sha256": connector_projection.projection_digest(connector_packet),
        "ledger_report": report,
        "selected_record": ref,
        "selected_event_id": selected_event_id,
        "selected_source_status": source["status"],
        "selected_source_freshness": source["freshness"],
        "selected_source_coverage": source["coverage"],
        "observation": observation,
        "jev": {
            "surface": jev["surface"],
            "model": jev["model"],
            "answers": copy.deepcopy(jev["answers"]),
            "answers_sha256": _digest(jev["answers"]),
            "decided_at": jev["decided_at"],
            "error": jev["error"],
            "selected_lane": None,
            "confidence_ppm": None,
        },
        "selected_route": None,
        "plan": None,
        "disposition": None,
        "authority": dict(AUTHORITY),
    }

    if not _source_is_complete(source):
        base["disposition"] = "HOLD_SOURCE_COVERAGE"
    elif jev["error"] is not None:
        base["disposition"] = "HOLD_JEV_ERROR"
    else:
        lane, confidence_ppm = _lane_answer(jev)
        base["jev"]["selected_lane"] = lane
        base["jev"]["confidence_ppm"] = confidence_ppm
        route = routes.get(lane)
        if route is None:
            base["disposition"] = "HOLD_NO_ROUTE"
        else:
            base["selected_route"] = copy.deepcopy(route)
            decision = {
                "model": jev["model"],
                "surface": jev["surface"],
                "selected_action": route["action"],
                "confidence_ppm": confidence_ppm,
                "answers_sha256": base["jev"]["answers_sha256"],
                "decided_at": jev["decided_at"],
            }
            plan = action_loop.compile_action(
                [observation],
                decision,
                {
                    "provider": route["provider"],
                    "destination_id": route["destination_id"],
                    "thread_id": route["thread_id"],
                },
                prior_receipts=prior_receipts,
                min_confidence_ppm=min_confidence_ppm,
            )
            base["plan"] = plan
            base["disposition"] = plan["disposition"]

    bundle = {**base, "bundle_sha256": _digest(base)}
    if not verify_bundle(bundle):
        raise RoutingPipelineError("self-generated routing bundle failed verification")
    return bundle


def verify_bundle(bundle: dict[str, Any]) -> bool:
    """Verify nested projection, ledger, Jev answer, route, and action-plan binding."""
    try:
        if type(bundle) is not dict or bundle.get("schema") != BUNDLE_SCHEMA:
            return False
        if bundle.get("authority") != AUTHORITY:
            return False
        expected = bundle.get("bundle_sha256")
        if type(expected) is not str or HEX64_RE.fullmatch(expected) is None:
            return False
        body = dict(bundle)
        body.pop("bundle_sha256", None)
        if _digest(body) != expected:
            return False

        projected = bundle.get("connector_projection")
        projection_sha = bundle.get("connector_projection_sha256")
        if type(projected) is not dict or type(projection_sha) is not str:
            return False
        if _digest(projected) != projection_sha:
            return False
        if projected.get("schema") != connector_projection.LEDGER_SCHEMA:
            return False

        report = bundle.get("ledger_report")
        if not event_ledger.verify_report(report):
            return False
        event_id = bundle.get("selected_event_id")
        ref = _normalize_ref(bundle.get("selected_record"))
        projected_events = [
            row for row in projected.get("events", [])
            if row.get("event_id") == event_id and row.get("source_id") == ref["source_id"]
        ]
        report_events = [row for row in report.get("events", []) if row.get("event_id") == event_id]
        if len(report_events) != 1:
            return False
        projected_event = _latest_observation(projected_events, "selected projected event")
        event = report_events[0]
        observation = bundle.get("observation")
        if type(observation) is not dict:
            return False
        if (
            observation.get("event_id") != event_id
            or observation.get("provider") != event.get("provider")
            or observation.get("provider_event_at") != event.get("provider_event_time")
            or observation.get("source_url") != projected_event.get("source_url")
            or observation.get("source_url") not in event.get("source_urls", [])
        ):
            return False
        action_loop.reconcile_observations([observation])

        selected_sources = [
            row for row in report.get("sources", [])
            if row.get("source_id") == bundle.get("selected_record", {}).get("source_id")
        ]
        if len(selected_sources) != 1:
            return False
        source = selected_sources[0]
        if (
            source.get("status") != bundle.get("selected_source_status")
            or source.get("freshness") != bundle.get("selected_source_freshness")
            or source.get("coverage") != bundle.get("selected_source_coverage")
        ):
            return False

        jev = bundle.get("jev")
        if type(jev) is not dict or type(jev.get("answers")) is not dict:
            return False
        if _digest(jev["answers"]) != jev.get("answers_sha256"):
            return False

        plan = bundle.get("plan")
        route = bundle.get("selected_route")
        disposition = bundle.get("disposition")
        if not _source_is_complete(source):
            return disposition == "HOLD_SOURCE_COVERAGE" and plan is None and route is None
        if jev.get("error") is not None:
            return disposition == "HOLD_JEV_ERROR" and plan is None and route is None

        lane, confidence_ppm = _lane_answer(jev)
        if lane != jev.get("selected_lane") or confidence_ppm != jev.get("confidence_ppm"):
            return False
        if plan is None:
            return disposition == "HOLD_NO_ROUTE" and route is None
        if type(route) is not dict:
            return False
        if (
            route.get("action") != plan.get("selected_action")
            or route.get("provider") != plan.get("target", {}).get("provider")
            or route.get("destination_id") != plan.get("target", {}).get("destination_id")
            or route.get("thread_id") != plan.get("target", {}).get("thread_id")
            or confidence_ppm != plan.get("confidence_ppm")
        ):
            return False
        decision = {
            "model": jev["model"],
            "surface": jev["surface"],
            "selected_action": plan["selected_action"],
            "confidence_ppm": confidence_ppm,
            "answers_sha256": jev["answers_sha256"],
            "decided_at": jev["decided_at"],
        }
        if _digest(decision) != plan.get("decision_sha256"):
            return False
        action_loop.verify_plan(plan)
        return (
            plan.get("disposition") == disposition
            and plan.get("effective_event_key") is not None
        )
    except (RoutingPipelineError, ValueError, TypeError, KeyError):
        return False


def make_receipt(
    bundle: dict[str, Any],
    *,
    provider_resource_id: str | None,
    provider_observed_operation_id: str | None,
    source_url: str,
    outcome: str,
    attempted_at: str,
    observed_at: str,
) -> dict[str, Any]:
    """Bind an executed action generation to exact installed-connector readback."""
    if not verify_bundle(bundle):
        raise RoutingPipelineError("routing bundle verification failed")
    plan = bundle.get("plan")
    if type(plan) is not dict or plan.get("disposition") not in {"ACTION_READY", "RETRY_SAME_OPERATION_ID"}:
        raise RoutingPipelineError("routing plan is not executable")
    receipt = action_loop.make_readback_receipt(
        plan,
        provider_resource_id=provider_resource_id,
        provider_observed_operation_id=provider_observed_operation_id,
        source_url=source_url,
        outcome=outcome,
        attempted_at=attempted_at,
        observed_at=observed_at,
    )
    action_loop.verify_receipt(receipt)
    return receipt
