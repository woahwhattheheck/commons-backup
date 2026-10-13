"""Hermetic offline execution and dependency-closure evidence for ARC3 SAGE.

This module is deliberately additive to the existing Kaggle packager.  It consumes
that packager's ``source_manifest.json`` and bundle layout (``src/**``), rebinds
every source byte immediately before execution, proves that imports are local or
Python-stdlib only, and executes a selected entrypoint in an isolated interpreter
with an audit-hook fence around network/process escape.

It does not submit to Kaggle, call ARC providers, or invent a platform memory
limit.  Runtime measurements are evidence, not authority.
"""
from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from typing import Mapping, Sequence

_SCHEMA_MANIFEST = "arc3-sage-offline-source-manifest/v1"
_SCHEMA_CLOSURE = "arc3-sage-dependency-closure/v1"
_SCHEMA_RECEIPT = "arc3-sage-hermetic-execution/v1"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class HermeticError(ValueError):
    """Bundle or execution evidence does not satisfy the hermetic contract."""


@dataclass(frozen=True)
class ExecutionPolicy:
    """Local execution limits; these are not claims about Kaggle hardware."""

    timeout_seconds: float
    competition_runtime_seconds: float = 32_400.0
    runtime_margin_fraction: float = 0.80
    memory_limit_mib: float | None = None
    max_output_bytes: int = 1 << 20
    poll_interval_seconds: float = 0.01
    terminate_grace_seconds: float = 0.25

    def __post_init__(self) -> None:
        finite_positive = {
            "timeout_seconds": self.timeout_seconds,
            "competition_runtime_seconds": self.competition_runtime_seconds,
            "poll_interval_seconds": self.poll_interval_seconds,
            "terminate_grace_seconds": self.terminate_grace_seconds,
        }
        for name, value in finite_positive.items():
            if not math.isfinite(value) or value <= 0:
                raise HermeticError(f"{name} must be finite positive")
        if not math.isfinite(self.runtime_margin_fraction) or not 0 < self.runtime_margin_fraction < 1:
            raise HermeticError("runtime_margin_fraction must be in (0,1)")
        if self.memory_limit_mib is not None and (
            not math.isfinite(self.memory_limit_mib) or self.memory_limit_mib <= 0
        ):
            raise HermeticError("memory_limit_mib must be finite positive when declared")
        if isinstance(self.max_output_bytes, bool) or not isinstance(self.max_output_bytes, int) or self.max_output_bytes <= 0:
            raise HermeticError("max_output_bytes must be a positive integer")


@dataclass(frozen=True)
class ExecutionReceipt:
    schema: str
    entrypoint: str
    source_manifest_sha256: str
    dependency_closure_sha256: str
    execution_identity_sha256: str
    returncode: int
    timed_out: bool
    output_limit_exceeded: bool
    wall_seconds: float
    peak_process_tree_rss_mib: float | None
    rss_measurement: str
    stdout_bytes: int
    stderr_bytes: int
    stdout_sha256: str
    stderr_sha256: str
    source_unchanged_after_execution: bool
    policy: Mapping[str, object]
    blockers: tuple[str, ...]
    state: str
    authority: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.schema != _SCHEMA_RECEIPT:
            raise HermeticError("unexpected receipt schema")
        for name in ("source_manifest_sha256", "dependency_closure_sha256", "execution_identity_sha256",
                     "stdout_sha256", "stderr_sha256"):
            if not _HEX64.fullmatch(getattr(self, name)):
                raise HermeticError(f"{name} must be lowercase sha256")
        if not math.isfinite(self.wall_seconds) or self.wall_seconds < 0:
            raise HermeticError("wall_seconds invalid")
        if self.peak_process_tree_rss_mib is not None and (
            not math.isfinite(self.peak_process_tree_rss_mib) or self.peak_process_tree_rss_mib < 0
        ):
            raise HermeticError("peak_process_tree_rss_mib invalid")
        if self.stdout_bytes < 0 or self.stderr_bytes < 0:
            raise HermeticError("output byte counts invalid")


@dataclass
class _Capture:
    limit: int
    data: bytearray
    total: int = 0
    overflow: bool = False

    def feed(self, chunk: bytes) -> None:
        self.total += len(chunk)
        room = max(0, self.limit - len(self.data))
        if room:
            self.data.extend(chunk[:room])
        if self.total > self.limit:
            self.overflow = True


