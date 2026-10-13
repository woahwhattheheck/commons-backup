#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reproduce the exact H3c repair and its negative control; no package build.

Run from any directory with normal Python or python -O. The checker authenticates
both source blobs before executing them in isolated temporary test directories.
Its JSON output is source evidence, never a gameplay-promotion decision.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HELPER = "h3c_goose_eod_cap_rescue.py"
TEST = "test_v4_h3c_market_prefix.py"
PREIMAGE = "2044d6cf1e0c51f95027229863f910aa43ac7008"
POSTIMAGE = "79c3fd029054a2db5931609db06f6b9aa4d4be3c"
TEST_BLOB = "c24bd784a43267f84071d2c293c10fe57f30a1da"
RUNNER = r'''
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, sys.argv[1])
suite = unittest.defaultTestLoader.discover(str(Path(sys.argv[1]) / "checks"), pattern="test_v4_h3c_market_prefix.py")
result = unittest.TextTestRunner(verbosity=0).run(suite)
print(json.dumps({"tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped), "expected_failures": len(result.expectedFailures), "unexpected_successes": len(result.unexpectedSuccesses)}, sort_keys=True))
sys.exit(0 if result.wasSuccessful() else 1)
'''


class VerificationError(RuntimeError):
    """A pinned source or observed execution result differs from the contract."""


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def authenticated(path: Path, expected: str) -> bytes:
    require(not path.is_symlink() and path.is_file(), f"not a regular source file: {path}")
    data = path.read_bytes()
    require(git_blob(data) == expected, f"source drift: {path}")
    compile(data, str(path), "exec")
    return data


def replace_once(data: bytes, old: bytes, new: bytes) -> bytes:
    require(data.count(old) == 1, "reverse repair anchor is not unique")
    return data.replace(old, new, 1)


def original_source(postimage: bytes) -> bytes:
    original = replace_once(postimage,
        b"worker has another non-PASS command on that same animal,",
        b"worker has another non-PASS command on the same animal,")
    original = replace_once(original,
        b'    # The standard engine executes ten raw slots, not ten nonempty rows.\n'
        b'    # A capped suffix cannot add shed inflow; keep it untouched in the action.\n'
        b'    for order in market[:STANDARD_CONFIG["maxMarketOrdersPerTurn"]]:\n',
        b'    for order in market:\n')
    require(git_blob(original) == PREIMAGE, "reconstructed predecessor blob differs")
    compile(original, "authenticated_h3c_preimage", "exec")
    return original


def run_case(helper: bytes, test: bytes, *, optimized: bool, negative: bool) -> dict:
    with tempfile.TemporaryDirectory(prefix="titan-h3c-source-") as temporary:
        root = Path(temporary)
        (root / "checks").mkdir()
        (root / HELPER).write_bytes(helper)
        (root / "checks" / TEST).write_bytes(test)
        command = [sys.executable, "-I", "-B"]
        if optimized:
            command.append("-O")
        command.extend(["-c", RUNNER, str(root)])
        completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
        try:
            observed = json.loads(completed.stdout)
        except (ValueError, TypeError) as error:
            raise VerificationError("test runner produced no valid single result") from error
        expected = {"tests": 15, "failures": 24 if negative else 0, "errors": 0,
                    "skipped": 0, "expected_failures": 0, "unexpected_successes": 0}
        require(completed.returncode == (1 if negative else 0),
                f"unexpected test exit {completed.returncode}: {completed.stderr}")
        require(observed == expected, f"test result drift: {observed!r}")
        return {"optimized": optimized, "exit_code": completed.returncode, **observed}


def verify() -> dict:
    workspace = Path(__file__).resolve().parents[3]
    overlay = workspace / "donor" / "overlay"
    helper = authenticated(overlay / HELPER, POSTIMAGE)
    test = authenticated(overlay / "checks" / TEST, TEST_BLOB)
    original = original_source(helper)
    return {
        "schema_version": 1,
        "scope": "SOURCE_ONLY_NOT_PRODUCTION_PROMOTION",
        "helper_blob": POSTIMAGE,
        "test_blob": TEST_BLOB,
        "preimage_blob": PREIMAGE,
        "positive_controls": [run_case(helper, test, optimized=o, negative=False) for o in (False, True)],
        "negative_controls": [run_case(original, test, optimized=o, negative=True) for o in (False, True)],
        "production_archive_changed": False,
    }


def main() -> int:
    try:
        report = verify()
    except (VerificationError, OSError, subprocess.TimeoutExpired) as error:
        print(f"H3c source verification failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
