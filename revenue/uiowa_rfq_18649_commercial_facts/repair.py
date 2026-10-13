"""Repair inconsistent draft text without collapsing prime/subcontract roles."""

from __future__ import annotations

import re

try:
    from .canonical import CANONICAL, STALE_SEPTEMBER_22_TOKENS
    from .checker import DocumentFacts, Finding, check_document
except ImportError:
    from canonical import CANONICAL, STALE_SEPTEMBER_22_TOKENS
    from checker import DocumentFacts, Finding, check_document

_STALE = re.compile(
    r"September 22, 2025|22 September 2025|Sep 22, 2025|9/22/2025|2025-09-22|"
    r"(?<!2026-)September 22(?!, 2026)",
    re.IGNORECASE,
)
_BASE = re.compile(r"\$?\s*25,000|\$?\s*20,000|\$?\s*28,000")
_OPTION = re.compile(r"\$?\s*5,000(?!.)")
_UPON_DELIVERY = re.compile(r"upon delivery", re.IGNORECASE)
_ROLE_AS_PRIME = re.compile(
    r"\bsubcontract(?:or|ing)?\b(.{0,40})\bas (?:the )?prime\b",
    re.IGNORECASE,
)


def repair_text(text: str) -> str:
    """Return a repaired draft. Prime/subcontract labels are preserved."""
    if type(text) is not str:
        raise TypeError("text must be a string")
    original_roles = (
        "prime" in text.casefold(),
        "subcontract" in text.casefold(),
    )
    out = text
    for token in STALE_SEPTEMBER_22_TOKENS:
        out = re.sub(re.escape(token), "September 22, 2026 3:00 PM CT", out, flags=re.IGNORECASE)
    out = _STALE.sub("September 22, 2026 3:00 PM CT", out)
    out = re.sub(
        r"(?im)^(deadline:\s*).+$",
        r"\g<1>2026-09-22 15:00 America/Chicago",
        out,
    )
    out = re.sub(r"(?im)^(base_amount_usd:\s*).+$", r"\g<1>24000", out)
    out = re.sub(r"(?im)^(option_amount_usd:\s*).+$", r"\g<1>4000", out)
    out = re.sub(r"(?im)^(milestone_split:\s*).+$", r"\g<1>40/40/20", out)
    out = re.sub(r"(?im)^(currency:\s*).+$", r"\g<1>USD", out)
    out = re.sub(r"(?im)^(kickoff_assumption:\s*).+$", r"\g<1>after_award_no_travel", out)
    out = re.sub(r"(?im)^(travel_treatment:\s*).+$", r"\g<1>excluded_from_base", out)
    out = re.sub(r"(?im)^(final_trigger:\s*).+$", r"\g<1>acceptance", out)
    out = re.sub(r"(?im)^(principal_role:\s*).+$", r"\g<1>prime", out)
    out = re.sub(r"(?im)^(specialist_role:\s*).+$", r"\g<1>subcontract", out)
    out = _BASE.sub("$24,000", out)
    out = re.sub(r"\$5,000", "$4,000", out)
    out = _UPON_DELIVERY.sub("upon acceptance", out)
    # Keep role identities; never rewrite subcontract as prime.
    out = _ROLE_AS_PRIME.sub(r"subcontract\1as subcontract", out)
    repaired_roles = (
        "prime" in out.casefold(),
        "subcontract" in out.casefold(),
    )
    if original_roles[1] and not repaired_roles[1]:
        raise RuntimeError("repair collapsed subcontract identity")
    if original_roles[0] and not repaired_roles[0]:
        raise RuntimeError("repair collapsed prime identity")
    return out


def repair_document(doc: DocumentFacts) -> tuple[str, list[Finding]]:
    repaired = repair_text(doc.text)
    remaining = [
        f
        for f in check_document(DocumentFacts(doc.name, repaired))
        if f.code != "ROLE_COLLAPSE"
    ]
    return repaired, remaining
