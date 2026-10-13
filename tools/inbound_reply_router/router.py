#!/usr/bin/env python3
"""Hardened public boundary for the inbound reply custody router.

The reviewed semantic engine is preserved byte-for-byte in ``router_base.py``.
This module adds independent owner-binding freshness and filesystem-custody
fences, then re-exports the original public API. It never authorizes an external
side effect.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any

try:
    from . import router_base as _base
except ImportError:  # direct script execution
    import router_base as _base

CONTEXT_SCHEMA = _base.CONTEXT_SCHEMA
EVIDENCE_SCHEMA = _base.EVIDENCE_SCHEMA
RECEIPT_SCHEMA = _base.RECEIPT_SCHEMA
ACTIONS = _base.ACTIONS
HUMAN_CLASSIFICATIONS = _base.HUMAN_CLASSIFICATIONS
PROVIDER_CLASSIFICATIONS = _base.PROVIDER_CLASSIFICATIONS
CLASSIFICATIONS = _base.CLASSIFICATIONS
DEFAULT_MAX_EVIDENCE_AGE_SECONDS = _base.DEFAULT_MAX_EVIDENCE_AGE_SECONDS
DEFAULT_MAX_FUTURE_SKEW_SECONDS = _base.DEFAULT_MAX_FUTURE_SKEW_SECONDS
DEFAULT_MAX_OWNER_BINDING_AGE_SECONDS = 900
RouterError = _base.RouterError
DuplicateKeyError = _base.DuplicateKeyError


@dataclass(frozen=True)
class Policy:
    max_evidence_age_seconds: int = DEFAULT_MAX_EVIDENCE_AGE_SECONDS
    max_future_skew_seconds: int = DEFAULT_MAX_FUTURE_SKEW_SECONDS
    max_owner_binding_age_seconds: int = DEFAULT_MAX_OWNER_BINDING_AGE_SECONDS


def _validated_owner_age(policy: Policy) -> None:
    value = policy.max_owner_binding_age_seconds
    if type(value) is not int or value < 0 or value > 86_400:
        raise RouterError("policy.max_owner_binding_age_seconds is invalid")


def _evaluated_time(value: str | datetime) -> datetime:
    if isinstance(value, str):
        return _base._parse_time(value, "evaluated_at")
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise RouterError("evaluated_at must include a timezone")
        return value.astimezone(timezone.utc)
    raise RouterError("evaluated_at must be a timestamp string or datetime")


def _owner_freshness_reasons(
    evidence: _base.Evidence, *, now: datetime, policy: Policy
) -> list[str]:
    reasons: list[str] = []
    maximum_age = timedelta(seconds=policy.max_owner_binding_age_seconds)
    future_skew = timedelta(seconds=policy.max_future_skew_seconds)
    for binding in evidence.owner_bindings:
        if now - binding.observed_at > maximum_age:
            reasons.append("owner_binding_stale")
        if binding.observed_at - now > future_skew:
            reasons.append("owner_binding_from_future")
    return sorted(set(reasons))


def _rehash_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    result = dict(receipt)
    result.pop("receipt_sha256", None)
    result["receipt_sha256"] = _base._sha256_json(result)
    return result


def route_reply(
    context_raw: Any,
    evidence_raw: Any,
    *,
    evaluated_at: str | datetime,
    policy: Policy | None = None,
) -> dict[str, Any]:
    """Route one reply while independently fencing stale ownership custody."""

    selected = policy or Policy()
    _validated_owner_age(selected)
    now = _evaluated_time(evaluated_at)
    parsed_evidence = _base._parse_evidence(evidence_raw)
    receipt = _base.route_reply(
        context_raw,
        evidence_raw,
        evaluated_at=now,
        policy=_base.Policy(
            max_evidence_age_seconds=selected.max_evidence_age_seconds,
            max_future_skew_seconds=selected.max_future_skew_seconds,
        ),
    )
    owner_reasons = _owner_freshness_reasons(
        parsed_evidence, now=now, policy=selected
    )
    if not owner_reasons:
        return receipt

    result = dict(receipt)
    prior_basis = result.get("basis", []) if result.get("action") == "HOLD" else []
    result["action"] = "HOLD"
    result["basis"] = sorted(set([*prior_basis, *owner_reasons]))
    result["candidate_new_route"] = None
    return _rehash_receipt(result)


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _require_plain_ancestors(path: Path, *, label: str) -> None:
    """Reject symlink/non-directory existing ancestors without resolving them."""

    parent = _lexical_absolute(path).parent
    current = Path(parent.anchor)
    for component in parent.parts[1:]:
        current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise RouterError(f"{label} parent cannot be safely inspected: {current}") from exc
        if stat.S_ISLNK(info.st_mode):
            raise RouterError(f"{label} parent must not traverse a symlink: {current}")
        if not stat.S_ISDIR(info.st_mode):
            raise RouterError(f"{label} parent component must be a directory: {current}")


def _require_plain_input(path: Path, *, label: str) -> None:
    _require_plain_ancestors(path, label=label)
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise RouterError(f"{label} does not exist: {path}") from exc
    except OSError as exc:
        raise RouterError(f"{label} cannot be safely inspected: {path}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise RouterError(f"{label} must not be a symlink")
    if not stat.S_ISREG(info.st_mode):
        raise RouterError(f"{label} must be a regular file")


def _require_plain_output(path: Path, *, label: str = "output") -> None:
    _require_plain_ancestors(path, label=label)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise RouterError(f"{label} cannot be safely inspected: {path}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise RouterError(f"{label} must not be a symlink")
    if not stat.S_ISREG(info.st_mode):
        raise RouterError(f"{label} must be a regular file")


def _paths_alias(left: Path, right: Path) -> bool:
    if _lexical_absolute(left) == _lexical_absolute(right):
        return True
    try:
        if left.exists() and right.exists() and os.path.samefile(left, right):
            return True
    except OSError:
        pass
    return False


def preflight_cli_artifacts(
    context_path: str | os.PathLike[str],
    evidence_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str] | None,
) -> None:
    """Validate source custody and aliases before either JSON input is consumed."""

    context = Path(context_path)
    evidence = Path(evidence_path)
    _require_plain_input(context, label="context")
    _require_plain_input(evidence, label="evidence")
    if _paths_alias(context, evidence):
        raise RouterError("context and evidence must not reference the same filesystem object")
    if output_path is None:
        return
    output = Path(output_path)
    _require_plain_output(output)
    if _paths_alias(output, context):
        raise RouterError("output and context must not reference the same filesystem object")
    if _paths_alias(output, evidence):
        raise RouterError("output and evidence must not reference the same filesystem object")


def load_json(path: str | os.PathLike[str]) -> Any:
    """Read strict JSON from one ordinary, non-symlink source object."""

    source = Path(path)
    _require_plain_input(source, label="JSON input")
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(source, flags)
    except OSError as exc:
        raise RouterError(f"JSON input cannot be safely opened: {source}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise RouterError("JSON input must be a regular file")
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            fd = -1
            return json.load(handle, object_pairs_hook=_base._strict_object)
    finally:
        if fd >= 0:
            os.close(fd)


def write_receipt_atomic(
    receipt: dict[str, Any], path: str | os.PathLike[str]
) -> None:
    target = Path(path)
    _require_plain_output(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    _require_plain_output(target)
    payload = (
        json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    temporary = Path(temp_name)
    owned_fd: int | None = fd
    try:
        _require_plain_output(target)
        with os.fdopen(fd, "wb") as handle:
            owned_fd = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _require_plain_output(target)
        os.replace(temporary, target)
        temporary = Path("")
        try:
            directory_fd = os.open(target.parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except BaseException:
        if owned_fd is not None:
            try:
                os.close(owned_fd)
            except OSError:
                pass
        if temporary != Path(""):
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        raise


def _build_parser():
    parser = _base._build_parser()
    parser.add_argument(
        "--max-owner-binding-age-seconds",
        type=int,
        default=DEFAULT_MAX_OWNER_BINDING_AGE_SECONDS,
        help="maximum age of every ownership row at evaluation time",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        preflight_cli_artifacts(args.context, args.evidence, args.output)
        context = load_json(args.context)
        evidence = load_json(args.evidence)
        receipt = route_reply(
            context,
            evidence,
            evaluated_at=args.evaluated_at,
            policy=Policy(
                max_evidence_age_seconds=args.max_evidence_age_seconds,
                max_future_skew_seconds=args.max_future_skew_seconds,
                max_owner_binding_age_seconds=args.max_owner_binding_age_seconds,
            ),
        )
        if args.output:
            write_receipt_atomic(receipt, args.output)
        else:
            json.dump(receipt, sys.stdout, sort_keys=True, indent=2, ensure_ascii=False)
            sys.stdout.write("\n")
        return 0
    except (OSError, RouterError, json.JSONDecodeError) as exc:
        print(f"inbound-reply-router: {exc}", file=sys.stderr)
        return 2


def __getattr__(name: str):
    return getattr(_base, name)


if __name__ == "__main__":
    raise SystemExit(main())
