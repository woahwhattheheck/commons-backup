#!/usr/bin/env python3
"""Create, verify, and restore full Git-bundle backups without closing the repo."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "commons-open-repo-backup/v3"
HEAD_SCHEMA_VERSION = "commons-open-repo-backup/v2"
LEGACY_SCHEMA_VERSION = "commons-open-repo-backup/v1"
DRILL_SCHEMA_VERSION = "commons-open-repo-backup-drill/v1"
ALLOWED_STORAGE = frozenset({"github-actions-artifact"})
ARTIFACT_RETENTION_DAYS = 90
DEFAULT_ARTIFACT_NAME = "commons-open-repo-backup"
SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")

DRILL_FIELDS = frozenset(
    {
        "schema_version",
        "state",
        "created_at",
        "storage",
        "retention_days",
        "artifact_name",
        "github_outage_protection",
        "same_repo_copy",
        "owner_disk",
        "secrets_present",
        "independent_of_git_objects",
        "independent_of_owner_disk",
        "github_hosted",
        "head_sha",
        "bundle",
        "bundle_sha256",
        "ref_count",
        "restored_head_sha",
        "bare",
        "run_id",
        "run_attempt",
        "repository",
        "ref",
        "sha",
    }
)


class BackupError(RuntimeError):
    """A snapshot, manifest, or restore failed its measured contract."""


def _run(
    args: list[str],
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    # Git hooks and parent Git commands can export repository-local selectors.
    # Explicit source/restore directories must not inherit another repository's
    # refs, index, or object storage. Keep unrelated configuration and credentials.
    env = os.environ.copy()
    for name in (
        "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_SHALLOW_FILE", "GIT_GRAFT_FILE", "GIT_NAMESPACE", "GIT_PREFIX",
        "GIT_IMPLICIT_WORK_TREE",
    ):
        env.pop(name, None)
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if check and completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise BackupError(f"git {' '.join(args)} failed: {detail}")
    return completed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise BackupError(f"cannot hash {path}: {error}") from error
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_exclusive_json(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if os.path.lexists(path):
        raise BackupError(f"refusing to overwrite {path}: path already exists")
    try:
        with tempfile.TemporaryDirectory(prefix=".commons-backup-json-", dir=path.parent) as staging:
            staged = Path(staging) / path.name
            fd = os.open(str(staged), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            try:
                remaining = memoryview(text.encode("utf-8"))
                while remaining:
                    written = os.write(fd, remaining)
                    if written <= 0:
                        raise BackupError(f"cannot write {path}: write made no progress")
                    remaining = remaining[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
            # Publish only complete bytes. An occupied destination still wins
            # even if it appeared after the cheap existence check above.
            try:
                os.link(staged, path)
            except OSError as error:
                raise BackupError(f"refusing to overwrite {path}: {error}") from error
    except OSError as error:
        raise BackupError(f"cannot write {path}: {error}") from error


def _bundle_heads(bundle: Path) -> list[dict[str, str]]:
    completed = _run(["bundle", "list-heads", str(bundle)])
    heads = []
    for line in completed.stdout.splitlines():
        sha, separator, ref = line.partition(" ")
        if not separator or not SHA_RE.fullmatch(sha) or not ref.strip():
            raise BackupError(f"invalid bundle head: {line!r}")
        heads.append({"ref": ref.strip(), "sha": sha})
    if not heads:
        raise BackupError("bundle has no refs")
    return sorted(heads, key=lambda row: row["ref"])


def _repo_heads(source: Path) -> list[dict[str, str]]:
    # The bundle records this worktree's HEAD plus every shared ref.
    # `for-each-ref` omits HEAD, so compare against `show-ref --head`.
    completed = _run(
        ["show-ref", "--head"],
        cwd=source,
    )
    heads = []
    for line in completed.stdout.splitlines():
        sha, separator, ref = line.partition(" ")
        if separator and SHA_RE.fullmatch(sha) and ref.strip():
            heads.append({"ref": ref.strip(), "sha": sha})
    return sorted(heads, key=lambda row: row["ref"])


def _head_ref(source: Path) -> str | None:
    """Return the immediate symbolic HEAD target, or None for detached HEAD."""
    completed = _run(["symbolic-ref", "--quiet", "--no-recurse", "HEAD"], cwd=source, check=False)
    if completed.returncode == 1:
        return None
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise BackupError(f"cannot read symbolic HEAD: {detail}")
    return completed.stdout.strip()


def _repo_symbolic_refs(source: Path) -> list[dict[str, str]]:
    """Read immediate targets for resolved shared symbolic refs, excluding HEAD."""
    completed = _run(["for-each-ref", "--format=%(refname) %(symref)"], cwd=source)
    rows = []
    for line in completed.stdout.splitlines():
        ref, _, target = line.partition(" ")
        if target:
            # %(symref) may resolve a chain; retain each immediate link instead.
            target = _run(
                ["symbolic-ref", "--quiet", "--no-recurse", ref], cwd=source,
            ).stdout.strip()
            rows.append({"ref": ref, "target": target})
    return sorted(rows, key=lambda row: row["ref"])


def _validate_symbolic_refs(
    value: Any, refs: list[dict[str, str]], head_ref: str | None,
) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise BackupError("manifest symbolic refs must be a list")
    objects = {row["ref"]: row["sha"] for row in refs}
    links = {}
    for row in value:
        if (not isinstance(row, dict) or set(row) != {"ref", "target"}
                or not isinstance(row["ref"], str) or not isinstance(row["target"], str)):
            raise BackupError("manifest symbolic ref fields drifted")
        ref, target = row["ref"], row["target"]
        if (not ref.startswith("refs/") or ref in links
                or ref not in objects or target not in objects
                or objects[ref] != objects[target]):
            raise BackupError("manifest symbolic ref differs from bundle refs")
        links[ref] = target
    graph = dict(links)
    if head_ref is not None:
        graph["HEAD"] = head_ref
    for ref in graph:
        seen = set()
        while ref in graph:
            if ref in seen:
                raise BackupError("manifest symbolic refs contain a cycle")
            seen.add(ref)
            ref = graph[ref]
    return [{"ref": ref, "target": links[ref]} for ref in sorted(links)]


def snapshot(source: Path, output_dir: Path) -> Path:
    source = source.resolve()
    output_dir = output_dir.resolve()
    # Bare mirrors and --bare restores hold the same Git objects and refs as
    # work trees. They must remain usable as sources for the next backup.
    _run(["rev-parse", "--git-dir"], cwd=source)
    # Bundle creation can succeed in a shallow clone while omitting parents
    # needed by a fresh restore. A full backup requires complete history.
    if _run(["rev-parse", "--is-shallow-repository"], cwd=source).stdout.strip() == "true":
        raise BackupError(
            "source repository is shallow; fetch complete history with "
            "git fetch --unshallow (or use a full clone) before creating a full backup"
        )
    head_sha = _run(["rev-parse", "HEAD"], cwd=source).stdout.strip()
    if not SHA_RE.fullmatch(head_sha):
        raise BackupError("HEAD is not a full object id")
    head_ref = _head_ref(source)
    symbolic_refs = _repo_symbolic_refs(source)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundle = output_dir / f"commons-{stamp}-{head_sha[:12]}.bundle"
    # Path.exists() follows the name, so a dangling symlink looks absent.
    # Git and os.link can still replace that occupied name.
    if os.path.lexists(bundle):
        raise BackupError(f"refusing to overwrite snapshot: {bundle}")
    # Git may replace an existing bundle path. Build privately on the same
    # filesystem, then publish with an exclusive hard link: an existence check
    # alone cannot protect another snapshot that finishes during generation.
    with tempfile.TemporaryDirectory(prefix=".commons-backup-", dir=output_dir) as staging:
        staged_bundle = Path(staging) / bundle.name
        # Other worktrees' pseudo-refs are not ordinary restorable refs. Keep
        # every shared ref and this source HEAD, matching show-ref --head.
        _run(["bundle", "create", str(staged_bundle), "--single-worktree", "--all"], cwd=source)
        bundle_heads = _bundle_heads(staged_bundle)
        repo_heads = _repo_heads(source)
        if bundle_heads != repo_heads:
            raise BackupError("bundle ref inventory differs from source")
        if (_head_ref(source) != head_ref
                or _run(["rev-parse", "HEAD"], cwd=source).stdout.strip() != head_sha):
            raise BackupError("source HEAD changed during snapshot")
        if _repo_symbolic_refs(source) != symbolic_refs:
            raise BackupError("source symbolic refs changed during snapshot")
        _validate_symbolic_refs(symbolic_refs, bundle_heads, head_ref)
        try:
            os.link(staged_bundle, bundle)
        except OSError as error:
            raise BackupError(f"cannot publish snapshot exclusively {bundle}: {error}") from error
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": _utc_now(),
        "head_sha": head_sha,
        "head_ref": head_ref,
        "symbolic_refs": symbolic_refs,
        "bundle": bundle.name,
        "bundle_sha256": _sha256(bundle),
        "refs": bundle_heads,
        "source": str(source),
    }
    manifest_path = bundle.with_suffix(".manifest.json")
    _write_exclusive_json(manifest_path, manifest)
    return manifest_path


def read_manifest(manifest_path: Path) -> tuple[dict[str, Any], Path]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BackupError(f"manifest unreadable: {manifest_path}: {error}") from error
    required = {
        "schema_version",
        "created_at",
        "head_sha",
        "bundle",
        "bundle_sha256",
        "refs",
        "source",
    }
    if not isinstance(manifest, dict):
        raise BackupError("manifest fields drifted")
    if manifest.get("schema_version") == SCHEMA_VERSION:
        required.add("symbolic_refs")
        required.add("head_ref")
    elif manifest.get("schema_version") == HEAD_SCHEMA_VERSION:
        required.add("head_ref")
    elif manifest.get("schema_version") != LEGACY_SCHEMA_VERSION:
        raise BackupError("manifest schema version drifted")
    if set(manifest) != required:
        raise BackupError("manifest fields drifted")
    if not SHA_RE.fullmatch(str(manifest["head_sha"])):
        raise BackupError("manifest HEAD is invalid")
    bundle_name = str(manifest["bundle"])
    if Path(bundle_name).name != bundle_name:
        raise BackupError("manifest bundle must be a sibling filename")
    bundle = manifest_path.resolve().parent / bundle_name
    if not bundle.is_file():
        raise BackupError(f"bundle missing: {bundle}")
    return manifest, bundle


def _verify_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest, bundle = read_manifest(manifest_path)
    actual_sha = _sha256(bundle)
    if actual_sha != manifest["bundle_sha256"]:
        raise BackupError("bundle sha256 mismatch")
    actual_refs = _bundle_heads(bundle)
    if actual_refs != manifest["refs"]:
        raise BackupError("bundle refs differ from manifest")
    if not any(row["sha"] == manifest["head_sha"] for row in actual_refs):
        raise BackupError("manifest HEAD is absent from bundle refs")
    if manifest["schema_version"] in {SCHEMA_VERSION, HEAD_SCHEMA_VERSION}:
        head_ref = manifest["head_ref"]
        if not any(row["ref"] == "HEAD" and row["sha"] == manifest["head_sha"] for row in actual_refs):
            raise BackupError("manifest HEAD differs from bundle HEAD")
        if head_ref is not None:
            if (not isinstance(head_ref, str) or not head_ref.startswith("refs/")
                    or not any(row["ref"] == head_ref and row["sha"] == manifest["head_sha"] for row in actual_refs)):
                raise BackupError("manifest symbolic HEAD differs from bundle refs")
    receipt = {
        "state": "VERIFIED",
        "manifest": str(manifest_path),
        "bundle": str(bundle),
        "bundle_sha256": actual_sha,
        "head_sha": manifest["head_sha"],
        "refs": len(actual_refs),
    }
    if manifest["schema_version"] in {SCHEMA_VERSION, HEAD_SCHEMA_VERSION}:
        receipt["head_ref"] = manifest["head_ref"]
    if manifest["schema_version"] == SCHEMA_VERSION:
        receipt["symbolic_refs"] = _validate_symbolic_refs(
            manifest["symbolic_refs"], actual_refs, manifest["head_ref"],
        )
    return receipt


def restore(manifest_path: Path, target: Path, bare: bool = False) -> dict[str, Any]:
    receipt = _verify_manifest(manifest_path)
    # A dangling symlink occupies the requested name even though exists() is
    # false. Reserve that name before resolving it so restoration cannot follow
    # an existing link into a different, not-yet-created destination.
    target = target.absolute()
    if os.path.lexists(target):
        raise BackupError(f"refusing to overwrite restore target: {target}")
    expected_refs = _bundle_heads(Path(receipt["bundle"]))
    try:
        target.mkdir(parents=True)
    except OSError as error:
        raise BackupError(f"cannot create new restore target {target}: {error}") from error
    target = target.resolve()
    # Ordinary clones rename branches into origin/* and omit notes/custom refs.
    # Mirror into the new target (or its .git directory) to retain every ref.
    git_dir = target if bare else target / ".git"
    _run(["clone", "--mirror", "--origin", "origin", receipt["bundle"], str(git_dir)])
    if not bare:
        _run(["config", "core.bare", "false"], cwd=target)
        # A recovered work tree must not acquire mirror-push semantics.
        _run(["config", "--unset", "remote.origin.mirror"], cwd=target)
        _run(
            ["config", "--replace-all", "remote.origin.fetch",
             "+refs/heads/*:refs/remotes/origin/*"],
            cwd=target,
        )
    # Bundles store HEAD's commit, not its attached/detached identity. Clone
    # may choose a different branch when multiple refs share that commit.
    if "head_ref" in receipt:
        if receipt["head_ref"] is None:
            _run(["update-ref", "--no-deref", "HEAD", receipt["head_sha"]], cwd=target)
        else:
            _run(["symbolic-ref", "HEAD", receipt["head_ref"]], cwd=target)
        if _head_ref(target) != receipt["head_ref"]:
            raise BackupError("restored symbolic HEAD differs from manifest")
    # Establish HEAD before links that may point to it, rather than using the
    # branch guessed by clone while reconstructing the saved alias graph.
    for row in receipt.get("symbolic_refs", []):
        _run(["symbolic-ref", row["ref"], row["target"]], cwd=target)
    restored_head = _run(["rev-parse", "HEAD"], cwd=target).stdout.strip()
    if restored_head != receipt["head_sha"]:
        raise BackupError(
            f"restored HEAD {restored_head} != manifest {receipt['head_sha']}"
        )
    if _repo_heads(target) != expected_refs:
        raise BackupError("restored ref inventory differs from manifest")
    if not bare:
        # Only this newly created target is populated; existing targets are refused.
        _run(["reset", "--hard", "HEAD"], cwd=target)
    if "symbolic_refs" in receipt and _repo_symbolic_refs(target) != receipt["symbolic_refs"]:
        raise BackupError("restored symbolic ref inventory differs from manifest")
    receipt.update(
        {
            "state": "RESTORED",
            "target": str(target),
            "restored_head_sha": restored_head,
            "bare": bare,
        }
    )
    return receipt


def verify(manifest_path: Path) -> dict[str, Any]:
    # A bundle's checksum and advertised refs cannot establish object
    # completeness. Exercise the same isolated restore used for recovery.
    with tempfile.TemporaryDirectory(prefix="commons-backup-verify-") as temporary:
        receipt = restore(manifest_path, Path(temporary) / "repository.git", bare=True)
    receipt["state"] = "VERIFIED"
    for key in ("target", "restored_head_sha", "bare"):
        del receipt[key]
    return receipt


def github_run_fields() -> dict[str, str]:
    return {
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        "repository": os.environ.get("GITHUB_REPOSITORY", ""),
        "ref": os.environ.get("GITHUB_REF", ""),
        "sha": os.environ.get("GITHUB_SHA", ""),
    }


def make_drill_receipt(
    *,
    storage: str,
    retention_days: int,
    artifact_name: str,
    restore_receipt: dict[str, Any],
    run: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the exclusive CI drill receipt.

    Forced flags cannot be overridden: github_outage_protection, same_repo_copy,
    owner_disk, and secrets_present are always False. Storage must be the
    measured GitHub Actions artifact store. This function will not mint S3,
    GCS, Drive, or Oracle receipts.
    """
    if storage not in ALLOWED_STORAGE:
        raise BackupError(
            f"storage {storage!r} is not a measured independent store; "
            "do not mint an unmeasured provider receipt"
        )
    if retention_days != ARTIFACT_RETENTION_DAYS:
        raise BackupError(
            f"retention_days must be {ARTIFACT_RETENTION_DAYS} for github-actions-artifact"
        )
    if not artifact_name or Path(artifact_name).name != artifact_name:
        raise BackupError("artifact name must be a bare filename")
    if restore_receipt.get("state") != "RESTORED":
        raise BackupError("drill receipt requires a RESTORED readback")
    required_restore = ("head_sha", "bundle", "bundle_sha256", "refs", "restored_head_sha")
    missing = [key for key in required_restore if key not in restore_receipt]
    if missing:
        raise BackupError(f"restore receipt missing {missing}")
    if restore_receipt["restored_head_sha"] != restore_receipt["head_sha"]:
        raise BackupError("restore readback HEAD does not match manifest")
    run = github_run_fields() if run is None else run
    receipt = {
        "schema_version": DRILL_SCHEMA_VERSION,
        "state": "DRILLED",
        "created_at": _utc_now(),
        "storage": "github-actions-artifact",
        "retention_days": ARTIFACT_RETENTION_DAYS,
        "artifact_name": artifact_name,
        "github_outage_protection": False,
        "same_repo_copy": False,
        "owner_disk": False,
        "secrets_present": False,
        "independent_of_git_objects": True,
        "independent_of_owner_disk": True,
        "github_hosted": True,
        "head_sha": restore_receipt["head_sha"],
        "bundle": Path(str(restore_receipt["bundle"])).name,
        "bundle_sha256": restore_receipt["bundle_sha256"],
        "ref_count": restore_receipt["refs"],
        "restored_head_sha": restore_receipt["restored_head_sha"],
        "bare": bool(restore_receipt.get("bare")),
        "run_id": str(run.get("run_id", "")),
        "run_attempt": str(run.get("run_attempt", "")),
        "repository": str(run.get("repository", "")),
        "ref": str(run.get("ref", "")),
        "sha": str(run.get("sha", "")),
    }
    # Re-force so a mutated restore_receipt or run dict cannot mint a false claim.
    receipt["github_outage_protection"] = False
    receipt["same_repo_copy"] = False
    receipt["owner_disk"] = False
    receipt["secrets_present"] = False
    receipt["storage"] = "github-actions-artifact"
    receipt["retention_days"] = ARTIFACT_RETENTION_DAYS
    if set(receipt) != DRILL_FIELDS:
        raise BackupError("drill receipt fields drifted")
    return receipt


