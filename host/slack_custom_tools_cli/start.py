#!/usr/bin/env python3
"""Slack CLI start hook (slack run). Socket Mode. Tokens stay in env, never printed."""
from __future__ import annotations

import os
import sys
from pathlib import Path

HOST = Path(__file__).resolve().parent.parent
if str(HOST) not in sys.path:
    sys.path.insert(0, str(HOST))

MISSING = (
    "NEEDS_OWNER_SIGNIN: Slack CLI app tokens are not in this environment. "
    "Queue #needs-bryce C0BRX6EV739. Do not paste tokens into Slack or git."
)
NO_BOLT = (
    "NEEDS_RUNTIME: slack_bolt is not installed. "
    "pip install slack_bolt then slack run --org-workspace-grant=all"
)


def _has_tokens(environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    bot = str(env.get("SLACK_BOT_TOKEN") or "").strip()
    app = str(env.get("SLACK_APP_TOKEN") or "").strip()
    return bool(bot and app)


def start(environ: dict[str, str] | None = None) -> int:
    env = environ if environ is not None else os.environ
    if not _has_tokens(env):
        print(MISSING, file=sys.stderr)
        return 2
    try:
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler
    except ImportError:
        print(NO_BOLT, file=sys.stderr)
        return 2
    import slack_custom_tools_app as cta

    bot = str(env.get("SLACK_BOT_TOKEN") or "").strip()
    app_token = str(env.get("SLACK_APP_TOKEN") or "").strip()
    app = App(token=bot)
    cta.register(app, environ=env)
    SocketModeHandler(app, app_token).start()
    return 0


def main(argv: list[str] | None = None) -> int:
    del argv
    return start()


if __name__ == "__main__":
    raise SystemExit(main())
