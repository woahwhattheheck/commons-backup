# SPDX-License-Identifier: Apache-2.0
"""Current verifier authority for the OHSU qualification evidence pack.

The deterministic qualification compiler remains useful for reconstruction, but
only a fresh isolated child verifier may emit CURRENT authority. The child owns
wall-clock sampling and reads one fixed verifier-side trust root with descriptor
custody. Caller-injected root/time evaluation is permanently historical-only.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any, Callable

def _load_qualification_module():
    path = Path(__file__).with_name("qualification.py")
    spec = importlib.util.spec_from_file_location("_ohsu_qualification_facade", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load qualification compiler")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_qualification = _load_qualification_module()
QualificationError = _qualification.QualificationError
digest = _qualification.digest
evaluate_candidate = _qualification.evaluate

CURRENT_SCHEMA = "ohsu-digital-pathology-current-authority/v2"
HISTORICAL_SCHEMA = "ohsu-digital-pathology-historical-integrity/v2"
CURRENT_AUTHORITY_MODE = "FRESH_ISOLATED_VERIFIER_RETAINED_ROOT_V2"
HISTORICAL_AUTHORITY_MODE = "HISTORICAL_INTEGRITY_ONLY_V2"
PRODUCTION_ROOT_DISPLAY = "/etc/commons/ohsu_digital_pathology_ims/trusted_completeness.sha256"
_MAX_ROOT_BYTES = 65
_MAX_INPUT_BYTES = 2 * 1024 * 1024


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        c in "0123456789abcdef" for c in value
    )


def _candidate_attestation_sha256(payload: dict[str, Any]) -> str | None:
    manifest = payload.get("requirements_manifest")
    if not isinstance(manifest, dict):
        return None
    attestation = manifest.get("completeness_attestation")
    if not isinstance(attestation, dict):
        return None
    value = attestation.get("sha256")
    return value if _is_sha256(value) else None


def _fingerprint(st: os.stat_result) -> tuple[int, ...]:
    return (
        st.st_dev,
        st.st_ino,
        st.st_mode,
        st.st_nlink,
        st.st_uid,
        st.st_gid,
        st.st_size,
        st.st_mtime_ns,
        st.st_ctime_ns,
    )


def _root_result(
    *,
    value: str | None,
    custody: str,
    reason: str | None,
    source: str,
) -> dict[str, Any]:
    return {
        "value": value,
        "custody": custody,
        "reason": reason,
        "source": source,
    }


def _probe_retained_root(
    directory: str,
    filename: str,
    *,
    expected_uid: int,
    after_read_hook: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Read one retained root with fail-closed POSIX descriptor custody.

    This generic probe is intentionally incapable of emitting a qualification
    decision. Production current authority invokes it only inside a fresh
    isolated child with a fixed /etc path and expected uid 0. Tests may invoke
    it on temporary paths to exercise the filesystem predecessor classes.
    """
    source = f"{directory.rstrip('/')}/{filename}"
    required_posix_flags = ("O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK", "O_DIRECTORY")
    if (
        os.name != "posix"
        or not os.path.isabs(directory)
        or any(not hasattr(os, name) for name in required_posix_flags)
    ):
        return _root_result(
            value=None,
            custody="UNAVAILABLE",
            reason="TRUSTED_COMPLETENESS_ROOT_POSIX_CUSTODY_UNAVAILABLE",
            source=source,
        )

    required_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW

    opened: list[int] = []
    leaf_fd: int | None = None
    try:
        root_fd = os.open("/", dir_flags)
        opened.append(root_fd)
        cursor_fd = root_fd

        parts = [part for part in Path(directory).parts if part not in ("/", "")]
        for part in parts:
            next_fd = os.open(part, dir_flags, dir_fd=cursor_fd)
            opened.append(next_fd)
            st = os.fstat(next_fd)
            if not stat.S_ISDIR(st.st_mode):
                raise OSError("trusted-root ancestor is not a directory")
            if st.st_uid not in {0, expected_uid}:
                raise OSError("trusted-root ancestor owner is not trusted")
            if stat.S_IMODE(st.st_mode) & 0o022:
                raise OSError("trusted-root ancestor is group/other writable")
            cursor_fd = next_fd

        parent_fd = cursor_fd
        parent_before = os.fstat(parent_fd)
        leaf_fd = os.open(filename, required_flags, dir_fd=parent_fd)
        leaf_before = os.fstat(leaf_fd)

        if not stat.S_ISREG(leaf_before.st_mode):
            raise OSError("trusted root must be a regular file")
        if leaf_before.st_uid != expected_uid:
            raise OSError("trusted root owner mismatch")
        if leaf_before.st_nlink != 1:
            raise OSError("trusted root must have one link")
        if stat.S_IMODE(leaf_before.st_mode) not in {0o400, 0o600}:
            raise OSError("trusted root mode must be owner-read-only or owner-private")
        if leaf_before.st_size < 64 or leaf_before.st_size > _MAX_ROOT_BYTES:
            raise OSError("trusted root size invalid")

        raw = bytearray()
        while len(raw) <= _MAX_ROOT_BYTES:
            chunk = os.read(leaf_fd, _MAX_ROOT_BYTES + 1 - len(raw))
            if not chunk:
                break
            raw.extend(chunk)
        if len(raw) > _MAX_ROOT_BYTES:
            raise OSError("trusted root too large")

        if after_read_hook is not None:
            after_read_hook()

        leaf_after = os.fstat(leaf_fd)
        parent_after = os.fstat(parent_fd)
        if _fingerprint(leaf_before) != _fingerprint(leaf_after):
            raise OSError("trusted root changed during read")
        if _fingerprint(parent_before) != _fingerprint(parent_after):
            raise OSError("trusted root parent changed during read")

        visible_leaf = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        if _fingerprint(leaf_after) != _fingerprint(visible_leaf):
            raise OSError("trusted root visible generation changed")

        visible_parent = os.stat(directory, follow_symlinks=False)
        if (visible_parent.st_dev, visible_parent.st_ino) != (
            parent_after.st_dev,
            parent_after.st_ino,
        ):
            raise OSError("trusted root parent path generation changed")

        data = bytes(raw)
        if data.endswith(b"\n"):
            data = data[:-1]
        if len(data) != 64:
            raise OSError("trusted root encoding invalid")
        try:
            value = data.decode("ascii")
        except UnicodeDecodeError as exc:
            raise OSError("trusted root encoding invalid") from exc
        if not _is_sha256(value):
            raise OSError("trusted root digest invalid")

        return _root_result(
            value=value,
            custody="VERIFIED",
            reason=None,
            source=source,
        )
    except (OSError, ValueError):
        return _root_result(
            value=None,
            custody="UNAVAILABLE",
            reason="TRUSTED_COMPLETENESS_ROOT_MISSING_OR_INVALID",
            source=source,
        )
    finally:
        if leaf_fd is not None:
            try:
                os.close(leaf_fd)
            except OSError:
                pass
        for fd in reversed(opened):
            try:
                os.close(fd)
            except OSError:
                pass


