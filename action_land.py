#!/usr/bin/env python3
"""Land exact Action Pad outputs from an unprivileged runner onto moving main."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMMIT_MESSAGE = "fire addressed Commons actions"
MAX_ATTEMPTS = 5
RESULT_PREFIX = "actions/results/"
REMOTE_REF = "HEAD:main"


def git(*args: str, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    if any(part == "--force" or part.startswith("--force") for part in args):
        raise RuntimeError("force-push is forbidden")
    kwargs = {"cwd": ROOT, "text": True, "check": check, "capture_output": True}
    if env is not None:
        kwargs["env"] = env
    return subprocess.run(["git", *args], **kwargs)


def git_bytes(*args: str) -> subprocess.CompletedProcess:
    if any(part == "--force" or part.startswith("--force") for part in args):
        raise RuntimeError("force-push is forbidden")
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=False)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def emit(payload: dict) -> None:
    print(json.dumps(payload, sort_keys=True), flush=True)


def combined(result: subprocess.CompletedProcess) -> str:
    stdout = result.stdout if isinstance(result.stdout, str) else (result.stdout or b"").decode("utf-8", "replace")
    stderr = result.stderr if isinstance(result.stderr, str) else (result.stderr or b"").decode("utf-8", "replace")
    return (stdout + "\n" + stderr).strip()


def manifest_name(value: object) -> str:
    """Preserve an executed effect's address in the receipt manifest."""
    return str(value or "").strip().replace("\\", "/")


def artifact_path(source: Path, name: str) -> Path | None:
    """Map only artifact-addressable effects; others remain receipt-only."""
    raw = Path(name).expanduser()
    if raw.is_absolute():
        return None
    candidate = (source / raw).resolve(strict=False)
    try:
        candidate.relative_to(source.resolve())
    except ValueError:
        return None
    return candidate


def repository_destination(name: str) -> Path | None:
    """Map only effects Git can persist; do not reject the other effects."""
    raw = Path(name).expanduser()
    if raw.is_absolute():
        return None
    candidate = (ROOT / raw).resolve(strict=False)
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        return None
    metadata = git("rev-parse", "--absolute-git-dir", check=False)
    if metadata.returncode == 0 and metadata.stdout.strip():
        metadata_path = Path(metadata.stdout.strip()).resolve()
        try:
            candidate.relative_to(metadata_path)
            return None
        except ValueError:
            pass
    return candidate


def manifest_map(data: dict, key: str, source: Path) -> dict[str, str]:
    raw = data.get(key) or {}
    if not isinstance(raw, dict):
        raise ValueError("action manifest %s must be an object" % key)
    out = {}
    for name, digest in raw.items():
        safe = manifest_name(name)
        if not safe:
            raise ValueError("action manifest path must not be blank")
        text = str(digest)
        if len(text) != 64 or any(c not in "0123456789abcdef" for c in text.lower()):
            raise ValueError("action manifest has an invalid sha256 for %s" % safe)
        out[safe] = text.lower()
    return out


def validate_manifest(data: dict, source_root: Path | None = None) -> list[str]:
    source = (source_root or ROOT).resolve()
    changed_raw = data.get("changed") or []
    if not isinstance(changed_raw, list):
        raise ValueError("action manifest changed must be an array")
    paths = [manifest_name(p) for p in changed_raw if manifest_name(p)]
    if len(paths) != len(set(paths)):
        raise ValueError("action manifest contains duplicate paths")
    canonical = manifest_map(data, "canonical_records", source)
    results = manifest_map(data, "result_records", source)
    outputs = manifest_map(data, "action_outputs", source)
    deleted_raw = data.get("action_deletions") or []
    if not isinstance(deleted_raw, list):
        raise ValueError("action manifest action_deletions must be an array")
    deletions = {manifest_name(name) for name in deleted_raw if manifest_name(name)}
    declared = set(canonical) | set(results) | set(outputs) | deletions
    if declared != set(paths):
        missing = sorted(set(paths) - declared)
        extra = sorted(declared - set(paths))
        raise ValueError("action manifest path/hash mismatch; missing=%r extra=%r" % (missing, extra))
    for name in paths:
        path = artifact_path(source, name)
        if name in deletions:
            if name in canonical or name in results or name in outputs:
                raise ValueError("action deletion cannot also carry a file hash: %s" % name)
            continue
        if path is None or path.is_symlink() or not path.is_file():
            continue
        actual = file_sha256(path)
        if results.get(name) == actual:
            continue
        if canonical.get(name) == actual:
            continue
        if outputs.get(name) == actual:
            continue
        raise ValueError("action output lacks the exact producer hash: %s" % name)
    return paths


def materialize(source: Path, paths: list[str], deletions: set[str]) -> list[str]:
    source = source.resolve()
    landed = []
    for name in paths:
        dest = repository_destination(name)
        if dest is None:
            continue
        if name in deletions:
            if dest.is_file() and not dest.is_symlink():
                dest.unlink()
                landed.append(name)
            continue
        src = artifact_path(source, name)
        if src is None or src.is_symlink() or not src.is_file():
            continue
        if dest.is_symlink() or (dest.exists() and not dest.is_file()):
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        landed.append(name)
    return landed


