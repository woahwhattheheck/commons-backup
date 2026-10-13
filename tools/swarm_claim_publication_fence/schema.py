from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Tuple

SCHEMA_VERSION = 1
MAX_INPUT_BYTES = 1_048_576
ROLES = {
    "SOURCE",
    "REVIEW",
    "FINALIZATION",
    "RESEARCH",
    "COMMERCIALIZATION",
    "PROVIDER",
    "OTHER",
}

_WORK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{2,159}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_CHANNEL_RE = re.compile(r"^[CDG][A-Z0-9]{8,20}$")
_PRINCIPAL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{1,127}$")
_SLACK_TS_RE = re.compile(r"^(0|[1-9][0-9]{0,15})\.([0-9]{6})$")


class ValidationError(ValueError):
    pass


def _obj(value: Any, name: str) -> Dict[str, Any]:
    if type(value) is not dict:
        raise ValidationError(f"{name} must be an object")
    return value


def _list(value: Any, name: str) -> List[Any]:
    if type(value) is not list:
        raise ValidationError(f"{name} must be an array")
    return value


def exact_keys(obj: Dict[str, Any], *, required: Iterable[str], optional: Iterable[str] = (), name: str) -> None:
    required_set = set(required)
    allowed = required_set | set(optional)
    actual = set(obj)
    missing = sorted(required_set - actual)
    unknown = sorted(actual - allowed)
    if missing:
        raise ValidationError(f"{name} missing fields: {', '.join(missing)}")
    if unknown:
        raise ValidationError(f"{name} unknown fields: {', '.join(unknown)}")


