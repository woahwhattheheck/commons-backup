#!/usr/bin/env python3
"""Replay three retained CLI canaries against the exact original time-window source."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def replay(runtime: Path, fixtures: Path) -> dict:
    document = json.loads(fixtures.read_text(encoding="utf-8"))
    source_sha = hashlib.sha256(runtime.read_bytes()).hexdigest()
    if source_sha != document["runtime_sha256"]:
        raise ValueError("Runtime changed; these fixtures are pinned to the original source.")
    results = []
    with tempfile.TemporaryDirectory(prefix="panel-time-canary-") as temporary:
        request = Path(temporary) / "request.json"
        for case in document["fixtures"]:
            request.write_text(json.dumps(case["request"]), encoding="utf-8")
            process = subprocess.run(
                [sys.executable, "-B", str(runtime.resolve()), str(request)],
                capture_output=True, text=True, timeout=15, check=False,
            )
            if process.returncode:
                raise ValueError(f"CLI failed for {case['name']}: {process.stderr.strip()}")
            actual = json.loads(process.stdout)
            if actual != case["expected"]:
                raise ValueError(f"CLI output differs for {case['name']}.")
            results.append({"name": case["name"], "slot_count": actual["slot_count"], "matched": True})
    return {"runtime_sha256": source_sha, "results": results, "booking_created": False,
            "messages_sent": False, "native_application_tested": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path,
                        default=Path(__file__).resolve().parents[2] / "panel_time_windows.py")
    parser.add_argument("--fixtures", type=Path,
                        default=Path(__file__).with_name("cli-fixtures.json"))
    args = parser.parse_args()
    try:
        result = replay(args.runtime, args.fixtures)
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        print(f"canary: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
