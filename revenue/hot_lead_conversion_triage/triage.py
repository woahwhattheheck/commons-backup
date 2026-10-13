"""Deterministic hot-lead conversion triage with a hard publication ceiling."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = 1
MAX_THREADS = 10_000
MAX_OBSERVATIONS_PER_THREAD = 2_000
MAX_CANDIDATE_CHARS = 20_000
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+~=-]{0,191}$")

HUMAN_POSITIVE = "HUMAN_POSITIVE"
HUMAN_QUESTION = "HUMAN_QUESTION"
HUMAN_NEGATIVE = "HUMAN_NEGATIVE"
EXPLICIT_DNR = "EXPLICIT_DNR"
AUTOMATED_ACK = "AUTOMATED_ACK"
DELIVERY_FAILURE = "DELIVERY_FAILURE"
NO_REPLY = "NO_REPLY"

ALLOWED_KINDS = frozenset(
    {
        HUMAN_POSITIVE,
        HUMAN_QUESTION,
        HUMAN_NEGATIVE,
        EXPLICIT_DNR,
        AUTOMATED_ACK,
        DELIVERY_FAILURE,
        NO_REPLY,
    }
)
HUMAN_KINDS = frozenset(
    {HUMAN_POSITIVE, HUMAN_QUESTION, HUMAN_NEGATIVE, EXPLICIT_DNR}
)
ACTIONABLE_HUMAN_KINDS = frozenset({HUMAN_POSITIVE, HUMAN_QUESTION})


class TriageInputError(ValueError):
    """Machine-readable structural failure before any triage authority is emitted."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_exact_keys(
    value: dict[str, Any], *, allowed: set[str], required: set[str], where: str
) -> None:
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - allowed)
    if missing:
        raise TriageInputError("MISSING_FIELD", f"{where} missing fields: {', '.join(missing)}")
    if unknown:
        raise TriageInputError("UNKNOWN_FIELD", f"{where} has unknown fields: {', '.join(unknown)}")


def _require_id(value: Any, *, where: str) -> str:
    if type(value) is not str or not ID_RE.fullmatch(value):
        raise TriageInputError(
            "INVALID_ID",
            f"{where} must match {ID_RE.pattern}",
        )
    return value


