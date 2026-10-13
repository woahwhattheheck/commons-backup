"""Stdin/stdout driver for one isolated current-authority operation."""
from __future__ import annotations

import json
import sys
from typing import Any

from .core import PortfolioError
from .fresh_exec import WORKER_LIMIT
from .fresh_worker_ops import compile_operation, verify_operation


def read_request() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(WORKER_LIMIT + 1)
    if len(raw) > WORKER_LIMIT:
        raise PortfolioError("worker request exceeds byte bound")
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PortfolioError("worker request is invalid JSON") from exc
    if type(value) is not dict:
        raise PortfolioError("worker request must be an object")
    return value


def write_response(value: dict[str, Any]) -> None:
    raw = (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    if len(raw) > WORKER_LIMIT:
        raise PortfolioError("worker response exceeds byte bound")
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def main() -> int:
    try:
        request = read_request()
        action = request.get("action")
        if action == "compile":
            response = compile_operation(request)
        elif action == "verify":
            response = verify_operation(request)
        else:
            raise PortfolioError("worker action must be compile or verify")
        write_response(response)
        return 0
    except (PortfolioError, OSError, TypeError, ValueError) as exc:
        write_response({"ok": False, "error": str(exc) or type(exc).__name__})
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
