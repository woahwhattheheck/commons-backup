#!/usr/bin/env python3
"""Strict offline validator for the OSS sponsor-route research map."""

from __future__ import annotations
import argparse, json, re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "oss-sponsor-route-map/v1"
OPERATION = "OSS-SPONSOR-ROUTE-EVIDENCE-MAP-20260916"
REWARDS = {"GUARANTEED", "ADVERTISED", "SUBJECTIVE", "UNKNOWN"}
CURRENT = {"OPEN", "ROLLING", "ACTIVE_MECHANISM"}
SOURCE_AUTHORITIES = {"FIRST_PARTY", "PROGRAM_AUTHORITY"}
CASH_KINDS = {"CASH", "NONCASH", "FUNDRAISING", "EQUITY", "UNKNOWN"}
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class ValidationError(ValueError):
    pass


def _strict_json(raw: bytes) -> Any:
    if len(raw) > 2_000_000:
        raise ValidationError("map is too large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("map must be UTF-8") from exc

    def hook(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValidationError(f"duplicate JSON key: {key!r}")
            out[key] = value
        return out

    try:
        return json.loads(
            text,
            object_pairs_hook=hook,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValidationError(f"non-finite JSON constant: {token}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON: {exc}") from exc


def load_map(path: str | Path) -> dict[str, Any]:
    value = _strict_json(Path(path).read_bytes())
    if type(value) is not dict:
        raise ValidationError("root must be an object")
    return value


def _obj(value, required, where):
    if type(value) is not dict:
        raise ValidationError(f"{where} must be an object")
    keys = set(value)
    missing = required - keys
    extra = keys - required
    if missing:
        raise ValidationError(f"{where} missing fields: {sorted(missing)}")
    if extra:
        raise ValidationError(f"{where} unsupported fields: {sorted(extra)}")
    return value


def _text(value, where):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValidationError(f"{where} must be a trimmed non-empty string")
    return value


def _url(value, where):
    text = _text(value, where)
    if not text.startswith("https://") or any(ch.isspace() for ch in text):
        raise ValidationError(f"{where} must be an https URL")
    return text


def _utc(value, where):
    text = _text(value, where)
    if UTC_RE.fullmatch(text) is None:
        raise ValidationError(f"{where} must be exact UTC seconds")
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValidationError(f"{where} invalid timestamp") from exc


def validate_map(data: dict[str, Any]) -> dict[str, Any]:
    root = _obj(
        data,
        {
            "schema", "operation", "generated_at_utc", "as_of_date",
            "authority_profiles", "fence_profiles", "reward_state_definitions",
            "action_profiles", "gate_profiles", "proof_catalog",
            "sources", "opportunities", "summary",
        },
        "root",
    )
    if root["schema"] != SCHEMA:
        raise ValidationError(f"schema must be {SCHEMA}")
    if root["operation"] != OPERATION:
        raise ValidationError(f"operation must be {OPERATION}")
    generated = _utc(root["generated_at_utc"], "generated_at_utc")
    if not isinstance(root["as_of_date"], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", root["as_of_date"]):
        raise ValidationError("as_of_date must be YYYY-MM-DD")

    authority_profiles = root["authority_profiles"]
    if type(authority_profiles) is not dict or "RESEARCH_ONLY_V1" not in authority_profiles:
        raise ValidationError("RESEARCH_ONLY_V1 authority profile required")
    for profile_id, profile in authority_profiles.items():
        item = _obj(
            profile,
            {
                "external_action_authorized", "submission_authorized",
                "cash_or_revenue_claimed", "vulnerability_exploitation_authorized",
            },
            f"authority profile {profile_id}",
        )
        if any(value is not False for value in item.values()):
            raise ValidationError(f"authority profile {profile_id} may not authorize side effects")

    fences = root["fence_profiles"]
    if fences != {"RECENSUS_V1": "RECENSUS_REQUIRED_BEFORE_IMPLEMENTATION_OR_EXTERNAL_ACTION"}:
        raise ValidationError("exact RECENSUS_V1 fence required")

    definitions = root["reward_state_definitions"]
    if type(definitions) is not dict or set(definitions) != REWARDS:
        raise ValidationError("reward_state_definitions must define exact enum")
    for key, value in definitions.items():
        _text(value, f"reward definition {key}")

    actions = root["action_profiles"]
    gates = root["gate_profiles"]
    if type(actions) is not dict or not actions or type(gates) is not dict or not gates:
        raise ValidationError("action_profiles and gate_profiles must be non-empty")
    for group, label in ((actions, "action"), (gates, "gate")):
        for key, value in group.items():
            _text(key, f"{label} profile id")
            _text(value, f"{label} profile {key}")

    proofs = root["proof_catalog"]
    if type(proofs) is not dict or not proofs:
        raise ValidationError("proof_catalog must be non-empty")
    for key, value in proofs.items():
        proof = _obj(value, {"label", "url", "fit"}, f"proof {key}")
        _text(proof["label"], f"proof {key}.label")
        _url(proof["url"], f"proof {key}.url")
        if type(proof["fit"]) is not list or not proof["fit"]:
            raise ValidationError(f"proof {key}.fit must be non-empty")

    sources = root["sources"]
    if type(sources) is not list or not sources:
        raise ValidationError("sources must be non-empty")
    source_ids, source_urls = set(), set()
    for index, raw in enumerate(sources):
        src = _obj(raw, {"id", "url", "authority", "observed_at_utc", "currentness_fact"}, f"sources[{index}]")
        sid = _text(src["id"], f"sources[{index}].id")
        if sid in source_ids:
            raise ValidationError(f"duplicate source id: {sid}")
        source_ids.add(sid)
        url = _url(src["url"], f"source {sid}.url")
        if url in source_urls:
            raise ValidationError(f"duplicate source URL: {url}")
        source_urls.add(url)
        if src["authority"] not in SOURCE_AUTHORITIES:
            raise ValidationError(f"source {sid}: invalid authority")
        if _utc(src["observed_at_utc"], f"source {sid}.observed_at_utc") > generated:
            raise ValidationError(f"source {sid}: observed after generation")
        _text(src["currentness_fact"], f"source {sid}.currentness_fact")

    opportunities = root["opportunities"]
    if type(opportunities) is not list or not 20 <= len(opportunities) <= 30:
        raise ValidationError("opportunities must contain 20..30 rows")
    opp_ids = set()
    for index, raw in enumerate(opportunities):
        opp = _obj(
            raw,
            {
                "id", "name", "source", "route", "reward", "current", "priority",
                "fit", "action", "gate", "econ", "proof", "fence", "authority",
            },
            f"opportunities[{index}]",
        )
        oid = _text(opp["id"], f"opportunities[{index}].id")
        if oid in opp_ids:
            raise ValidationError(f"duplicate opportunity id: {oid}")
        opp_ids.add(oid)
        _text(opp["name"], f"{oid}.name")
        if opp["source"] not in source_ids:
            raise ValidationError(f"{oid}: unknown source")
        _text(opp["route"], f"{oid}.route")
        if opp["reward"] not in REWARDS:
            raise ValidationError(f"{oid}: invalid reward")
        if opp["reward"] == "GUARANTEED":
            raise ValidationError(f"{oid}: pre-award map may not assert GUARANTEED")
        if opp["current"] not in CURRENT:
            raise ValidationError(f"{oid}: invalid current state")
        if type(opp["priority"]) is not int or isinstance(opp["priority"], bool) or not 1 <= opp["priority"] <= 5:
            raise ValidationError(f"{oid}: priority must be integer 1..5")
        if type(opp["fit"]) is not list or not opp["fit"] or any(not isinstance(x, str) or not x for x in opp["fit"]):
            raise ValidationError(f"{oid}: fit must be non-empty string list")
        if opp["action"] not in actions or opp["gate"] not in gates:
            raise ValidationError(f"{oid}: unknown action/gate profile")
        if opp["proof"] not in proofs:
            raise ValidationError(f"{oid}: unknown proof")
        if opp["fence"] != "RECENSUS_V1" or opp["authority"] != "RESEARCH_ONLY_V1":
            raise ValidationError(f"{oid}: wrong fence/authority profile")

        econ = _obj(opp["econ"], {"cash_kind", "advertised_value"}, f"{oid}.econ")
        if econ["cash_kind"] not in CASH_KINDS:
            raise ValidationError(f"{oid}: invalid cash_kind")
        if opp["reward"] == "ADVERTISED":
            _text(econ["advertised_value"], f"{oid}.advertised_value")
        elif econ["advertised_value"] is not None:
            raise ValidationError(f"{oid}: non-ADVERTISED row cannot assert value")

    expected = {
        "opportunity_count": len(opportunities),
        "source_count": len(sources),
        "priority_counts": {str(k): v for k, v in sorted(Counter(x["priority"] for x in opportunities).items())},
        "reward_state_counts": dict(sorted(Counter(x["reward"] for x in opportunities).items())),
        "route_type_counts": dict(sorted(Counter(x["route"] for x in opportunities).items())),
    }
    if root["summary"] != expected:
        raise ValidationError("summary does not match map")
    return expected


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("map_path", nargs="?", default="research/oss_sponsor_route_map/route_map.json")
    args = parser.parse_args(argv)
    try:
        summary = validate_map(load_map(args.map_path))
    except (OSError, ValidationError) as exc:
        parser.error(str(exc))
    print(
        f"VALID opportunities={summary['opportunity_count']} "
        f"sources={summary['source_count']} reward_states={summary['reward_state_counts']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
