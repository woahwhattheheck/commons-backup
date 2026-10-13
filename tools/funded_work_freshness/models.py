"""Validated inputs and immutable transport models."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any, Mapping, Protocol
from urllib.parse import urlsplit, urlunsplit

from constants import GITHUB_ITEM_RE
from errors import EvidenceError, PreflightInputError


@dataclass(frozen=True)
class Response:
    """Small immutable HTTP response used by real and fixture transports."""

    url: str
    status: int
    headers: Mapping[str, str]
    body: bytes

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        try:
            return json.loads(self.text())
        except json.JSONDecodeError as exc:
            raise EvidenceError("invalid_json", f"invalid JSON from {self.url}: {exc}") from exc


class Transport(Protocol):
    def fetch(self, url: str, *, accept: str) -> Response:
        """Read one URL without mutating remote state."""


def validate_http_url(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise PreflightInputError(f"{field} must be a string")
    try:
        parsed = urlsplit(value.strip())
        port_number = parsed.port
    except ValueError as exc:
        raise PreflightInputError(f"{field} contains an invalid port") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise PreflightInputError(f"{field} must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise PreflightInputError(f"{field} must not contain credentials")
    host = parsed.hostname.lower()
    port = f":{port_number}" if port_number else ""
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), host + port, path, parsed.query, ""))


def canonicalize_github_match(match: re.Match[str]) -> str:
    owner, repo, kind, number = match.group(1), match.group(2), match.group(3), match.group(4)
    return f"https://github.com/{owner}/{repo}/{kind.lower()}/{int(number)}"


def validate_github_item_url(value: str) -> str:
    normalized = validate_http_url(value, "canonical_url")
    match = GITHUB_ITEM_RE.fullmatch(normalized)
    if not match:
        raise PreflightInputError("canonical_url must name one GitHub issue or pull request")
    return canonicalize_github_match(match)


@dataclass(frozen=True)
class Candidate:
    candidate_url: str
    platform: str
    advertised_amount: str
    currency: str
    canonical_url: str | None = None
    max_age_days: int = 90
    max_visible_claims: int = 0

    @classmethod
    def validated(
        cls,
        *,
        candidate_url: str,
        platform: str,
        advertised_amount: str,
        currency: str,
        canonical_url: str | None = None,
        max_age_days: int = 90,
        max_visible_claims: int = 0,
    ) -> "Candidate":
        normalized_candidate = validate_http_url(candidate_url, "candidate_url")
        normalized_canonical = validate_github_item_url(canonical_url) if canonical_url else None
        if not platform.strip() or len(platform.strip()) > 80:
            raise PreflightInputError("platform must contain 1..80 visible characters")
        try:
            amount = Decimal(str(advertised_amount))
        except (InvalidOperation, ValueError) as exc:
            raise PreflightInputError("advertised_amount must be a decimal number") from exc
        if not amount.is_finite() or amount < 0:
            raise PreflightInputError("advertised_amount must be finite and non-negative")
        normalized_amount = format(amount, "f")
        if "." in normalized_amount:
            normalized_amount = normalized_amount.rstrip("0").rstrip(".")
        normalized_amount = normalized_amount or "0"
        normalized_currency = currency.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", normalized_currency):
            raise PreflightInputError("currency must be a three-letter code")
        if isinstance(max_age_days, bool) or not isinstance(max_age_days, int) or max_age_days < 1:
            raise PreflightInputError("max_age_days must be a positive integer")
        if isinstance(max_visible_claims, bool) or not isinstance(max_visible_claims, int) or max_visible_claims < 0:
            raise PreflightInputError("max_visible_claims must be a non-negative integer")
        return cls(
            candidate_url=normalized_candidate,
            platform=platform.strip(),
            advertised_amount=normalized_amount,
            currency=normalized_currency,
            canonical_url=normalized_canonical,
            max_age_days=max_age_days,
            max_visible_claims=max_visible_claims,
        )


@dataclass(frozen=True)
class Resolution:
    requested_url: str
    candidate_final_url: str
    candidate_status: int | None
    canonical_url: str | None
    canonical_hint: str | None = None
