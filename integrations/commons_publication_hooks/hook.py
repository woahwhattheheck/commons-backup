"""Native client hook for owner-controlled outward publication; never schedules peers."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Installer places the shared module beside this hook; repository use resolves
# the same source, without a claim vault, credentials, network or background job.
_directory = Path(__file__).resolve().parent
sys.path.insert(
    0,
    str(
        _directory
        if (_directory / "commons_publication_policy.py").is_file()
        else _directory.parents[1]
    ),
)
from commons_publication_policy import (
    POLICY_CONTEXT,
    check_outbound_identity,
    check_publication,
)

SWARM_CONTEXT = (
    "Standing owner rules: read RULES.md before starting work. "
    "GPTs are major builders and leads. No agent peer review: agents don't "
    "review, approve or gate each other's work, and nobody waits on a review "
    "before merging (owner, 2026-09-22). Don't write tests or run test suites; "
    "run the real thing and read the exit code. "
    "Outward communications must use the owner's identity only. "
    "Internal TJLabs Slack coordination is not outward publication and is "
    "exempt from the publication hook, including channels, threads and DMs. "
)

_GITHUB_FIELDS = (
    ("create_issue", ("title", "body"), True),
    ("update_issue", ("title", "body"), True),
    ("add_comment_to_issue", ("comment", "body"), True),
    ("add_issue_comment", ("body", "comment"), True),
    ("update_issue_comment", ("comment", "body"), True),
    ("create_pull_request", ("title", "body", "head", "head_branch", "base", "base_branch"), True),
    ("update_pull_request", ("title", "body", "base", "base_branch"), True),
    ("reply_to_review_comment", ("comment",), True),
    ("update_review_comment", ("comment",), True),
    ("dismiss_pull_request_review", ("message",), True),
    ("create_file", ("message", "branch"), False),
    ("update_file", ("message", "branch"), False),
    ("delete_file", ("message", "branch"), False),
    ("create_commit", ("message",), False),
    ("merge_pull_request", ("commit_title", "commit_message"), False),
    ("create_branch", ("branch_name",), False),
    ("update_ref", ("branch_name",), False),
)

_GITHUB_NO_TEXT_MUTATIONS = {
    "add_issue_assignees",
    "remove_issue_assignees",
    "remove_issue_label",
    "add_reaction_to_issue_comment",
    "add_reaction_to_pr",
    "add_reaction_to_pr_review_comment",
    "remove_reaction_from_issue_comment",
    "remove_reaction_from_pr",
    "remove_reaction_from_pr_review_comment",
    "convert_pull_request_to_draft",
    "mark_pull_request_ready_for_review",
    "request_pull_request_reviewers",
    "remove_pull_request_reviewers",
    "resolve_review_thread",
    "unresolve_review_thread",
    "lock_issue_conversation",
    "unlock_issue_conversation",
    "rerun_failed_workflow_run_jobs",
    "rerun_workflow_job",
}

_GATEWAY_FIELDS = {
    "issue.create": (("title", "body"), True),
    "issue.update": (("title", "body"), True),
    "issue.comment.create": (("body", "comment"), True),
    "issue.comment.update": (("body", "comment"), True),
    "pull.create": (("title", "body", "head", "base"), True),
    "pull.update": (("title", "body", "base"), True),
    "pull.comment.create": (("body", "comment"), True),
    "pull.comment.update": (("body", "comment"), True),
    "pull.review.create": (("body", "review"), True),
    "file.put": (("message", "branch"), False),
    "commit.create": (("message",), False),
    "commit.merge": (("commit_title", "commit_message", "message"), False),
    "branch.create": (("branch", "branch_name", "ref"), False),
    "branch.update": (("branch", "branch_name", "ref"), False),
    "release.create": (("name", "title", "body", "tag_name"), True),
    "release.update": (("name", "title", "body", "tag_name"), True),
}

_READ_VERBS = {
    "fetch",
    "get",
    "list",
    "read",
    "search",
    "download",
    "compare",
    "check",
    "peek",
}
_MUTATION_WORDS = {
    "add",
    "append",
    "comment",
    "commit",
    "create",
    "delete",
    "edit",
    "fire",
    "merge",
    "post",
    "publish",
    "reply",
    "schedule",
    "send",
    "submit",
    "update",
    "upload",
    "write",
}


def _event_args(event: dict) -> dict | None:
    args = event.get("tool_input") or {}
    # Cursor beforeMCPExecution supplies JSON text; generic/native tool hooks
    # supply an object. Parsing is in memory and never logs submitted content.
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (ValueError, TypeError):
            return None
    return args if isinstance(args, dict) else None


def _provider_text(event: dict, tool: str) -> str:
    mcp = event.get("mcp_context") or {}
    if not isinstance(mcp, dict):
        mcp = {}
    return " ".join(
        str(value or "")
        for value in (
            tool,
            event.get("mcp_server_name"),
            event.get("mcp_server_url"),
            event.get("url"),
            mcp.get("server_name"),
            mcp.get("server_url"),
        )
    ).lower()


def _tool_is(tool: str, operation: str) -> bool:
    return tool == operation or any(
        tool.endswith(separator + operation)
        for separator in ("_", ".", "/", ":")
    )


def _tool_words(value: str) -> set[str]:
    return {
        word
        for word in re.split(r"[^a-z0-9]+|_+", value.lower())
        if word
    }


def _is_mutation(value: str) -> bool:
    return bool(_tool_words(value) & _MUTATION_WORDS)


def _is_read(value: str) -> bool:
    words = _tool_words(value)
    return bool(words & _READ_VERBS) and not bool(words & _MUTATION_WORDS)


def _string_fields(args: dict, names: tuple[str, ...]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for name in names:
        value = args.get(name)
        if isinstance(value, str):
            fields[name] = value
    return fields


def _string_list_fields(
    args: dict, name: str, *, field_prefix: str | None = None
) -> dict[str, str]:
    value = args.get(name)
    if isinstance(value, str):
        return {field_prefix or name: value}
    if not isinstance(value, list):
        return {}
    prefix = field_prefix or name
    return {
        f"{prefix}[{index}]": item
        for index, item in enumerate(value)
        if isinstance(item, str)
    }


def _private_control_fields(fields: dict[str, str]) -> list[str]:
    """Find a private gateway object only after it enters an outward field."""
    matches: list[str] = []
    decoder = json.JSONDecoder()
    for name, value in fields.items():
        for start, character in enumerate(value):
            if character != "{":
                continue
            try:
                candidate, _end = decoder.raw_decode(value[start:])
            except (TypeError, ValueError):
                continue
            if (
                isinstance(candidate, dict)
                and candidate.get("schema") == "commons-github-gateway/v1"
                and {"operation_id", "operation", "args"}.issubset(candidate)
            ):
                matches.append(name)
                break
    return matches


def _hold_decision(
    *,
    code: str,
    instruction: str,
    fields: list[str] | None = None,
) -> dict:
    return {
        "allowed": False,
        "code": code,
        "rule": code,
        "message": "Outward operation was not delivered. " + instruction,
        "incident": False,
        "delivered": False,
        "matched_fields": list(fields or ()),
        "matched_terms": [],
        "private_instruction": instruction,
    }


def _selected_verdict(fields: dict[str, str], *, prose: bool) -> dict:
    envelope_fields = _private_control_fields(fields)
    if envelope_fields:
        return _hold_decision(
            code="private_control_envelope",
            fields=envelope_fields,
            instruction=(
                "Remove the private gateway/control envelope from the outward "
                "field and execute its nested operation directly. Do not create "
                "an issue, comment, email, ticket, or incident as a fallback."
            ),
        )

    identity = check_outbound_identity(fields)
    if not identity["allowed"]:
        return identity

    if not prose or not fields:
        return identity

    prose_names = {
        "subject", "title", "body", "comment", "review", "text",
        "content", "speech",
    }
    prose_fields = {
        name: value
        for name, value in fields.items()
        if name.rsplit(".", 1)[-1] in prose_names
    }
    if not prose_fields:
        return identity
    subject = "\n".join(
        value
        for name, value in prose_fields.items()
        if name.rsplit(".", 1)[-1] in {"subject", "title"}
    )
    body = "\n".join(
        value
        for name, value in prose_fields.items()
        if name.rsplit(".", 1)[-1] not in {"subject", "title"}
    )
    verdict = check_publication(body, subject)
    if verdict["allowed"]:
        return verdict

    verdict = dict(verdict)
    verdict.setdefault("incident", False)
    verdict.setdefault("delivered", False)
    verdict.setdefault("matched_fields", list(fields))
    verdict.setdefault("matched_terms", [])
    verdict.setdefault("private_instruction", verdict.get("message", "Revise and retry."))
    return verdict


def _github_fields(tool: str, args: dict) -> tuple[dict[str, str], bool] | None:
    if _tool_is(tool, "add_review_to_pr"):
        fields = _string_fields(args, ("review",))
        comments = args.get("file_comments")
        if isinstance(comments, list):
            for index, comment in enumerate(comments):
                if isinstance(comment, dict) and isinstance(comment.get("body"), str):
                    fields[f"file_comments[{index}].body"] = comment["body"]
        return fields, True

    if _tool_is(tool, "add_issue_labels"):
        return _string_list_fields(args, "labels"), False
    if _tool_is(tool, "label_pr"):
        return _string_list_fields(args, "label"), False

    for operation, names, prose in _GITHUB_FIELDS:
        if _tool_is(tool, operation):
            fields = _string_fields(args, names)
            if operation in {"create_issue", "update_issue"}:
                fields.update(_string_list_fields(args, "labels"))
            return fields, prose

    if any(_tool_is(tool, operation) for operation in _GITHUB_NO_TEXT_MUTATIONS):
        return {}, False

    # Blob/tree contents and file paths are source/control data. The later
    # commit message is the outward metadata boundary.
    if _tool_is(tool, "create_blob") or _tool_is(tool, "create_tree"):
        return {}, False

    return None


def _gateway_fields(args: dict) -> tuple[dict[str, str], bool] | None:
    operation = str(args.get("operation") or "").strip().lower()
    if not operation:
        return None
    mapping = _GATEWAY_FIELDS.get(operation)
    if mapping is None:
        return None
    nested = args.get("args")
    if not isinstance(nested, dict):
        return {}, mapping[1]
    names, prose = mapping
    fields = _string_fields(nested, names)
    if operation in {"issue.create", "issue.update", "pull.update"}:
        fields.update(_string_list_fields(nested, "labels"))
    if operation == "pull.review.create":
        for collection in ("file_comments", "comments"):
            comments = nested.get(collection)
            if isinstance(comments, list):
                for index, comment in enumerate(comments):
                    if isinstance(comment, dict) and isinstance(comment.get("body"), str):
                        fields[f"{collection}[{index}].body"] = comment["body"]
    return fields, prose


def _route_hold(provider: str) -> dict:
    return _hold_decision(
        code="outbound_field_mapping_missing",
        instruction=(
            "This mutating route has no explicit outward-field mapping. Add or "
            "use a verified owner-controlled mapping; do not send a fallback notification."
        ),
    )


def publication_verdict(event: dict) -> dict | None:
    """Select final provider-visible fields; never recursively scan envelopes."""
    tool = str(event.get("tool_name") or "").strip().lower()
    args = _event_args(event)
    if args is None:
        return None
    provider = _provider_text(event, tool)

    if "slack" in provider:
        # Owner-connected TJLabs Slack is the internal swarm coordination
        # surface, not outward publication. Apply this exemption before any
        # sender, field, tool-spelling or prose check, including edits/uploads
        # and Claude's native MCP route. The Slack transport still owns its
        # schema, destination permissions and provider rate limits.
        return None

    gateway_route = (
        args.get("schema") == "commons-github-gateway/v1"
        or ("github" in provider and "gateway" in provider)
    )
    if gateway_route:
        operation = str(args.get("operation") or "").strip().lower()
        if _is_read(operation):
            return None
        gateway = _gateway_fields(args)
        if gateway is None or not isinstance(args.get("args"), dict):
            return _route_hold(provider)
        if operation == "commit.merge":
            method = str(args["args"].get("merge_method") or "").strip().lower()
            if method not in {"merge", "squash"}:
                return _route_hold(provider)
        fields, prose = gateway
        if not fields:
            return _route_hold(provider)
        return _selected_verdict(fields, prose=prose)

    if "github" in provider:
        if _tool_is(tool, "merge_pull_request"):
            method = str(args.get("merge_method") or "").strip().lower()
            title = args.get("commit_title")
            message = args.get("commit_message")
            if (
                method not in {"merge", "squash"}
                or not isinstance(title, str)
                or not title.strip()
                or not isinstance(message, str)
                or not message.strip()
            ):
                return _hold_decision(
                    code="outbound_field_mapping_missing",
                    instruction=(
                        "Use the checked managed merge route with merge or squash "
                        "and explicit commit_title and commit_message, then retry."
                    ),
                )
        selected = _github_fields(tool, args)
        if selected is not None:
            fields, prose = selected
            return _selected_verdict(fields, prose=prose)
        return None if _is_read(tool) else _route_hold(provider)

    managed = any(name in provider for name in ("commons", "discord"))
    if not managed:
        return None
    operation = str(args.get("operation") or tool)
    if _is_read(operation):
        return None
    if not _is_mutation(operation):
        return None

    # Legacy managed tools without a typed operation may expose direct authored
    # prose. Select only named top-level fields; payload/model_packet/args and
    # all other control/source values remain private and uninspected.
    fields = _string_fields(
        args,
        ("subject", "title", "body", "comment", "text", "message", "content", "speech"),
    )
    if fields:
        return _selected_verdict(fields, prose=True)
    return _route_hold(provider)


def private_feedback(verdict: dict) -> str:
    """Serialize a content-free denial for the invoking agent only."""
    code = str(verdict.get("code") or "publication_blocked")
    if code == "outbound_identity_attribution":
        state = "OUTBOUND_IDENTITY_BLOCKED"
    elif code == "private_control_envelope":
        state = "PRIVATE_CONTROL_ENVELOPE_BLOCKED"
    elif code in {"outbound_sender_identity_unverified", "outbound_field_mapping_missing"}:
        state = "OUTBOUND_ROUTE_BLOCKED"
    else:
        state = "PUBLICATION_BLOCKED"
    return json.dumps(
        {
            "state": state,
            "delivered": False,
            "incident": False,
            "matched_fields": list(verdict.get("matched_fields") or ()),
            "matched_terms": list(verdict.get("matched_terms") or ()),
            "instruction": str(
                verdict.get("private_instruction")
                or verdict.get("message")
                or "Revise the outward fields and retry."
            ),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def handle(event: dict) -> dict:
    name = str(event.get("hook_event_name") or "")
    if name in {"SessionStart", "UserPromptSubmit"}:
        return {
            "hookSpecificOutput": {
                "hookEventName": name,
                "additionalContext": (
                    SWARM_CONTEXT
                    + "When publishing through Commons, chat, code-hosting, "
                    + "or other owner-operated channels: "
                    + POLICY_CONTEXT
                ),
            }
        }
    if name != "PreToolUse":
        return {}
    verdict = publication_verdict(event)
    if verdict is None or verdict["allowed"]:
        return {}

    # Return the correction only through the invoking client's private tool
    # result. Never create a provider-visible notification about this hold.
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": private_feedback(verdict),
        },
    }


if __name__ == "__main__":
    event = json.load(sys.stdin)
    print(json.dumps(handle(event), ensure_ascii=False))