def probe_trusted_root_for_testing(
    path: str | os.PathLike[str],
    *,
    expected_uid: int,
    after_read_hook: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Test-only custody probe. It cannot emit CURRENT authority."""
    target = Path(path)
    return _probe_retained_root(
        str(target.parent),
        target.name,
        expected_uid=expected_uid,
        after_read_hook=after_read_hook,
    )


def evaluate_historical_with_root(
    payload: dict[str, Any],
    *,
    evaluated_at: str,
    trusted_completeness_sha256: str | None,
) -> dict[str, Any]:
    """Deterministic reconstruction seam that can never assert CURRENT authority."""
    core = evaluate_candidate(payload, evaluated_at=evaluated_at)
    receipt = dict(core)
    receipt.pop("receipt_digest", None)

    holds = set(receipt.get("holds") or [])
    candidate_root = _candidate_attestation_sha256(payload)
    trusted_valid = _is_sha256(trusted_completeness_sha256)

    if not trusted_valid:
        holds.add("TRUSTED_COMPLETENESS_ROOT_MISSING_OR_INVALID")
    elif candidate_root != trusted_completeness_sha256:
        holds.add("TRUSTED_COMPLETENESS_ROOT_MISMATCH")

    policy_decision = "READY_FOR_INTERNAL_BID_REVIEW" if not holds else "HOLD"
    holds.add("HISTORICAL_INTEGRITY_ONLY")

    receipt["schema"] = HISTORICAL_SCHEMA
    receipt["historical_candidate_decision"] = policy_decision
    receipt["decision"] = "HOLD"
    receipt["holds"] = sorted(holds)
    receipt["candidate_completeness_attestation_sha256"] = candidate_root
    receipt["trusted_completeness_root_sha256"] = (
        trusted_completeness_sha256 if trusted_valid else None
    )
    receipt["current_authority_mode"] = HISTORICAL_AUTHORITY_MODE
    receipt["current_authority"] = False
    receipt["receipt_digest"] = digest(receipt)
    return receipt


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _build_current_bytes_evaluator() -> Callable[[bytes], dict[str, Any]]:
    run = subprocess.run
    executable = sys.executable
    script = str(Path(__file__).resolve())
    interpreter_options = ["-I", "-S"]
    if sys.flags.optimize:
        interpreter_options.append("-O")
    stdout_pipe = subprocess.PIPE
    stderr_pipe = subprocess.PIPE
    subprocess_error = subprocess.SubprocessError
    qualification_error = QualificationError
    loads = json.loads
    current_schema = CURRENT_SCHEMA
    input_limit = _MAX_INPUT_BYTES

    def evaluate_current_bytes(raw: bytes) -> dict[str, Any]:
        """Evaluate exact JSON bytes in a fresh isolated verifier process."""
        if not isinstance(raw, (bytes, bytearray)):
            raise qualification_error("current evaluation requires bytes")
        if len(raw) > input_limit:
            raise qualification_error(
                "qualification bundle exceeds current verifier byte limit"
            )
        try:
            proc = run(
                [executable, *interpreter_options, script, "--isolated-current-child"],
                input=bytes(raw),
                stdout=stdout_pipe,
                stderr=stderr_pipe,
                check=False,
                timeout=15,
                env={"PYTHONHASHSEED": "0"},
            )
        except (OSError, subprocess_error) as exc:
            raise qualification_error(
                "isolated current verifier failed to start"
            ) from exc
        if proc.returncode != 0:
            detail = proc.stderr.decode("utf-8", "replace").strip()
            raise qualification_error(
                detail or "isolated current verifier rejected input"
            )
        try:
            receipt = loads(proc.stdout.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise qualification_error(
                "isolated current verifier returned invalid JSON"
            ) from exc
        if not isinstance(receipt, dict) or receipt.get("schema") != current_schema:
            raise qualification_error(
                "isolated current verifier returned wrong receipt schema"
            )
        return receipt

    return evaluate_current_bytes


evaluate_current_bytes = _build_current_bytes_evaluator()
del _build_current_bytes_evaluator


def _build_current_object_evaluator() -> Callable[[dict[str, Any]], dict[str, Any]]:
    evaluate_bytes = evaluate_current_bytes
    dumps = json.dumps
    qualification_error = QualificationError

    def evaluate_current(payload: dict[str, Any]) -> dict[str, Any]:
        """Evaluate a Python object through the same fresh-process CURRENT boundary."""
        if not isinstance(payload, dict):
            raise qualification_error("payload must be an object")
        try:
            raw = dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise qualification_error("payload is not strict JSON") from exc
        return evaluate_bytes(raw)

    return evaluate_current


evaluate_current = _build_current_object_evaluator()
del _build_current_object_evaluator


def _child_main(argv: list[str]) -> int:
    """Fresh isolated CURRENT verifier entrypoint; never valid as an imported call."""
    if __name__ != "__main__" or not sys.flags.isolated or not sys.flags.no_site:
        raise RuntimeError("CURRENT authority requires a fresh isolated interpreter")
    if argv != ["--isolated-current-child"]:
        raise RuntimeError("invalid isolated verifier invocation")

    raw = sys.stdin.buffer.read(_MAX_INPUT_BYTES + 1)
    if len(raw) > _MAX_INPUT_BYTES:
        raise ValueError("qualification bundle exceeds current verifier byte limit")
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"strict qualification JSON rejected: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")

    qualification_path = Path(__file__).with_name("qualification.py")
    spec = importlib.util.spec_from_file_location("_ohsu_current_qualification", qualification_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load qualification compiler")
    qualification = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qualification)

    # These bindings are local to this fresh -I -S process. They are not
    # parameters, environment selectors, or import-time mutable globals.
    from datetime import datetime, timezone

    evaluated_at = (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    root_probe = _probe_retained_root(
        "/etc/commons/ohsu_digital_pathology_ims",
        "trusted_completeness.sha256",
        expected_uid=0,
    )

    core = qualification.evaluate(payload, evaluated_at=evaluated_at)
    receipt = dict(core)
    receipt.pop("receipt_digest", None)
    holds = set(receipt.get("holds") or [])

    candidate_root = _candidate_attestation_sha256(payload)
    trusted_root = root_probe["value"]
    if trusted_root is None:
        holds.add(root_probe["reason"] or "TRUSTED_COMPLETENESS_ROOT_MISSING_OR_INVALID")
    elif candidate_root != trusted_root:
        holds.add("TRUSTED_COMPLETENESS_ROOT_MISMATCH")

    if holds:
        receipt["decision"] = "HOLD"
    receipt["holds"] = sorted(holds)
    receipt["schema"] = CURRENT_SCHEMA
    receipt["candidate_completeness_attestation_sha256"] = candidate_root
    receipt["trusted_completeness_root_sha256"] = trusted_root
    receipt["trusted_completeness_root_source"] = PRODUCTION_ROOT_DISPLAY
    receipt["trusted_completeness_root_custody"] = root_probe["custody"]
    receipt["current_authority_mode"] = CURRENT_AUTHORITY_MODE
    receipt["current_authority"] = (
        receipt["decision"] == "READY_FOR_INTERNAL_BID_REVIEW"
        and trusted_root is not None
        and candidate_root == trusted_root
    )
    receipt["receipt_digest"] = qualification.digest(receipt)
    sys.stdout.write(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_child_main(sys.argv[1:]))
    except Exception as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        raise SystemExit(2)
