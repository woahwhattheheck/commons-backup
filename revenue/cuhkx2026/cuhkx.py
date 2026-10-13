from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

CHOICES = "ABCD"
REQUIRED_BASE = ("qa_id", "source", "path", "category", "question", "A", "B", "C", "D")
ALLOWED_CATEGORIES = {
    "single",
    "multi",
    "object_interaction",
    "sequence",
    "combination",
    "emotion",
}
_USER_RE = re.compile(r"(?:^|/)user(?P<user>\d+)(?:/|$)", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")


class ContractError(ValueError):
    pass


def normalize_prediction(value: str, valid_letters: str = CHOICES) -> str:
    """Canonicalize one or more option letters while rejecting ambiguous answers."""
    raw = (value or "").strip().upper().replace(" ", "").replace(",", "")
    if not raw:
        raise ContractError("empty prediction")
    if any(c not in valid_letters for c in raw):
        raise ContractError(f"prediction contains invalid option: {value!r}")
    if len(set(raw)) != len(raw):
        raise ContractError(f"prediction repeats an option: {value!r}")
    return "".join(c for c in valid_letters if c in raw)


def valid_letters(row: Mapping[str, str]) -> str:
    letters = "".join(c for c in CHOICES if (row.get(c) or "").strip())
    if len(letters) < 2:
        raise ContractError(f"qa_id={row.get('qa_id')} exposes fewer than two options")
    return letters


def _require_columns(fieldnames: Sequence[str] | None, *, training: bool) -> None:
    fields = set(fieldnames or [])
    required = set(REQUIRED_BASE)
    if training:
        required.add("answer")
    missing = sorted(required - fields)
    if missing:
        raise ContractError(f"missing required columns: {', '.join(missing)}")


def read_qa_csv(path: str | Path, *, training: bool) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        _require_columns(reader.fieldnames, training=training)
        rows = [dict(row) for row in reader]
    validate_rows(rows, training=training)
    return rows


def validate_rows(rows: Sequence[Mapping[str, str]], *, training: bool) -> None:
    if not rows:
        raise ContractError("QA table is empty")
    seen: set[str] = set()
    for i, row in enumerate(rows, 2):
        qa_id = (row.get("qa_id") or "").strip()
        if not qa_id:
            raise ContractError(f"row {i}: blank qa_id")
        if qa_id in seen:
            raise ContractError(f"duplicate qa_id: {qa_id}")
        seen.add(qa_id)
        for key in ("source", "path", "category", "question"):
            if not (row.get(key) or "").strip():
                raise ContractError(f"qa_id={qa_id}: blank {key}")
        category = (row.get("category") or "").strip().lower()
        if category not in ALLOWED_CATEGORIES:
            raise ContractError(f"qa_id={qa_id}: unsupported category {category!r}")
        letters = valid_letters(row)
        if training:
            pred = normalize_prediction(row.get("answer", ""), letters)
            is_multi = category == "multi"
            if not is_multi and len(pred) != 1:
                raise ContractError(f"qa_id={qa_id}: non-multi category has multi-letter answer")


def subject_id(row: Mapping[str, str]) -> str:
    match = _USER_RE.search((row.get("path") or ""))
    if not match:
        raise ContractError(f"qa_id={row.get('qa_id')}: training path lacks user<id> subject key")
    return f"user{int(match.group('user'))}"


def grouped_subject_folds(rows: Sequence[Mapping[str, str]], folds: int = 5) -> list[tuple[list[int], list[int]]]:
    """Deterministic subject-disjoint folds; no clip/person can cross train/validation."""
    if folds < 2:
        raise ContractError("folds must be >= 2")
    users = sorted({subject_id(r) for r in rows})
    if len(users) < folds:
        raise ContractError(f"need at least {folds} distinct subjects, got {len(users)}")
    buckets: list[list[str]] = [[] for _ in range(folds)]
    for user in users:
        digest = int(hashlib.sha256(user.encode()).hexdigest()[:16], 16)
        buckets[digest % folds].append(user)
    while any(not b for b in buckets):
        empty = next(i for i, b in enumerate(buckets) if not b)
        donor = max(range(folds), key=lambda i: (len(buckets[i]), -i))
        if len(buckets[donor]) <= 1:
            raise ContractError("cannot construct nonempty subject folds")
        buckets[empty].append(sorted(buckets[donor]).pop())
        buckets[donor] = sorted(buckets[donor])[:-1]
    subject_by_idx = [subject_id(r) for r in rows]
    result = []
    for held in buckets:
        held_set = set(held)
        val = [i for i, s in enumerate(subject_by_idx) if s in held_set]
        train = [i for i, s in enumerate(subject_by_idx) if s not in held_set]
        if not train or not val:
            raise ContractError("empty train/validation fold")
        result.append((train, val))
    return result


def normalize_question(text: str) -> str:
    text = _SPACE_RE.sub(" ", (text or "").strip().lower())
    return _NUMBER_RE.sub("<n>", text)


def question_signature(row: Mapping[str, str]) -> str:
    return "|".join([
        (row.get("source") or "").strip().lower(),
        (row.get("category") or "").strip().lower(),
        normalize_question(row.get("question") or ""),
    ])


@dataclass(frozen=True)
class Prediction:
    qa_id: str
    prediction: str
    confidence: float
    model_id: str

    def __post_init__(self) -> None:
        if not self.qa_id:
            raise ContractError("prediction qa_id is blank")
        if not self.model_id:
            raise ContractError("prediction model_id is blank")
        if not math.isfinite(self.confidence) or not (0.0 <= self.confidence <= 1.0):
            raise ContractError(f"invalid confidence: {self.confidence}")


class HierarchicalPrior:
    """Leakage-safe floor model: exact question signature -> category -> global answer prior."""

    def __init__(self, min_signature_support: int = 3):
        self.min_signature_support = min_signature_support
        self._sig: dict[str, Counter[str]] = defaultdict(Counter)
        self._cat: dict[str, Counter[str]] = defaultdict(Counter)
        self._global: Counter[str] = Counter()

    def fit(self, rows: Iterable[Mapping[str, str]]) -> "HierarchicalPrior":
        count = 0
        for row in rows:
            letters = valid_letters(row)
            answer = normalize_prediction(row.get("answer", ""), letters)
            self._sig[question_signature(row)][answer] += 1
            self._cat[(row.get("category") or "").strip().lower()][answer] += 1
            self._global[answer] += 1
            count += 1
        if count == 0:
            raise ContractError("cannot fit on empty rows")
        return self

    @staticmethod
    def _pick(counter: Counter[str], allowed: str) -> tuple[str, float]:
        candidates = [(n, answer) for answer, n in counter.items() if set(answer) <= set(allowed)]
        if not candidates:
            return allowed[0], 1.0 / len(allowed)
        candidates.sort(key=lambda x: (-x[0], x[1]))
        n, answer = candidates[0]
        total = sum(v for v, _ in candidates)
        return answer, n / total

    def predict_one(self, row: Mapping[str, str]) -> Prediction:
        allowed = valid_letters(row)
        sig_counter = self._sig.get(question_signature(row), Counter())
        if sum(sig_counter.values()) >= self.min_signature_support:
            answer, conf = self._pick(sig_counter, allowed)
            model = "prior:signature"
        else:
            cat = (row.get("category") or "").strip().lower()
            cat_counter = self._cat.get(cat, Counter())
            if cat_counter:
                answer, conf = self._pick(cat_counter, allowed)
                model = "prior:category"
            else:
                answer, conf = self._pick(self._global, allowed)
                model = "prior:global"
        return Prediction(str(row["qa_id"]), answer, conf, model)

    def predict(self, rows: Sequence[Mapping[str, str]]) -> list[Prediction]:
        return [self.predict_one(r) for r in rows]


def read_prediction_csv(path: str | Path, *, model_id: str | None = None) -> list[Prediction]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"qa_id", "prediction"}
        if not required <= set(reader.fieldnames or []):
            raise ContractError("prediction file requires qa_id,prediction columns")
        out = []
        for row in reader:
            confidence_text = (row.get("confidence") or "1").strip()
            try:
                confidence = float(confidence_text)
            except ValueError as exc:
                raise ContractError(f"invalid confidence {confidence_text!r}") from exc
            out.append(Prediction(
                qa_id=(row.get("qa_id") or "").strip(),
                prediction=normalize_prediction(row.get("prediction") or ""),
                confidence=confidence,
                model_id=(model_id or row.get("model_id") or Path(path).stem).strip(),
            ))
    return out


