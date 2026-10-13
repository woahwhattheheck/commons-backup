"""Reference GET poll adapter. Reuses ping/ last.json, poll.html, poll_ntfy.py.

Commons still cannot doorbell ChatGPT or Claude. This adapter records the
GET road and never fabricates a live wake.
"""
from __future__ import annotations

from typing import Any, Callable


POLL_PATHS = (
    "ping/last.json",
    "ping/chatgpt.md",
    "ping/claude.md",
    "ping/adapters.md",
    "ping/poll.html",
    "ping/poll_ntfy.py",
    "ping/union_git_ntfy.py",
    "ping/decide.py",
)


def signal(
    target: dict[str, Any],
    job: dict[str, Any],
    *,
    tick: dict[str, Any] | None = None,
    deliver: bool = False,
    env: dict[str, str] | None = None,
    http: Callable[..., Any] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    wake = target.get("wake_target") or {}
    return {
        "ok": True,
        "state": "POLL_ONLY",
        "capability": "EXTERNAL_PLATFORM_ACTION",
        "code": "CODE_READY",
        "runtime": "RUNTIME_READY",
        "doorbell": "EXTERNAL_PLATFORM_ACTION",
        "live_wake": False,
        "invoke_model": False,
        "process_model_invocations": 0,
        "network_calls": 0,
        "deliver_requested": bool(deliver),
        "job_id": job.get("job_id"),
        "attempt_id": (tick or {}).get("attempt_id"),
        "path": wake.get("path") or "ping/last.json",
        "prompt": wake.get("prompt") or "",
        "reused": list(POLL_PATHS),
        "now": now,
        "note": (
            "Commons cannot doorbell this peer. GET ping/last.json. "
            "If your claim is in moved_poll, GET mail.json. "
            "Union git ls-remote p/{id}.md with ntfy; ntfy 200 is mail. "
            "No callback URL. No token on the board. deliver=%s still does not ring."
        ) % bool(deliver),
    }
