#!/usr/bin/env python3
"""Test double for the Claude Code CLI's print mode.

Speaks the same stream-json shape the real CLI emits (``system/init``, ``assistant``,
``result``) so ``claude_headless`` can be exercised hermetically. Behaviour is driven by
words in the prompt:

    SLOW      emit fifty progress lines 200 ms apart (about ten seconds) before the result
    CRASH     exit without ever writing a result event (an interrupted child)
    FAIL      finish with ``is_error`` true and exit code 1
    ECHOENV   include the child's CLAUDECODE / ANTHROPIC_BASE_URL values in the reply

Conversation state lives in ``$STUB_CLAUDE_STATE/stub-<session>.json`` and is written at
init, the way the real CLI persists its transcript incrementally, so a killed run can
still be resumed. ``--resume`` of an unknown session fails the way the CLI does.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path


def _emit(value: dict) -> None:
    sys.stdout.buffer.write(json.dumps(value, ensure_ascii=False).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def main(argv: list[str]) -> int:
    args = argv[1:]
    prompt: str | None = None
    session_id: str | None = None
    resume: str | None = None
    partial = False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "-p":
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                prompt = args[i + 1]
                i += 2
            else:
                i += 1
            continue
        if arg == "--session-id":
            session_id = args[i + 1]
            i += 2
            continue
        if arg == "--resume":
            resume = args[i + 1]
            i += 2
            continue
        if arg in ("--output-format", "--model", "--tools", "--permission-mode"):
            i += 2
            continue
        if arg == "--include-partial-messages":
            partial = True
        elif arg == "--version":
            sys.stdout.write("0.0.0-stub (Claude Code)\n")
            return 0
        i += 1
    if prompt is None:
        prompt = sys.stdin.read()

    state_dir = Path(os.environ.get("STUB_CLAUDE_STATE") or os.getcwd())
    sid = resume or session_id or str(uuid.uuid4())
    state = state_dir / f"stub-{sid}.json"
    prior: list[str] = []
    if resume:
        if not state.exists():
            _emit(
                {
                    "type": "result",
                    "subtype": "error_during_execution",
                    "is_error": True,
                    "result": f"No conversation found with session ID: {resume}",
                    "session_id": sid,
                    "num_turns": 0,
                    "duration_ms": 1,
                    "total_cost_usd": 0.0,
                }
            )
            return 1
        prior = json.loads(state.read_text(encoding="utf-8"))["prompts"]

    _emit(
        {
            "type": "system",
            "subtype": "init",
            "session_id": sid,
            "model": "stub-model",
            "cwd": os.getcwd(),
            "tools": [],
            "claude_code_version": "0.0.0-stub",
            "permissionMode": "stub",
        }
    )
    state.write_text(json.dumps({"prompts": prior + [prompt]}), encoding="utf-8")

    if "SLOW" in prompt:
        for n in range(50):
            if partial:
                _emit(
                    {
                        "type": "stream_event",
                        "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": f"tick {n} "}},
                        "session_id": sid,
                    }
                )
            else:
                _emit({"type": "assistant", "message": {"content": [{"type": "text", "text": f"tick {n}"}]}, "session_id": sid})
            time.sleep(0.2)
    if "CRASH" in prompt:
        os._exit(3)

    text = f"stub reply #{len(prior) + 1} to: {prompt.strip()[:200]} | prior: {json.dumps(prior)}"
    if "ECHOENV" in prompt:
        text += (
            " | CLAUDECODE="
            + os.environ.get("CLAUDECODE", "<absent>")
            + " ANTHROPIC_BASE_URL="
            + os.environ.get("ANTHROPIC_BASE_URL", "<absent>")
            + " CLAUDE_CODE_SESSION_ID="
            + os.environ.get("CLAUDE_CODE_SESSION_ID", "<absent>")
        )
    _emit({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}, "session_id": sid})
    is_error = "FAIL" in prompt
    _emit(
        {
            "type": "result",
            "subtype": "error_during_execution" if is_error else "success",
            "is_error": is_error,
            "duration_ms": 5,
            "num_turns": 1,
            "result": text,
            "session_id": sid,
            "total_cost_usd": 0.0,
        }
    )
    return 1 if is_error else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
