"""Exact committed-tree Git source capsules with live, unsealed main drift."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

try:
    from host import git_source_capsules_legacy as _legacy
except ModuleNotFoundError:
    import git_source_capsules_legacy as _legacy

GitSourceError = _legacy.GitSourceError
HEX40 = _legacy.HEX40
GIT_SOURCE_KEYS = {
    "commit",
    "tree_sha",
    "max_file_bytes",
    "requested_paths",
    "capsules",
}
LIVE_DRIFT_KEYS = {
    "observed_current_main_head",
    "source_commit_matches_current_main",
}


def collect_git_source(
    repository: str | Path,
    commit: str,
    paths: Any,
    *,
    max_file_bytes: int = 16_384,
) -> dict[str, Any]:
    """Collect exact source identity without sealing a historical ref observation."""
    bundle = _legacy.collect_git_source(
        repository,
        commit,
        paths,
        max_file_bytes=max_file_bytes,
    )
    return {key: copy.deepcopy(bundle[key]) for key in GIT_SOURCE_KEYS}


def observe_current_main(repository: str | Path, source_commit: str) -> dict[str, Any]:
    """Return a fresh, explicitly unsealed comparison with local ``main``."""
    repo = Path(repository)
    if not repo.is_dir():
        raise GitSourceError(f"repository path is not a directory: {repo}")
    if not isinstance(source_commit, str) or not HEX40.fullmatch(source_commit):
        raise GitSourceError("source commit must be exact lowercase 40-hex")
    observed = _legacy._observed_main(repo)
    return {
        "observed_current_main_head": observed,
        "source_commit_matches_current_main": None if observed is None else observed == source_commit,
    }


def _legacy_source(bundle: Any, repository: str | Path) -> tuple[dict[str, Any] | None, str]:
    if type(bundle) is not dict or set(bundle) != GIT_SOURCE_KEYS:
        return None, "git-source-shape"
    commit = bundle.get("commit")
    if type(commit) is not str or not HEX40.fullmatch(commit):
        return None, "git-source-commit"
    expanded = copy.deepcopy(bundle)
    drift = observe_current_main(repository, commit)
    expanded["observed_main_head"] = drift["observed_current_main_head"]
    expanded["source_commit_matches_observed_main"] = drift["source_commit_matches_current_main"]
    return expanded, "ok"


def verify_git_source(bundle: Any, repository: str | Path) -> tuple[bool, str]:
    expanded, reason = _legacy_source(bundle, repository)
    if expanded is None:
        return False, reason
    return _legacy.verify_git_source(expanded, repository)


def _canonical(value: Any) -> str:
    return _legacy._canonical(value)


def _expanded_budget_packet(packet: dict[str, Any], repository: str | Path) -> tuple[dict[str, Any] | None, str]:
    source = packet.get("git_source")
    expanded_source, reason = _legacy_source(source, repository)
    if expanded_source is None:
        return None, reason
    expanded = copy.deepcopy(packet)
    expanded["git_source"] = expanded_source
    try:
        original_limit = packet["limits"]["max_chars"]
        if type(original_limit) is not int:
            return None, "git-source-packet-shape"
        added_fields = {key: value for key, value in expanded_source.items() if key not in source}
        # Inserting fields into the nonempty source object adds their encoded
        # object length minus one: braces give way to separating commas.
        source_growth = len(_canonical(added_fields)) - 1 if added_fields else 0
        original_width = len(str(original_limit))
        adjusted = original_limit
        for _ in range(8):
            expanded["limits"]["max_chars"] = adjusted
            delta = source_growth + len(str(adjusted)) - original_width
            new_adjusted = original_limit + delta
            if new_adjusted == adjusted:
                break
            adjusted = new_adjusted
        expanded["limits"]["max_chars"] = adjusted
    except (KeyError, TypeError):
        return None, "git-source-packet-shape"
    return expanded, "ok"


def verify_packet_git_source(packet: Any, repository: str | Path) -> tuple[bool, str]:
    """Verify source identity/admission while treating main drift as live metadata."""
    if not isinstance(packet, dict):
        return False, "git-source-packet-shape"
    if packet.get("git_source") is None:
        return True, "ok"
    expanded, reason = _expanded_budget_packet(packet, repository)
    if expanded is None:
        return False, "git-source-readback" if reason == "git-source-shape" else reason
    return _legacy.verify_packet_git_source(expanded, repository)


for _name in (
    "_git_env",
    "_run",
    "_git_object_oid",
    "_canonical_path",
    "_object_type",
    "_commit_tree",
    "_observed_main",
    "_tree_rows",
    "_tree_entry",
    "_blob",
    "_text_status",
    "_validate_packet_capsule",
):
    globals()[_name] = getattr(_legacy, _name)
