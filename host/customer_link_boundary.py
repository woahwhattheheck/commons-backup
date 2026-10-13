#!/usr/bin/env python3
"""Fail-closed URL boundary for customer-facing copy."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import urlsplit


SCHEMA = "customer-link-boundary/v1"
_URL = re.compile(
    r"""(?P<url>
        (?:https?://|//|www\.)[^\s<>'"\[\](){}|]+
        |
        (?<![@A-Za-z0-9_.-])
        (?:
            (?:[A-Za-z0-9-]+\.)*github\.com
            |(?:[A-Za-z0-9-]+\.)*github\.io
            |(?:[A-Za-z0-9-]+\.)*githubusercontent\.com
            |(?:[A-Za-z0-9-]+\.)*githubassets\.com
            |(?:[A-Za-z0-9-]+\.)*commons\.mno
            |tokenjunkielabs\.slack\.com
        )
        (?:/[^\s<>'"\[\](){}|]*)?
    )""",
    re.IGNORECASE | re.VERBOSE,
)
_TRAILING = ".,;:!?"


class CustomerLinkBoundaryError(ValueError):
    """Customer-facing text contains an internal evidence URL."""


def _normalized_url(raw):
    value = unicodedata.normalize("NFKC", html.unescape(raw)).strip()
    value = value.rstrip(_TRAILING)
    value = value.replace("\\", "/")
    if value.startswith("//"):
        value = "https:" + value
    elif value.lower().startswith("www."):
        value = "https://" + value
    elif "://" not in value:
        value = "https://" + value
    return value


def _normalized_host(raw):
    parsed = urlsplit(_normalized_url(raw))
    host = (parsed.hostname or "").strip().rstrip(".").lower()
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return host


def _reason(host):
    if host == "github.io" or host.endswith(".github.io"):
        return "GITHUB_PAGES_HOST"
    if (
        host == "github.com"
        or host.endswith(".github.com")
        or host == "githubusercontent.com"
        or host.endswith(".githubusercontent.com")
        or host == "githubassets.com"
        or host.endswith(".githubassets.com")
    ):
        return "GITHUB_HOST"
    if host == "commons.mno" or host.endswith(".commons.mno"):
        return "COMMONS_HOST"
    if host == "tokenjunkielabs.slack.com":
        return "COMMONS_SLACK_HOST"
    return None


def _nfkc_view_with_offsets(text):
    normalized = []
    offsets = []
    for index, char in enumerate(text):
        for output in unicodedata.normalize("NFKC", char):
            normalized.append(output)
            offsets.append(index)
    return "".join(normalized), offsets


def scan_customer_text(text):
    """Return exact forbidden-link findings; an empty list is customer-link safe."""
    if not isinstance(text, str):
        raise TypeError("customer text must be str")
    normalized_text, offsets = _nfkc_view_with_offsets(text)
    findings = []
    for match in _URL.finditer(normalized_text):
        normalized_raw = match.group("url")
        start = offsets[match.start("url")]
        end = offsets[match.end("url") - 1] + 1
        raw = text[start:end]
        host = _normalized_host(normalized_raw)
        reason = _reason(host)
        if reason:
            findings.append({
                "start": start,
                "end": end,
                "raw": raw,
                "normalized_url": _normalized_url(normalized_raw),
                "host": host,
                "reason": reason,
            })
    return findings


def customer_link_report(text):
    findings = scan_customer_text(text)
    return {
        "schema": SCHEMA,
        "audience": "CUSTOMER",
        "state": "BLOCKED_CUSTOMER_LINK" if findings else "CUSTOMER_LINK_SAFE",
        "safe": not findings,
        "violation_count": len(findings),
        "violations": findings,
    }


def require_customer_link_safe(text):
    report = customer_link_report(text)
    if not report["safe"]:
        raise CustomerLinkBoundaryError(json.dumps(report, sort_keys=True))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Reject Commons and GitHub URLs in customer-facing copy"
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="-",
        help="UTF-8 text file, or - for stdin",
    )
    args = parser.parse_args(argv)
    if args.path == "-":
        text = sys.stdin.read()
    else:
        text = Path(args.path).read_text(encoding="utf-8")
    report = customer_link_report(text)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["safe"] else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
