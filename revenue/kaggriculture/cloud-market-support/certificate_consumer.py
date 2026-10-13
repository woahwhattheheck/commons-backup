# SPDX-License-Identifier: Apache-2.0
"""Independent consumer checks for POLY finite-table certificates; no optimizer.

This verifies supplied numbers and their table binding. It does not certify
plan feasibility, observed fills, future scenarios, or whole-game strength.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from typing import Any, Iterable


def _number(value: Any) -> Fraction:
    if isinstance(value, bool):
        raise ValueError("Boolean values are not rational receipts")
    try:
        return Fraction(str(value)) if isinstance(value, float) else Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError("Expected finite rational receipts") from exc


def _table(deltas: Iterable[Iterable[Any]]) -> tuple[tuple[Fraction, ...], ...]:
    rows = tuple(tuple(_number(x) for x in row) for row in deltas)
    if not 1 <= len(rows) <= 9 or not 1 <= len(rows[0]) <= 32:
        raise ValueError("Expected 1..9 plans and 1..32 streams")
    if any(len(row) != len(rows[0]) for row in rows) or any(rows[0]):
        raise ValueError("Expected a rectangular table with the original zero baseline")
    return rows


def table_digest(deltas: Iterable[Iterable[Any]]) -> str:
    """Canonical POLY table identity, retaining original row and column order."""
    rows = _table(deltas)
    encoded = json.dumps([[str(x) for x in row] for row in rows],
                         separators=(",", ":")).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def check_certificate(deltas: Iterable[Iterable[Any]], solution: dict[str, Any]) -> dict[str, Any]:
    """Check exact bounds and the provider's completion/baseline contract.

    A feasible row mixture proves min_j sum_i p_i D_ij as a lower bound.
    A feasible column mixture proves max_i sum_j q_j D_ij as an upper bound.
    Equality proves the finite-table optimum. It does not turn a computation
    limit into a completed provider run: bounds_closed and completed remain
    separate. positive_optimum is true only for a valid, completed, positive
    exact result. It is NOT an own-plan feasibility or promotion verdict.

    No provider verifier, policy, sampling function, or simplex is imported.
    The provider's certificate_valid flag is deliberately not trusted.
    """
    try:
        rows = _table(deltas)
        p = tuple(_number(x) for x in solution["weights"])
        q = tuple(_number(x) for x in solution["dual_weights"])
        if len(p) != len(rows) or len(q) != len(rows[0]):
            raise ValueError("Weight dimensions differ from the complete input table")
        if any(x < 0 for x in p+q) or sum(p) != 1 or sum(q) != 1:
            raise ValueError("Both mixtures must be normalized and nonnegative")
        digest = table_digest(rows)
        if solution["table_sha256"] != digest:
            raise ValueError("Certificate belongs to a different ordered table")
        columns = tuple(sum((p[i]*rows[i][j] for i in range(len(rows))), Fraction(0))
                        for j in range(len(rows[0])))
        dual_rows = tuple(sum((q[j]*row[j] for j in range(len(q))), Fraction(0))
                         for row in rows)
        lower, upper = min(columns), max(dual_rows)
        if lower < 0 or upper < lower:
            raise ValueError("Bounds do not preserve the zero-baseline guarantee")
        if (_number(solution["value"]), _number(solution["upper_bound"]),
                _number(solution["gap"])) != (lower, upper, upper-lower):
            raise ValueError("Recorded bounds/gap differ from independent expectations")
        if tuple(map(_number, solution["column_expectations"])) != columns:
            raise ValueError("Recorded column expectations differ")
        if tuple(map(_number, solution["row_expectations_under_dual"])) != dual_rows:
            raise ValueError("Recorded dual row expectations differ")
        if tuple(map(_number, solution["pure_minima"])) != tuple(min(row) for row in rows):
            raise ValueError("Recorded pure minima differ")
        support = [i for i, weight in enumerate(p) if weight]
        reported = solution["support"]
        if not isinstance(reported, list) or any(type(i) is not int for i in reported) or reported != support:
            raise ValueError("Support does not retain the original nonzero row indices")
        status = solution["status"]
        if status not in ("optimal", "pivot_limit", "bit_limit"):
            raise ValueError("Unknown provider completion status")
        completed = status == "optimal"
        if completed and lower != upper:
            raise ValueError("Completed optimum requires equal exact bounds")
        if solution["exact"] is not (completed and lower == upper):
            raise ValueError("Exact flag disagrees with provider completion and bounds")
        if solution["arithmetic_exact"] is not True:
            raise ValueError("Expected exact rational arithmetic metadata")
        baseline = (Fraction(1),) + (Fraction(0),)*(len(rows)-1)
        if (not completed or lower == 0) and p != baseline:
            raise ValueError("Budget limits and zero-value ties must retain the baseline")
        for key, minimum, maximum in (("max_pivots", 0, 4096), ("max_bits", 16, 4096)):
            if type(solution[key]) is not int or not minimum <= solution[key] <= maximum:
                raise ValueError("Invalid provider computation-limit metadata")
        if type(solution["pivots"]) is not int or not 0 <= solution["pivots"] <= solution["max_pivots"]:
            raise ValueError("Pivot count exceeds the declared computation limit")
        if type(solution["alpha"]) is not int or solution["alpha"] != 0 or solution["probabilities"] is not None:
            raise ValueError("Expected alpha zero and no calibrated scenario probabilities")
        return {"valid": True, "table_sha256": digest, "lower_bound": str(lower),
                "upper_bound": str(upper), "gap": str(upper-lower),
                "bounds_closed": lower == upper, "completed": completed,
                "positive_optimum": completed and lower > 0, "status": status,
                "support": support, "row_count": len(rows), "stream_count": len(q),
                "scope": "Supplied finite table and provider contract only"}
    except (KeyError, TypeError, ValueError, IndexError, OverflowError) as exc:
        return {"valid": False, "positive_optimum": False, "reason": str(exc),
                "scope": "Supplied finite table and provider contract only"}


def main() -> int:
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON object with deltas and solution")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        raw = args.input.read_bytes()
        envelope = json.loads(raw)
        result = check_certificate(envelope["deltas"], envelope["solution"])
        result["input_sha256"] = hashlib.sha256(raw).hexdigest()
        text = json.dumps(result, indent=2)+"\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return 0 if result["valid"] else 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"certificate input error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
