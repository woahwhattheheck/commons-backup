"""Read-only Google Calendar adapter for landed sales-meeting readiness.

Current READY is available only through an independent host authority store and
verifier-owned current UTC.  Direct historical bytes are permanently
non-authorizing.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any, Iterable, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from revenue.sales_meeting_readiness.meeting_readiness import (
    SCHEMA as CORE_SCHEMA,
    READY as CORE_READY,
    busy_digest as core_busy_digest,
    compile_meeting_readiness,
    render_markdown as render_core_markdown,
    request_digest as core_request_digest,
)

TRIGGER_SCHEMA = "sales-meeting-calendar-trigger/v1"
HUMAN_AUTHORITY_SCHEMA = "verified-human-meeting-request/v1"
PLAN_SCHEMA = "google-calendar-freebusy-plan/v1"
CAPTURE_SCHEMA = "google-calendar-freebusy-capture/v1"
RECEIPT_SCHEMA = "sales-meeting-calendar-consumer-receipt/v2"
CURRENT_MODE = "CURRENT"
HISTORICAL_MODE = "HISTORICAL_REPLAY"
HISTORICAL_REPLAY = "HISTORICAL_REPLAY_ONLY"
PROVIDER_REF = "google-calendar:get_availability/v1"
CALENDAR_ID = "primary"

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?1[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}(?!\d)")
_SECRET = re.compile(r"(?i)\b(?:sk_live_|ghp_|github_pat_|AIza|xox[baprs]-)[A-Za-z0-9_\-]{8,}")
_PREP_SCALARS = ("objective", "recommended_opening", "recommended_closing")
_PREP_LISTS = ("key_questions", "likely_asks", "risks_commitments_to_avoid", "owner_actions")


class CalendarConsumerError(ValueError):
    pass


class CurrentAuthorityStore(Protocol):
    """Trusted-host lookups; no JSON/file implementation is supplied here."""
    def get_human_authority(self, authority_ref: str) -> Any: ...
    def get_calendar_capture(self, capture_ref: str) -> Any: ...


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def strict_json_loads(data: str | bytes) -> Any:
    def pairs(items: Iterable[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise CalendarConsumerError(f"duplicate JSON key: {key}")
            out[key] = value
        return out
    try:
        return json.loads(data, object_pairs_hook=pairs)
    except CalendarConsumerError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CalendarConsumerError(f"invalid JSON: {exc}") from exc


def _obj(value: Any, keys: set[str], *, where: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise CalendarConsumerError(f"{where} keys invalid")
    return value


def _s(value: Any, *, where: str, maximum: int = 256) -> str:
    if type(value) is not str or not value or len(value) > maximum or "\x00" in value:
        raise CalendarConsumerError(f"{where} invalid string")
    return value


def _id(value: Any, *, where: str) -> str:
    text = _s(value, where=where, maximum=128)
    if not _ID.fullmatch(text) or _EMAIL.search(text) or _PHONE.search(text) or _SECRET.search(text):
        raise CalendarConsumerError(f"{where} must be a safe opaque identifier")
    return text


def _sha(value: Any, *, where: str) -> str:
    text = _s(value, where=where, maximum=64)
    if not _SHA.fullmatch(text):
        raise CalendarConsumerError(f"{where} must be lowercase SHA-256")
    return text


def _dt(value: Any, *, where: str) -> datetime:
    text = _s(value, where=where, maximum=40)
    try:
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CalendarConsumerError(f"{where} must be RFC3339") from exc
    if result.tzinfo is None:
        raise CalendarConsumerError(f"{where} must include timezone")
    return result.astimezone(timezone.utc)


def _utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise CalendarConsumerError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tz(value: Any, *, where: str) -> str:
    name = _s(value, where=where, maximum=64)
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise CalendarConsumerError(f"{where} is not an IANA timezone") from exc
    return name


def _interval(value: Any, *, where: str) -> dict[str, str]:
    raw = _obj(value, {"start", "end"}, where=where)
    start, end = _dt(raw["start"], where=f"{where}.start"), _dt(raw["end"], where=f"{where}.end")
    if end <= start:
        raise CalendarConsumerError(f"{where} end must be after start")
    return {"start": _utc(start), "end": _utc(end)}


def _intervals(value: Any, *, where: str, maximum: int, allow_empty: bool = False) -> list[dict[str, str]]:
    if type(value) is not list or len(value) > maximum or (not allow_empty and not value):
        raise CalendarConsumerError(f"{where} must be a bounded list")
    out = [_interval(item, where=f"{where}[{i}]") for i, item in enumerate(value)]
    keys = [(item["start"], item["end"]) for item in out]
    if len(set(keys)) != len(keys):
        raise CalendarConsumerError(f"{where} contains duplicate interval")
    return sorted(out, key=lambda x: (x["start"], x["end"]))


def _private(value: Any, *, where: str) -> str:
    text = _s(value, where=where, maximum=2400)
    if _EMAIL.search(text) or _PHONE.search(text) or _SECRET.search(text):
        raise CalendarConsumerError(f"{where} contains disallowed direct contact/secret material")
    return text


def _prep(value: Any) -> dict[str, Any]:
    keys = {"context", *_PREP_SCALARS, *_PREP_LISTS}
    raw = _obj(value, keys, where="trigger.prep")
    context = raw["context"]
    if type(context) is not list or not context or len(context) > 16:
        raise CalendarConsumerError("trigger.prep.context must be nonempty bounded list")
    ctx = []
    for i, item in enumerate(context):
        fact = _obj(item, {"text", "source_ref"}, where=f"trigger.prep.context[{i}]")
        ctx.append({"text": _private(fact["text"], where=f"context[{i}].text"),
                    "source_ref": _id(fact["source_ref"], where=f"context[{i}].source_ref")})
    out: dict[str, Any] = {"context": sorted(ctx, key=lambda x: (x["source_ref"], x["text"]))}
    for key in _PREP_SCALARS:
        out[key] = _private(raw[key], where=f"trigger.prep.{key}")
    for key in _PREP_LISTS:
        items = raw[key]
        if type(items) is not list or not items or len(items) > 16:
            raise CalendarConsumerError(f"trigger.prep.{key} must be nonempty bounded list")
        normalized = [_private(item, where=f"trigger.prep.{key}[{i}]") for i, item in enumerate(items)]
        if len(set(normalized)) != len(normalized):
            raise CalendarConsumerError(f"trigger.prep.{key} contains duplicates")
        out[key] = normalized
    return out


def _trigger(value: Any) -> dict[str, Any]:
    keys = {"schema", "opportunity_id", "owner_ref", "counterparty_ref", "thread_ref",
            "human_authority_ref", "inbound", "request", "prep"}
    raw = _obj(value, keys, where="trigger")
    if raw["schema"] != TRIGGER_SCHEMA:
        raise CalendarConsumerError("unsupported trigger schema")
    inbound = _obj(raw["inbound"], {"observation_id", "content_sha256", "received_at"}, where="trigger.inbound")
    request = _obj(raw["request"], {"duration_minutes", "timezone", "windows"}, where="trigger.request")
    if type(request["duration_minutes"]) is not int or not 5 <= request["duration_minutes"] <= 240:
        raise CalendarConsumerError("trigger.request.duration_minutes outside bounds")
    windows = _intervals(request["windows"], where="trigger.request.windows", maximum=16)
    duration = timedelta(minutes=request["duration_minutes"])
    for i, item in enumerate(windows):
        if _dt(item["end"], where="window.end") - _dt(item["start"], where="window.start") < duration:
            raise CalendarConsumerError(f"trigger.request.windows[{i}] is shorter than requested duration")
    return {
        "schema": TRIGGER_SCHEMA,
        "opportunity_id": _id(raw["opportunity_id"], where="trigger.opportunity_id"),
        "owner_ref": _id(raw["owner_ref"], where="trigger.owner_ref"),
        "counterparty_ref": _id(raw["counterparty_ref"], where="trigger.counterparty_ref"),
        "thread_ref": _id(raw["thread_ref"], where="trigger.thread_ref"),
        "human_authority_ref": _id(raw["human_authority_ref"], where="trigger.human_authority_ref"),
        "inbound": {"observation_id": _id(inbound["observation_id"], where="trigger.inbound.observation_id"),
                    "content_sha256": _sha(inbound["content_sha256"], where="trigger.inbound.content_sha256"),
                    "received_at": _utc(_dt(inbound["received_at"], where="trigger.inbound.received_at"))},
        "request": {"duration_minutes": request["duration_minutes"],
                    "timezone": _tz(request["timezone"], where="trigger.request.timezone"), "windows": windows},
        "prep": _prep(raw["prep"]),
    }


def _human(value: Any, trigger: dict[str, Any]) -> dict[str, Any]:
    keys = {"schema", "authority_id", "provider_ref", "event_id", "event_sha256", "observed_at",
            "opportunity_id", "thread_ref", "classification", "verified_human", "meeting_requested"}
    raw = _obj(value, keys, where="human_authority")
    if raw["schema"] != HUMAN_AUTHORITY_SCHEMA or raw["classification"] != "MEETING_REQUEST" \
            or raw["verified_human"] is not True or raw["meeting_requested"] is not True:
        raise CalendarConsumerError("retained authority is not verified human meeting intent")
    out = {"schema": HUMAN_AUTHORITY_SCHEMA,
           "authority_id": _id(raw["authority_id"], where="human_authority.authority_id"),
           "provider_ref": _id(raw["provider_ref"], where="human_authority.provider_ref"),
           "event_id": _id(raw["event_id"], where="human_authority.event_id"),
           "event_sha256": _sha(raw["event_sha256"], where="human_authority.event_sha256"),
           "observed_at": _utc(_dt(raw["observed_at"], where="human_authority.observed_at")),
           "opportunity_id": _id(raw["opportunity_id"], where="human_authority.opportunity_id"),
           "thread_ref": _id(raw["thread_ref"], where="human_authority.thread_ref"),
           "classification": "MEETING_REQUEST", "verified_human": True, "meeting_requested": True}
    bindings = ((out["authority_id"], trigger["human_authority_ref"], "authority ref"),
                (out["event_id"], trigger["inbound"]["observation_id"], "event id"),
                (out["event_sha256"], trigger["inbound"]["content_sha256"], "event digest"),
                (out["observed_at"], trigger["inbound"]["received_at"], "event time"),
                (out["opportunity_id"], trigger["opportunity_id"], "opportunity"),
                (out["thread_ref"], trigger["thread_ref"], "thread"))
    for left, right, label in bindings:
        if left != right:
            raise CalendarConsumerError(f"human authority {label} binding mismatch")
    return out


def _lookup(store: Any, method: str, ref: str, *, where: str) -> Any:
    if store is None or type(store) is dict or not callable(getattr(store, method, None)):
        raise CalendarConsumerError(f"{where} requires an independent authority-store object")
    try:
        value = getattr(store, method)(ref)
    except (KeyError, LookupError) as exc:
        raise CalendarConsumerError(f"{where} retained authority is missing") from exc
    if value is None:
        raise CalendarConsumerError(f"{where} retained authority is missing")
    return deepcopy(value)


def _plan(trigger: dict[str, Any], human: dict[str, Any]) -> dict[str, Any]:
    human_sha = sha256_hex(canonical_json_bytes(human))
    windows = trigger["request"]["windows"]
    core = {"schema": PLAN_SCHEMA, "provider_ref": PROVIDER_REF, "calendar_id": CALENDAR_ID,
            "owner_ref": trigger["owner_ref"],
            "time_min": min(w["start"] for w in windows), "time_max": max(w["end"] for w in windows),
            "response_timezone_str": trigger["request"]["timezone"],
            "request_digest": core_request_digest(trigger["opportunity_id"], trigger["thread_ref"], trigger["request"]),
            "human_authority_sha256": human_sha}
    return {**core, "plan_sha256": sha256_hex(canonical_json_bytes(core))}


def build_google_availability_plan(trigger: Any, *, authority_store: CurrentAuthorityStore) -> dict[str, Any]:
    t = _trigger(trigger)
    human = _human(_lookup(authority_store, "get_human_authority", t["human_authority_ref"], where="current human authority"), t)
    return _plan(t, human)


def build_google_availability_plan_historical(trigger: Any, human_authority: Any) -> dict[str, Any]:
    t = _trigger(trigger)
    return _plan(t, _human(human_authority, t))


def _normalize_plan(value: Any) -> dict[str, Any]:
    keys = {"schema", "provider_ref", "calendar_id", "owner_ref", "time_min", "time_max", "response_timezone_str",
            "request_digest", "human_authority_sha256", "plan_sha256"}
    raw = _obj(value, keys, where="plan")
    if raw["schema"] != PLAN_SCHEMA or raw["provider_ref"] != PROVIDER_REF or raw["calendar_id"] != CALENDAR_ID:
        raise CalendarConsumerError("plan provider/schema/calendar mismatch")
    core = {"schema": PLAN_SCHEMA, "provider_ref": PROVIDER_REF, "calendar_id": CALENDAR_ID,
            "owner_ref": _id(raw["owner_ref"], where="plan.owner_ref"),
            "time_min": _utc(_dt(raw["time_min"], where="plan.time_min")),
            "time_max": _utc(_dt(raw["time_max"], where="plan.time_max")),
            "response_timezone_str": _tz(raw["response_timezone_str"], where="plan.response_timezone_str"),
            "request_digest": _sha(raw["request_digest"], where="plan.request_digest"),
            "human_authority_sha256": _sha(raw["human_authority_sha256"], where="plan.human_authority_sha256")}
    if _dt(core["time_max"], where="plan.time_max") <= _dt(core["time_min"], where="plan.time_min"):
        raise CalendarConsumerError("plan time range invalid")
    digest = sha256_hex(canonical_json_bytes(core))
    if _sha(raw["plan_sha256"], where="plan.plan_sha256") != digest:
        raise CalendarConsumerError("plan digest mismatch")
    return {**core, "plan_sha256": digest}


def google_tool_args(plan: Any) -> dict[str, Any]:
    p = _normalize_plan(plan)
    return {"calendar_ids": [p["calendar_id"]], "time_min": p["time_min"], "time_max": p["time_max"],
            "response_timezone_str": p["response_timezone_str"]}


def _opaque_id(prefix: str, digest: str) -> str:
    _sha(digest, where="digest")
    return _id(prefix + "/" + "x".join(digest[i:i + 2] for i in range(0, 64, 2)), where="generated opaque id")


def capture_google_availability(plan: Any, provider_result: Any, *, captured_at: datetime) -> dict[str, Any]:
    p = _normalize_plan(plan)
    result = _obj(provider_result, {"calendars"}, where="provider_result")
    calendars = result["calendars"]
    if type(calendars) is not list or len(calendars) != 1:
        raise CalendarConsumerError("provider_result must contain exactly one calendar")
    cal = _obj(calendars[0], {"calendar_id", "busy", "errors"}, where="provider_result.calendars[0]")
    if cal["calendar_id"] != CALENDAR_ID:
        raise CalendarConsumerError("provider calendar binding mismatch")
    if cal["errors"] is not None and type(cal["errors"]) is not list:
        raise CalendarConsumerError("provider errors must be null or list")
    busy = _intervals(cal["busy"], where="provider_result.calendars[0].busy", maximum=128, allow_empty=True)
    qmin, qmax = _dt(p["time_min"], where="plan.time_min"), _dt(p["time_max"], where="plan.time_max")
    for item in busy:
        if _dt(item["start"], where="busy.start") < qmin or _dt(item["end"], where="busy.end") > qmax:
            raise CalendarConsumerError("provider busy window exceeds exact query bounds")
    captured = _utc(captured_at)
    raw_sha = sha256_hex(canonical_json_bytes(provider_result))
    seed = {"plan_sha256": p["plan_sha256"], "captured_at": captured, "busy": busy,
            "errors_present": bool(cal["errors"]), "provider_result_sha256": raw_sha}
    core = {"schema": CAPTURE_SCHEMA, "capture_id": _opaque_id("gcal", sha256_hex(canonical_json_bytes(seed))),
            "provider_ref": PROVIDER_REF, "calendar_id": CALENDAR_ID, "captured_at": captured, "plan": p,
            "provider_result_sha256": raw_sha,
            "response": {"calendars": [{"calendar_id": CALENDAR_ID, "busy": busy,
                                          "errors_present": bool(cal["errors"])}]}}
    return {**core, "capture_sha256": sha256_hex(canonical_json_bytes(core))}


def _capture(value: Any) -> dict[str, Any]:
    keys = {"schema", "capture_id", "provider_ref", "calendar_id", "captured_at", "plan",
            "provider_result_sha256", "response", "capture_sha256"}
    raw = _obj(value, keys, where="capture")
    if raw["schema"] != CAPTURE_SCHEMA or raw["provider_ref"] != PROVIDER_REF or raw["calendar_id"] != CALENDAR_ID:
        raise CalendarConsumerError("capture provider/schema/calendar mismatch")
    response = _obj(raw["response"], {"calendars"}, where="capture.response")
    calendars = response["calendars"]
    if type(calendars) is not list or len(calendars) != 1:
        raise CalendarConsumerError("capture.response must contain exactly one calendar")
    cal = _obj(calendars[0], {"calendar_id", "busy", "errors_present"}, where="capture.response.calendars[0]")
    if cal["calendar_id"] != CALENDAR_ID or type(cal["errors_present"]) is not bool:
        raise CalendarConsumerError("capture calendar/error binding mismatch")
    core = {"schema": CAPTURE_SCHEMA, "capture_id": _id(raw["capture_id"], where="capture.capture_id"),
            "provider_ref": PROVIDER_REF, "calendar_id": CALENDAR_ID,
            "captured_at": _utc(_dt(raw["captured_at"], where="capture.captured_at")),
            "plan": _normalize_plan(raw["plan"]),
            "provider_result_sha256": _sha(raw["provider_result_sha256"], where="capture.provider_result_sha256"),
            "response": {"calendars": [{"calendar_id": CALENDAR_ID,
                                          "busy": _intervals(cal["busy"], where="capture.busy", maximum=128, allow_empty=True),
                                          "errors_present": cal["errors_present"]}]}}
    digest = sha256_hex(canonical_json_bytes(core))
    if _sha(raw["capture_sha256"], where="capture.capture_sha256") != digest:
        raise CalendarConsumerError("capture digest mismatch")
    return {**core, "capture_sha256": digest}


def _first_slot(request: dict[str, Any]) -> dict[str, str]:
    start = _dt(request["windows"][0]["start"], where="window.start")
    return {"start": _utc(start), "end": _utc(start + timedelta(minutes=request["duration_minutes"]))}


def _free_slot(request: dict[str, Any], busy: list[dict[str, str]]) -> dict[str, str] | None:
    duration = timedelta(minutes=request["duration_minutes"])
    ranges = [(_dt(x["start"], where="busy.start"), _dt(x["end"], where="busy.end")) for x in busy]
    for window in request["windows"]:
        cursor, end = _dt(window["start"], where="window.start"), _dt(window["end"], where="window.end")
        for bs, be in ranges:
            if be <= cursor or bs >= end:
                continue
            if bs > cursor and bs - cursor >= duration:
                return {"start": _utc(cursor), "end": _utc(cursor + duration)}
            cursor = max(cursor, be)
            if cursor + duration > end:
                break
        if cursor + duration <= end:
            return {"start": _utc(cursor), "end": _utc(cursor + duration)}
    return None


def _overlap(slot: dict[str, str], busy: list[dict[str, str]]) -> bool:
    s, e = _dt(slot["start"], where="slot.start"), _dt(slot["end"], where="slot.end")
    return any(s < _dt(x["end"], where="busy.end") and _dt(x["start"], where="busy.start") < e for x in busy)


def _busy_slot(request: dict[str, Any], busy: list[dict[str, str]]) -> dict[str, str]:
    slot = _first_slot(request)
    if _overlap(slot, busy):
        return slot
    duration = timedelta(minutes=request["duration_minutes"])
    for window in request["windows"]:
        ws, we = _dt(window["start"], where="window.start"), _dt(window["end"], where="window.end")
        for item in busy:
            bs, be = max(ws, _dt(item["start"], where="busy.start")), min(we, _dt(item["end"], where="busy.end"))
            start = max(ws, bs - duration + timedelta(seconds=1))
            if start + duration <= we and start < be:
                return {"start": _utc(start), "end": _utc(start + duration)}
    raise CalendarConsumerError("calendar has no free duration but no reproducible busy-overlap slot")


def _process_now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _compile(t: dict[str, Any], human: dict[str, Any], cap: dict[str, Any], *, as_of: datetime,
             mode: str, capture_ref: str) -> dict[str, Any]:
    human_sha = sha256_hex(canonical_json_bytes(human))
    if cap["plan"]["human_authority_sha256"] != human_sha or cap["plan"] != _plan(t, human):
        raise CalendarConsumerError("capture plan does not match retained human authority and trigger")
    cal = cap["response"]["calendars"][0]
    busy = cal["busy"]
    if cal["errors_present"]:
        result, slot = "UNKNOWN", _first_slot(t["request"])
    else:
        slot = _free_slot(t["request"], busy)
        result = "FREE" if slot is not None else "BUSY"
        if slot is None:
            slot = _busy_slot(t["request"], busy)
    packet = {"schema": CORE_SCHEMA, "opportunity_id": t["opportunity_id"], "owner_ref": t["owner_ref"],
              "counterparty_ref": t["counterparty_ref"], "thread_ref": t["thread_ref"], "inbound": t["inbound"],
              "request": t["request"], "prep": t["prep"],
              "availability": {"observation_id": cap["capture_id"], "provider_ref": "google-calendar:primary",
                               "captured_at": cap["captured_at"], "opportunity_id": t["opportunity_id"],
                               "owner_ref": t["owner_ref"],
                               "thread_ref": t["thread_ref"], "timezone": t["request"]["timezone"],
                               "duration_minutes": t["request"]["duration_minutes"],
                               "request_digest": cap["plan"]["request_digest"], "busy_windows": busy,
                               "busy_digest": core_busy_digest(busy), "result": result, "proposed_slot": slot}}
    core = compile_meeting_readiness(packet, as_of=as_of)
    current = mode == CURRENT_MODE
    body = {"schema": RECEIPT_SCHEMA, "mode": mode, "state": core["state"] if current else HISTORICAL_REPLAY,
            "historical_core_state": None if current else core["state"], "as_of": core["as_of"],
            "human_authority_ref": t["human_authority_ref"], "calendar_capture_ref": capture_ref,
            "human_authority_sha256": human_sha, "calendar_capture_sha256": cap["capture_sha256"],
            "calendar_plan_sha256": cap["plan"]["plan_sha256"], "core_receipt_sha256": core["receipt_sha256"],
            "core_receipt": core,
            "authority": {"owner_review_only": current, "current_authority_store_bound": current,
                          "historical_replay_only": not current, "calendar_freebusy_read_consumed": True,
                          "calendar_create": False, "calendar_update": False, "calendar_delete": False,
                          "invite_or_rsvp": False, "provider_send_or_reply": False,
                          "scheduling_confirmation": False, "commercial_commitment": False}}
    return {**body, "receipt_sha256": sha256_hex(canonical_json_bytes(body))}


def compile_calendar_consumer_current(trigger: Any, calendar_capture_ref: str, *,
                                      authority_store: CurrentAuthorityStore) -> dict[str, Any]:
    t = _trigger(trigger)
    human = _human(_lookup(authority_store, "get_human_authority", t["human_authority_ref"],
                           where="current human authority"), t)
    ref = _id(calendar_capture_ref, where="calendar_capture_ref")
    cap = _capture(_lookup(authority_store, "get_calendar_capture", ref, where="current calendar capture"))
    return _compile(t, human, cap, as_of=_process_now_utc(), mode=CURRENT_MODE, capture_ref=ref)


def compile_calendar_consumer_historical(trigger: Any, human_authority: Any, capture: Any, *,
                                         as_of: datetime) -> dict[str, Any]:
    t = _trigger(trigger)
    return _compile(t, _human(human_authority, t), _capture(capture), as_of=as_of,
                    mode=HISTORICAL_MODE, capture_ref="historical/direct")


compile_calendar_consumer = compile_calendar_consumer_current


def _receipt(value: Any) -> dict[str, Any]:
    keys = {"schema", "mode", "state", "historical_core_state", "as_of", "human_authority_ref",
            "calendar_capture_ref", "human_authority_sha256", "calendar_capture_sha256", "calendar_plan_sha256",
            "core_receipt_sha256", "core_receipt", "authority", "receipt_sha256"}
    raw = _obj(value, keys, where="receipt")
    if raw["schema"] != RECEIPT_SCHEMA or raw["mode"] not in {CURRENT_MODE, HISTORICAL_MODE}:
        raise CalendarConsumerError("unsupported receipt schema/mode")
    if type(raw["core_receipt"]) is not dict or raw["core_receipt"].get("receipt_sha256") != raw["core_receipt_sha256"]:
        raise CalendarConsumerError("core receipt binding mismatch")
    body = {k: deepcopy(v) for k, v in raw.items() if k != "receipt_sha256"}
    if sha256_hex(canonical_json_bytes(body)) != _sha(raw["receipt_sha256"], where="receipt.receipt_sha256"):
        raise CalendarConsumerError("wrapper receipt digest mismatch")
    return raw


def render_markdown(receipt: Any) -> str:
    r = _receipt(receipt)
    lines = ["# Sales meeting calendar consumer", "", f"**Mode:** `{r['mode']}`", f"**State:** `{r['state']}`",
             f"**Verified at:** `{r['as_of']}`", f"**Human authority ref:** `{r['human_authority_ref']}`",
             f"**Calendar capture ref:** `{r['calendar_capture_ref']}`", "", "## Mutation boundary", "",
             "- Current READY requires independently retained authority-store records."
             if r["mode"] == CURRENT_MODE else "- Historical replay is integrity-only and cannot authorize scheduling review.",
             "- Google Calendar free/busy: read-only evidence consumed.",
             "- Calendar create/update/delete: **not authorized**.",
             "- Invite/RSVP/send/reply/scheduling confirmation: **not authorized**.", ""]
    return "\n".join(lines) + "\n" + render_core_markdown(r["core_receipt"])


def is_ready_for_owner_review(receipt: Any, trigger: Any, *, authority_store: CurrentAuthorityStore) -> bool:
    r = _receipt(receipt)
    if r["mode"] != CURRENT_MODE or r["state"] != CORE_READY:
        return False
    t = _trigger(trigger)
    if t["human_authority_ref"] != r["human_authority_ref"]:
        return False
    human = _human(_lookup(authority_store, "get_human_authority", t["human_authority_ref"],
                           where="current human authority"), t)
    cap = _capture(_lookup(authority_store, "get_calendar_capture", r["calendar_capture_ref"],
                           where="current calendar capture"))
    if sha256_hex(canonical_json_bytes(human)) != r["human_authority_sha256"] or cap["capture_sha256"] != r["calendar_capture_sha256"]:
        return False
    return compile_calendar_consumer_current(t, r["calendar_capture_ref"], authority_store=authority_store)["state"] == CORE_READY
