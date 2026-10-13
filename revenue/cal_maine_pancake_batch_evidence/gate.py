from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import os
import re
import stat
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "cal-maine-pancake-batch-evidence/v1"
MANIFEST_SCHEMA = "cal-maine-pancake-batch-evidence-manifest/v1"
POLICY_SCHEMA = "cal-maine-pancake-batch-evidence-policy/v1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
IDENT = re.compile(r"^[A-Z0-9][A-Z0-9._:-]{0,63}$")
MAX_INPUT_BYTES = 1_000_000

EVIDENCE_FIELDS = (
    "formula_revision",
    "egg_allergen_declaration",
    "flour_allergen_declaration",
    "label_revision",
    "film_revision",
    "line_id",
    "calibration_status",
    "cook_time_seconds",
    "cook_temp_f",
    "finished_weight_g",
    "metal_detector_check",
    "finished_lot_lineage",
)

FAMILY_ORDER = (
    "FORMULA_OR_ALLERGEN",
    "LABEL_OR_FILM",
    "LINE_OR_CALIBRATION",
    "COOK_PROCESS",
    "METAL_DETECTOR",
    "LOT_LINEAGE",
)

FAMILY_FIELDS = {
    "FORMULA_OR_ALLERGEN": ("formula_revision", "egg_allergen_declaration", "flour_allergen_declaration"),
    "LABEL_OR_FILM": ("label_revision", "film_revision"),
    "LINE_OR_CALIBRATION": ("line_id", "calibration_status"),
    "COOK_PROCESS": ("cook_time_seconds", "cook_temp_f", "finished_weight_g"),
    "METAL_DETECTOR": ("metal_detector_check",),
    "LOT_LINEAGE": ("finished_lot_lineage",),
}

PACKET_KEYS = {
    "schema",
    "batch_id",
    "source_generation",
    "capture_utc",
    "export_complete",
    "policy_revision",
    "evidence",
}
POLICY_KEYS = {
    "schema",
    "policy_revision",
    "source_generation",
    "max_age_seconds",
    "expected",
}
EVIDENCE_ITEM_KEYS = {"value", "sha256"}


class GateError(ValueError):
    pass


