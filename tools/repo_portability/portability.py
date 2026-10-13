from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit


SNAPSHOT_SCHEMA = "repo-portability-snapshot/v1"
INVENTORY_SCHEMA = "repo-portability-inventory/v1"
PLAN_SCHEMA = "repo-portability-plan/v1"

ACTIONS = frozenset({"MIGRATE_PRIVATE", "COLD_ARCHIVE", "KEEP_PRIVATE", "PUBLIC_REVIEW"})
HEX_OID = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")
REF_NAME = re.compile(r"^refs/[A-Za-z0-9][A-Za-z0-9._/-]{0,511}$")
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class PortabilityError(RuntimeError):
    """Base error for deterministic repository portability operations."""


class ValidationError(PortabilityError):
    """Input or local-path validation failed."""


class VerificationError(PortabilityError):
    """A snapshot failed byte, object, or ref verification."""


@dataclass(frozen=True)
class GitResult:
    stdout: str
    stderr: str


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_float(value: str) -> None:
    raise ValidationError(f"floating point JSON value is forbidden: {value!r}")


def _reject_constant(value: str) -> None:
    raise ValidationError(f"non-finite JSON value is forbidden: {value!r}")


def _parse_int(value: str) -> int:
    if len(value.lstrip("-")) > 18:
        raise ValidationError("oversized JSON integer")
    return int(value)


def _pairs(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValidationError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(data: bytes | str) -> Any:
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise ValidationError("JSON is not valid UTF-8") from exc
    else:
        text = data
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_int=_parse_int,
            parse_constant=_reject_constant,
        )
    except ValidationError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValidationError("invalid JSON") from exc


def _exact_keys(obj: dict[str, Any], allowed: set[str], *, required: set[str] | None = None, where: str = "object") -> None:
    if not isinstance(obj, dict):
        raise ValidationError(f"{where} must be an object")
    unknown = set(obj) - allowed
    if unknown:
        raise ValidationError(f"{where} has unknown keys: {sorted(unknown)!r}")
    req = allowed if required is None else required
    missing = req - set(obj)
    if missing:
        raise ValidationError(f"{where} is missing keys: {sorted(missing)!r}")


