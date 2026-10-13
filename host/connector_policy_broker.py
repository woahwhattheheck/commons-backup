"""Fail-closed policy broker for connector-backed GitHub and Slack writes.

This module is deliberately vendor-token-free. It validates a narrowly typed action
request before a connector call is made and emits a deterministic, secret-free
receipt that can be appended to an audit log. It does not call GitHub or Slack.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import posixpath
import re
from typing import Any, Mapping

SCHEMA = "commons.connector-policy-broker/v1"
SUPPORTED_ACTIONS = frozenset(
    {
        "github.create_branch",
        "github.commit_files",
        "github.create_pull_request",
        "slack.post_message",
        "slack.upload_file",
    }
)
_GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_CHANNEL_RE = re.compile(r"^[CDG][A-Z0-9]{8,}$")
_CORRELATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class PolicyError(ValueError):
    """Raised for invalid policy configuration."""


@dataclass(frozen=True)
class Policy:
    policy_version: str
    github_repositories: frozenset[str] = field(default_factory=frozenset)
    github_branch_prefixes: tuple[str, ...] = ("agent/", "agent-canary/")
    github_path_prefixes: tuple[str, ...] = ()
    slack_channel_ids: frozenset[str] = field(default_factory=frozenset)
    default_branch: str = "main"
    require_draft_pr: bool = True
    allow_workflow_writes: bool = False
    workflow_write_requires_human_approval: bool = True
    workflow_approval_sha256s: frozenset[str] = field(default_factory=frozenset)
    max_files_per_commit: int = 32
    max_file_bytes: int = 512_000
    max_commit_bytes: int = 2_000_000
    max_slack_message_bytes: int = 32_000
    max_slack_file_bytes: int = 2_000_000

    def __post_init__(self) -> None:
        if type(self.policy_version) is not str or not self.policy_version.strip():
            raise PolicyError("policy_version must be a non-empty string")
        if type(self.default_branch) is not str or not _valid_branch(self.default_branch):
            raise PolicyError("default_branch is invalid")
        if type(self.github_repositories) is not frozenset:
            raise PolicyError("github_repositories must be a frozenset")
        if type(self.slack_channel_ids) is not frozenset:
            raise PolicyError("slack_channel_ids must be a frozenset")
        if type(self.workflow_approval_sha256s) is not frozenset:
            raise PolicyError("workflow_approval_sha256s must be a frozenset")
        if type(self.github_branch_prefixes) is not tuple or type(self.github_path_prefixes) is not tuple:
            raise PolicyError("github prefix collections must be tuples")
        for repo in self.github_repositories:
            if type(repo) is not str or not _GITHUB_REPO_RE.fullmatch(repo):
                raise PolicyError("github_repositories contains an invalid repository")
        for channel in self.slack_channel_ids:
            if type(channel) is not str or not _CHANNEL_RE.fullmatch(channel):
                raise PolicyError("slack_channel_ids contains an invalid channel id")
        for prefix in self.github_branch_prefixes:
            if type(prefix) is not str or not prefix.endswith("/") or not _valid_branch(prefix + "x"):
                raise PolicyError("github_branch_prefixes contains an invalid directory prefix")
        for prefix in self.github_path_prefixes:
            _normalize_repo_prefix(prefix)
        for name in (
            "max_files_per_commit",
            "max_file_bytes",
            "max_commit_bytes",
            "max_slack_message_bytes",
            "max_slack_file_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise PolicyError(f"{name} must be a positive integer")
        for digest in self.workflow_approval_sha256s:
            if type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise PolicyError("workflow_approval_sha256s contains an invalid digest")
        for name in (
            "require_draft_pr",
            "allow_workflow_writes",
            "workflow_write_requires_human_approval",
        ):
            if type(getattr(self, name)) is not bool:
                raise PolicyError(f"{name} must be boolean")


@dataclass(frozen=True)
class Decision:
    allowed: bool
    code: str
    action: str
    resource: str | None
    request_sha256: str
    policy_sha256: str
    receipt_sha256: str
    correlation_id: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "allowed": self.allowed,
            "code": self.code,
            "action": self.action,
            "resource": self.resource,
            "correlation_id": self.correlation_id,
            "request_sha256": self.request_sha256,
            "policy_sha256": self.policy_sha256,
            "receipt_sha256": self.receipt_sha256,
        }


def canary_policy(*, repository: str, slack_channel_id: str) -> Policy:
    """Return a deliberately narrow policy for inert connector canaries."""
    return Policy(
        policy_version="connector-canary/v1",
        github_repositories=frozenset({repository}),
        github_branch_prefixes=("agent-canary/",),
        github_path_prefixes=(".connector-canary/",),
        slack_channel_ids=frozenset({slack_channel_id}),
        require_draft_pr=True,
        allow_workflow_writes=False,
        max_files_per_commit=4,
        max_file_bytes=64_000,
        max_commit_bytes=128_000,
        max_slack_message_bytes=4_000,
        max_slack_file_bytes=128_000,
    )


def authorize(request: Mapping[str, Any], policy: Policy) -> Decision:
    """Validate *request* against *policy* and return a deterministic decision."""
    if type(request) is not dict:
        return _decision({}, policy, False, "REQUEST_NOT_OBJECT", "", None, None)
    try:
        req = _copy_json_object(request)
    except (TypeError, ValueError):
        return _decision({}, policy, False, "REQUEST_NOT_STRICT_JSON", "", None, None)

    action = req.get("action")
    correlation = req.get("correlation_id")
    if not isinstance(action, str) or action not in SUPPORTED_ACTIONS:
        return _decision(req, policy, False, "UNSUPPORTED_ACTION", str(action or ""), None, correlation if isinstance(correlation, str) else None)
    if not isinstance(correlation, str) or not _CORRELATION_RE.fullmatch(correlation):
        return _decision(req, policy, False, "INVALID_CORRELATION_ID", action, None, None)

    validators = {
        "github.create_branch": _authorize_create_branch,
        "github.commit_files": _authorize_commit_files,
        "github.create_pull_request": _authorize_pull_request,
        "slack.post_message": _authorize_slack_message,
        "slack.upload_file": _authorize_slack_file,
    }
    try:
        allowed, code, resource = validators[action](req, policy)
    except (TypeError, ValueError, UnicodeError):
        allowed, code, resource = False, "INVALID_REQUEST", None
    return _decision(req, policy, allowed, code, action, resource, correlation)


def workflow_approval_subject_sha256(request: Mapping[str, Any]) -> str:
    """Hash the exact workflow-write request body excluding its approval proof.

    A trusted approval service can retain this digest in Policy.workflow_approval_sha256s.
    The caller cannot authorize itself by merely supplying a boolean or opaque token.
    """
    if type(request) is not dict:
        raise TypeError("request must be a plain dict")
    req = _copy_json_object(request)
    if req.get("action") != "github.commit_files" or "workflow_approval_sha256" not in req:
        raise ValueError("workflow approval is only defined for github.commit_files")
    subject = dict(req)
    subject["workflow_approval_sha256"] = None
    return hashlib.sha256(canonical_json(subject)).hexdigest()


def verify_decision(request: Mapping[str, Any], policy: Policy, receipt: Mapping[str, Any]) -> bool:
    """Recompute a decision and require byte-level canonical equality."""
    try:
        expected = canonical_json(authorize(request, policy).as_dict())
        observed = canonical_json(_copy_json_object(receipt))
    except (TypeError, ValueError, UnicodeError):
        return False
    return expected == observed


def canonical_json(value: Any) -> bytes:
    """Canonical UTF-8 JSON used for hashes and exact receipt verification."""
    normalized = _copy_json_value(value)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _authorize_create_branch(req: dict[str, Any], policy: Policy) -> tuple[bool, str, str | None]:
    if set(req) != {"action", "correlation_id", "repository", "branch", "base_sha"}:
        return False, "SCHEMA_MISMATCH", None
    repo = req["repository"]
    branch = req["branch"]
    base_sha = req["base_sha"]
    if not _repo_allowed(repo, policy):
        return False, "REPOSITORY_NOT_ALLOWED", _safe_resource(repo)
    if not isinstance(branch, str) or not _valid_branch(branch):
        return False, "INVALID_BRANCH", repo
    if branch == policy.default_branch:
        return False, "DEFAULT_BRANCH_DIRECT_WRITE_DENIED", f"{repo}:{branch}"
    if not _branch_allowed(branch, policy):
        return False, "BRANCH_PREFIX_NOT_ALLOWED", f"{repo}:{branch}"
    if not isinstance(base_sha, str) or not _SHA_RE.fullmatch(base_sha):
        return False, "BASE_SHA_REQUIRED", f"{repo}:{branch}"
    return True, "ALLOW", f"{repo}:{branch}"


def _authorize_commit_files(req: dict[str, Any], policy: Policy) -> tuple[bool, str, str | None]:
    if set(req) != {"action", "correlation_id", "repository", "branch", "expected_head_sha", "force", "files", "workflow_approval_sha256"}:
        return False, "SCHEMA_MISMATCH", None
    repo = req["repository"]
    branch = req["branch"]
    if not _repo_allowed(repo, policy):
        return False, "REPOSITORY_NOT_ALLOWED", _safe_resource(repo)
    if not isinstance(branch, str) or not _valid_branch(branch):
        return False, "INVALID_BRANCH", repo
    if branch == policy.default_branch:
        return False, "DEFAULT_BRANCH_DIRECT_WRITE_DENIED", f"{repo}:{branch}"
    if not _branch_allowed(branch, policy):
        return False, "BRANCH_PREFIX_NOT_ALLOWED", f"{repo}:{branch}"
    if not isinstance(req["expected_head_sha"], str) or not _SHA_RE.fullmatch(req["expected_head_sha"]):
        return False, "EXPECTED_HEAD_SHA_REQUIRED", f"{repo}:{branch}"
    if req["force"] is not False:
        return False, "FORCE_UPDATE_DENIED", f"{repo}:{branch}"
    approval = req["workflow_approval_sha256"]
    if approval is not None and (not isinstance(approval, str) or not re.fullmatch(r"[0-9a-f]{64}", approval)):
        return False, "WORKFLOW_APPROVAL_INVALID", f"{repo}:{branch}"
    files = req["files"]
    if not isinstance(files, list) or not files or len(files) > policy.max_files_per_commit:
        return False, "FILE_COUNT_INVALID", f"{repo}:{branch}"

    seen: set[str] = set()
    total = 0
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "content_utf8"}:
            return False, "FILE_SCHEMA_MISMATCH", f"{repo}:{branch}"
        path = _normalize_repo_path(item["path"])
        if path in seen:
            return False, "DUPLICATE_PATH", f"{repo}:{branch}"
        seen.add(path)
        if policy.github_path_prefixes and not any(path.startswith(prefix) for prefix in policy.github_path_prefixes):
            return False, "PATH_PREFIX_NOT_ALLOWED", f"{repo}:{path}"
        content = item["content_utf8"]
        if not isinstance(content, str) or "\x00" in content:
            return False, "CONTENT_NOT_UTF8_TEXT", f"{repo}:{path}"
        size = len(content.encode("utf-8"))
        if size > policy.max_file_bytes:
            return False, "FILE_TOO_LARGE", f"{repo}:{path}"
        total += size
        if total > policy.max_commit_bytes:
            return False, "COMMIT_TOO_LARGE", f"{repo}:{branch}"
        if path.startswith(".github/workflows/"):
            if not policy.allow_workflow_writes:
                return False, "WORKFLOW_WRITE_DENIED", f"{repo}:{path}"
            if policy.workflow_write_requires_human_approval:
                subject = workflow_approval_subject_sha256(req)
                if approval != subject or subject not in policy.workflow_approval_sha256s:
                    return False, "WORKFLOW_APPROVAL_REQUIRED", f"{repo}:{path}"
    if approval is not None and not any(item["path"].startswith(".github/workflows/") for item in files):
        return False, "UNEXPECTED_WORKFLOW_APPROVAL", f"{repo}:{branch}"
    return True, "ALLOW", f"{repo}:{branch}"


def _authorize_pull_request(req: dict[str, Any], policy: Policy) -> tuple[bool, str, str | None]:
    if set(req) != {"action", "correlation_id", "repository", "head", "base", "draft"}:
        return False, "SCHEMA_MISMATCH", None
    repo = req["repository"]
    head = req["head"]
    base = req["base"]
    draft = req["draft"]
    if not _repo_allowed(repo, policy):
        return False, "REPOSITORY_NOT_ALLOWED", _safe_resource(repo)
    if not isinstance(head, str) or not _valid_branch(head) or not _branch_allowed(head, policy):
        return False, "HEAD_BRANCH_NOT_ALLOWED", repo
    if base != policy.default_branch:
        return False, "BASE_BRANCH_NOT_ALLOWED", f"{repo}:{_safe_resource(base)}"
    if type(draft) is not bool:
        return False, "DRAFT_FLAG_INVALID", f"{repo}:{head}"
    if policy.require_draft_pr and draft is not True:
        return False, "DRAFT_PR_REQUIRED", f"{repo}:{head}"
    return True, "ALLOW", f"{repo}:{head}->{base}"


def _authorize_slack_message(req: dict[str, Any], policy: Policy) -> tuple[bool, str, str | None]:
    if set(req) != {"action", "correlation_id", "channel_id", "text", "unfurl_links", "unfurl_media"}:
        return False, "SCHEMA_MISMATCH", None
    channel = req["channel_id"]
    if not _channel_allowed(channel, policy):
        return False, "CHANNEL_NOT_ALLOWED", _safe_resource(channel)
    text = req["text"]
    if not isinstance(text, str) or not text or "\x00" in text:
        return False, "MESSAGE_INVALID", channel
    if len(text.encode("utf-8")) > policy.max_slack_message_bytes:
        return False, "MESSAGE_TOO_LARGE", channel
    if req["unfurl_links"] is not False or req["unfurl_media"] is not False:
        return False, "UNFURL_MUST_BE_DISABLED", channel
    return True, "ALLOW", channel


def _authorize_slack_file(req: dict[str, Any], policy: Policy) -> tuple[bool, str, str | None]:
    if set(req) != {"action", "correlation_id", "channel_id", "filename", "size_bytes", "sha256"}:
        return False, "SCHEMA_MISMATCH", None
    channel = req["channel_id"]
    if not _channel_allowed(channel, policy):
        return False, "CHANNEL_NOT_ALLOWED", _safe_resource(channel)
    filename = req["filename"]
    if not isinstance(filename, str) or not filename or filename in {".", ".."} or "/" in filename or "\\" in filename or "\x00" in filename:
        return False, "FILENAME_INVALID", channel
    size = req["size_bytes"]
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0 or size > policy.max_slack_file_bytes:
        return False, "FILE_SIZE_INVALID", channel
    digest = req["sha256"]
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        return False, "FILE_SHA256_REQUIRED", channel
    return True, "ALLOW", f"{channel}:{filename}"


def _decision(
    request: Mapping[str, Any],
    policy: Policy,
    allowed: bool,
    code: str,
    action: str,
    resource: str | None,
    correlation_id: str | None,
) -> Decision:
    request_sha = hashlib.sha256(canonical_json(request)).hexdigest()
    policy_payload = {
        "policy_version": policy.policy_version,
        "github_repositories": sorted(policy.github_repositories),
        "github_branch_prefixes": list(policy.github_branch_prefixes),
        "github_path_prefixes": list(policy.github_path_prefixes),
        "slack_channel_ids": sorted(policy.slack_channel_ids),
        "default_branch": policy.default_branch,
        "require_draft_pr": policy.require_draft_pr,
        "allow_workflow_writes": policy.allow_workflow_writes,
        "workflow_write_requires_human_approval": policy.workflow_write_requires_human_approval,
        "workflow_approval_sha256s": sorted(policy.workflow_approval_sha256s),
        "max_files_per_commit": policy.max_files_per_commit,
        "max_file_bytes": policy.max_file_bytes,
        "max_commit_bytes": policy.max_commit_bytes,
        "max_slack_message_bytes": policy.max_slack_message_bytes,
        "max_slack_file_bytes": policy.max_slack_file_bytes,
    }
    policy_sha = hashlib.sha256(canonical_json(policy_payload)).hexdigest()
    unsigned = {
        "schema": SCHEMA,
        "allowed": allowed,
        "code": code,
        "action": action,
        "resource": resource,
        "correlation_id": correlation_id,
        "request_sha256": request_sha,
        "policy_sha256": policy_sha,
    }
    receipt_sha = hashlib.sha256(canonical_json(unsigned)).hexdigest()
    return Decision(allowed, code, action, resource, request_sha, policy_sha, receipt_sha, correlation_id)


def _repo_allowed(repo: Any, policy: Policy) -> bool:
    return isinstance(repo, str) and _GITHUB_REPO_RE.fullmatch(repo) is not None and repo in policy.github_repositories


def _channel_allowed(channel: Any, policy: Policy) -> bool:
    return isinstance(channel, str) and _CHANNEL_RE.fullmatch(channel) is not None and channel in policy.slack_channel_ids


def _valid_branch(branch: str) -> bool:
    if not _BRANCH_RE.fullmatch(branch):
        return False
    if branch.startswith("/") or branch.endswith("/") or branch.endswith("."):
        return False
    if ".." in branch or "//" in branch or "@{" in branch or "\\" in branch or "\x00" in branch:
        return False
    return True


def _branch_allowed(branch: str, policy: Policy) -> bool:
    return any(branch.startswith(prefix) for prefix in policy.github_branch_prefixes)


def _normalize_repo_prefix(prefix: Any) -> str:
    if not isinstance(prefix, str) or not prefix or not prefix.endswith("/"):
        raise PolicyError("github_path_prefixes must be non-empty directory prefixes ending in /")
    normalized = _normalize_repo_path(prefix + "x")[:-1]
    if normalized != prefix:
        raise PolicyError("github_path_prefixes must already be normalized")
    return prefix


def _normalize_repo_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ValueError("invalid repository path")
    if value.startswith("/") or value.endswith("/"):
        raise ValueError("repository path must be a file path")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("ambiguous repository path")
    normalized = posixpath.normpath(value)
    if normalized != value or normalized.startswith("../"):
        raise ValueError("repository path is not normalized")
    return normalized


def _safe_resource(value: Any) -> str | None:
    return value if isinstance(value, str) and len(value) <= 256 and "\x00" not in value else None


def _copy_json_object(value: Mapping[str, Any]) -> dict[str, Any]:
    copied = _copy_json_value(value)
    if not isinstance(copied, dict):
        raise TypeError("expected JSON object")
    return copied


def _copy_json_value(value: Any) -> Any:
    if value is None or type(value) is bool or type(value) is int or type(value) is str:
        return value
    if type(value) is float:
        raise TypeError("floats are not admitted")
    if isinstance(value, list):
        return [_copy_json_value(v) for v in value]
    if type(value) is dict:
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or key in out:
                raise TypeError("object keys must be unique strings")
            out[key] = _copy_json_value(item)
        return out
    raise TypeError("value is not strict JSON")