def is_result_latch(name: str) -> bool:
    return name.startswith(RESULT_PREFIX) and name.endswith(".json")


def already_on_origin_main(name: str) -> bool:
    probed = git("cat-file", "-e", "origin/main:%s" % name, check=False)
    return probed.returncode == 0


def drop_already_latched(paths: list[str], deletions: set[str]) -> tuple[list[str], list[str]]:
    """Duplicate result ids keep the original. Do not remint."""
    kept = []
    deduped = []
    for name in paths:
        if name in deletions or not is_result_latch(name) or not already_on_origin_main(name):
            kept.append(name)
            continue
        dest = repository_destination(name)
        if dest is not None and dest.is_file() and not dest.is_symlink():
            dest.unlink()
        deduped.append(name)
    return kept, deduped


def unmerged_paths() -> list[str] | None:
    listed = git("diff", "--name-only", "--diff-filter=U", check=False)
    if listed.returncode != 0:
        return None
    return [row.strip() for row in listed.stdout.splitlines() if row.strip()]


def resolve_result_rebase() -> dict:
    """Keep already-latched result ids during rebase. Never force-push."""
    paths = unmerged_paths()
    if paths is None:
        return {"ok": False, "reason": "UNMERGED_LIST_FAILED"}
    if not paths:
        return {"ok": False, "reason": "NO_UNMERGED"}
    for path in paths:
        if not is_result_latch(path):
            return {"ok": False, "reason": "NON_RESULT_PATH", "path": path}
        shown = git_bytes("show", ":2:%s" % path)
        if shown.returncode != 0:
            return {"ok": False, "reason": "MISSING_STAGE", "path": path}
        dest = repository_destination(path)
        if dest is None:
            return {"ok": False, "reason": "NON_REPO_PATH", "path": path}
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(shown.stdout)
        added = git("add", "--", path, check=False)
        if added.returncode != 0:
            return {"ok": False, "reason": "ADD_FAILED", "path": path, "detail": combined(added)}
    env = os.environ.copy()
    env["GIT_EDITOR"] = "true"
    env["GIT_SEQUENCE_EDITOR"] = "true"
    continued = git("rebase", "--continue", check=False, env=env)
    if continued.returncode == 0:
        return {"ok": True, "state": "DEDUPED", "paths": paths}
    blob = combined(continued).lower()
    if "nothing to commit" in blob or "no changes" in blob:
        skipped = git("rebase", "--skip", check=False)
        if skipped.returncode == 0:
            return {"ok": True, "state": "DEDUPED", "paths": paths}
        return {"ok": False, "reason": "SKIP_FAILED", "detail": combined(skipped)}
    return {"ok": False, "reason": "CONTINUE_FAILED", "detail": combined(continued)}


def land_from_source(source: Path) -> int:
    source = source.resolve()
    data = json.loads((source / ".action_changed.json").read_text(encoding="utf-8"))
    paths = validate_manifest(data, source)
    deletions = {manifest_name(name) for name in (data.get("action_deletions") or []) if manifest_name(name)}
    if source != ROOT.resolve():
        paths = materialize(source, paths, deletions)
    else:
        paths = [name for name in paths if repository_destination(name) is not None]
    fetched = git("fetch", "origin", "main", check=False)
    deduped: list[str] = []
    if fetched.returncode == 0:
        paths, deduped = drop_already_latched(paths, deletions)
    if not paths:
        emit({"ok": True, "state": "DEDUPED" if deduped else "QUIET", "deduped": deduped})
        return 0
    git("add", "--all", "--", *paths)
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        emit({"ok": True, "state": "DEDUPED" if deduped else "QUIET", "deduped": deduped})
        return 0
    git("config", "user.name", "commons-action")
    git("config", "user.email", "commons-action@users.noreply.github.com")
    git("commit", "-m", COMMIT_MESSAGE)
    last_resolve = None
    last_push = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        pushed = git("push", "origin", REMOTE_REF, check=False)
        last_push = pushed
        if pushed.returncode == 0:
            emit({"ok": True, "state": "LANDED", "attempts": attempt, "deduped": deduped, "resolve": last_resolve})
            return 0
        git("fetch", "origin", "main", check=False)
        rebased = git("rebase", "origin/main", check=False)
        if rebased.returncode != 0:
            resolved = resolve_result_rebase()
            last_resolve = resolved
            if resolved.get("ok"):
                if attempt < MAX_ATTEMPTS:
                    time.sleep(attempt * 3)
                continue
            git("rebase", "--abort", check=False)
            emit({
                "ok": False,
                "state": "REBASE_CONFLICT",
                "attempts": attempt,
                "detail": combined(rebased),
                "resolve": resolved,
            })
            return 1
        if attempt < MAX_ATTEMPTS:
            time.sleep(attempt * 3)
    emit({
        "ok": False,
        "state": "PUSH_RACE",
        "attempts": MAX_ATTEMPTS,
        "detail": combined(last_push) if last_push is not None else "",
    })
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, help="artifact directory from the unprivileged execute job")
    args = ap.parse_args()
    source = (args.source or ROOT).resolve()
    return land_from_source(source)


if __name__ == "__main__":
    raise SystemExit(main())
