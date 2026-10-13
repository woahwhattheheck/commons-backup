"""Strict data, receipt, and quantity-custody primitives for QuantiPhy Main."""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence


SCHEMA = "quantiphy-main/v1"
RECEIPT_SCHEMA = "quantiphy-main-receipt/v1"
MANIFEST_SCHEMA = "quantiphy-main-manifest/v1"
CATEGORIES = ("S2", "D2", "S3", "D3")
THRESHOLDS = (0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95)
KEY_FIELDS = ("video_id", "question")
GROUND_TRUTH = "ground_truth_posterior"
MAX_SAFE_INT = 9_000_000_000_000_000
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
SAFE_UNIT = re.compile(r"^[A-Za-z%°][A-Za-z0-9%°^*/._-]{0,31}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
NUMBER_TOKEN = re.compile(r"(?<![A-Za-z0-9_.])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?(?![A-Za-z0-9_.])")


class QuantiPhyMainError(ValueError):
    pass


def _no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise QuantiPhyMainError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_json_loads(raw: str | bytes) -> Any:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise QuantiPhyMainError("JSON must be UTF-8") from exc
    try:
        return json.loads(
            raw,
            object_pairs_hook=_no_dupes,
            parse_constant=lambda token: (_ for _ in ()).throw(
                QuantiPhyMainError(f"nonfinite JSON number: {token}")
            ),
        )
    except QuantiPhyMainError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise QuantiPhyMainError(f"invalid JSON: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise QuantiPhyMainError(f"not canonical JSON: {exc}") from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def _obj(value: Any, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise QuantiPhyMainError(f"{where} must be an object")
    return value


def _list(value: Any, where: str, max_len: int = 100000) -> list[Any]:
    if type(value) is not list:
        raise QuantiPhyMainError(f"{where} must be an array")
    if len(value) > max_len:
        raise QuantiPhyMainError(f"{where} too large")
    return value


def _keys(obj: Mapping[str, Any], allowed: set[str], required: set[str], where: str) -> None:
    unknown = set(obj) - allowed
    missing = required - set(obj)
    if unknown:
        raise QuantiPhyMainError(f"{where} unknown keys: {sorted(unknown)}")
    if missing:
        raise QuantiPhyMainError(f"{where} missing keys: {sorted(missing)}")


def _int(value: Any, where: str, lo: int = 0, hi: int = MAX_SAFE_INT) -> int:
    if type(value) is not int:
        raise QuantiPhyMainError(f"{where} must be an integer")
    if not lo <= value <= hi:
        raise QuantiPhyMainError(f"{where} out of range")
    return value


def _sid(value: Any, where: str) -> str:
    if type(value) is not str or not SAFE_ID.fullmatch(value):
        raise QuantiPhyMainError(f"{where} invalid identifier")
    return value


def _hex(value: Any, where: str) -> str:
    if type(value) is not str or not HEX64.fullmatch(value):
        raise QuantiPhyMainError(f"{where} must be lowercase SHA-256 hex")
    return value


def _unit(value: Any, where: str) -> str:
    if type(value) is not str or not SAFE_UNIT.fullmatch(value):
        raise QuantiPhyMainError(f"{where} invalid unit")
    return value


def _decimal(value: Any, where: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, (str, int, Decimal)):
        raise QuantiPhyMainError(f"{where} must be canonical decimal text/integer, not float/bool")
    text = str(value)
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise QuantiPhyMainError(f"{where} invalid decimal") from exc
    if not result.is_finite():
        raise QuantiPhyMainError(f"{where} must be finite")
    if positive and result <= 0:
        raise QuantiPhyMainError(f"{where} must be positive")
    return result


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise QuantiPhyMainError("cannot serialize nonfinite decimal")
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal(1)))
    return format(normalized, "f")


def row_key(row: Mapping[str, Any]) -> tuple[str, str]:
    values: list[str] = []
    for field in KEY_FIELDS:
        value = row.get(field)
        if type(value) is not str or not value.strip():
            raise QuantiPhyMainError(f"missing/invalid key field: {field}")
        if len(value) > 512:
            raise QuantiPhyMainError(f"key field too long: {field}")
        values.append(value.strip())
    return values[0], values[1]


