#!/usr/bin/env python3
"""Strict three-layer activation census for Commons findings (visibility D5)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

VERSION = 1
LAYERS = ("detector_hits", "candidate_callbacks", "realized_actions")
LAYER_STATES = ("MEASURED", "UNKNOWN", "NOT_SEARCHED")
_ALLOWED_FINDING = frozenset({"id", "canonical_parent", "evidence", *LAYERS})
_ALLOWED_LAYER = frozenset({"state", "count", "search_space"})


class FindingError(ValueError):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": False, "error": self.code, "message": str(self)}
        if self.details:
            out["details"] = self.details
        return out


def _text(value: Any, field: str, finding_id: str | None = None) -> str:
    if type(value) is not str or not value.strip():
        raise FindingError("INVALID_FIELD", f"{field} must be a non-empty string", finding=finding_id, field=field)
    return value.strip()


def _layer(raw: Any, layer: str, finding_id: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != _ALLOWED_LAYER:
        keys = sorted(raw) if isinstance(raw, dict) else None
        raise FindingError(
            "INVALID_LAYER",
            "activation layer must contain exactly state, count and search_space",
            finding=finding_id,
            layer=layer,
            keys=keys,
        )
    state = raw["state"]
    if type(state) is not str or state not in LAYER_STATES:
        raise FindingError(
            "INVALID_LAYER_STATE",
            "state must be exactly MEASURED, UNKNOWN or NOT_SEARCHED",
            finding=finding_id,
            layer=layer,
            state=state,
        )
    count = raw["count"]
    if state == "MEASURED":
        if type(count) is not int or count < 0:
            raise FindingError(
                "INVALID_COUNT",
                "MEASURED count must be a non-negative exact integer",
                finding=finding_id,
                layer=layer,
            )
    elif count is not None:
        raise FindingError(
            "INVALID_COUNT",
            f"{state} count must be null",
            finding=finding_id,
            layer=layer,
        )
    search_space = _text(raw["search_space"], f"{layer}.search_space", finding_id)
    return {"state": state, "count": count, "search_space": search_space}


def load_registry(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or set(payload) != {"version", "findings"}:
        raise FindingError("INVALID_REGISTRY", "registry must contain exactly version and findings")
    if type(payload["version"]) is not int or payload["version"] != VERSION:
        raise FindingError("UNSUPPORTED_VERSION", "registry version must be exact integer 1")
    if type(payload["findings"]) is not list:
        raise FindingError("INVALID_FINDINGS", "findings must be a list")

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for raw in payload["findings"]:
        if not isinstance(raw, dict):
            raise FindingError("INVALID_FINDING", "finding row must be an object")
        extra = sorted(set(raw) - _ALLOWED_FINDING)
        missing = sorted(_ALLOWED_FINDING - set(raw))
        if extra or missing:
            raise FindingError(
                "INVALID_FINDING_FIELDS",
                "finding row must carry id, parent, evidence and all three census layers",
                extra=extra,
                missing=missing,
            )
        finding_id = _text(raw["id"], "id")
        if finding_id in seen:
            raise FindingError("DUPLICATE_FINDING", "finding id appears more than once", finding=finding_id)
        seen.add(finding_id)
        item: dict[str, Any] = {
            "id": finding_id,
            "canonical_parent": _text(raw["canonical_parent"], "canonical_parent", finding_id),
            "evidence": _text(raw["evidence"], "evidence", finding_id),
        }
        for layer in LAYERS:
            item[layer] = _layer(raw[layer], layer, finding_id)
        out.append(item)
    return sorted(out, key=lambda item: item["id"])


def summarize(findings: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in findings:
        states = {layer: item[layer]["state"] for layer in LAYERS}
        counts = {layer: item[layer]["count"] for layer in LAYERS}
        unknown = [layer for layer in LAYERS if states[layer] == "UNKNOWN"]
        not_searched = [layer for layer in LAYERS if states[layer] == "NOT_SEARCHED"]
        zero = [layer for layer in LAYERS if states[layer] == "MEASURED" and counts[layer] == 0]
        rows.append(
            {
                **item,
                "complete_census": all(states[layer] == "MEASURED" for layer in LAYERS),
                "unknown_layers": unknown,
                "not_searched_layers": not_searched,
                "zero_layers": zero,
            }
        )
    return {
        "version": VERSION,
        "findings": rows,
        "counts": {
            "findings": len(rows),
            "complete": sum(1 for row in rows if row["complete_census"]),
            "incomplete": sum(1 for row in rows if not row["complete_census"]),
        },
    }


def read_registry(path: str) -> list[dict[str, Any]]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FindingError("INVALID_JSON", "registry is not strict JSON", line=exc.lineno, column=exc.colno) from exc
    return load_registry(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", help="registry JSON path, or - for stdin")
    parser.add_argument("--finding", help="emit one exact finding id")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = summarize(read_registry(args.registry))
        if args.finding:
            row = next((row for row in output["findings"] if row["id"] == args.finding), None)
            if row is None:
                raise FindingError("FINDING_NOT_FOUND", "finding id is not registered", finding=args.finding)
            output = {"version": VERSION, "finding": row}
    except (FindingError, OSError) as exc:
        result = exc.as_dict() if isinstance(exc, FindingError) else {"ok": False, "error": "IO_ERROR", "message": str(exc)}
        json.dump(result, sys.stdout, sort_keys=True, indent=2 if args.pretty else None)
        sys.stdout.write("\n")
        return 2
    output["ok"] = True
    json.dump(output, sys.stdout, sort_keys=True, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
