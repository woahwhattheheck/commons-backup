"""Canonical GitHub resolution and complete read helpers."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlsplit

from constants import AUTO_RESOLVE_SOURCE_HOSTS, GITHUB_ITEM_RE, LINK_NEXT_RE
from errors import EvidenceError
from models import Candidate, Resolution, Response, Transport, canonicalize_github_match


def github_urls(text: str) -> list[str]:
    return sorted({canonicalize_github_match(match) for match in GITHUB_ITEM_RE.finditer(text)})


def auto_resolve_source_allowed(url: str) -> bool:
    """Return whether an advertised page is trusted enough for automatic network discovery.

    Arbitrary marketplace URLs are untrusted input. Fetching them after a separate DNS
    safety preflight would leave a DNS-rebinding time-of-check/time-of-use window because
    the HTTP stack resolves the hostname again when it opens the socket. Automatic page
    discovery is therefore restricted to recognized sponsor-owned host suffixes. Other
    boards stay supported by supplying an explicit canonical GitHub issue/PR URL.
    """

    host = (urlsplit(url).hostname or "").rstrip(".").lower()
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in AUTO_RESOLVE_SOURCE_HOSTS)


def resolve_candidate(candidate: Candidate, transport: Transport) -> Resolution:
    if candidate.canonical_url:
        return Resolution(
            requested_url=candidate.candidate_url,
            candidate_final_url=candidate.candidate_url,
            candidate_status=None,
            canonical_url=candidate.canonical_url,
        )
    direct = GITHUB_ITEM_RE.fullmatch(candidate.candidate_url)
    if direct:
        canonical = canonicalize_github_match(direct)
        return Resolution(
            requested_url=candidate.candidate_url,
            candidate_final_url=canonical,
            candidate_status=None,
            canonical_url=canonical,
        )

    if not auto_resolve_source_allowed(candidate.candidate_url):
        raise EvidenceError(
            "candidate_source_requires_canonical_url",
            "automatic candidate-page discovery is restricted to recognized sponsor hosts; "
            "provide --canonical-url for other boards",
        )

    response = transport.fetch(candidate.candidate_url, accept="text/html,application/xhtml+xml")
    urls = set(github_urls(response.url))
    urls.update(github_urls(response.text()))
    if len(urls) > 1:
        raise EvidenceError(
            "ambiguous_canonical_target",
            f"candidate page exposed multiple GitHub issue/PR targets: {sorted(urls)}",
        )
    canonical = next(iter(urls), None)
    if response.status in {404, 410} and canonical:
        return Resolution(
            requested_url=candidate.candidate_url,
            candidate_final_url=response.url,
            candidate_status=response.status,
            canonical_url=canonical,
            canonical_hint="deleted_or_missing",
        )
    if response.status == 429 or (
        response.status == 403 and response.headers.get("x-ratelimit-remaining") == "0"
    ):
        raise EvidenceError(
            "candidate_source_rate_limited", f"candidate source returned {response.status}"
        )
    if response.status < 200 or response.status >= 400:
        raise EvidenceError(
            "candidate_source_unavailable", f"candidate source returned {response.status}"
        )
    if canonical is None:
        raise EvidenceError(
            "canonical_target_missing", "candidate page did not expose one GitHub issue/PR URL"
        )
    return Resolution(
        requested_url=candidate.candidate_url,
        candidate_final_url=response.url,
        candidate_status=response.status,
        canonical_url=canonical,
    )


def github_parts(url: str) -> tuple[str, str, str, int]:
    match = GITHUB_ITEM_RE.fullmatch(url)
    if not match:
        raise EvidenceError("invalid_canonical_target", f"not a GitHub issue/PR URL: {url}")
    return match.group(1), match.group(2), match.group(3).lower(), int(match.group(4))


def api_item_url(url: str) -> str:
    owner, repo, _kind, number = github_parts(url)
    return f"https://api.github.com/repos/{quote(owner)}/{quote(repo)}/issues/{number}"


def classify_http_failure(response: Response, prefix: str) -> EvidenceError:
    if response.status == 429 or (
        response.status == 403 and response.headers.get("x-ratelimit-remaining") == "0"
    ):
        return EvidenceError(f"{prefix}_rate_limited", f"{prefix} returned {response.status}")
    return EvidenceError(f"{prefix}_unavailable", f"{prefix} returned {response.status}")


def fetch_json_pages(
    transport: Transport,
    url: str,
    *,
    prefix: str,
    max_pages: int = 10,
) -> list[Any]:
    values: list[Any] = []
    next_url: str | None = url
    seen: set[str] = set()
    for _ in range(max_pages):
        if next_url is None:
            return values
        if next_url in seen:
            raise EvidenceError(f"{prefix}_redirect_loop", f"pagination loop at {next_url}")
        seen.add(next_url)
        response = transport.fetch(next_url, accept="application/vnd.github+json")
        if response.status < 200 or response.status >= 300:
            raise classify_http_failure(response, prefix)
        payload = response.json()
        if not isinstance(payload, list):
            raise EvidenceError(
                f"{prefix}_invalid_json", f"{prefix} did not return a JSON array"
            )
        values.extend(payload)
        match = LINK_NEXT_RE.search(response.headers.get("link", ""))
        next_url = match.group(1) if match else None
    if next_url is not None:
        raise EvidenceError(f"{prefix}_pagination_incomplete", f"more than {max_pages} pages")
    return values
