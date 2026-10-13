#!/usr/bin/env python3
"""Compile one Resource Master sweep into a deterministic incremental report.

The report is advisory routing metadata.  It does not authenticate, authorize,
admit, reserve, contact, deploy, or spend.  Every source supplies its own exact
watermark so a future sweep can distinguish new work from repeated history.
Slack events at or before their channel's previous cursor remain visible as
previously observed evidence; only events in (previous, current] count as new.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OBSERVATION_SCHEMA = "commons-resource-master-delta-observations/v1"
REPORT_SCHEMA = "commons-resource-master-delta-report/v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SLACK_TS_RE = re.compile(r"^[0-9]{10}\.[0-9]{6}$")
ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,100}$")
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:password|passwd|api[_ -]?key|client[_ -]?secret)\s*[:=]\s*\S+"),
    re.compile(r"\b(?:ghp|github_pat|sk_live|sk_test|xox[baprs])-[-A-Za-z0-9_]{8,}\b"),
    re.compile(r"(?i)[?&](?:token|code|secret|key|signature)=[^&\s]+"),
)


class ResourceDeltaError(ValueError):
    """A sweep violates the deterministic or public-safe delta contract."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ResourceDeltaError("watermark timestamps must be UTC Z timestamps")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ResourceDeltaError("invalid UTC watermark timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise ResourceDeltaError("watermark timestamp is not UTC")
    return parsed


def _scan_secrets(value: Any) -> None:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True)
    for pattern in SECRET_PATTERNS:
        if pattern.search(blob):
            raise ResourceDeltaError("secret-shaped value found in public delta evidence")


def _require_unique(rows: list[dict[str, Any]], field: str, label: str) -> None:
    values = [row.get(field) for row in rows]
    if any(not isinstance(value, str) or not value for value in values):
        raise ResourceDeltaError(f"{label} rows require nonempty {field}")
    if len(values) != len(set(values)):
        raise ResourceDeltaError(f"duplicate {label} {field}")


