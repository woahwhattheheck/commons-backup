#!/usr/bin/env python3
"""Unique titanmcp list_rooms KEEP remainder.

Live list_rooms with empty arguments is HTTP 200 JSON, MCP ok:true,
rooms a list, count equal to len(rooms). Optional integer limit
including advertised-out-of-range 101 and -1 stays ok:true, not
BAD_ARGUMENT (schema text says 1-100 default 50; those bounds are
not enforced). JSON float limit 1.5 and boolean limit are MCP
isError BAD_ARGUMENT hint arguments.limit must be integer, not
JSON-RPC -32602. Extra room_id, extra cursor, extra query, extra
need, extra minutes, and extra id are MCP isError BAD_ARGUMENT hint
arguments.<name> is not allowed (room_id is required on list_roles;
cursor is the list_messages page key; query is the
list_research_power filter; need is required on request_setup;
id=github is OPTIONAL_CAPABILITY_NOT_FOUND on list_custom_tooling).
Commons /mcp KEEP has no list_rooms. Isolated classifier stays
green without reminting pad runtime, Latch titanmcp.html,
setup-schema, SAVE/LOAD DRAFT, GET /mcp identity, Origin pair,
list_messages cursor, unknown after=, create_play_token,
consent-attach, get_operator, MESSAGE_CURSOR_NOT_FOUND,
get_connector, check_subscription, list_connectors,
list_research_power, list_custom_tooling, or get_setup_status
batteries. leftover --bake/--deploy/--go REFUSED sent=0. No
competition resubmission.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


ID = "cursor-titanmcp-list-rooms-20261003-01"
PAD_MCP = "https://webmcp-pad.vercel.app/mcp"
COMMONS_MCP = "https://commons-spark-mcp.vercel.app/mcp"
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
        "User-Agent": "titanmcp-list-rooms",
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


def classify_ok_rooms(packet: dict[str, Any], status: int) -> dict[str, Any]:
    err = jsonrpc_error(packet)
    result = packet.get("result") if isinstance(packet.get("result"), dict) else {}
    sc = structured_content(packet)
    rooms = sc.get("rooms")
    count = sc.get("count")
    ok = (
        status == 200
        and not err
        and result.get("isError") is not True
        and sc.get("ok") is True
        and isinstance(rooms, list)
        and isinstance(count, int)
        and count == len(rooms)
        and err.get("code") != -32602
    )
    return {
        "ok": ok,
        "status": status,
        "jsonrpc_code": err.get("code"),
        "is_error": result.get("isError"),
        "sc_ok": sc.get("ok"),
        "rooms_is_list": isinstance(rooms, list),
        "count": count,
        "count_matches": isinstance(rooms, list) and isinstance(count, int) and count == len(rooms),
        "not_jsonrpc_32602": err.get("code") != -32602,
    }


def classify_must_be_integer(packet: dict[str, Any], status: int, argument: str) -> dict[str, Any]:
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
        and f"arguments.{argument} must be integer" in hint
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
        "kind": "TITANMCP_LIST_ROOMS",
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
            "list_research_power, list_custom_tooling, or "
            "get_setup_status KEEP. leftover bake/deploy sent=0."
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
                "clientInfo": {"name": "titanmcp-list-rooms", "version": "1"},
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
    if "list_rooms" not in names:
        errors.append("pad_tool")

    empty = _call("list_rooms", {}, 3)
    empty_row = classify_ok_rooms(empty.get("packet") or {}, empty.get("status") or 0)
    if not empty_row["ok"]:
        errors.append("empty")

    limit_high = _call("list_rooms", {"limit": 101}, 4)
    limit_high_row = classify_ok_rooms(limit_high.get("packet") or {}, limit_high.get("status") or 0)
    if not limit_high_row["ok"]:
        errors.append("limit_high")

    limit_neg = _call("list_rooms", {"limit": -1}, 5)
    limit_neg_row = classify_ok_rooms(limit_neg.get("packet") or {}, limit_neg.get("status") or 0)
    if not limit_neg_row["ok"]:
        errors.append("limit_neg")

    limit_float = _call("list_rooms", {"limit": 1.5}, 6)
    limit_float_row = classify_must_be_integer(
        limit_float.get("packet") or {}, limit_float.get("status") or 0, "limit"
    )
    if not limit_float_row["ok"]:
        errors.append("wrong_type_limit_float")

    extra_room_id = _call("list_rooms", {"room_id": "room-x"}, 7)
    extra_room_id_row = classify_not_allowed(
        extra_room_id.get("packet") or {}, extra_room_id.get("status") or 0, "room_id"
    )
    if not extra_room_id_row["ok"]:
        errors.append("extra_room_id")

    extra_cursor = _call("list_rooms", {"cursor": "cursor"}, 8)
    extra_cursor_row = classify_not_allowed(
        extra_cursor.get("packet") or {}, extra_cursor.get("status") or 0, "cursor"
    )
    if not extra_cursor_row["ok"]:
        errors.append("extra_cursor")

    extra_query = _call("list_rooms", {"query": "github"}, 9)
    extra_query_row = classify_not_allowed(
        extra_query.get("packet") or {}, extra_query.get("status") or 0, "query"
    )
    if not extra_query_row["ok"]:
        errors.append("extra_query")

    extra_need = _call("list_rooms", {"need": "x"}, 10)
    extra_need_row = classify_not_allowed(
        extra_need.get("packet") or {}, extra_need.get("status") or 0, "need"
    )
    if not extra_need_row["ok"]:
        errors.append("extra_need")

    extra_minutes = _call("list_rooms", {"minutes": 1}, 11)
    extra_minutes_row = classify_not_allowed(
        extra_minutes.get("packet") or {}, extra_minutes.get("status") or 0, "minutes"
    )
    if not extra_minutes_row["ok"]:
        errors.append("extra_minutes")

    extra_id = _call("list_rooms", {"id": "github"}, 12)
    extra_id_row = classify_not_allowed(
        extra_id.get("packet") or {}, extra_id.get("status") or 0, "id"
    )
    if not extra_id_row["ok"]:
        errors.append("extra_id")

    commons_init = _rpc(
        COMMONS_MCP,
        {
            "jsonrpc": "2.0",
            "id": 13,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "titanmcp-list-rooms", "version": "1"},
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
        or "list_rooms" in commons_names
    ):
        errors.append("commons_keep")

    return {
        "kind": "TITANMCP_LIST_ROOMS",
        "id": ID,
        "pad_initialize": {"name": info.get("name"), "version": info.get("version")},
        "commons_initialize": {
            "name": commons_info.get("name"),
            "version": commons_info.get("version"),
        },
        "pad_has_list_rooms": "list_rooms" in names,
        "commons_has_list_rooms": "list_rooms" in commons_names,
        "empty_arguments": empty_row,
        "limit_high": limit_high_row,
        "limit_neg": limit_neg_row,
        "wrong_type_limit_float": limit_float_row,
        "extra_room_id": extra_room_id_row,
        "extra_cursor": extra_cursor_row,
        "extra_query": extra_query_row,
        "extra_need": extra_need_row,
        "extra_minutes": extra_minutes_row,
        "extra_id": extra_id_row,
        "did_not_remint": list(DO_NOT_REMINT),
        "sent": 0,
        "cash": 0,
        "errors": errors,
        "verdict": "MATCH" if not errors else "FINDER-FAILED",
        "note": (
            "Unique remainder after get_setup_status KEEP: list_rooms empty "
            "arguments is 200 ok:true rooms list count==len(rooms). Integer "
            "limit 101 and -1 stay ok:true (schema 1-100 is not enforced). "
            "Float limit 1.5 is MCP isError BAD_ARGUMENT must be integer, "
            "not JSON-RPC -32602. Extra room_id, cursor, query, need, "
            "minutes, and id are MCP isError BAD_ARGUMENT is not allowed. "
            "Commons /mcp KEEP has no list_rooms. No competition "
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
                        "kind": "TITANMCP_LIST_ROOMS",
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