def _reject_constant(value: str) -> None:
    raise GateError(f"non-finite JSON constant: {value}")


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise GateError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_loads(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_pairs_no_duplicates, parse_constant=_reject_constant)
    except GateError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise GateError(f"invalid JSON: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    _validate_json_value(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _validate_json_value(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        if abs(value) > 9_007_199_254_740_991:
            raise GateError(f"unsafe integer at {path}")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise GateError(f"non-finite number at {path}")
        raise GateError(f"floating-point values are not allowed at {path}")
    if isinstance(value, list):
        if len(value) > 10_000:
            raise GateError(f"array too large at {path}")
        for i, child in enumerate(value):
            _validate_json_value(child, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        if len(value) > 1_000:
            raise GateError(f"object too large at {path}")
        for key, child in value.items():
            if not isinstance(key, str):
                raise GateError(f"non-string key at {path}")
            if len(key) > 128:
                raise GateError(f"key too long at {path}")
            _validate_json_value(child, f"{path}.{key}")
        return
    raise GateError(f"unsupported JSON type at {path}: {type(value).__name__}")


def _require_exact_keys(obj: Any, keys: set[str], where: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise GateError(f"{where} must be an object")
    got = set(obj)
    if got != keys:
        missing = sorted(keys - got)
        extra = sorted(got - keys)
        raise GateError(f"{where} keys mismatch; missing={missing} extra={extra}")
    return obj


def _require_int(value: Any, where: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GateError(f"{where} must be an integer")
    if minimum is not None and value < minimum:
        raise GateError(f"{where} must be >= {minimum}")
    return value


def _require_ident(value: Any, where: str) -> str:
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        raise GateError(f"{where} is not a canonical identifier")
    return value


def _parse_utc(value: Any, where: str) -> dt.datetime:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise GateError(f"{where} must be canonical whole-second UTC (YYYY-MM-DDTHH:MM:SSZ)")
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError as exc:
        raise GateError(f"{where} is not a valid UTC time") from exc


def _format_utc(value: dt.datetime) -> str:
    if value.tzinfo is None:
        raise GateError("trusted time must be timezone-aware")
    value = value.astimezone(dt.timezone.utc).replace(microsecond=0)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_policy(policy: Any) -> dict[str, Any]:
    policy = copy.deepcopy(_require_exact_keys(policy, POLICY_KEYS, "policy"))
    if policy["schema"] != POLICY_SCHEMA:
        raise GateError("unsupported policy schema")
    policy["policy_revision"] = _require_int(policy["policy_revision"], "policy.policy_revision", 1)
    policy["source_generation"] = _require_ident(policy["source_generation"], "policy.source_generation")
    policy["max_age_seconds"] = _require_int(policy["max_age_seconds"], "policy.max_age_seconds", 1)
    expected = _require_exact_keys(policy["expected"], set(EVIDENCE_FIELDS), "policy.expected")
    for name in ("cook_time_seconds", "cook_temp_f", "finished_weight_g"):
        rng = expected[name]
        if not isinstance(rng, list) or len(rng) != 2:
            raise GateError(f"policy.expected.{name} must be [min,max]")
        low = _require_int(rng[0], f"policy.expected.{name}[0]")
        high = _require_int(rng[1], f"policy.expected.{name}[1]")
        if low > high:
            raise GateError(f"policy.expected.{name} has inverted range")
    for name in set(EVIDENCE_FIELDS) - {"cook_time_seconds", "cook_temp_f", "finished_weight_g"}:
        _validate_json_value(expected[name], f"policy.expected.{name}")
    return policy


def _normalize_packet(packet: Any, policy: dict[str, Any], trusted_now: dt.datetime) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    packet = copy.deepcopy(_require_exact_keys(packet, PACKET_KEYS, "packet"))
    if packet["schema"] != SCHEMA:
        raise GateError("unsupported packet schema")
    packet["batch_id"] = _require_ident(packet["batch_id"], "packet.batch_id")
    packet["source_generation"] = _require_ident(packet["source_generation"], "packet.source_generation")
    if packet["source_generation"] != policy["source_generation"]:
        raise GateError("packet source_generation does not match policy")
    packet["policy_revision"] = _require_int(packet["policy_revision"], "packet.policy_revision", 1)
    if packet["policy_revision"] != policy["policy_revision"]:
        raise GateError("packet policy_revision does not match policy")
    if type(packet["export_complete"]) is not bool:
        raise GateError("packet.export_complete must be boolean")
    capture = _parse_utc(packet["capture_utc"], "packet.capture_utc")
    now = trusted_now.astimezone(dt.timezone.utc).replace(microsecond=0)
    if capture > now:
        raise GateError("packet capture time is in the future")
    if (now - capture).total_seconds() > policy["max_age_seconds"]:
        raise GateError("packet evidence is stale")
    if not packet["export_complete"]:
        raise GateError("packet export is incomplete")

    evidence = _require_exact_keys(packet["evidence"], set(EVIDENCE_FIELDS), "packet.evidence")
    normalized_evidence: dict[str, dict[str, Any]] = {}
    for field in EVIDENCE_FIELDS:
        item = copy.deepcopy(_require_exact_keys(evidence[field], EVIDENCE_ITEM_KEYS, f"packet.evidence.{field}"))
        digest = item["sha256"]
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise GateError(f"packet.evidence.{field}.sha256 is malformed")
        if sha256_value(item["value"]) != digest:
            raise GateError(f"packet.evidence.{field} digest drift")
        normalized_evidence[field] = item
    packet["evidence"] = normalized_evidence

    defects: list[dict[str, Any]] = []
    expected = policy["expected"]

    def add(family: str, field: str, observed: Any, exp: Any) -> None:
        defects.append({
            "family": family,
            "field": f"evidence.{field}",
            "source_sha256": normalized_evidence[field]["sha256"],
            "observed": observed,
            "expected": exp,
        })

    for family in FAMILY_ORDER:
        for field in FAMILY_FIELDS[family]:
            observed = normalized_evidence[field]["value"]
            exp = expected[field]
            if field in {"cook_time_seconds", "cook_temp_f", "finished_weight_g"}:
                value = _require_int(observed, f"packet.evidence.{field}.value")
                if value < exp[0] or value > exp[1]:
                    add(family, field, value, exp)
            elif observed != exp:
                add(family, field, observed, exp)
    return packet, defects


def compile_packet(packet: Any, policy: Any, trusted_now: dt.datetime) -> dict[str, Any]:
    normalized_policy = _normalize_policy(policy)
    normalized_packet, defects = _normalize_packet(packet, normalized_policy, trusted_now)
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "evaluated_at_utc": _format_utc(trusted_now),
        "state": "HOLD_FOR_OWNER_REVIEW" if defects else "COMPLETE_FOR_OWNER_REVIEW",
        "batch_id": normalized_packet["batch_id"],
        "packet_sha256": sha256_value(normalized_packet),
        "policy_sha256": sha256_value(normalized_policy),
        "defects": defects,
        "authority": {
            "source_writes": False,
            "network_calls": False,
            "product_release": False,
            "food_safety_decision": False,
        },
        "packet": normalized_packet,
        "policy": normalized_policy,
    }
    receipt = sha256_value(manifest)
    return {"manifest": manifest, "receipt_sha256": receipt}


def verify_compiled(compiled: Any) -> bool:
    compiled = _require_exact_keys(compiled, {"manifest", "receipt_sha256"}, "compiled")
    receipt = compiled["receipt_sha256"]
    if not isinstance(receipt, str) or not HEX64.fullmatch(receipt):
        raise GateError("compiled receipt is malformed")
    manifest = compiled["manifest"]
    if sha256_value(manifest) != receipt:
        raise GateError("compiled receipt mismatch")
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise GateError("unsupported manifest schema")
    trusted_now = _parse_utc(manifest.get("evaluated_at_utc"), "manifest.evaluated_at_utc")
    rebuilt = compile_packet(manifest.get("packet"), manifest.get("policy"), trusted_now)
    if canonical_bytes(rebuilt) != canonical_bytes(compiled):
        raise GateError("manifest does not reproduce from embedded evidence")
    return True


def compile_corpus(packets: Iterable[Any], policy: Any, trusted_now: dt.datetime) -> dict[str, Any]:
    normalized_policy = _normalize_policy(policy)
    seen: dict[str, tuple[str, dict[str, Any]]] = {}
    decisions: list[dict[str, Any]] = []
    replay_count = 0
    for raw in packets:
        compiled = compile_packet(raw, normalized_policy, trusted_now)
        batch_id = compiled["manifest"]["batch_id"]
        digest = compiled["manifest"]["packet_sha256"]
        prior = seen.get(batch_id)
        if prior is None:
            seen[batch_id] = (digest, compiled)
            decisions.append(compiled)
        elif prior[0] == digest:
            replay_count += 1
        else:
            raise GateError(f"changed-payload replay for batch_id {batch_id}")
    decisions.sort(key=lambda item: (item["manifest"]["batch_id"], item["manifest"]["packet_sha256"]))
    summary = {
        "schema": "cal-maine-pancake-batch-evidence-corpus/v1",
        "evaluated_at_utc": _format_utc(trusted_now),
        "unique_batch_count": len(decisions),
        "exact_replay_count": replay_count,
        "complete_count": sum(d["manifest"]["state"] == "COMPLETE_FOR_OWNER_REVIEW" for d in decisions),
        "hold_count": sum(d["manifest"]["state"] == "HOLD_FOR_OWNER_REVIEW" for d in decisions),
        "decision_receipts": [d["receipt_sha256"] for d in decisions],
        "policy_sha256": sha256_value(normalized_policy),
    }
    return {"summary": summary, "receipt_sha256": sha256_value(summary)}


def markdown_projection(compiled: dict[str, Any]) -> str:
    verify_compiled(compiled)
    m = compiled["manifest"]
    lines = [
        "# Pancake batch evidence review",
        "",
        f"- Batch: `{m['batch_id']}`",
        f"- State: **{m['state']}**",
        f"- Packet SHA-256: `{m['packet_sha256']}`",
        f"- Policy SHA-256: `{m['policy_sha256']}`",
        f"- Receipt SHA-256: `{compiled['receipt_sha256']}`",
        "",
        "This artifact is evidence for owner review only. It is not a food-safety conclusion or product-release authorization.",
    ]
    if m["defects"]:
        lines.extend(["", "## Holds"])
        for defect in m["defects"]:
            lines.append(f"- `{defect['family']}` · `{defect['field']}` · source `{defect['source_sha256']}`")
    return "\n".join(lines) + "\n"


def evidence(value: Any) -> dict[str, Any]:
    return {"value": copy.deepcopy(value), "sha256": sha256_value(value)}


def acceptance_policy() -> dict[str, Any]:
    return {
        "schema": POLICY_SCHEMA,
        "policy_revision": 7,
        "source_generation": "SYNTH-20260913-A",
        "max_age_seconds": 7_200,
        "expected": {
            "formula_revision": "FORMULA-PANCAKE-42",
            "egg_allergen_declaration": "EGG-DECLARED",
            "flour_allergen_declaration": "WHEAT-DECLARED",
            "label_revision": "LABEL-19",
            "film_revision": "FILM-8",
            "line_id": "BURLINGTON-LINE-2",
            "calibration_status": "CURRENT",
            "cook_time_seconds": [85, 95],
            "cook_temp_f": [345, 355],
            "finished_weight_g": [48, 52],
            "metal_detector_check": "PASS",
            "finished_lot_lineage": ["EGGLOT-1", "FLOURLOT-1", "FILMLOT-1"],
        },
    }


def _base_packet(batch_id: str, capture_utc: str = "2026-09-13T13:00:00Z") -> dict[str, Any]:
    policy = acceptance_policy()
    ev: dict[str, Any] = {}
    for field, exp in policy["expected"].items():
        value = exp[0] if field == "cook_time_seconds" else exp
        if field == "cook_temp_f":
            value = 350
        elif field == "finished_weight_g":
            value = 50
        elif field == "cook_time_seconds":
            value = 90
        ev[field] = evidence(value)
    return {
        "schema": SCHEMA,
        "batch_id": batch_id,
        "source_generation": policy["source_generation"],
        "capture_utc": capture_utc,
        "export_complete": True,
        "policy_revision": policy["policy_revision"],
        "evidence": ev,
    }


def _set_value(packet: dict[str, Any], field: str, value: Any) -> None:
    packet["evidence"][field] = evidence(value)


def generate_acceptance_corpus() -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, str]]:
    packets: list[dict[str, Any]] = []
    seeded: dict[str, str] = {}
    for i in range(128):
        packets.append(_base_packet(f"CLEAN-{i:04d}"))

    mutations = {
        "FORMULA_OR_ALLERGEN": ("formula_revision", "FORMULA-PANCAKE-41"),
        "LABEL_OR_FILM": ("label_revision", "LABEL-18"),
        "LINE_OR_CALIBRATION": ("calibration_status", "EXPIRED"),
        "COOK_PROCESS": ("cook_temp_f", 340),
        "METAL_DETECTOR": ("metal_detector_check", "MISSING"),
        "LOT_LINEAGE": ("finished_lot_lineage", ["EGGLOT-1", "FLOURLOT-1"]),
    }
    for family in FAMILY_ORDER:
        field, bad = mutations[family]
        for j in range(16):
            packet = _base_packet(f"DEFECT-{family[:4]}-{j:02d}")
            _set_value(packet, field, bad)
            packets.append(packet)
            seeded[packet["batch_id"]] = family

    for i in range(32):
        packet = _base_packet(f"ROBUST-{i:04d}", "2026-09-13T12:00:00Z")
        packet["evidence"] = dict(reversed(list(packet["evidence"].items())))
        packets.append(packet)

    if len(packets) != 256 or len(seeded) != 96:
        raise AssertionError("acceptance corpus construction invariant failed")
    return packets, acceptance_policy(), seeded


def run_acceptance() -> dict[str, Any]:
    now = dt.datetime(2026, 9, 13, 14, 0, 0, tzinfo=dt.timezone.utc)
    packets, policy, seeded = generate_acceptance_corpus()
    clean_complete = 0
    seeded_recalled = 0
    false_complete = 0
    family_counts = {family: 0 for family in FAMILY_ORDER}
    hold_sources_complete = True
    per_packet: list[dict[str, Any]] = []
    for index, packet in enumerate(packets):
        compiled = compile_packet(packet, policy, now)
        verify_compiled(compiled)
        per_packet.append(compiled)
        state = compiled["manifest"]["state"]
        if index < 128 and state == "COMPLETE_FOR_OWNER_REVIEW":
            clean_complete += 1
        family = seeded.get(packet["batch_id"])
        if family:
            defects = compiled["manifest"]["defects"]
            if state == "HOLD_FOR_OWNER_REVIEW" and any(d["family"] == family for d in defects):
                seeded_recalled += 1
                family_counts[family] += 1
            if state == "COMPLETE_FOR_OWNER_REVIEW":
                false_complete += 1
            for defect in defects:
                hold_sources_complete &= bool(defect["field"] and HEX64.fullmatch(defect["source_sha256"]))

    corpus_a = compile_corpus(packets, policy, now)
    corpus_b = compile_corpus(copy.deepcopy(packets), copy.deepcopy(policy), now)
    corpus_c = compile_corpus(list(reversed(list(reversed(copy.deepcopy(packets))))), copy.deepcopy(policy), now)
    deterministic = canonical_bytes(corpus_a) == canonical_bytes(corpus_b) == canonical_bytes(corpus_c)
    authority_ok = all(
        decision["manifest"]["authority"] == {
            "source_writes": False,
            "network_calls": False,
            "product_release": False,
            "food_safety_decision": False,
        }
        for decision in per_packet
    )
    passed = (
        clean_complete == 128
        and seeded_recalled == 96
        and false_complete == 0
        and all(family_counts[f] == 16 for f in FAMILY_ORDER)
        and hold_sources_complete
        and deterministic
        and authority_ok
    )
    return {
        "schema": "cal-maine-pancake-batch-evidence-acceptance/v1",
        "packet_count": 256,
        "clean_complete": clean_complete,
        "seeded_defects": 96,
        "seeded_recalled": seeded_recalled,
        "false_complete": false_complete,
        "family_counts": family_counts,
        "all_holds_bind_source_hash_and_field": hold_sources_complete,
        "source_writes": 0,
        "network_calls": 0,
        "three_manifests_byte_identical": deterministic,
        "passed": passed,
        "corpus_receipt_sha256": corpus_a["receipt_sha256"],
    }


def _read_bounded_regular(path: Path) -> str:
    st = path.lstat()
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise GateError(f"input is not a regular non-symlink file: {path}")
    if st.st_size > MAX_INPUT_BYTES:
        raise GateError(f"input exceeds {MAX_INPUT_BYTES} bytes: {path}")
    data = path.read_bytes()
    if len(data) != st.st_size:
        raise GateError("input changed while reading")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GateError("input is not UTF-8") from exc


def write_exclusive(path: Path, data: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise GateError(f"refusing to overwrite output: {path}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o644)
    try:
        with os.fdopen(fd, "wb", closefd=False) as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    finally:
        os.close(fd)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only pancake batch evidence gate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_compile = sub.add_parser("compile")
    p_compile.add_argument("packet")
    p_compile.add_argument("policy")
    p_compile.add_argument("output_prefix")
    p_verify = sub.add_parser("verify")
    p_verify.add_argument("compiled_json")
    sub.add_parser("acceptance")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "compile":
            packet = strict_loads(_read_bounded_regular(Path(args.packet)))
            policy = strict_loads(_read_bounded_regular(Path(args.policy)))
            compiled = compile_packet(packet, policy, _utc_now())
            prefix = Path(args.output_prefix)
            write_exclusive(prefix.with_suffix(".json"), canonical_bytes(compiled) + b"\n")
            write_exclusive(prefix.with_suffix(".md"), markdown_projection(compiled).encode("utf-8"))
            print(compiled["receipt_sha256"])
            return 0
        if args.cmd == "verify":
            compiled = strict_loads(_read_bounded_regular(Path(args.compiled_json)))
            verify_compiled(compiled)
            print("VERIFIED")
            return 0
        if args.cmd == "acceptance":
            result = run_acceptance()
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0 if result["passed"] else 2
    except (GateError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=os.sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
