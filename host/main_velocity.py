#!/usr/bin/env python3
"""Measure Commons main velocity from the local Git graph, without API paging."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess


WINDOWS = (("6h", "6 hours ago", 360), ("24h", "24 hours ago", 1440), ("7d", "7 days ago", 10080))


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ).stdout.strip()


def measure(target: str = "HEAD", high_velocity_per_hour: float = 30.0) -> dict:
    """Return exact local counts. Cost is one Git query per time window."""
    # Git commit dates have whole-second precision. Freeze the clock once so
    # every window and the receipt describe the same measurement instant.
    measured_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    head = _git("rev-parse", f"{target}^{{commit}}")
    windows = {}
    for label, _since, minutes in WINDOWS:
        since = (measured_at - dt.timedelta(minutes=minutes)).isoformat()
        # Commit timestamps need not follow parent order. Filter the full walk;
        # --since can stop at an old commit and hide newer-dated ancestors.
        count = int(_git("rev-list", "--count", f"--since-as-filter={since}",
                         f"--until={measured_at.isoformat()}", head) or "0")
        windows[label] = {
            "commits": count,
            "commits_per_minute": round(count / minutes, 4),
            "commits_per_hour": round(count * 60 / minutes, 2),
        }
    # Keep presentation rounding out of the threshold decision.
    per_hour = windows["24h"]["commits"] / 24
    return {
        "schema": "commons.main-velocity.v1",
        "measured_at": measured_at.isoformat(),
        "target": target,
        "head": head,
        "windows": windows,
        "high_velocity": per_hour >= high_velocity_per_hour,
        "high_velocity_threshold_per_hour": high_velocity_per_hour,
        "integration_mode": "coalesce_ranges" if per_hour >= high_velocity_per_hour else "range_batch",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default="HEAD")
    parser.add_argument("--high-velocity-per-hour", type=float, default=30.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = measure(args.target, args.high_velocity_per_hour)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        w = result["windows"]
        print(
            "head=%s 6h=%d 24h=%d 7d=%d mode=%s"
            % (result["head"], w["6h"]["commits"], w["24h"]["commits"], w["7d"]["commits"], result["integration_mode"])
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