def _canonical_sha(obj: object) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return sha256(raw).hexdigest()


def _load_manifest(bundle_root: Path) -> dict[str, object]:
    path = bundle_root / "source_manifest.json"
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise HermeticError(f"cannot read source_manifest.json: {exc.__class__.__name__}") from exc
    try:
        obj = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HermeticError("source_manifest.json is not valid UTF-8 JSON") from exc
    if not isinstance(obj, dict) or obj.get("schema") != _SCHEMA_MANIFEST:
        raise HermeticError("unexpected source manifest schema")
    findings = obj.get("network_or_secret_findings")
    if not isinstance(findings, list) or findings:
        raise HermeticError("source manifest offline/secret findings are not clean")
    manifest_sha = obj.get("manifest_sha256")
    if not isinstance(manifest_sha, str) or not _HEX64.fullmatch(manifest_sha):
        raise HermeticError("source manifest missing valid manifest_sha256")
    unsigned = dict(obj)
    unsigned.pop("manifest_sha256", None)
    if _canonical_sha(unsigned) != manifest_sha:
        raise HermeticError("source manifest self-hash mismatch")
    return obj


def _safe_relpath(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise HermeticError("manifest path must be non-empty POSIX text")
    rel = PurePosixPath(value)
    if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
        raise HermeticError(f"unsafe manifest path: {value!r}")
    return rel


def _read_regular_no_symlink(src_root: Path, rel: PurePosixPath) -> bytes:
    """Read one manifest file through held directory FDs without path re-resolution."""
    if os.open not in getattr(os, "supports_dir_fd", set()) or not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise HermeticError("descriptor-safe source traversal is unavailable")
    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        dir_flags |= os.O_CLOEXEC
        file_flags |= os.O_CLOEXEC
    try:
        current_fd = os.open(src_root, dir_flags)
    except OSError as exc:
        raise HermeticError("bundle src root must be a real directory") from exc
    try:
        if not stat.S_ISDIR(os.fstat(current_fd).st_mode):
            raise HermeticError("bundle src root must be a real directory")
        for part in rel.parts[:-1]:
            try:
                next_fd = os.open(part, dir_flags, dir_fd=current_fd)
            except OSError as exc:
                raise HermeticError(f"manifest parent is not a real directory: {rel.as_posix()}") from exc
            try:
                if not stat.S_ISDIR(os.fstat(next_fd).st_mode):
                    raise HermeticError(f"manifest parent is not a real directory: {rel.as_posix()}")
            except Exception:
                os.close(next_fd)
                raise
            os.close(current_fd)
            current_fd = next_fd
        try:
            fd = os.open(rel.parts[-1], file_flags, dir_fd=current_fd)
        except OSError as exc:
            raise HermeticError(f"cannot safely open manifest file: {rel.as_posix()}") from exc
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise HermeticError(f"manifest file is not regular: {rel.as_posix()}")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1 << 20)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(fd)
    finally:
        os.close(current_fd)


def _verified_sources(bundle_root: Path, manifest: Mapping[str, object]) -> dict[str, bytes]:
    src_root = bundle_root / "src"
    rows = manifest.get("files")
    if not isinstance(rows, list) or not rows:
        raise HermeticError("manifest files must be a non-empty list")
    out: dict[str, bytes] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise HermeticError("manifest file row must be an object")
        rel = _safe_relpath(row.get("path"))
        rel_text = rel.as_posix()
        if rel_text in out:
            raise HermeticError(f"duplicate manifest path: {rel_text}")
        expected_sha = row.get("sha256")
        expected_bytes = row.get("bytes")
        if not isinstance(expected_sha, str) or not _HEX64.fullmatch(expected_sha):
            raise HermeticError(f"invalid sha256 for {rel_text}")
        if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int) or expected_bytes < 0:
            raise HermeticError(f"invalid byte count for {rel_text}")
        data = _read_regular_no_symlink(src_root, rel)
        if len(data) != expected_bytes or sha256(data).hexdigest() != expected_sha:
            raise HermeticError(f"source byte mismatch: {rel_text}")
        out[rel_text] = data

    # The packager's src/ is a closed Python source tree. Extra files are not
    # merely ignored: an unmanifested .py/.so/.pth could change import behavior.
    actual: set[str] = set()
    for root, dirs, files in os.walk(src_root, followlinks=False):
        root_path = Path(root)
        for name in list(dirs):
            candidate = root_path / name
            try:
                st = candidate.lstat()
            except OSError as exc:
                raise HermeticError("cannot inventory bundle src directory") from exc
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
                raise HermeticError("bundle src contains non-directory/symlink component")
        for name in files:
            candidate = root_path / name
            try:
                st = candidate.lstat()
            except OSError as exc:
                raise HermeticError("cannot inventory bundle src file") from exc
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
                raise HermeticError("bundle src contains non-regular/symlink file")
            actual.add(candidate.relative_to(src_root).as_posix())
    if actual != set(out):
        missing = sorted(set(out) - actual)
        extra = sorted(actual - set(out))
        raise HermeticError(f"bundle src inventory mismatch missing={missing} extra={extra}")
    return out


