"""Stable work identities shared by ingest, the projector and the dispatcher."""

from __future__ import annotations

import re
from collections.abc import Mapping
from functools import lru_cache
from urllib.parse import urlsplit

_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_GITHUB = re.compile(r"^(?:github:)?([^/:]+/[^/:]+):(issue|pr):(\d+)$", re.I)
_SHORT = re.compile(r"^(issue|pr):([^/:]+/[^/:]+):(\d+)$", re.I)
_COMMAND = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")


def _repo(value):
    value = str(value or "").strip()
    if not _REPO.fullmatch(value) or any(p in {".", ".."} for p in value.split("/")):
        raise ValueError("task identity requires an unambiguous owner/repo")
    return value.lower()


def _github(repo, kind, number):
    kind = str(kind or "").lower()
    kind = {"issues": "issue", "pull": "pr", "pulls": "pr", "pull_request": "pr"}.get(kind, kind)
    if kind not in {"issue", "pr"}:
        raise ValueError("task identity requires explicit issue or pr kind")
    if isinstance(number, bool) or not re.fullmatch(r"[0-9]+", str(number or "")):
        raise ValueError("task identity requires a positive issue or PR number")
    number = int(number)
    if number <= 0:
        raise ValueError("task identity requires a positive issue or PR number")
    return f"github:{_repo(repo)}:{kind}:{number}"


def task_key(value=None, repo=None, kind=None, number=None):
    """Normalize a provider URL/key or explicit fields; never guess from prose.

    GitHub repository names are case insensitive. Owner-command IDs are not:
    their exact spelling is retained so unrelated owner commands never coalesce.
    An issue and its implementing PR remain different identities until explicit
    provider evidence relates them; a coincident number is not such evidence.
    """
    if type(value) is str and len(value) <= 1024 and repo is None and kind is None and number is None:
        return _cached_task_key(value)
    return _task_key(value, repo=repo, kind=kind, number=number)


@lru_cache(maxsize=4096)
def _cached_task_key(value):
    # Only bounded plain strings enter the cache; mappings and contextual fields
    # are evaluated on every call, and the retained result is an immutable key.
    return _task_key(value)


def _task_key(value=None, repo=None, kind=None, number=None):
    if isinstance(value, Mapping):
        item = value
        for field in ("task_key", "html_url", "url"):
            if item.get(field):
                return task_key(item[field], repo=repo, kind=kind, number=number)
        repo = item.get("repo", item.get("repository", repo))
        if isinstance(repo, Mapping):
            repo = repo.get("full_name")
        if item.get("issue") is not None:
            kind, number = "issue", item["issue"]
        elif item.get("pr") is not None:
            kind, number = "pr", item["pr"]
        else:
            kind, number = item.get("kind", kind), item.get("number", number)
        value = None
    if value is None or value == "":
        return _github(repo, kind, number)
    value = str(value).strip()
    for prefix in ("commons:owner-command:", "owner:"):
        if value.startswith(prefix):
            stable_id = value[len(prefix):]
            if not _COMMAND.fullmatch(stable_id):
                raise ValueError("owner command requires a stable nonempty identifier")
            return "commons:owner-command:" + stable_id
    match = _GITHUB.fullmatch(value)
    if match:
        return _github(*match.groups())
    match = _SHORT.fullmatch(value)
    if match:
        return _github(match[2], match[1], match[3])
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme in {"https", "http"} and host in {"github.com", "www.github.com", "api.github.com"}:
        parts = parsed.path.strip("/").split("/")
        if host == "api.github.com" and parts and parts[0] == "repos":
            parts = parts[1:]
        if len(parts) >= 4 and parts[2] in {"issues", "pull", "pulls"}:
            return _github("/".join(parts[:2]), parts[2], parts[3])
        raise ValueError("GitHub task URL must name one issue or pull request")
    if re.fullmatch(r"#?\d+", value) and repo and kind:
        return _github(repo, kind, value.lstrip("#"))
    raise ValueError("ambiguous task identity; use a GitHub issue/PR URL or an owner command ID")


def key_parts(value):
    """Return provider coordinates without making callers split key syntax."""
    key = task_key(value)
    if key.startswith("github:"):
        _, repo, kind, number = key.split(":")
        return {"task_key": key, "repo": repo, "kind": kind, "number": int(number)}
    return {"task_key": key, "kind": "owner-command", "command_id": key.split(":", 2)[2]}
