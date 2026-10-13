#!/usr/bin/env python3
"""Redact raw attachment URLs in exact-body republish.

PICK: accepted source bodies preserve ordinary local paths byte-for-byte.
Only raw private attachment-download URLs are replaced with the established
marker before a body is written to public/git surfaces.

This is not an admission gate. Posts still land. Redaction only transforms
matching attachment URL bytes.

Law: ground/EXACT_BODY_REDACT.md
Leftover: exact-body-republish-private-paths-attachments
"""

from __future__ import annotations

import re

# Keep the established marker for compatibility with already-published pages.
LOCAL_PATH_REDACTED = "[local path redacted]"

# Raw attachment URLs. No named attachment marker exists on HEAD; use the
# established marker and never emit the URL. Do not recover expired ntfy files.
_ATTACHMENT_URL = re.compile(
    r"https?://(?:files\.slack\.com|slack-files\.com|"
    r"(?:www\.)?ntfy\.sh/file|ntfy\.envs\.net/file)/[^\s`\"'<>]+",
    re.IGNORECASE,
)

_SPANS = (_ATTACHMENT_URL,)


def redact_private_spans(text: str) -> str:
    """Replace raw attachment URL spans. Leave every other byte unchanged."""
    if not text:
        return text
    out = text
    for pattern in _SPANS:
        out = pattern.sub(LOCAL_PATH_REDACTED, out)
    return out


def same_after_redact(left: str, right: str) -> bool:
    """True when two bodies differ only by attachment URLs that redact equally."""
    return redact_private_spans(left or "").rstrip("\n") == redact_private_spans(
        right or ""
    ).rstrip("\n")
