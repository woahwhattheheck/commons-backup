#!/usr/bin/env python3
"""Strict needs-runner / needs-owner queue reducer (visibility F3 + F4).

Runner rows name the exact work, required runner capabilities, canonical packet,
one designated result publisher, and return slot. Owner rows name the exact
authenticated owner action, canonical packet, and return slot. Results are
append-only events. A first SUCCESS retires a row; later events remain audit
history and cannot replace the first-success receipt.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

VERSION = 1
_ITEM_KINDS = frozenset({"runner", "owner"})
_EVENT_STATUSES = frozenset({"SUCCESS", "FAILED"})
_COMMON_ITEM_KEYS = frozenset({"id", "kind", "canonical_packet", "return_slot"})
_RUNNER_ITEM_KEYS = _COMMON_ITEM_KEYS | frozenset({"task", "required_capabilities", "publisher"})
_OWNER_ITEM_KEYS = _COMMON_ITEM_KEYS | frozenset({"owner_action"})
_EVENT_KEYS = frozenset({"seq", "event_id", "item_id", "actor", "status", "receipt"})


class NeedsQueueError(ValueError):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": False, "error": self.code, "message": str(self)}
        if self.details:
            out["details"] = self.details
        return out


def _text(value: Any, field: str, item_id: str | None = None) -> str:
    if type(value) is not str or not value.strip():
        raise NeedsQueueError(
            "INVALID_FIELD",
            f"{field} must be a non-empty string",
            field=field,
            item=item_id,
        )
    return value.strip()


def _capabilities(raw: Any, item_id: str) -> list[str]:
    if type(raw) is not list or not raw:
        raise NeedsQueueError(
            "INVALID_CAPABILITIES",
            "required_capabilities must be a non-empty list",
            item=item_id,
        )
    values = [_text(value, "required_capabilities", item_id) for value in raw]
    if len(values) != len(set(values)):
        raise NeedsQueueError(
            "DUPLICATE_CAPABILITY",
            "required_capabilities contains duplicate values",
            item=item_id,
        )
    return values


def _parse_item(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise NeedsQueueError("INVALID_ITEM", "queue item must be an object")
    kind = raw.get("kind")
    if kind not in _ITEM_KINDS:
        raise NeedsQueueError("INVALID_KIND", "item kind must be runner or owner", kind=kind)

    expected = _RUNNER_ITEM_KEYS if kind == "runner" else _OWNER_ITEM_KEYS
    extra = sorted(set(raw) - expected)
    missing = sorted(expected - set(raw))
    if extra or missing:
        raise NeedsQueueError(
            "INVALID_ITEM_FIELDS",
            "item fields do not match the selected queue kind",
            kind=kind,
            extra=extra,
            missing=missing,
        )

    item_id = _text(raw["id"], "id")
    parsed: dict[str, Any] = {
        "id": item_id,
        "kind": kind,
        "canonical_packet": _text(raw["canonical_packet"], "canonical_packet", item_id),
        "return_slot": _text(raw["return_slot"], "return_slot", item_id),
    }
    if kind == "runner":
        parsed.update(
            {
                "task": _text(raw["task"], "task", item_id),
                "required_capabilities": _capabilities(raw["required_capabilities"], item_id),
                "publisher": _text(raw["publisher"], "publisher", item_id),
            }
        )
    else:
        parsed["owner_action"] = _text(raw["owner_action"], "owner_action", item_id)
    return parsed


def load_registry(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != {"version", "items", "events"}:
        raise NeedsQueueError(
            "INVALID_REGISTRY",
            "registry must contain exactly version, items, and events",
        )
    if type(payload["version"]) is not int or payload["version"] != VERSION:
        raise NeedsQueueError(
            "UNSUPPORTED_VERSION",
            "registry version must be the exact integer 1",
            version=payload.get("version"),
        )
    if type(payload["items"]) is not list:
        raise NeedsQueueError("INVALID_ITEMS", "items must be a list")
    if type(payload["events"]) is not list:
        raise NeedsQueueError("INVALID_EVENTS", "events must be a list")

    items: dict[str, dict[str, Any]] = {}
    for raw in payload["items"]:
        item = _parse_item(raw)
        if item["id"] in items:
            raise NeedsQueueError(
                "DUPLICATE_ITEM",
                "queue item id appears more than once",
                item=item["id"],
            )
        items[item["id"]] = item

    events: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    seen_sequences: set[int] = set()
    previous_sequence = -1
    for raw in payload["events"]:
        if not isinstance(raw, dict) or set(raw) != _EVENT_KEYS:
            keys = sorted(raw) if isinstance(raw, dict) else None
            raise NeedsQueueError(
                "INVALID_EVENT",
                "event must contain exactly seq, event_id, item_id, actor, status, and receipt",
                keys=keys,
            )

        sequence = raw["seq"]
        if type(sequence) is not int or sequence < 0:
            raise NeedsQueueError(
                "INVALID_SEQUENCE",
                "event seq must be a non-negative exact integer",
                seq=sequence,
            )
        if sequence in seen_sequences:
            raise NeedsQueueError(
                "DUPLICATE_SEQUENCE",
                "event seq appears more than once",
                seq=sequence,
            )
        if sequence <= previous_sequence:
            raise NeedsQueueError(
                "NON_APPEND_ORDER",
                "events must be supplied in strictly increasing seq order",
                seq=sequence,
                previous=previous_sequence,
            )
        seen_sequences.add(sequence)
        previous_sequence = sequence

        event_id = _text(raw["event_id"], "event_id")
        if event_id in seen_event_ids:
            raise NeedsQueueError(
                "DUPLICATE_EVENT",
                "event_id appears more than once",
                event_id=event_id,
            )
        seen_event_ids.add(event_id)

        item_id = _text(raw["item_id"], "item_id")
        if item_id not in items:
            raise NeedsQueueError(
                "UNKNOWN_ITEM",
                "event references an item absent from this queue",
                item=item_id,
            )
        actor = _text(raw["actor"], "actor", item_id)
        status = _text(raw["status"], "status", item_id).upper()
        if status not in _EVENT_STATUSES:
            raise NeedsQueueError(
                "INVALID_EVENT_STATUS",
                "event status must be SUCCESS or FAILED",
                item=item_id,
                status=status,
            )
        receipt = _text(raw["receipt"], "receipt", item_id)

        item = items[item_id]
        if item["kind"] == "runner" and actor != item["publisher"]:
            raise NeedsQueueError(
                "WRONG_PUBLISHER",
                "runner result was not published by the row's designated publisher",
                item=item_id,
                expected=item["publisher"],
                actual=actor,
            )

        events.append(
            {
                "seq": sequence,
                "event_id": event_id,
                "item_id": item_id,
                "actor": actor,
                "status": status,
                "receipt": receipt,
            }
        )

    return {
        "version": VERSION,
        "items": [items[item_id] for item_id in sorted(items)],
        "events": events,
    }


def reduce_registry(registry: dict[str, Any]) -> dict[str, Any]:
    by_item = {item["id"]: item for item in registry["items"]}
    histories: dict[str, list[dict[str, Any]]] = {item_id: [] for item_id in by_item}
    for event in registry["events"]:
        histories[event["item_id"]].append(event)

    rendered: list[dict[str, Any]] = []
    for item_id in sorted(by_item):
        item = by_item[item_id]
        history = histories[item_id]
        first_success = next(
            (event for event in history if event["status"] == "SUCCESS"),
            None,
        )
        after_retirement = (
            [event for event in history if event["seq"] > first_success["seq"]]
            if first_success is not None
            else []
        )
        rendered.append(
            {
                **item,
                "state": "RETIRED" if first_success is not None else "OPEN",
                "first_success": first_success,
                "attempts": len(history),
                "failed_attempts": sum(
                    1 for event in history if event["status"] == "FAILED"
                ),
                "events_after_retirement": after_retirement,
            }
        )

    return {
        "version": VERSION,
        "items": rendered,
        "counts": {
            "open": sum(1 for item in rendered if item["state"] == "OPEN"),
            "retired": sum(1 for item in rendered if item["state"] == "RETIRED"),
            "needs_runner_open": sum(
                1
                for item in rendered
                if item["kind"] == "runner" and item["state"] == "OPEN"
            ),
            "needs_owner_open": sum(
                1
                for item in rendered
                if item["kind"] == "owner" and item["state"] == "OPEN"
            ),
        },
    }


def read_registry(path: str) -> dict[str, Any]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NeedsQueueError(
            "INVALID_JSON",
            "queue registry is not strict JSON",
            line=exc.lineno,
            column=exc.colno,
        ) from exc
    return load_registry(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", help="queue registry JSON path, or - for stdin")
    parser.add_argument("--item", help="emit one exact queue item id")
    parser.add_argument(
        "--open-kind",
        choices=("runner", "owner"),
        help="emit only OPEN items of one queue kind",
    )
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)

    try:
        output = reduce_registry(read_registry(args.registry))
        if args.item and args.open_kind:
            raise NeedsQueueError(
                "INVALID_QUERY",
                "choose at most one of --item and --open-kind",
            )
        if args.item:
            item = next(
                (row for row in output["items"] if row["id"] == args.item),
                None,
            )
            if item is None:
                raise NeedsQueueError(
                    "ITEM_NOT_FOUND",
                    "queue item id is not registered",
                    item=args.item,
                )
            output = {"version": VERSION, "item": item}
        elif args.open_kind:
            output = {
                "version": VERSION,
                "kind": args.open_kind,
                "items": [
                    row
                    for row in output["items"]
                    if row["kind"] == args.open_kind and row["state"] == "OPEN"
                ],
            }
    except (NeedsQueueError, OSError) as exc:
        result = (
            exc.as_dict()
            if isinstance(exc, NeedsQueueError)
            else {"ok": False, "error": "IO_ERROR", "message": str(exc)}
        )
        json.dump(result, sys.stdout, sort_keys=True, indent=2 if args.pretty else None)
        sys.stdout.write("\n")
        return 2

    output["ok"] = True
    json.dump(output, sys.stdout, sort_keys=True, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
