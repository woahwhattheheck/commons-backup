"""Slack route mapping for the fixed authenticated Commons Slack tools.

Slack's installed connector binds the authenticated owner-connected account;
the tool inputs have no author override. This recognizes only those exact tool
schemas. Model, seat and role never participate in the route decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SlackRoute:
    kind: str
    selected_fields: dict[str, str]
    sender_contract: str = "fixed owner-connected provider account; no caller author override"


CONNECTOR_SEND_FIELDS = {"channel_id", "message", "draft_id", "reply_broadcast", "thread_ts", "unfurl_app_links"}
GATEWAY_SEND_FIELDS = {"channel_id", "text", "thread_ts"}
CLAUDE_CLOUD_SEND_FIELDS = {"channel_id", "message", "thread_ts"}
CONNECTOR_UPLOAD_FIELDS = {"filename", "content_length", "snippet_type", "alt_txt"}
CONNECTOR_COMPLETE_FIELDS = {"file_id", "channel_id", "thread_ts", "title", "initial_comment"}
IDENTITY_OVERRIDE_FIELDS = {"author", "username", "icon_emoji", "icon_url", "as_user", "user_name", "display_name"}


def _suffix(tool: str, name: str) -> bool:
    return tool == name or tool.endswith("_" + name) or tool.endswith("." + name) or tool.endswith("/" + name) or tool.endswith(":" + name)


def slack_route_mapping(tool: str, args: dict[str, Any]) -> SlackRoute | None:
    """Return a known fixed-sender route, rejecting malformed/unknown shapes.

    Return None for non-Slack tools. The caller should keep unknown Slack writes
    on the existing `_route_hold` path. Internal Slack text is exempt from the
    public publication classifier; this function only validates the transport
    schema and fixed-authenticated-sender contract.
    """
    name = str(tool or "").lower()
    if "slack" not in name:
        return None
    connector_route = name.startswith("mcp__codex_apps__slack_")
    gateway_route = name.startswith("mcp__commons_gateway__slack_")
    claude_cloud_route = name.startswith("mcp__slack__")
    if not (connector_route or gateway_route or claude_cloud_route):
        return SlackRoute("unknown", {})
    if not isinstance(args, dict) or IDENTITY_OVERRIDE_FIELDS.intersection(args):
        return SlackRoute("invalid", {})

    if connector_route and _suffix(name, "slack_slack_get_file_upload_url"):
        if (set(args) <= CONNECTOR_UPLOAD_FIELDS and isinstance(args.get("filename"), str)
                and isinstance(args.get("content_length"), int) and not isinstance(args.get("content_length"), bool)):
            return SlackRoute("private_upload_stage", {})
        return SlackRoute("invalid", {})

    if connector_route and _suffix(name, "slack_slack_send_message"):
        if (set(args) <= CONNECTOR_SEND_FIELDS and isinstance(args.get("channel_id"), str)
                and isinstance(args.get("message"), str)):
            return SlackRoute("connector_send", {"message": args["message"]})
        return SlackRoute("invalid", {})

    if claude_cloud_route and name == "mcp__slack__slack_send_message":
        if (set(args) <= CLAUDE_CLOUD_SEND_FIELDS and isinstance(args.get("channel_id"), str)
                and isinstance(args.get("message"), str)
                and ("thread_ts" not in args or isinstance(args["thread_ts"], str))):
            # This is the same owner-connected internal Slack transport as the
            # installed connector. Its native spelling is not a sender hold.
            return SlackRoute("connector_send", {"message": args["message"]})
        return SlackRoute("invalid", {})

    if gateway_route and _suffix(name, "slack_post_message"):
        if (set(args) <= GATEWAY_SEND_FIELDS and isinstance(args.get("channel_id"), str)
                and isinstance(args.get("text"), str)):
            return SlackRoute("gateway_send", {"text": args["text"]})
        return SlackRoute("invalid", {})

    if connector_route and _suffix(name, "slack_slack_complete_file_upload"):
        if (set(args) <= CONNECTOR_COMPLETE_FIELDS and isinstance(args.get("file_id"), str)
                and isinstance(args.get("channel_id"), str)):
            fields = {key: args[key] for key in ("initial_comment", "title") if isinstance(args.get(key), str)}
            return SlackRoute("connector_complete_upload", fields)
        return SlackRoute("invalid", {})

    # Keep all other Slack mutations on the current explicit route-hold path.
    return SlackRoute("unknown", {})


def slack_route_allowed(tool: str, args: dict[str, Any]) -> bool:
    route = slack_route_mapping(tool, args)
    return route is not None and route.kind in {
        "connector_send", "gateway_send", "private_upload_stage"
    }
