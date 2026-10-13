from __future__ import annotations

import json

from .mcp_server import Dispatcher, MCP_PROTOCOL_VERSION


def rpc(dispatcher: Dispatcher, request_id: int, method: str, params: dict | None = None) -> dict:
    response = dispatcher.handle({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
    assert response is not None
    return response


def tool(dispatcher: Dispatcher, request_id: int, name: str, arguments: dict) -> dict:
    return rpc(dispatcher, request_id, "tools/call", {"name": name, "arguments": arguments})["result"]["structuredContent"]


def run_demo() -> dict:
    dispatcher = Dispatcher()
    initialize = rpc(
        dispatcher,
        1,
        "initialize",
        {"protocolVersion": MCP_PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "homeops-demo", "version": "1"}},
    )
    issue = tool(
        dispatcher,
        2,
        "homeops.intake_issue",
        {
            "title": "Water collecting under kitchen sink",
            "area": "kitchen",
            "severity": "HIGH",
            "details": "Slow water leak appears after the faucet runs.",
            "evidence": ["photo:demo/sink-cabinet.jpg", "observation:dry when faucet is unused"],
        },
    )
    tool(
        dispatcher,
        3,
        "homeops.record_quote",
        {
            "issue_id": issue["issue_id"],
            "provider": "Example Plumbing A",
            "amount_minor": 24500,
            "currency": "USD",
            "scope": "Replace supply line if inspection confirms leak",
            "source": "synthetic demo quote",
        },
    )
    tool(
        dispatcher,
        4,
        "homeops.record_quote",
        {
            "issue_id": issue["issue_id"],
            "provider": "Example Plumbing B",
            "amount_minor": 31000,
            "currency": "USD",
            "scope": "Diagnostic visit plus approved supply-line repair",
            "source": "synthetic demo quote",
        },
    )
    plan = tool(dispatcher, 5, "homeops.propose_plan", {"issue_id": issue["issue_id"]})
    action = tool(
        dispatcher,
        6,
        "homeops.request_action",
        {
            "issue_id": issue["issue_id"],
            "action_type": "CONTACT_PROVIDER",
            "target": "Example Plumbing A",
            "max_amount_minor": 24500,
            "currency": "USD",
            "note": "Ask for earliest diagnostic window; do not book automatically.",
        },
    )
    snapshot = tool(dispatcher, 7, "homeops.snapshot", {})
    verification = dispatcher.ledger.verify_events(dispatcher.ledger.export_events())
    return {
        "initialize": initialize["result"],
        "issue": issue,
        "plan": plan,
        "action": action,
        "snapshot": snapshot,
        "verification": verification,
    }


def main() -> None:
    print(json.dumps(run_demo(), indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
