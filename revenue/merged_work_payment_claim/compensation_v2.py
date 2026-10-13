from __future__ import annotations

from typing import Any

from .bindings_v2 import _same_subject, _source, _subject
from .codec_v2 import ClaimError, canonical, exact, integer, nullable_utc, repo, text, utc


def _compensation(raw: Any, root_subject: dict[str, str], work: dict[str, Any]) -> list[dict[str, Any]]:
    if type(raw) is not list or len(raw) > 32:
        raise ClaimError("compensation: bounded array required")
    rows: list[dict[str, Any]] = []
    by_id: dict[str, bytes] = {}
    for i, item in enumerate(raw):
        where = f"compensation[{i}]"
        row = exact(item, {"offer_id", "subject", "repository", "pr_number", "source_ref", "source_sha256", "advertised_at", "expires_at", "currency", "amount_minor", "terms_text", "eligibility_required", "supersedes_offer_id"}, where)
        subject = _subject(row["subject"], f"{where}.subject"); _same_subject(subject, root_subject, f"{where}.subject")
        if repo(row["repository"], f"{where}.repository") != work["repository"] or integer(row["pr_number"], f"{where}.pr_number", 1, 2_147_483_647) != work["pr_number"]:
            raise ClaimError(f"{where}: cross-work compensation transplant")
        advertised_at, _ = utc(row["advertised_at"], f"{where}.advertised_at")
        expires_at, _ = nullable_utc(row["expires_at"], f"{where}.expires_at")
        currency = row["currency"]
        amount = row["amount_minor"]
        terms = row["terms_text"]
        if currency is not None:
            currency = text(currency, f"{where}.currency", 3)
            if len(currency) != 3 or not currency.isascii() or not currency.isalpha() or currency.upper() != currency:
                raise ClaimError(f"{where}.currency: uppercase ISO-like code required")
        if amount is not None:
            amount = integer(amount, f"{where}.amount_minor", 1)
        if terms is not None:
            terms = text(terms, f"{where}.terms_text", 500)
        if (currency is None) != (amount is None):
            raise ClaimError(f"{where}: currency and amount_minor must be paired")
        if currency is not None and terms is not None:
            raise ClaimError(f"{where}: fixed amount and non-fixed terms are mutually exclusive")
        required = row["eligibility_required"]
        if type(required) is not bool:
            raise ClaimError(f"{where}.eligibility_required: bool required")
        supersedes = row["supersedes_offer_id"]
        if supersedes is not None:
            supersedes = text(supersedes, f"{where}.supersedes_offer_id", 120)
        source_ref, source_sha = _source(row, where)
        normalized = {
            "offer_id": text(row["offer_id"], f"{where}.offer_id", 120),
            "subject": subject,
            "repository": work["repository"],
            "pr_number": work["pr_number"],
            "source_ref": source_ref,
            "source_sha256": source_sha,
            "advertised_at": advertised_at,
            "expires_at": expires_at,
            "currency": currency,
            "amount_minor": amount,
            "terms_text": terms,
            "eligibility_required": required,
            "supersedes_offer_id": supersedes,
        }
        encoded = canonical(normalized)
        oid = normalized["offer_id"]
        if oid in by_id:
            if by_id[oid] != encoded:
                raise ClaimError(f"{where}: changed same-ID compensation evidence")
            raise ClaimError(f"{where}: duplicate compensation offer_id")
        by_id[oid] = encoded
        rows.append(normalized)
    ids = set(by_id)
    for row in rows:
        sup = row["supersedes_offer_id"]
        if sup is not None and sup not in ids:
            raise ClaimError("compensation: supersedes_offer_id not found")
        if sup == row["offer_id"]:
            raise ClaimError("compensation: offer cannot supersede itself")
    rows.sort(key=lambda r: (r["advertised_at"], r["offer_id"]))
    return rows
