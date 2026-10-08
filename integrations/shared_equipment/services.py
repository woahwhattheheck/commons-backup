"""Private Slack/GitHub tools shared by model and shell harnesses.

No server or provider credentials are created here. Slack uses the existing
encrypted Grok Slack vault reader, and GitHub uses gh's existing keyring.
The catalog is composed into the existing local Gemini tool gateway only.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from queue import Empty, Queue
from threading import BoundedSemaphore, Thread
from time import monotonic
from typing import Any

from integrations.shared_equipment.outcomes import effect_uncertain, tool_failed
from integrations.shared_equipment.slack_read_arguments import normalize_slack_read_arguments
from integrations.shared_equipment.source_bindings import SourceBindings
from commons_publication_policy import PublicationPolicyViolation, check_outbound_identity
from integrations.shared_equipment.provider_io import (
    EquipmentError, GitHubSlackEquipment, redacted,
)
from integrations.shared_equipment.workhandoff import (
    DEFAULT_CHANNEL_ID, DEFAULT_THREAD_TS, WorkHandoff,
)


def _string(args: dict, key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EquipmentError(f"{key} must be a nonempty string")
    return value


def _repo(args: dict) -> str:
    repo = _string(args, "repository")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise EquipmentError("repository must be owner/name")
    return repo


def _quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def _file_tree(files: Any) -> list[dict]:
    """Build the complete Git tree payload before any provider operation."""
    if not isinstance(files, list) or not files:
        raise EquipmentError("files must contain the useful task changes")
    tree = []
    for index, entry in enumerate(files):
        if not isinstance(entry, dict):
            raise EquipmentError(f"files[{index}] must be a path/content object")
        path = _string(entry, "path")
        content = entry.get("content")
        if not isinstance(content, str):
            raise EquipmentError(f"files[{index}].content must be a string")
        tree.append({"path": path, "mode": "100644", "type": "blob", "content": content})
    return tree


def _require_outbound_identity(fields: dict[str, str]) -> None:
    """Check final mapped text before any provider access."""
    decision = check_outbound_identity(fields)
    if not decision["allowed"]:
        raise PublicationPolicyViolation(decision)

def _schema(name: str, description: str, required: dict[str, Any], optional: dict[str, Any] | None = None) -> dict:
    properties = {k: {"type": v} if isinstance(v, str) else v for k, v in required.items()}
    for k, v in (optional or {}).items():
        properties[k] = {"type": v} if isinstance(v, str) else v
    return {"name": name, "description": description, "inputSchema": {"type": "object", "properties": properties, "required": list(required)}}


_TOKEN_POOL_PROVIDERS = ("grokbot", "cursor", "claude", "codex", "gemini_code_assist", "antigravity")
_TOKEN_POOL_BATCH_WAIT_SECONDS = 45.0
_TOKEN_POOL_BATCH_SLOTS = BoundedSemaphore(4)


def _token_pool_status_tool() -> dict:
    tool = _schema(
        "token_pool_status",
        "Read provider quota without starting model work or spending/resetting capacity. "
        "Use provider for one pool or providers for a batch of 1-4 distinct names. "
        "Batches preserve requested order and each outcome, wait at most 45 seconds, "
        "and share four active reader slots per process. Missing values stay null. "
        "Antigravity polling renews its existing grant only when expired and synchronizes shared custody. "
        "Omit both selectors for the original GrokBot result shape.",
        {},
        {"provider": {"type": "string", "enum": list(_TOKEN_POOL_PROVIDERS)},
         "providers": {"type": "array", "minItems": 1, "maxItems": 4, "uniqueItems": True,
                       "items": {"type": "string", "enum": list(_TOKEN_POOL_PROVIDERS)}}},
    )
    tool["inputSchema"]["not"] = {"required": ["provider", "providers"]}
    return tool


def plan_capability_fallback(arguments: dict) -> dict:
    """Suggest sustainable free quota domains; never invoke, retry or gate work.

    Route facts come from the existing connected-capability observations, not a
    second registry. Published free pricing is separate from the actual account
    plan and binding. Temporary grants and funded usage are not fleet fallback
    capacity. Metered recurring free routes need verified zero net spend;
    direct authorized tools and credentials remain available. Consumption is
    descriptive, never an admission rule.
    """
    capability = _string(arguments, "capability")
    operation_id = _string(arguments, "operation_id")
    routes = arguments.get("routes")
    if not isinstance(routes, list) or len(routes) > 500:
        raise EquipmentError("routes must be an array of at most 500 route facts")
    effect = arguments.get("effect", "read")
    previous_effect = arguments.get("previous_effect", "unknown" if effect == "write" else "none")
    if effect not in {"read", "inference", "write"} or previous_effect not in {"none", "rejected", "accepted", "unknown"}:
        raise EquipmentError("effect or previous_effect is invalid")
    sensitivity = arguments.get("input_sensitivity", "public")
    if sensitivity not in {"public", "private", "confidential"}:
        raise EquipmentError("input_sensitivity must be public, private or confidential")
    failure = arguments.get("failure") or {}
    if not isinstance(failure, dict):
        raise EquipmentError("failure must be an object")
    now = datetime.now(timezone.utc)

    def timestamp(value, field):
        if value is None or value == "":
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("timezone required")
            return parsed.astimezone(timezone.utc)
        except (ValueError, TypeError) as exc:
            raise EquipmentError(field + " must be an ISO timestamp with timezone") from exc

    def iso(value):
        return value.isoformat().replace("+00:00", "Z") if value else None

    normalized, ids = [], set()
    for index, route in enumerate(routes):
        if not isinstance(route, dict):
            raise EquipmentError(f"routes[{index}] must be an object")
        row = dict(route)
        for field in ("id", "provider", "quota_domain", "backend", "allowance_type",
                      "free_evidence", "connection_state", "binding_state", "consumption_state"):
            row[field] = _string(route, field).strip()
        if row["id"] in ids:
            raise EquipmentError("duplicate route id: " + row["id"])
        ids.add(row["id"])
        capabilities = row.get("capabilities")
        if not isinstance(capabilities, list) or any(not isinstance(item, str) or not item.strip() for item in capabilities):
            raise EquipmentError(f"routes[{index}].capabilities must be an array of nonempty strings")
        if "free_plan_verified" in row and type(row["free_plan_verified"]) is not bool:
            raise EquipmentError("free_plan_verified must be a boolean")
        remaining = row.get("quota_remaining")
        if remaining is not None and (isinstance(remaining, bool) or not isinstance(remaining, (int, float))
                                      or not math.isfinite(remaining) or remaining < 0):
            raise EquipmentError("quota_remaining must be a finite nonnegative number or null")
        scopes = row.get("input_sensitivity", ["public"])
        if not isinstance(scopes, list) or any(item not in {"public", "private", "confidential"} for item in scopes):
            raise EquipmentError("route input_sensitivity must be an array of supported scopes")
        normalized.append(row)
    failed_id = arguments.get("failed_route")
    failed = next((row for row in normalized if row["id"] == failed_id), None)
    if failed_id is not None and failed is None:
        raise EquipmentError("failed_route must identify an existing route")
    if failure and failed is None:
        raise EquipmentError("failed_route is required with provider failure evidence")
    retry_at = timestamp(failure.get("retry_not_before"), "failure.retry_not_before")
    retry_after = failure.get("retry_after")
    if retry_after is not None:
        observed = timestamp(failure.get("observed_at"), "failure.observed_at")
        if observed is None:
            raise EquipmentError("failure.observed_at is required with retry_after")
        try:
            seconds = float(retry_after)
        except (TypeError, ValueError):
            try:
                deadline = parsedate_to_datetime(str(retry_after))
                if deadline.tzinfo is None:
                    raise ValueError("timezone required")
                deadline = deadline.astimezone(timezone.utc)
            except (TypeError, ValueError, OverflowError) as exc:
                raise EquipmentError("retry_after must be provider seconds or an HTTP date") from exc
        else:
            if not math.isfinite(seconds) or seconds < 0:
                raise EquipmentError("retry_after seconds must be finite and nonnegative")
            try:
                deadline = observed + timedelta(seconds=seconds)
            except OverflowError as exc:
                raise EquipmentError("retry_after deadline is out of range") from exc
        retry_at = max(retry_at, deadline) if retry_at else deadline
    # All aliases of a provider/account/model quota share the latest cooldown.
    cooldowns = {}
    exhausted_domains = {row["quota_domain"] for row in normalized if row.get("quota_remaining") == 0}
    for row in normalized:
        deadline = timestamp(row.get("cooldown_until"), "cooldown_until")
        domain = row["quota_domain"]
        if deadline and (domain not in cooldowns or deadline > cooldowns[domain]):
            cooldowns[domain] = deadline
    if failed and retry_at:
        domain = failed["quota_domain"]
        cooldowns[domain] = max(cooldowns.get(domain, retry_at), retry_at)
    no_replay = effect == "write" and (previous_effect in {"accepted", "unknown"} or effect_uncertain(failure))
    candidates = []
    for row in normalized:
        if capability not in row["capabilities"]:
            continue
        reasons = []
        sustainable = row["allowance_type"] in {"recurring_free", "free_tier", "unmetered_free", "no_key_free"}
        if row["allowance_type"] in {"one_time_free", "conditional_free"}:
            reasons.append("TEMPORARY_ALLOWANCE_NOT_SUSTAINABLE")
        elif not sustainable:
            reasons.append("FREE_ALLOWANCE_TYPE_UNSUPPORTED")
        if row["allowance_type"] in {"recurring_free", "free_tier"} and row.get("zero_net_spend_verified") is not True:
            reasons.append("ZERO_NET_SPEND_UNVERIFIED")
        allowance_expiry = timestamp(row.get("allowance_expires_at"), "allowance_expires_at")
        if allowance_expiry and allowance_expiry <= now:
            reasons.append("FREE_ALLOWANCE_EXPIRED")
        if row.get("free_plan_verified") is not True:
            reasons.append("FREE_PLAN_UNVERIFIED")
        if row["connection_state"].lower() not in {"connected", "authenticated", "ready", "not_required"}:
            reasons.append("CONNECTION_REQUIRED")
        if row["binding_state"].lower() not in {"bound", "callable", "ready"}:
            reasons.append("BINDING_REQUIRED")
        if row["quota_domain"].lower() in {"unknown", "unmeasured"}:
            reasons.append("QUOTA_DOMAIN_UNRESOLVED")
        if row["quota_domain"] in exhausted_domains:
            reasons.append("EXHAUSTED")
        if sensitivity not in row.get("input_sensitivity", ["public"]):
            reasons.append("INPUT_SCOPE_MISMATCH")
        if failed and row["quota_domain"] == failed["quota_domain"]:
            reasons.append("SAME_QUOTA_DOMAIN")
        deadline = cooldowns.get(row["quota_domain"])
        if deadline and deadline > now:
            reasons.append("COOLDOWN")
        if no_replay:
            reasons.append("RECONCILE_EXISTING_WRITE")
        known_backend = (row["backend"].lower() not in {"unknown", "unmeasured"}
                         and "unresolved" not in row["backend"].lower())
        shared_backend = bool(failed and known_backend and row["backend"] == failed["backend"])
        candidates.append({key: row.get(key) for key in
                           ("id", "provider", "quota_domain", "backend", "connection_state", "binding_state",
                            "consumption_state", "owner", "native_tool", "quota_remaining")} |
                          {"status": "READY" if not reasons else reasons[0], "reasons": reasons,
                           "retry_not_before": iso(deadline), "shared_backend_with_failed": shared_backend,
                           "backend_independence_known": bool(failed and known_backend and
                                                               failed["backend"].lower() not in {"unknown", "unmeasured"}
                                                               and "unresolved" not in failed["backend"].lower())})
    candidates.sort(key=lambda row: (bool(row["reasons"]), row["shared_backend_with_failed"],
                                     row["consumption_state"].lower() != "producing", row["id"]))
    ready, domains = [], set()
    for row in candidates:
        if not row["reasons"] and row["quota_domain"] not in domains:
            ready.append(row)
            domains.add(row["quota_domain"])
    return {"schema": "commons.shared_equipment.fallback_plan.v1", "advisory_only": True,
            "operation_id": operation_id, "capability": capability, "effect": effect,
            "previous_effect": previous_effect, "observed_at": iso(now),
            "failed_route": failed_id, "failed_quota_domain": failed["quota_domain"] if failed else None,
            "retry_not_before": iso(retry_at), "http_status": failure.get("http_status"),
            "decision": "RECONCILE_EXISTING_WRITE" if no_replay else "USE_READY_ROUTE" if ready else "NO_READY_ALTERNATIVE",
            "recommended_route": ready[0]["id"] if ready else None, "ready_quota_domains": len(domains),
            "ready_routes": [row["id"] for row in ready], "candidates": candidates,
            "provider_calls": 0, "writes": 0, "sleeps": 0, "schedules": 0,
            "retry_layer": "caller_only", "telemetry_gates_work": False,
            "remaining_allowance_unknown_unless_measured": True}


TOOLS = [
    _token_pool_status_tool(),
    _schema("equipment_fallback_plan", "Advise capability-compatible free routes across distinct quota domains using existing observations. Preserves cooldown and operation identity; never calls providers, retries, admits peers or replays uncertain/accepted writes.",
            {"operation_id": "string", "capability": "string", "routes": {"type": "array", "maxItems": 500, "items": {"type": "object"}}},
            {"failed_route": "string", "failure": "object", "effect": {"type": "string", "enum": ["read", "inference", "write"]}, "previous_effect": {"type": "string", "enum": ["none", "rejected", "accepted", "unknown"]}, "input_sensitivity": {"type": "string", "enum": ["public", "private", "confidential"]}}),
    _schema("credential_references", "Discover credential references, configured sources, and populated/empty Claude MCP entries. Returns metadata only, equally for newcomers.", {}),
    _schema("credential_retrieve_sealed", "Retrieve an actual credential encrypted to the requester's ephemeral public key. recipient_public_key must be the raw 32-byte X25519 public key encoded as 64 lowercase hex characters. Keep the private key in the requesting runtime; only ciphertext enters this road.", {"credential_ref": "string", "recipient_public_key": "string", "transfer_id": "string", "request_id": "string", "call_id": "string"}),
    _schema("slack_read_channel", "Read a Slack channel using existing workspace access. Follow next_cursor for remaining pages.", {"channel_id": "string"}, {"oldest": "string", "latest": "string", "cursor": "string", "limit": "integer"}),
    _schema("slack_read_thread", "Read a Slack thread within optional oldest/latest timestamps. Follow next_cursor for remaining replies.", {"channel_id": "string", "thread_ts": "string"}, {"oldest": "string", "latest": "string", "cursor": "string", "limit": "integer"}),
    _schema("slack_post_message", "Post to a channel verified as internal to the authenticated workspace. Sender is the fixed existing Slack account; do not add model or peer bylines. Returns the provider timestamp and permalink.", {"channel_id": "string", "text": "string"}, {"thread_ts": "string"}),
    _schema("slack_post_external_demo_message", "Post public demo copy only to michael-external-demo (C0C7S2D5QRE), using the fixed existing Slack account and the existing outward publication checks. Reuse operation_id: accepted or uncertain sends are never repeated. Delivery requires provider readback of the sender and exact text. No channel, sender or icon override.", {"operation_id": "string", "text": "string"}, {"thread_ts": "string"}),
    _schema("slack_external_demo_message_status", "Read back an existing external demo operation without sending. Optional message_ts reconciles a provider handle recovered after an interrupted send. Reads only michael-external-demo; reuse the original operation_id.", {"operation_id": "string"}, {"message_ts": "string"}),
    _schema("commons_team_workhandoff", "Share an exact patch, tests, and result in the active BountyHub team thread. Internal Slack only; the fixed authenticated account is used, and the route reads back the actual file, message body, sender, and any provider footer. Same operation ID and content is idempotent; changed payload under that ID is rejected. No model/peer allowlist.", {"operation_id": "string", "work_id": "string", "objective": "string", "summary": "string", "patch": "string", "tests": "string", "result": "string"}, {"channel_id": {"type": "string", "default": DEFAULT_CHANNEL_ID}, "thread_ts": {"type": "string", "default": DEFAULT_THREAD_TS}}),
    _schema("commons_team_workhandoff_status", "Reconcile a prior internal Slack workhandoff by stable operation ID. Reads the current provider thread/file and returns actual sender/body/footer verification; it never sends a duplicate.", {"operation_id": "string"}, {"channel_id": {"type": "string", "default": DEFAULT_CHANNEL_ID}, "thread_ts": {"type": "string", "default": DEFAULT_THREAD_TS}}),
    _schema("slack_read_file", "Fetch a shared Slack text or patch file by file ID using the existing shared encrypted Slack credential. Same operation for every peer; no per-peer grant.", {"file_id": "string"}),
    _schema("github_read_file", "Read a UTF-8 source file and resolved blob SHA through the existing gh account. Set ref to pin a version.", {"repository": "string", "path": "string"}, {"ref": "string"}),
    _schema("github_read_issue", "Read a GitHub issue and one comment page; use comment_page for further pages.", {"repository": "string", "issue_number": "integer"}, {"comment_page": "integer"}),
    _schema("github_read_pull_request", "Read PR state, head/base SHAs, changed files and checks. Use page for further file pages.", {"repository": "string", "pull_number": "integer"}, {"page": "integer"}),
    _schema("github_add_issue_comment", "Comment on an issue or PR through the existing owner account publishing service. Optional actor selects an existing named GitHub account; omission keeps the current default. Reuse operation_id for retries; inspect its actual receipt. Available to every peer.", {"repository": "string", "issue_number": "integer", "body": "string", "operation_id": "string"}, {"actor": "string"}),
    _schema("github_update_issue_comment", "Update an existing issue/PR conversation comment through the account publishing service, preserving the comment ID. Optional actor selects an existing named GitHub account; omission keeps the current default. Reuse operation_id for retries.", {"repository": "string", "comment_id": "integer", "body": "string", "operation_id": "string"}, {"actor": "string"}),
    _schema("github_update_issue", "Update issue title/body through the existing account publishing service. Optional actor selects an existing named GitHub account; omission keeps the current default. GitHub enforces author/repository permissions. Reuse operation_id for retries.", {"repository": "string", "issue_number": "integer", "operation_id": "string"}, {"title": "string", "body": "string", "actor": "string"}),
    _schema("github_update_pull_request", "Update PR title/body through the existing account publishing service. Optional actor selects an existing named GitHub account; omission keeps the current default. Reads expected_head before publication and returns after-write head readback; it does not lock the branch. Reuse operation_id for retries.", {"repository": "string", "pull_number": "integer", "expected_head": "string", "operation_id": "string"}, {"title": "string", "body": "string", "actor": "string"}),
    _schema("github_create_branch", "Create a branch from base_ref (default main), resolving its commit internally. base_sha remains a compatible override and also accepts a ref. Returns an existing branch only when its head matches the resolved base; never moves an existing branch. Publication runs through the existing account publishing service; reuse operation_id for retries.", {"repository": "string", "branch": "string", "operation_id": "string"}, {"base_ref": {"type": "string", "default": "main", "description": "Source branch, tag, ref, or commit; resolved internally. Defaults to main."}, "base_sha": {"type": "string", "description": "Compatibility override for base_ref: an existing commit SHA or ref."}}),
    _schema("github_commit_files", "Commit UTF-8 files to an existing branch through the existing account publishing service, comparing expected_head first and again inside the named operation. Supply full file contents. Reuse operation_id for retries.", {"repository": "string", "branch": "string", "expected_head": "string", "message": "string", "operation_id": "string"}, {"files": {"type": "array", "items": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}}),
    _schema("github_edit_files", "Commit compact exact replacements using files read at expected_head. Each path and expected_blob_sha must match; each nonempty old anchor must occur exactly once. Delegates the complete atomic files to github_commit_files and its existing named-account publisher. Reuse operation_id for retries.",
            {"repository": "string", "branch": "string", "expected_head": "string", "message": "string", "operation_id": "string",
             "edits": {"type": "array", "minItems": 1, "items": {"type": "object", "additionalProperties": False,
                       "properties": {"path": {"type": "string", "minLength": 1}, "expected_blob_sha": {"type": "string", "pattern": "^[0-9a-fA-F]{40}$"},
                                      "replacements": {"type": "array", "minItems": 1, "items": {"type": "object", "additionalProperties": False,
                                                       "properties": {"old": {"type": "string", "minLength": 1}, "new": {"type": "string"}}, "required": ["old", "new"]}}},
                       "required": ["path", "expected_blob_sha", "replacements"]}}}),
    _schema("github_create_pull_request", "Open a useful PR for existing task work through the existing account publishing service. Returns an existing open PR for the same head/base on retry. Reuse operation_id for retries; head_repo is the short repository name (e.g. wavelum-frontend), never owner/name; omit when it matches the target repo name. maintainer_can_modify and transport ('graphql') pass through to the named operation.", {"repository": "string", "head": "string", "base": "string", "title": "string", "body": "string", "operation_id": "string"}, {"draft": "boolean", "head_repo": {"type": "string", "minLength": 1, "maxLength": 100, "pattern": "^(?!\\.$|\\.\\.$)[A-Za-z0-9_.-]+$", "description": "Short head repository name, not owner/name. Omit when it matches the target repo name."}, "maintainer_can_modify": "boolean", "transport": "string"}),
    _schema("github_merge_pull_request", "Merge an authorized reviewed PR through the existing account publishing service. Reads the pull head, commit identities and base branch head first and supplies head and base compare-and-swap inside the named operation; GitHub still enforces branch rules. Reuse operation_id for retries.", {"repository": "string", "pull_number": "integer", "expected_head": "string", "operation_id": "string"}, {"merge_method": "string"}),
    _schema("cua_s1_form", "Score a form in one already-open Chrome tab with the official CUA-S1-FORMS checkpoint. Defaults to a dry run; execute and submit are separate explicit booleans. Reports observed actions and failures, and never opens a tab.",
            {"url": "string", "form_title": "string", "entities": {"type": "array", "items": {"type": "object", "properties": {"label": {"type": "string"}, "value": {"type": "string"}}, "required": ["label", "value"]}}},
            {"checkpoint": "string", "execute": "boolean", "submit": "boolean", "min_confidence": "number", "cdp_endpoint": "string"}),
]


for _demo_tool in TOOLS:
    if _demo_tool["name"] in {"slack_post_external_demo_message", "slack_external_demo_message_status"}:
        _demo_tool["annotations"] = {
            "readOnlyHint": _demo_tool["name"] == "slack_external_demo_message_status",
            "idempotentHint": True,
            "openWorldHint": True,
        }


class ServiceEquipment(GitHubSlackEquipment):
    def __init__(self, *, gh: str = "gh", slack_token_loader=None, gh_runner=None, opener=None, credential_sources=None, workhandoff_journal_path: Path | None = None):
        super().__init__(gh=gh, slack_token_loader=slack_token_loader, gh_runner=gh_runner, opener=opener)
        self.credential_sources = credential_sources
        self._work_handoff = WorkHandoff(self, journal_path=workhandoff_journal_path)
        self._external_demo_messages = None

    def _slack_write_route_verified(self, channel_id: str | None = None) -> bool:
        # Internal workspace coordination bypasses the outward sender hook.
        # Keep the destination boundary for Slack Connect/external channels.
        return channel_id is None or self._work_handoff._channel_info(channel_id) is not None

    def tools(self, **_kwargs) -> list[dict]:
        return TOOLS.copy()

    def call(self, name: str, arguments: dict) -> dict:
        try:
            result = self._call(name, arguments)
            return {"isError": tool_failed(result), "result": redacted(result),
                    "uncertain": effect_uncertain(result)}
        except Exception as exc:
            result = {
                "isError": True,
                "error": type(exc).__name__,
                "message": redacted(str(exc)),
                "code": getattr(exc, "code", type(exc).__name__),
                "uncertain": bool(getattr(exc, "uncertain", False)),
            }
            for attribute in (
                "incident",
                "delivered",
                "matched_fields",
                "matched_terms",
                "private_instruction",
                "http_status",
                "retry_after",
                "rate_limit_remaining",
                "rate_limit_reset",
                "rate_limit_resource",
                "rate_limit_kind",
            ):
                value = getattr(exc, attribute, None)
                if value is not None:
                    result[attribute] = list(value) if isinstance(value, tuple) else value
            return redacted(result)

    def _token_pool_batch(self, selected: list[str]) -> dict:
        observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        deadline = monotonic() + _TOKEN_POOL_BATCH_WAIT_SECONDS
        results: list[dict | None] = [None] * len(selected)
        completed: Queue = Queue()
        pending: set[int] = set()

        def failure(provider: str, status: str, error_class: str, **fields) -> dict:
            return {"schema": "commons.token_pool_status.v1", "provider": provider,
                    "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "ok": False, "status": status, "pools": [],
                    "error": {"class": error_class, "code": "token_pool_status_" + status},
                    **fields}

        def read_one(index: int, provider: str) -> None:
            try:
                outcome = self._call("token_pool_status", {"provider": provider})
                if not isinstance(outcome, dict):
                    outcome = failure(provider, "error", "UnexpectedPayloadType")
            except Exception as exc:
                outcome = failure(provider, "error", type(exc).__name__)
            finally:
                # A caller timeout does not cancel the reader or release its slot.
                _TOKEN_POOL_BATCH_SLOTS.release()
            completed.put((index, outcome))

        for index, provider in enumerate(selected):
            if not _TOKEN_POOL_BATCH_SLOTS.acquire(blocking=False):
                results[index] = failure(provider, "busy", "BatchReadersBusy", read_started=False)
                continue
            pending.add(index)
            try:
                Thread(target=read_one, args=(index, provider), daemon=True).start()
            except Exception as exc:
                _TOKEN_POOL_BATCH_SLOTS.release()
                pending.remove(index)
                results[index] = failure(provider, "error", type(exc).__name__, read_started=False)

        while pending:
            try:
                # Once the deadline passes, still drain already-queued outcomes.
                index, outcome = completed.get(timeout=max(0.0, deadline - monotonic()))
            except Empty:
                break
            results[index] = outcome
            pending.remove(index)
        for index in pending:
            results[index] = failure(selected[index], "timeout", "TimeoutError",
                                     read_started=True, reader_may_still_be_running=True)

        return {"schema": "commons.token_pool_status_batch.v1", "observed_at": observed_at,
                "ok": all(isinstance(result, dict) and result.get("ok") is True for result in results),
                "results": results}

    def _call(self, name: str, a: dict) -> dict:
        if name == "equipment_fallback_plan":
            return plan_capability_fallback(a)
        a = normalize_slack_read_arguments(name, a)
        if name == "cua_s1_form":
            from cua_s1.schema import Entity
            from host.cua_s1_browser import connect_cdp
            from host.cua_s1_forms import run_with_driver

            url = _string(a, "url")
            title = _string(a, "form_title")
            raw_entities = a.get("entities")
            if not isinstance(raw_entities, list) or any(
                not isinstance(item, dict) or not isinstance(item.get("label"), str)
                or not item["label"].strip() or not isinstance(item.get("value"), str)
                or not item["value"].strip() for item in raw_entities
            ):
                raise EquipmentError("entities must be an array of nonempty label/value objects")
            entities = [Entity(item["label"], item["value"]) for item in raw_entities]
            execute, submit = a.get("execute", False), a.get("submit", False)
            if not isinstance(execute, bool) or not isinstance(submit, bool):
                raise EquipmentError("execute and submit must be booleans")
            confidence = a.get("min_confidence", 0.5)
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
                raise EquipmentError("min_confidence must be a number")
            checkpoint = a.get("checkpoint")
            if checkpoint is None:
                from huggingface_hub import hf_hub_download
                checkpoint = hf_hub_download("cua-ai/cua-s1-forms", "cua-s1-forms.safetensors", local_files_only=True)
                hf_hub_download("cua-ai/cua-s1-forms", "cua-s1-forms.json", local_files_only=True)
            else:
                checkpoint = _string(a, "checkpoint")
            endpoint = a.get("cdp_endpoint", "http://127.0.0.1:9222")
            if not isinstance(endpoint, str) or not endpoint.strip():
                raise EquipmentError("cdp_endpoint must be a nonempty string")
            driver, target = connect_cdp(url, endpoint=endpoint, allow_submit=submit)
            try:
                return run_with_driver(checkpoint=Path(checkpoint), driver=driver, target=target,
                                       form_title=title, entities=entities, min_confidence=confidence,
                                       execute=execute, submit=submit)
            finally:
                driver.close()
        if name == "token_pool_status":
            if "provider" in a and "providers" in a:
                raise EquipmentError("Use provider or providers, not both")
            if "providers" in a:
                selected = a["providers"]
                if (not isinstance(selected, list) or not 1 <= len(selected) <= 4
                        or any(not isinstance(provider, str) or provider not in _TOKEN_POOL_PROVIDERS
                               for provider in selected)
                        or len(set(selected)) != len(selected)):
                    raise EquipmentError("providers must contain 1-4 distinct supported names")
                return self._token_pool_batch(list(selected))
            provider = a.get("provider", "grokbot")
            if provider == "codex":
                from .codex_pool import poll_codex_pool
                return poll_codex_pool()
            from .token_pools import poll_token_pools, poll_cursor_pool, poll_claude_pool
            from .gemini_code_assist import poll_gemini_code_assist_pool
            from .antigravity_pool import poll_antigravity_pool
            readers = {"grokbot": poll_token_pools, "cursor": poll_cursor_pool,
                       "claude": poll_claude_pool, "gemini_code_assist": poll_gemini_code_assist_pool,
                       "antigravity": poll_antigravity_pool}
            if not isinstance(provider, str) or provider not in readers:
                raise EquipmentError("provider must be grokbot, cursor, claude, codex, gemini_code_assist or antigravity")
            from .credential_transfer import CredentialSources
            sources = self.credential_sources or CredentialSources(gh=self.gh, gh_runner=self.gh_runner)
            recovery = None
            if provider == "antigravity":
                try:
                    from .antigravity_grant import ensure_antigravity_grant
                    recovery = ensure_antigravity_grant(sources=sources)
                except Exception:
                    recovery = {
                        "provider": "antigravity", "operation": "existing_grant_renewal",
                        "ok": False, "status": "unavailable", "refreshed": False,
                        "primary_custody_updated": None, "shared_custody_updated": None,
                        "expires_at": None,
                        "error": {"code": "existing_grant_recovery_failed", "http_status": None},
                    }
            outcome = readers[provider](credential_reader=sources.read)
            # Custody maintenance must not hide a usable primary quota result.
            if recovery and (not recovery.get("ok") or recovery.get("refreshed")
                             or recovery.get("shared_custody_updated")):
                outcome["credential_recovery"] = recovery
            return outcome
        if name == "credential_references":
            from .credential_transfer import credential_references
            return credential_references(self.credential_sources)
        if name == "credential_retrieve_sealed":
            from .credential_transfer import CredentialSources
            sources = self.credential_sources or CredentialSources(gh=self.gh, gh_runner=self.gh_runner)
            return sources.retrieve_sealed(a)
        if name == "commons_team_workhandoff":
            return self._work_handoff.submit(a)
        if name == "commons_team_workhandoff_status":
            return self._work_handoff.status(a)
        if name == "slack_read_file":
            return self._work_handoff.read_file(a)
        if name == "slack_read_channel":
            p = {"channel": _string(a, "channel_id"), "limit": min(100, max(1, int(a.get("limit", 50))))}
            p.update({k: a[k] for k in ("oldest", "latest", "cursor") if a.get(k)})
            return self.slack("conversations.history", p)
        if name == "slack_read_thread":
            p = {"channel": _string(a, "channel_id"), "ts": _string(a, "thread_ts"), "limit": min(100, max(1, int(a.get("limit", 50))))}
            p.update({k: a[k] for k in ("oldest", "latest", "cursor") if a.get(k)})
            return self.slack("conversations.replies", p)
        if name in {"slack_post_external_demo_message", "slack_external_demo_message_status"}:
            if self._external_demo_messages is None:
                from .external_demo import ExternalDemoMessages
                self._external_demo_messages = ExternalDemoMessages(self,
                    journal_path=self._work_handoff.path.with_name("external_demo.sqlite3"))
            route = self._external_demo_messages
            return route.submit(a) if name == "slack_post_external_demo_message" else route.status(a)
        if name == "slack_post_message":
            channel_id = _string(a, "channel_id")
            if not self._slack_write_route_verified(channel_id):
                return {"ok": False, "state": "PUBLISHER_ROUTE_REQUIRED", "delivered": False,
                        "error": "destination is external, pending, archived, or unavailable in this workspace"}
            self._slack_route_preverified = channel_id
            p = {"channel": channel_id, "text": _string(a, "text"), "unfurl_links": False, "unfurl_media": False, "parse": "none"}
            if a.get("thread_ts"):
                p["thread_ts"] = a["thread_ts"]
            result = self.slack("chat.postMessage", p)
            if result.get("ok"):
                # The message already exists. Optional link lookup cannot erase its handle.
                message = result.get("message")
                sent = {"ok": True, "channel": result["channel"], "ts": result["ts"],
                        "permalink": None, "text": message.get("text") if isinstance(message, dict) else None}
                try:
                    link = self.slack("chat.getPermalink", {"channel": result["channel"], "message_ts": result["ts"]})
                    sent["permalink"] = link.get("permalink")
                    if not link.get("ok"):
                        sent["permalink_error"] = redacted(link.get("error", "permalink_unavailable"))
                except Exception:
                    sent["permalink_error"] = "permalink_unavailable"
                return sent
            return result
        repo = _repo(a)
        root = "repos/" + repo
        publication_tools = {
            "github_add_issue_comment": ("issue.comment.create", "issue_number"),
            "github_update_issue_comment": ("issue.comment.update", "comment_id"),
            "github_update_issue": ("issue.update", "issue_number"),
            "github_update_pull_request": ("pull.update", "pull_number"),
        }
        if name in publication_tools:
            from .github_publication import publish
            operation, number_key = publication_tools[name]
            actor = _string(a, "actor") if "actor" in a else None
            number = a.get(number_key)
            if isinstance(number, bool) or not isinstance(number, int) or number < 1:
                raise EquipmentError(number_key + " must be a positive integer")
            owner, repository_name = repo.split("/")
            outgoing = {"owner": owner, "repo": repository_name, number_key: number}
            fields = ("body",) if "comment" in name else ("title", "body")
            for field in fields:
                if field in a:
                    if not isinstance(a[field], str) or field == "title" and not a[field].strip():
                        raise EquipmentError(field + " must be text")
                    outgoing[field] = a[field]
            if not any(field in outgoing for field in fields):
                raise EquipmentError("supply the intended title or body")
            _require_outbound_identity({
                field: outgoing[field] for field in fields if field in outgoing
            })
            expected = None
            if name == "github_update_pull_request":
                expected = _string(a, "expected_head")
                current = self.github(f"{root}/pulls/{number}")
                if current["head"]["sha"] != expected:
                    raise EquipmentError("PR head changed; read the current PR before updating its description")
            result = publish(operation, outgoing, _string(a, "operation_id"), actor=actor)
            if expected is not None and result["ok"]:
                # Publication already succeeded. A failed read cannot erase its receipt.
                try:
                    current = self.github(f"{root}/pulls/{number}")
                    result["head_after"] = current["head"]["sha"]
                    result["head_unchanged"] = result["head_after"] == expected
                except Exception:
                    result["readback_error"] = "PR head readback unavailable; retain publication receipt"
            return result
        if name == "github_read_file":
            path = "/".join(_quote(part) for part in _string(a, "path").split("/"))
            endpoint = root + "/contents/" + path
            if a.get("ref"):
                endpoint += "?ref=" + _quote(a["ref"])
            value = self.github(endpoint)
            if not isinstance(value, dict) or value.get("type") != "file":
                raise EquipmentError("path is not a file; supply an exact source path")
            source = value
            if value.get("encoding") == "none":
                # Contents omits inline bytes for large files. Read the resolved
                # immutable blob so a populated file cannot become empty source.
                source = self.github(root + "/git/blobs/" + _quote(value["sha"]))
                if not isinstance(source, dict) or source.get("encoding") != "base64":
                    raise EquipmentError("GitHub returned no readable blob content")
            content = base64.b64decode(source.get("content", "")).decode("utf-8")
            return {"repository": repo, "path": value["path"], "sha": value["sha"], "url": value["html_url"], "content": redacted(content), "size": value.get("size")}
        if name == "github_read_issue":
            number = int(a["issue_number"])
            page = max(1, int(a.get("comment_page", 1)))
            issue = self.github(f"{root}/issues/{number}")
            comments = self.github(f"{root}/issues/{number}/comments?per_page=100&page={page}")
            return {"issue": issue, "comments": comments, "comment_page": page, "may_have_more_comments": len(comments) == 100}
        if name == "github_read_pull_request":
            number = int(a["pull_number"])
            page = max(1, int(a.get("page", 1)))
            pr = self.github(f"{root}/pulls/{number}")
            files = self.github(f"{root}/pulls/{number}/files?per_page=100&page={page}")
            sha = pr["head"]["sha"]
            return {"pull_request": pr, "files": files, "may_have_more_files": len(files) == 100,
                "checks": self.github(f"{root}/commits/{sha}/check-runs"),
                "status": self.github(f"{root}/commits/{sha}/status")}
        if name == "github_create_branch":
            branch = _string(a, "branch")
            _require_outbound_identity({"branch": branch})
            # A caller names the source; GitHub resolves it. Keep explicit
            # commit callers compatible, including their existing call shape,
            # and accept legacy base_sha='main' without an extra peer round trip.
            if "base_sha" in a:
                base = _string(a, "base_sha").strip()
            elif "base_ref" in a:
                base = _string(a, "base_ref").strip()
            else:
                base = "main"
            if re.fullmatch(r"[0-9a-fA-F]{40}", base):
                sha = base.lower()
            else:
                # The commits endpoint documents heads/... and tags/...;
                # retain that namespace when given a fully qualified Git ref.
                if base.startswith(("refs/heads/", "refs/tags/")):
                    base = base[5:]
                resolved = self.github(root + "/commits/" + _quote(base))
                sha = resolved.get("sha") if isinstance(resolved, dict) else None
                if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
                    raise EquipmentError("GitHub did not resolve the source ref to a commit")
            try:
                found = self.github(root + "/git/ref/heads/" + _quote(branch))
            except EquipmentError as exc:
                if exc.http_status != 404:
                    raise
            else:
                if (not isinstance(found, dict) or not isinstance(found.get("object"), dict)
                        or not isinstance(found["object"].get("sha"), str)):
                    raise EquipmentError("GitHub returned an invalid branch reference",
                                         code="github_response_invalid")
                if found["object"]["sha"] != sha:
                    raise EquipmentError("existing branch has a different head")
                return {"created": False, **found}
            from .github_publication import publish
            owner, repository_name = repo.split("/")
            return publish("branch.create",
                           {"owner": owner, "repo": repository_name, "branch": branch, "sha": sha},
                           _string(a, "operation_id"), actor=owner)
        if name == "github_edit_files":
            from .file_edits import prepare_file_edits, require_sha, validate_file_edits
            edits = validate_file_edits(a.get("edits"))
            branch = _string(a, "branch")
            expected = require_sha(a.get("expected_head"), "expected_head")
            message, operation_id = _string(a, "message"), _string(a, "operation_id")
            _require_outbound_identity({"branch": branch, "message": message})
            ref = self.github(root + "/git/ref/heads/" + _quote(branch))
            if ref["object"]["sha"] != expected:
                raise EquipmentError("branch head changed; read current head and reconcile edits")
            sources = {}
            for edit in edits:
                path = "/".join(_quote(part) for part in edit["path"].split("/"))
                value = self.github(root + "/contents/" + path + "?ref=" + _quote(expected))
                if (not isinstance(value, dict) or value.get("type") != "file"
                        or value.get("path") != edit["path"] or value.get("sha") != edit["expected_blob_sha"]):
                    raise EquipmentError("pinned file path or blob SHA changed: " + edit["path"])
                if value.get("encoding") == "none":
                    blob = self.github(root + "/git/blobs/" + _quote(edit["expected_blob_sha"]))
                    if not isinstance(blob, dict) or blob.get("sha") != edit["expected_blob_sha"]:
                        raise EquipmentError("GitHub returned an invalid resolved blob")
                    value = {**blob, "path": edit["path"]}
                sources[edit["path"]] = value
            files = prepare_file_edits(edits, sources)
            return self._call("github_commit_files", {"repository": repo, "branch": branch,
                              "expected_head": expected, "message": message,
                              "operation_id": operation_id, "files": files})
        if name == "github_commit_files":
            branch, expected = _string(a, "branch"), _string(a, "expected_head")
            message = _string(a, "message")
            _require_outbound_identity({"branch": branch, "message": message})
            tree = _file_tree(a.get("files"))
            ref = self.github(root + "/git/ref/heads/" + _quote(branch))
            if ref["object"]["sha"] != expected:
                raise EquipmentError("branch head changed; read current head and reconcile files")
            additions = [{"path": entry["path"],
                          "contents": base64.b64encode(entry["content"].encode("utf-8")).decode("ascii")}
                         for entry in tree]
            headline, _, message_body = message.partition("\n")
            outgoing_message = {"headline": headline}
            if message_body.strip():
                outgoing_message["body"] = message_body.lstrip("\n")
            from .github_publication import publish
            owner, repository_name = repo.split("/")
            return publish("commit.create",
                           {"owner": owner, "repo": repository_name, "branch": branch,
                            "expectedHeadOid": expected, "message": outgoing_message,
                            "fileChanges": {"additions": additions}},
                           _string(a, "operation_id"), actor=owner)
        if name == "github_create_pull_request":
            owner = repo.split("/")[0]
            head, base = _string(a, "head"), _string(a, "base")
            title, body = _string(a, "title"), _string(a, "body")
            _require_outbound_identity({
                "head": head,
                "base": base,
                "title": title,
                "body": body,
            })
            head_repo = None
            if "head_repo" in a:
                head_repo = _string(a, "head_repo")
                if (re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", head_repo) is None
                        or head_repo in {".", ".."}):
                    raise EquipmentError(
                        "head_repo must be a short repository name, not owner/name",
                        code="invalid_head_repo", uncertain=False,
                    )
            query = urllib.parse.urlencode({"state": "open", "head": head if ":" in head else owner + ":" + head, "base": base})
            existing = self.github(root + "/pulls?" + query)
            if existing:
                return {"created": False, "pull_request": existing[0]}
            outgoing = {"owner": owner, "repo": repo.split("/")[1], "head": head, "base": base,
                        "title": title, "body": body, "draft": bool(a.get("draft", False))}
            if head_repo is not None:
                outgoing["head_repo"] = head_repo
            if "maintainer_can_modify" in a:
                outgoing["maintainer_can_modify"] = bool(a["maintainer_can_modify"])
            if "transport" in a:
                outgoing["transport"] = _string(a, "transport")
            from .github_publication import publish
            head_owner = head.split(":", 1)[0] if ":" in head else owner
            return publish("pull.create", outgoing, _string(a, "operation_id"), actor=head_owner)
        if name == "github_merge_pull_request":
            number = a.get("pull_number")
            if isinstance(number, bool) or not isinstance(number, int) or number < 1:
                raise EquipmentError("pull_number must be a positive integer")
            expected = _string(a, "expected_head")
            method = a.get("merge_method", "squash")
            if method not in {"merge", "squash", "rebase"}:
                raise EquipmentError("merge_method must be merge, squash, or rebase")

            pull = self.github(f"{root}/pulls/{number}")
            if pull.get("head", {}).get("sha") != expected:
                raise EquipmentError("PR head changed; read the current PR before merging")
            inherited = {
                "pull_request.title": str(pull.get("title") or ""),
                "pull_request.body": str(pull.get("body") or ""),
            }
            if method in {"merge", "rebase"}:
                for page in range(1, 11):
                    commits = self.github(
                        f"{root}/pulls/{number}/commits?per_page=100&page={page}"
                    )
                    if not isinstance(commits, list):
                        raise EquipmentError("GitHub returned invalid PR commit metadata")
                    for commit in commits:
                        sha = str(commit.get("sha") or "unknown")
                        metadata = commit.get("commit", {})
                        if not isinstance(metadata, dict):
                            metadata = {}
                        message = metadata.get("message")
                        if isinstance(message, str):
                            inherited[f"commits[{sha}].message"] = message
                        for role in ("author", "committer"):
                            person = metadata.get(role)
                            if isinstance(person, dict):
                                for key in ("name", "email"):
                                    value = person.get(key)
                                    if isinstance(value, str):
                                        inherited[f"commits[{sha}].{role}.{key}"] = value
                            account = commit.get(role)
                            if isinstance(account, dict) and isinstance(account.get("login"), str):
                                inherited[f"commits[{sha}].{role}.login"] = account["login"]
                    if len(commits) < 100:
                        break
                else:
                    raise EquipmentError(
                        "PR commit metadata exceeds the bounded identity preflight"
                    )
            _require_outbound_identity(inherited)

            base_ref = (pull.get("base") or {}).get("ref")
            if not base_ref:
                raise EquipmentError("pull request base ref unavailable")
            base = self.github(root + "/branches/" + _quote(base_ref))
            base_sha = (base.get("commit") or {}).get("sha") if isinstance(base, dict) else None
            if not isinstance(base_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", base_sha):
                raise EquipmentError("pull request base head unavailable")
            owner, repository_name = repo.split("/")
            outgoing = {"owner": owner, "repo": repository_name, "pull_number": number,
                        "expectedHeadOid": expected, "expectedBaseHeadOid": base_sha,
                        "merge_method": method}
            if method in {"merge", "squash"}:
                outgoing["commit_title"] = f"Integrate pull request #{number}"
                outgoing["commit_message"] = "Integrate the reviewed change."
            from .github_publication import publish
            return publish("pull.merge", outgoing, _string(a, "operation_id"), actor=owner)
        raise EquipmentError("unknown equipment tool: " + name)


class CombinedCatalog:
    """Add private local equipment without publishing it to the public MCP."""
    def __init__(self, commons, services=None, *, source_bindings=None, extensions=None):
        self.commons = commons
        self.services = services or ServiceEquipment()
        self.source_bindings = (source_bindings if isinstance(source_bindings, SourceBindings)
                                else SourceBindings(source_bindings))
        if extensions is None:
            from integrations.command_center.equipment import CommandCenterEquipment
            from .provider_apis import GroqExaEquipment
            from .free_model_apis import FreeModelEquipment
            from .connected_tools import ConnectedToolEquipment
            self.extensions = [ConnectedToolEquipment(self), CommandCenterEquipment(),
                               GroqExaEquipment(), FreeModelEquipment()]
        else:
            self.extensions = list(extensions)

    def tools(self, **kwargs):
        # Keep the advertised catalog consistent with call() dispatch precedence:
        # extensions, then shared services, then the public Commons MCP. Some
        # public deployments expose overlapping Slack or credential names.
        # Advertise the first implementation once so model clients do not see
        # ambiguous duplicate names or route a call differently than expected.
        ordered = [
            *(tool for extension in self.extensions for tool in extension.tools()),
            *self.services.tools(),
            *self.commons.tools(**kwargs),
        ]
        unique = []
        seen = set()
        for tool in ordered:
            name = tool.get("name") if isinstance(tool, dict) else None
            if isinstance(name, str) and name not in seen:
                seen.add(name)
                unique.append(tool)
        return unique

    def resolve_source(self, account_ref, service=None):
        """Select an existing concrete reader without changing provider arguments."""
        return self.source_bindings.resolve(account_ref, service)

    def call(self, name, arguments, *, account_ref=None, service=None):
        if account_ref is not None:
            return self.resolve_source(account_ref, service).call(name, arguments)
        if service is not None:
            raise EquipmentError("service requires an explicit account_ref",
                                 code="source_binding_unresolved")
        for extension in self.extensions:
            if name in {tool["name"] for tool in extension.tools()}:
                result = extension.call(name, arguments)
                if name in {"gemini_get_request", "gemini_events", "grokbot_inspect", "grokbot_events"}:
                    # Use the catalog's existing center and already-read event
                    # page. Only an exact canonical dispatch binding may roll.
                    from integrations.command_center.equipment import CommandCenterEquipment
                    center = next((item for item in self.extensions
                                   if isinstance(item, CommandCenterEquipment)), None)
                    if center is not None:
                        try:
                            from integrations.command_center.swarm_lifecycle import observe_result
                            lifecycle = observe_result(center.center, name, result)
                        except Exception as exc:
                            lifecycle = {"status": "deferred", "reason": getattr(exc, "kind", type(exc).__name__)}
                            if getattr(exc, "retry_after", None) is not None:
                                lifecycle["retry_after"] = exc.retry_after
                        if isinstance(result, dict):
                            result = {**result, "swarm_lifecycle": lifecycle}
                return result
        if name in {tool["name"] for tool in self.services.tools()}:
            return self.services.call(name, arguments)
        return self.commons.call(name, arguments)


class _EmptyCommonsCatalog:
    """CLI has no public Commons MCP sidecar; keep CombinedCatalog shape."""

    def tools(self, **_kwargs):
        return []

    def call(self, name, arguments):
        raise EquipmentError("unknown equipment tool: " + str(name))


def build_cli_catalog(*, grokbot_base_url: str | None = None, claude_headless_root: str | None = None):
    """Slack/GitHub services + GrokBot lifecycle (G2) + headless Claude (C1), no public MCP tools."""
    from integrations.shared_equipment.peers import ClaudeHeadlessEquipment, GrokBotEquipment

    catalog = CombinedCatalog(_EmptyCommonsCatalog())
    if grokbot_base_url:
        catalog.extensions.append(GrokBotEquipment(grokbot_base_url))
    else:
        catalog.extensions.append(GrokBotEquipment())
    catalog.extensions.append(ClaudeHeadlessEquipment(claude_headless_root))
    return catalog


# Non-secret harness inventory. Same for every peer; not an allowlist.
HARNESS_ROADS = [
    {
        "road_id": "owner_pc_shared_equipment",
        "kind": "loopback_http",
        "base_url": "http://127.0.0.1:8878",
        "discover": "GET /v1/tools",
        "call": "POST /v1/tools/call",
        "note": "Stable request_id + call_id. Service custody stays in existing host stores.",
    },
    {
        "road_id": "owner_pc_grokbot_control",
        "kind": "grokbot_control",
        "base_url": "http://127.0.0.1:8881",
        "discover": "python -m integrations.shared_equipment.services manifest",
        "call": "grokbot_* tools via catalog/call",
        "note": "GrokBot pools only. Occupant field is optional metadata on the pool run, not role_id.",
    },
    {
        "road_id": "workspace_shared_equipment",
        "kind": "slack_request_return",
        "channel_id": "C0BU51F1PL3",
        "thread_ts": "1788567066.179399",
        "discover": "equipment_capability_manifest envelope",
        "call": "commons_equipment_request envelope",
        "write_disabled": False,
        "note": "Configured internal Slack carrier dispatches existing request/call IDs without an outward sender gate. Live readiness comes from the deployed gateway health and matching result; source discovery does not claim deployment.",
    },
]

CREDENTIAL_CUSTODY = [
    {
        "service": "slack",
        "custody": "existing_encrypted_vault",
        "loader": "integrations.grok_slack.handoff.read_vault",
        "bytes_in_model_context": False,
    },
    {
        "service": "github",
        "custody": "existing_gh_os_keyring",
        "transport": "gh api --hostname github.com",
        "bytes_in_model_context": False,
    },
    {
        "service": "grokbot",
        "custody": "loopback_control",
        "base_url_default": "http://127.0.0.1:8881",
        "bytes_in_model_context": False,
    },
]


def build_capability_manifest(*, catalog=None, peer: str | None = None) -> dict:
    """Inventory callable operations + roads without secret bytes.

    ``peer`` is accepted and ignored so newcomers and legacy peers share one
    discovery surface. Transferable roles describe responsibility only; they
    never gate this manifest.
    """
    del peer  # parity: label never changes the inventory
    equipment = catalog or build_cli_catalog()
    operations = []
    for tool in equipment.tools():
        name = tool["name"]
        operations.append(
            {
                "operation_id": name,
                "name": name,
                "description": tool.get("description", ""),
                "inputSchema": tool.get("inputSchema", {"type": "object"}),
            }
        )
    operations.sort(key=lambda row: row["operation_id"])
    return {
        "schema": "commons.shared_equipment.capability_manifest.v1",
        "same_operations_for_every_peer": True,
        "peer_label_does_not_change_inventory": True,
        "credential_bytes_in_manifest": False,
        "peer_argument_ignored": True,
        "credential_custody": list(CREDENTIAL_CUSTODY),
        "roads": [dict(road) for road in HARNESS_ROADS],
        "operations": operations,
        "operation_count": len(operations),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("catalog", "call", "manifest", "fallback-plan"))
    parser.add_argument("--routes-file", type=Path, help="existing connected observations with tool_fleet.free_pool_routes")
    parser.add_argument("--capability", help="exact capability requested by this worker")
    parser.add_argument("--operation-id", help="existing logical operation ID; preserve across recovery")
    parser.add_argument("--failed-route", help="route ID of the observed failure")
    parser.add_argument("--effect", choices=("read", "inference", "write"), default="read")
    parser.add_argument("--previous-effect", choices=("none", "rejected", "accepted", "unknown"))
    parser.add_argument("--input-sensitivity", choices=("public", "private", "confidential"), default="public")
    parser.add_argument("--http-status", type=int, help="actual observed provider status")
    parser.add_argument("--retry-after", help="actual provider seconds or HTTP date")
    parser.add_argument("--failure-observed-at", help="provider response observation time with timezone")
    parser.add_argument("--retry-not-before", help="actual provider cooldown deadline with timezone")
    parser.add_argument(
        "--grokbot-control",
        default=None,
        help="Override GrokBot control base URL (default http://127.0.0.1:8881)",
    )
    parser.add_argument(
        "--claude-headless-root",
        default=None,
        help="Runs root for headless Claude (default ~/.claude/commons_headless or CLAUDE_HEADLESS_ROOT)",
    )
    args = parser.parse_args()
    if args.operation == "fallback-plan":
        try:
            if args.routes_file is None:
                raise EquipmentError("--routes-file is required for fallback-plan")
            observations = json.loads(args.routes_file.read_text(encoding="utf-8"))
            request = {"operation_id": args.operation_id, "capability": args.capability,
                       "routes": observations if isinstance(observations, list) else observations["tool_fleet"]["free_pool_routes"],
                       "effect": args.effect, "input_sensitivity": args.input_sensitivity,
                       "failure": {key: value for key, value in {
                           "http_status": args.http_status, "retry_after": args.retry_after,
                           "observed_at": args.failure_observed_at,
                           "retry_not_before": args.retry_not_before}.items() if value is not None}}
            if args.failed_route is not None:
                request["failed_route"] = args.failed_route
            if args.previous_effect is not None:
                request["previous_effect"] = args.previous_effect
            print(json.dumps(redacted(plan_capability_fallback(request)), ensure_ascii=False))
            return 0
        except (OSError, ValueError, KeyError, TypeError, EquipmentError) as exc:
            print(json.dumps({"isError": True, "code": "invalid_fallback_request",
                              "message": redacted(str(exc)), "uncertain": False}))
            return 2
    request = None
    if args.operation == "call":
        try:
            request = json.load(sys.stdin)
            if not isinstance(request, dict):
                raise ValueError("request must be a JSON object")
            _string(request, "name")
            if not isinstance(request.get("arguments", {}), dict):
                raise ValueError("arguments must be a JSON object")
        except (ValueError, EquipmentError) as exc:
            print(json.dumps({"isError": True, "code": "invalid_cli_request",
                              "message": redacted(str(exc)), "uncertain": False}))
            return 2

    dispatched = False
    try:
        equipment = build_cli_catalog(
            grokbot_base_url=args.grokbot_control,
            claude_headless_root=args.claude_headless_root,
        )
        if args.operation == "manifest":
            result = build_capability_manifest(catalog=equipment)
        elif args.operation == "catalog":
            result = {"tools": equipment.tools()}
        else:
            dispatched = True
            result = equipment.call(request["name"], request.get("arguments", {}))
    except Exception as exc:
        # An extension can raise after dispatch. Without explicit outcome
        # metadata, do not tell a shell caller that replay is safe.
        result = {"isError": True, "error": type(exc).__name__,
                  "code": getattr(exc, "code", type(exc).__name__),
                  "message": redacted(str(exc)),
                  "uncertain": bool(getattr(exc, "uncertain", dispatched))}
    print(json.dumps(redacted(result), ensure_ascii=False))
    if effect_uncertain(result):
        return 3
    return 1 if tool_failed(result) else 0


if __name__ == "__main__":
    raise SystemExit(main())
