"""Deterministic, evidence-bound revenue opportunity portfolio compiler."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any

SCHEMA = "commons-opportunity-portfolio/v1"
RECEIPT_SCHEMA = "commons-opportunity-portfolio-receipt/v1"
MAX_OPPORTUNITIES = 64
MAX_EXACT_CANDIDATES = 26
MAX_CAPACITY_BUCKETS = 12
MAX_TEXT = 512

_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_CURRENCY = re.compile(r"^[A-Z][A-Z0-9]{1,11}$")
_BUCKET = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_ALLOWED_OWNER = {"AVAILABLE", "OWNED_BY_THIS_SEAT", "OWNED_BY_OTHER", "UNKNOWN"}
_ALLOWED_ELIGIBILITY = {"ELIGIBLE", "UNKNOWN", "INELIGIBLE"}


class PortfolioError(ValueError):
    """Fail-closed input or verification error."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(value: Any) -> str:
    return sha256(_canonical(value)).hexdigest()


def _require_dict(value: Any, field: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise PortfolioError(f"{field}: expected object")
    return value


def _require_list(value: Any, field: str) -> list[Any]:
    if type(value) is not list:
        raise PortfolioError(f"{field}: expected array")
    return value


def _require_str(value: Any, field: str, *, pattern: re.Pattern[str] | None = None) -> str:
    if type(value) is not str or not value or len(value) > MAX_TEXT:
        raise PortfolioError(f"{field}: expected non-empty bounded string")
    if pattern is not None and not pattern.fullmatch(value):
        raise PortfolioError(f"{field}: invalid value")
    return value


def _require_int(value: Any, field: str, *, minimum: int = 0, maximum: int = 10**36) -> int:
    if type(value) is not int or not (minimum <= value <= maximum):
        raise PortfolioError(f"{field}: expected integer in [{minimum}, {maximum}]")
    return value


def _parse_utc(value: Any, field: str) -> datetime:
    text = _require_str(value, field)
    if not text.endswith("Z"):
        raise PortfolioError(f"{field}: must be UTC RFC3339 ending in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise PortfolioError(f"{field}: invalid RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise PortfolioError(f"{field}: must be UTC")
    if parsed.microsecond:
        raise PortfolioError(f"{field}: fractional seconds are not allowed")
    return parsed


def _fmt_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _scan_secret_shaped(value: Any, field: str = "$") -> None:
    if type(value) is str:
        for pattern in _SECRET_PATTERNS:
            if pattern.search(value):
                raise PortfolioError(f"{field}: secret-shaped material refused")
    elif type(value) is list:
        for index, item in enumerate(value):
            _scan_secret_shaped(item, f"{field}[{index}]")
    elif type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise PortfolioError(f"{field}: object keys must be strings")
            _scan_secret_shaped(item, f"{field}.{key}")


def _normalize_digest(value: Any, field: str) -> str:
    text = _require_str(value, field)
    if not _SHA256.fullmatch(text):
        raise PortfolioError(f"{field}: expected lowercase sha256 hex")
    return text


def _normalize_capacity(value: Any, field: str) -> dict[str, int]:
    raw = _require_dict(value, field)
    if len(raw) > MAX_CAPACITY_BUCKETS:
        raise PortfolioError(f"{field}: too many capacity buckets")
    out: dict[str, int] = {}
    for name, amount in raw.items():
        _require_str(name, f"{field}.bucket", pattern=_BUCKET)
        out[name] = _require_int(amount, f"{field}.{name}", maximum=10**9)
    return dict(sorted(out.items()))


def _normalize_source(raw: Any, field: str) -> dict[str, Any]:
    source = _require_dict(raw, field)
    unknown = set(source) - {"ref", "digestSha256", "observedAt"}
    if unknown:
        raise PortfolioError(f"{field}: unknown fields {sorted(unknown)}")
    ref = _require_str(source.get("ref"), f"{field}.ref")
    digest = _normalize_digest(source.get("digestSha256"), f"{field}.digestSha256")
    observed = _parse_utc(source.get("observedAt"), f"{field}.observedAt")
    return {"ref": ref, "digestSha256": digest, "observedAt": _fmt_utc(observed)}


def _normalize_blockers(raw: Any, field: str) -> list[dict[str, Any]]:
    blockers = _require_list(raw, field)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(blockers):
        b = _require_dict(item, f"{field}[{index}]")
        unknown = set(b) - {"code", "status", "evidenceSha256"}
        if unknown:
            raise PortfolioError(f"{field}[{index}]: unknown fields {sorted(unknown)}")
        code = _require_str(b.get("code"), f"{field}[{index}].code", pattern=_ID)
        if code in seen:
            raise PortfolioError(f"{field}: duplicate blocker code {code}")
        seen.add(code)
        status = _require_str(b.get("status"), f"{field}[{index}].status")
        if status not in {"OPEN", "RESOLVED"}:
            raise PortfolioError(f"{field}[{index}].status: expected OPEN or RESOLVED")
        evidence = _normalize_digest(b.get("evidenceSha256"), f"{field}[{index}].evidenceSha256")
        out.append({"code": code, "status": status, "evidenceSha256": evidence})
    return sorted(out, key=lambda x: x["code"])


def _normalize_opportunity(raw: Any, index: int, actor_seat: str) -> dict[str, Any]:
    field = f"opportunities[{index}]"
    item = _require_dict(raw, field)
    allowed = {
        "id", "title", "source", "freshUntil", "deadline", "eligibility", "value",
        "capacity", "owner", "blockers", "dependsOn", "exclusiveGroup", "labels",
    }
    unknown = set(item) - allowed
    if unknown:
        raise PortfolioError(f"{field}: unknown fields {sorted(unknown)}")

    oid = _require_str(item.get("id"), f"{field}.id", pattern=_ID)
    title = _require_str(item.get("title"), f"{field}.title")
    source = _normalize_source(item.get("source"), f"{field}.source")
    fresh_until = _parse_utc(item.get("freshUntil"), f"{field}.freshUntil")
    deadline = _parse_utc(item.get("deadline"), f"{field}.deadline")

    eligibility_raw = _require_dict(item.get("eligibility"), f"{field}.eligibility")
    if set(eligibility_raw) - {"status", "evidenceSha256"}:
        raise PortfolioError(f"{field}.eligibility: unknown fields")
    eligibility_status = _require_str(eligibility_raw.get("status"), f"{field}.eligibility.status")
    if eligibility_status not in _ALLOWED_ELIGIBILITY:
        raise PortfolioError(f"{field}.eligibility.status: invalid")
    eligibility = {
        "status": eligibility_status,
        "evidenceSha256": _normalize_digest(eligibility_raw.get("evidenceSha256"), f"{field}.eligibility.evidenceSha256"),
    }

    value_raw = _require_dict(item.get("value"), f"{field}.value")
    if set(value_raw) - {"currency", "amountMinor", "probabilityBps", "probabilityEvidenceSha256"}:
        raise PortfolioError(f"{field}.value: unknown fields")
    currency = _require_str(value_raw.get("currency"), f"{field}.value.currency", pattern=_CURRENCY)
    amount = _require_int(value_raw.get("amountMinor"), f"{field}.value.amountMinor", minimum=1)
    probability = value_raw.get("probabilityBps")
    probability_digest = value_raw.get("probabilityEvidenceSha256")
    if probability is None and probability_digest is None:
        normalized_probability = None
        normalized_probability_digest = None
    elif probability is None or probability_digest is None:
        raise PortfolioError(f"{field}.value: probability and evidence must appear together")
    else:
        normalized_probability = _require_int(probability, f"{field}.value.probabilityBps", minimum=1, maximum=10000)
        normalized_probability_digest = _normalize_digest(probability_digest, f"{field}.value.probabilityEvidenceSha256")
    value = {
        "currency": currency,
        "amountMinor": amount,
        "probabilityBps": normalized_probability,
        "probabilityEvidenceSha256": normalized_probability_digest,
    }

    capacity = _normalize_capacity(item.get("capacity"), f"{field}.capacity")
    owner_raw = _require_dict(item.get("owner"), f"{field}.owner")
    if set(owner_raw) - {"status", "seat"}:
        raise PortfolioError(f"{field}.owner: unknown fields")
    owner_status = _require_str(owner_raw.get("status"), f"{field}.owner.status")
    if owner_status not in _ALLOWED_OWNER:
        raise PortfolioError(f"{field}.owner.status: invalid")
    seat = owner_raw.get("seat")
    if seat is not None:
        seat = _require_str(seat, f"{field}.owner.seat", pattern=_ID)
    if owner_status == "OWNED_BY_THIS_SEAT" and seat != actor_seat:
        raise PortfolioError(f"{field}.owner: OWNED_BY_THIS_SEAT must name actorSeat")
    if owner_status == "OWNED_BY_OTHER" and (seat is None or seat == actor_seat):
        raise PortfolioError(f"{field}.owner: OWNED_BY_OTHER must name another seat")
    if owner_status in {"AVAILABLE", "UNKNOWN"} and seat is not None:
        raise PortfolioError(f"{field}.owner: seat must be null for {owner_status}")
    owner = {"status": owner_status, "seat": seat}

    blockers = _normalize_blockers(item.get("blockers"), f"{field}.blockers")
    depends = _require_list(item.get("dependsOn"), f"{field}.dependsOn")
    normalized_depends = [_require_str(dep, f"{field}.dependsOn[{i}]", pattern=_ID) for i, dep in enumerate(depends)]
    if len(set(normalized_depends)) != len(normalized_depends):
        raise PortfolioError(f"{field}.dependsOn: duplicates")
    if oid in normalized_depends:
        raise PortfolioError(f"{field}.dependsOn: self dependency")

    exclusive = item.get("exclusiveGroup")
    if exclusive is not None:
        exclusive = _require_str(exclusive, f"{field}.exclusiveGroup", pattern=_ID)
    labels = _require_list(item.get("labels", []), f"{field}.labels")
    normalized_labels = [_require_str(label, f"{field}.labels[{i}]", pattern=_ID) for i, label in enumerate(labels)]
    if len(set(normalized_labels)) != len(normalized_labels):
        raise PortfolioError(f"{field}.labels: duplicates")

    return {
        "id": oid, "title": title, "source": source,
        "freshUntil": _fmt_utc(fresh_until), "deadline": _fmt_utc(deadline),
        "eligibility": eligibility, "value": value, "capacity": capacity, "owner": owner,
        "blockers": blockers, "dependsOn": sorted(normalized_depends),
        "exclusiveGroup": exclusive, "labels": sorted(normalized_labels),
    }


def normalize_input(payload: Any) -> dict[str, Any]:
    """Validate and canonicalize an opportunity portfolio request."""
    _scan_secret_shaped(payload)
    root = _require_dict(payload, "$")
    allowed = {"schema", "actorSeat", "capacities", "currencyPriority", "opportunities"}
    unknown = set(root) - allowed
    if unknown:
        raise PortfolioError(f"$: unknown fields {sorted(unknown)}")
    if root.get("schema") != SCHEMA:
        raise PortfolioError(f"schema: expected {SCHEMA}")
    actor_seat = _require_str(root.get("actorSeat"), "actorSeat", pattern=_ID)
    capacities = _normalize_capacity(root.get("capacities"), "capacities")

    priority_raw = _require_list(root.get("currencyPriority", []), "currencyPriority")
    priority = [_require_str(currency, f"currencyPriority[{i}]", pattern=_CURRENCY) for i, currency in enumerate(priority_raw)]
    if len(set(priority)) != len(priority):
        raise PortfolioError("currencyPriority: duplicates")

    items = _require_list(root.get("opportunities"), "opportunities")
    if not (1 <= len(items) <= MAX_OPPORTUNITIES):
        raise PortfolioError(f"opportunities: expected 1..{MAX_OPPORTUNITIES}")
    normalized = [_normalize_opportunity(item, index, actor_seat) for index, item in enumerate(items)]
    ids = [item["id"] for item in normalized]
    if len(set(ids)) != len(ids):
        raise PortfolioError("opportunities: duplicate id")

    known = set(ids)
    for item in normalized:
        unknown_deps = set(item["dependsOn"]) - known
        if unknown_deps:
            raise PortfolioError(f"{item['id']}: unknown dependencies {sorted(unknown_deps)}")

    graph = {item["id"]: item["dependsOn"] for item in normalized}
    visiting: set[str] = set()
    visited: set[str] = set()
    def walk(node: str) -> None:
        if node in visiting:
            raise PortfolioError("opportunities: dependency cycle")
        if node in visited:
            return
        visiting.add(node)
        for dep in graph[node]:
            walk(dep)
        visiting.remove(node)
        visited.add(node)
    for node in sorted(graph):
        walk(node)

    return {
        "schema": SCHEMA, "actorSeat": actor_seat, "capacities": capacities,
        "currencyPriority": priority,
        "opportunities": sorted(normalized, key=lambda x: x["id"]),
    }


def _gating_reason(item: dict[str, Any], *, trusted_as_of: datetime, capacities: dict[str, int]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    observed = _parse_utc(item["source"]["observedAt"], f"{item['id']}.source.observedAt")
    fresh_until = _parse_utc(item["freshUntil"], f"{item['id']}.freshUntil")
    deadline = _parse_utc(item["deadline"], f"{item['id']}.deadline")
    if observed > trusted_as_of:
        reasons.append("SOURCE_OBSERVED_IN_FUTURE")
    if fresh_until < observed:
        reasons.append("SOURCE_FRESHNESS_INVERTED")
    if trusted_as_of > fresh_until:
        reasons.append("SOURCE_STALE")
    if trusted_as_of >= deadline:
        reasons.append("DEADLINE_CLOSED")
    if item["eligibility"]["status"] == "INELIGIBLE":
        reasons.append("INELIGIBLE")
    elif item["eligibility"]["status"] == "UNKNOWN":
        reasons.append("ELIGIBILITY_UNKNOWN")
    owner = item["owner"]["status"]
    if owner == "OWNED_BY_OTHER":
        reasons.append("OWNER_COLLISION")
    elif owner == "UNKNOWN":
        reasons.append("OWNER_UNKNOWN")
    reasons.extend(f"BLOCKER:{b['code']}" for b in item["blockers"] if b["status"] == "OPEN")
    for bucket, required in item["capacity"].items():
        if bucket not in capacities:
            reasons.append(f"CAPACITY_BUCKET_UNKNOWN:{bucket}")
        elif required > capacities[bucket]:
            reasons.append(f"INDIVIDUAL_CAPACITY_EXCEEDS:{bucket}")
    if item["value"]["probabilityBps"] is None:
        reasons.append("PROBABILITY_EVIDENCE_MISSING")

    hard_hold = {"INELIGIBLE", "SOURCE_OBSERVED_IN_FUTURE", "SOURCE_FRESHNESS_INVERTED", "DEADLINE_CLOSED", "OWNER_COLLISION"}
    if any(reason in hard_hold for reason in reasons):
        return "HOLD", sorted(reasons)
    if any(reason.startswith("BLOCKER:") or reason.startswith("INDIVIDUAL_CAPACITY_EXCEEDS:") for reason in reasons):
        return "BLOCKED", sorted(reasons)
    if reasons:
        return "QUALIFY", sorted(reasons)
    return "RUNNABLE", []


@dataclass(frozen=True)
class _Candidate:
    item: dict[str, Any]
    expected: int
    face: int


def _select_exact(candidates: list[_Candidate], capacities: dict[str, int], currency_priority: list[str]) -> tuple[list[str], dict[str, int], dict[str, int]]:
    if len(candidates) > MAX_EXACT_CANDIDATES:
        raise PortfolioError(f"exact optimizer limit exceeded: {len(candidates)} > {MAX_EXACT_CANDIDATES}")
    rank = {currency: index for index, currency in enumerate(currency_priority)}
    candidates = sorted(candidates, key=lambda c: (rank[c.item["value"]["currency"]], -c.expected, c.item["deadline"], c.item["id"]))
    n = len(candidates)
    suffix_expected = [[0] * len(currency_priority) for _ in range(n + 1)]
    suffix_face = [[0] * len(currency_priority) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        suffix_expected[i] = suffix_expected[i + 1].copy()
        suffix_face[i] = suffix_face[i + 1].copy()
        currency_index = rank[candidates[i].item["value"]["currency"]]
        suffix_expected[i][currency_index] += candidates[i].expected
        suffix_face[i][currency_index] += candidates[i].face

    best_score: tuple[int, ...] | None = None
    best_ids: tuple[str, ...] | None = None
    best_expected = {c: 0 for c in currency_priority}
    best_face = {c: 0 for c in currency_priority}
    selected: set[str] = set()
    used = {bucket: 0 for bucket in capacities}
    groups: set[str] = set()
    expected = {c: 0 for c in currency_priority}
    face = {c: 0 for c in currency_priority}
    candidate_ids = {c.item["id"] for c in candidates}
    by_id = {c.item["id"]: c for c in candidates}

    def score_tuple() -> tuple[int, ...]:
        # All expected-value coordinates dominate all face-value tie-breakers. This
        # preserves the explicit currency priority without letting a face-value tie
        # break in one currency suppress expected value in a lower-priority currency.
        return tuple(expected[c] for c in currency_priority) + tuple(face[c] for c in currency_priority)

    def upper_tuple(i: int) -> tuple[int, ...]:
        expected_upper = tuple(expected[c] + suffix_expected[i][idx] for idx, c in enumerate(currency_priority))
        face_upper = tuple(face[c] + suffix_face[i][idx] for idx, c in enumerate(currency_priority))
        return expected_upper + face_upper

    def deps_possible(i: int) -> bool:
        remaining = {candidates[j].item["id"] for j in range(i, n)}
        return all(dep in selected or dep in remaining for oid in selected for dep in by_id[oid].item["dependsOn"] if dep in candidate_ids)

    def dfs(i: int) -> None:
        nonlocal best_score, best_ids, best_expected, best_face
        if best_score is not None and upper_tuple(i) < best_score:
            return
        if not deps_possible(i):
            return
        if i == n:
            for oid in selected:
                if any(dep in candidate_ids and dep not in selected for dep in by_id[oid].item["dependsOn"]):
                    return
            score = score_tuple()
            ids = tuple(sorted(selected))
            if best_score is None or score > best_score or (score == best_score and (best_ids is None or ids < best_ids)):
                best_score, best_ids = score, ids
                best_expected, best_face = dict(expected), dict(face)
            return

        c = candidates[i]
        item = c.item
        currency = item["value"]["currency"]
        group = item["exclusiveGroup"]
        can_include = group is None or group not in groups
        if can_include:
            for bucket, amount in item["capacity"].items():
                if used[bucket] + amount > capacities[bucket]:
                    can_include = False
                    break
        if can_include:
            selected.add(item["id"])
            if group is not None:
                groups.add(group)
            for bucket, amount in item["capacity"].items():
                used[bucket] += amount
            expected[currency] += c.expected
            face[currency] += c.face
            dfs(i + 1)
            face[currency] -= c.face
            expected[currency] -= c.expected
            for bucket, amount in item["capacity"].items():
                used[bucket] -= amount
            if group is not None:
                groups.remove(group)
            selected.remove(item["id"])
        dfs(i + 1)

    dfs(0)
    return list(best_ids or ()), best_expected, best_face


def compile_portfolio(payload: Any, *, trusted_as_of: str) -> dict[str, Any]:
    """Compile a deterministic portfolio using an out-of-band trusted evaluation instant."""
    normalized = normalize_input(payload)
    as_of = _parse_utc(trusted_as_of, "trusted_as_of")
    priority = list(normalized["currencyPriority"])
    currencies = sorted({item["value"]["currency"] for item in normalized["opportunities"]})
    global_holds: list[str] = []
    if not priority:
        if len(currencies) == 1:
            priority = currencies
        else:
            global_holds.append("MULTI_CURRENCY_PRIORITY_REQUIRED")
    elif set(priority) != set(currencies):
        global_holds.append("CURRENCY_PRIORITY_MUST_COVER_EXACT_CURRENCIES")

    decisions: dict[str, dict[str, Any]] = {}
    runnable: list[_Candidate] = []
    for item in normalized["opportunities"]:
        status, reasons = _gating_reason(item, trusted_as_of=as_of, capacities=normalized["capacities"])
        decisions[item["id"]] = {"status": status, "reasons": reasons}
        if status == "RUNNABLE":
            p = item["value"]["probabilityBps"]
            assert type(p) is int
            runnable.append(_Candidate(item=item, expected=item["value"]["amountMinor"] * p, face=item["value"]["amountMinor"]))

    runnable_ids = {c.item["id"] for c in runnable}
    changed = True
    while changed:
        changed = False
        for c in list(runnable):
            missing = [dep for dep in c.item["dependsOn"] if dep not in runnable_ids]
            if missing:
                decisions[c.item["id"]] = {"status": "BLOCKED", "reasons": [f"DEPENDENCY_NOT_RUNNABLE:{dep}" for dep in sorted(missing)]}
                runnable.remove(c)
                runnable_ids.remove(c.item["id"])
                changed = True

    selected: list[str] = []
    expected_totals = {c: 0 for c in priority}
    face_totals = {c: 0 for c in priority}
    if not global_holds:
        if len(runnable) > MAX_EXACT_CANDIDATES:
            global_holds.append(f"EXACT_OPTIMIZER_LIMIT:{len(runnable)}>{MAX_EXACT_CANDIDATES}")
        else:
            selected, expected_totals, face_totals = _select_exact(runnable, normalized["capacities"], priority)

    selected_set = set(selected)
    if global_holds:
        for c in runnable:
            decisions[c.item["id"]] = {"status": "HOLD", "reasons": list(global_holds)}
    else:
        for c in runnable:
            decisions[c.item["id"]] = {
                "status": "EXECUTE_NOW" if c.item["id"] in selected_set else "READY_NOT_SELECTED",
                "reasons": [] if c.item["id"] in selected_set else ["PORTFOLIO_CONSTRAINT_OR_LOWER_OBJECTIVE"],
            }

    used_capacity = {bucket: 0 for bucket in normalized["capacities"]}
    for c in runnable:
        if c.item["id"] in selected_set:
            for bucket, amount in c.item["capacity"].items():
                used_capacity[bucket] += amount

    decision_rows = [{"id": item["id"], "status": decisions[item["id"]]["status"], "reasons": decisions[item["id"]]["reasons"]} for item in normalized["opportunities"]]
    authority = {
        "externalActionsAuthorized": False,
        "outreachAuthorized": False,
        "submissionAuthorized": False,
        "spendAuthorized": False,
        "contractAuthorized": False,
        "paymentAuthorized": False,
        "revenueRecognized": False,
        "strongestState": "HOLD" if global_holds else "PORTFOLIO_READY_FOR_HUMAN_EXECUTION_REVIEW",
    }
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "trustedAsOf": _fmt_utc(as_of),
        "inputDigestSha256": _digest(normalized),
        "normalizedInput": normalized,
        "currencyPriorityApplied": priority,
        "globalHolds": global_holds,
        "portfolio": selected,
        "objective": {currency: {"expectedValueNumerator": expected_totals.get(currency, 0), "expectedValueDenominator": 10000, "faceAmountMinor": face_totals.get(currency, 0)} for currency in priority},
        "capacity": {
            "available": normalized["capacities"],
            "used": used_capacity,
            "remaining": {bucket: normalized["capacities"][bucket] - used_capacity[bucket] for bucket in normalized["capacities"]},
        },
        "decisions": decision_rows,
        "authority": authority,
    }
    receipt["receiptDigestSha256"] = _digest(receipt)
    return receipt


def verify_receipt(receipt: Any) -> bool:
    """Independently recompile and compare a receipt; raises on tamper or semantic drift."""
    _scan_secret_shaped(receipt)
    if type(receipt) is not dict or receipt.get("schema") != RECEIPT_SCHEMA:
        raise PortfolioError("receipt: wrong schema")
    claimed = receipt.get("receiptDigestSha256")
    if type(claimed) is not str or not _SHA256.fullmatch(claimed):
        raise PortfolioError("receipt: invalid receipt digest")
    unsigned = dict(receipt)
    unsigned.pop("receiptDigestSha256", None)
    if _digest(unsigned) != claimed:
        raise PortfolioError("receipt: digest mismatch")
    normalized = receipt.get("normalizedInput")
    if _digest(normalized) != receipt.get("inputDigestSha256"):
        raise PortfolioError("receipt: input digest mismatch")
    recomputed = compile_portfolio(normalized, trusted_as_of=receipt.get("trustedAsOf"))
    if _canonical(recomputed) != _canonical(receipt):
        raise PortfolioError("receipt: deterministic recompilation mismatch")
    return True


def render_markdown(receipt: dict[str, Any]) -> str:
    """Render an operator-facing summary without granting external authority."""
    verify_receipt(receipt)
    lines = [
        "# Revenue Opportunity Portfolio", "",
        f"- Trusted as-of: `{receipt['trustedAsOf']}`",
        f"- State: `{receipt['authority']['strongestState']}`",
        f"- Receipt: `{receipt['receiptDigestSha256']}`",
        "- External action authority: **false**", "", "## Execute now",
    ]
    if receipt["portfolio"]:
        by_id = {x["id"]: x for x in receipt["normalizedInput"]["opportunities"]}
        for oid in receipt["portfolio"]:
            item = by_id[oid]
            lines.append(f"- `{oid}` — {item['title']} — {item['value']['amountMinor']} {item['value']['currency']} minor units")
    else:
        lines.append("- None")
    lines += ["", "## Decisions"]
    for row in receipt["decisions"]:
        suffix = f" — {', '.join(row['reasons'])}" if row["reasons"] else ""
        lines.append(f"- `{row['id']}`: **{row['status']}**{suffix}")
    lines += ["", "## Authority boundary", "This artifact is a deterministic prioritization receipt only. It does not send outreach, submit bids, spend funds, sign contracts, execute payments, schedule provider work, or recognize revenue."]
    return "\n".join(lines) + "\n"
