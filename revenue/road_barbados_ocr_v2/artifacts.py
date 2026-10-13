from __future__ import annotations

import csv
import io
from copy import deepcopy
from typing import Any, Mapping

from .core import (
    CHALLENGE, MODEL_RE, RoadV2Error, _exact, _id_col, _sha, _value_col, normalize_transcript,
    parse_csv, sha256_hex, validate_manifest,
)
from .profile import _validate_profile

def _validate_audit(audit: Mapping[str, Any]) -> dict[str, Any]:
    a = deepcopy(_exact(audit, {
        "schema_version", "product", "challenge", "manifest_sha256", "profile_receipt_sha256",
        "train_label_sha256", "row_count", "rows", "authority", "receipt_sha256",
    }, "audit"))
    if a["schema_version"] != 1 or a["product"] != "ROAD_OCR_V2_ENSEMBLE_AUDIT" or a["challenge"] != CHALLENGE:
        raise RoadV2Error("unsupported audit")
    for key in ("manifest_sha256", "profile_receipt_sha256", "train_label_sha256"):
        _sha(a[key], f"audit.{key}")
    receipt = _sha(a.pop("receipt_sha256"), "audit.receipt_sha256")
    if sha256_hex(a) != receipt:
        raise RoadV2Error("AUDIT_RECEIPT_MISMATCH")
    a["receipt_sha256"] = receipt
    if type(a["row_count"]) is not int or a["row_count"] < 0 or type(a["rows"]) is not list or len(a["rows"]) != a["row_count"]:
        raise RoadV2Error("audit row_count mismatch")
    seen_ids = set()
    for idx, row in enumerate(a["rows"]):
        row = _exact(row, {"id_sha256", "candidate_count", "support_models", "support_ppm", "agreement_ppm", "lm_score_ppm", "chosen_text_sha256"}, f"audit.rows[{idx}]")
        _sha(row["id_sha256"], "audit.id_sha256"); _sha(row["chosen_text_sha256"], "audit.chosen_text_sha256")
        if row["id_sha256"] in seen_ids:
            raise RoadV2Error("duplicate audit id")
        seen_ids.add(row["id_sha256"])
        if type(row["candidate_count"]) is not int or row["candidate_count"] < 1:
            raise RoadV2Error("audit candidate_count invalid")
        if type(row["support_models"]) is not list or len(row["support_models"]) != len(set(row["support_models"])) or any(type(x) is not str or not MODEL_RE.fullmatch(x) for x in row["support_models"]):
            raise RoadV2Error("audit support_models invalid")
        for key in ("support_ppm", "agreement_ppm", "lm_score_ppm"):
            if type(row[key]) is not int or not 0 <= row[key] <= 1_000_000:
                raise RoadV2Error(f"audit {key} invalid")
    auth = _exact(a["authority"], {"manual_test_labels", "external_data", "hosted_inference"}, "audit.authority")
    if auth != {"manual_test_labels": False, "external_data": False, "hosted_inference": False}:
        raise RoadV2Error("AUDIT_AUTHORITY_ESCALATION")
    return a


def admit_pseudo_labels(audit: Mapping[str, Any], predictions: Mapping[str, str], *, min_support_models: int = 2, min_support_ppm: int = 600_000, min_agreement_ppm: int = 850_000) -> dict[str, Any]:
    if type(min_support_models) is not int or min_support_models < 2:
        raise RoadV2Error("min_support_models must be >=2")
    for v, name in ((min_support_ppm, "min_support_ppm"), (min_agreement_ppm, "min_agreement_ppm")):
        if type(v) is not int or not 0 <= v <= 1_000_000:
            raise RoadV2Error(f"{name} invalid")
    audit = _validate_audit(audit)
    rows = audit["rows"]
    by_hash = {sha256_hex(rid.encode("utf-8")): rid for rid in predictions}
    admitted = []
    for row in rows:
        row = _exact(row, {"id_sha256", "candidate_count", "support_models", "support_ppm", "agreement_ppm", "lm_score_ppm", "chosen_text_sha256"}, "audit.row")
        rid = by_hash.get(row["id_sha256"])
        if rid is None:
            raise RoadV2Error("AUDIT_ID_TRANSPLANT")
        text = normalize_transcript(predictions[rid])
        if sha256_hex(text.encode("utf-8")) != row["chosen_text_sha256"]:
            raise RoadV2Error("AUDIT_TEXT_TRANSPLANT")
        if len(row["support_models"]) >= min_support_models and row["support_ppm"] >= min_support_ppm and row["agreement_ppm"] >= min_agreement_ppm:
            admitted.append({"id": rid, "pseudo_label": text, "support_models": sorted(row["support_models"]), "support_ppm": row["support_ppm"], "agreement_ppm": row["agreement_ppm"]})
    result = {
        "schema_version": 1, "product": "ROAD_OCR_V2_AUTOMATED_PSEUDOLABELS", "challenge": CHALLENGE,
        "policy": {"fully_automated": True, "manual_test_labels": False, "min_support_models": min_support_models, "min_support_ppm": min_support_ppm, "min_agreement_ppm": min_agreement_ppm},
        "rows": admitted,
        "authority": {"self_training_authorized_by_artifact": False, "submission_authorized": False, "manual_review_for_label_content": False},
    }
    result["receipt_sha256"] = sha256_hex(result)
    return result


