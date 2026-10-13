from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping

from .schema import (
    ANSWER_STATUSES, CURRENCY_RE, EVIDENCE_KINDS, PRICING_MODELS, PRICING_OPTIONS,
    QUESTION_BY_ID, RFIError, source_binding,
)

def _obj(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RFIError(f"{where} must be an object")
    return value


def _arr(value: Any, where: str, *, max_items: int) -> list[Any]:
    if not isinstance(value, list) or len(value) > max_items:
        raise RFIError(f"{where} must be an array of <= {max_items} items")
    return value


def _exact_keys(obj: Mapping[str, Any], expected: set[str], where: str) -> None:
    actual = set(obj)
    if actual != expected:
        raise RFIError(f"{where} keys mismatch; missing={sorted(expected-actual)} extra={sorted(actual-expected)}")


def _text(value: Any, where: str, *, max_len: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise RFIError(f"{where} must be text")
    if not allow_empty and not value.strip():
        raise RFIError(f"{where} must be non-empty text")
    if len(value) > max_len or "\x00" in value:
        raise RFIError(f"{where} exceeds length limit or contains NUL")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise RFIError(f"{where} must be Unicode scalar text") from None
    return value.strip() if value.strip() else ""


def _integer(value: Any, where: str, *, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RFIError(f"{where} must be an integer")
    if value < low or value > high:
        raise RFIError(f"{where} out of range [{low}, {high}]")
    return value


def _boolean(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise RFIError(f"{where} must be a boolean")
    return value


def _date(value: Any, where: str) -> str:
    text = _text(value, where, max_len=10)
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        raise RFIError(f"{where} must be YYYY-MM-DD") from None
    if parsed.isoformat() != text:
        raise RFIError(f"{where} must use canonical YYYY-MM-DD")
    return text


def _timestamp(value: Any, where: str) -> str:
    text = _text(value, where, max_len=64)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        raise RFIError(f"{where} must be ISO-8601") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RFIError(f"{where} must include an offset")
    return text


def _evidence_refs(value: Any, where: str, *, allowed_kinds: frozenset[str], require_any: bool) -> list[dict[str, str]]:
    items = _arr(value, where, max_items=64)
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for i, raw in enumerate(items):
        obj = _obj(raw, f"{where}[{i}]")
        _exact_keys(obj, {"kind", "ref"}, f"{where}[{i}]")
        kind = _text(obj["kind"], f"{where}[{i}].kind", max_len=16)
        if kind not in EVIDENCE_KINDS:
            raise RFIError(f"{where}[{i}].kind invalid")
        if kind not in allowed_kinds:
            raise RFIError(f"{where}[{i}] evidence kind {kind} is not admissible for this question")
        ref = _text(obj["ref"], f"{where}[{i}].ref", max_len=512)
        key = (kind, ref.casefold())
        if key in seen:
            raise RFIError(f"{where} contains duplicate evidence")
        seen.add(key)
        out.append({"kind": kind, "ref": ref})
    if require_any and not out:
        raise RFIError(f"{where} requires at least one admissible evidence reference")
    return out


def _validate_source(value: Any) -> dict[str, Any]:
    obj = _obj(value, "input.source")
    expected = source_binding()
    _exact_keys(obj, set(expected), "input.source")
    for key, expected_value in expected.items():
        if obj[key] != expected_value:
            raise RFIError(f"input.source.{key} does not match the retained buyer manifest")
    return dict(expected)


def _validate_answer(value: Any, where: str) -> dict[str, Any]:
    obj = _obj(value, where)
    _exact_keys(obj, {"question_id", "status", "answer", "evidence_refs"}, where)
    qid = _text(obj["question_id"], f"{where}.question_id", max_len=3)
    spec = QUESTION_BY_ID.get(qid)
    if spec is None:
        raise RFIError(f"{where}.question_id unknown: {qid}")
    status = _text(obj["status"], f"{where}.status", max_len=32)
    if status not in ANSWER_STATUSES:
        raise RFIError(f"{where}.status invalid")
    answer = _text(obj["answer"], f"{where}.answer", max_len=12000, allow_empty=True)
    if status == "OWNER_INPUT_REQUIRED":
        if answer:
            raise RFIError(f"{where}.answer must be empty when OWNER_INPUT_REQUIRED")
        evidence = _evidence_refs(obj["evidence_refs"], f"{where}.evidence_refs", allowed_kinds=spec["allowed_evidence_kinds"], require_any=False)
        if evidence:
            raise RFIError(f"{where}.evidence_refs must be empty when OWNER_INPUT_REQUIRED")
    else:
        if not answer:
            raise RFIError(f"{where}.answer must be non-empty when resolved")
        if status == "NOT_APPLICABLE" and not spec["allow_not_applicable"]:
            raise RFIError(f"{qid} may not be marked NOT_APPLICABLE")
        evidence = _evidence_refs(obj["evidence_refs"], f"{where}.evidence_refs", allowed_kinds=spec["allowed_evidence_kinds"], require_any=True)
    return {
        "question_id": qid,
        "section": spec["section"],
        "key": spec["key"],
        "status": status,
        "answer": answer,
        "evidence_refs": evidence,
    }


def _validate_assurances(value: Any) -> dict[str, bool]:
    obj = _obj(value, "input.assurances")
    expected = {"sensitive_information_screened", "claim_evidence_reviewed", "pricing_non_binding_ack"}
    _exact_keys(obj, expected, "input.assurances")
    return {key: _boolean(obj[key], f"input.assurances.{key}") for key in sorted(expected)}


def _pricing_evidence(value: Any, where: str) -> list[dict[str, str]]:
    return _evidence_refs(value, where, allowed_kinds=frozenset({"OWNER"}), require_any=True)


def _validate_pricing(value: Any) -> list[dict[str, Any]]:
    rows = _arr(value, "input.pricing_options", max_items=4)
    out: list[dict[str, Any]] = []
    seen_options: set[str] = set()
    currency_shape: tuple[str, int] | None = None
    for i, raw in enumerate(rows):
        where = f"input.pricing_options[{i}]"
        obj = _obj(raw, where)
        _exact_keys(obj, {"option", "currency", "decimals", "low_minor", "high_minor", "model", "assumptions", "evidence_refs"}, where)
        option = _text(obj["option"], f"{where}.option", max_len=48)
        if option not in PRICING_OPTIONS:
            raise RFIError(f"{where}.option invalid")
        if option in seen_options:
            raise RFIError(f"duplicate pricing option: {option}")
        seen_options.add(option)
        currency = _text(obj["currency"], f"{where}.currency", max_len=8)
        if not CURRENCY_RE.fullmatch(currency):
            raise RFIError(f"{where}.currency must be 2-8 uppercase letters/digits")
        decimals = _integer(obj["decimals"], f"{where}.decimals", low=0, high=8)
        shape = (currency, decimals)
        if currency_shape is None:
            currency_shape = shape
        elif currency_shape != shape:
            raise RFIError("pricing estimates must remain in one native currency/decimal convention; no FX conversion")
        low_minor = _integer(obj["low_minor"], f"{where}.low_minor", low=1, high=10**18)
        high_minor = _integer(obj["high_minor"], f"{where}.high_minor", low=1, high=10**18)
        if low_minor > high_minor:
            raise RFIError(f"{where}.low_minor cannot exceed high_minor")
        model = _text(obj["model"], f"{where}.model", max_len=32)
        if model not in PRICING_MODELS:
            raise RFIError(f"{where}.model invalid")
        assumptions_raw = _arr(obj["assumptions"], f"{where}.assumptions", max_items=32)
        assumptions: list[str] = []
        seen_assumptions: set[str] = set()
        for j, item in enumerate(assumptions_raw):
            text = _text(item, f"{where}.assumptions[{j}]", max_len=1000)
            key = text.casefold()
            if key in seen_assumptions:
                raise RFIError(f"{where}.assumptions contains duplicate item")
            seen_assumptions.add(key)
            assumptions.append(text)
        if not assumptions:
            raise RFIError(f"{where}.assumptions must not be empty")
        evidence = _pricing_evidence(obj["evidence_refs"], f"{where}.evidence_refs")
        out.append({
            "option": option,
            "currency": currency,
            "decimals": decimals,
            "low_minor": low_minor,
            "high_minor": high_minor,
            "model": model,
            "assumptions": assumptions,
            "evidence_refs": evidence,
            "binding": False,
        })
    return sorted(out, key=lambda row: row["option"])