def ensemble_predictions(
    test_rows: Sequence[Mapping[str, str]],
    components: Sequence[Sequence[Prediction]],
    weights: Sequence[float] | None = None,
) -> list[Prediction]:
    if not components:
        raise ContractError("ensemble requires at least one component")
    if weights is None:
        weights = [1.0] * len(components)
    if len(weights) != len(components) or any((not math.isfinite(w) or w <= 0) for w in weights):
        raise ContractError("weights must be finite positive values matching component count")
    expected = [str(r["qa_id"]) for r in test_rows]
    expected_set = set(expected)
    indexed = []
    for comp in components:
        mapping = {p.qa_id: p for p in comp}
        if len(mapping) != len(comp):
            raise ContractError("component contains duplicate qa_id")
        if set(mapping) != expected_set:
            missing = sorted(expected_set - set(mapping))[:3]
            extra = sorted(set(mapping) - expected_set)[:3]
            raise ContractError(f"component coverage mismatch missing={missing} extra={extra}")
        indexed.append(mapping)
    result = []
    for row in test_rows:
        qa_id = str(row["qa_id"])
        allowed = valid_letters(row)
        votes: dict[str, float] = defaultdict(float)
        provenance = []
        for weight, mapping in zip(weights, indexed):
            pred = mapping[qa_id]
            canonical = normalize_prediction(pred.prediction, allowed)
            mass = weight * max(pred.confidence, 1e-12)
            votes[canonical] += mass
            provenance.append(f"{pred.model_id}:{canonical}")
        ordered = sorted(votes.items(), key=lambda item: (-item[1], item[0]))
        winner, winning_mass = ordered[0]
        total_mass = sum(votes.values())
        result.append(Prediction(qa_id, winner, winning_mass / total_mass, "ensemble[" + ",".join(provenance) + "]"))
    return result


