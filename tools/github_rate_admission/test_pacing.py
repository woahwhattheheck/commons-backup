#!/usr/bin/env python3
"""Focused deterministic regression for account/bucket admission pacing."""
from __future__ import annotations

import sqlite3

from admission import SCHEMA, acquire, settle


def main() -> None:
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.executescript(SCHEMA)

    first = acquire(
        db, "woahwhattheheck", "github-app", "search:one", "PACE-1", 1000,
        min_interval_seconds=3,
    )
    assert first["admitted"] is True
    assert settle(db, "PACE-1", "confirmed")["updated"] is True

    blocked = acquire(
        db, "woahwhattheheck", "github-app", "search:two", "PACE-2", 1002,
        min_interval_seconds=3,
    )
    assert blocked == {
        "admitted": False,
        "reason": "provider_pacing",
        "last_admit_epoch": 1000,
        "retry_at_epoch": 1003,
        "min_interval_seconds": 3,
    }

    boundary = acquire(
        db, "woahwhattheheck", "github-app", "search:two", "PACE-3", 1003,
        min_interval_seconds=3,
    )
    assert boundary["admitted"] is True
    assert settle(db, "PACE-3", "confirmed")["updated"] is True

    # Default pacing remains disabled for existing callers.
    immediate = acquire(
        db, "woahwhattheheck", "github-app", "search:three", "PACE-4", 1003,
    )
    assert immediate["admitted"] is True

    # A distinct provider bucket has independent pacing history.
    independent = acquire(
        db, "woahwhattheheck", "user-token", "search:four", "PACE-5", 1001,
        min_interval_seconds=3,
    )
    assert independent["admitted"] is True

    print("github_rate_admission pacing regression passed")


if __name__ == "__main__":
    main()