def drill(
    source: Path,
    output_dir: Path,
    restore_dir: Path,
    *,
    storage: str,
    retention_days: int,
    artifact_name: str = DEFAULT_ARTIFACT_NAME,
    bare: bool = True,
    run: dict[str, str] | None = None,
) -> dict[str, Any]:
    manifest_path = snapshot(source, output_dir)
    restored = restore(manifest_path, restore_dir, bare=bare)
    receipt = make_drill_receipt(
        storage=storage,
        retention_days=retention_days,
        artifact_name=artifact_name,
        restore_receipt=restored,
        run=run,
    )
    receipt_path = output_dir.resolve() / "drill-receipt.json"
    _write_exclusive_json(receipt_path, receipt)
    return {
        **receipt,
        "manifest": str(manifest_path),
        "receipt": str(receipt_path),
        "target": restored["target"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("snapshot")
    make.add_argument("--source", type=Path, default=Path.cwd(),
                      help="Git work tree or bare repository to back up")
    make.add_argument("--output-dir", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("manifest", type=Path)
    recover = commands.add_parser("restore")
    recover.add_argument("manifest", type=Path)
    recover.add_argument("target", type=Path)
    recover.add_argument("--bare", action="store_true")
    exercise = commands.add_parser("drill")
    exercise.add_argument("--source", type=Path, default=Path.cwd(),
                          help="Git work tree or bare repository to back up")
    exercise.add_argument("--output-dir", type=Path, required=True)
    exercise.add_argument("--restore-dir", type=Path, required=True)
    exercise.add_argument("--bare", action="store_true")
    exercise.add_argument("--storage", required=True)
    exercise.add_argument("--retention-days", type=int, required=True)
    exercise.add_argument("--artifact-name", default=DEFAULT_ARTIFACT_NAME)
    args = parser.parse_args()
    try:
        if args.command == "snapshot":
            output = {"state": "SNAPSHOT", "manifest": str(snapshot(args.source, args.output_dir))}
        elif args.command == "verify":
            output = verify(args.manifest)
        elif args.command == "drill":
            output = drill(
                args.source,
                args.output_dir,
                args.restore_dir,
                storage=args.storage,
                retention_days=args.retention_days,
                artifact_name=args.artifact_name,
                bare=args.bare,
            )
        else:
            output = restore(args.manifest, args.target, args.bare)
        print(json.dumps(output, sort_keys=True))
        return 0
    except BackupError as error:
        print(f"BACKUP_ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
