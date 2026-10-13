#!/usr/bin/env python3
"""Generation-bound registry and provisioning primitives for Creator Desk multisite."""
from __future__ import annotations

import contextlib
import json
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from toolkit import Store

REGISTRY_VERSION = 1
REGISTRY_MAX_BYTES = 1024 * 1024
MAX_PROXY_BODY = 12 * 1024 * 1024
COMMUNITY_RE = re.compile(r"[a-z][a-z0-9-]{0,62}\Z")
LABEL_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
ALLOWED_REQUEST_HEADERS = frozenset({"authorization", "content-type", "content-length"})
ALLOWED_RESPONSE_HEADERS = frozenset({
    "content-type", "content-length", "cache-control", "x-content-type-options",
    "referrer-policy", "content-disposition", "x-content-sha256",
})
HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade",
})
DB_NAME = "workspace.sqlite3"
PROC_FD_ROOT = Path("/proc/self/fd")


class RegistryError(ValueError):
    """Fail-closed registry, host, workspace, generation, or routing error."""


def _reject_constant(value: str):
    raise RegistryError(f"non-finite JSON value is not allowed: {value}")


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RegistryError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _fingerprint(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _identity(st):
    return (st.st_dev, st.st_ino)


def _read_regular_json(path: str | Path, *, max_bytes: int = REGISTRY_MAX_BYTES):
    """Read one exact regular-file generation without following a final symlink."""
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(os.fspath(path), flags)
    except OSError as exc:
        raise RegistryError(f"registry is unavailable or unsafe: {exc.strerror or exc}") from None
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise RegistryError("registry must be a regular file")
        if before.st_size < 2 or before.st_size > max_bytes:
            raise RegistryError(f"registry must be between 2 and {max_bytes} bytes")
        chunks = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                raise RegistryError("registry changed or truncated while being read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise RegistryError("registry grew while being read")
        after = os.fstat(fd)
        if _fingerprint(before) != _fingerprint(after):
            raise RegistryError("registry generation changed while being read")
        raw = b"".join(chunks)
    finally:
        os.close(fd)
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError:
        raise RegistryError("registry must be strict UTF-8") from None
    try:
        return json.loads(text, object_pairs_hook=_strict_object, parse_constant=_reject_constant)
    except RegistryError:
        raise
    except (ValueError, RecursionError):
        raise RegistryError("registry must be strict JSON") from None


def canonical_community_id(value) -> str:
    if not isinstance(value, str) or not COMMUNITY_RE.fullmatch(value):
        raise RegistryError("community_id must match [a-z][a-z0-9-]{0,62}")
    if value.endswith("-") or "--" in value:
        raise RegistryError("community_id cannot end in '-' or contain '--'")
    return value


def canonical_host(value) -> str:
    """Canonicalize a DNS Host authority with optional decimal TCP port."""
    if not isinstance(value, str) or not value or len(value) > 253 + 6:
        raise RegistryError("host must be bounded text")
    if value != value.strip() or any(ord(c) < 33 or ord(c) == 127 for c in value):
        raise RegistryError("host cannot contain whitespace or control characters")
    if any(c in value for c in "/\\?#@") or value.startswith("[") or "]" in value:
        raise RegistryError("host must be a DNS name with optional port, not a URL/userinfo/IPv6 literal")
    if value.count(":") > 1:
        raise RegistryError("IPv6/ambiguous host authorities are unsupported")
    hostname, sep, port_text = value.partition(":")
    hostname = hostname.lower()
    if hostname.endswith(".") or not hostname or len(hostname) > 253:
        raise RegistryError("host must be an absolute canonical DNS name without a trailing dot")
    labels = hostname.split(".")
    if len(labels) < 2 or any(not LABEL_RE.fullmatch(label) for label in labels):
        raise RegistryError("host must contain valid DNS labels and at least one dot")
    try:
        hostname.encode("ascii")
    except UnicodeError:
        raise RegistryError("host must use ASCII DNS labels; use an explicit punycode name if required") from None
    if not sep:
        return hostname
    if not port_text.isdecimal() or (len(port_text) > 1 and port_text.startswith("0")):
        raise RegistryError("host port must be canonical decimal text")
    port = int(port_text)
    if not 1 <= port <= 65535:
        raise RegistryError("host port must be between 1 and 65535")
    return f"{hostname}:{port}"


def _require_generation_primitives():
    required = ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC")
    if os.name != "posix" or any(not hasattr(os, name) for name in required):
        raise RegistryError("generation-bound multisite storage requires POSIX O_DIRECTORY/O_NOFOLLOW/O_CLOEXEC")
    if not PROC_FD_ROOT.is_dir():
        raise RegistryError("generation-bound multisite storage requires /proc/self/fd")


def _directory_flags():
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _file_flags(*, create: bool):
    flags = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC
    if create:
        flags |= os.O_CREAT
    return flags


def _absolute_parts(path: str | Path):
    value = Path(path)
    if not value.is_absolute():
        raise RegistryError("workspace root must be an absolute path")
    parts = value.parts
    if len(parts) <= 1 or any(part in {"", ".", ".."} for part in parts[1:]):
        raise RegistryError("workspace root must be a non-root absolute path without dot components")
    return Path(os.path.normpath(os.fspath(value))), parts[1:]


def _open_root(path: str | Path, *, create_final: bool):
    """Open every absolute path component no-follow and retain the final generation."""
    _require_generation_primitives()
    normalized, parts = _absolute_parts(path)
    current = os.open("/", _directory_flags())
    try:
        for index, component in enumerate(parts):
            last = index == len(parts) - 1
            try:
                next_fd = os.open(component, _directory_flags(), dir_fd=current)
            except FileNotFoundError:
                if not (create_final and last):
                    raise RegistryError(f"workspace root component is not provisioned: {component}") from None
                try:
                    os.mkdir(component, 0o700, dir_fd=current)
                except FileExistsError:
                    pass
                try:
                    next_fd = os.open(component, _directory_flags(), dir_fd=current)
                except OSError as exc:
                    raise RegistryError(f"workspace root component is unsafe: {component}: {exc.strerror or exc}") from None
            except OSError as exc:
                raise RegistryError(f"workspace root component is unsafe: {component}: {exc.strerror or exc}") from None
            os.close(current)
            current = next_fd
        root_st = os.fstat(current)
        if not stat.S_ISDIR(root_st.st_mode):
            raise RegistryError("workspace root generation is not a directory")
        return normalized, current, _identity(root_st)
    except Exception:
        with contextlib.suppress(OSError):
            os.close(current)
        raise


def _open_workspace(root_fd: int, community_id: str, *, create: bool):
    try:
        fd = os.open(community_id, _directory_flags(), dir_fd=root_fd)
    except FileNotFoundError:
        if not create:
            raise RegistryError(f"community workspace is not provisioned: {community_id}") from None
        try:
            os.mkdir(community_id, 0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        try:
            fd = os.open(community_id, _directory_flags(), dir_fd=root_fd)
        except OSError as exc:
            raise RegistryError(f"community workspace is unsafe: {community_id}: {exc.strerror or exc}") from None
    except OSError as exc:
        raise RegistryError(f"community workspace is unsafe: {community_id}: {exc.strerror or exc}") from None
    st = os.fstat(fd)
    if not stat.S_ISDIR(st.st_mode):
        os.close(fd)
        raise RegistryError(f"community workspace generation is not a directory: {community_id}")
    return fd, _identity(st)


def _open_database(workspace_fd: int, community_id: str, *, create: bool):
    try:
        fd = os.open(DB_NAME, _file_flags(create=create), 0o600, dir_fd=workspace_fd)
    except FileNotFoundError:
        raise RegistryError(f"community workspace database is not provisioned: {community_id}") from None
    except OSError as exc:
        raise RegistryError(f"workspace database is unsafe: {community_id}: {exc.strerror or exc}") from None
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        os.close(fd)
        raise RegistryError(f"workspace database must be one regular-file generation: {community_id}")
    anchored = PROC_FD_ROOT / str(fd)
    try:
        proc_st = os.stat(anchored)
    except OSError:
        os.close(fd)
        raise RegistryError("cannot bind workspace database to retained file generation") from None
    if _identity(proc_st) != _identity(st):
        os.close(fd)
        raise RegistryError("retained workspace database generation did not bind through /proc/self/fd")
    return fd, anchored, _identity(st)


@dataclass(frozen=True)
class CommunitySpec:
    community_id: str
    host: str
    database: Path
    workspace_fd: int = field(repr=False, compare=False)
    database_fd: int = field(repr=False, compare=False)
    workspace_identity: tuple[int, int] = field(repr=False)
    database_identity: tuple[int, int] = field(repr=False)


class Registry:
    """Immutable host mapping that owns retained root/workspace/database generations."""

    def __init__(self, specs: Iterable[CommunitySpec], root: Path, root_fd: int, root_identity: tuple[int, int]):
        ordered = tuple(sorted(specs, key=lambda item: item.community_id))
        if not ordered:
            raise RegistryError("registry must contain at least one community")
        self.specs = ordered
        self.root = root
        self.root_fd = root_fd
        self.root_identity = root_identity
        self.by_id = {spec.community_id: spec for spec in ordered}
        self.by_host = {spec.host: spec for spec in ordered}
        self._closed = False
        if len(self.by_id) != len(ordered) or len(self.by_host) != len(ordered):
            raise RegistryError("registry contains duplicate community IDs or canonical hosts")
        if len({spec.workspace_identity for spec in ordered}) != len(ordered):
            raise RegistryError("two communities resolve to the same workspace generation")
        if len({spec.database_identity for spec in ordered}) != len(ordered):
            raise RegistryError("two communities resolve to the same database generation")

    def _assert_open(self):
        if self._closed:
            raise RegistryError("registry generation custody is closed")

    def assert_spec(self, spec: CommunitySpec):
        """Prove retained generations still occupy their registered logical names."""
        self._assert_open()
        try:
            root_st = os.fstat(self.root_fd)
            workspace_fd_st = os.fstat(spec.workspace_fd)
            workspace_name_st = os.stat(spec.community_id, dir_fd=self.root_fd, follow_symlinks=False)
            database_fd_st = os.fstat(spec.database_fd)
            database_name_st = os.stat(DB_NAME, dir_fd=spec.workspace_fd, follow_symlinks=False)
            database_proc_st = os.stat(spec.database)
        except OSError as exc:
            raise RegistryError(f"community storage generation changed: {spec.community_id}: {exc.strerror or exc}") from None
        if _identity(root_st) != self.root_identity or not stat.S_ISDIR(root_st.st_mode):
            raise RegistryError("workspace root generation changed")
        if (
            _identity(workspace_fd_st) != spec.workspace_identity
            or _identity(workspace_name_st) != spec.workspace_identity
            or not stat.S_ISDIR(workspace_fd_st.st_mode)
            or not stat.S_ISDIR(workspace_name_st.st_mode)
        ):
            raise RegistryError(f"community workspace generation changed: {spec.community_id}")
        if (
            _identity(database_fd_st) != spec.database_identity
            or _identity(database_name_st) != spec.database_identity
            or _identity(database_proc_st) != spec.database_identity
            or not stat.S_ISREG(database_fd_st.st_mode)
            or not stat.S_ISREG(database_name_st.st_mode)
            or database_fd_st.st_nlink != 1
            or database_name_st.st_nlink != 1
        ):
            raise RegistryError(f"community database generation changed: {spec.community_id}")
        return spec

    def assert_all(self):
        for spec in self.specs:
            self.assert_spec(spec)
        return self

    def resolve(self, raw_host) -> CommunitySpec:
        host = canonical_host(raw_host)
        try:
            spec = self.by_host[host]
        except KeyError:
            raise RegistryError("host is not registered") from None
        return self.assert_spec(spec)

    def close(self):
        if self._closed:
            return
        self._closed = True
        for spec in reversed(self.specs):
            with contextlib.suppress(OSError):
                os.close(spec.database_fd)
            with contextlib.suppress(OSError):
                os.close(spec.workspace_fd)
        with contextlib.suppress(OSError):
            os.close(self.root_fd)

    def __enter__(self):
        self._assert_open()
        return self

    def __exit__(self, *_exc):
        self.close()


def _validated_entries(payload):
    if not isinstance(payload, dict) or set(payload) != {"version", "communities"}:
        raise RegistryError("registry keys must be exactly version and communities")
    if type(payload["version"]) is not int or payload["version"] != REGISTRY_VERSION:
        raise RegistryError(f"registry version must be {REGISTRY_VERSION}")
    entries = payload["communities"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= 1000:
        raise RegistryError("communities must be a list containing 1..1000 entries")
    result = []
    ids, hosts = set(), set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"community_id", "host"}:
            raise RegistryError("each community must contain exactly community_id and host")
        community_id = canonical_community_id(entry["community_id"])
        host = canonical_host(entry["host"])
        if community_id in ids:
            raise RegistryError(f"duplicate community_id: {community_id}")
        if host in hosts:
            raise RegistryError(f"duplicate canonical host: {host}")
        ids.add(community_id)
        hosts.add(host)
        result.append((community_id, host))
    return result


def load_registry(registry_path: str | Path, workspace_root: str | Path, *, create_workspaces: bool = False) -> Registry:
    entries = _validated_entries(_read_regular_json(registry_path))
    root, root_fd, root_identity = _open_root(workspace_root, create_final=create_workspaces)
    specs: list[CommunitySpec] = []
    try:
        for community_id, host in entries:
            workspace_fd, workspace_identity = _open_workspace(root_fd, community_id, create=create_workspaces)
            try:
                database_fd, database, database_identity = _open_database(
                    workspace_fd, community_id, create=create_workspaces
                )
            except Exception:
                os.close(workspace_fd)
                raise
            specs.append(CommunitySpec(
                community_id=community_id,
                host=host,
                database=database,
                workspace_fd=workspace_fd,
                database_fd=database_fd,
                workspace_identity=workspace_identity,
                database_identity=database_identity,
            ))
        registry = Registry(specs, root, root_fd, root_identity)
        return registry.assert_all()
    except Exception:
        for spec in reversed(specs):
            with contextlib.suppress(OSError):
                os.close(spec.database_fd)
            with contextlib.suppress(OSError):
                os.close(spec.workspace_fd)
        with contextlib.suppress(OSError):
            os.close(root_fd)
        raise


def provision(registry_path: str | Path, workspace_root: str | Path):
    """Provision missing workspaces; retain an empty second result for compatibility."""
    registry = load_registry(registry_path, workspace_root, create_workspaces=True)
    created = {}
    try:
        for spec in registry.specs:
            registry.assert_spec(spec)
            Store(spec.database)
            registry.assert_spec(spec)
        return registry, created
    except Exception:
        registry.close()
        raise