def evaluate(rows: Sequence[Mapping[str, str]], predictions: Sequence[Prediction]) -> dict[str, object]:
    truth = {str(r["qa_id"]): (r, normalize_prediction(r.get("answer", ""), valid_letters(r))) for r in rows}
    pred_map = {p.qa_id: p for p in predictions}
    if set(pred_map) != set(truth):
        raise ContractError("prediction coverage does not exactly match evaluation rows")
    per_cat: dict[str, list[int]] = defaultdict(list)
    correct = 0
    for qa_id, (row, answer) in truth.items():
        pred = normalize_prediction(pred_map[qa_id].prediction, valid_letters(row))
        hit = int(pred == answer)
        correct += hit
        per_cat[(row.get("category") or "").strip().lower()].append(hit)
    return {
        "n": len(rows),
        "exact_accuracy": correct / len(rows),
        "by_category": {
            cat: {"n": len(vals), "exact_accuracy": sum(vals) / len(vals)}
            for cat, vals in sorted(per_cat.items())
        },
    }


def write_submission(test_rows: Sequence[Mapping[str, str]], predictions: Sequence[Prediction], output: str | Path) -> dict[str, str]:
    pred_map = {p.qa_id: p for p in predictions}
    expected = [str(r["qa_id"]) for r in test_rows]
    if len(pred_map) != len(predictions) or set(pred_map) != set(expected):
        raise ContractError("submission must contain exactly one prediction for every test qa_id")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["qa_id", "prediction"])
        for row in test_rows:
            qa_id = str(row["qa_id"])
            writer.writerow([qa_id, normalize_prediction(pred_map[qa_id].prediction, valid_letters(row))])
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return {"path": str(output), "sha256": digest, "rows": str(len(test_rows))}


def write_evidence(predictions: Sequence[Prediction], output: str | Path) -> dict[str, str]:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {"qa_id": p.qa_id, "prediction": p.prediction, "confidence": round(p.confidence, 8), "model_id": p.model_id}
        for p in predictions
    ]
    raw = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
    output.write_bytes(raw)
    return {"path": str(output), "sha256": hashlib.sha256(raw).hexdigest(), "rows": str(len(payload))}
