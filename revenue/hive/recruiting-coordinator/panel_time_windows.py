#!/usr/bin/env python3
"""Pure timezone/availability component for a recruiter-operated scheduling desk.

No storage, network, messages, hiring scores, UI or booking writes. A caller must
recheck under its own booking transaction before committing a suggested slot.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc
MAX_SPAN = timedelta(days=31)
MAX_ROWS = 10000

class WindowError(ValueError):
    """Invalid time/availability input, including ambiguous local wall times."""


def _integer(value, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise WindowError(f'{label} must be an integer from {low} to {high}.')
    return value


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise WindowError(f'{label} must be a nonempty string of at most 200 characters.')
    return value


def _bounded(rows: Iterable, label: str, maximum: int = MAX_ROWS) -> list:
    if isinstance(rows, (str, bytes, Mapping)):
        raise WindowError(f'{label} must be a sequence of entries.')
    try:
        result = []
        for row in rows:
            if len(result) >= maximum:
                raise WindowError(f'{label} exceeds {maximum} entries.')
            result.append(row)
        return result
    except TypeError:
        raise WindowError(f'{label} must be iterable.') from None


def timezone_for(name: str) -> ZoneInfo:
    if not isinstance(name, str) or not name or len(name) > 100:
        raise WindowError('Provide an IANA timezone name, for example America/Chicago.')
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise WindowError(f'Time zone {name!r} is unavailable in this Python environment.') from None


def resolve_time(value: str | datetime, timezone_name: str | None = None, *, fold: int | None = None) -> datetime:
    """Return a minute-aligned aware UTC instant, without guessing a DST fold.

    Explicit-offset inputs name an instant directly. A naive input requires an
    IANA zone; a nonexistent wall time fails, and an ambiguous one requires an
    explicit UTC offset or fold=0 (first) / fold=1 (second).
    """
    if fold is not None and (type(fold) is not int or fold not in (0, 1)):
        raise WindowError('Fold must be 0, 1, or omitted.')
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and len(value) <= 100 and 'T' in value:
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            raise WindowError('Use an ISO date and time, for example 2030-01-15T09:00-06:00.') from None
    else:
        raise WindowError('Use an ISO date and time, not a date alone.')
    if dt.second or dt.microsecond:
        raise WindowError('Scheduling times must use whole-minute precision.')
    if dt.tzinfo is not None:
        offset = dt.utcoffset()
        if offset is None or offset.total_seconds() % 60:
            raise WindowError('An explicit UTC offset must have whole-minute precision.')
        try:
            return dt.astimezone(UTC)
        except (OverflowError, ValueError):
            raise WindowError('Time is outside the supported datetime range.') from None
    if timezone_name is None:
        raise WindowError('Naive local time requires a participant timezone.')
    z = timezone_for(timezone_name)
    candidates = {}
    try:
        for f in (0, 1):
            aware = dt.replace(tzinfo=z, fold=f)
            utc = aware.astimezone(UTC)
            if utc.astimezone(z).replace(tzinfo=None) == dt:
                candidates[f] = utc
    except (OverflowError, ValueError):
        raise WindowError('Time is outside the supported datetime range.') from None
    if not candidates:
        raise WindowError('Local time does not exist because of a clock change; choose another time.')
    if len(set(candidates.values())) > 1 and fold is None:
        raise WindowError('Ambiguous local time: provide an explicit UTC offset or fold=0/1.')
    result = candidates.get(fold, next(iter(candidates.values())))
    if result.second or result.microsecond:
        raise WindowError('This historical timezone offset cannot be represented at whole-minute precision.')
    return result


def utc_text(value: datetime) -> str:
    return resolve_time(value).isoformat(timespec='minutes').replace('+00:00', 'Z')


@dataclass(frozen=True, order=True)
class Window:
    start: datetime
    end: datetime

    def __post_init__(self):
        a, b = resolve_time(self.start), resolve_time(self.end)
        if b <= a:
            raise WindowError('An interval must end strictly after it starts.')
        object.__setattr__(self, 'start', a)
        object.__setattr__(self, 'end', b)

    def to_dict(self) -> dict[str, str]:
        return {'start': utc_text(self.start), 'end': utc_text(self.end)}


@dataclass(frozen=True)
class BusyBooking:
    booking_id: str
    participant_ids: tuple[str, ...]
    window: Window

    def __post_init__(self):
        _identifier(self.booking_id, 'Booking ID')
        ids = _bounded(self.participant_ids, 'Booking participants', 100)
        for pid in ids:
            _identifier(pid, 'Participant ID')
        if not ids or len(set(ids)) != len(ids):
            raise WindowError('A booking needs distinct participant IDs.')
        if not isinstance(self.window, Window):
            raise WindowError('Booking window must be a Window.')
        object.__setattr__(self, 'participant_ids', tuple(ids))


def normalize_windows(rows: Iterable[dict | Window], timezone_name: str | None = None) -> tuple[Window, ...]:
    """Validate, sort and merge overlapping/adjacent intervals without mutation.

    Dict rows contain start/end; optional start_fold/end_fold disambiguate local
    endpoints independently. Each source row is limited to 31 days. The result
    can span longer when adjacent valid rows are merged.
    """
    parsed = []
    for row in _bounded(rows, 'Availability'):
        if isinstance(row, Window):
            w = row
        elif isinstance(row, dict) and 'start' in row and 'end' in row:
            w = Window(resolve_time(row['start'], timezone_name, fold=row.get('start_fold')),
                       resolve_time(row['end'], timezone_name, fold=row.get('end_fold')))
        else:
            raise WindowError('Each availability row needs start and end.')
        if w.end-w.start > MAX_SPAN:
            raise WindowError('An availability source interval exceeds 31 days.')
        parsed.append(w)
    merged = []
    for w in sorted(parsed):
        if merged and w.start <= merged[-1].end:
            merged[-1] = Window(merged[-1].start, max(merged[-1].end, w.end))
        else:
            merged.append(w)
    return tuple(merged)


def _participants(ids: Sequence[str]) -> tuple[str, ...]:
    result = _bounded(ids, 'Participants', 100)
    for pid in result:
        _identifier(pid, 'Participant ID')
    if not result or len(set(result)) != len(result):
        raise WindowError('Provide distinct participant IDs.')
    return tuple(result)


def _availability(mapping: Mapping[str, Iterable[Window]], ids: tuple[str, ...]) -> dict[str, tuple[Window, ...]]:
    if not isinstance(mapping, Mapping):
        raise WindowError('Availability must map participant IDs to normalized Window entries.')
    result = {}
    for pid in ids:
        rows = _bounded(mapping.get(pid, ()), f'Availability for {pid}')
        if any(not isinstance(w, Window) for w in rows):
            raise WindowError('Call normalize_windows before passing availability to slot search.')
        # Re-merge without the source-row span cap: a normalized result may be
        # longer than 31 days due to legitimate adjacent source windows.
        merged = []
        for w in sorted(rows):
            if merged and w.start <= merged[-1].end:
                merged[-1] = Window(merged[-1].start, max(merged[-1].end, w.end))
            else:
                merged.append(w)
        result[pid] = tuple(merged)
    return result


def _busy(rows: Iterable[BusyBooking], exclude_booking_id: str | None) -> tuple[BusyBooking, ...]:
    if exclude_booking_id is not None:
        _identifier(exclude_booking_id, 'Excluded booking ID')
    entries = _bounded(rows, 'Busy bookings')
    ids = set()
    for booking in entries:
        if not isinstance(booking, BusyBooking):
            raise WindowError('Busy entries must be BusyBooking values.')
        if booking.booking_id in ids:
            raise WindowError('Duplicate busy booking ID: supply one current record per booking.')
        ids.add(booking.booking_id)
    return tuple(b for b in entries if b.booking_id != exclude_booking_id)


def _conflicts(availability, ids, window, busy) -> list[dict[str, str]]:
    found = []
    for pid in ids:
        if not any(w.start <= window.start and window.end <= w.end for w in availability[pid]):
            found.append({'kind': 'unavailable', 'participant_id': pid})
        if any(pid in b.participant_ids and window.start < b.window.end and b.window.start < window.end for b in busy):
            # Deliberately omit another interview's ID, candidate name, title,
            # email, location and other participant identities from the result.
            found.append({'kind': 'busy', 'participant_id': pid})
    return found


def slot_conflicts(availability: Mapping[str, Iterable[Window]], participant_ids: Sequence[str],
                   window: Window, busy: Iterable[BusyBooking] = (), *,
                   exclude_booking_id: str | None = None) -> list[dict[str, str]]:
    """Validate one proposed slot; use again inside the caller's transaction."""
    if not isinstance(window, Window):
        raise WindowError('Proposed slot must be a Window.')
    ids = _participants(participant_ids)
    return _conflicts(_availability(availability, ids), ids, window, _busy(busy, exclude_booking_id))