def validate_observations(data: dict[str, Any]) -> None:
    if not isinstance(data, dict) or data.get("schema") != OBSERVATION_SCHEMA:
        raise ResourceDeltaError("wrong observation schema")
    previous = data.get("previous_watermark")
    current = data.get("current_watermark")
    if not isinstance(previous, dict) or not isinstance(current, dict):
        raise ResourceDeltaError("previous and current watermarks are required")
    if _parse_utc(current.get("observed_at")) <= _parse_utc(previous.get("observed_at")):
        raise ResourceDeltaError("current watermark must advance observed_at")
    for watermark in (previous, current):
        if not SHA_RE.fullmatch(str(watermark.get("main_sha", ""))):
            raise ResourceDeltaError("watermark main_sha must be an exact commit SHA")
        channels = watermark.get("slack_channels")
        if not isinstance(channels, dict) or not channels:
            raise ResourceDeltaError("each watermark requires Slack channel cursors")
        for channel, value in channels.items():
            if not isinstance(channel, str) or not isinstance(value, str) or not SLACK_TS_RE.fullmatch(value):
                raise ResourceDeltaError("Slack cursors must use exact native timestamps")

    previous_channels = previous["slack_channels"]
    current_channels = current["slack_channels"]
    for channel, cursor in previous_channels.items():
        if channel not in current_channels:
            raise ResourceDeltaError("current watermark is missing a previous Slack channel")
        if current_channels[channel] < cursor:
            raise ResourceDeltaError("Slack channel cursor must not regress")

    comparison = data.get("github_comparison")
    if not isinstance(comparison, dict):
        raise ResourceDeltaError("github_comparison is required")
    if comparison.get("base_sha") != previous["main_sha"]:
        raise ResourceDeltaError("comparison base does not match previous main")
    if comparison.get("head_sha") != current["main_sha"]:
        raise ResourceDeltaError("comparison head does not match current main")
    changed = comparison.get("changed_paths")
    if not isinstance(changed, list):
        raise ResourceDeltaError("changed_paths must be a list")
    _require_unique(changed, "path", "changed path")
    for row in changed:
        if row.get("class") not in {"MATERIAL", "PROJECTION_ONLY"}:
            raise ResourceDeltaError("changed path class must be explicit")

    pull_requests = data.get("new_pull_requests")
    if not isinstance(pull_requests, list):
        raise ResourceDeltaError("new_pull_requests must be a list")
    numbers = [row.get("number") for row in pull_requests]
    if len(numbers) != len(set(numbers)) or any(not isinstance(n, int) or n < 1 for n in numbers):
        raise ResourceDeltaError("pull request numbers must be unique positive integers")
    for row in pull_requests:
        if not SHA_RE.fullmatch(str(row.get("head_sha", ""))):
            raise ResourceDeltaError("pull request head must be exact")

    slack_events = data.get("new_slack_events")
    if not isinstance(slack_events, list):
        raise ResourceDeltaError("new_slack_events must be a list")
    _require_unique(slack_events, "source_id", "Slack event")
    for row in slack_events:
        native_ts = row.get("native_ts")
        if not isinstance(native_ts, str) or not SLACK_TS_RE.fullmatch(native_ts):
            raise ResourceDeltaError("Slack event requires exact native_ts")
        channel = row.get("channel")
        if not isinstance(channel, str) or channel not in previous_channels or channel not in current_channels:
            raise ResourceDeltaError("Slack event channel requires previous and current cursors")
        if native_ts > current_channels[channel]:
            raise ResourceDeltaError("Slack event is beyond its current channel cursor")

    orders = data.get("routed_build_orders")
    if not isinstance(orders, list):
        raise ResourceDeltaError("routed_build_orders must be a list")
    _require_unique(orders, "id", "build order")
    seen = set(data.get("previously_routed_order_ids") or [])
    for order in orders:
        if not ID_RE.fullmatch(order["id"]):
            raise ResourceDeltaError("build order id is not canonical-safe")
        if order["id"] in seen:
            raise ResourceDeltaError("build order duplicates a previous routed order")
        if order.get("state") != "ROUTED":
            raise ResourceDeltaError("this report records only actually routed orders")
        if not SLACK_TS_RE.fullmatch(str(order.get("slack_ts", ""))):
            raise ResourceDeltaError("routed build order requires Slack receipt")

    gmail = data.get("gmail_delta")
    if not isinstance(gmail, dict) or not isinstance(gmail.get("new_receipts"), int):
        raise ResourceDeltaError("gmail_delta requires an integer receipt count")
    if gmail.get("private_content_persisted") is not False:
        raise ResourceDeltaError("private mail content may not enter the public report")
    _scan_secrets(data)


