from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
from collections import Counter
from copy import deepcopy
from fractions import Fraction
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = 1
CHALLENGE = "road-barbados-historic-handwriting-2026"
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
REV_RE = re.compile(r"^[0-9A-Za-z._:/@+-]{1,160}$")
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class RoadV2Error(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise RoadV2Error(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(raw: bytes | str) -> Any:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise RoadV2Error("JSON must be strict UTF-8") from exc
    if not isinstance(raw, str):
        raise RoadV2Error("JSON input must be bytes or string")
    try:
        return json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_float=lambda _: (_ for _ in ()).throw(RoadV2Error("JSON floats forbidden")),
            parse_constant=lambda _: (_ for _ in ()).throw(RoadV2Error("non-finite JSON forbidden")),
        )
    except RoadV2Error:
        raise
    except Exception as exc:
        raise RoadV2Error(f"invalid JSON: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def sha256_hex(value: bytes | bytearray | Any) -> str:
    data = bytes(value) if isinstance(value, (bytes, bytearray)) else canonical_bytes(value)
    return hashlib.sha256(data).hexdigest()


def _exact(obj: Any, keys: set[str], where: str) -> dict[str, Any]:
    if type(obj) is not dict:
        raise RoadV2Error(f"{where} must be object")
    if set(obj) != keys:
        raise RoadV2Error(f"{where} keys mismatch")
    return obj


def _text(value: Any, where: str, *, allow_empty: bool = False, max_len: int = 4096) -> str:
    if type(value) is not str:
        raise RoadV2Error(f"{where} must be string")
    if value != value.strip() and not allow_empty:
        raise RoadV2Error(f"{where} must not have surrounding whitespace")
    if len(value) > max_len:
        raise RoadV2Error(f"{where} too long")
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in value):
        raise RoadV2Error(f"{where} contains control character")
    if not allow_empty and not value:
        raise RoadV2Error(f"{where} must be non-empty")
    return value


def normalize_transcript(value: str) -> str:
    if type(value) is not str:
        raise RoadV2Error("transcript must be string")
    value = unicodedata.normalize("NFC", value)
    value = " ".join(value.replace("\r", " ").replace("\n", " ").replace("\t", " ").split())
    if not value:
        raise RoadV2Error("transcript must be non-empty after normalization")
    if len(value) > 4096:
        raise RoadV2Error("transcript too long")
    if any(ord(ch) < 32 for ch in value):
        raise RoadV2Error("transcript contains control character")
    return value


def _sha(value: Any, where: str) -> str:
    if type(value) is not str or not SHA_RE.fullmatch(value):
        raise RoadV2Error(f"{where} must be lowercase sha256")
    return value


def _revision(value: Any, where: str) -> str:
    if type(value) is not str or not REV_RE.fullmatch(value):
        raise RoadV2Error(f"{where} invalid revision/source token")
    return value


def _bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise RoadV2Error(f"{where} must be boolean")
    return value


def validate_manifest(raw: Mapping[str, Any]) -> dict[str, Any]:
    obj = deepcopy(_exact(raw, {"schema_version", "challenge", "models", "authority"}, "manifest"))
    if obj["schema_version"] != SCHEMA_VERSION or obj["challenge"] != CHALLENGE:
        raise RoadV2Error("unsupported manifest schema/challenge")
    models = obj["models"]
    if type(models) is not list or not 2 <= len(models) <= 16:
        raise RoadV2Error("manifest.models must contain 2..16 models")
    seen: set[str] = set()
    required = {
        "model_id", "base_name", "base_source", "base_revision", "base_license",
        "commercial_use_compatible", "openly_available", "adaptation_data",
        "external_training_data", "hosted_api", "automl", "weights_sha256",
    }
    for idx, model in enumerate(models):
        model = _exact(model, required, f"models[{idx}]")
        mid = model["model_id"]
        if type(mid) is not str or not MODEL_RE.fullmatch(mid):
            raise RoadV2Error(f"models[{idx}].model_id invalid")
        if mid in seen:
            raise RoadV2Error("duplicate model_id")
        seen.add(mid)
        _text(model["base_name"], f"models[{idx}].base_name", max_len=200)
        _revision(model["base_source"], f"models[{idx}].base_source")
        _revision(model["base_revision"], f"models[{idx}].base_revision")
        _text(model["base_license"], f"models[{idx}].base_license", max_len=100)
        if not _bool(model["commercial_use_compatible"], "commercial_use_compatible"):
            raise RoadV2Error("MODEL_LICENSE_NOT_COMMERCIAL_USE_COMPATIBLE")
        if not _bool(model["openly_available"], "openly_available"):
            raise RoadV2Error("MODEL_NOT_OPENLY_AVAILABLE")
        if model["adaptation_data"] != "challenge_only":
            raise RoadV2Error("EXTERNAL_ADAPTATION_DATA_FORBIDDEN")
        if _bool(model["external_training_data"], "external_training_data"):
            raise RoadV2Error("EXTERNAL_TRAINING_DATA_FORBIDDEN")
        if _bool(model["hosted_api"], "hosted_api"):
            raise RoadV2Error("HOSTED_API_FORBIDDEN")
        if _bool(model["automl"], "automl"):
            raise RoadV2Error("AUTOML_FORBIDDEN")
        _sha(model["weights_sha256"], f"models[{idx}].weights_sha256")
    authority = _exact(obj["authority"], {
        "manual_test_labels", "external_data", "hosted_inference", "automl",
        "submit_to_zindi", "claim_score_rank_award_payment",
    }, "manifest.authority")
    if any(_bool(v, f"manifest.authority.{k}") for k, v in authority.items()):
        raise RoadV2Error("MANIFEST_AUTHORITY_ESCALATION")
    return obj


def parse_csv(raw: bytes | str, *, where: str) -> tuple[list[str], list[dict[str, str]]]:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError as exc:
            raise RoadV2Error(f"{where} must be UTF-8") from exc
    if not isinstance(raw, str):
        raise RoadV2Error(f"{where} must be bytes/string")
    reader = csv.reader(io.StringIO(raw, newline=""))
    try:
        header = next(reader)
    except StopIteration:
        raise RoadV2Error(f"{where} empty")
    if not header or any(not h for h in header):
        raise RoadV2Error(f"{where} invalid header")
    if len(header) != len(set(header)):
        raise RoadV2Error(f"{where} duplicate header")
    rows: list[dict[str, str]] = []
    for line_no, cells in enumerate(reader, 2):
        if len(cells) != len(header):
            raise RoadV2Error(f"{where}:{line_no} width mismatch")
        rows.append(dict(zip(header, cells)))
    if not rows:
        raise RoadV2Error(f"{where} has no rows")
    return header, rows


def _id_col(header: Sequence[str]) -> str:
    hits = [h for h in header if h.casefold() == "id"]
    if len(hits) != 1:
        raise RoadV2Error("CSV must have exactly one ID column")
    return hits[0]


def _value_col(header: Sequence[str], id_col: str) -> str:
    rest = [h for h in header if h != id_col]
    if len(rest) != 1:
        raise RoadV2Error("CSV must have exactly one value column besides ID")
    return rest[0]


def csv_text_map(raw: bytes | str, *, where: str) -> tuple[dict[str, str], str, str]:
    header, rows = parse_csv(raw, where=where)
    iid = _id_col(header)
    value = _value_col(header, iid)
    out: dict[str, str] = {}
    for idx, row in enumerate(rows):
        rid = _text(row[iid], f"{where}[{idx}].ID", max_len=512)
        if rid in out:
            raise RoadV2Error(f"{where} duplicate ID")
        out[rid] = normalize_transcript(row[value])
    return out, iid, value


def edit_distance(a: Sequence[Any], b: Sequence[Any]) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, av in enumerate(a, 1):
        cur = [i]
        for j, bv in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + (av != bv)))
        prev = cur
    return prev[-1]


