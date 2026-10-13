#!/usr/bin/env python3
"""Deterministic outbound lead leases for multi-agent revenue work.

The production protocol is transport agnostic but designed around GitHub Contents
API compare-and-swap semantics:

* Initial ownership: create ``coordination/outbound/leases/<key>.json``. Creation
  MUST fail if the path already exists; only the successful creator owns the lead.
* Takeover/release/send: fetch the current document and update it using the exact
  current blob SHA. A competing update against the same prior SHA loses.
* ``sent`` is terminal. A sent lease is never recycled.

This module deliberately stores only a SHA-256 fingerprint of the destination,
not an email address or other raw lead destination.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import os
import pathlib
import tempfile
import time
from typing import Any, Mapping

VERSION = 1
ACTIVE = "active"
RELEASED = "released"
SENT = "sent"
TERMINAL_STATES = {SENT}
VALID_STATES = {ACTIVE, RELEASED, SENT}
DEFAULT_TTL_SECONDS = 30 * 60
LEASE_PREFIX = "coordination/outbound/leases"


class LeaseError(RuntimeError):
    """Raised when an outbound lease invariant would be violated."""


class LeaseHeld(LeaseError):
    """Raised when another holder owns a live lease."""


class PreflightFailed(LeaseError):
    """Raised when a send preflight is unsafe."""


def _norm(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def _utc(value: dt.datetime | None = None) -> dt.datetime:
    value = value or dt.datetime.now(dt.timezone.utc)
    if value.tzinfo is None:
        raise LeaseError("timestamps must be timezone-aware")
    return value.astimezone(dt.timezone.utc).replace(microsecond=0)


def _iso(value: dt.datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> dt.datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return _utc(dt.datetime.fromisoformat(value))


def fingerprint(value: str) -> str:
    """Return a non-reversible identifier suitable for a public coordination repo."""
    if not value or not value.strip():
        raise LeaseError("cannot fingerprint a blank value")
    return hashlib.sha256(_norm(value).encode("utf-8")).hexdigest()


def lead_key(*, opportunity: str, channel: str, destination: str) -> str:
    """Map the same outbound target to one deterministic lock key."""
    parts = (_norm(opportunity), _norm(channel), _norm(destination))
    if any(not part for part in parts):
        raise LeaseError("opportunity, channel, and destination are required")
    material = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def lease_path(key: str) -> str:
    if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        raise LeaseError("key must be a lowercase SHA-256 hex digest")
    return f"{LEASE_PREFIX}/{key}.json"


@dataclasses.dataclass(frozen=True)
class Lease:
    version: int
    key: str
    opportunity: str
    channel: str
    destination_sha256: str
    holder: str
    state: str
    acquired_at: str
    expires_at: str
    provider_snapshot: str
    generation: int = 1
    released_at: str | None = None
    release_reason: str | None = None
    sent_at: str | None = None
    send_receipt_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.version != VERSION:
            raise LeaseError(f"unsupported lease version: {self.version}")
        if self.state not in VALID_STATES:
            raise LeaseError(f"invalid state: {self.state}")
        if not self.holder.strip():
            raise LeaseError("holder is required")
        lease_path(self.key)
        if self.generation < 1:
            raise LeaseError("generation must be >= 1")
        if self.state == SENT and not (self.sent_at and self.send_receipt_sha256):
            raise LeaseError("sent leases require sent_at and send_receipt_sha256")
        if self.state == RELEASED and not (self.released_at and self.release_reason):
            raise LeaseError("released leases require released_at and release_reason")

    @property
    def expires(self) -> dt.datetime:
        return _parse_iso(self.expires_at)

    def expired(self, now: dt.datetime | None = None) -> bool:
        return self.state == ACTIVE and _utc(now) >= self.expires

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Lease":
        return cls(**dict(value))

    @classmethod
    def from_json(cls, value: str) -> "Lease":
        return cls.from_mapping(json.loads(value))


def acquire(
    *,
    opportunity: str,
    channel: str,
    destination: str,
    holder: str,
    provider_snapshot: str,
    now: dt.datetime | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> Lease:
    if ttl_seconds <= 0:
        raise LeaseError("ttl_seconds must be positive")
    now = _utc(now)
    key = lead_key(opportunity=opportunity, channel=channel, destination=destination)
    return Lease(
        version=VERSION,
        key=key,
        opportunity=opportunity.strip(),
        channel=_norm(channel),
        destination_sha256=fingerprint(destination),
        holder=holder.strip(),
        state=ACTIVE,
        acquired_at=_iso(now),
        expires_at=_iso(now + dt.timedelta(seconds=ttl_seconds)),
        provider_snapshot=fingerprint(provider_snapshot),
    )


def takeover(
    lease: Lease,
    *,
    holder: str,
    provider_snapshot: str,
    now: dt.datetime | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> Lease:
    """Take over an expired/released lease only if provider truth is unchanged.

    ``provider_snapshot`` must come from a fresh provider read.  A changed provider
    generation is ambiguous: the prior holder may have sent successfully and then
    crashed before persisting ``state=sent``.  Treat that as reconciliation work,
    never as permission to establish a new baseline and send again.
    """
    now = _utc(now)
    if lease.state in TERMINAL_STATES:
        raise LeaseHeld("sent leases are terminal and cannot be taken over")
    if lease.state == ACTIVE and not lease.expired(now):
        raise LeaseHeld(f"live lease held by {lease.holder}")
    if ttl_seconds <= 0:
        raise LeaseError("ttl_seconds must be positive")
    current_provider_snapshot = fingerprint(provider_snapshot)
    if current_provider_snapshot != lease.provider_snapshot:
        raise PreflightFailed(
            "provider state changed since lease capture; reconcile before takeover"
        )
    return dataclasses.replace(
        lease,
        holder=holder.strip(),
        state=ACTIVE,
        acquired_at=_iso(now),
        expires_at=_iso(now + dt.timedelta(seconds=ttl_seconds)),
        provider_snapshot=lease.provider_snapshot,
        generation=lease.generation + 1,
        released_at=None,
        release_reason=None,
        sent_at=None,
        send_receipt_sha256=None,
    )


def assert_preflight(
    lease: Lease,
    *,
    holder: str,
    provider_snapshot: str,
    now: dt.datetime | None = None,
) -> None:
    """Fail closed unless ownership and the just-reread provider state match."""
    now = _utc(now)
    if lease.state != ACTIVE:
        raise PreflightFailed(f"lease is {lease.state}, not active")
    if lease.holder != holder.strip():
        raise PreflightFailed(f"lease belongs to {lease.holder}, not {holder.strip()}")
    if lease.expired(now):
        raise PreflightFailed("lease expired before send")
    current = fingerprint(provider_snapshot)
    if current != lease.provider_snapshot:
        raise PreflightFailed("provider state changed since claim; re-evaluate before sending")


def mark_sent(
    lease: Lease,
    *,
    holder: str,
    provider_snapshot: str,
    send_receipt: str,
    now: dt.datetime | None = None,
) -> Lease:
    now = _utc(now)
    assert_preflight(lease, holder=holder, provider_snapshot=provider_snapshot, now=now)
    if not send_receipt.strip():
        raise LeaseError("send_receipt is required")
    return dataclasses.replace(
        lease,
        state=SENT,
        expires_at=_iso(now),
        sent_at=_iso(now),
        send_receipt_sha256=fingerprint(send_receipt),
        generation=lease.generation + 1,
    )


def release(
    lease: Lease,
    *,
    holder: str,
    reason: str,
    now: dt.datetime | None = None,
) -> Lease:
    now = _utc(now)
    if lease.state == SENT:
        raise LeaseHeld("sent leases are terminal and cannot be released")
    if lease.state != ACTIVE:
        raise LeaseHeld(f"cannot release lease in state {lease.state}")
    if lease.holder != holder.strip():
        raise LeaseHeld(f"lease belongs to {lease.holder}, not {holder.strip()}")
    if not reason.strip():
        raise LeaseError("release reason is required")
    return dataclasses.replace(
        lease,
        state=RELEASED,
        expires_at=_iso(now),
        released_at=_iso(now),
        release_reason=reason.strip(),
        generation=lease.generation + 1,
    )


class LocalCASStore:
    """Reference CAS store used by tests and local/offline agents.

    GitHub is the production cross-session store. This class mirrors the same
    create-if-absent + revision-CAS contract using only the filesystem.
    """

    def __init__(self, root: os.PathLike[str] | str):
        self.root = pathlib.Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _state_path(self, key: str) -> pathlib.Path:
        lease_path(key)
        return self.root / f"{key}.json"

    def _guard_path(self, key: str) -> pathlib.Path:
        return self.root / f".{key}.guard"

    def _guard(self, key: str, timeout: float = 5.0):
        return _DirectoryGuard(self._guard_path(key), timeout=timeout)

    def create(self, lease: Lease) -> str:
        """Create exactly once. Returns a revision hash or raises LeaseHeld."""
        path = self._state_path(lease.key)
        with self._guard(lease.key):
            if path.exists():
                raise LeaseHeld(f"lease already exists: {lease.key}")
            _atomic_write(path, lease.to_json())
            return _revision(lease.to_json())

    def read(self, key: str) -> tuple[Lease, str]:
        text = self._state_path(key).read_text(encoding="utf-8")
        return Lease.from_json(text), _revision(text)

    def compare_and_swap(self, lease: Lease, *, expected_revision: str) -> str:
        path = self._state_path(lease.key)
        with self._guard(lease.key):
            if not path.exists():
                raise LeaseError("lease does not exist")
            current = path.read_text(encoding="utf-8")
            if _revision(current) != expected_revision:
                raise LeaseHeld("compare-and-swap lost: lease changed")
            text = lease.to_json()
            _atomic_write(path, text)
            return _revision(text)


class _DirectoryGuard:
    def __init__(self, path: pathlib.Path, timeout: float):
        self.path = path
        self.timeout = timeout

    def __enter__(self):
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self.path.mkdir()
                return self
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise LeaseError(f"timed out acquiring local guard {self.path.name}")
                time.sleep(0.005)

    def __exit__(self, exc_type, exc, tb):
        try:
            self.path.rmdir()
        except FileNotFoundError:
            pass


def _revision(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic_write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    except BaseException:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
        raise


def _read_lease_file(path: str) -> Lease:
    if path == "-":
        import sys
        return Lease.from_json(sys.stdin.read())
    return Lease.from_json(pathlib.Path(path).read_text(encoding="utf-8"))


def _emit_lease(value: Lease) -> int:
    print(value.to_json(), end="")
    return 0


def _cmd_key(args: argparse.Namespace) -> int:
    key = lead_key(opportunity=args.opportunity, channel=args.channel, destination=args.destination)
    print(json.dumps({"key": key, "path": lease_path(key)}, sort_keys=True))
    return 0


def _cmd_claim(args: argparse.Namespace) -> int:
    return _emit_lease(acquire(
        opportunity=args.opportunity,
        channel=args.channel,
        destination=args.destination,
        holder=args.holder,
        provider_snapshot=args.provider_snapshot,
        ttl_seconds=args.ttl,
    ))


def _cmd_validate(args: argparse.Namespace) -> int:
    value = _read_lease_file(args.lease)
    print(json.dumps({
        "ok": True,
        "key": value.key,
        "path": lease_path(value.key),
        "state": value.state,
        "holder": value.holder,
        "generation": value.generation,
    }, sort_keys=True))
    return 0


def _cmd_preflight(args: argparse.Namespace) -> int:
    value = _read_lease_file(args.lease)
    assert_preflight(value, holder=args.holder, provider_snapshot=args.provider_snapshot)
    print(json.dumps({"ok": True, "key": value.key, "generation": value.generation}, sort_keys=True))
    return 0


def _cmd_takeover(args: argparse.Namespace) -> int:
    value = _read_lease_file(args.lease)
    return _emit_lease(takeover(
        value,
        holder=args.holder,
        provider_snapshot=args.provider_snapshot,
        ttl_seconds=args.ttl,
    ))


def _cmd_release(args: argparse.Namespace) -> int:
    value = _read_lease_file(args.lease)
    return _emit_lease(release(value, holder=args.holder, reason=args.reason))


def _cmd_sent(args: argparse.Namespace) -> int:
    value = _read_lease_file(args.lease)
    return _emit_lease(mark_sent(
        value,
        holder=args.holder,
        provider_snapshot=args.provider_snapshot,
        send_receipt=args.send_receipt,
    ))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    key = sub.add_parser("key", help="print deterministic lease key/path")
    key.add_argument("--opportunity", required=True)
    key.add_argument("--channel", required=True)
    key.add_argument("--destination", required=True)
    key.set_defaults(func=_cmd_key)

    claim = sub.add_parser("claim", help="emit a canonical initial claim document")
    claim.add_argument("--opportunity", required=True)
    claim.add_argument("--channel", required=True)
    claim.add_argument("--destination", required=True)
    claim.add_argument("--holder", required=True)
    claim.add_argument("--provider-snapshot", required=True)
    claim.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS)
    claim.set_defaults(func=_cmd_claim)

    validate = sub.add_parser("validate", help="validate and summarize a lease JSON document")
    validate.add_argument("--lease", required=True, help="lease JSON file, or - for stdin")
    validate.set_defaults(func=_cmd_validate)

    preflight = sub.add_parser("preflight", help="fail closed unless a send is still safe")
    preflight.add_argument("--lease", required=True, help="lease JSON file, or - for stdin")
    preflight.add_argument("--holder", required=True)
    preflight.add_argument("--provider-snapshot", required=True)
    preflight.set_defaults(func=_cmd_preflight)

    take = sub.add_parser("takeover", help="emit a takeover document only if provider state is unchanged")
    take.add_argument("--lease", required=True, help="lease JSON file, or - for stdin")
    take.add_argument("--holder", required=True)
    take.add_argument("--provider-snapshot", required=True)
    take.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS)
    take.set_defaults(func=_cmd_takeover)

    release_cmd = sub.add_parser("release", help="emit a released lease document")
    release_cmd.add_argument("--lease", required=True, help="lease JSON file, or - for stdin")
    release_cmd.add_argument("--holder", required=True)
    release_cmd.add_argument("--reason", required=True)
    release_cmd.set_defaults(func=_cmd_release)

    sent = sub.add_parser("sent", help="emit the terminal sent receipt document")
    sent.add_argument("--lease", required=True, help="lease JSON file, or - for stdin")
    sent.add_argument("--holder", required=True)
    sent.add_argument("--provider-snapshot", required=True)
    sent.add_argument("--send-receipt", required=True)
    sent.set_defaults(func=_cmd_sent)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.func(args)
    except (LeaseError, ValueError, json.JSONDecodeError, OSError) as exc:
        import sys
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