def category_of(row: Mapping[str, Any]) -> str:
    inference_type = row.get("inference_type")
    video_type = row.get("video_type")
    if type(inference_type) is not str or type(video_type) is not str or len(inference_type.strip()) < 1 or len(video_type.strip()) < 2:
        raise QuantiPhyMainError("inference_type/video_type cannot form category")
    category = inference_type.strip()[0].upper() + video_type.strip()[1]
    if category not in CATEGORIES:
        raise QuantiPhyMainError(f"unsupported category: {category}")
    return category


def parse_quantity(text: str, *, expected_unit: str | None = None) -> tuple[str, str | None]:
    """Parse exactly one numeric token and an optional trailing unit.

    This intentionally refuses ambiguous multi-number prose and does not invent unit
    conversions. If an expected unit is supplied, the parsed unit must match exactly.
    """
    if type(text) is not str or not text.strip() or len(text) > 4096:
        raise QuantiPhyMainError("quantity text invalid")
    matches = list(NUMBER_TOKEN.finditer(text))
    if len(matches) != 1:
        raise QuantiPhyMainError("quantity output must contain exactly one numeric token")
    match = matches[0]
    number = _decimal(match.group(0), "quantity", positive=True)
    suffix = text[match.end():].strip()
    prefix = text[:match.start()].strip()
    if prefix:
        # Pure labels/prose before the number can hide alternate interpretation.
        raise QuantiPhyMainError("quantity output has unsupported leading prose")
    parsed_unit: str | None = None
    if suffix:
        if " " in suffix:
            raise QuantiPhyMainError("quantity output has ambiguous trailing prose")
        parsed_unit = _unit(suffix, "quantity.unit")
    if expected_unit is not None:
        expected_unit = _unit(expected_unit, "expected_unit")
        if parsed_unit != expected_unit:
            raise QuantiPhyMainError(f"unit mismatch: expected {expected_unit!r}, got {parsed_unit!r}")
    return _decimal_text(number), parsed_unit


def validate_dataset(raw: Any, *, require_truth: bool) -> list[dict[str, Any]]:
    rows = _list(raw, "dataset", 100000)
    if not rows:
        raise QuantiPhyMainError("dataset is empty")
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    output: list[dict[str, Any]] = []
    required = {"video_id", "question", "inference_type", "video_type"}
    allowed = required | {GROUND_TRUTH, "expected_unit"}
    if require_truth:
        required = required | {GROUND_TRUTH}
    for i, raw_row in enumerate(rows):
        row = _obj(raw_row, f"dataset[{i}]")
        _keys(row, allowed, required, f"dataset[{i}]")
        key = row_key(row)
        if key in indexed:
            raise QuantiPhyMainError(f"duplicate dataset key: {key!r}")
        clean: dict[str, Any] = {
            "video_id": key[0],
            "question": key[1],
            "inference_type": str(row["inference_type"]).strip(),
            "video_type": str(row["video_type"]).strip(),
        }
        category_of(clean)
        if "expected_unit" in row:
            clean["expected_unit"] = _unit(row["expected_unit"], f"dataset[{i}].expected_unit")
        if GROUND_TRUTH in row:
            clean[GROUND_TRUTH] = _decimal_text(_decimal(row[GROUND_TRUTH], f"dataset[{i}].{GROUND_TRUTH}", positive=True))
        indexed[key] = clean
        output.append(clean)
    output.sort(key=lambda row: row_key(row))
    return output


