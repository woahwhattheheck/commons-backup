#!/usr/bin/env python3
"""UIOWA-129: evidence-preserving timestamp normalization; no clock or network."""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import re
import sys
from datetime import datetime, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any
import zoneinfo

UTC = timezone.utc
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
PATTERN = re.compile(
    r"(?P<local>[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?)(?P<offset>[Zz]|[+-][0-9]{2}:[0-9]{2})?\Z"
)


class InputError(ValueError):
    """Malformed input contract, as distinct from an unresolved timestamp."""


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def read_json(path: Path) -> Any:
    def invalid_constant(value: str) -> None:
        raise InputError(f"non-finite JSON value: {value}")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs,
                      parse_constant=invalid_constant)


def _iso(instant: datetime) -> str:
    return instant.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _micros(instant: datetime) -> int:
    delta = instant.astimezone(UTC) - EPOCH
    return (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds


@lru_cache(maxsize=128)
def _zone(key: str) -> tuple[zoneinfo.ZoneInfo, dict]:
    """Load AND hash the same TZif bytes. A cached ZoneInfo is not mixed with a newer file."""
    parts = key.split("/")
    if (key != "UTC" and len(parts) < 2) or any(
        not re.fullmatch(r"[A-Za-z0-9_+.-]+", part) or part in {".", ".."}
        for part in parts
    ):
        raise InputError("use an IANA key such as America/New_York or UTC, not an abbreviation/path")
    for root in zoneinfo.TZPATH:
        path = Path(root).joinpath(*parts)
        try:
            data = path.read_bytes()
        except (OSError, ValueError):
            continue
        try:
            zone = zoneinfo.ZoneInfo.from_file(io.BytesIO(data), key=key)
        except (ValueError, OSError):
            continue
        return zone, {"zone": key, "provider": "system", "tzif_sha256": hashlib.sha256(data).hexdigest()}
    try:
        data = resources.files("tzdata.zoneinfo").joinpath(*parts).read_bytes()
        zone = zoneinfo.ZoneInfo.from_file(io.BytesIO(data), key=key)
        return zone, {"zone": key, "provider": "tzdata", "tzif_sha256": hashlib.sha256(data).hexdigest()}
    except (ImportError, OSError, ValueError) as exc:
        raise LookupError("IANA zone is unknown or its timezone data is unavailable") from exc


def normalize(spec: Any) -> dict:
    """Return a JSON-safe diagnostic; never guess a zone or silently select a DST fold.

    spec: timestamp string, null, or {value: string|null, zone?: IANA key, fold?: 0|1}.
    Z/-00:00 specify a known UTC instant, not an unknown instant (RFC 9557 section 2).
    With numeric offsets and a zone, the stated civil time/offset must agree with that zone.
    """
    result = {"source": copy.deepcopy(spec), "status": "invalid", "code": None,
              "message": None, "instant_utc": None, "epoch_microseconds": None,
              "candidates": [], "tzdb": None, "source_offset_kind": None}

    def stop(status: str, code: str, message: str) -> dict:
        result.update(status=status, code=code, message=message)
        return result

    def resolved(instant: datetime, code: str, message: str) -> dict:
        result.update(instant_utc=_iso(instant), epoch_microseconds=_micros(instant))
        return stop("resolved", code, message)

    if isinstance(spec, dict):
        if set(spec) - {"value", "zone", "fold"} or "value" not in spec:
            return stop("invalid", "invalid_spec", "timestamp object requires value and allows only zone/fold")
        value, key, fold = spec["value"], spec.get("zone"), spec.get("fold")
    else:
        value, key, fold = spec, None, None
    if key is not None and (not isinstance(key, str) or not key):
        return stop("invalid", "invalid_zone", "zone must be a nonempty IANA key")
    if fold is not None and (type(fold) is not int or fold not in (0, 1)):
        return stop("invalid", "invalid_fold", "fold must be integer 0 or 1, not a boolean")
    if fold is not None and key is None:
        return stop("invalid", "fold_requires_zone", "fold has meaning only with an explicit IANA zone")
    if value is None or (isinstance(value, str) and not value.strip()):
        return stop("missing", "missing_timestamp", "no timestamp supplied; no zero or current time substituted")
    if not isinstance(value, str):
        return stop("invalid", "invalid_type", "timestamp value must be a string or null")
    match = PATTERN.fullmatch(value)
    if not match:
        return stop("invalid", "invalid_format", "expected YYYY-MM-DDTHH:MM:SS[.ffffff][Z|+HH:MM|-HH:MM]")
    local_text, offset = match.group("local"), match.group("offset")
    fraction = local_text.partition(".")[2]
    if len(fraction) > 6:
        return stop("invalid", "unsupported_precision", "more than six fractional digits would lose precision")
    if local_text[17:19] == "60":
        return stop("invalid", "unsupported_leap_second", "leap-second arithmetic is outside this adapter's datetime profile")
    if offset and offset.upper() != "Z" and (int(offset[1:3]) > 23 or int(offset[4:6]) > 59):
        return stop("invalid", "invalid_offset", "numeric offset hours/minutes are out of range")
    try:
        local = datetime.fromisoformat(local_text.replace("t", "T"))
        unknown_local_offset = offset in ("Z", "z", "-00:00")
        result["source_offset_kind"] = (
            "utc_known_local_offset_unspecified" if unknown_local_offset else "numeric" if offset else "local"
        )
        aware = datetime.fromisoformat(local.isoformat() + ("+00:00" if unknown_local_offset else offset)) if offset else None
        tz, metadata = None, None
        if key is not None:
            try:
                tz, metadata = _zone(key)
            except InputError as exc:
                return stop("invalid", "invalid_zone", str(exc))
            except LookupError as exc:
                return stop("unresolved", "zone_unavailable", str(exc))
            result["tzdb"] = copy.deepcopy(metadata)
        if aware is not None:
            instant = aware.astimezone(UTC)
            if tz is not None:
                actual_local = instant.astimezone(tz)
                result["local_in_zone"] = actual_local.isoformat()
                if not unknown_local_offset and (
                    actual_local.replace(tzinfo=None) != local or actual_local.utcoffset() != aware.utcoffset()
                ):
                    return stop("invalid", "offset_zone_mismatch", "supplied civil time/offset contradicts the IANA zone")
                if fold is not None and actual_local.fold != fold:
                    return stop("invalid", "fold_conflict", "explicit fold contradicts the resolved instant")
            return resolved(instant, "resolved_offset", "instant established by explicit UTC/numeric offset")
        if tz is None:
            return stop("unresolved", "missing_offset_or_zone", "local time has neither a UTC offset nor an IANA zone")
        by_instant: dict[int, tuple[datetime, int]] = {}
        for candidate_fold in (0, 1):
            candidate = local.replace(tzinfo=tz, fold=candidate_fold).astimezone(UTC)
            back = candidate.astimezone(tz)
            # replace(tzinfo=...) alone accepts imaginary times. Round-trip each candidate.
            if back.replace(tzinfo=None) == local and back.fold == candidate_fold:
                by_instant[_micros(candidate)] = (candidate, candidate_fold)
        for instant, candidate_fold in sorted(by_instant.values(), key=lambda pair: pair[0]):
            result["candidates"].append({"fold": candidate_fold, "instant_utc": _iso(instant),
                                         "offset_seconds": int(instant.astimezone(tz).utcoffset().total_seconds())})
        if not by_instant:
            return stop("invalid", "nonexistent_local_time", "local clock value falls in a timezone gap; fold cannot repair it")
        if len(by_instant) > 1 and fold is None:
            return stop("unresolved", "ambiguous_local_time", "multiple real instants; supply an evidenced fold or numeric offset")
        selected = [(instant, f) for instant, f in by_instant.values() if fold is None or f == fold]
        if not selected:
            return stop("invalid", "fold_conflict", "fold=1 is not valid for this unambiguous local clock value")
        instant, _ = selected[0]
        result["local_in_zone"] = instant.astimezone(tz).isoformat()
        return resolved(instant, "resolved_zone", "unique instant established from supplied zone and any explicit fold")
    except (ValueError, OverflowError) as exc:
        return stop("invalid", "invalid_or_out_of_range_time", str(exc))


def interval_from_results(start: dict, end: dict) -> dict:
    """Subtract normalized UTC integer microseconds, not wall-clock datetimes."""
    result = {"status": "unresolved", "code": "unresolved_endpoint", "duration_microseconds": None,
              "duration_seconds": None, "start_status": start["status"], "end_status": end["status"]}
    if start["status"] == "invalid" or end["status"] == "invalid":
        result.update(status="invalid", code="invalid_endpoint")
    if start["status"] != "resolved" or end["status"] != "resolved":
        return result
    micros = end["epoch_microseconds"] - start["epoch_microseconds"]
    if micros < 0:
        result.update(status="invalid", code="reversed_timeline", signed_microseconds=micros)
        return result
    result.update(status="resolved", code="resolved_interval", duration_microseconds=micros,
                  duration_seconds=micros / 1000000)
    return result


def elapsed(start: Any, end: Any) -> dict:
    first, last = normalize(start), normalize(end)
    return {**interval_from_results(first, last), "start": first, "end": last}


def normalize_packet(packet: Any) -> dict:
    if not isinstance(packet, dict) or type(packet.get("schema_version")) is not int or packet["schema_version"] != 1:
        raise InputError("packet must be an object with integer schema_version=1")
    if not isinstance(packet.get("events"), list) or not isinstance(packet.get("intervals", []), list):
        raise InputError("events and intervals must be arrays")
    if "synthetic" in packet and type(packet["synthetic"]) is not bool:
        raise InputError("synthetic label must be a boolean when supplied")
    try:
        digest = hashlib.sha256(canonical(packet).encode("utf-8")).hexdigest()
    except (TypeError, ValueError) as exc:
        raise InputError(f"packet must contain finite JSON values: {exc}") from exc
    events, intervals, by_id = [], [], {}
    for index, event in enumerate(packet["events"]):
        locator = f"/events/{index}"
        if not isinstance(event, dict) or not isinstance(event.get("id"), str) or not event["id"].strip():
            raise InputError(f"{locator}: event requires a nonempty string id")
        identifier = event["id"]
        if identifier in by_id:
            raise InputError(f"{locator}/id: duplicate event id {identifier!r}; joining is ambiguous")
        normalized = normalize(event.get("timestamp"))
        by_id[identifier] = normalized
        events.append({"id": identifier, "source_locator": locator, "source_record": copy.deepcopy(event),
                       "normalization": normalized})
    seen = set()
    for index, item in enumerate(packet.get("intervals", [])):
        locator = f"/intervals/{index}"
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
            raise InputError(f"{locator}: interval requires a nonempty string id")
        if item["id"] in seen:
            raise InputError(f"{locator}/id: duplicate interval id {item['id']!r}")
        seen.add(item["id"])
        if not all(isinstance(item.get(k), str) and item[k].strip() for k in ("start", "end")):
            raise InputError(f"{locator}: start and end must be nonempty event-id strings")
        missing = sorted({item[k] for k in ("start", "end") if item[k] not in by_id})
        measurement = ({"status": "unresolved", "code": "unknown_event", "missing_event_ids": missing,
                        "duration_microseconds": None, "duration_seconds": None} if missing else
                       interval_from_results(by_id[item["start"]], by_id[item["end"]]))
        intervals.append({"id": item["id"], "source_locator": locator, "source_record": copy.deepcopy(item),
                          **measurement})
    return {"schema_version": 1, "synthetic": packet.get("synthetic"), "source_packet": copy.deepcopy(packet),
            "source_sha256": digest, "events": events, "intervals": intervals,
            "summary": {"events": len(events), "intervals": len(intervals),
                        "unresolved_events": sum(e["normalization"]["status"] != "resolved" for e in events),
                        "unresolved_intervals": sum(i["status"] != "resolved" for i in intervals)},
            "boundary": "Timestamp consistency only; not proof of record authenticity, clock synchronization, recovery or causality."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--output", type=Path, help="new JSON report path; existing paths are refused")
    parser.add_argument("--require-resolved", action="store_true", help="exit 1 when any event or interval is unresolved/invalid/missing")
    args = parser.parse_args(argv)
    try:
        if args.output and args.output.resolve() == args.packet.resolve():
            raise InputError("output must not overwrite the source packet")
        report = normalize_packet(read_json(args.packet))
        payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
        if args.output:
            # Exclusive creation also refuses hard-link and dangling symlink
            # aliases; resolve() alone does not identify every existing file.
            with args.output.open("x", encoding="utf-8", newline="") as stream:
                stream.write(payload)
        else:
            sys.stdout.write(payload)
    except (InputError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return int(args.require_resolved and bool(report["summary"]["unresolved_events"] or report["summary"]["unresolved_intervals"]))


if __name__ == "__main__":
    raise SystemExit(main())
