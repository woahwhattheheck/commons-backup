#!/usr/bin/env python3
"""Slack CLI project entry for Commons Service Tools.

Delegates to host/slack_custom_tools_app.register. Does not remint that
driver. Login stays #needs-bryce. Not a Commons admission gate.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HOST = ROOT / "host"
if str(HOST) not in sys.path:
    sys.path.insert(0, str(HOST))


def build_app(app_factory):
    from slack_custom_tools_app import register

    app = app_factory(process_before_response=True)
    return register(app)


def main() -> int:
    try:
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler
    except ImportError:
        print("slack-bolt missing; pip install -r requirements.txt", file=sys.stderr)
        return 2
    app = build_app(App)
    token = (
        os.environ.get("SLACK_APP_TOKEN")
        or os.environ.get("SLACK_APP_LEVEL_TOKEN")
        or ""
    )
    if not token:
        print(
            "SLACK_APP_TOKEN unset; Slack CLI login stays #needs-bryce",
            file=sys.stderr,
        )
        return 3
    SocketModeHandler(app, token).start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