def strict_int(value: Any, name: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        raise ValidationError(f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise ValidationError(f"{name} outside [{minimum}, {maximum}]")
    return value


def strict_bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise ValidationError(f"{name} must be a boolean")
    return value


def strict_text(value: Any, name: str, *, pattern: re.Pattern[str], max_len: int = 256) -> str:
    if type(value) is not str or not value or len(value) > max_len or not pattern.fullmatch(value):
        raise ValidationError(f"{name} is malformed")
    return value


def parse_slack_ts(value: Any, name: str) -> Tuple[int, int]:
    if type(value) is not str:
        raise ValidationError(f"{name} must be a Slack timestamp string")
    match = _SLACK_TS_RE.fullmatch(value)
    if not match:
        raise ValidationError(f"{name} is malformed")
    return int(match.group(1)), int(match.group(2))


def slack_ts_datetime(value: Any, name: str) -> datetime:
    seconds, micros = parse_slack_ts(value, name)
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc) + timedelta(microseconds=micros)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValidationError(f"{name} is outside supported epoch range") from exc


def parse_utc(value: Any, name: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise ValidationError(f"{name} must be RFC3339 UTC ending in Z")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValidationError(f"{name} is malformed") from exc
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise ValidationError(f"{name} must be UTC")
    return dt


def validate_identity(obj: Any, name: str) -> Dict[str, str]:
    row = _obj(obj, name)
    exact_keys(row, required=("work_key", "role", "scope_digest_sha256"), name=name)
    work_key = strict_text(row["work_key"], f"{name}.work_key", pattern=_WORK_RE, max_len=160)
    role = row["role"]
    if type(role) is not str or role not in ROLES:
        raise ValidationError(f"{name}.role is unsupported")
    digest = strict_text(row["scope_digest_sha256"], f"{name}.scope_digest_sha256", pattern=_DIGEST_RE, max_len=64)
    return {"work_key": work_key, "role": role, "scope_digest_sha256": digest}


def validate_message_locator(obj: Any, name: str) -> Dict[str, str]:
    row = _obj(obj, name)
    exact_keys(row, required=("channel_id", "message_ts", "author_id", "seat_id"), name=name)
    channel = strict_text(row["channel_id"], f"{name}.channel_id", pattern=_CHANNEL_RE, max_len=22)
    parse_slack_ts(row["message_ts"], f"{name}.message_ts")
    author = strict_text(row["author_id"], f"{name}.author_id", pattern=_PRINCIPAL_RE, max_len=128)
    seat = strict_text(row["seat_id"], f"{name}.seat_id", pattern=_PRINCIPAL_RE, max_len=128)
    return {"channel_id": channel, "message_ts": row["message_ts"], "author_id": author, "seat_id": seat}


def validate_claim(obj: Any, name: str) -> Dict[str, str]:
    row = _obj(obj, name)
    exact_keys(
        row,
        required=("work_key", "role", "scope_digest_sha256", "channel_id", "message_ts", "author_id", "seat_id"),
        name=name,
    )
    identity = validate_identity({k: row[k] for k in ("work_key", "role", "scope_digest_sha256")}, name + ".identity")
    locator = validate_message_locator({k: row[k] for k in ("channel_id", "message_ts", "author_id", "seat_id")}, name + ".locator")
    return {**identity, **locator}


def claim_key(claim: Dict[str, str]) -> Tuple[str, str, str]:
    return claim["work_key"], claim["role"], claim["scope_digest_sha256"]


def message_key(claim: Dict[str, str]) -> Tuple[str, str]:
    return claim["channel_id"], claim["message_ts"]


def validate_snapshot(raw: Any) -> Dict[str, Any]:
    root = _obj(raw, "snapshot")
    exact_keys(
        root,
        required=("schema_version", "issued_at", "max_observation_age_seconds", "identity", "candidate", "history", "search"),
        name="snapshot",
    )
    if strict_int(root["schema_version"], "schema_version", minimum=1, maximum=1) != SCHEMA_VERSION:
        raise ValidationError("unsupported schema_version")
    issued_at_text = root["issued_at"]
    issued_at = parse_utc(issued_at_text, "issued_at")
    max_age = strict_int(root["max_observation_age_seconds"], "max_observation_age_seconds", minimum=1, maximum=86_400)
    identity = validate_identity(root["identity"], "identity")
    candidate_locator = validate_message_locator(root["candidate"], "candidate")
    candidate = {**identity, **candidate_locator}

    history = _obj(root["history"], "history")
    exact_keys(
        history,
        required=("channel_id", "observed_at", "window_start_ts", "window_end_ts", "complete", "claims"),
        name="history",
    )
    history_channel = strict_text(history["channel_id"], "history.channel_id", pattern=_CHANNEL_RE, max_len=22)
    if history_channel != candidate["channel_id"]:
        raise ValidationError("history.channel_id must equal candidate.channel_id")
    history_observed_text = history["observed_at"]
    history_observed = parse_utc(history_observed_text, "history.observed_at")
    start_key = parse_slack_ts(history["window_start_ts"], "history.window_start_ts")
    end_key = parse_slack_ts(history["window_end_ts"], "history.window_end_ts")
    if start_key > end_key:
        raise ValidationError("history window is inverted")
    candidate_ts_key = parse_slack_ts(candidate["message_ts"], "candidate.message_ts")
    candidate_dt = slack_ts_datetime(candidate["message_ts"], "candidate.message_ts")
    if candidate_dt > issued_at:
        raise ValidationError("candidate.message_ts is in the future relative to issued_at")
    if issued_at - candidate_dt > timedelta(seconds=max_age):
        raise ValidationError("candidate.message_ts is stale")
    if candidate_ts_key < start_key or candidate_ts_key > end_key:
        raise ValidationError("candidate.message_ts is outside history window")
    history_complete = strict_bool(history["complete"], "history.complete")
    history_claims = [validate_claim(row, f"history.claims[{idx}]") for idx, row in enumerate(_list(history["claims"], "history.claims"))]

    search = _obj(root["search"], "search")
    exact_keys(search, required=("observed_at", "matches"), name="search")
    search_observed_text = search["observed_at"]
    search_observed = parse_utc(search_observed_text, "search.observed_at")
    search_matches = [validate_claim(row, f"search.matches[{idx}]") for idx, row in enumerate(_list(search["matches"], "search.matches"))]

    for name, observed in (("history.observed_at", history_observed), ("search.observed_at", search_observed)):
        if observed > issued_at:
            raise ValidationError(f"{name} is in the future relative to issued_at")
        if issued_at - observed > timedelta(seconds=max_age):
            raise ValidationError(f"{name} is stale")

    seen_messages: Dict[Tuple[str, str], Dict[str, str]] = {}
    for idx, claim in enumerate(history_claims):
        if claim["channel_id"] != history_channel:
            raise ValidationError(f"history.claims[{idx}].channel_id outside history channel")
        ts_key = parse_slack_ts(claim["message_ts"], f"history.claims[{idx}].message_ts")
        claim_dt = slack_ts_datetime(claim["message_ts"], f"history.claims[{idx}].message_ts")
        if claim_dt > history_observed:
            raise ValidationError(f"history.claims[{idx}] is later than history.observed_at")
        if ts_key < start_key or ts_key > end_key:
            raise ValidationError(f"history.claims[{idx}] outside history window")
        key = message_key(claim)
        if key in seen_messages:
            raise ValidationError("duplicate/transplanted message identity in history")
        seen_messages[key] = claim

    target_key = claim_key(candidate)
    seen_search = set()
    for idx, claim in enumerate(search_matches):
        if claim_key(claim) != target_key:
            raise ValidationError(f"search.matches[{idx}] is not the exact requested work identity")
        if claim["channel_id"] != history_channel:
            raise ValidationError(f"search.matches[{idx}].channel_id outside history channel")
        if slack_ts_datetime(claim["message_ts"], f"search.matches[{idx}].message_ts") > search_observed:
            raise ValidationError(f"search.matches[{idx}] is later than search.observed_at")
        key = message_key(claim)
        if key in seen_search:
            raise ValidationError("duplicate message identity in search matches")
        seen_search.add(key)

    return {
        "schema_version": SCHEMA_VERSION,
        "issued_at": issued_at_text,
        "max_observation_age_seconds": max_age,
        "identity": identity,
        "candidate": candidate_locator,
        "history": {
            "channel_id": history_channel,
            "observed_at": history_observed_text,
            "window_start_ts": history["window_start_ts"],
            "window_end_ts": history["window_end_ts"],
            "complete": history_complete,
            "claims": history_claims,
        },
        "search": {"observed_at": search_observed_text, "matches": search_matches},
    }
