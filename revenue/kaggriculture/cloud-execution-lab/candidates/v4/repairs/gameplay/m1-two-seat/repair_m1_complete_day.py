#!/usr/bin/env python3
"""Support-only M1 complete-day funding-custody repair for fb1 helper bytes.

Input must be exact server blob d4d068d62ffc8fcd25842193bc7031f764630262.
The repair only tightens `_future_literal_pickup`: a same-day pickup/cash theorem
requires frozen tape coverage through the literal end of that day.  No new
mechanism, key, economics, ancestry, or public surface is introduced.
"""
from pathlib import Path
import subprocess
import sys

EXPECTED_HELPER_BLOB = "d4d068d62ffc8fcd25842193bc7031f764630262"

OLD = '''    if not isinstance(tape, (list, tuple)) or len(tape) <= step + LOOKAHEAD_MIN:\n        return None, 0\n\n    day_end = min(len(tape) - 1, (step // 24 + 1) * 24 - 1)\n'''

NEW = '''    if not isinstance(tape, (list, tuple)) or len(tape) <= step + LOOKAHEAD_MIN:\n        return None, 0\n\n    # Funding custody extends through the rest of this day.  A truncated frozen\n    # tape cannot prove that omitted same-day steps contain no HIRE/BUY cash owner.\n    expected_day_end = (step // 24 + 1) * 24 - 1\n    if len(tape) <= expected_day_end:\n        return None, 0\n    day_end = expected_day_end\n'''


def git_blob(path: Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()


def repair(text: str) -> str:
    if "expected_day_end = (step // 24 + 1) * 24 - 1" in text:
        raise RuntimeError("complete-day custody repair already present")
    count = text.count(OLD)
    if count != 1:
        raise RuntimeError(f"expected exactly one funding-horizon anchor, found {count}")
    out = text.replace(OLD, NEW, 1)
    if out.count("expected_day_end = (step // 24 + 1) * 24 - 1") != 1:
        raise RuntimeError("postcondition: expected_day_end guard missing/duplicated")
    if "day_end = min(len(tape) - 1" in out:
        raise RuntimeError("postcondition: truncated-day min authority survived")
    return out


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: repair_m1_complete_day.py path/to/r04_m1_wheat_trade.py")
    path = Path(sys.argv[1])
    if git_blob(path) != EXPECTED_HELPER_BLOB:
        raise SystemExit("wrong M1 helper authority; re-CAS repair before use")
    text = path.read_text(encoding="utf-8")
    path.write_text(repair(text), encoding="utf-8", newline="")


if __name__ == "__main__":
    main()
