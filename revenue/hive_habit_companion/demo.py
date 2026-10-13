#!/usr/bin/env python3
"""Create a clearly synthetic Paceboard workspace for local demonstration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from paceboard import Store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    store = Store(Path(args.db))
    first = store.mutate(
        "goal.create",
        "demo-goal-reading-v1",
        {
            "title": "Read for ten minutes",
            "intention": "Use a small reading ritual to leave work mode",
            "reminder_minutes": 60,
            "target_focus_minutes": 10,
        },
    )
    second = store.mutate(
        "goal.create",
        "demo-goal-walk-v1",
        {
            "title": "Take a screen-free walk",
            "intention": "Make room for a reset without measuring performance",
            "reminder_minutes": 0,
            "target_focus_minutes": 20,
        },
    )
    store.mutate(
        "checkin.record",
        "demo-checkin-pause-v1",
        {"goal_id": second["goal_id"], "kind": "PAUSED", "note": "Rain made today a pause day."},
    )
    store.mutate(
        "checkin.record",
        "demo-checkin-resume-v1",
        {"goal_id": second["goal_id"], "kind": "RESUMED", "note": "Moved the walk to tomorrow morning."},
    )
    store.mutate(
        "note.record",
        "demo-note-v1",
        {"goal_id": first["goal_id"], "body": "The next step felt easier after putting the book on the desk."},
    )
    print(json.dumps({"db": str(Path(args.db).resolve()), "summary": store.snapshot()["summary"]}, sort_keys=True))


if __name__ == "__main__":
    main()