def _parse_timestamp(value: Any, *, where: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise TriageInputError(
            "INVALID_TIMESTAMP",
            f"{where} must be an RFC3339 UTC timestamp ending in Z",
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise TriageInputError(
            "INVALID_TIMESTAMP",
            f"{where} must be an RFC3339 UTC timestamp",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise TriageInputError(
            "INVALID_TIMESTAMP",
            f"{where} must be UTC",
        )
    return parsed


def _candidate_digest(value: Any) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not value or len(value) > MAX_CANDIDATE_CHARS:
        raise TriageInputError(
            "INVALID_CANDIDATE",
            f"candidate_followup must be 1..{MAX_CANDIDATE_CHARS} Unicode characters",
        )
    return _sha256_bytes(value.encode("utf-8"))


def _blocked_item(
    *,
    prospect_id: str,
    thread_id: str,
    reason_code: str,
    candidate_sha256: str | None,
    latest_observed_at: str | None,
) -> dict[str, Any]:
    return {
        "prospect_id": prospect_id,
        "thread_id": thread_id,
        "disposition": "BLOCKED",
        "reason_code": reason_code,
        "priority": 999,
        "needs_human_response": False,
        "candidate_followup_sha256": candidate_sha256,
        "latest_observed_at": latest_observed_at,
        "external_send_authorized": False,
    }


def _triage_thread(thread: Any, *, as_of: datetime) -> dict[str, Any]:
    if type(thread) is not dict:
        raise TriageInputError("INVALID_THREAD", "each threads item must be an object")
    _require_exact_keys(
        thread,
        allowed={
            "prospect_id",
            "thread_id",
            "last_outbound_at",
            "candidate_followup",
            "observations",
        },
        required={"prospect_id", "thread_id", "observations"},
        where="thread",
    )
    prospect_id = _require_id(thread["prospect_id"], where="thread.prospect_id")
    thread_id = _require_id(thread["thread_id"], where="thread.thread_id")
    candidate_sha256 = _candidate_digest(thread.get("candidate_followup"))

    raw_last_outbound = thread.get("last_outbound_at")
    last_outbound: datetime | None = None
    if raw_last_outbound is not None:
        last_outbound = _parse_timestamp(
            raw_last_outbound, where=f"{prospect_id}/{thread_id}.last_outbound_at"
        )
        if last_outbound > as_of:
            raise TriageInputError(
                "FUTURE_TIMESTAMP",
                f"{prospect_id}/{thread_id}.last_outbound_at is after as_of",
            )

    observations = thread["observations"]
    if type(observations) is not list or len(observations) > MAX_OBSERVATIONS_PER_THREAD:
        raise TriageInputError(
            "INVALID_OBSERVATIONS",
            f"observations must be a list of at most {MAX_OBSERVATIONS_PER_THREAD} items",
        )

    parsed: list[tuple[datetime, str, str, str]] = []
    event_ids: set[str] = set()
    human_by_time: dict[datetime, set[str]] = {}
    for index, observation in enumerate(observations):
        if type(observation) is not dict:
            raise TriageInputError(
                "INVALID_OBSERVATION",
                f"{prospect_id}/{thread_id}.observations[{index}] must be an object",
            )
        _require_exact_keys(
            observation,
            allowed={"event_id", "observed_at", "kind"},
            required={"event_id", "observed_at", "kind"},
            where=f"{prospect_id}/{thread_id}.observations[{index}]",
        )
        event_id = _require_id(
            observation["event_id"],
            where=f"{prospect_id}/{thread_id}.observations[{index}].event_id",
        )
        if event_id in event_ids:
            raise TriageInputError(
                "DUPLICATE_EVENT_ID",
                f"{prospect_id}/{thread_id} repeats event_id {event_id}",
            )
        event_ids.add(event_id)
        observed = _parse_timestamp(
            observation["observed_at"],
            where=f"{prospect_id}/{thread_id}.observations[{index}].observed_at",
        )
        if observed > as_of:
            raise TriageInputError(
                "FUTURE_TIMESTAMP",
                f"{prospect_id}/{thread_id} observation {event_id} is after as_of",
            )
        kind = observation["kind"]
        if type(kind) is not str or kind not in ALLOWED_KINDS:
            raise TriageInputError(
                "INVALID_KIND",
                f"{prospect_id}/{thread_id} observation {event_id} has unsupported kind",
            )
        parsed.append((observed, event_id, kind, observation["observed_at"]))
        if kind in HUMAN_KINDS:
            human_by_time.setdefault(observed, set()).add(kind)

    parsed.sort(key=lambda row: (row[0], row[1]))
    latest_observed_at = parsed[-1][3] if parsed else None

    # Multiple mutually exclusive human meanings at the same observation instant
    # are not ordered evidence. Refuse to infer which one should win.
    for timestamp, kinds in human_by_time.items():
        if len(kinds) > 1:
            return _blocked_item(
                prospect_id=prospect_id,
                thread_id=thread_id,
                reason_code="CONTRADICTORY_HUMAN_OBSERVATION",
                candidate_sha256=candidate_sha256,
                latest_observed_at=latest_observed_at,
            )

    dnr_events = [row for row in parsed if row[2] == EXPLICIT_DNR]
    if dnr_events:
        return {
            "prospect_id": prospect_id,
            "thread_id": thread_id,
            "disposition": "TERMINAL_DNR",
            "reason_code": "EXPLICIT_DNR_PRESENT",
            "priority": 999,
            "needs_human_response": False,
            "candidate_followup_sha256": candidate_sha256,
            "latest_observed_at": latest_observed_at,
            "external_send_authorized": False,
        }

    human_events = [row for row in parsed if row[2] in HUMAN_KINDS]
    latest_human = human_events[-1] if human_events else None
    latest_failure = next(
        (row for row in reversed(parsed) if row[2] == DELIVERY_FAILURE), None
    )
    latest_auto = next(
        (row for row in reversed(parsed) if row[2] == AUTOMATED_ACK), None
    )

    if latest_human is not None and last_outbound is not None and latest_human[0] == last_outbound:
        return _blocked_item(
            prospect_id=prospect_id,
            thread_id=thread_id,
            reason_code="AMBIGUOUS_REPLY_OUTBOUND_ORDER",
            candidate_sha256=candidate_sha256,
            latest_observed_at=latest_observed_at,
        )

    # A human reply after the latest outbound is the conversion event that matters.
    if latest_human is not None and (
        last_outbound is None or latest_human[0] > last_outbound
    ):
        kind = latest_human[2]
        if kind == HUMAN_POSITIVE:
            disposition, reason, priority, needs_response = (
                "ACTIONABLE_INBOUND",
                "UNANSWERED_HUMAN_POSITIVE",
                0,
                True,
            )
        elif kind == HUMAN_QUESTION:
            disposition, reason, priority, needs_response = (
                "ACTIONABLE_INBOUND",
                "UNANSWERED_HUMAN_QUESTION",
                10,
                True,
            )
        else:
            disposition, reason, priority, needs_response = (
                "HOLD",
                "UNANSWERED_HUMAN_NEGATIVE",
                40,
                False,
            )
        return {
            "prospect_id": prospect_id,
            "thread_id": thread_id,
            "disposition": disposition,
            "reason_code": reason,
            "priority": priority,
            "needs_human_response": needs_response,
            "candidate_followup_sha256": candidate_sha256,
            "latest_observed_at": latest_observed_at,
            "external_send_authorized": False,
        }

    # If we attempted a newer outbound and it failed, the thread is not answered.
    if latest_failure is not None and (
        last_outbound is None or latest_failure[0] >= last_outbound
    ):
        return {
            "prospect_id": prospect_id,
            "thread_id": thread_id,
            "disposition": "BLOCKED",
            "reason_code": "DELIVERY_FAILURE",
            "priority": 60,
            "needs_human_response": False,
            "candidate_followup_sha256": candidate_sha256,
            "latest_observed_at": latest_observed_at,
            "external_send_authorized": False,
        }

    if latest_human is not None and last_outbound is not None:
        return {
            "prospect_id": prospect_id,
            "thread_id": thread_id,
            "disposition": "WAIT",
            "reason_code": "HUMAN_REPLY_ALREADY_ANSWERED",
            "priority": 70,
            "needs_human_response": False,
            "candidate_followup_sha256": candidate_sha256,
            "latest_observed_at": latest_observed_at,
            "external_send_authorized": False,
        }

    if latest_auto is not None:
        return {
            "prospect_id": prospect_id,
            "thread_id": thread_id,
            "disposition": "HOLD",
            "reason_code": "AUTOMATED_ACK_ONLY",
            "priority": 80,
            "needs_human_response": False,
            "candidate_followup_sha256": candidate_sha256,
            "latest_observed_at": latest_observed_at,
            "external_send_authorized": False,
        }

    if last_outbound is not None:
        return {
            "prospect_id": prospect_id,
            "thread_id": thread_id,
            "disposition": "WAIT",
            "reason_code": "NO_HUMAN_REPLY",
            "priority": 90,
            "needs_human_response": False,
            "candidate_followup_sha256": candidate_sha256,
            "latest_observed_at": latest_observed_at,
            "external_send_authorized": False,
        }

    return {
        "prospect_id": prospect_id,
        "thread_id": thread_id,
        "disposition": "COLD",
        "reason_code": "NO_OUTBOUND_OR_HUMAN_REPLY",
        "priority": 100,
        "needs_human_response": False,
        "candidate_followup_sha256": candidate_sha256,
        "latest_observed_at": latest_observed_at,
        "external_send_authorized": False,
    }


def triage_document(document: Any) -> dict[str, Any]:
    """Validate and rank one owner-supplied hot-lead observation document."""
    if type(document) is not dict:
        raise TriageInputError("INVALID_DOCUMENT", "document must be an object")
    _require_exact_keys(
        document,
        allowed={"schema_version", "as_of", "threads"},
        required={"schema_version", "as_of", "threads"},
        where="document",
    )
    if document["schema_version"] != SCHEMA_VERSION or type(document["schema_version"]) is not int:
        raise TriageInputError(
            "UNSUPPORTED_SCHEMA",
            f"schema_version must equal {SCHEMA_VERSION}",
        )
    as_of = _parse_timestamp(document["as_of"], where="document.as_of")
    threads = document["threads"]
    if type(threads) is not list or len(threads) > MAX_THREADS:
        raise TriageInputError(
            "INVALID_THREADS",
            f"threads must be a list of at most {MAX_THREADS} items",
        )

    seen_threads: set[tuple[str, str]] = set()
    items: list[dict[str, Any]] = []
    for thread in threads:
        item = _triage_thread(thread, as_of=as_of)
        key = (item["prospect_id"], item["thread_id"])
        if key in seen_threads:
            raise TriageInputError(
                "DUPLICATE_THREAD",
                f"duplicate prospect/thread identity: {key[0]}/{key[1]}",
            )
        seen_threads.add(key)
        items.append(item)

    items.sort(
        key=lambda item: (
            item["priority"],
            item["prospect_id"],
            item["thread_id"],
        )
    )
    queue = [
        {
            "prospect_id": item["prospect_id"],
            "thread_id": item["thread_id"],
            "reason_code": item["reason_code"],
            "priority": item["priority"],
            "candidate_followup_sha256": item["candidate_followup_sha256"],
            "external_send_authorized": False,
        }
        for item in items
        if item["disposition"] == "ACTIONABLE_INBOUND"
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "as_of": document["as_of"],
        "input_sha256": _sha256_bytes(_canonical_json(document)),
        "authority": {
            "scope": "triage_only",
            "external_send_authorized": False,
            "muse_election_claimed": False,
            "publication_authority_required": True,
            "publication_authority_note": (
                "A separate current publication-election/authority receipt is required "
                "before any external send."
            ),
        },
        "action_queue": queue,
        "items": items,
    }


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TriageInputError("DUPLICATE_JSON_KEY", f"duplicate JSON key: {key}")
        result[key] = value
    return result


def loads_strict(text: str) -> Any:
    """Parse JSON while rejecting duplicate keys and non-finite constants."""
    def reject_constant(value: str) -> None:
        raise TriageInputError("NONFINITE_JSON", f"non-finite JSON value: {value}")

    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=reject_constant,
        )
    except TriageInputError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise TriageInputError("INVALID_JSON", "input is not valid JSON") from exc
