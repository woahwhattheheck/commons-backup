from __future__ import annotations

from collections import Counter
from copy import deepcopy
from fractions import Fraction
from typing import Any, Mapping

from .core import (
    CHALLENGE, MODEL_RE, RoadV2Error, _exact, _sha, aggregate_metric, edit_distance,
    normalize_transcript, sha256_hex, validate_manifest,
)

def build_profile(manifest: Mapping[str, Any], labels: Mapping[str, str], oof: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    m = validate_manifest(manifest)
    mids = [x["model_id"] for x in m["models"]]
    if set(oof) != set(mids):
        raise RoadV2Error("OOF model set differs from manifest")
    rows = []
    inverse_scores: list[Fraction] = []
    for mid in mids:
        metric = aggregate_metric(labels, oof[mid])
        combined = Fraction(metric["combined"]["numerator"], metric["combined"]["denominator"])
        quality = Fraction(1, 1) / (Fraction(1, 1) + combined)
        inverse_scores.append(quality)
        rows.append({"model_id": mid, "metric": metric})
    total = sum(inverse_scores, Fraction(0, 1))
    reliabilities: dict[str, int] = {}
    assigned = 0
    for idx, mid in enumerate(mids):
        if idx == len(mids) - 1:
            ppm = 1_000_000 - assigned
        else:
            share = inverse_scores[idx] / total
            ppm = (share.numerator * 1_000_000) // share.denominator
            assigned += ppm
        reliabilities[mid] = ppm
    profile = {
        "schema_version": 1,
        "product": "ROAD_OCR_V2_PROFILE",
        "challenge": CHALLENGE,
        "manifest_sha256": sha256_hex(m),
        "label_set_sha256": sha256_hex({k: normalize_transcript(v) for k, v in sorted(labels.items())}),
        "models": rows,
        "reliability_ppm": reliabilities,
        "authority": {"training_labels_only": True, "test_labels_used": False, "external_data_used": False},
    }
    profile["receipt_sha256"] = sha256_hex(profile)
    return profile


def _validate_profile(profile: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    p = deepcopy(_exact(profile, {
        "schema_version", "product", "challenge", "manifest_sha256", "label_set_sha256",
        "models", "reliability_ppm", "authority", "receipt_sha256",
    }, "profile"))
    if p["schema_version"] != 1 or p["product"] != "ROAD_OCR_V2_PROFILE" or p["challenge"] != CHALLENGE:
        raise RoadV2Error("unsupported profile")
    if p["manifest_sha256"] != sha256_hex(validate_manifest(manifest)):
        raise RoadV2Error("PROFILE_MANIFEST_TRANSPLANT")
    receipt = _sha(p.pop("receipt_sha256"), "profile.receipt_sha256")
    if sha256_hex(p) != receipt:
        raise RoadV2Error("PROFILE_RECEIPT_MISMATCH")
    p["receipt_sha256"] = receipt
    mids = [m["model_id"] for m in manifest["models"]]
    rel = p["reliability_ppm"]
    if type(rel) is not dict or set(rel) != set(mids):
        raise RoadV2Error("profile reliability model mismatch")
    if any(type(v) is not int or v < 0 or v > 1_000_000 for v in rel.values()) or sum(rel.values()) != 1_000_000:
        raise RoadV2Error("profile reliability invalid")
    rows = p["models"]
    if type(rows) is not list or len(rows) != len(mids):
        raise RoadV2Error("profile models invalid")
    seen = set()
    metric_keys = {"word_edits", "reference_words", "char_edits", "reference_chars", "wer", "cer", "combined", "combined_ppm"}
    for idx, row in enumerate(rows):
        row = _exact(row, {"model_id", "metric"}, f"profile.models[{idx}]")
        mid = row["model_id"]
        if mid not in set(mids) or mid in seen:
            raise RoadV2Error("profile model row mismatch")
        seen.add(mid)
        metric = _exact(row["metric"], metric_keys, f"profile.models[{idx}].metric")
        for key in ("word_edits", "reference_words", "char_edits", "reference_chars", "combined_ppm"):
            if type(metric[key]) is not int or metric[key] < 0:
                raise RoadV2Error("profile metric invalid")
        for key in ("wer", "cer", "combined"):
            frac = _exact(metric[key], {"numerator", "denominator"}, f"metric.{key}")
            if type(frac["numerator"]) is not int or type(frac["denominator"]) is not int or frac["numerator"] < 0 or frac["denominator"] <= 0:
                raise RoadV2Error("profile fraction invalid")
    if seen != set(mids):
        raise RoadV2Error("profile model rows incomplete")
    auth = _exact(p["authority"], {"training_labels_only", "test_labels_used", "external_data_used"}, "profile.authority")
    if auth != {"training_labels_only": True, "test_labels_used": False, "external_data_used": False}:
        raise RoadV2Error("PROFILE_AUTHORITY_ESCALATION")
    return p


def train_char_lm(labels: Mapping[str, str], order: int = 3) -> dict[str, Any]:
    if type(order) is not int or not 2 <= order <= 5:
        raise RoadV2Error("LM order must be 2..5")
    grams: Counter[str] = Counter(); prefixes: Counter[str] = Counter(); alphabet: set[str] = set()
    for rid in sorted(labels):
        text = f"^{normalize_transcript(labels[rid])}$"
        alphabet.update(text)
        for i in range(len(text) - order + 1):
            gram = text[i:i+order]; grams[gram] += 1; prefixes[gram[:-1]] += 1
    if not grams:
        raise RoadV2Error("LM training corpus empty")
    return {"order": order, "grams": dict(sorted(grams.items())), "prefixes": dict(sorted(prefixes.items())), "alphabet_size": len(alphabet), "train_sha256": sha256_hex({k: normalize_transcript(v) for k, v in sorted(labels.items())})}


def lm_score_ppm(lm: Mapping[str, Any], text: str) -> int:
    order = lm["order"]; grams = lm["grams"]; prefixes = lm["prefixes"]; vocab = max(2, lm["alphabet_size"])
    text = f"^{normalize_transcript(text)}$"
    pieces = []
    for i in range(len(text) - order + 1):
        gram = text[i:i+order]; prefix = gram[:-1]
        num = grams.get(gram, 0) + 1; den = prefixes.get(prefix, 0) + vocab
        pieces.append((num * 1_000_000) // den)
    return sum(pieces) // len(pieces) if pieces else 0


def _normalized_char_distance_ppm(a: str, b: str) -> int:
    a = normalize_transcript(a); b = normalize_transcript(b)
    den = max(len(a), len(b), 1)
    return (edit_distance(list(a), list(b)) * 1_000_000 + den // 2) // den


def ensemble(manifest: Mapping[str, Any], profile: Mapping[str, Any], labels: Mapping[str, str], predictions: Mapping[str, Mapping[str, str]]) -> tuple[dict[str, str], dict[str, Any]]:
    m = validate_manifest(manifest); p = _validate_profile(profile, m)
    normalized_labels = {k: normalize_transcript(v) for k, v in sorted(labels.items())}
    if sha256_hex(normalized_labels) != p["label_set_sha256"]:
        raise RoadV2Error("PROFILE_LABEL_TRANSPLANT")
    mids = [x["model_id"] for x in m["models"]]
    if set(predictions) != set(mids):
        raise RoadV2Error("prediction model set differs from manifest")
    id_sets = [set(predictions[mid]) for mid in mids]
    if not id_sets or any(s != id_sets[0] for s in id_sets[1:]):
        raise RoadV2Error("prediction ID sets differ across models")
    lm = train_char_lm(labels)
    reliability = p["reliability_ppm"]
    out: dict[str, str] = {}; audit: list[dict[str, Any]] = []
    for rid in sorted(id_sets[0]):
        candidates: dict[str, list[str]] = {}
        norm_by_model: dict[str, str] = {}
        for mid in mids:
            text = normalize_transcript(predictions[mid][rid]); norm_by_model[mid] = text; candidates.setdefault(text, []).append(mid)
        scored = []
        for text, supporters in candidates.items():
            weighted_dist = sum(reliability[mid] * _normalized_char_distance_ppm(text, norm_by_model[mid]) for mid in mids) // 1_000_000
            support_ppm = sum(reliability[mid] for mid in supporters)
            lm_ppm = lm_score_ppm(lm, text)
            objective = weighted_dist * 1000 - support_ppm * 180 - lm_ppm * 20
            scored.append((objective, weighted_dist, -support_ppm, -lm_ppm, text, supporters))
        scored.sort(key=lambda x: (x[0], x[1], x[2], x[3], x[4]))
        _, dist, neg_support, neg_lm, chosen, supporters = scored[0]
        out[rid] = chosen
        audit.append({
            "id_sha256": sha256_hex(rid.encode("utf-8")),
            "candidate_count": len(candidates),
            "support_models": sorted(supporters),
            "support_ppm": -neg_support,
            "agreement_ppm": max(0, 1_000_000 - dist),
            "lm_score_ppm": -neg_lm,
            "chosen_text_sha256": sha256_hex(chosen.encode("utf-8")),
        })
    meta = {
        "schema_version": 1, "product": "ROAD_OCR_V2_ENSEMBLE_AUDIT", "challenge": CHALLENGE,
        "manifest_sha256": sha256_hex(m), "profile_receipt_sha256": p["receipt_sha256"],
        "train_label_sha256": lm["train_sha256"], "row_count": len(out), "rows": audit,
        "authority": {"manual_test_labels": False, "external_data": False, "hosted_inference": False},
    }
    meta["receipt_sha256"] = sha256_hex(meta)
    return out, meta
