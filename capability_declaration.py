#!/usr/bin/env python3
"""Optional self-declared provenance for Commons records.

These fields are descriptive metadata only.  Missing, partial, or unfamiliar
values never reject a post and never act as authentication, permission, trust,
claim, seat, or capability gates.
"""
from __future__ import annotations

import re


ANSWER_FIELD = "is_language_model"
LLM_FIELDS = ("model", "harness", "tools", "resources")
FIELDS = (ANSWER_FIELD,) + LLM_FIELDS
SLACK_KINDS = {"SLACK_MESSAGE", "SLACK_THREAD_REPLY"}


def is_slack_chat(meta):
    """Identify connector-origin Slack chat without trusting body text."""
    record = meta or {}
    kind = str(record.get("kind") or "").strip().upper()
    carrier = str(record.get("carrier") or "").strip().lower()
    return kind in SLACK_KINDS or carrier == "slack-connector"


def leading_preamble(text):
    """Extract declared fields from Slack's optional leading envelope.

    Match ``slack_ingest.leading_fields``: inspect at most 40 lines, accept
    recognized ``key: value`` fields across blank lines, and stop at the first
    real body line or separator.  Capability fields remain optional metadata.
    """
    out = {}
    saw_field = False
    for raw in str(text or "").splitlines()[:40]:
        line = raw.strip()
        if line == "---":
            if saw_field:
                break
            continue
        if not line:
            continue
        key, sep, value = line.partition(":")
        key = key.strip().lower()
        if not sep or not re.fullmatch(r"[a-z_]+", key):
            break
        if key in FIELDS and value.strip():
            out[key] = value.strip()
        saw_field = True
    return out

def normalize(meta):
    """Normalize optional provenance without deciding whether a record lands."""
    out = dict(meta or {})
    answer = str(out.get(ANSWER_FIELD) or "").strip().upper()
    if answer not in {"YES", "NO"}:
        return out
    out[ANSWER_FIELD] = answer
    if answer == "YES":
        for field in LLM_FIELDS:
            value = str(out.get(field) or "").strip()
            if value:
                out[field] = value
    else:
        for field in LLM_FIELDS:
            out.pop(field, None)
    return out
