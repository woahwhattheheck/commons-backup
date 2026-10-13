"""Bounded read-only public-network transport with DNS-pinned connections."""
from __future__ import annotations

import http.client
import ipaddress
import math
import socket
import ssl
from typing import Any
from urllib.parse import urljoin, urlsplit

from constants import AUTO_RESOLVE_SOURCE_HOSTS, MAX_HTTP_BYTES, USER_AGENT
from errors import EvidenceError, PreflightInputError
from models import Response

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_MAX_REDIRECTS = 10


def _host_in_suffix(host: str, suffix: str) -> bool:
    normalized = host.rstrip(".").lower()
    return normalized == suffix or normalized.endswith(f".{suffix}")


def _trusted_source_suffix(host: str) -> str | None:
    for suffix in AUTO_RESOLVE_SOURCE_HOSTS:
        if _host_in_suffix(host, suffix):
            return suffix
    return None


def _public_destination(url: str) -> tuple[object, str, int, tuple[str, ...]]:
    """Resolve one URL once and return only public IPs for the actual socket connect."""
    try:
        parsed = urlsplit(url)
        port_number = parsed.port
    except ValueError as exc:
        raise EvidenceError("unsafe_destination", f"invalid destination port: {url}") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise EvidenceError("unsafe_destination", f"unsupported destination URL: {url}")
    if parsed.username or parsed.password:
        raise EvidenceError("unsafe_destination", "destination URL must not contain credentials")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise EvidenceError("unsafe_destination", f"non-public hostname rejected: {host}")
    port = port_number or (443 if parsed.scheme.lower() == "https" else 80)
    try:
        rows = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise EvidenceError("network_unavailable", f"DNS resolution failed for {host}: {exc}") from exc
    if not rows:
        raise EvidenceError("network_unavailable", f"DNS resolution returned no addresses for {host}")
    addresses: list[str] = []
    for row in rows:
        address = ipaddress.ip_address(row[4][0])
        if not address.is_global:
            raise EvidenceError("unsafe_destination", f"non-public address rejected for {host}: {address}")
        rendered = str(address)
        if rendered not in addresses:
            addresses.append(rendered)
    return parsed, host, port, tuple(addresses)


def validate_public_destination(url: str) -> None:
    """Reject credentials and non-public network destinations."""
    _public_destination(url)


def validate_redirect_destination(source_url: str, target_url: str) -> None:
    """Require redirects to remain inside the source's trusted hostname scope."""
    _parsed, target_host, _port, _addresses = _public_destination(target_url)
    source_host = (urlsplit(source_url).hostname or "").rstrip(".").lower()
    sponsor_suffix = _trusted_source_suffix(source_host)
    if sponsor_suffix:
        if not _host_in_suffix(target_host, sponsor_suffix):
            raise EvidenceError(
                "unsafe_redirect",
                f"redirect left trusted source domain {sponsor_suffix}: {target_host}",
            )
        return
    if target_host != source_host:
        raise EvidenceError(
            "unsafe_redirect",
            f"cross-host redirect rejected: {source_host} -> {target_host}",
        )


def read_bounded(handle: Any) -> bytes:
    body = handle.read(MAX_HTTP_BYTES + 1)
    if len(body) > MAX_HTTP_BYTES:
        raise EvidenceError("response_too_large", f"response exceeded {MAX_HTTP_BYTES} bytes")
    return body


def _host_header(host: str, port: int, scheme: str) -> str:
    rendered = f"[{host}]" if ":" in host else host
    default = 443 if scheme == "https" else 80
    return rendered if port == default else f"{rendered}:{port}"


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to an already-resolved IP while verifying TLS for the original host."""

    def __init__(self, address: str, *, server_hostname: str, port: int, timeout: float):
        super().__init__(
            address,
            port=port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self._server_hostname = server_hostname

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self.host, self.port),
            self.timeout,
            self.source_address,
        )
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self._server_hostname)


def _request_to_address(
    *,
    parsed: object,
    host: str,
    port: int,
    address: str,
    timeout: float,
    headers: dict[str, str],
) -> Response:
    scheme = parsed.scheme.lower()
    connection: http.client.HTTPConnection
    if scheme == "https":
        connection = _PinnedHTTPSConnection(
            address, server_hostname=host, port=port, timeout=timeout
        )
    else:
        connection = http.client.HTTPConnection(address, port=port, timeout=timeout)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    request_headers = dict(headers)
    request_headers["Host"] = _host_header(host, port, scheme)
    try:
        connection.request("GET", path, headers=request_headers)
        reply = connection.getresponse()
        body = read_bounded(reply)
        response_headers = {str(k).lower(): str(v) for k, v in reply.getheaders()}
        return Response(
            url=parsed.geturl(),
            status=int(reply.status),
            headers=response_headers,
            body=body,
        )
    finally:
        connection.close()


class UrlLibTransport:
    """Public-network HTTP reader with DNS-pinned sockets and optional GitHub auth."""

    def __init__(self, *, timeout: float = 15.0, github_token: str | None = None):
        if not math.isfinite(timeout) or timeout <= 0:
            raise PreflightInputError("timeout must be a positive finite number")
        self.timeout = timeout
        self.github_token = github_token

    def _headers(self, url: str, accept: str) -> dict[str, str]:
        headers = {"Accept": accept, "User-Agent": USER_AGENT}
        if self.github_token and urlsplit(url).hostname == "api.github.com":
            headers["Authorization"] = f"Bearer {self.github_token}"
            headers["X-GitHub-Api-Version"] = "2022-11-28"
        return headers

    def _fetch_once(self, url: str, *, accept: str) -> Response:
        parsed, host, port, addresses = _public_destination(url)
        headers = self._headers(url, accept)
        failures: list[str] = []
        for address in addresses:
            try:
                return _request_to_address(
                    parsed=parsed,
                    host=host,
                    port=port,
                    address=address,
                    timeout=self.timeout,
                    headers=headers,
                )
            except EvidenceError:
                raise
            except (OSError, TimeoutError, ValueError, http.client.HTTPException, ssl.SSLError) as exc:
                failures.append(f"{address}: {exc}")
        detail = "; ".join(failures)[:400]
        raise EvidenceError("network_unavailable", f"read failed for {url}: {detail}")

    def fetch(self, url: str, *, accept: str) -> Response:
        current = url
        for redirects in range(_MAX_REDIRECTS + 1):
            response = self._fetch_once(current, accept=accept)
            if response.status not in _REDIRECT_STATUSES:
                return response
            location = response.headers.get("location")
            if not location:
                return response
            if redirects == _MAX_REDIRECTS:
                raise EvidenceError("too_many_redirects", f"more than {_MAX_REDIRECTS} redirects")
            target = urljoin(current, location)
            validate_redirect_destination(url, target)
            current = target
        raise EvidenceError("too_many_redirects", f"more than {_MAX_REDIRECTS} redirects")
