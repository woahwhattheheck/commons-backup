#!/usr/bin/env python3
"""Resolve a webmcp-pad ref so actions/checkout@v4 can fetch it.

actions/checkout@v4 with fetch-depth:1 only treats a 40-character hex string
as a commit SHA. Anything else is fetched as:

  refs/heads/<ref>*  and  refs/tags/<ref>*

An abbreviated SHA such as ec8961c (woahwhattheheck/webmcp-pad, measured on
commons run 33849697120) matches no branch or tag, so git fetch exits 1
after three retries and the deploy never starts.

The GitHub commits API accepts branch, tag, full SHA, and abbreviated SHA.
This helper expands only abbreviated SHAs; named refs and full SHAs pass
through so the existing `main` bake road stays an ordinary checkout.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, TextIO


FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
ABBREV_SHA_RE = re.compile(r"^[0-9a-fA-F]{4,39}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
COMMITS_API = "https://api.github.com/repos/{repo}/commits/{ref}"
MEASURED_RUN = "33849697120"
MEASURED_SHORT = "ec8961c"


UrlOpen = Callable[..., object]


def classify_ref(ref: str) -> str:
    text = (ref or "").strip()
    if not text:
        raise ValueError("ref is empty")
    if FULL_SHA_RE.fullmatch(text):
        return "full_sha"
    if ABBREV_SHA_RE.fullmatch(text):
        return "abbrev_sha"
    return "named_ref"


def commits_api_url(repo: str, ref: str) -> str:
    if not REPO_RE.fullmatch(repo):
        raise ValueError("repo must be owner/name, got %r" % repo)
    return COMMITS_API.format(
        repo=repo,
        ref=urllib.parse.quote(ref, safe=""),
    )


def fetch_commit_sha(
    repo: str,
    ref: str,
    *,
    token: str = "",
    urlopen: UrlOpen | None = None,
    timeout: int = 20,
) -> str:
    """Return the 40-char SHA GitHub assigns to ``repo@ref``."""
    opener = urlopen or urllib.request.urlopen
    url = commits_api_url(repo, ref)
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "commons-webmcp-pad-ref",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer %s" % token
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with opener(request, timeout=timeout) as resp:
            raw = resp.read()
            status = getattr(resp, "status", 200)
    except urllib.error.HTTPError as visc:
        body = visc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(
            "could not resolve %s@%s (HTTP %s). actions/checkout@v4 fetch-depth:1 "
            "treats abbreviated SHAs as branch names; git fetch of refs/heads/%s* "
            "exits 1 (measured run %s). body: %s"
            % (repo, ref, visc.code, ref, MEASURED_RUN, body)
        ) from visc
    except urllib.error.URLError as visc:
        raise RuntimeError(
            "could not resolve %s@%s (%s)" % (repo, ref, visc.reason)
        ) from visc
    if status != 200:
        raise RuntimeError(
            "could not resolve %s@%s (HTTP %s)" % (repo, ref, status)
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as visc:
        raise RuntimeError(
            "commits API for %s@%s did not return JSON" % (repo, ref)
        ) from visc
    sha = str(payload.get("sha") or "")
    if not FULL_SHA_RE.fullmatch(sha):
        raise RuntimeError(
            "commits API for %s@%s did not return a 40-char SHA" % (repo, ref)
        )
    return sha.lower()


def checkout_ref(
    repo: str,
    ref: str,
    *,
    token: str = "",
    urlopen: UrlOpen | None = None,
) -> tuple[str, str]:
    """Return (kind, value-to-pass-to-actions-checkout)."""
    text = (ref or "").strip()
    kind = classify_ref(text)
    if kind == "full_sha":
        return kind, text.lower()
    if kind == "named_ref":
        return kind, text
    sha = fetch_commit_sha(repo, text, token=token, urlopen=urlopen)
    if not sha.startswith(text.lower()):
        raise RuntimeError(
            "resolved SHA %s does not start with abbreviated ref %s" % (sha, text)
        )
    return kind, sha


def write_github_output(path: str, kind: str, value: str) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("kind=%s\n" % kind)
        handle.write("ref=%s\n" % value)
        if FULL_SHA_RE.fullmatch(value):
            handle.write("sha=%s\n" % value)


def main(argv: list[str] | None = None, stdout: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/name (PAD_REPO)")
    parser.add_argument("--ref", required=True, help="branch, tag, full SHA, or abbreviated SHA")
    parser.add_argument(
        "--github-output",
        default="",
        help="append kind=/ref=/sha= lines (GITHUB_OUTPUT)",
    )
    parser.add_argument(
        "--token",
        default="",
        help="GitHub token; default GH_TOKEN or GITHUB_TOKEN",
    )
    args = parser.parse_args(argv)
    token = args.token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    try:
        kind, value = checkout_ref(args.repo, args.ref, token=token)
    except (ValueError, RuntimeError) as visc:
        print("::error::%s" % visc, file=sys.stderr)
        return 1
    out = stdout or sys.stdout
    print("resolved %s@%s (%s) -> %s" % (args.repo, args.ref.strip(), kind, value), file=out)
    if args.github_output:
        write_github_output(args.github_output, kind, value)
    return 0


if __name__ == "__main__":
    sys.exit(main())
