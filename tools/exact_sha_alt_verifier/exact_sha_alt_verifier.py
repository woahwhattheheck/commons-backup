#!/usr/bin/env python3
"""Exact-SHA alternate (non-hosted) verification receipts.

This tool intentionally does not claim hosted/GitHub CI authority. It checks out
one exact commit into a fresh workspace, runs only explicit argv commands, and
emits a tamper-evident receipt for offline/equivalent evidence policies.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import hmac
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import tempfile
from typing import Any, Iterable
from urllib.parse import urlsplit

VERIFICATION_KIND = "alternate_nonhosted"
SCHEMA = "exact-sha-alt-verifier-v1"
SHA_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")
MAX_COMMANDS = 64
MAX_ARGV = 128
MAX_ARTIFACTS = 1000
DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_PREVIEW_BYTES = 4096
MAX_PREVIEW_BYTES = 65536


class VerifyError(ValueError):
    """Deterministic verifier input or execution error."""


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def _safe_repo(repo: str) -> str:
    repo = str(repo or "").strip()
    if not repo:
        raise VerifyError("repo is required")
    parsed = urlsplit(repo)
    if parsed.scheme:
        if parsed.scheme.lower() not in {"https", "http", "file"}:
            raise VerifyError("repo URL scheme must be https, http, or file")
        if parsed.username is not None or parsed.password is not None:
            raise VerifyError("repo URL must not contain credentials")
    elif re.match(r"^[^/\\]+@[^:]+:", repo):
        raise VerifyError("scp-style repository URLs are not allowed")
    return repo


def _safe_sha(value: str) -> str:
    value = str(value or "").strip().lower()
    if not SHA_RE.fullmatch(value):
        raise VerifyError("exact_sha must be a full 40-64 character hexadecimal object id")
    return value


def _safe_artifact_pattern(value: str) -> str:
    value = str(value or "").strip().replace("\\", "/")
    if not value or value.startswith("/") or re.match(r"^[A-Za-z]:/", value):
        raise VerifyError(f"artifact pattern must be relative: {value!r}")
    if ".." in Path(value).parts:
        raise VerifyError(f"artifact pattern may not traverse parents: {value!r}")
    return value


def _load_spec(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerifyError(f"cannot read spec: {exc}") from exc
    if not isinstance(raw, dict):
        raise VerifyError("spec must be a JSON object")
    allowed = {"repo", "exact_sha", "commands", "artifacts", "timeout_seconds", "log_preview_bytes"}
    extra = sorted(set(raw) - allowed)
    if extra:
        raise VerifyError(f"unknown spec fields: {', '.join(extra)}")
    repo = _safe_repo(raw.get("repo", ""))
    exact_sha = _safe_sha(raw.get("exact_sha", ""))
    commands = raw.get("commands")
    if not isinstance(commands, list) or not commands or len(commands) > MAX_COMMANDS:
        raise VerifyError(f"commands must be a non-empty list of at most {MAX_COMMANDS} argv arrays")
    clean_commands: list[list[str]] = []
    for index, argv in enumerate(commands):
        if not isinstance(argv, list) or not argv or len(argv) > MAX_ARGV:
            raise VerifyError(f"commands[{index}] must be a non-empty argv list of at most {MAX_ARGV} items")
        if any(not isinstance(item, str) or "\x00" in item for item in argv):
            raise VerifyError(f"commands[{index}] argv items must be NUL-free strings")
        if not argv[0].strip():
            raise VerifyError(f"commands[{index}][0] may not be blank")
        _reject_obvious_provider_mutator(argv)
        clean_commands.append(argv)
    artifacts = raw.get("artifacts", [])
    if not isinstance(artifacts, list) or any(not isinstance(item, str) for item in artifacts):
        raise VerifyError("artifacts must be a list of relative glob strings")
    clean_artifacts = [_safe_artifact_pattern(item) for item in artifacts]
    timeout = raw.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not (0 < float(timeout) <= 3600):
        raise VerifyError("timeout_seconds must be > 0 and <= 3600")
    preview = raw.get("log_preview_bytes", DEFAULT_PREVIEW_BYTES)
    if isinstance(preview, bool) or not isinstance(preview, int) or not (0 <= preview <= MAX_PREVIEW_BYTES):
        raise VerifyError(f"log_preview_bytes must be an integer between 0 and {MAX_PREVIEW_BYTES}")
    return {
        "repo": repo,
        "exact_sha": exact_sha,
        "commands": clean_commands,
        "artifacts": clean_artifacts,
        "timeout_seconds": float(timeout),
        "log_preview_bytes": preview,
    }


def _reject_obvious_provider_mutator(argv: list[str]) -> None:
    """Reject direct provider/package publication commands; this is not a sandbox."""
    exe = Path(argv[0]).name.lower()
    args = [item.lower() for item in argv[1:]]
    if exe == "git" and args and args[0] in {"push", "send-email"}:
        raise VerifyError("provider-mutating git command is not allowed")
    if exe in {"gh", "glab"}:
        raise VerifyError(f"provider CLI {exe!r} is not allowed in alternate verification commands")
    if exe in {"curl", "wget", "scp", "sftp", "ssh"}:
        raise VerifyError(f"network-capable command {exe!r} is not allowed in alternate verification commands")
    if exe in {"npm", "pnpm", "yarn"} and any(item == "publish" for item in args):
        raise VerifyError("package publication is not allowed")
    if exe in {"twine"} or (exe.startswith("python") and "-m" in args and "twine" in args):
        raise VerifyError("package publication is not allowed")


def _scrubbed_env(home: Path, temp: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    env.update({
        "HOME": str(home),
        "USERPROFILE": str(home),
        "TMPDIR": str(temp),
        "TMP": str(temp),
        "TEMP": str(temp),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "CI": "true",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "SSH_ASKPASS_REQUIRE": "never",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    return env


def _run_capture(argv: list[str], *, cwd: Path, env: dict[str, str], timeout: float, out: Path, err: Path) -> tuple[int, bool]:
    creationflags = 0
    kwargs: dict[str, Any] = {}
    if os.name == "posix":
        kwargs["start_new_session"] = True
    elif os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    with out.open("wb") as stdout, err.open("wb") as stderr:
        try:
            proc = subprocess.Popen(argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                                    stdout=stdout, stderr=stderr, shell=False,
                                    creationflags=creationflags, **kwargs)
        except OSError as exc:
            stderr.write(f"launch error: {exc}\n".encode("utf-8", "replace"))
            return 127, False
        try:
            code = proc.wait(timeout=timeout)
            return int(code), False
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                proc.kill()
            proc.wait()
            return 124, True


def _log_record(path: Path, preview_bytes: int) -> dict[str, Any]:
    digest, size = _sha256_file(path)
    with path.open("rb") as handle:
        preview = handle.read(preview_bytes)
    return {
        "sha256": digest,
        "bytes": size,
        "preview_utf8": preview.decode("utf-8", "replace"),
        "preview_truncated": size > len(preview),
    }


def _git(argv: list[str], *, cwd: Path, env: dict[str, str], check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *argv], cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False)
    if check and result.returncode != 0:
        raise VerifyError(f"git {' '.join(argv)} failed ({result.returncode}): {result.stderr.strip()}")
    return result


def _head_sha(root: Path, env: dict[str, str]) -> str:
    return _git(["rev-parse", "HEAD"], cwd=root, env=env).stdout.strip().lower()


def _assert_exact_head(requested: str, actual: str) -> None:
    if requested.lower() != actual.lower():
        raise VerifyError(f"wrong SHA: requested {requested}, checkout is {actual}")


def _tree_status(root: Path, env: dict[str, str]) -> list[str]:
    result = _git(["status", "--porcelain=v1", "--untracked-files=all"], cwd=root, env=env)
    return [line for line in result.stdout.splitlines() if line]


def _assert_clean(root: Path, env: dict[str, str]) -> None:
    rows = _tree_status(root, env)
    if rows:
        raise VerifyError("checkout is dirty: " + "; ".join(rows[:20]))


def _runtime() -> dict[str, str]:
    git_version = subprocess.run(["git", "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, check=False).stdout.strip()
    return {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "git": git_version,
    }


def _artifacts(root: Path, patterns: Iterable[str]) -> list[dict[str, Any]]:
    found: dict[str, Path] = {}
    root_real = root.resolve()
    for pattern in patterns:
        for raw in glob.glob(str(root / pattern), recursive=True):
            path = Path(raw)
            if path.is_symlink() or not path.is_file():
                continue
            resolved = path.resolve()
            try:
                rel = resolved.relative_to(root_real).as_posix()
            except ValueError as exc:
                raise VerifyError(f"artifact escaped checkout: {path}") from exc
            found[rel] = resolved
            if len(found) > MAX_ARTIFACTS:
                raise VerifyError(f"artifact match count exceeds {MAX_ARTIFACTS}")
    rows = []
    for rel, path in sorted(found.items()):
        digest, size = _sha256_file(path)
        rows.append({"path": rel, "bytes": size, "sha256": digest})
    return rows


def _seal(receipt: dict[str, Any]) -> dict[str, Any]:
    body = copy_without_receipt_id(receipt)
    receipt["receipt_id"] = hashlib.sha256(_canonical_bytes(body)).hexdigest()
    return receipt


def copy_without_receipt_id(receipt: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in receipt.items() if key != "receipt_id"}


def verify_receipt(receipt: dict[str, Any]) -> bool:
    if not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA:
        return False
    receipt_id = receipt.get("receipt_id")
    if not isinstance(receipt_id, str) or not re.fullmatch(r"[0-9a-f]{64}", receipt_id):
        return False
    expected = hashlib.sha256(_canonical_bytes(copy_without_receipt_id(receipt))).hexdigest()
    return hmac.compare_digest(receipt_id, expected)


def run_spec(spec: dict[str, Any], receipt_path: Path) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "verification_kind": VERIFICATION_KIND,
        "authority": {
            "hosted_ci_green": False,
            "overrides_required_checks": False,
            "merge_authority": False,
            "credentials_inherited": False,
            "network_sandbox_claimed": False,
        },
        "repo": spec["repo"],
        "requested_sha": spec["exact_sha"],
        "checkout_sha": None,
        "detached_head": False,
        "pre_tree_clean": False,
        "post_tree_clean": False,
        "post_checkout_sha": None,
        "runtime": _runtime(),
        "policy": {
            "shell": False,
            "timeout_seconds": spec["timeout_seconds"],
            "log_preview_bytes": spec["log_preview_bytes"],
            "artifact_patterns": list(spec["artifacts"]),
            "max_artifacts": MAX_ARTIFACTS,
        },
        "commands": [],
        "artifacts": [],
        "outcome": "FAILED",
        "failure": None,
    }
    with tempfile.TemporaryDirectory(prefix="exact-sha-alt-") as tmp_name:
        tmp = Path(tmp_name)
        home = tmp / "home"; home.mkdir()
        scratch = tmp / "tmp"; scratch.mkdir()
        checkout = tmp / "checkout"; checkout.mkdir()
        logs = tmp / "logs"; logs.mkdir()
        env = _scrubbed_env(home, scratch)
        try:
            _git(["init", "-q"], cwd=checkout, env=env)
            _git(["remote", "add", "origin", spec["repo"]], cwd=checkout, env=env)
            _git(["fetch", "--no-tags", "--depth=1", "--no-recurse-submodules", "origin", spec["exact_sha"]], cwd=checkout, env=env)
            _git(["checkout", "--detach", "-q", "FETCH_HEAD"], cwd=checkout, env=env)
            actual = _head_sha(checkout, env)
            receipt["checkout_sha"] = actual
            _assert_exact_head(spec["exact_sha"], actual)
            symbolic = _git(["symbolic-ref", "-q", "HEAD"], cwd=checkout, env=env, check=False)
            receipt["detached_head"] = symbolic.returncode != 0
            if not receipt["detached_head"]:
                raise VerifyError("checkout HEAD is not detached")
            _assert_clean(checkout, env)
            receipt["pre_tree_clean"] = True
            for index, argv in enumerate(spec["commands"]):
                out = logs / f"{index:03d}.stdout"
                err = logs / f"{index:03d}.stderr"
                code, timed_out = _run_capture(argv, cwd=checkout, env=env,
                                               timeout=spec["timeout_seconds"], out=out, err=err)
                row = {
                    "argv": argv,
                    "exit_code": code,
                    "timed_out": timed_out,
                    "stdout": _log_record(out, spec["log_preview_bytes"]),
                    "stderr": _log_record(err, spec["log_preview_bytes"]),
                }
                receipt["commands"].append(row)
                if code != 0:
                    raise VerifyError(f"command {index} exited {code}")
            post_sha = _head_sha(checkout, env)
            receipt["post_checkout_sha"] = post_sha
            _assert_exact_head(spec["exact_sha"], post_sha)
            post_symbolic = _git(["symbolic-ref", "-q", "HEAD"], cwd=checkout, env=env, check=False)
            if post_symbolic.returncode == 0:
                raise VerifyError("checkout HEAD is no longer detached after commands")
            dirty = _tree_status(checkout, env)
            receipt["post_tree_clean"] = not dirty
            if dirty:
                raise VerifyError("checkout dirty after commands: " + "; ".join(dirty[:20]))
            receipt["artifacts"] = _artifacts(checkout, spec["artifacts"])
            receipt["outcome"] = "PASSED"
        except (VerifyError, OSError) as exc:
            receipt["failure"] = str(exc) if isinstance(exc, VerifyError) else f"I/O error: {exc}"
            if receipt["checkout_sha"] is not None and not receipt["post_tree_clean"]:
                try:
                    receipt["post_tree_clean"] = not _tree_status(checkout, env)
                except VerifyError:
                    pass
        finally:
            _seal(receipt)
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_bytes(_canonical_bytes(receipt))
    return receipt


def cmd_run(args: argparse.Namespace) -> int:
    try:
        spec = _load_spec(args.spec)
        receipt = run_spec(spec, args.receipt)
    except VerifyError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"outcome": receipt["outcome"], "receipt_id": receipt["receipt_id"],
                      "verification_kind": receipt["verification_kind"]}, sort_keys=True))
    return 0 if receipt["outcome"] == "PASSED" else 1


def cmd_verify(args: argparse.Namespace) -> int:
    try:
        raw = json.loads(args.receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    ok = verify_receipt(raw)
    print(json.dumps({"receipt_valid": ok, "receipt_id": raw.get("receipt_id")}, sort_keys=True))
    return 0 if ok else 1


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run an exact-SHA verification spec")
    run.add_argument("spec", type=Path)
    run.add_argument("--receipt", type=Path, required=True)
    run.set_defaults(func=cmd_run)
    verify = sub.add_parser("verify-receipt", help="verify receipt integrity")
    verify.add_argument("receipt", type=Path)
    verify.set_defaults(func=cmd_verify)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
