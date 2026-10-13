# SPDX-License-Identifier: Apache-2.0
"""Pure RouteFoundry validation, URL tagging, and event contracts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import ipaddress
import re
import secrets
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, unquote

SLUG_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,48}[a-z0-9]")
EVENT_ID_RE = re.compile(r"[A-Za-z0-9_-]{8,96}")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
HOST_LABEL_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
EVENT_TYPES = frozenset({"click", "conversion"})
ROUTE_MODES = frozenset({"redirect", "offer"})
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")


class ValidationError(ValueError):
    """User-supplied value failed a stable product contract."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def require_text(value: Any, field: str, *, maximum: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text")
    if value != value.strip():
        raise ValidationError(f"{field} cannot start or end with whitespace")
    if CONTROL_RE.search(value):
        raise ValidationError(f"{field} cannot contain control characters")
    if not allow_empty and not value:
        raise ValidationError(f"{field} is required")
    if len(value) > maximum:
        raise ValidationError(f"{field} is longer than {maximum} characters")
    return value


def validate_slug(value: Any) -> str:
    slug = require_text(value, "slug", maximum=50).lower()
    if not SLUG_RE.fullmatch(slug):
        raise ValidationError("slug must be 3-50 lowercase letters, digits, underscores, or hyphens")
    return slug


def _normalized_hostname(parts: Any) -> str:
    try:
        host = parts.hostname
        _ = parts.port
    except ValueError as exc:
        raise ValidationError("destination has an invalid port") from exc
    if not host:
        raise ValidationError("destination requires a hostname")
    if parts.username is not None or parts.password is not None:
        raise ValidationError("destination cannot include user information")
    try:
        ascii_host = host.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as exc:
        raise ValidationError("destination hostname is invalid") from exc
    if not ascii_host or len(ascii_host) > 253:
        raise ValidationError("destination hostname is invalid")
    return ascii_host


def validate_destination(value: Any) -> str:
    """Return a normalized public HTTPS redirect destination.

    The router never fetches a destination. Rejecting local/private hosts still
    prevents links from being used as deceptive internal-network shortcuts and
    gives operators one predictable public-link contract.
    """
    url = require_text(value, "destination", maximum=2048)
    decoded = unquote(url)
    if "\\" in decoded or CONTROL_RE.search(decoded):
        raise ValidationError("destination contains unsafe characters")
    parts = urlsplit(url)
    if parts.scheme.lower() != "https":
        raise ValidationError("destination must use https")
    host = _normalized_hostname(parts)
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValidationError("destination must use a public hostname")
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        if "." not in host or any(not HOST_LABEL_RE.fullmatch(label) for label in host.split(".")):
            raise ValidationError("destination hostname is invalid")
    else:
        if not ip.is_global:
            raise ValidationError("destination IP must be globally routable")
    netloc = f"[{host}]" if ":" in host else host
    if parts.port is not None:
        netloc += f":{parts.port}"
    path = parts.path or "/"
    return urlunsplit(("https", netloc, path, parts.query, parts.fragment))


def validate_public_base_url(value: Any) -> str:
    """Validate the URL encoded into stable QR codes.

    HTTPS is required except loopback HTTP, which keeps the complete customer
    workflow runnable on a laptop without a local certificate.
    """
    url = require_text(value, "public_base_url", maximum=512).rstrip("/")
    parts = urlsplit(url)
    host = _normalized_hostname(parts)
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
        loopback = ip.is_loopback
    except ValueError:
        loopback = host == "localhost"
    if parts.scheme.lower() == "http" and not loopback:
        raise ValidationError("public_base_url must use https outside loopback development")
    if parts.scheme.lower() not in {"http", "https"}:
        raise ValidationError("public_base_url must use http or https")
    if parts.query or parts.fragment or parts.username is not None or parts.password is not None:
        raise ValidationError("public_base_url cannot include query, fragment, or user information")
    path = parts.path.rstrip("/")
    netloc = (f"[{host}]" if ":" in host else host) + (f":{parts.port}" if parts.port is not None else "")
    return urlunsplit((parts.scheme.lower(), netloc, path, "", ""))


def append_utm(destination: str, preset: Mapping[str, Any] | None) -> str:
    """Apply a link's UTM preset while preserving non-UTM query parameters."""
    target = validate_destination(destination)
    if not preset:
        return target
    parts = urlsplit(target)
    pairs = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if key not in UTM_KEYS]
    for key in UTM_KEYS:
        value = preset.get(key)
        if value:
            pairs.append((key, str(value)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), parts.fragment))


def short_url(public_base_url: str, slug: str) -> str:
    return f"{validate_public_base_url(public_base_url)}/r/{validate_slug(slug)}"


def event_id(value: Any | None = None) -> str:
    if value is None:
        return secrets.token_urlsafe(18)
    candidate = require_text(value, "event_id", maximum=96)
    if not EVENT_ID_RE.fullmatch(candidate):
        raise ValidationError("event_id must be 8-96 URL-safe characters")
    return candidate


def referrer_host(value: Any | None) -> str | None:
    if value in (None, ""):
        return None
    url = require_text(value, "referrer", maximum=2048)
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return None
    if not host:
        return None
    try:
        return host.encode("idna").decode("ascii").lower()[:253]
    except UnicodeError:
        return None


@dataclass(frozen=True)
class EventResult:
    event_id: str
    created: bool