def compile_report(data: dict[str, Any]) -> dict[str, Any]:
    validate_observations(data)
    comparison = copy.deepcopy(data["github_comparison"])
    material = sorted(row["path"] for row in comparison["changed_paths"] if row["class"] == "MATERIAL")
    projection = sorted(row["path"] for row in comparison["changed_paths"] if row["class"] == "PROJECTION_ONLY")
    pull_requests = sorted(copy.deepcopy(data["new_pull_requests"]), key=lambda row: row["number"])
    observed_events = sorted(copy.deepcopy(data["new_slack_events"]), key=lambda row: (row["native_ts"], row["source_id"]))
    previous_channels = data["previous_watermark"]["slack_channels"]
    events = [row for row in observed_events if row["native_ts"] > previous_channels[row["channel"]]]
    previously_observed = [row for row in observed_events if row["native_ts"] <= previous_channels[row["channel"]]]
    orders = sorted(copy.deepcopy(data["routed_build_orders"]), key=lambda row: row["id"])
    report = {
        "schema": REPORT_SCHEMA,
        "policy": {
            "metadata_only": True,
            "admission_gate": False,
            "authentication_gate": False,
            "spend_authority": False,
            "external_contact_authority": False,
            "private_content_persisted": False,
        },
        "previous_watermark": copy.deepcopy(data["previous_watermark"]),
        "next_watermark": copy.deepcopy(data["current_watermark"]),
        "summary": {
            "main_advanced": comparison["base_sha"] != comparison["head_sha"],
            "commits_ahead": comparison["ahead_by"],
            "material_changed_paths": len(material),
            "projection_only_paths": len(projection),
            "new_open_pull_requests": len(pull_requests),
            "new_slack_events": len(events),
            "previously_observed_slack_events": len(previously_observed),
            "new_business_gmail_receipts": data["gmail_delta"]["new_receipts"],
            "automation_state_changes": len(data.get("automation_state_changes") or []),
            "plugin_route_changes": len(data.get("plugin_route_changes") or []),
            "routed_build_orders": len(orders),
        },
        "github": {
            "base_sha": comparison["base_sha"],
            "head_sha": comparison["head_sha"],
            "material_paths": material,
            "projection_only_paths": projection,
            "new_pull_requests": pull_requests,
        },
        "slack": {
            "events": events,
            "previously_observed_events": previously_observed,
            "routed_build_orders": orders,
        },
        "connected_state": {
            "gmail_delta": copy.deepcopy(data["gmail_delta"]),
            "automation_state_changes": sorted(copy.deepcopy(data.get("automation_state_changes") or []), key=lambda row: row["id"]),
            "plugin_route_changes": sorted(copy.deepcopy(data.get("plugin_route_changes") or []), key=lambda row: row["id"]),
        },
        "ignored_as_not_new_capacity": sorted(copy.deepcopy(data.get("ignored_as_not_new_capacity") or []), key=lambda row: row["id"]),
        "evidence": copy.deepcopy(data.get("evidence") or {}),
        "non_claims": list(data.get("non_claims") or []),
    }
    _scan_secrets(report)
    return report


def self_test() -> dict[str, Any]:
    base = "1" * 40
    head = "2" * 40
    sample = {
        "schema": OBSERVATION_SCHEMA,
        "previous_watermark": {"observed_at": "2026-09-01T00:00:00Z", "main_sha": base, "slack_channels": {"commons": "1788210000.000000"}},
        "current_watermark": {"observed_at": "2026-09-01T01:00:00Z", "main_sha": head, "slack_channels": {"commons": "1788213600.000000"}},
        "github_comparison": {"base_sha": base, "head_sha": head, "ahead_by": 1, "changed_paths": [{"path": "head.json", "class": "PROJECTION_ONLY"}]},
        "new_pull_requests": [{"number": 1, "title": "one", "head_sha": "3" * 40, "state": "OPEN"}],
        "new_slack_events": [{"source_id": "slack:commons:1788213600.000000", "native_ts": "1788213600.000000", "channel": "commons", "kind": "CLAIM"}],
        "gmail_delta": {"new_receipts": 0, "private_content_persisted": False},
        "automation_state_changes": [],
        "plugin_route_changes": [],
        "previously_routed_order_ids": [],
        "routed_build_orders": [{"id": "sample-order-01", "state": "ROUTED", "slack_ts": "1788213600.000000", "consumer": "test"}],
        "ignored_as_not_new_capacity": [],
    }
    first = compile_report(sample)
    second = compile_report(copy.deepcopy(sample))
    return {
        "ok": first == second
        and first["summary"]["material_changed_paths"] == 0
        and first["summary"]["projection_only_paths"] == 1
        and first["summary"]["routed_build_orders"] == 1
        and first["policy"]["admission_gate"] is False,
        "summary": first["summary"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile an incremental Resource Master report")
    parser.add_argument("--input", default="inventory/resources/resource_master_delta_observations.json")
    parser.add_argument("--output", default="inventory/resources/resource_master_delta_report.json")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        result = self_test()
        print(canonical_json(result), end="")
        return 0 if result["ok"] else 1
    source = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rendered = canonical_json(compile_report(source))
    output = Path(args.output)
    if args.verify:
        if not output.is_file() or output.read_text(encoding="utf-8") != rendered:
            print("MISMATCH")
            return 1
        print("MATCH")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(f"WROTE {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
