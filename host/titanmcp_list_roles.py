#!/usr/bin/env python3
"""Unique titanmcp list_roles KEEP remainder.

Live list_roles with empty arguments is HTTP 200 JSON, MCP isError
BAD_ARGUMENT argument=room_id hint arguments.room_id is required, not
JSON-RPC -32602. Unknown string room_id is MCP isError ROOM_NOT_FOUND
with that room_id retained (empty string room_id is also
ROOM_NOT_FOUND, not required). Extra task_id, extra after, extra
limit, extra agent_name, extra role, and extra cursor are MCP isError
BAD_ARGUMENT hint arguments.<name> is not allowed (task_id is optional
on list_assignments; after pages list_messages which shares
ROOM_NOT_FOUND; limit is optional on list_rooms; agent_name is
required on invite_agent; role is required on set_role and optional on
get_operator). JSON float room_id 1.5 is MCP isError BAD_ARGUMENT
hint arguments.room_id must be string, not JSON-RPC -32602. Commons
/mcp KEEP has no list_roles. Isolated classifier stays green without
reminting pad runtime, Latch titanmcp.html, setup-schema, SAVE/LOAD
DRAFT, GET /mcp identity, Origin pair, list_messages cursor, unknown
after=, create_play_token, consent-attach, get_operator,
MESSAGE_CURSOR_NOT_FOUND, get_connector, check_subscription,
list_connectors, list_research_power, list_custom_tooling,
get_setup_status, or list_rooms batteries. leftover
--bake/--deploy/--go REFUSED sent=0. No competition resubmission.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


ID = "cursor-titanmcp-list-roles-20261003-01"
PAD_MCP = "https://webmcp-pad.vercel.app/mcp"
COMMONS_MCP = "https://commons-spark-mcp.vercel.app/mcp"
UNKNOWN_ROOM = "room-does-not-exist"
REFUSE = ("--send", "--apply", "--go", "--autopilot", "--live", "--checkout", "--deploy", "--bake")
DO_NOT_REMINT = (
    "api/mcp.py",
    "commons_mcp.py",
    "titanmcp.html",
    "webmcp.html",
    ".github/workflows/webmcp-pad-production.yml",
    "host/titanmcp_setup_schema.py",
    "host/titanmcp_save_load_draft.py",
    "host/titanmcp_get_mcp_identity.py",
    "host/titanmcp_origin_pair.py",
    "host/titanmcp_list_messages_cursor.py",
    "host/titanmcp_unknown_after.py",
    "host/titanmcp_play_token.py",
    "host/titanmcp_consent_attach.py",
    "host/titanmcp_get_operator.py",
    "host/titanmcp_message_cursor_not_found.py",
    "host/titanmcp_get_connector.py",
    "host/titanmcp_check_subscription.py",
    "host/titanmcp_list_connectors.py",
    "host/titanmcp_list_research_power.py",
    "host/titanmcp_list_custom_tooling.py",
    "host/titanmcp_get_setup_status.py",
    "host/titanmcp_list_rooms.py",
    "p/cursor-titanmcp-setup-schema-20260929-01.md",
    "p/cursor-titanmcp-save-load-draft-20260930-01.md",
    "p/cursor-titanmcp-get-mcp-identity-20261001-01.md",
    "p/cursor-titanmcp-origin-pair-20261001-01.md",
    "p/cursor-titanmcp-list-messages-cursor-20261001-01.md",
    "p/cursor-titanmcp-unknown-after-20261001-01.md",
    "p/cursor-titanmcp-play-token-20261002-01.md",
    "p/cursor-titanmcp-consent-attach-20261002-01.md",
    "p/cursor-titanmcp-get-operator-20261002-01.md",
    "p/cursor-titanmcp-message-cursor-not-found-20261003-01.md",
    "p/cursor-titanmcp-get-connector-20261003-01.md",
    "p/cursor-titanmcp-check-subscription-20261003-01.md",
    "p/cursor-titanmcp-list-connectors-20261003-01.md",
    "p/cursor-titanmcp-list-research-power-20261003-01.md",
    "p/cursor-titanmcp-list-custom-tooling-20261003-01.md",
    "p/cursor-titanmcp-get-setup-status-20261003-01.md",
    "p/cursor-titanmcp-list-rooms-20261003-01.md",
)


def structured_content(packet: dict[str, Any]) -> dict[str, Any]:
    result = packet.get("result")
    if not isinstance(result, dict):
        return {}
    sc = result.get("structuredContent")
    return sc if isinstance(sc, dict) else {}


def jsonrpc_error(packet: dict[str, Any]) -> dict[str, Any]:
    err = packet.get("error")
    return err if isinstance(err, dict) else {}


def _rpc(url: str, obj: dict[str, Any], *, origin: str = "https://chatgpt.com") -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-03-26",
        "User-Agent": "titanmcp-list-roles",
    }
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(
        url,
        data=json.dumps(obj).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"status": resp.status, "packet": json.loads(resp.read().decode("utf-8"))}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            packet = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            packet = {"raw": raw[:200].decode("utf-8", "replace")}
        return {"status": exc.code, "packet": packet}


def _call(name: str, arguments: dict[str, Any], request_id: int) -> dict[str, Any]:
    return _rpc(
        PAD_MCP,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )


def classify_required(packet: dict[str, Any], status: int, argument: str) -> dict[str, Any]:
    err = jsonrpc_error(packet)
    result = packet.get("result") if isinstance(packet.get("result"), dict) else {}
    sc = structured_content(packet)
    hint = str(sc.get("hint") or "")
    ok = (
        status == 200
        and not err
        and result.get("isError") is True
        and sc.get("ok") is False
        and sc.get("error") == "BAD_ARGUMENT"
        and sc.get("argument") == argument
        and f"arguments.{argument} is required" in hint
        and err.get("code") != -32602
    )
    return {
        "ok": ok,
        "status": status,
        "jsonrpc_code": err.get("code"),
        "is_error": result.get("isError"),
        "error": sc.get("error"),
        "argument": sc.get("argument"),
        "hint": sc.get("hint"),
        "not_jsonrpc_32602": err.get("code") != -32602,
    }


def classify_room_not_found(packet: dict[str, Any], status: int, room_id: str) -> dict[str, Any]:
    err = jsonrpc_error(packet)
    result = packet.get("result") if isinstance(packet.get("result"), dict) else {}
    sc = structured_content(packet)
    ok = (
        status == 200
        and not err
        and result.get("isError") is True
        and sc.get("ok") is False
        and sc.get("error") == "ROOM_NOT_FOUND"
        and sc.get("room_id") == room_id
        and err.get("code") != -32602
    )
    return {
        "ok": ok,
        "status": status,
        "jsonrpc_code": err.get("code"),
        "is_error": result.get("isError"),
        "error": sc.get("error"),
        "room_id": sc.get("room_id"),
        "not_jsonrpc_32602": err.get("code") != -32602,
    }


def classify_must_be_string(packet: dict[str, Any], status: int, argument: str) -> dict[str, Any]:
    err = jsonrpc_error(packet)
    result = packet.get("result") if isinstance(packet.get("result"), dict) else {}
    sc = structured_content(packet)
    hint = str(sc.get("hint") or "")
    ok = (
        status == 200
        and not err
        and result.get("isError") is True
        and sc.get("ok") is False
        and sc.get("error") == "BAD_ARGUMENT"
        and sc.get("argument") == argument
        and f"arguments.{argument} must be string" in hint
        and err.get("code") != -32602
    )
    return {
        "ok": ok,
        "status": status,
        "jsonrpc_code": err.get("code"),
        "is_error": result.get("isError"),
        "error": sc.get("error"),
        "argument": sc.get("argument"),
        "hint": sc.get("hint"),
        "not_jsonrpc_32602": err.get("code") != -32602,
    }


def classify_not_allowed(packet: dict[str, Any], status: int, argument: str) -> dict[str, Any]:
    err = jsonrpc_error(packet)
    result = packet.get("result") if isinstance(packet.get("result"), dict) else {}
    sc = structured_content(packet)
    hint = str(sc.get("hint") or "")
    ok = (
        status == 200
        and not err
        and result.get("isError") is True
        and sc.get("ok") is False
        and sc.get("error") == "BAD_ARGUMENT"
        and sc.get("argument") == argument
        and f"arguments.{argument} is not allowed" in hint
        and err.get("code") != -32602
    )
    return {
        "ok": ok,
        "status": status,
        "jsonrpc_code": err.get("code"),
        "is_error": result.get("isError"),
        "error": sc.get("error"),
        "argument": sc.get("argument"),
        "hint": sc.get("hint"),
        "not_jsonrpc_32602": err.get("code") != -32602,
    }


def refuse_payload(flag: str) -> dict[str, Any]:
    return {
        "kind": "TITANMCP_LIST_ROLES",
        "id": ID,
        "refused": flag,
        "sent": 0,
        "cash": 0,
        "invented_stripe_urls": False,
        "verdict": "REFUSED",
        "note": (
            f"{flag} REFUSED. Did not remint pad runtime, titanmcp.html, "
            "setup-schema, SAVE/LOAD DRAFT, GET /mcp identity, Origin pair, "
            "list_messages cursor, unknown after=, create_play_token, "
            "consent-attach, get_operator, MESSAGE_CURSOR_NOT_FOUND, "
            "get_connector, check_subscription, list_connectors, "
            "list_research_power, list_custom_tooling, get_setup_status, "
            "or list_rooms KEEP. leftover bake/deploy sent=0."
        ),
    }


def measure() -> dict[str, Any]:
    errors: list[str] = []
    init = _rpc(
        PAD_MCP,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "titanmcp-list-roles", "version": "1"},
            },
        },
    )
    info = ((init.get("packet") or {}).get("result") or {}).get("serverInfo") or {}
    if info.get("name") != "titanmcp" or info.get("version") != "1.4.5":
        errors.append("pad_mcp")

    listed = _rpc(PAD_MCP, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    names = [
        row.get("name")
        for row in ((listed.get("packet") or {}).get("result") or {}).get("tools") or []
        if isinstance(row, dict)
    ]
    if "list_roles" not in names:
        errors.append("pad_tool")

    empty = _call("list_roles", {}, 3)
    empty_row = classify_required(empty.get("packet") or {}, empty.get("status") or 0, "room_id")
    if not empty_row["ok"]:
        errors.append("empty")

    unknown = _call("list_roles", {"room_id": UNKNOWN_ROOM}, 4)
    unknown_row = classify_room_not_found(
        unknown.get("packet") or {}, unknown.get("status") or 0, UNKNOWN_ROOM
    )
    if not unknown_row["ok"]:
        errors.append("unknown_room")

    empty_string = _call("list_roles", {"room_id": ""}, 5)
    empty_string_row = classify_room_not_found(
        empty_string.get("packet") or {}, empty_string.get("status") or 0, ""
    )
    if not empty_string_row["ok"]:
        errors.append("empty_string_room")

    extra_task_id = _call("list_roles", {"room_id": UNKNOWN_ROOM, "task_id": "t1"}, 6)
    extra_task_id_row = classify_not_allowed(
        extra_task_id.get("packet") or {}, extra_task_id.get("status") or 0, "task_id"
    )
    if not extra_task_id_row["ok"]:
        errors.append("extra_task_id")

    extra_after = _call("list_roles", {"room_id": UNKNOWN_ROOM, "after": "a"}, 7)
    extra_after_row = classify_not_allowed(
        extra_after.get("packet") or {}, extra_after.get("status") or 0, "after"
    )
    if not extra_after_row["ok"]:
        errors.append("extra_after")

    extra_limit = _call("list_roles", {"room_id": UNKNOWN_ROOM, "limit": 10}, 8)
    extra_limit_row = classify_not_allowed(
        extra_limit.get("packet") or {}, extra_limit.get("status") or 0, "limit"
    )
    if not extra_limit_row["ok"]:
        errors.append("extra_limit")

    extra_agent_name = _call("list_roles", {"room_id": UNKNOWN_ROOM, "agent_name": "peer"}, 9)
    extra_agent_name_row = classify_not_allowed(
        extra_agent_name.get("packet") or {}, extra_agent_name.get("status") or 0, "agent_name"
    )
    if not extra_agent_name_row["ok"]:
        errors.append("extra_agent_name")

    extra_role = _call("list_roles", {"room_id": UNKNOWN_ROOM, "role": "builder"}, 10)
    extra_role_row = classify_not_allowed(
        extra_role.get("packet") or {}, extra_role.get("status") or 0, "role"
    )
    if not extra_role_row["ok"]:
        errors.append("extra_role")

    extra_cursor = _call("list_roles", {"room_id": UNKNOWN_ROOM, "cursor": "cursor"}, 11)
    extra_cursor_row = classify_not_allowed(
        extra_cursor.get("packet") or {}, extra_cursor.get("status") or 0, "cursor"
    )
    if not extra_cursor_row["ok"]:
        errors.append("extra_cursor")

    room_id_float = _call("list_roles", {"room_id": 1.5}, 12)
    room_id_float_row = classify_must_be_string(
        room_id_float.get("packet") or {}, room_id_float.get("status") or 0, "room_id"
    )
    if not room_id_float_row["ok"]:
        errors.append("wrong_type_room_id_float")

    commons_init = _rpc(
        COMMONS_MCP,
        {
            "jsonrpc": "2.0",
            "id": 13,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "titanmcp-list-roles", "version": "1"},
            },
        },
        origin="",
    )
    commons_info = ((commons_init.get("packet") or {}).get("result") or {}).get("serverInfo") or {}
    commons_listed = _rpc(
        COMMONS_MCP,
        {"jsonrpc": "2.0", "id": 14, "method": "tools/list", "params": {}},
        origin="",
    )
    commons_names = [
        row.get("name")
        for row in ((commons_listed.get("packet") or {}).get("result") or {}).get("tools") or []
        if isinstance(row, dict)
    ]
    if (
        commons_info.get("name") != "commons"
        or commons_info.get("version") != "1.4.0"
        or "list_roles" in commons_names
    ):
        errors.append("commons_keep")

    return {
        "kind": "TITANMCP_LIST_ROLES",
        "id": ID,
        "pad_initialize": {"name": info.get("name"), "version": info.get("version")},
        "commons_initialize": {
            "name": commons_info.get("name"),
            "version": commons_info.get("version"),
        },
        "pad_has_list_roles": "list_roles" in names,
        "commons_has_list_roles": "list_roles" in commons_names,
        "empty_arguments": empty_row,
        "unknown_room": unknown_row,
        "empty_string_room": empty_string_row,
        "extra_task_id": extra_task_id_row,
        "extra_after": extra_after_row,
        "extra_limit": extra_limit_row,
        "extra_agent_name": extra_agent_name_row,
        "extra_role": extra_role_row,
        "extra_cursor": extra_cursor_row,
        "wrong_type_room_id_float": room_id_float_row,
        "did_not_remint": list(DO_NOT_REMINT),
        "sent": 0,
        "cash": 0,
        "errors": errors,
        "verdict": "MATCH" if not errors else "FINDER-FAILED",
        "note": (
            "Unique remainder after list_rooms KEEP: list_roles empty "
            "arguments is MCP isError BAD_ARGUMENT room_id is required, "
            "not JSON-RPC -32602. Unknown string room_id is ROOM_NOT_FOUND. "
            "Empty string room_id is also ROOM_NOT_FOUND, not required. "
            "Extra task_id, after, limit, agent_name, role, and cursor are "
            "MCP isError BAD_ARGUMENT is not allowed. Float room_id 1.5 is "
            "MCP isError BAD_ARGUMENT must be string, not JSON-RPC -32602. "
            "Commons /mcp KEEP has no list_roles. No competition "
            "resubmission."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--json", action="store_true")
    args, unknown = parser.parse_known_args(argv)
    del args
    for flag in unknown:
        if flag in REFUSE:
            print(json.dumps(refuse_payload(flag), sort_keys=True))
            return 2
        if flag.startswith("-"):
            print(
                json.dumps(
                    {
                        "kind": "TITANMCP_LIST_ROLES",
                        "verdict": "FINDER-FAILED",
                        "sent": 0,
                        "unknown": flag,
                        "note": f"{flag} FINDER-FAILED, never silent 0.",
                    },
                    sort_keys=True,
                )
            )
            return 1
    packet = measure()
    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0 if packet["verdict"] == "MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
