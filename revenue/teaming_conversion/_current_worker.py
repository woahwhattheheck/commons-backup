from __future__ import annotations

import marshal
import sys

from .common import (
    ControlError,
    MAX_JSON_BYTES,
    canonical_bytes,
    format_timestamp,
    require_timestamp,
)
from .control import CURRENT_MODE, _compile_at, _utc_now, parse_receipt_bytes
from .trusted_roots import load_current_roots_bytes

_MAX_WIRE_BYTES = 8 * MAX_JSON_BYTES


def _compile_current(candidate_bytes: bytes, evidence_bytes: bytes) -> dict:
    roots_bytes = load_current_roots_bytes()
    return _compile_at(
        candidate_bytes,
        evidence_bytes,
        roots_bytes,
        evaluated_at=_utc_now(),
        mode=CURRENT_MODE,
    )


def _verify_current(
    candidate_bytes: bytes,
    evidence_bytes: bytes,
    receipt_bytes: bytes,
) -> dict:
    receipt = parse_receipt_bytes(receipt_bytes)
    now = _utc_now()
    roots_bytes = load_current_roots_bytes()
    integrity_valid = False
    if receipt["mode"] == CURRENT_MODE:
        evaluated_at = require_timestamp(
            receipt["evaluated_at"], "receipt.evaluated_at"
        )
        rebuilt = _compile_at(
            candidate_bytes,
            evidence_bytes,
            roots_bytes,
            evaluated_at=evaluated_at,
            mode=CURRENT_MODE,
        )
        integrity_valid = canonical_bytes(rebuilt) == receipt_bytes
    current = _compile_at(
        candidate_bytes,
        evidence_bytes,
        roots_bytes,
        evaluated_at=now,
        mode=CURRENT_MODE,
    )
    receipt_valid_until = require_timestamp(
        receipt["current_valid_until"], "receipt.current_valid_until"
    )
    current_valid = (
        integrity_valid
        and now <= receipt_valid_until
        and current["decision_sha256"] == receipt["decision_sha256"]
    )
    return {
        "schema": "teaming-conversion-current-verification/v2",
        "verified_at": format_timestamp(now),
        "integrity_valid": integrity_valid,
        "current_valid": current_valid,
        "receipt_disposition": receipt["disposition"],
        "current_disposition": current["disposition"],
        "current_decision_sha256": current["decision_sha256"],
        "receipt_decision_sha256": receipt["decision_sha256"],
        "current_valid_until": current["current_valid_until"],
    }


def main() -> int:
    raw = sys.stdin.buffer.read(_MAX_WIRE_BYTES + 1)
    if len(raw) > _MAX_WIRE_BYTES:
        response = ("error", "CURRENT authority request is too large")
    else:
        try:
            request = marshal.loads(raw)
            if type(request) is not tuple or not request:
                raise ControlError("CURRENT authority request envelope is invalid")
            operation = request[0]
            if operation == "compile" and len(request) == 3:
                result = _compile_current(request[1], request[2])
            elif operation == "verify" and len(request) == 4:
                result = _verify_current(request[1], request[2], request[3])
            else:
                raise ControlError("CURRENT authority operation is invalid")
            response = ("ok", result)
        except Exception as exc:
            response = ("error", f"{type(exc).__name__}: {exc}")

    sys.stdout.buffer.write(marshal.dumps(response))
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
