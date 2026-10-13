"""Local Windows UI doorbell adapter — DIRECTIVE 2 remaining gap.

The bus's open half is a doorbell for desktop agent windows (ChatGPT/Codex/
Grok-class desktop apps). OpenAI/Anthropic-side resume stays
EXTERNAL_PLATFORM_ACTION; this adapter is the local-machine leg: on a Windows
host where ``host.titan_hands`` is importable, it rings a named app window by
UI actuation (focus -> composer click -> type the wake line -> Return), then
re-observes and only reports live_wake when the typed text is visible.

No env secrets. deliver=False never touches the UI. Non-Windows hosts or a
missing titan_hands import report RUNTIME_UNCONFIGURED / CODE_MISSING instead
of fabricating a wake.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

EDIT_ROLES = {"Edit", "Document", "Text", "TextBox"}


def _hands():
    try:
        from host.titan_hands.one_tool import TitanHandsOne
    except ImportError:
        try:
            root = Path(__file__).resolve().parents[2]
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            from host.titan_hands.one_tool import TitanHandsOne
        except ImportError:
            return None
    return TitanHandsOne()


def _observe(hands, max_nodes=400):
    return hands.handle({"op": "observe", "target": "windows", "max_nodes": max_nodes})


def _find_window(nodes, title_re):
    for node in nodes or []:
        name = str(node.get("name") or node.get("title") or "")
        role = str(node.get("role") or "")
        if title_re.search(name) and role in {"Window", "Pane", "Document", ""}:
            return node
    return None


def _find_composer(nodes, window_id):
    for node in nodes or []:
        role = str(node.get("role") or "")
        if role in EDIT_ROLES and str(node.get("parent") or "") == str(window_id):
            return node
    for node in nodes or []:
        if str(node.get("role") or "") in EDIT_ROLES:
            return node
    return None


def signal(
    target: dict[str, Any],
    job: dict[str, Any],
    *,
    tick: dict[str, Any] | None = None,
    deliver: bool = False,
    env: dict[str, str] | None = None,
    http: Any | None = None,
    hands: Any | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    wake = target.get("wake_target") or {}
    apps = wake.get("apps") or []
    base = {
        "ok": True,
        "live_wake": False,
        "invoke_model": False,
        "process_model_invocations": 0,
        "network_calls": 0,
        "secrets_in_config": False,
        "adapter": "windows_titan",
        "doorbell": str(target.get("doorbell") or "RUNTIME_READY"),
        "job_id": job.get("job_id"),
        "attempt_id": (tick or {}).get("attempt_id"),
        "deliver_requested": bool(deliver),
        "reused": [
            "host/titan_hands/one_tool.py",
            "host/titan_hands/windows adapter (UIA + SendInput)",
        ],
        "now": now,
    }
    if os.name != "nt":
        base.update({
            "state": "RUNTIME_UNCONFIGURED",
            "capability": "RUNTIME_UNCONFIGURED",
            "code": "CODE_READY",
            "runtime": "RUNTIME_UNCONFIGURED",
            "note": "Local UI doorbell needs a Windows host with the desktop app open.",
        })
        return base
    hands = hands if hands is not None else _hands()
    if hands is None:
        base.update({
            "state": "CODE_MISSING",
            "capability": "RUNTIME_UNCONFIGURED",
            "code": "CODE_MISSING",
            "runtime": "RUNTIME_UNCONFIGURED",
            "note": "host.titan_hands is not importable from this tree.",
        })
        return base
    if not deliver:
        base.update({
            "state": "RUNTIME_READY",
            "capability": "RUNTIME_READY",
            "code": "CODE_READY",
            "runtime": "RUNTIME_READY",
            "note": "Dry run. Windows + titan_hands present. No UI touched.",
        })
        return base

    app_name = str(job.get("wake_app") or (apps[0].get("app") if apps else "") or "")
    app = next((a for a in apps if str(a.get("app")) == app_name), apps[0] if apps else None)
    title_re = re.compile(str((app or {}).get("title_regex") or "ChatGPT"), re.I)
    text = str(job.get("wake_text") or wake.get("wake_text") or wake.get("prompt")
               or "WAKE job_id=%s — check Commons." % (job.get("job_id") or "?"))
    text = text.replace("{job_id}", str(job.get("job_id") or "?"))

    try:
        snap = _observe(hands)
    except Exception as exc:
        base.update({"state": "OBSERVE_FAILED", "capability": "RUNTIME_UNCONFIGURED",
                     "note": "windows observe failed: %r" % exc})
        return base
    window = _find_window(snap.get("nodes"), title_re)
    if window is None:
        base.update({
            "state": "WINDOW_MISS",
            "capability": "RUNTIME_READY",
            "code": "CODE_READY",
            "runtime": "RUNTIME_READY",
            "note": "No window matching %r. Nothing was typed." % title_re.pattern,
        })
        return base
    composer = _find_composer(snap.get("nodes"), window.get("id"))
    if composer is None:
        base.update({"state": "COMPOSER_MISS", "capability": "RUNTIME_READY",
                     "note": "Window found, no editable node. Nothing typed."})
        return base
    steps = [
        {"op": "act", "target": "windows", "action": {"type": "click", "id": composer.get("id")}},
        {"op": "act", "target": "windows", "action": {"type": "type_text", "id": composer.get("id"), "text": text}},
        {"op": "act", "target": "windows", "action": {"type": "key", "id": composer.get("id"), "key": "Return"}},
    ]
    for step in steps:
        try:
            outcome = hands.handle(step)
        except Exception as exc:
            base.update({"state": "ACT_FAILED", "note": "%r during %s" % (exc, step["action"]["type"])})
            return base
        if not outcome.get("ok"):
            base.update({"state": "ACT_FAILED", "note": "act %s refused: %s"
                         % (step["action"]["type"], outcome.get("failure_reason") or outcome.get("message"))})
            return base
    try:
        verify = _observe(hands)
    except Exception:
        verify = {}
    marker = str(job.get("job_id") or text)[:24]
    seen = any(marker and marker in str(n.get("value") or n.get("name") or "")
               for n in (verify.get("nodes") or []))
    base.update({
        "state": "MAILED" if seen else "ACT_UNVERIFIED",
        "capability": "RUNTIME_READY",
        "code": "CODE_READY",
        "runtime": "RUNTIME_READY",
        "live_wake": bool(seen),
        "window": str(window.get("name") or "")[:80],
        "note": "Typed into the composer and re-observed."
                if seen else "Acts accepted but the wake line was not observed — not claimed live.",
    })
    return base
