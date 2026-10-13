#!/usr/bin/env python3
"""Prove that one file on GitHub ``main`` is the file served by Pages.

The checker pins repository truth to an immutable commit before reading the
source file.  It then compares those exact bytes with the corresponding GitHub
Pages URL.  A caller may also supply a marker that distinguishes the new page
from an older bake.

Exit codes: 0 LIVE, 1 STALE/MISMATCH, 2 UNAVAILABLE.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


Fetch = Callable[[str], bytes]


@dataclass(frozen=True)
class Result:
    status: str
    repo: str
    path: str
    main_sha: str
    blob_sha: str
    pages_url: str
    source_sha256: str
    served_sha256: str
    marker_present: bool | None
    detail: str


def fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "commons-pages-readback/1"})
    with urlopen(request, timeout=20) as response:
        return response.read()


def api_url(repo: str, suffix: str) -> str:
    owner, name = repo.split("/", 1)
    return "https://api.github.com/repos/%s/%s/%s" % (quote(owner), quote(name), suffix)


def pages_url(repo: str, path: str) -> str:
    owner, name = repo.split("/", 1)
    encoded = "/".join(quote(part) for part in path.split("/"))
    return "https://%s.github.io/%s/%s" % (owner, quote(name), encoded)


def classify(source: bytes, served: bytes, marker: bytes | None) -> tuple[str, bool | None, str]:
    marker_present = None if marker is None else marker in served
    if marker is not None and marker not in source:
        return "MISMATCH", marker_present, "expected marker is absent from pinned source"
    if source == served:
        return "LIVE", marker_present, "served bytes exactly match pinned source"
    if marker is not None and marker not in served:
        return "STALE", False, "served bytes do not contain the pinned-source marker"
    return "MISMATCH", marker_present, "served bytes differ from pinned source"


def check(repo: str, path: str, marker: str | None, fetch: Fetch = fetch_bytes) -> Result:
    if repo.count("/") != 1 or not all(repo.split("/")):
        raise ValueError("repo must be OWNER/NAME")
    path = path.strip("/")
    if not path:
        raise ValueError("path must not be empty")

    commit = json.loads(fetch(api_url(repo, "commits/main")))
    main_sha = commit["sha"]
    content_suffix = "contents/%s?ref=%s" % ("/".join(quote(part) for part in path.split("/")), quote(main_sha))
    content = json.loads(fetch(api_url(repo, content_suffix)))
    encoded = "".join(content["content"].split())
    source = base64.b64decode(encoded, validate=True)
    target = pages_url(repo, path)
    served = fetch(target)
    marker_bytes = marker.encode("utf-8") if marker is not None else None
    status, marker_present, detail = classify(source, served, marker_bytes)
    return Result(
        status=status,
        repo=repo,
        path=path,
        main_sha=main_sha,
        blob_sha=content["sha"],
        pages_url=target,
        source_sha256=hashlib.sha256(source).hexdigest(),
        served_sha256=hashlib.sha256(served).hexdigest(),
        marker_present=marker_present,
        detail=detail,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="repository-relative Pages path")
    parser.add_argument("--repo", default="woahwhattheheck/commons")
    parser.add_argument("--contains", help="UTF-8 marker expected in source and served bytes")
    parser.add_argument("--json", action="store_true", help="emit a machine-readable result")
    args = parser.parse_args(argv)
    try:
        result = check(args.repo, args.path, args.contains)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        payload = {"status": "UNAVAILABLE", "repo": args.repo, "path": args.path, "detail": str(exc)}
        print(json.dumps(payload, sort_keys=True) if args.json else "UNAVAILABLE: %s" % exc)
        return 2
    payload = asdict(result)
    print(json.dumps(payload, sort_keys=True) if args.json else "%s: %s (%s)" % (result.status, result.pages_url, result.detail))
    return 0 if result.status == "LIVE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