def _no_control(value: str, *, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{where} must be a non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValidationError(f"{where} contains control characters")
    return value


def _validate_name(value: str, *, where: str = "name") -> str:
    _no_control(value, where=where)
    if not SAFE_NAME.fullmatch(value):
        raise ValidationError(f"{where} must match {SAFE_NAME.pattern}")
    return value


def _validate_ref(value: str) -> str:
    _no_control(value, where="ref")
    if not REF_NAME.fullmatch(value):
        raise ValidationError(f"invalid ref name: {value!r}")
    if ".." in value or "@{" in value or "//" in value or value.endswith((".", "/")) or "/." in value:
        raise ValidationError(f"unsafe ref name: {value!r}")
    return value


def _validate_oid(value: str, *, object_format: str | None = None) -> str:
    if not isinstance(value, str) or not HEX_OID.fullmatch(value):
        raise ValidationError("malformed Git object id")
    if object_format == "sha1" and len(value) != 40:
        raise ValidationError("object id does not match sha1 repository")
    if object_format == "sha256" and len(value) != 64:
        raise ValidationError("object id does not match sha256 repository")
    return value


def _path_no_parent_escape(raw: str | os.PathLike[str], *, where: str) -> Path:
    text = os.fspath(raw)
    _no_control(text, where=where)
    p = Path(text)
    if any(part == ".." for part in p.parts):
        raise ValidationError(f"{where} contains parent traversal")
    return p


def _assert_no_symlink_ancestors(path: Path, *, include_leaf: bool, where: str) -> None:
    probe = path.absolute()
    parts = probe.parents if not include_leaf else (probe, *probe.parents)
    for item in parts:
        try:
            if item.is_symlink():
                raise ValidationError(f"{where} traverses a symlink: {item}")
        except OSError as exc:
            raise ValidationError(f"cannot inspect {where}") from exc


def _existing_regular_file(raw: str | os.PathLike[str], *, where: str) -> Path:
    p = _path_no_parent_escape(raw, where=where)
    _assert_no_symlink_ancestors(p, include_leaf=True, where=where)
    try:
        st = p.stat()
    except OSError as exc:
        raise ValidationError(f"{where} is not readable") from exc
    if not stat.S_ISREG(st.st_mode):
        raise ValidationError(f"{where} must be a regular file")
    return p.resolve()


def _existing_directory(raw: str | os.PathLike[str], *, where: str) -> Path:
    p = _path_no_parent_escape(raw, where=where)
    _assert_no_symlink_ancestors(p, include_leaf=True, where=where)
    try:
        st = p.stat()
    except OSError as exc:
        raise ValidationError(f"{where} is not readable") from exc
    if not stat.S_ISDIR(st.st_mode):
        raise ValidationError(f"{where} must be a directory")
    return p.resolve()


def _new_output_target(raw: str | os.PathLike[str], *, where: str, directory: bool) -> Path:
    p = _path_no_parent_escape(raw, where=where)
    if p.exists() or p.is_symlink():
        raise ValidationError(f"{where} already exists")
    parent = p.parent if p.parent != Path("") else Path(".")
    parent = _existing_directory(parent, where=f"{where} parent")
    target = parent / p.name
    _assert_no_symlink_ancestors(target, include_leaf=False, where=where)
    if directory and not target.name:
        raise ValidationError(f"{where} has no directory name")
    return target


def _run_git(args: list[str], *, cwd: Path | None = None, timeout: int = 30) -> GitResult:
    env = os.environ.copy()
    env.update(
        {
            "LC_ALL": "C",
            "LANG": "C",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise VerificationError(f"git command failed to execute: {args[0] if args else '<none>'}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        if len(detail) > 800:
            detail = detail[:800] + "..."
        raise VerificationError(f"git {' '.join(args[:3])} failed ({proc.returncode}): {detail}")
    return GitResult(proc.stdout, proc.stderr)


def _git_try(args: list[str], *, cwd: Path, timeout: int = 30) -> tuple[int, str, str]:
    env = os.environ.copy()
    env.update({"LC_ALL": "C", "LANG": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"})
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise VerificationError("git command failed to execute") from exc
    return proc.returncode, proc.stdout, proc.stderr


def _object_format(repo: Path) -> str:
    value = _run_git(["rev-parse", "--show-object-format"], cwd=repo).stdout.strip()
    if value not in {"sha1", "sha256"}:
        raise VerificationError(f"unsupported Git object format: {value!r}")
    return value


def _read_refs(repo: Path, *, object_format: str) -> list[dict[str, str]]:
    result = _run_git(["for-each-ref", "--format=%(refname)%00%(objectname)"], cwd=repo)
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in result.stdout.splitlines():
        if not raw:
            continue
        try:
            ref, oid = raw.split("\x00", 1)
        except ValueError as exc:
            raise VerificationError("unexpected for-each-ref output") from exc
        _validate_ref(ref)
        _validate_oid(oid, object_format=object_format)
        if ref in seen:
            raise VerificationError(f"duplicate repository ref: {ref}")
        seen.add(ref)
        refs.append({"name": ref, "object_id": oid})
    refs.sort(key=lambda item: item["name"])
    if not refs:
        raise VerificationError("repository has no refs to snapshot")
    return refs


def _read_head(repo: Path, *, object_format: str) -> dict[str, Any]:
    oid = _run_git(["rev-parse", "--verify", "HEAD"], cwd=repo).stdout.strip()
    _validate_oid(oid, object_format=object_format)
    rc, out, _ = _git_try(["symbolic-ref", "-q", "HEAD"], cwd=repo)
    if rc == 0:
        target = out.strip()
        _validate_ref(target)
        return {"mode": "symbolic", "target": target, "object_id": oid}
    if rc == 1:
        return {"mode": "detached", "target": None, "object_id": oid}
    raise VerificationError("unable to inspect repository HEAD")


def _parse_bundle_heads(bundle: Path, *, object_format: str) -> dict[str, str]:
    result = _run_git(["bundle", "list-heads", str(bundle)])
    heads: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line:
            continue
        try:
            oid, ref = line.split(" ", 1)
        except ValueError as exc:
            raise VerificationError("malformed git bundle list-heads output") from exc
        _validate_oid(oid, object_format=object_format)
        _no_control(ref, where="bundle ref")
        if ref in heads and heads[ref] != oid:
            raise VerificationError("bundle advertises conflicting duplicate refs")
        heads[ref] = oid
    return heads


def _manifest_ref_map(manifest: dict[str, Any]) -> dict[str, str]:
    refs = manifest["refs"]
    if not isinstance(refs, list) or not refs:
        raise ValidationError("manifest refs must be a non-empty list")
    out: dict[str, str] = {}
    object_format = manifest["object_format"]
    for idx, item in enumerate(refs):
        _exact_keys(item, {"name", "object_id"}, where=f"manifest refs[{idx}]")
        name = _validate_ref(item["name"])
        oid = _validate_oid(item["object_id"], object_format=object_format)
        if name in out:
            raise ValidationError("duplicate ref in manifest")
        out[name] = oid
    return out


def _validate_snapshot_manifest(manifest: Any) -> dict[str, Any]:
    _exact_keys(
        manifest,
        {"schema", "repository_label", "object_format", "head", "refs", "bundle", "verification", "authority"},
        where="snapshot manifest",
    )
    if manifest["schema"] != SNAPSHOT_SCHEMA:
        raise ValidationError("unsupported snapshot manifest schema")
    _validate_name(manifest["repository_label"], where="repository_label")
    if manifest["object_format"] not in {"sha1", "sha256"}:
        raise ValidationError("unsupported object format")
    head = manifest["head"]
    _exact_keys(head, {"mode", "target", "object_id"}, where="manifest head")
    if head["mode"] not in {"symbolic", "detached"}:
        raise ValidationError("invalid HEAD mode")
    _validate_oid(head["object_id"], object_format=manifest["object_format"])
    if head["mode"] == "symbolic":
        _validate_ref(head["target"])
    elif head["target"] is not None:
        raise ValidationError("detached HEAD target must be null")
    _manifest_ref_map(manifest)

    bundle = manifest["bundle"]
    _exact_keys(bundle, {"file", "sha256", "size_bytes"}, where="manifest bundle")
    if bundle["file"] != "repository.bundle":
        raise ValidationError("unexpected bundle filename")
    if not isinstance(bundle["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", bundle["sha256"]):
        raise ValidationError("invalid bundle SHA-256")
    if isinstance(bundle["size_bytes"], bool) or not isinstance(bundle["size_bytes"], int) or bundle["size_bytes"] <= 0:
        raise ValidationError("invalid bundle size")

    verification = manifest["verification"]
    _exact_keys(verification, {"bundle_verify", "restore_fsck", "ref_equality", "head_equality"}, where="manifest verification")
    if any(verification[key] != "PASS" for key in verification):
        raise ValidationError("snapshot manifest cannot self-assert a non-PASS finalized verification")

    authority = manifest["authority"]
    expected_authority = {
        "delete_source_repo": False,
        "publish_source_repo": False,
        "change_visibility": False,
        "billing_change": False,
        "push_destination": False,
    }
    if authority != expected_authority:
        raise ValidationError("snapshot authority ceiling must remain hard-false")
    return manifest


def _restore_and_verify(bundle: Path, manifest: dict[str, Any]) -> None:
    object_format = manifest["object_format"]
    expected_refs = _manifest_ref_map(manifest)
    expected_head = manifest["head"]

    bundle_heads = _parse_bundle_heads(bundle, object_format=object_format)
    advertised_refs = {k: v for k, v in bundle_heads.items() if k.startswith("refs/")}
    if advertised_refs != expected_refs:
        raise VerificationError("bundle advertised refs do not match manifest refs")
    if "HEAD" in bundle_heads and bundle_heads["HEAD"] != expected_head["object_id"]:
        raise VerificationError("bundle HEAD does not match manifest HEAD")

    with tempfile.TemporaryDirectory(prefix="repo-portability-restore-") as td:
        restored = Path(td) / "restored.git"
        _run_git(["init", "--bare", f"--object-format={object_format}", str(restored)])
        # Fetch every advertised namespace without interpreting any owner input as an option.
        _run_git(["fetch", "--force", "--no-tags", str(bundle), "+refs/*:refs/*"], cwd=restored, timeout=60)

        if expected_head["mode"] == "symbolic":
            _run_git(["symbolic-ref", "HEAD", expected_head["target"]], cwd=restored)
        else:
            _run_git(["update-ref", "--no-deref", "HEAD", expected_head["object_id"]], cwd=restored)

        _run_git(["fsck", "--full", "--no-reflogs"], cwd=restored, timeout=60)
        actual_refs = {item["name"]: item["object_id"] for item in _read_refs(restored, object_format=object_format)}
        if actual_refs != expected_refs:
            raise VerificationError("restored refs do not match manifest refs")
        actual_head = _read_head(restored, object_format=object_format)
        if actual_head != expected_head:
            raise VerificationError("restored HEAD does not match manifest HEAD")


def verify_snapshot(bundle_path: str | os.PathLike[str], manifest_path: str | os.PathLike[str]) -> dict[str, Any]:
    bundle = _existing_regular_file(bundle_path, where="bundle")
    manifest_file = _existing_regular_file(manifest_path, where="manifest")
    manifest_bytes = manifest_file.read_bytes()
    manifest = _validate_snapshot_manifest(loads_strict(manifest_bytes))
    if manifest_bytes != canonical_json(manifest):
        raise VerificationError("manifest is not canonical JSON")

    data = bundle.read_bytes()
    if len(data) != manifest["bundle"]["size_bytes"]:
        raise VerificationError("bundle byte size mismatch")
    if sha256_bytes(data) != manifest["bundle"]["sha256"]:
        raise VerificationError("bundle SHA-256 mismatch")

    # A full --all bundle must have no missing prerequisites when verified against its source-independent payload.
    # `list-heads` plus independent restore/fsck/ref equality is the trust-bearing proof.
    _restore_and_verify(bundle, manifest)
    return manifest


def _write_exclusive(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, mode)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def create_snapshot(
    repo_path: str | os.PathLike[str],
    out_dir: str | os.PathLike[str],
    *,
    repository_label: str | None = None,
) -> dict[str, Any]:
    repo = _existing_directory(repo_path, where="repository")
    _run_git(["rev-parse", "--git-dir"], cwd=repo)
    object_format = _object_format(repo)
    refs = _read_refs(repo, object_format=object_format)
    head = _read_head(repo, object_format=object_format)
    label = _validate_name(repository_label or repo.name, where="repository_label")
    target = _new_output_target(out_dir, where="snapshot output", directory=True)

    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.stage-", dir=str(target.parent)))
    try:
        bundle = staging / "repository.bundle"
        _run_git(["bundle", "create", str(bundle), "--all"], cwd=repo, timeout=120)
        # Explicit source-side bundle verification, then independent restore below.
        _run_git(["bundle", "verify", str(bundle)], cwd=repo, timeout=60)
        bundle_bytes = bundle.read_bytes()

        manifest: dict[str, Any] = {
            "schema": SNAPSHOT_SCHEMA,
            "repository_label": label,
            "object_format": object_format,
            "head": head,
            "refs": refs,
            "bundle": {
                "file": "repository.bundle",
                "sha256": sha256_bytes(bundle_bytes),
                "size_bytes": len(bundle_bytes),
            },
            "verification": {
                "bundle_verify": "PASS",
                "restore_fsck": "PASS",
                "ref_equality": "PASS",
                "head_equality": "PASS",
            },
            "authority": {
                "delete_source_repo": False,
                "publish_source_repo": False,
                "change_visibility": False,
                "billing_change": False,
                "push_destination": False,
            },
        }
        _validate_snapshot_manifest(manifest)
        _restore_and_verify(bundle, manifest)
        _write_exclusive(staging / "manifest.json", canonical_json(manifest))
        os.replace(staging, target)
        staging = None  # type: ignore[assignment]
        # Final bytes must verify from their published location.
        return verify_snapshot(target / "repository.bundle", target / "manifest.json")
    finally:
        if staging is not None and Path(staging).exists():
            shutil.rmtree(staging, ignore_errors=True)


def _validate_destination_url(value: str) -> str:
    _no_control(value, where="destination_url")
    if any(ch.isspace() for ch in value):
        raise ValidationError("destination_url contains whitespace")
    split = urlsplit(value)
    if split.scheme not in {"https", "ssh"}:
        raise ValidationError("destination_url must use https:// or ssh://")
    if not split.hostname or not split.path or split.path == "/":
        raise ValidationError("destination_url must name a host and repository path")
    if split.username is not None or split.password is not None:
        raise ValidationError("destination_url userinfo/credentials are forbidden")
    if split.query or split.fragment:
        raise ValidationError("destination_url query/fragment is forbidden")
    if split.port is not None and not (1 <= split.port <= 65535):
        raise ValidationError("destination_url has invalid port")
    return value


def _validate_bundle_locator(value: str) -> str:
    _no_control(value, where="bundle_path")
    p = Path(value)
    if any(part == ".." for part in p.parts):
        raise ValidationError("bundle_path contains parent traversal")
    if value.startswith("-"):
        raise ValidationError("bundle_path cannot begin with '-'")
    return value


def _validate_inventory(inventory: Any) -> dict[str, Any]:
    _exact_keys(inventory, {"schema", "repositories"}, where="inventory")
    if inventory["schema"] != INVENTORY_SCHEMA:
        raise ValidationError("unsupported inventory schema")
    repos = inventory["repositories"]
    if not isinstance(repos, list) or not repos:
        raise ValidationError("inventory repositories must be a non-empty list")
    if len(repos) > 1000:
        raise ValidationError("inventory too large")
    seen: set[str] = set()
    for idx, item in enumerate(repos):
        _exact_keys(
            item,
            {"name", "action", "bundle_path", "destination_url"},
            required={"name", "action"},
            where=f"repositories[{idx}]",
        )
        name = _validate_name(item["name"], where=f"repositories[{idx}].name")
        if name in seen:
            raise ValidationError("duplicate repository name")
        seen.add(name)
        action = item["action"]
        if action not in ACTIONS:
            raise ValidationError(f"unsupported action: {action!r}")
        bundle = item.get("bundle_path")
        destination = item.get("destination_url")
        if action in {"MIGRATE_PRIVATE", "COLD_ARCHIVE"}:
            if bundle is None:
                raise ValidationError(f"{action} requires bundle_path")
            _validate_bundle_locator(bundle)
        elif bundle is not None:
            _validate_bundle_locator(bundle)
        if action == "MIGRATE_PRIVATE":
            if destination is None:
                raise ValidationError("MIGRATE_PRIVATE requires destination_url")
            _validate_destination_url(destination)
        elif destination is not None:
            raise ValidationError(f"{action} must not include destination_url")
    return inventory


def compile_migration_plan(inventory_bytes: bytes) -> bytes:
    inventory = _validate_inventory(loads_strict(inventory_bytes))
    source_hash = sha256_bytes(inventory_bytes)
    entries: list[dict[str, Any]] = []

    for item in inventory["repositories"]:
        name = item["name"]
        action = item["action"]
        base: dict[str, Any] = {
            "name": name,
            "action": action,
            "commands": [],
            "destination_push_authorized": False,
            "source_deletion_authorized": False,
            "visibility_change_authorized": False,
            "publication_authorized": False,
        }
        if action == "MIGRATE_PRIVATE":
            restored = f"{name}.mirror.git"
            base["state"] = "PLAN_REQUIRES_SEPARATE_EXECUTOR_APPROVAL"
            base["commands"] = [
                ["git", "clone", "--mirror", item["bundle_path"], restored],
                ["git", "-C", restored, "remote", "add", "destination", item["destination_url"]],
                ["git", "-C", restored, "push", "--mirror", "destination"],
            ]
        elif action == "COLD_ARCHIVE":
            base["state"] = "HOLD_UNTIL_SNAPSHOT_VERIFIED_AND_ARCHIVE_CUSTODY_PROVEN"
            base["commands"] = [
                ["python", "-m", "tools.repo_portability.cli", "verify", "--bundle", item["bundle_path"], "--manifest", str(Path(item["bundle_path"]).with_name("manifest.json"))]
            ]
        elif action == "KEEP_PRIVATE":
            base["state"] = "KEEP_PRIVATE_NO_MUTATION"
        elif action == "PUBLIC_REVIEW":
            base["state"] = "HOLD_PUBLICATION_REVIEW_REQUIRED"
        else:  # unreachable after validation
            raise AssertionError(action)
        entries.append(base)

    plan = {
        "schema": PLAN_SCHEMA,
        "inventory_sha256": source_hash,
        "repositories": entries,
        "authority": {
            "execute_commands": False,
            "delete_source_repo": False,
            "publish_source_repo": False,
            "change_visibility": False,
            "billing_change": False,
            "push_destination": False,
        },
    }
    return canonical_json(plan)


def write_migration_plan(
    inventory_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
) -> dict[str, Any]:
    src = _existing_regular_file(inventory_path, where="inventory")
    target = _new_output_target(output_path, where="plan output", directory=False)
    data = compile_migration_plan(src.read_bytes())
    _write_exclusive(target, data)
    parsed = loads_strict(data)
    if target.read_bytes() != canonical_json(parsed):
        raise VerificationError("published plan failed canonical readback")
    return parsed