def compile_submission(sample_raw: bytes | str, predictions: Mapping[str, str]) -> bytes:
    header, rows = parse_csv(sample_raw, where="SampleSubmission.csv")
    iid = _id_col(header); pred_col = _value_col(header, iid)
    sample_ids = [r[iid] for r in rows]
    if any(not x for x in sample_ids) or len(sample_ids) != len(set(sample_ids)):
        raise RoadV2Error("sample IDs invalid/duplicate")
    if set(sample_ids) != set(predictions):
        raise RoadV2Error("submission ID set differs from sample")
    buf = io.StringIO(newline=""); writer = csv.writer(buf, lineterminator="\n"); writer.writerow(header)
    for row in rows:
        rid = row[iid]; writer.writerow([rid if h == iid else normalize_transcript(predictions[rid]) for h in header])
    return buf.getvalue().encode("utf-8")


def build_receipt(manifest: Mapping[str, Any], profile: Mapping[str, Any], audit: Mapping[str, Any], pseudo: Mapping[str, Any], *, sample_raw: bytes, submission_raw: bytes, input_prediction_digests: Mapping[str, str]) -> dict[str, Any]:
    m = validate_manifest(manifest); p = _validate_profile(profile, m); audit = _validate_audit(audit)
    if audit["manifest_sha256"] != sha256_hex(m) or audit["profile_receipt_sha256"] != p["receipt_sha256"] or audit["train_label_sha256"] != p["label_set_sha256"]:
        raise RoadV2Error("audit provenance mismatch")
    if type(pseudo) is not dict:
        raise RoadV2Error("pseudo artifact invalid")
    pseudo_copy = deepcopy(pseudo)
    pseudo_receipt = _sha(pseudo_copy.pop("receipt_sha256", None), "pseudo.receipt_sha256")
    if sha256_hex(pseudo_copy) != pseudo_receipt:
        raise RoadV2Error("PSEUDO_RECEIPT_MISMATCH")
    if pseudo.get("product") != "ROAD_OCR_V2_AUTOMATED_PSEUDOLABELS" or pseudo.get("challenge") != CHALLENGE:
        raise RoadV2Error("pseudo artifact identity mismatch")
    if pseudo.get("authority") != {"self_training_authorized_by_artifact": False, "submission_authorized": False, "manual_review_for_label_content": False}:
        raise RoadV2Error("PSEUDO_AUTHORITY_ESCALATION")
    for mid in {x["model_id"] for x in m["models"]}:
        if mid not in input_prediction_digests:
            raise RoadV2Error("missing prediction digest")
        _sha(input_prediction_digests[mid], f"prediction_digest.{mid}")
    r = {
        "schema_version": 1, "product": "ROAD_OCR_V2_BUILD_RECEIPT", "challenge": CHALLENGE,
        "manifest_sha256": sha256_hex(m), "profile_receipt_sha256": p["receipt_sha256"],
        "ensemble_receipt_sha256": _sha(audit["receipt_sha256"], "audit.receipt_sha256"),
        "pseudolabel_receipt_sha256": _sha(pseudo["receipt_sha256"], "pseudo.receipt_sha256"),
        "sample_sha256": sha256_hex(sample_raw), "submission_sha256": sha256_hex(submission_raw),
        "input_prediction_sha256": dict(sorted(input_prediction_digests.items())),
        "authority": {
            "zindi_joined_or_terms_mutated": False, "challenge_data_committed": False,
            "external_training_data": False, "hosted_inference": False, "automl": False,
            "submission_sent": False, "leaderboard_score_or_rank_known": False,
            "award_payment_revenue_claimed": False,
        },
    }
    r["receipt_sha256"] = sha256_hex(r)
    return r


def verify_receipt(receipt: Mapping[str, Any], *, sample_raw: bytes, submission_raw: bytes) -> bool:
    if type(receipt) is not dict:
        return False
    try:
        r = deepcopy(receipt); got = _sha(r.pop("receipt_sha256"), "receipt.receipt_sha256")
        if sha256_hex(r) != got:
            return False
        if r["sample_sha256"] != sha256_hex(sample_raw) or r["submission_sha256"] != sha256_hex(submission_raw):
            return False
        auth = r["authority"]
        return type(auth) is dict and not any(auth.values())
    except (KeyError, RoadV2Error):
        return False
