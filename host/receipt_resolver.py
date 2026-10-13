#!/usr/bin/env python3
"""Resolve Commons receipt identifiers into one fail-closed state record.

Supported identifiers:
  #12569 | pr:12569 | GitHub pull URL (including query/fragment permalinks)
  review:5178620884 | review:12567:5178620884
  run:34594768274 | GitHub Actions run/job URL (including query/fragment permalinks)
  blob:830e8e9a3ddae95799142eba6bcbd03f85eb4787
  commit:ae90064a7c0f0a2b0346a9f88b056403825a9313 | GitHub commit URL
  marker:OUTCOME-COMMERCE-PR12567-GUARDED-INTEGRATION-20260911-01

The resolver deliberately does not accept a bare integer: numeric PR, review and run
IDs overlap as a namespace. Ambiguous or missing lookups fail closed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

DEFAULT_REPO = "woahwhattheheck/commons"
DEFAULT_COORDINATION_URL = (
    "https://raw.githubusercontent.com/woahwhattheheck/commons/"
    "state/coordination/coordination.json"
)
_HEX40 = re.compile(r"^[0-9a-fA-F]{40}$")
_PULL_URL = re.compile(r"^https://github\.com/([^/?#]+/[^/?#]+)/pull/(\d+)(?:[/?#].*)?$")
_RUN_URL = re.compile(
    r"^https://github\.com/([^/?#]+/[^/?#]+)/actions/runs/([0-9]+)"
    r"(?:/job/[0-9]+)?/?(?:[?#].*)?$"
)
_COMMIT_URL = re.compile(r"^https://github\.com/([^/]+/[^/]+)/commit/([0-9a-fA-F]{40})/?(?:[?#].*)?$")
_GITHUB_CREDENTIAL_HOSTS = frozenset({"api.github.com", "raw.githubusercontent.com"})


class ResolutionError(RuntimeError):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": False, "error": self.code, "message": str(self)}
        if self.details:
            out["details"] = self.details
        return out


@dataclass(frozen=True)
class ParsedId:
    kind: str
    value: str
    parent: int | None = None


JsonGetter = Callable[[str], Any]
TextGetter = Callable[[str], str]


def parse_identifier(raw: str, repo: str = DEFAULT_REPO) -> ParsedId:
    value = raw.strip()
    if not value:
        raise ResolutionError("INVALID_IDENTIFIER", "identifier is empty")

    match = _PULL_URL.match(value)
    if match:
        url_repo, number = match.groups()
        if url_repo.lower() != repo.lower():
            raise ResolutionError(
                "WRONG_REPOSITORY",
                "pull URL points at a different repository",
                expected=repo,
                actual=url_repo,
            )
        return ParsedId("pr", number)

    match = _RUN_URL.fullmatch(value)
    if match:
        url_repo, run_id = match.groups()
        if url_repo.lower() != repo.lower():
            raise ResolutionError(
                "WRONG_REPOSITORY",
                "run URL points at a different repository",
                expected=repo,
                actual=url_repo,
            )
        # A job permalink still identifies its containing run; job success is not inferred.
        return ParsedId("run", run_id)

    match = _COMMIT_URL.fullmatch(value)
    if match:
        url_repo, sha = match.groups()
        if url_repo.lower() != repo.lower():
            raise ResolutionError(
                "WRONG_REPOSITORY",
                "commit URL points at a different repository",
                expected=repo,
                actual=url_repo,
            )
        return ParsedId("commit", sha.lower())

    if value.startswith("#") and value[1:].isdigit():
        return ParsedId("pr", value[1:])
    if value.lower().startswith("pr:") and value[3:].isdigit():
        return ParsedId("pr", value[3:])
    if value.lower().startswith("run:") and value[4:].isdigit():
        return ParsedId("run", value[4:])
    if value.lower().startswith("commit:"):
        sha = value[7:]
        if not _HEX40.fullmatch(sha):
            raise ResolutionError("INVALID_COMMIT", "commit id must be an exact 40-hex Git SHA")
        return ParsedId("commit", sha.lower())
    if value.lower().startswith("blob:"):
        sha = value[5:]
        if not _HEX40.fullmatch(sha):
            raise ResolutionError("INVALID_BLOB", "blob id must be an exact 40-hex Git SHA")
        return ParsedId("blob", sha.lower())
    if value.lower().startswith("review:"):
        bits = value.split(":")
        if len(bits) == 2 and bits[1].isdigit():
            return ParsedId("review", bits[1])
        if len(bits) == 3 and bits[1].isdigit() and bits[2].isdigit():
            return ParsedId("review", bits[2], int(bits[1]))
        raise ResolutionError(
            "INVALID_REVIEW",
            "review id must be review:<id> or review:<pr>:<id>",
        )
    if value.lower().startswith("marker:") and value[7:].strip():
        return ParsedId("marker", value[7:].strip())
    if value.isdigit():
        raise ResolutionError(
            "AMBIGUOUS_NUMERIC_ID",
            "bare numeric ids are ambiguous; prefix with pr:, review:, or run:",
        )
    raise ResolutionError("INVALID_IDENTIFIER", "unsupported identifier syntax", identifier=value)


def _coordination_rows(text: str, *, expected_repo: str | None = None) -> list[dict[str, Any]]:
    text = text.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        rows: list[dict[str, Any]] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ResolutionError("BAD_COORDINATION_STATE", "coordination JSONL is malformed") from exc
            if not isinstance(item, dict):
                raise ResolutionError("BAD_COORDINATION_STATE", "JSONL row is not an object")
            rows.append(item)
        return rows

    if isinstance(parsed, list):
        if not all(isinstance(row, dict) for row in parsed):
            raise ResolutionError("BAD_COORDINATION_STATE", "coordination array contains non-object rows")
        return list(parsed)
    if isinstance(parsed, dict):
        source_repo = parsed.get("repo")
        if expected_repo is not None and source_repo is not None:
            if not isinstance(source_repo, str) or not source_repo.strip():
                raise ResolutionError("BAD_COORDINATION_STATE", "coordination repo is not a nonempty string")
            if source_repo.lower() != expected_repo.lower():
                raise ResolutionError(
                    "WRONG_COORDINATION_REPOSITORY",
                    "coordination state belongs to another repository; select a coordination URL for the requested repository",
                    expected=expected_repo,
                    actual=source_repo,
                )
        for key in ("pull_requests", "prs", "rows"):
            rows = parsed.get(key)
            if isinstance(rows, list):
                if not all(isinstance(row, dict) for row in rows):
                    raise ResolutionError("BAD_COORDINATION_STATE", "coordination row collection contains non-object rows")
                return list(rows)
        return [parsed]
    raise ResolutionError("BAD_COORDINATION_STATE", "coordination payload is not object/array/JSONL")


def _walk_review_ids(value: Any) -> Iterable[int]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"review_id", "reviewId"}:
                try:
                    yield int(item)
                except (TypeError, ValueError):
                    pass
            yield from _walk_review_ids(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_review_ids(item)


def _marker_values(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            low = key.lower()
            if "marker" in low:
                if isinstance(item, str):
                    yield item
                elif isinstance(item, list):
                    for part in item:
                        if isinstance(part, str):
                            yield part
            yield from _marker_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _marker_values(item)


def _row_pr_number(row: dict[str, Any]) -> int | None:
    for key in ("number", "pr", "pr_number", "pull_number"):
        value = row.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    pr = row.get("pull_request")
    if isinstance(pr, dict):
        value = pr.get("number")
        if isinstance(value, int):
            return value
    return None


class Resolver:
    def __init__(
        self,
        repo: str = DEFAULT_REPO,
        *,
        api_base: str = "https://api.github.com",
        coordination_url: str = DEFAULT_COORDINATION_URL,
        get_json: JsonGetter,
        get_text: TextGetter,
    ) -> None:
        if repo.count("/") != 1:
            raise ValueError("repo must be owner/name")
        self.repo = repo
        self.api_base = api_base.rstrip("/")
        self.coordination_url = coordination_url
        self.get_json = get_json
        self.get_text = get_text
        self._coord_cache: list[dict[str, Any]] | None = None

    def _api(self, suffix: str) -> Any:
        return self.get_json(f"{self.api_base}/repos/{self.repo}{suffix}")

    def _coord(self) -> list[dict[str, Any]]:
        if self._coord_cache is None:
            self._coord_cache = _coordination_rows(
                self.get_text(self.coordination_url), expected_repo=self.repo
            )
        return self._coord_cache

    def resolve(self, raw: str) -> dict[str, Any]:
        parsed = parse_identifier(raw, self.repo)
        method = getattr(self, f"_resolve_{parsed.kind}")
        result = method(parsed)
        result["ok"] = True
        result["query"] = raw
        result["kind"] = parsed.kind
        return result

    def _resolve_pr(self, parsed: ParsedId) -> dict[str, Any]:
        number = int(parsed.value)
        pr = self._api(f"/pulls/{number}")
        if not isinstance(pr, dict) or int(pr.get("number", -1)) != number:
            raise ResolutionError("BAD_GITHUB_RESPONSE", "pull response did not bind requested number")
        merged = bool(pr.get("merged"))
        if merged:
            state = "MERGED"
        elif pr.get("state") == "open" and pr.get("draft"):
            state = "OPEN_DRAFT"
        elif pr.get("state") == "open":
            state = "OPEN"
        else:
            state = "CLOSED"
        base = pr.get("base") if isinstance(pr.get("base"), dict) else {}
        base_repo = base.get("repo") if isinstance(base.get("repo"), dict) else {}
        return {
            "state": state,
            "pr": number,
            "url": pr.get("html_url"),
            "head_sha": (pr.get("head") or {}).get("sha") if isinstance(pr.get("head"), dict) else None,
            "base_sha": base.get("sha"),
            "base_ref": base.get("ref"),
            "base_repository": base_repo.get("full_name"),
            # GitHub also supplies a prospective merge SHA on unmerged PRs.
            "merge_commit_sha": pr.get("merge_commit_sha") if merged else None,
            "merged_at": pr.get("merged_at") if merged else None,
            "mergeable": pr.get("mergeable"),
            "updated_at": pr.get("updated_at"),
        }

    def _resolve_run(self, parsed: ParsedId) -> dict[str, Any]:
        run_id = int(parsed.value)
        run = self._api(f"/actions/runs/{run_id}")
        if not isinstance(run, dict) or int(run.get("id", -1)) != run_id:
            raise ResolutionError("BAD_GITHUB_RESPONSE", "run response did not bind requested id")
        status = str(run.get("status") or "unknown").upper()
        conclusion = run.get("conclusion")
        state = f"{status}:{str(conclusion).upper()}" if conclusion else status
        return {
            "state": state,
            "run_id": run_id,
            "url": run.get("html_url"),
            "head_sha": run.get("head_sha"),
            "event": run.get("event"),
            "run_attempt": run.get("run_attempt"),
            "updated_at": run.get("updated_at"),
        }

    def _resolve_commit(self, parsed: ParsedId) -> dict[str, Any]:
        sha = parsed.value
        commit = self._api(f"/git/commits/{sha}")
        if not isinstance(commit, dict) or str(commit.get("sha", "")).lower() != sha:
            raise ResolutionError("BAD_GITHUB_RESPONSE", "commit response did not bind requested sha")
        tree = commit.get("tree") if isinstance(commit.get("tree"), dict) else {}
        committer = commit.get("committer") if isinstance(commit.get("committer"), dict) else {}
        return {
            # An available Git object does not prove branch inclusion or deployment.
            "state": "AVAILABLE",
            "sha": sha,
            "url": commit.get("html_url"),
            "tree_sha": tree.get("sha"),
            "parent_shas": [parent.get("sha") for parent in commit.get("parents", []) if isinstance(parent, dict)],
            "committed_at": committer.get("date"),
        }

    def _resolve_blob(self, parsed: ParsedId) -> dict[str, Any]:
        sha = parsed.value
        blob = self._api(f"/git/blobs/{sha}")
        if not isinstance(blob, dict) or str(blob.get("sha", "")).lower() != sha:
            raise ResolutionError("BAD_GITHUB_RESPONSE", "blob response did not bind requested sha")
        return {
            "state": "AVAILABLE",
            "sha": sha,
            "size": blob.get("size"),
            "encoding": blob.get("encoding"),
            "url": blob.get("url"),
        }

    def _resolve_review(self, parsed: ParsedId) -> dict[str, Any]:
        review_id = int(parsed.value)
        pr_number = parsed.parent
        evidence = "explicit-pr"
        if pr_number is None:
            matches: list[int] = []
            for row in self._coord():
                if review_id in set(_walk_review_ids(row)):
                    number = _row_pr_number(row)
                    if number is not None:
                        matches.append(number)
            matches = sorted(set(matches))
            if not matches:
                raise ResolutionError(
                    "REVIEW_NOT_INDEXED",
                    "review:<id> is not indexed by coordination state; use review:<pr>:<id>",
                    review_id=review_id,
                )
            if len(matches) != 1:
                raise ResolutionError(
                    "AMBIGUOUS_REVIEW",
                    "review id matched more than one coordination row",
                    review_id=review_id,
                    prs=matches,
                )
            pr_number = matches[0]
            evidence = "coordination-index"

        review = self._api(f"/pulls/{pr_number}/reviews/{review_id}")
        if not isinstance(review, dict) or int(review.get("id", -1)) != review_id:
            raise ResolutionError("BAD_GITHUB_RESPONSE", "review response did not bind requested id")
        return {
            "state": str(review.get("state") or "UNKNOWN").upper(),
            "review_id": review_id,
            "pr": pr_number,
            "commit_id": review.get("commit_id"),
            "submitted_at": review.get("submitted_at"),
            "url": review.get("html_url"),
            "resolved_via": evidence,
        }

    def _resolve_marker(self, parsed: ParsedId) -> dict[str, Any]:
        marker = parsed.value
        coord_matches: list[int] = []
        for row in self._coord():
            if marker in set(_marker_values(row)):
                number = _row_pr_number(row)
                if number is not None:
                    coord_matches.append(number)
        coord_matches = sorted(set(coord_matches))
        if len(coord_matches) == 1:
            target = self._resolve_pr(ParsedId("pr", str(coord_matches[0])))
            return {"state": "RESOLVED", "marker": marker, "resolved_via": "coordination-index", "target": target}
        if len(coord_matches) > 1:
            raise ResolutionError("AMBIGUOUS_MARKER", "marker matched multiple coordination rows", prs=coord_matches)

        query = f'repo:{self.repo} is:pr "{marker}"'
        search = self.get_json(f"{self.api_base}/search/issues?{urlencode({'q': query, 'per_page': 10})}")
        items = search.get("items", []) if isinstance(search, dict) else []
        prs = sorted({int(item["number"]) for item in items if isinstance(item, dict) and item.get("pull_request") and str(item.get("number", "")).isdigit()})
        if not prs:
            raise ResolutionError("MARKER_NOT_FOUND", "marker did not resolve to a pull request", marker=marker)
        if len(prs) != 1:
            raise ResolutionError("AMBIGUOUS_MARKER", "marker search matched multiple pull requests", marker=marker, prs=prs)
        target = self._resolve_pr(ParsedId("pr", str(prs[0])))
        return {"state": "RESOLVED", "marker": marker, "resolved_via": "github-search", "target": target}


def _credential_request(request: Request, token: str | None) -> Request:
    """Credentials follow the provider endpoint, not a caller-supplied URL."""
    request.remove_header("Authorization")
    try:
        parsed = urlsplit(request.full_url)
        provider = (parsed.scheme == "https" and parsed.hostname in _GITHUB_CREDENTIAL_HOSTS
                    and parsed.port in (None, 443) and parsed.username is None)
    except ValueError:
        provider = False
    if token and provider:
        # urllib does not copy unredirected headers; redirects are scoped again.
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    return request


class _CredentialRedirectHandler(HTTPRedirectHandler):
    def __init__(self, token: str | None) -> None:
        self._token = token

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        request = super().redirect_request(req, fp, code, msg, headers, newurl)
        return _credential_request(request, self._token) if request is not None else None


def _network_getters(token: str | None) -> tuple[JsonGetter, TextGetter]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "commons-receipt-resolver/1"}
    opener = build_opener(_CredentialRedirectHandler(token))

    def get_text(url: str) -> str:
        try:
            request = _credential_request(Request(url, headers=headers), token)
            with opener.open(request, timeout=20) as response:
                return response.read().decode("utf-8")
        except HTTPError as exc:
            raise ResolutionError("HTTP_ERROR", f"HTTP {exc.code} while reading {url}") from exc
        except URLError as exc:
            raise ResolutionError("NETWORK_ERROR", f"network error while reading {url}: {exc.reason}") from exc

    def get_json(url: str) -> Any:
        text = get_text(url)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ResolutionError("BAD_JSON", f"response from {url} is not JSON") from exc

    return get_json, get_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("identifier")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--coordination-url", default=DEFAULT_COORDINATION_URL)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)

    get_json, get_text = _network_getters(os.environ.get("GITHUB_TOKEN"))
    resolver = Resolver(
        args.repo,
        coordination_url=args.coordination_url,
        get_json=get_json,
        get_text=get_text,
    )
    try:
        result = resolver.resolve(args.identifier)
    except ResolutionError as exc:
        json.dump(exc.as_dict(), sys.stdout, indent=2 if args.pretty else None, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    json.dump(result, sys.stdout, indent=2 if args.pretty else None, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
