"""Shared deterministic fixtures for funded-work preflight tests."""
from __future__ import annotations

from datetime import datetime, timezone
import json

from funded_work_freshness import Candidate, Response

NOW = datetime(2026, 9, 13, 6, 30, tzinfo=timezone.utc)


class FakeTransport:
    def __init__(self, routes):
        self.routes = dict(routes)
        self.calls = []

    def fetch(self, url, *, accept):
        self.calls.append((url, accept))
        value = self.routes[url]
        if isinstance(value, Exception):
            raise value
        return value


def response(url, payload, status=200, headers=None):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    return Response(url=url, status=status, headers=headers or {}, body=body)


def html_response(url, html, status=200, headers=None):
    return Response(url=url, status=status, headers=headers or {}, body=html.encode("utf-8"))


def candidate(url="https://board.example/reward/1", amount="500", canonical_url=None):
    return Candidate.validated(
        candidate_url=url,
        platform="fixture-board",
        advertised_amount=amount,
        currency="USD",
        canonical_url=canonical_url,
        max_age_days=30,
    )


def api(owner, repo, number):
    return f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"


def open_issue(
    url,
    *,
    body=None,
    assignees=None,
    title="Fresh funded work",
    labels=None,
    author_login="maintainer",
    author_association="OWNER",
    created_at="2026-09-10T00:00:00Z",
    updated_at="2026-09-13T03:00:00Z",
):
    return {
        "html_url": url,
        "title": title,
        "body": body
        or "## Acceptance Criteria\n- [ ] deterministic receipt\n\nReward: $500 via Algora",
        "state": "open",
        "assignees": assignees or [],
        "labels": labels or [],
        "user": {"login": author_login},
        "author_association": author_association,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def evidence_routes(owner, repo, number, issue, comments=None, timeline=None, *, archived=False):
    base = api(owner, repo, number)
    repository_url = f"https://api.github.com/repos/{owner}/{repo}"
    return {
        repository_url: response(repository_url, {"archived": archived}),
        base: response(base, issue),
        f"{base}/comments?per_page=100": response(
            f"{base}/comments?per_page=100", comments or []
        ),
        f"{base}/timeline?per_page=100": response(
            f"{base}/timeline?per_page=100", timeline or []
        ),
    }
