from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ._constants import MAX_ITEMS, QualificationInputError, _EXPLICIT_TZ
from ._json import _identifier, _string


def _instant(value: Any, name: str) -> datetime:
    value = _string(value, name, max_bytes=64)
    if _EXPLICIT_TZ.search(value) is None:
        raise QualificationInputError(f"{name} must include an explicit UTC offset or Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise QualificationInputError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise QualificationInputError(f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise QualificationInputError("trusted clock must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _optional_expiry(value: Any, name: str) -> datetime | None:
    return None if value is None else _instant(value, name)


def _id_list(value: Any, name: str, *, allow_empty: bool = True) -> list[str]:
    if type(value) is not list or len(value) > MAX_ITEMS or (not allow_empty and not value):
        raise QualificationInputError(f"{name} must be a bounded array")
    parsed = [_identifier(item, f"{name}[]") for item in value]
    if len(parsed) != len(set(parsed)):
        raise QualificationInputError(f"{name} contains duplicates")
    return sorted(parsed)