def _intersect(left: tuple[Window, ...], right: tuple[Window, ...]) -> tuple[Window, ...]:
    i = j = 0
    out = []
    while i < len(left) and j < len(right):
        a, b = max(left[i].start, right[j].start), min(left[i].end, right[j].end)
        if a < b:
            out.append(Window(a, b))
        if left[i].end <= right[j].end:
            i += 1
        else:
            j += 1
    return tuple(out)


def _subtract(windows: tuple[Window, ...], occupied: Window) -> tuple[Window, ...]:
    out = []
    for w in windows:
        if occupied.end <= w.start or occupied.start >= w.end:
            out.append(w)
        else:
            if w.start < occupied.start:
                out.append(Window(w.start, occupied.start))
            if occupied.end < w.end:
                out.append(Window(occupied.end, w.end))
    return tuple(out)


def suggest_slots(availability: Mapping[str, Iterable[Window]], participant_ids: Sequence[str],
                  search: Window, duration_minutes: int, busy: Iterable[BusyBooking] = (), *,
                  exclude_booking_id: str | None = None, grid_minutes: int = 15,
                  limit: int = 100) -> tuple[Window, ...]:
    """Intersect all participants, subtract shared bookings, enumerate UTC grid.

    Empty/missing availability produces no slot. Ranges are half-open [start,end):
    adjacent bookings do not conflict. Returned slots are suggestions, not holds.
    No clock is consulted: callers clip search.start to their current clock.
    """
    if not isinstance(search, Window) or search.end-search.start > MAX_SPAN:
        raise WindowError('Search must be a positive Window of no more than 31 days.')
    _integer(duration_minutes, 'Duration', 1, 1440)
    _integer(grid_minutes, 'Grid minutes', 1, 1440)
    _integer(limit, 'Result limit', 1, 10000)
    ids = _participants(participant_ids)
    normalized = _availability(availability, ids)
    busy_rows = _busy(busy, exclude_booking_id)
    free = (search,)
    for pid in ids:
        free = _intersect(free, normalized[pid])
    id_set = set(ids)
    for b in busy_rows:
        if id_set.intersection(b.participant_ids):
            free = _subtract(free, b.window)
    result = []
    duration = timedelta(minutes=duration_minutes)
    grid = timedelta(minutes=grid_minutes)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    grid_seconds = grid_minutes * 60
    for w in free:
        seconds = (w.start-epoch) // timedelta(seconds=1)
        ticks = -(-seconds // grid_seconds)  # ceiling division, including pre-epoch dates
        try:
            cursor = epoch + ticks*grid
        except OverflowError:
            continue  # Ceiling lies beyond the datetime range: no grid point in this window.
        while cursor < w.end and w.end-cursor >= duration:
            result.append(Window(cursor, cursor+duration))
            if len(result) >= limit:
                return tuple(result)
            try:
                cursor += grid
            except OverflowError:
                break
    return tuple(result)


def from_request(request: dict) -> dict:
    """JSON adapter for CLI/native consumers; contains no contact information."""
    if not isinstance(request, dict):
        raise WindowError('Request must be a JSON object.')
    ids = _participants(request.get('participants', ()))
    zones = request.get('timezones', {})
    raw = request.get('availability', {})
    if not isinstance(zones, dict) or not isinstance(raw, dict):
        raise WindowError('Timezones and availability must be objects keyed by participant ID.')
    avail = {pid: normalize_windows(raw.get(pid, []), zones.get(pid)) for pid in ids}
    query = request.get('search')
    if not isinstance(query, dict):
        raise WindowError('Search needs start and end with explicit UTC offsets.')
    search = Window(resolve_time(query.get('start')), resolve_time(query.get('end')))
    busy = []
    for row in _bounded(request.get('busy', []), 'Busy bookings'):
        if not isinstance(row, dict):
            raise WindowError('Each busy booking must be an object.')
        busy.append(BusyBooking(row.get('id'), row.get('participants'), Window(resolve_time(row.get('start')), resolve_time(row.get('end')))))
    found = suggest_slots(avail, ids, search, request.get('duration_minutes'), busy,
        exclude_booking_id=request.get('exclude_booking_id'), grid_minutes=request.get('grid_minutes',15),
        limit=request.get('limit',100))
    return {'slots':[w.to_dict() for w in found], 'slot_count':len(found), 'booking_created':False,
            'messages_sent':False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('request', type=Path, help='UTF-8 JSON input; examples contain synthetic IDs only')
    p.add_argument('--output', type=Path, help='Write JSON to a new file, or stdout when omitted')
    args = p.parse_args(argv)
    try:
        with args.request.open('r', encoding='utf-8') as f:
            raw = f.read(2*1024*1024+1)
        if len(raw.encode('utf-8')) > 2*1024*1024:
            raise WindowError('JSON input exceeds 2 MiB.')
        def bad_constant(value):
            raise WindowError(f'Non-finite JSON number {value} is invalid.')
        result = from_request(json.loads(raw, parse_constant=bad_constant))
        content = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)+'\n'
        if args.output:
            with args.output.open('x', encoding='utf-8') as f:
                f.write(content)
        else:
            print(content, end='')
        return 0
    except (WindowError, json.JSONDecodeError, UnicodeError, OSError) as e:
        p.exit(2, f'Input not processed: {e}\n')

if __name__ == '__main__':
    raise SystemExit(main())
