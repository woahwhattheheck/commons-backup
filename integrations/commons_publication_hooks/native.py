"""Cursor and Gemini CLI protocol adapters for the shared publication policy."""
from __future__ import annotations

import argparse
import json
import sys

from hook import POLICY_CONTEXT, private_feedback, publication_verdict


def handle(event: dict, client: str) -> dict:
    name = str(event.get("hook_event_name") or "")
    context = "When working with Commons or Slack: " + POLICY_CONTEXT
    if client == "cursor":
        if name == "sessionStart":
            return {"additional_context": context}
        if name not in {"preToolUse", "beforeMCPExecution"}:
            return {}
        verdict = publication_verdict(event)
        if verdict is None or verdict["allowed"]:
            return {"permission": "allow"}
        feedback = private_feedback(verdict)
        return {"permission": "deny", "user_message": feedback,
                "agent_message": feedback}
    if client == "gemini":
        if name in {"SessionStart", "BeforeAgent"}:
            return {"hookSpecificOutput": {"hookEventName": name,
                    "additionalContext": context}}
        if name != "BeforeTool":
            return {}
        verdict = publication_verdict(event)
        if verdict is None or verdict["allowed"]:
            return {}
        # Deny only this proposed publication. continue:false would terminate
        # the agent loop and prevent the requested useful work from continuing.
        return {"decision": "deny", "reason": private_feedback(verdict)}
    raise ValueError("unsupported native client")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=("cursor", "gemini"), required=True)
    args = parser.parse_args()
    print(json.dumps(handle(json.load(sys.stdin), args.client), ensure_ascii=False))
