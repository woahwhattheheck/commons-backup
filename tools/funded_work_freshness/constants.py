"""Shared constants for the funded-work freshness preflight."""
from __future__ import annotations

import re

SCHEMA = "commons-funded-work-freshness/v1"
MAX_HTTP_BYTES = 2 * 1024 * 1024
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
TRUSTED_SPONSOR_BOTS = {"algora-pbc[bot]", "opire-bot", "opire[bot]", "polar-sh[bot]"}
# Candidate-page auto-discovery is intentionally narrower than the generic HTTP transport.
# Arbitrary boards remain supported when callers provide an explicit canonical GitHub URL.
AUTO_RESOLVE_SOURCE_HOSTS = (
    "algora.io",
    "opire.dev",
    "polar.sh",
    "issuehunt.io",
    "gitcoin.co",
)
USER_AGENT = "commons-funded-work-freshness/1.0"
# Query/fragment tails may contain reserved characters. Slash tails are limited to
# unreserved path segments so dot-segments and encoded delimiters cannot prefix-bind.
GITHUB_ITEM_RE = re.compile(
    r"https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/(issues|pull)/(\d+)(?:[?#][^\s\"'<>]*|/(?:[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*/?)?(?:[?#][^\s\"'<>]*)?(?=$|[\s\"'<>]|[.,;:!?)\]}]+(?=$|\s))|(?=$|[\s\"'<>]|[.,;:!?)\]}]+(?=$|\s)))",
    re.IGNORECASE,
)
STRICT_CLAIM_RE = re.compile(
    r"(?im)(?:^|\n)\s*/(?:attempt|claim)\b|\bclaiming\s+(?:this|the)\s+(?:issue|bounty|reward)\b"
)
SPONSOR_RE = re.compile(
    r"(?i)(?:https?://(?:www\.)?(?:algora\.io|opire\.dev|polar\.sh|issuehunt\.io|gitcoin\.co)/|\b(?:via|sponsored\s+by|reward(?:ed)?\s+by)\s+(?:algora|opire|polar|issuehunt|gitcoin)\b)"
)
ACCEPTANCE_RE = re.compile(
    r"(?im)^\s{0,3}(?:#{1,6}\s*)?(?:acceptance criteria|requirements?|definition of done|deliverables?|scope)\b|^\s*[-*]\s*\[[ xX]\]"
)
# These directives are intentionally narrow. Ordinary words such as "cancelled build"
# must not alter commercial state merely because a bounty is mentioned elsewhere.
FUNDING_WITHDRAWAL_RE = re.compile(
    r"(?i)\b(?:"
    r"(?:bounty|reward|funding)\s+(?:(?:is|was|has\s+been)\s+)?(?:withdrawn|revoked|cancelled|canceled)"
    r"|(?:bounty|reward)\s+(?:(?:is|was)\s+)?no\s+longer\s+(?:available|active|funded|offered)"
    r"|funding\s+(?:(?:is|was)\s+)?no\s+longer\s+(?:available|active|offered)"
    r"|(?:withdrawn|revoked|cancelled|canceled)\s+(?:this|the)\s+(?:bounty|reward|funding)"
    r")\b"
)
FUNDING_RESTORATION_RE = re.compile(
    r"(?i)\b(?:"
    r"(?:bounty|reward|funding)\s+(?:(?:is|was|has\s+been)\s+)?(?:restored|reinstated|reactivated|reopened)"
    r"|(?:bounty|reward)\s+(?:(?:is|was)\s+)?(?:available|active|funded|offered)\s+again"
    r"|funding\s+(?:(?:is|was)\s+)?(?:available|active|offered)\s+again"
    r"|(?:restored|reinstated|reactivated|reopened)\s+(?:this|the)\s+(?:bounty|reward|funding)"
    r")\b"
)
SECURITY_RE = re.compile(
    r"(?i)\b(?:security|vulnerabilit(?:y|ies)|cve-\d{4}-\d+|exploit|rce|xss|csrf|ssrf|sql injection)\b"
)
LINK_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')