def validate_receipts(raw: Any, dataset_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    receipts = _list(raw, "receipts", 500000)
    dataset_index = {row_key(row): row for row in dataset_rows}
    seen_request: dict[str, dict[str, Any]] = {}
    seen_model_item: set[tuple[str, str, tuple[str, str]]] = set()
    output: list[dict[str, Any]] = []
    allowed = {
        "schema", "request_id", "provider", "model", "video_id", "question", "status",
        "output_sha256", "parsed_value", "unit", "prompt_tokens", "completion_tokens",
        "latency_ms", "cost_microusd", "evidence_sha256"
    }
    required = {
        "schema", "request_id", "provider", "model", "video_id", "question", "status",
        "output_sha256", "prompt_tokens", "completion_tokens", "latency_ms", "cost_microusd", "evidence_sha256"
    }
    for i, raw_receipt in enumerate(receipts):
        receipt = _obj(raw_receipt, f"receipts[{i}]")
        _keys(receipt, allowed, required, f"receipts[{i}]")
        if receipt["schema"] != RECEIPT_SCHEMA:
            raise QuantiPhyMainError(f"receipts[{i}].schema unsupported")
        status = receipt["status"]
        if status not in {"OK", "REFUSAL", "ERROR"}:
            raise QuantiPhyMainError(f"receipts[{i}].status invalid")
        clean: dict[str, Any] = {
            "schema": RECEIPT_SCHEMA,
            "request_id": _sid(receipt["request_id"], f"receipts[{i}].request_id"),
            "provider": _sid(receipt["provider"], f"receipts[{i}].provider"),
            "model": _sid(receipt["model"], f"receipts[{i}].model"),
            "video_id": str(receipt["video_id"]).strip() if type(receipt["video_id"]) is str else "",
            "question": str(receipt["question"]).strip() if type(receipt["question"]) is str else "",
            "status": status,
            "output_sha256": _hex(receipt["output_sha256"], f"receipts[{i}].output_sha256"),
            "prompt_tokens": _int(receipt["prompt_tokens"], f"receipts[{i}].prompt_tokens"),
            "completion_tokens": _int(receipt["completion_tokens"], f"receipts[{i}].completion_tokens"),
            "latency_ms": _int(receipt["latency_ms"], f"receipts[{i}].latency_ms", 0, 86_400_000),
            "cost_microusd": _int(receipt["cost_microusd"], f"receipts[{i}].cost_microusd"),
            "evidence_sha256": _hex(receipt["evidence_sha256"], f"receipts[{i}].evidence_sha256"),
        }
        key = row_key(clean)
        if key not in dataset_index:
            raise QuantiPhyMainError(f"receipt references unknown dataset item: {key!r}")
        if status == "OK":
            if "parsed_value" not in receipt:
                raise QuantiPhyMainError(f"receipts[{i}] OK requires parsed_value")
            clean["parsed_value"] = _decimal_text(_decimal(receipt["parsed_value"], f"receipts[{i}].parsed_value", positive=True))
            expected_unit = dataset_index[key].get("expected_unit")
            if expected_unit is not None:
                if "unit" not in receipt:
                    raise QuantiPhyMainError(f"receipts[{i}] expected unit {expected_unit!r}")
                clean["unit"] = _unit(receipt["unit"], f"receipts[{i}].unit")
                if clean["unit"] != expected_unit:
                    raise QuantiPhyMainError(f"receipts[{i}] unit mismatch")
            elif "unit" in receipt:
                clean["unit"] = _unit(receipt["unit"], f"receipts[{i}].unit")
        else:
            if "parsed_value" in receipt or "unit" in receipt:
                raise QuantiPhyMainError(f"receipts[{i}] non-OK cannot carry parsed_value/unit")
        request_id = clean["request_id"]
        old = seen_request.get(request_id)
        if old is not None:
            if canonical_bytes(old) != canonical_bytes(clean):
                raise QuantiPhyMainError(f"changed request_id reuse: {request_id}")
            continue
        model_item = (clean["provider"], clean["model"], key)
        if model_item in seen_model_item:
            raise QuantiPhyMainError(f"duplicate provider/model receipt for dataset item: {model_item!r}")
        seen_request[request_id] = clean
        seen_model_item.add(model_item)
        output.append(clean)
    if not output:
        raise QuantiPhyMainError("receipts are empty")
    output.sort(key=lambda r: (r["provider"], r["model"], r["video_id"], r["question"], r["request_id"]))
    return output


def model_name(receipt: Mapping[str, Any]) -> str:
    return f"{receipt['provider']}::{receipt['model']}"


def _receipt_index(receipts: Sequence[Mapping[str, Any]]) -> dict[str, dict[tuple[str, str], Mapping[str, Any]]]:
    out: dict[str, dict[tuple[str, str], Mapping[str, Any]]] = defaultdict(dict)
    for receipt in receipts:
        out[model_name(receipt)][row_key(receipt)] = receipt
    return dict(out)


def _dataset_index(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], Mapping[str, Any]]:
    return {row_key(row): row for row in rows}
