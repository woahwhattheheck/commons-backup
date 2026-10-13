"""Canonical buyer/opportunity keys and typed alias normalization."""
from __future__ import annotations

import ipaddress
import re
import socket
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from .strict import ALIAS_TYPES, IdentityAliasError, exact_keys

_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_OFFICIAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+\- ]{0,159}$")
_NONPUBLIC_SUFFIXES = (
    ".localhost", ".local", ".internal", ".invalid", ".test", ".home.arpa", ".onion"
)

def machine_key(value: Any, field: str) -> str:
    if type(value) is not str:
        raise IdentityAliasError(f"{field}: string required")
    token = value.strip().casefold()
    if _KEY_RE.fullmatch(token) is None:
        raise IdentityAliasError(f"{field}: lowercase opaque key required")
    return token

def _official_id(value: Any) -> str:
    if type(value) is not str:
        raise IdentityAliasError("official_id alias: string required")
    raw = " ".join(value.strip().split())
    if _OFFICIAL_ID_RE.fullmatch(raw) is None:
        raise IdentityAliasError("official_id alias: bounded ASCII identifier required")
    return raw.casefold()

def _domain(hostname: str) -> str:
    if not hostname:
        raise IdentityAliasError("authority_url alias: hostname required")
    candidate = hostname.rstrip(".").casefold()
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        try:
            socket.inet_aton(candidate)
        except OSError:
            pass
        else:
            raise IdentityAliasError("authority_url alias: legacy IP literal forbidden")
    else:
        raise IdentityAliasError("authority_url alias: IP literal forbidden")
    try:
        host = candidate.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise IdentityAliasError("authority_url alias: invalid hostname") from exc
    labels = host.split(".")
    if len(labels) < 2:
        raise IdentityAliasError("authority_url alias: dotted public hostname required")
    if all(label.isdigit() for label in labels):
        raise IdentityAliasError("authority_url alias: numeric IP-style hostname forbidden")
    if any(host == suffix[1:] or host.endswith(suffix) for suffix in _NONPUBLIC_SUFFIXES):
        raise IdentityAliasError("authority_url alias: special-use/non-public hostname forbidden")
    for label in labels:
        if (
            not label or len(label) > 63 or label[0] == "-" or label[-1] == "-"
            or re.fullmatch(r"[a-z0-9-]+", label) is None
        ):
            raise IdentityAliasError("authority_url alias: invalid hostname label")
    return host

def _authority_url(value: Any) -> str:
    if type(value) is not str or not value.strip():
        raise IdentityAliasError("authority_url alias: URL string required")
    raw = value.strip()
    if len(raw) > 2048 or any(ord(ch) < 32 for ch in raw) or "\\" in raw:
        raise IdentityAliasError("authority_url alias: invalid URL")
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError as exc:
        raise IdentityAliasError("authority_url alias: invalid URL") from exc
    if parts.scheme.casefold() != "https":
        raise IdentityAliasError("authority_url alias: https required")
    if parts.username is not None or parts.password is not None:
        raise IdentityAliasError("authority_url alias: userinfo forbidden")
    if parts.query or parts.fragment:
        raise IdentityAliasError("authority_url alias: query/fragment forbidden")
    if port not in (None, 443):
        raise IdentityAliasError("authority_url alias: non-default port forbidden")
    host = _domain(parts.hostname or "")
    path = parts.path or "/"
    if any(ord(ch) > 127 for ch in path) or "%" in path:
        raise IdentityAliasError("authority_url alias: encoded/non-ASCII path forbidden")
    if not path.startswith("/") or "//" in path:
        raise IdentityAliasError("authority_url alias: canonical absolute path required")
    if any(segment in (".", "..") for segment in path.split("/")):
        raise IdentityAliasError("authority_url alias: dot path segment forbidden")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit(("https", host, path, "", ""))

def normalize_alias(raw: Any) -> dict[str, str]:
    item = exact_keys(raw, {"type", "value"}, "alias")
    if type(item["type"]) is not str or item["type"] not in ALIAS_TYPES:
        raise IdentityAliasError("alias.type: official_id or authority_url required")
    kind = item["type"]
    value = _official_id(item["value"]) if kind == "official_id" else _authority_url(item["value"])
    return {"type": kind, "value": value}

def alias_key(alias: Mapping[str, str]) -> tuple[str, str]:
    return alias["type"], alias["value"]

def normalize_aliases(raw: Any, *, require_nonempty: bool) -> list[dict[str, str]]:
    if type(raw) is not list:
        raise IdentityAliasError("aliases: array required")
    if require_nonempty and not raw:
        raise IdentityAliasError("aliases: at least one alias required")
    if len(raw) > 128:
        raise IdentityAliasError("aliases: too many aliases")
    normalized = [normalize_alias(item) for item in raw]
    keys = [alias_key(item) for item in normalized]
    if len(set(keys)) != len(keys):
        raise IdentityAliasError("aliases: duplicate normalized alias")
    return sorted(normalized, key=alias_key)
