#!/usr/bin/env python3
"""Unique titanmcp list_operators KEEP remainder.

Live list_operators with empty arguments is HTTP 200 JSON, MCP ok:true,
operators a list, count equal to len(operators) and 5, store
roles_and_operators_in_mcp_not_harness, product titanmcp, calibration
no_tradeoff true. Extra id and extra role are MCP isError BAD_ARGUMENT
hint arguments.<name> is not allowed (get_operator KEEP accepts id and
role=builder). Extra limit is not allowed (list_rooms optional integer
limit stays ok:true). Extra room_id is BAD_ARGUMENT is not allowed, not
ROOM_NOT_FOUND (list_roles / list_assignments require room_id). Extra
task_id is not allowed (list_assignments optional task_id stays
ROOM_NOT_FOUND). Extra subject is not allowed (get_setup_status optional
subject). Extra query is not allowed (list_research_power). JSON float
id 1.5 is arguments.id is not allowed, not must be string. Commons /mcp
KEEP has no list_operators. Isolated classifier stays green without
reminting pad runtime, Latch titanmcp.html, setup-schema, SAVE/LOAD
DRAFT, GET /mcp identity, Origin pair, list_messages cursor, unknown
after=, create_play_token, consent-attach, get_operator,
MESSAGE_CURSOR_NOT_FOUND, get_connector, check_subscription,
list_connectors, list_research_power, list_custom_tooling,
get_setup_status, list_rooms, list_roles, or list_assignments batteries.
leftover --bake/--deploy/--go REFUSED sent=0. No competition
resubmission.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


ID = "cursor-titanmcp-list-operators-20261003-01"
PAD_MCP = "https://webmcp-pad.vercel.app/mcp"
COMMONS_MCP = "https://commons-spark-mcp.vercel.app/mcp"
OPERATOR_IDS = ("COORDINATOR", "BUILDER", "PROBER", "SETUP", "ACCURACY")
OPERATOR_ROLES = {
    "COORDINATOR": "coordinator",
    "BUILDER": "builder",
    "PROBER": "prober",
    "SETUP": "setup",
    "ACCURACY": "general",
}
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
    "host/titanmcp_list_roles.py",
    "host/titanmcp_list_assignments.py",
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
    "p/cursor-titanmcp-list-roles-20261003-01.md",
    "p/cursor-titanmcp-list-assignments-20261003-01.md",
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
        "User-Agent": "titanmcp-list-operators",
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


def classify_ok_operators(packet: dict[str, Any], status: int) -> dict[str, Any]:
    err = jsonrpc_error(packet)
    result = packet.get("result") if isinstance(packet.get("result"), dict) else {}
    sc = structured_content(packet)
    rows = sc.get("operators") if isinstance(sc.get("operators"), list) else []
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    roles = {
        row.get("id"): row.get("role") for row in rows if isinstance(row, dict)
    }
    headers = {
        row.get("id"): str(row.get("header") or "")
        for row in rows
        if isinstance(row, dict)
    }
    calibration = sc.get("calibration") if isinstance(sc.get("calibration"), dict) else {}
    ok = (
        status == 200
        and not err
        and result.get("isError") is not True
        and sc.get("ok") is True
        and sc.get("product") == "titanmcp"
        and sc.get("store") == "roles_and_operators_in_mcp_not_harness"
        and sc.get("count") == 5
        and len(ids) == 5
        and tuple(ids) == OPERATOR_IDS
        and roles == OPERATOR_ROLES
        and all(headers.get(op_id, "").endswith(op_id) for op_id in OPERATOR_IDS)
        and calibration.get("no_tradeoff") is True
        and err.get("code") != -32602
    )
    return {
        "ok": ok,
        "status": status,
        "jsonrpc_code": err.get("code"),
        "is_error": result.get("isError"),
        "sc_ok": sc.get("ok"),
        "product": sc.get("product"),
        "store": sc.get("store"),
        "count": sc.get("count"),
        "ids": ids,
        "roles": roles,
        "no_tradeoff": calibration.get("no_tradeoff"),
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
        and "must be string" not in hint
        and sc.get("error") != "ROOM_NOT_FOUND"
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
        "not_room_not_found": sc.get("error") != "ROOM_NOT_FOUND",
        "not_must_be_string": "must be string" not in hint,
    }


def refuse_payload(flag: str) -> dict[str, Any]:
    return {
        "kind": "TITANMCP_LIST_OPERATORS",
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
            "list_rooms, list_roles, or list_assignments KEEP. leftover "
            "bake/deploy sent=0."
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
                "clientInfo": {"name": "titanmcp-list-operators", "version": "1"},
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
    schema = next(
        (
            row.get("inputSchema")
            for row in ((listed.get("packet") or {}).get("result") or {}).get("tools") or []
            if isinstance(row, dict) and row.get("name") == "list_operators"
        ),
        {},
    )
    if "list_operators" not in names:
        errors.append("pad_tool")
    if (
        not isinstance(schema, dict)
        or schema.get("additionalProperties") is not False
        or schema.get("properties") != {}
        or schema.get("required") not in ([], None)
    ):
        errors.append("empty_schema")

    empty = _call("list_operators", {}, 3)
    empty_row = classify_ok_operators(empty.get("packet") or {}, empty.get("status") or 0)
    if not empty_row["ok"]:
        errors.append("empty")

    extra_id = _call("list_operators", {"id": "BUILDER"}, 4)
    extra_id_row = classify_not_allowed(extra_id.get("packet") or {}, extra_id.get("status") or 0, "id")
    if not extra_id_row["ok"]:
        errors.append("extra_id")

    extra_role = _call("list_operators", {"role": "builder"}, 5)
    extra_role_row = classify_not_allowed(
        extra_role.get("packet") or {}, extra_role.get("status") or 0, "role"
    )
    if not extra_role_row["ok"]:
        errors.append("extra_role")

    extra_limit = _call("list_operators", {"limit": 1}, 6)
    extra_limit_row = classify_not_allowed(
        extra_limit.get("packet") or {}, extra_limit.get("status") or 0, "limit"
    )
    if not extra_limit_row["ok"]:
        errors.append("extra_limit")

    extra_room_id = _call("list_operators", {"room_id": "room-does-not-exist"}, 7)
    extra_room_id_row = classify_not_allowed(
        extra_room_id.get("packet") or {}, extra_room_id.get("status") or 0, "room_id"
    )
    if not extra_room_id_row["ok"]:
        errors.append("extra_room_id")

    extra_task_id = _call("list_operators", {"task_id": "task-does-not-exist"}, 8)
    extra_task_id_row = classify_not_allowed(
        extra_task_id.get("packet") or {}, extra_task_id.get("status") or 0, "task_id"
    )
    if not extra_task_id_row["ok"]:
        errors.append("extra_task_id")

    extra_subject = _call("list_operators", {"subject": "x"}, 9)
    extra_subject_row = classify_not_allowed(
        extra_subject.get("packet") or {}, extra_subject.get("status") or 0, "subject"
    )
    if not extra_subject_row["ok"]:
        errors.append("extra_subject")

    extra_query = _call("list_operators", {"query": "github"}, 10)
    extra_query_row = classify_not_allowed(
        extra_query.get("packet") or {}, extra_query.get("status") or 0, "query"
    )
    if not extra_query_row["ok"]:
        errors.append("extra_query")

    extra_id_float = _call("list_operators", {"id": 1.5}, 11)
    extra_id_float_row = classify_not_allowed(
        extra_id_float.get("packet") or {}, extra_id_float.get("status") or 0, "id"
    )
    if not extra_id_float_row["ok"]:
        errors.append("extra_id_float")

    commons_init = _rpc(
        COMMONS_MCP,
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "titanmcp-list-operators", "version": "1"},
            },
        },
        origin="",
    )
    commons_info = ((commons_init.get("packet") or {}).get("result") or {}).get("serverInfo") or {}
    commons_listed = _rpc(
        COMMONS_MCP,
        {"jsonrpc": "2.0", "id": 13, "method": "tools/list", "params": {}},
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
        or "list_operators" in commons_names
    ):
        errors.append("commons_keep")

    return {
        "kind": "TITANMCP_LIST_OPERATORS",
        "id": ID,
        "pad_initialize": {"name": info.get("name"), "version": info.get("version")},
        "commons_initialize": {
            "name": commons_info.get("name"),
            "version": commons_info.get("version"),
        },
        "pad_has_list_operators": "list_operators" in names,
        "commons_has_list_operators": "list_operators" in commons_names,
        "empty_schema": {
            "additionalProperties": schema.get("additionalProperties") if isinstance(schema, dict) else None,
            "properties": schema.get("properties") if isinstance(schema, dict) else None,
            "required": schema.get("required") if isinstance(schema, dict) else None,
        },
        "empty_arguments": empty_row,
        "extra_id": extra_id_row,
        "extra_role": extra_role_row,
        "extra_limit": extra_limit_row,
        "extra_room_id": extra_room_id_row,
        "extra_task_id": extra_task_id_row,
        "extra_subject": extra_subject_row,
        "extra_query": extra_query_row,
        "extra_id_float": extra_id_float_row,
        "did_not_remint": list(DO_NOT_REMINT),
        "sent": 0,
        "cash": 0,
        "errors": errors,
        "verdict": "MATCH" if not errors else "FINDER-FAILED",
        "note": (
            "Unique remainder after list_assignments KEEP: list_operators empty "
            "arguments is 200 ok:true operators list count=5 store "
            "roles_and_operators_in_mcp_not_harness calibration no_tradeoff. "
            "Empty inputSchema properties={}, additionalProperties=false. "
            "Extra id and extra role are MCP isError BAD_ARGUMENT is not "
            "allowed (get_operator KEEP accepts id and role=builder). Extra "
            "limit is not allowed (list_rooms optional limit stays ok). Extra "
            "room_id is BAD_ARGUMENT is not allowed, not ROOM_NOT_FOUND. Extra "
            "task_id is not allowed (list_assignments optional). Extra subject "
            "and extra query are not allowed. Float id 1.5 is is not allowed, "
            "not must be string. Commons /mcp KEEP has no list_operators. No "
            "competition resubmission."
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
                        "kind": "TITANMCP_LIST_OPERATORS",
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
