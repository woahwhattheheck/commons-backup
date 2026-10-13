#!/usr/bin/env python3
"""One-shot Muhlnickel command drive with frozen, validated ingress.

The historical action implementation is loaded as data only after this wrapper
installs snapshot-bound local/GitHub loaders. No command action is dispatched
until both snapshots have been frozen and validated.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import muhl_command_snapshot as snapshot

LEGACY_SOURCE = os.path.join(HERE, "_muhl_github_drive_legacy_source.txt")
LEGACY_GIT_BLOB = "c491d09c762b9f8683d5e0bdd071104298c721ab"
REPO = "woahwhattheheck/kite-mouth-help"
REPO_API = "https://api.github.com/repos/" + REPO + "/"
MAX_API_BYTES = 2 * 1024 * 1024
# Every command field the pinned legacy engine reads as text. The snapshot
# parser closes required/per-kind fields; this second fence closes optional
# legacy-consumed fields before the legacy loop can dispatch any command.
LEGACY_STRING_FIELDS = frozenset({
    "id",
    "kind",
    "approved",
    "claimed_from",
    "authenticated_player",
    "purpose",
    "path",
    "from",
    "to",
    "body",
    "owner_ok",
    "_source",
})


def _load_legacy_namespace() -> dict[str, Any]:
    source = snapshot.read_stable_file(LEGACY_SOURCE)
    if snapshot.git_blob_sha(source) != LEGACY_GIT_BLOB:
        raise snapshot.SnapshotError("legacy drive source does not match pinned Git blob")
    namespace: dict[str, Any] = {
        "__name__": "_muhl_github_drive_legacy",
        "__file__": LEGACY_SOURCE,
        "__builtins__": __builtins__,
    }
    exec(compile(source, LEGACY_SOURCE, "exec"), namespace, namespace)
    return namespace


def _github_json(endpoint: str, token: str | None) -> Any:
    if not endpoint or "://" in endpoint or endpoint.startswith("/") or ".." in endpoint:
        raise snapshot.SnapshotError("unsafe GitHub API endpoint")
    url = REPO_API + endpoint
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "muhl-github-drive",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read(MAX_API_BYTES + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        raise snapshot.SnapshotError(
            "GitHub command snapshot request failed: " + type(exc).__name__
        ) from exc
    if len(raw) > MAX_API_BYTES:
        raise snapshot.SnapshotError("GitHub command snapshot response is too large")
    try:
        return json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise snapshot.SnapshotError("GitHub command snapshot response is invalid JSON") from exc


def _close_legacy_schema(
    commands: dict[str, dict[str, Any]], *, source: str
) -> dict[str, dict[str, Any]]:
    """Type-close every field the pinned legacy engine consumes as text."""
    if not isinstance(commands, dict):
        raise snapshot.SnapshotError(f"{source}: command snapshot must be a mapping")
    for command_id, command in commands.items():
        if not isinstance(command_id, str):
            raise snapshot.SnapshotError(f"{source}: command map key must be a string")
        if not isinstance(command, dict):
            raise snapshot.SnapshotError(f"{source}:{command_id}: command must be an object")
        for key in LEGACY_STRING_FIELDS:
            if key in command and not isinstance(command[key], str):
                raise snapshot.SnapshotError(
                    f"{source}:{command_id}: {key} must be a string before legacy dispatch"
                )
        declared_id = command.get("id")
        if declared_id is not None and declared_id != command_id:
            raise snapshot.SnapshotError(
                f"{source}:{command_id}: command map key/id mismatch {declared_id!r}"
            )
    return commands


def _install_snapshot_loaders(namespace: dict[str, Any]) -> None:
    command_root = namespace.get("CMD_ROOT")
    if not isinstance(command_root, str) or not command_root:
        raise snapshot.SnapshotError("legacy drive command root is invalid")

    local_ids: set[str] = set()

    def load_local_commands() -> dict[str, dict[str, Any]]:
        commands = _close_legacy_schema(
            snapshot.load_local_commands(command_root), source="local-snapshot"
        )
        local_ids.clear()
        local_ids.update(commands)
        return commands

    def load_github_commands(token: str | None = None) -> dict[str, dict[str, Any]]:
        commands, commit_sha = snapshot.load_github_commands(
            lambda endpoint: _github_json(endpoint, token)
        )
        commands = _close_legacy_schema(commands, source=f"github-snapshot@{commit_sha}")
        duplicates = sorted(local_ids.intersection(commands))
        if duplicates:
            raise snapshot.SnapshotError(
                "local/GitHub command id collision(s): " + ", ".join(duplicates)
            )
        print("DRIVE snapshot github", commit_sha, "ids", len(commands))
        return commands

    namespace["load_local_commands"] = load_local_commands
    namespace["load_github_commands"] = load_github_commands


def main() -> int:
    try:
        namespace = _load_legacy_namespace()
        _install_snapshot_loaders(namespace)
        legacy_main = namespace.get("main")
        if not callable(legacy_main):
            raise snapshot.SnapshotError("legacy drive main is missing")
        return int(legacy_main())
    except snapshot.SnapshotError as exc:
        print("REFUSE command snapshot:", exc)
        print("DIE")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