def error_counts(reference: str, hypothesis: str) -> dict[str, int]:
    ref = normalize_transcript(reference)
    hyp = normalize_transcript(hypothesis)
    rw, hw = ref.split(" "), hyp.split(" ")
    return {
        "word_edits": edit_distance(rw, hw),
        "reference_words": len(rw),
        "char_edits": edit_distance(list(ref), list(hyp)),
        "reference_chars": len(ref),
    }


def aggregate_metric(labels: Mapping[str, str], predictions: Mapping[str, str]) -> dict[str, Any]:
    if set(labels) != set(predictions):
        raise RoadV2Error("metric ID sets differ")
    wc = rcw = cc = rcc = 0
    for rid in sorted(labels):
        c = error_counts(labels[rid], predictions[rid])
        wc += c["word_edits"]; rcw += c["reference_words"]
        cc += c["char_edits"]; rcc += c["reference_chars"]
    if not rcw or not rcc:
        raise RoadV2Error("metric denominator empty")
    wer = Fraction(wc, rcw); cer = Fraction(cc, rcc); combined = (wer + cer) / 2
    return {
        "word_edits": wc, "reference_words": rcw,
        "char_edits": cc, "reference_chars": rcc,
        "wer": {"numerator": wer.numerator, "denominator": wer.denominator},
        "cer": {"numerator": cer.numerator, "denominator": cer.denominator},
        "combined": {"numerator": combined.numerator, "denominator": combined.denominator},
        "combined_ppm": (combined.numerator * 1_000_000 + combined.denominator // 2) // combined.denominator,
    }