def _stage_verified_sources(src_root: Path, sources: Mapping[str, bytes]) -> None:
    """Materialize only verified manifest bytes into a private execution tree."""
    src_root.mkdir(parents=True)
    for rel_text, data in sorted(sources.items()):
        rel = _safe_relpath(rel_text)
        path = src_root.joinpath(*rel.parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def _local_roots(paths: Sequence[str]) -> frozenset[str]:
    roots: set[str] = set()
    for item in paths:
        rel = PurePosixPath(item)
        first = rel.parts[0]
        if first.endswith(".py"):
            roots.add(PurePosixPath(first).stem)
        else:
            roots.add(first)
    return frozenset(roots)


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def dependency_closure(bundle_root: Path) -> dict[str, object]:
    """Verify source bytes and classify every static import.

    A clean closure has no undeclared third-party imports and no dynamic import
    sites. Relative imports are local by construction. The result is hash-bound
    to the source manifest used by the existing packager.
    """
    bundle_root = bundle_root.resolve()
    manifest = _load_manifest(bundle_root)
    sources = _verified_sources(bundle_root, manifest)
    local_roots = _local_roots(tuple(sources))
    stdlib = frozenset(getattr(sys, "stdlib_module_names", ())) | {"__future__"}
    local_imports: set[str] = set()
    stdlib_imports: set[str] = set()
    undeclared: set[str] = set()
    dynamic_sites: set[str] = set()
    runtime_escape_imports: set[str] = set()
    for rel, data in sources.items():
        try:
            tree = ast.parse(data.decode("utf-8"), filename=rel)
        except (UnicodeDecodeError, SyntaxError) as exc:
            raise HermeticError(f"cannot parse verified Python source: {rel}") from exc

        builtins_module_aliases: set[str] = set()
        builtin_import_aliases: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "builtins":
                        builtins_module_aliases.add(alias.asname or "builtins")
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "builtins":
                for alias in node.names:
                    if alias.name == "__import__":
                        builtin_import_aliases.add(alias.asname or "__import__")

        for node in ast.walk(tree):
            roots: list[str] = []
            if isinstance(node, ast.Import):
                roots.extend(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    local_imports.add(f"{rel}:relative")
                elif node.module:
                    roots.append(node.module.split(".", 1)[0])
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                # A closed bundle must not acquire dependencies at runtime.
                # Treat importlib capability itself as dynamic, including aliasing.
                imported_roots: list[str] = []
                if isinstance(node, ast.Import):
                    imported_roots.extend(alias.name.split(".", 1)[0] for alias in node.names)
                elif node.module:
                    imported_roots.append(node.module.split(".", 1)[0])
                if "importlib" in imported_roots:
                    dynamic_sites.add(f"{rel}:{getattr(node, 'lineno', 0)}:importlib-capability")
                if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "builtins":
                    if any(alias.name == "__import__" for alias in node.names):
                        dynamic_sites.add(f"{rel}:{getattr(node, 'lineno', 0)}:builtins.__import__-capability")
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id == "__builtins__" or node.id in builtin_import_aliases or node.id == "__import__":
                    dynamic_sites.add(f"{rel}:{getattr(node, 'lineno', 0)}:{node.id}-capability")
            elif isinstance(node, ast.Attribute) and node.attr == "__import__":
                if isinstance(node.value, ast.Name) and node.value.id in builtins_module_aliases | {"__builtins__"}:
                    dynamic_sites.add(f"{rel}:{getattr(node, 'lineno', 0)}:builtins.__import__-capability")
            elif isinstance(node, ast.Subscript):
                if isinstance(node.value, ast.Name) and node.value.id == "__builtins__":
                    key = node.slice
                    if isinstance(key, ast.Constant) and key.value == "__import__":
                        dynamic_sites.add(f"{rel}:{getattr(node, 'lineno', 0)}:__builtins__.__import__-capability")
            elif isinstance(node, ast.Call):
                name = _call_name(node.func)
                alias_calls = {f"{alias}.__import__" for alias in builtins_module_aliases}
                if name in {"__import__", "importlib.import_module"} | builtin_import_aliases | alias_calls:
                    dynamic_sites.add(f"{rel}:{getattr(node, 'lineno', 0)}:{name}")
                if name == "getattr" and len(node.args) >= 2:
                    target, attribute = node.args[0], node.args[1]
                    target_name = target.id if isinstance(target, ast.Name) else None
                    if target_name in builtins_module_aliases | {"__builtins__"} and isinstance(attribute, ast.Constant) and attribute.value == "__import__":
                        dynamic_sites.add(f"{rel}:{getattr(node, 'lineno', 0)}:reflective-builtins.__import__")
            for root in roots:
                if root in {"ctypes", "_ctypes"}:
                    runtime_escape_imports.add(f"{rel}:{getattr(node, 'lineno', 0)}:{root}")
                if root in local_roots:
                    local_imports.add(root)
                elif root in stdlib:
                    stdlib_imports.add(root)
                else:
                    undeclared.add(root)
    closure: dict[str, object] = {
        "schema": _SCHEMA_CLOSURE,
        "source_manifest_sha256": manifest["manifest_sha256"],
        "verified_files": len(sources),
        "local_roots": sorted(local_roots),
        "local_imports": sorted(local_imports),
        "stdlib_imports": sorted(stdlib_imports),
        "undeclared_imports": sorted(undeclared),
        "dynamic_import_sites": sorted(dynamic_sites),
        "runtime_escape_imports": sorted(runtime_escape_imports),
    }
    closure["closure_sha256"] = _canonical_sha(closure)
    return closure


def require_closed_dependencies(closure: Mapping[str, object]) -> None:
    if closure.get("schema") != _SCHEMA_CLOSURE:
        raise HermeticError("unexpected dependency closure schema")
    expected = closure.get("closure_sha256")
    if not isinstance(expected, str) or not _HEX64.fullmatch(expected):
        raise HermeticError("dependency closure missing valid hash")
    unsigned = dict(closure)
    unsigned.pop("closure_sha256", None)
    if _canonical_sha(unsigned) != expected:
        raise HermeticError("dependency closure hash mismatch")
    undeclared = closure.get("undeclared_imports")
    dynamic = closure.get("dynamic_import_sites")
    runtime_escape = closure.get("runtime_escape_imports")
    if not isinstance(undeclared, list) or not isinstance(dynamic, list) or not isinstance(runtime_escape, list):
        raise HermeticError("dependency closure lists malformed")
    if undeclared:
        raise HermeticError("undeclared third-party imports: " + ",".join(map(str, undeclared)))
    if dynamic:
        raise HermeticError("dynamic imports prevent dependency closure")
    if runtime_escape:
        raise HermeticError("runtime escape imports prevent hermetic execution")


def _bootstrap_text(src_root: Path, entrypoint: str) -> str:
    blocked = repr((
        "socket.__new__", "socket.bind", "socket.connect", "socket.getaddrinfo",
        "subprocess.Popen", "os.system", "os.exec", "os.spawn", "os.posix_spawn",
        "os.posix_spawnp", "os.fork", "os.forkpty", "ctypes.dlopen", "ctypes.dlsym",
    ))
    return f'''from pathlib import Path\nimport runpy, sys\nBLOCKED = set({blocked})\ndef _audit(event, args):\n    if event in BLOCKED:\n        raise RuntimeError("HERMETIC_AUDIT_DENY:" + event)\nsys.addaudithook(_audit)\nROOT = Path({str(src_root)!r})\nsys.path.insert(0, str(ROOT))\nrunpy.run_path(str(ROOT / {entrypoint!r}), run_name="__main__")\n'''


def _sanitized_env(home: Path, tmp: Path) -> dict[str, str]:
    # Deliberately do not inherit credentials, proxy settings, PYTHONPATH, HOME,
    # Kaggle tokens, cloud metadata controls, or arbitrary caller variables.
    return {
        "HOME": str(home),
        "TMPDIR": str(tmp),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _drain(stream: object, capture: _Capture) -> None:
    read = getattr(stream, "read")
    try:
        while True:
            chunk = read(1 << 16)
            if not chunk:
                return
            capture.feed(chunk)
    finally:
        try:
            getattr(stream, "close")()
        except Exception:
            pass


def _linux_children(pid: int) -> tuple[int, ...]:
    path = Path(f"/proc/{pid}/task/{pid}/children")
    try:
        text = path.read_text(encoding="ascii").strip()
    except OSError:
        return ()
    out: list[int] = []
    for field in text.split():
        try:
            out.append(int(field))
        except ValueError:
            continue
    return tuple(out)


def _linux_rss_kib(pid: int) -> int | None:
    try:
        lines = Path(f"/proc/{pid}/status").read_text(encoding="ascii").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("VmRSS:"):
            fields = line.split()
            if len(fields) >= 2:
                try:
                    return int(fields[1])
                except ValueError:
                    return None
    return None


def _process_tree_rss_mib(root_pid: int) -> tuple[float | None, str]:
    if not Path("/proc").is_dir():
        return None, "UNAVAILABLE_NON_LINUX"
    pending = [root_pid]
    seen: set[int] = set()
    total_kib = 0
    measured = 0
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        rss = _linux_rss_kib(pid)
        if rss is not None:
            total_kib += rss
            measured += 1
        pending.extend(_linux_children(pid))
    if not measured:
        return None, "UNAVAILABLE_PROCESS_EXITED"
    return total_kib / 1024.0, "LINUX_PROC_PROCESS_TREE"


def _terminate_process_group(proc: subprocess.Popen[bytes], grace: float) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        try:
            proc.terminate()
        except ProcessLookupError:
            return
    deadline = time.monotonic() + grace
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass


def _execution_identity(*, entrypoint: str, manifest_sha: str, closure_sha: str,
                        policy: Mapping[str, object], stdout_sha: str, stderr_sha: str,
                        stdout_bytes: int, stderr_bytes: int, returncode: int, timed_out: bool,
                        output_limit_exceeded: bool, source_unchanged: bool,
                        blockers: Sequence[str], state: str) -> str:
    stable = {
        "schema": "arc3-sage-hermetic-execution-identity/v1",
        "entrypoint": entrypoint,
        "source_manifest_sha256": manifest_sha,
        "dependency_closure_sha256": closure_sha,
        "policy": policy,
        "stdout_sha256": stdout_sha,
        "stderr_sha256": stderr_sha,
        "stdout_bytes": stdout_bytes,
        "stderr_bytes": stderr_bytes,
        "returncode": returncode,
        "timed_out": timed_out,
        "output_limit_exceeded": output_limit_exceeded,
        "source_unchanged_after_execution": source_unchanged,
        "blockers": list(blockers),
        "state": state,
    }
    return _canonical_sha(stable)


def run_hermetic(bundle_root: Path, *, entrypoint: str, policy: ExecutionPolicy) -> ExecutionReceipt:
    """Run one verified bundle entrypoint from a private copy of verified bytes."""
    bundle_root = bundle_root.resolve()
    manifest = _load_manifest(bundle_root)
    sources = _verified_sources(bundle_root, manifest)
    rel = _safe_relpath(entrypoint).as_posix()
    if rel not in sources:
        raise HermeticError("entrypoint is not present in the verified manifest")
    closure = dependency_closure(bundle_root)
    require_closed_dependencies(closure)
    policy_dict = asdict(policy)
    manifest_sha = str(manifest["manifest_sha256"])
    closure_sha = str(closure["closure_sha256"])

    with tempfile.TemporaryDirectory(prefix="arc3-hermetic-") as td:
        run_root = Path(td)
        home = run_root / "home"
        tmp = run_root / "tmp"
        exec_bundle = run_root / "exec-bundle"
        exec_src = exec_bundle / "src"
        home.mkdir()
        tmp.mkdir()
        exec_bundle.mkdir()
        _stage_verified_sources(exec_src, sources)
        if _verified_sources(exec_bundle, manifest) != sources:
            raise HermeticError("staged source bytes do not match verified source bytes")
        bootstrap = run_root / "bootstrap.py"
        bootstrap.write_text(_bootstrap_text(exec_src, rel), encoding="utf-8")
        out_cap = _Capture(policy.max_output_bytes, bytearray())
        err_cap = _Capture(policy.max_output_bytes, bytearray())
        started = time.monotonic()
        try:
            proc = subprocess.Popen(
                (sys.executable, "-I", "-S", str(bootstrap)),
                cwd=str(exec_bundle),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=_sanitized_env(home, tmp),
                start_new_session=True,
            )
        except OSError as exc:
            raise HermeticError(f"cannot start isolated interpreter: {exc.__class__.__name__}") from exc
        assert proc.stdout is not None and proc.stderr is not None
        threads = [
            threading.Thread(target=_drain, args=(proc.stdout, out_cap), daemon=True),
            threading.Thread(target=_drain, args=(proc.stderr, err_cap), daemon=True),
        ]
        for thread in threads:
            thread.start()
        timed_out = False
        peak_rss: float | None = None
        rss_authority = "UNAVAILABLE_NOT_SAMPLED"
        while proc.poll() is None:
            rss, authority = _process_tree_rss_mib(proc.pid)
            if rss is not None:
                peak_rss = rss if peak_rss is None else max(peak_rss, rss)
                rss_authority = authority
            elapsed = time.monotonic() - started
            if elapsed >= policy.timeout_seconds:
                timed_out = True
                _terminate_process_group(proc, policy.terminate_grace_seconds)
                break
            if out_cap.overflow or err_cap.overflow:
                _terminate_process_group(proc, policy.terminate_grace_seconds)
                break
            time.sleep(policy.poll_interval_seconds)
        try:
            returncode = proc.wait(timeout=policy.terminate_grace_seconds + 1.0)
        except subprocess.TimeoutExpired:
            _terminate_process_group(proc, policy.terminate_grace_seconds)
            returncode = proc.wait()
        for thread in threads:
            thread.join(timeout=1.0)
        wall = time.monotonic() - started
        output_limit_exceeded = out_cap.overflow or err_cap.overflow
        stdout_sha = sha256(bytes(out_cap.data)).hexdigest()
        stderr_sha = sha256(bytes(err_cap.data)).hexdigest()
        staged_unchanged = True
        try:
            staged_unchanged = _verified_sources(exec_bundle, manifest) == sources
        except HermeticError:
            staged_unchanged = False

    source_unchanged = staged_unchanged
    try:
        source_unchanged = source_unchanged and _verified_sources(bundle_root, manifest) == sources
    except HermeticError:
        source_unchanged = False

    blockers: list[str] = []
    if returncode != 0:
        blockers.append("NONZERO_EXIT")
    if timed_out:
        blockers.append("LOCAL_TIMEOUT")
    if output_limit_exceeded:
        blockers.append("OUTPUT_LIMIT_EXCEEDED")
    if not source_unchanged:
        blockers.append("SOURCE_MUTATED_DURING_EXECUTION")
    if wall > policy.competition_runtime_seconds * policy.runtime_margin_fraction:
        blockers.append("COMPETITION_RUNTIME_MARGIN_INSUFFICIENT")
    if policy.memory_limit_mib is not None:
        if peak_rss is None:
            blockers.append("MEMORY_MEASUREMENT_UNAVAILABLE")
        elif peak_rss > policy.memory_limit_mib * policy.runtime_margin_fraction:
            blockers.append("MEMORY_MARGIN_INSUFFICIENT")

    state = "HERMETIC_RUNTIME_CONFORMANT" if not blockers else "BLOCKED"
    identity = _execution_identity(
        entrypoint=rel,
        manifest_sha=manifest_sha,
        closure_sha=closure_sha,
        policy=policy_dict,
        stdout_sha=stdout_sha,
        stderr_sha=stderr_sha,
        stdout_bytes=out_cap.total,
        stderr_bytes=err_cap.total,
        returncode=returncode,
        timed_out=timed_out,
        output_limit_exceeded=output_limit_exceeded,
        source_unchanged=source_unchanged,
        blockers=blockers,
        state=state,
    )
    return ExecutionReceipt(
        schema=_SCHEMA_RECEIPT,
        entrypoint=rel,
        source_manifest_sha256=manifest_sha,
        dependency_closure_sha256=closure_sha,
        execution_identity_sha256=identity,
        returncode=returncode,
        timed_out=timed_out,
        output_limit_exceeded=output_limit_exceeded,
        wall_seconds=wall,
        peak_process_tree_rss_mib=peak_rss,
        rss_measurement=rss_authority,
        stdout_bytes=out_cap.total,
        stderr_bytes=err_cap.total,
        stdout_sha256=stdout_sha,
        stderr_sha256=stderr_sha,
        source_unchanged_after_execution=source_unchanged,
        policy=policy_dict,
        blockers=tuple(blockers),
        state=state,
        authority={
            "kaggle_submit": False,
            "leaderboard_claim": False,
            "prize_claim": False,
            "declared_memory_limit": policy.memory_limit_mib is not None,
        },
    )


def receipt_json(receipt: ExecutionReceipt) -> str:
    return json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":"), allow_nan=False)


def verify_receipt(receipt: Mapping[str, object]) -> None:
    """Verify stable execution identity and fail closed on malformed authority."""
    if receipt.get("schema") != _SCHEMA_RECEIPT:
        raise HermeticError("unexpected receipt schema")
    policy = receipt.get("policy")
    authority = receipt.get("authority")
    if not isinstance(policy, dict) or not isinstance(authority, dict):
        raise HermeticError("receipt policy/authority malformed")
    for forbidden in ("kaggle_submit", "leaderboard_claim", "prize_claim"):
        if authority.get(forbidden) is not False:
            raise HermeticError("receipt cannot grant external authority")
    required = {
        "entrypoint": receipt.get("entrypoint"),
        "manifest_sha": receipt.get("source_manifest_sha256"),
        "closure_sha": receipt.get("dependency_closure_sha256"),
        "stdout_sha": receipt.get("stdout_sha256"),
        "stderr_sha": receipt.get("stderr_sha256"),
    }
    if not isinstance(required["entrypoint"], str):
        raise HermeticError("receipt entrypoint malformed")
    for key in ("manifest_sha", "closure_sha", "stdout_sha", "stderr_sha"):
        value = required[key]
        if not isinstance(value, str) or not _HEX64.fullmatch(value):
            raise HermeticError(f"receipt {key} malformed")
    returncode = receipt.get("returncode")
    if isinstance(returncode, bool) or not isinstance(returncode, int):
        raise HermeticError("receipt returncode malformed")
    for key in ("timed_out", "output_limit_exceeded", "source_unchanged_after_execution"):
        if not isinstance(receipt.get(key), bool):
            raise HermeticError(f"receipt {key} malformed")
    stdout_bytes = receipt.get("stdout_bytes")
    stderr_bytes = receipt.get("stderr_bytes")
    blockers = receipt.get("blockers")
    state = receipt.get("state")
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in (stdout_bytes, stderr_bytes)):
        raise HermeticError("receipt output byte counts malformed")
    if not isinstance(blockers, (list, tuple)) or any(not isinstance(x, str) for x in blockers):
        raise HermeticError("receipt blockers malformed")
    if state not in {"HERMETIC_RUNTIME_CONFORMANT", "BLOCKED"}:
        raise HermeticError("receipt state malformed")
    if (not blockers) != (state == "HERMETIC_RUNTIME_CONFORMANT"):
        raise HermeticError("receipt state/blockers inconsistent")
    expected = _execution_identity(
        entrypoint=required["entrypoint"],
        manifest_sha=required["manifest_sha"],
        closure_sha=required["closure_sha"],
        policy=policy,
        stdout_sha=required["stdout_sha"],
        stderr_sha=required["stderr_sha"],
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        returncode=returncode,
        timed_out=bool(receipt["timed_out"]),
        output_limit_exceeded=bool(receipt["output_limit_exceeded"]),
        source_unchanged=bool(receipt["source_unchanged_after_execution"]),
        blockers=tuple(blockers),
        state=state,
    )
    if receipt.get("execution_identity_sha256") != expected:
        raise HermeticError("execution identity hash mismatch")
