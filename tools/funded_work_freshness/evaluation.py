"""Trust, activity, occupancy, and funding evidence checks."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import re
from typing import Any, Mapping, Sequence

from constants import (
    ACCEPTANCE_RE,
    FUNDING_RESTORATION_RE,
    FUNDING_WITHDRAWAL_RE,
    GITHUB_ITEM_RE,
    SPONSOR_RE,
    STRICT_CLAIM_RE,
    TRUSTED_ASSOCIATIONS,
    TRUSTED_SPONSOR_BOTS,
)
from models import validate_github_item_url


_MONEY_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    r"(?P<code>[A-Za-z]{3})\s*(?P<code_value>\d+(?:,\d{3})*(?:\.\d+)?)"
    r"|(?P<symbol>[$€£])\s*(?P<symbol_value>\d+(?:,\d{3})*(?:\.\d+)?)"
    r"|(?P<suffix_value>\d+(?:,\d{3})*(?:\.\d+)?)\s*(?P<suffix_code>[A-Za-z]{3})(?![A-Za-z0-9_])"
    r")"
)
_COMMERCIAL_NOUN_RE = re.compile(r"(?i)\b(?:reward|bounty|funding)(?:\s+amount)?\b")
_DIRECT_AMOUNT_LINK_RE = re.compile(
    r"(?i)^[\s:=,()\-]*"
    r"(?:(?:(?-i:[A-Z]{3})|amount|is|was|has|been|now|currently|set|updated|changed|increased|decreased|raised|reduced|to|at|of|worth|totals?|equals?)\b[\s:=,()\-]*){0,6}$"
)
_DIRECT_AMOUNT_CODE_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<code>[A-Za-z]{3})(?![A-Za-z0-9_])"
)
_REVERSE_AMOUNT_LINK_RE = re.compile(
    r"(?i)^\s*(?:as\s+(?:the\s+)?)?(?:reward|bounty|funding)\b"
)
_FROM_TO_RE = re.compile(
    r"(?i)\b(?:changed|updated|increased|decreased|raised|reduced)\b.*\bfrom\b.*\bto\b"
)
_CURRENT_TRANSITION_RE = re.compile(r"(?i)\bnow\b")
_CHANGE_FROM_PREFIX_RE = re.compile(
    r"(?i)\b(?:changed|updated|increased|decreased|raised|reduced)\b[^;\n]{0,120}\bfrom\b[\s:=,()\-]*$"
)
_TO_DESTINATION_RE = re.compile(r"(?i)^[\s:=,()\-]*to\b[\s:=,()\-]*$")
_NOW_DESTINATION_RE = re.compile(
    r"(?i)^[\s:=,()\-]*now\b[\s:=,()\-]*(?:is\b[\s:=,()\-]*)?$"
)
_UNRESOLVED_VALUE_PATTERN = (
    r"(?:tbd|unknown|variable|negotiable|unconfirmed|more|less|"
    r"varies(?:\s+by\s+scope)?|depends\s+on\s+(?:the\s+)?scope|"
    r"(?:an?\s+)?amount\s+to\s+be\s+determined|to\s+be\s+determined|"
    r"no\s+fixed\s+amount|not\s+(?:yet\s+)?(?:set|fixed))"
)
_UNRESOLVED_DIRECT_RE = re.compile(
    r"(?i)^(?:reward|bounty|funding)(?:\s+amount)?\b"
    r"[\s:=,()\-]*"
    r"(?:(?:is|was|now(?:\s+is)?|"
    r"has\s+been(?:\s+set(?:\s+to|\s+at)?)?|"
    r"set(?:\s+to|\s+at)?|changed\s+to|updated\s+to|"
    r"reduced\s+to|increased\s+to)\b[\s:=,()\-]*)?"
    + _UNRESOLVED_VALUE_PATTERN
    + r"\b"
)
_UNRESOLVED_AFTER_MONEY_RE = re.compile(
    r"(?i)^[\s:=,()\-]*(?:to|or|now(?:\s+is)?|instead(?:\s+is)?|"
    r"but\s+now(?:\s+is)?)\b[\s:=,()\-]*"
    + _UNRESOLVED_VALUE_PATTERN
    + r"\b"
)
_NONEXACT_AMOUNT_RE = re.compile(
    r"(?i)^(?:reward|bounty|funding)(?:\s+amount)?\b[^;\n]{0,120}(?:"
    r"\b(?:up\s+to|at\s+least|at\s+most|between|ranges?|varies|variable|"
    r"depends\s+on)\b"
    r"|\b(?:changed|updated|increased|decreased|raised|reduced)\b"
    r"[^;\n]{0,40}\bfrom\b"
    r")"
)
_SYMBOL_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP"}
# Mixed/lowercase strings count as currency codes only when they are known ISO
# 4217 alpha codes. This keeps ordinary prose such as "$200 via Algora" from
# becoming a false symbol/code conflict. All-uppercase unknown codes retain the
# previous fail-closed behavior, and historic codes remain useful for old issues.
_KNOWN_ISO_CURRENCY_CODES = frozenset(
    """
    AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND
    BOB BOV BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU
    CRC CUC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS
    GIP GMD GNF GTQ GYD HKD HNL HRK HTG HUF IDR ILS INR IQD IRR ISK JMD JOD
    JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL
    MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR
    NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG
    SEK SGD SHP SLE SLL SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY
    TTD TWD TZS UAH UGX USD USN UYI UYU UYW UZS VED VES VND VUV WST XAF XAG
    XAU XBA XBB XBC XBD XCD XDR XOF XPD XPF XPT XSU XTS XUA XXX YER ZAR ZMW
    ZWG ZWL
    """.split()
)
_SYMBOL_CODE_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    r"(?P<prefix>[A-Za-z]{3})[\s:=,()\-]*(?P<prefix_symbol>[$€£])\s*\d+(?:,\d{3})*(?:\.\d+)?"
    r"|(?P<suffix_symbol>[$€£])\s*\d+(?:,\d{3})*(?:\.\d+)?[\s:=,()\-]*(?P<suffix>[A-Za-z]{3})(?![A-Za-z0-9_])"
    r")"
)


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return None
    return stamp.astimezone(timezone.utc)


def iso(stamp: datetime) -> str:
    return stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def funding_authority(user: Mapping[str, Any], association: Any) -> bool:
    """Return whether one actor may authorize sponsor/amount/acceptance evidence."""

    login = str(user.get("login") or "").lower()
    normalized_association = str(association or "").upper()
    return normalized_association in TRUSTED_ASSOCIATIONS or login in TRUSTED_SPONSOR_BOTS


def trusted_comment(
    comment: Mapping[str, Any], issue_author: str | None = None
) -> bool:
    """Return whether a comment is authoritative for funded-work qualification.

    ``issue_author`` is retained only for call/API compatibility; being the issue
    author does not grant funding authority.
    """

    del issue_author
    user = comment.get("user") if isinstance(comment.get("user"), Mapping) else {}
    return funding_authority(user, comment.get("author_association"))


def canonical_text(issue: Mapping[str, Any], comments: Sequence[Mapping[str, Any]]) -> str:
    """Return only sponsor/maintainer-authoritative funding/acceptance prose."""

    issue_user = issue.get("user") if isinstance(issue.get("user"), Mapping) else {}
    chunks: list[str] = []
    if funding_authority(issue_user, issue.get("author_association")):
        chunks.extend((str(issue.get("title") or ""), str(issue.get("body") or "")))
    chunks.extend(
        str(comment.get("body") or "")
        for comment in comments
        if trusted_comment(comment)
    )
    return "\n".join(chunks)


def descriptive_issue_text(issue: Mapping[str, Any]) -> str:
    """Return issue-authored descriptive text independent of funding authority."""

    return "\n".join((str(issue.get("title") or ""), str(issue.get("body") or "")))


def amount_supported(text: str, amount: str, currency: str) -> bool:
    """Require an exact numeric currency token, not a prefix of a larger amount."""

    target = Decimal(amount)
    number = r"(?<![\d.,])(?P<value>\d+(?:,\d{3})*(?:\.\d+)?)(?![\d.,])"
    symbols = {"USD": r"\$", "EUR": "€", "GBP": "£"}
    markers = [rf"\b{re.escape(currency)}\b"]
    if currency in symbols:
        markers.append(symbols[currency])
    for marker in markers:
        for pattern in (rf"{marker}\s*{number}", rf"{number}\s*{marker}"):
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                found = Decimal(match.group("value").replace(",", ""))
                if found == target:
                    return True
    return False


def _normalize_amount_token(value: str) -> str:
    amount = Decimal(value.replace(",", ""))
    normalized = format(amount, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def _normalized_adjacent_currency_code(value: str) -> str | None:
    """Return a plausible adjacent currency code without treating prose as one."""

    normalized = value.upper()
    if value.isupper() or normalized in _KNOWN_ISO_CURRENCY_CODES:
        return normalized
    return None


def _money_tokens(text: str) -> list[tuple[int, int, str, str]]:
    """Return positioned currency/amount tokens without assigning commercial meaning."""

    tokens: list[tuple[int, int, str, str]] = []
    for match in _MONEY_RE.finditer(text):
        if match.group("code") is not None:
            currency = _normalized_adjacent_currency_code(str(match.group("code")))
            value = str(match.group("code_value"))
        elif match.group("symbol") is not None:
            currency = _SYMBOL_CURRENCY[str(match.group("symbol"))]
            value = str(match.group("symbol_value"))
        else:
            currency = _normalized_adjacent_currency_code(
                str(match.group("suffix_code"))
            )
            value = str(match.group("suffix_value"))
        if currency is None:
            continue
        tokens.append((match.start(), match.end(), currency, _normalize_amount_token(value)))
    return tokens


def _direct_amount_link_supported(value: str) -> bool:
    """Accept mixed-case known codes in a direct-link bridge, but not prose."""

    def normalize_code(match: re.Match[str]) -> str:
        raw_code = str(match.group("code"))
        return _normalized_adjacent_currency_code(raw_code) or raw_code

    normalized = _DIRECT_AMOUNT_CODE_RE.sub(normalize_code, value)
    return bool(_DIRECT_AMOUNT_LINK_RE.fullmatch(normalized))


def _has_conflicting_symbol_code(text: str) -> bool:
    """Fail closed when a currency symbol and adjacent plausible code disagree."""

    for match in _SYMBOL_CODE_RE.finditer(text):
        if match.group("prefix") is not None:
            raw_code = str(match.group("prefix"))
            symbol = str(match.group("prefix_symbol"))
        else:
            raw_code = str(match.group("suffix"))
            symbol = str(match.group("suffix_symbol"))
        code = _normalized_adjacent_currency_code(raw_code)
        if code is None:
            continue
        if code != _SYMBOL_CURRENCY[symbol]:
            return True
    return False


def _commercial_amount_event(text: str) -> dict[str, str | None]:
    """Resolve one authority event's explicit reward/bounty/funding amount.

    Each line/semicolon clause is trimmed to its first commercial noun before
    monetary parsing. This prevents unrelated leading money from hiding a later
    reward transition while preserving fail-closed treatment of money after the
    commercial statement. Conflicting symbol/code notation is ambiguous. Multiple
    distinct amounts are ambiguous unless an exactly two-amount transition binds
    the second token as the destination.
    """

    event_values: list[tuple[str, str]] = []
    event_ambiguous = False
    for raw_segment in re.split(r"[\n;]+", text):
        raw_nouns = list(_COMMERCIAL_NOUN_RE.finditer(raw_segment))
        if not raw_nouns:
            continue
        segment = raw_segment[raw_nouns[0].start() :]
        if _has_conflicting_symbol_code(segment):
            event_ambiguous = True
            continue
        nouns = list(_COMMERCIAL_NOUN_RE.finditer(segment))
        monies = _money_tokens(segment)
        if not monies:
            if _UNRESOLVED_DIRECT_RE.search(segment) or _NONEXACT_AMOUNT_RE.search(
                segment
            ):
                event_ambiguous = True
            continue
        if len(monies) == 1 and _UNRESOLVED_AFTER_MONEY_RE.match(
            segment[monies[0][1] :]
        ):
            event_ambiguous = True
            continue

        first_noun = nouns[0].start()
        if len(monies) >= 2 and first_noun < monies[0][0]:
            before_source = segment[: monies[0][0]]
            between_first_second = segment[monies[0][1] : monies[1][0]]
            after_first = segment[monies[0][1] :]
            broad_from_to = bool(_FROM_TO_RE.search(segment))
            broad_now = bool(_CURRENT_TRANSITION_RE.search(after_first))
            if broad_from_to or broad_now:
                from_to_destination = bool(
                    broad_from_to
                    and _CHANGE_FROM_PREFIX_RE.search(before_source)
                    and _TO_DESTINATION_RE.fullmatch(between_first_second)
                )
                now_destination = bool(
                    broad_now and _NOW_DESTINATION_RE.fullmatch(between_first_second)
                )
                if len(monies) == 2 and (from_to_destination or now_destination):
                    event_values.append((monies[1][2], monies[1][3]))
                else:
                    event_ambiguous = True
                continue

        direct_values: list[tuple[str, str]] = []
        for start, end, currency, amount in monies:
            prior = [noun for noun in nouns if noun.end() <= start]
            if prior:
                noun = prior[-1]
                between = segment[noun.end() : start]
                if len(between) <= 80 and _direct_amount_link_supported(between):
                    direct_values.append((currency, amount))
                    continue
            if _REVERSE_AMOUNT_LINK_RE.match(segment[end:]):
                direct_values.append((currency, amount))

        unique_direct: list[tuple[str, str]] = []
        for value in direct_values:
            if value not in unique_direct:
                unique_direct.append(value)
        if not unique_direct:
            if len(monies) > 1 or _NONEXACT_AMOUNT_RE.search(segment):
                event_ambiguous = True
            continue

        all_unique: list[tuple[str, str]] = []
        for _, _, currency, amount in monies:
            value = (currency, amount)
            if value not in all_unique:
                all_unique.append(value)
        if len(all_unique) > 1 or len(unique_direct) > 1:
            event_ambiguous = True
        else:
            event_values.append(unique_direct[0])

    unique_values: list[tuple[str, str]] = []
    for value in event_values:
        if value not in unique_values:
            unique_values.append(value)
    if event_ambiguous or len(unique_values) > 1:
        return {"status": "ambiguous", "currency": None, "amount": None}
    if len(unique_values) == 1:
        return {
            "status": "resolved",
            "currency": unique_values[0][0],
            "amount": unique_values[0][1],
        }
    return {"status": "none", "currency": None, "amount": None}


def _trusted_comment_events(
    comments: Sequence[Mapping[str, Any]],
) -> list[tuple[datetime, int, str]]:
    """Return trusted comment prose in deterministic authority chronology."""

    far_future = datetime.max.replace(tzinfo=timezone.utc)
    events: list[tuple[datetime, int, str]] = []
    for index, comment in enumerate(comments):
        if not trusted_comment(comment):
            continue
        stamp = (
            parse_timestamp(comment.get("updated_at"))
            or parse_timestamp(comment.get("created_at"))
            or far_future
        )
        events.append((stamp, index, str(comment.get("body") or "")))
    return sorted(events, key=lambda row: (row[0], row[1]))


def authoritative_amount_state(
    issue: Mapping[str, Any],
    comments: Sequence[Mapping[str, Any]],
    advertised_amount: str,
    advertised_currency: str,
) -> dict[str, str | bool | None]:
    """Resolve the latest trusted commercial amount and compare it to the candidate."""

    status = "missing"
    current_currency: str | None = None
    current_amount: str | None = None

    issue_user = issue.get("user") if isinstance(issue.get("user"), Mapping) else {}
    if funding_authority(issue_user, issue.get("author_association")):
        issue_text = "\n".join(
            (str(issue.get("title") or ""), str(issue.get("body") or ""))
        )
        event = _commercial_amount_event(issue_text)
        if event["status"] != "none":
            status = str(event["status"])
            current_currency = event["currency"]
            current_amount = event["amount"]

    for _, _, text in _trusted_comment_events(comments):
        event = _commercial_amount_event(text)
        if event["status"] == "none":
            continue
        status = str(event["status"])
        current_currency = event["currency"]
        current_amount = event["amount"]

    matches = (
        status == "resolved"
        and current_currency == advertised_currency
        and current_amount is not None
        and Decimal(current_amount) == Decimal(advertised_amount)
    )
    return {
        "status": status,
        "currency": current_currency,
        "amount": current_amount,
        "matches_advertised": matches,
    }


def _funding_directive(text: str) -> str | None:
    """Return the last explicit commercial-state directive in one authority event."""

    directives = [
        *((match.start(), "withdrawn") for match in FUNDING_WITHDRAWAL_RE.finditer(text)),
        *((match.start(), "restored") for match in FUNDING_RESTORATION_RE.finditer(text)),
    ]
    return max(directives, default=(0, None), key=lambda row: row[0])[1]


def authoritative_funding_state(
    issue: Mapping[str, Any],
    comments: Sequence[Mapping[str, Any]],
    amount: str,
    currency: str,
) -> str:
    """Resolve explicit funding withdrawal/restoration in authority-event order.

    Positive evidence remains cumulative for normal qualification, but an explicit
    trusted withdrawal blocks it. A later restoration can clear that block only
    when the same restoration event restates sponsor, exact amount, and acceptance
    evidence, preventing stale pre-withdrawal terms from silently reactivating.
    """

    state = "not_withdrawn"

    issue_user = issue.get("user") if isinstance(issue.get("user"), Mapping) else {}
    if funding_authority(issue_user, issue.get("author_association")):
        issue_text = "\n".join(
            (str(issue.get("title") or ""), str(issue.get("body") or ""))
        )
        directive = _funding_directive(issue_text)
        if directive == "withdrawn":
            state = "withdrawn"
        elif directive == "restored" and state == "withdrawn":
            if (
                SPONSOR_RE.search(issue_text)
                and amount_supported(issue_text, amount, currency)
                and ACCEPTANCE_RE.search(issue_text)
            ):
                state = "not_withdrawn"

    for _, _, text in _trusted_comment_events(comments):
        directive = _funding_directive(text)
        if directive == "withdrawn":
            state = "withdrawn"
        elif directive == "restored" and state == "withdrawn":
            if (
                SPONSOR_RE.search(text)
                and amount_supported(text, amount, currency)
                and ACCEPTANCE_RE.search(text)
            ):
                state = "not_withdrawn"

    return state


def visible_claimants(comments: Sequence[Mapping[str, Any]]) -> list[str]:
    claimants: set[str] = set()
    for comment in comments:
        if not STRICT_CLAIM_RE.search(str(comment.get("body") or "")):
            continue
        user = comment.get("user") if isinstance(comment.get("user"), Mapping) else {}
        claimants.add(str(user.get("login") or "unknown"))
    return sorted(claimants)


def active_competing_prs(timeline: Sequence[Mapping[str, Any]]) -> list[str]:
    urls: set[str] = set()
    for event in timeline:
        if event.get("event") != "cross-referenced":
            continue
        source = event.get("source") if isinstance(event.get("source"), Mapping) else {}
        issue = source.get("issue") if isinstance(source.get("issue"), Mapping) else {}
        if not isinstance(issue.get("pull_request"), Mapping):
            continue
        if str(issue.get("state") or "").lower() != "open":
            continue
        url = issue.get("html_url")
        if isinstance(url, str) and GITHUB_ITEM_RE.fullmatch(url):
            urls.add(validate_github_item_url(url))
    return sorted(urls)


def last_activity(
    issue: Mapping[str, Any], comments: Sequence[Mapping[str, Any]]
) -> datetime | None:
    """Return the newest timestamp allowed to refresh funded-work freshness.

    GitHub issue ``updated_at`` is intentionally excluded: arbitrary comments can
    advance it even when the sponsor or maintainer has done nothing. The immutable
    issue creation time is the baseline. After creation, only comments from actors
    already trusted for funding evidence may refresh the clock. Untrusted comments
    remain available to claim/occupancy and security checks elsewhere in the gate.
    """

    stamps = [parse_timestamp(issue.get("created_at"))]
    for comment in comments:
        if not trusted_comment(comment):
            continue
        stamps.extend(
            (parse_timestamp(comment.get("updated_at")), parse_timestamp(comment.get("created_at")))
        )
    real = [stamp for stamp in stamps if stamp is not None]
    return max(real) if real else None
