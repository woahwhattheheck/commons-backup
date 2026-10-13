#!/usr/bin/env python3
"""Build and verify the public, synthetic Subzero Artifact Explorer packet.

The instrument reads only checked-in repository artifacts. It never opens a live
Titan, device, model, container, or host substrate. A path or file being present
is structural evidence only; it can never prove a runtime measurement.

No auth. No gate. The explorer and its validation receipts are open files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
from datetime import datetime
from urllib.parse import quote


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "SUBZERO_EXPLORER.json")
DEFAULT_CARD = os.path.join("ground", "SUBZERO_EXPLORER.md")
DEFAULT_DOOR = "subzero.html"
RECEIPT_SCHEMA = os.path.join(
    "revenue", "subzero_buyers", "validation_receipt.schema.json"
)
PACKET = os.path.join("excerpts", "20260823", "titan_move_packet.json")
EXCERPT_DIR = os.path.join("excerpts", "20260823")
ARCH = os.path.join("muhl", "desktop", "MUHL_SUBZERO_ARCHETYPES")
REPOSITORY = "woahwhattheheck/commons"
SCHEMA_VERSION = "subzero-explorer/v2"
RECEIPT_VERSION = "subzero-validation-receipt/v1"
SLACK_TS = "1787646413.997539"
HANDOFF_ID = "jojo-model-work-profitability-bridge-20260825-01"
V2_SLACK_TS = "1787647728.185449"
V2_SPEC_ID = "jojo-subzero-explorer-v2-followup-20260825-01"
LDA_SHA = "fb0b0b2f59f8ca81741371b6ddd8036b164e77e8"
LDA_BLOCK = "BLOCKED_ON_PUBLISHED_WIDE_RECEIVER_RESULT"
EXPECTED_EXCERPTS = 31
EVIDENCE_CLASSES = (
    "STRUCTURAL_ONLY",
    "RUNTIME_MEASURED",
    "CUSTOMER_READY",
    "UNKNOWN",
)
OFFER_REFS = ("P01", "P03", "P05")
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
    os.path.join(EXCERPT_DIR, "muhl_grbn.mno"),
)
BASE_SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "subzero_explorer.py"),
    DEFAULT_DOOR,
    RECEIPT_SCHEMA,
    PACKET,
    EXCERPT_DIR,
    ARCH,
    os.path.join("ground", "SUBZERO_TECH.md"),
    os.path.join("ground", "SUBZERO_BUYERS.md"),
) + CALIBRATION
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
STRUCTURAL_SOURCE_KEYS = (
    "fabricator",
    "structural_test",
    "sidecar",
    "card",
    "packet",
)


def _norm(rel):
    return str(rel or "").replace("\\", "/")


def _path(root, rel):
    return os.path.join(root, *_norm(rel).split("/"))


def _read(root, rel):
    try:
        with open(_path(root, rel), encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _read_bytes(root, rel):
    try:
        with open(_path(root, rel), "rb") as handle:
            return handle.read()
    except OSError:
        return b""


def _exists(root, rel):
    return os.path.isfile(_path(root, rel))


def _sha256(blob):
    return hashlib.sha256(blob).hexdigest()


def _git_blob_sha1(blob):
    prefix = b"blob " + str(len(blob)).encode("ascii") + b"\0"
    return hashlib.sha1(prefix + blob).hexdigest()


def _pinned_url(source_commit, rel):
    encoded = quote(_norm(rel), safe="/")
    return "https://github.com/%s/blob/%s/%s" % (
        REPOSITORY,
        source_commit,
        encoded,
    )


def _valid_commit(value):
    return bool(HEX40.fullmatch(str(value or "").strip().lower()))


def _valid_sha(value):
    return bool(HEX64.fullmatch(str(value or "").strip().lower()))


def _valid_timestamp(value):
    """Require a timezone-aware ISO-8601 timestamp. Invalid is not empty."""
    text = str(value or "").strip()
    if not text:
        return False
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _as_dict(value):
    return value if isinstance(value, dict) else None


def _git_output(root, args):
    try:
        out = subprocess.check_output(
            ["git", "-C", root] + list(args),
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return out.decode("ascii", "replace").strip()


def _git_object_kind(root, sha):
    return _git_output(root, ["cat-file", "-t", sha])


def _git_blob_at(root, source_commit, rel):
    if not _valid_commit(source_commit):
        return None
    spec = "%s:%s" % (source_commit, _norm(rel))
    try:
        return subprocess.check_output(
            ["git", "-C", root, "cat-file", "blob", spec],
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None


def resolve_source_objects(root, source_commit, source_tree):
    """Exact present Git commit + matching tree. Syntax-only pins fail closed."""
    source_commit = str(source_commit or "").strip().lower()
    source_tree = str(source_tree or "").strip().lower()
    if not _valid_commit(source_commit) or not _valid_commit(source_tree):
        raise ValueError("source commit and tree must be exact 40-hex Git objects")
    if _git_object_kind(root, source_commit) != "commit":
        raise ValueError("source commit is not a present Git commit object")
    if _git_object_kind(root, source_tree) != "tree":
        raise ValueError("source tree is not a present Git tree object")
    commit_tree = _git_output(root, ["rev-parse", "--verify", source_commit + "^{tree}"])
    if commit_tree != source_tree:
        raise ValueError("source tree is not the tree of the source commit")
    return source_commit, source_tree


def canonical_json(data):
    """Canonical checked-in representation: sorted keys, UTF-8, LF, newline."""
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def source_evidence(root, rel, source_commit):
    """Bind checkout bytes to the pinned commit blob. Miss/stale never pass."""
    rel = _norm(rel)
    url = _pinned_url(source_commit, rel)
    git_blob = _git_blob_at(root, source_commit, rel)
    checkout_present = _exists(root, rel)
    checkout = _read_bytes(root, rel) if checkout_present else None
    if git_blob is None:
        return {
            "path": rel,
            "status": "FINDER_FAILED",
            "bytes": None,
            "sha256": None,
            "git_blob_sha1": None,
            "url": url,
        }
    git_sha1 = _git_blob_sha1(git_blob)
    if checkout is None:
        return {
            "path": rel,
            "status": "FINDER_FAILED",
            "bytes": None,
            "sha256": None,
            "git_blob_sha1": git_sha1,
            "url": url,
        }
    if checkout != git_blob:
        return {
            "path": rel,
            "status": "STALE_BINDING",
            "bytes": len(checkout),
            "sha256": _sha256(checkout),
            "git_blob_sha1": git_sha1,
            "url": url,
        }
    return {
        "path": rel,
        "status": "PRESENT",
        "bytes": len(git_blob),
        "sha256": _sha256(git_blob),
        "git_blob_sha1": git_sha1,
        "url": url,
    }


def parse_excerpt(blob):
    """Parse the stored 8-byte magic and five little-endian header integers."""
    if len(blob) < 28:
        return {"ok": False, "reason": "header too short"}
    magic = blob[:8].decode("ascii", "replace")
    n_gate, n_wires, n_in, n_out, depth = struct.unpack_from("<IIIII", blob, 8)
    return {
        "ok": True,
        "magic": magic,
        "n_gate": n_gate,
        "n_wires": n_wires,
        "n_in": n_in,
        "n_out": n_out,
        "depth": depth,
        "bytes": len(blob),
        "sha256": _sha256(blob),
    }


def count_archetypes(root):
    counts = {
        "fabricators": 0,
        "tests": 0,
        "docs": 0,
        "html": 0,
        "other_py": 0,
        "status": "FINDER_FAILED",
    }
    base = _path(root, ARCH)
    if not os.path.isdir(base):
        return counts
    counts["status"] = "MEASURED"
    for _, _, files in os.walk(base):
        for name in files:
            if name.endswith(".py"):
                if name.startswith("muhl_fab_"):
                    counts["fabricators"] += 1
                elif name.startswith("test_"):
                    counts["tests"] += 1
                else:
                    counts["other_py"] += 1
            elif name.endswith((".md", ".txt")):
                counts["docs"] += 1
            elif name.endswith(".html"):
                counts["html"] += 1
    return counts


def _expected_header(expected):
    return {
        key: expected.get(key)
        for key in ("magic", "n_gate", "n_wires", "n_in", "n_out", "depth")
    }


def _card_path(name, magic):
    special = {
        "muhl_titanx_forge": "ground/SUBZERO_TITF.md",
        "muhl_titanx_mirror": "ground/SUBZERO_TITM.md",
        "muhl_titanx_commons": "ground/SUBZERO_TITX.md",
    }
    if name in special:
        return special[name]
    code = str(magic or "")[4:] if str(magic or "").startswith("MUHL") else ""
    return "ground/SUBZERO_%s.md" % code


def _component_cards(root, name, source_commit):
    prefix = "muhl_chimera_"
    if not name.startswith(prefix):
        return []
    cards = []
    for component in name[len(prefix) :].split("_"):
        rel = "ground/SUBZERO_%s.md" % component.upper()
        if _exists(root, rel):
            cards.append(source_evidence(root, rel, source_commit))
    return cards


def _binding(receipt, artifact, catalog):
    reasons = []
    allowed = {
        "schema_version",
        "kind",
        "receipt_id",
        "catalog",
        "artifact",
        "checks",
        "runtime_measurement",
        "buyer_acceptance",
        "delivered_at",
        "result_address",
        "payment",
    }
    if set(receipt) - allowed:
        reasons.append("additionalProperties")
    for key in ("artifact", "catalog", "runtime_measurement", "buyer_acceptance"):
        if key in receipt and receipt.get(key) is not None and not isinstance(receipt.get(key), dict):
            reasons.append(key + ".properties")
    if receipt.get("schema_version") != RECEIPT_VERSION:
        reasons.append("schema_version")
    if receipt.get("kind") != "SUBZERO_VALIDATION_RECEIPT":
        reasons.append("kind")
    if not str(receipt.get("receipt_id") or "").strip():
        reasons.append("receipt_id")
    bound_artifact = _as_dict(receipt.get("artifact"))
    if bound_artifact is None or set(bound_artifact) != {
        "name",
        "path",
        "sha256",
    }:
        reasons.append("artifact.properties")
        bound_artifact = {}
    if bound_artifact.get("name") != artifact.get("name"):
        reasons.append("artifact.name")
    if _norm(bound_artifact.get("path")) != _norm(artifact.get("path")):
        reasons.append("artifact.path")
    if bound_artifact.get("sha256") != artifact.get("sha256"):
        reasons.append("artifact.sha256")
    bound_catalog = _as_dict(receipt.get("catalog"))
    if bound_catalog is None or set(bound_catalog) != {
        "source_commit",
        "source_tree",
    }:
        reasons.append("catalog.properties")
        bound_catalog = {}
    if bound_catalog.get("source_commit") != catalog.get("source_commit"):
        reasons.append("catalog.source_commit")
    if bound_catalog.get("source_tree") != catalog.get("source_tree"):
        reasons.append("catalog.source_tree")
    checks = receipt.get("checks") or []
    if not isinstance(checks, list):
        reasons.append("checks")
    else:
        check_keys = {
            "id",
            "status",
            "evidence_path",
            "evidence_sha256",
            "observation",
        }
        for check in checks:
            if not isinstance(check, dict) or set(check) != check_keys:
                reasons.append("checks.properties")
                continue
            if check.get("status") not in ("PASS", "FAIL", "UNKNOWN"):
                reasons.append("checks.status")
            if not _valid_sha(check.get("evidence_sha256")):
                reasons.append("checks.evidence_sha256")
            for key in ("id", "evidence_path", "observation"):
                if not str(check.get(key) or "").strip():
                    reasons.append("checks." + key)
    return reasons


def runtime_receipt_reasons(receipt, artifact, catalog):
    reasons = _binding(receipt, artifact, catalog)
    runtime = _as_dict(receipt.get("runtime_measurement"))
    runtime_keys = {
        "status",
        "run_id",
        "process_id",
        "observed_at",
        "runner_path",
        "runner_sha256",
        "test_path",
        "test_sha256",
        "input_sha256",
        "output_sha256",
    }
    if runtime is None or set(runtime) != runtime_keys:
        reasons.append("runtime_measurement.properties")
        runtime = {}
    for key in ("run_id", "process_id", "observed_at", "runner_path", "test_path"):
        if not str(runtime.get(key) or "").strip():
            reasons.append("runtime_measurement." + key)
    if not _valid_timestamp(runtime.get("observed_at")):
        reasons.append("runtime_measurement.observed_at")
    if runtime.get("status") != "PASS":
        reasons.append("runtime_measurement.status")
    for key in ("runner_sha256", "test_sha256", "input_sha256", "output_sha256"):
        if not _valid_sha(runtime.get(key)):
            reasons.append("runtime_measurement." + key)
    checks = receipt.get("checks") if isinstance(receipt.get("checks"), list) else []
    if not checks:
        reasons.append("checks.empty")
    for check in checks:
        if not isinstance(check, dict) or check.get("status") != "PASS":
            reasons.append("checks.status")
    return sorted(set(reasons))


def customer_receipt_reasons(receipt, artifact, catalog):
    reasons = _binding(receipt, artifact, catalog)
    acceptance = _as_dict(receipt.get("buyer_acceptance"))
    if acceptance is None or set(acceptance) != {
        "status",
        "buyer_reference",
        "accepted_at",
    }:
        reasons.append("buyer_acceptance.properties")
        acceptance = {}
    if acceptance.get("status") != "PASS":
        reasons.append("buyer_acceptance.status")
    for key in ("buyer_reference", "accepted_at"):
        if not str(acceptance.get(key) or "").strip():
            reasons.append("buyer_acceptance." + key)
    if not _valid_timestamp(acceptance.get("accepted_at")):
        reasons.append("buyer_acceptance.accepted_at")
    if not str(receipt.get("delivered_at") or "").strip():
        reasons.append("delivered_at")
    if not _valid_timestamp(receipt.get("delivered_at")):
        reasons.append("delivered_at")
    if not str(receipt.get("result_address") or "").strip():
        reasons.append("result_address")
    checks = receipt.get("checks") if isinstance(receipt.get("checks"), list) else []
    if not checks:
        reasons.append("checks.empty")
    artifact_check = False
    for check in checks:
        if not isinstance(check, dict) or check.get("status") != "PASS":
            reasons.append("checks.status")
            continue
        if (
            check.get("id") == "artifact_sha256"
            and check.get("evidence_sha256") == artifact.get("sha256")
        ):
            artifact_check = True
    if not artifact_check:
        reasons.append("checks.artifact_sha256")
    return sorted(set(reasons))


def classify_evidence(structural_ok, receipts, artifact, catalog):
    """Exclusive evidence class. Presence/Titan/payment fields never escalate."""
    if not structural_ok:
        return "UNKNOWN", [], []
    valid_runtime = []
    valid_customer = []
    for receipt in receipts or []:
        if not isinstance(receipt, dict):
            continue
        if not runtime_receipt_reasons(receipt, artifact, catalog):
            valid_runtime.append(receipt.get("receipt_id"))
        if not customer_receipt_reasons(receipt, artifact, catalog):
            valid_customer.append(receipt.get("receipt_id"))
    if valid_customer:
        return "CUSTOMER_READY", valid_runtime, valid_customer
    if valid_runtime:
        return "RUNTIME_MEASURED", valid_runtime, valid_customer
    return "STRUCTURAL_ONLY", valid_runtime, valid_customer


def _row_paths(expected):
    name = str(expected.get("name") or "")
    stem = name[5:] if name.startswith("muhl_") else name
    container = str(expected.get("container") or (name + ".mno"))
    return {
        "artifact": _norm(os.path.join(EXCERPT_DIR, container)),
        "fabricator": _norm(os.path.join(ARCH, "muhl_fab_%s.py" % stem)),
        "test": _norm(os.path.join(ARCH, "test_muhl_fab_%s.py" % stem)),
        "sidecar": _norm(os.path.join(EXCERPT_DIR, "%s_circuits.json" % stem)),
        "card": _card_path(name, expected.get("magic")),
    }


def build_artifact_row(root, expected, source_commit, source_tree, receipts=(), calibrated=True):
    name = str(expected.get("name") or "").strip()
    paths = _row_paths(expected)
    parsed = parse_excerpt(_read_bytes(root, paths["artifact"]))
    artifact = source_evidence(root, paths["artifact"], source_commit)
    artifact.update({"name": name})
    packet_sha = str(expected.get("sha256") or "").strip().lower()
    header_expected = _expected_header(expected)
    header_actual = {key: parsed.get(key) for key in header_expected}
    checks = {
        "calibration": bool(calibrated),
        "artifact_present": artifact["status"] == "PRESENT",
        "artifact_hash": bool(packet_sha and artifact.get("sha256") == packet_sha),
        "header": bool(parsed.get("ok") and header_actual == header_expected),
    }
    sources = {
        "fabricator": source_evidence(root, paths["fabricator"], source_commit),
        "structural_test": source_evidence(root, paths["test"], source_commit),
        "sidecar": source_evidence(root, paths["sidecar"], source_commit),
        "card": source_evidence(root, paths["card"], source_commit),
        "component_cards": _component_cards(root, name, source_commit),
        "packet": source_evidence(root, PACKET, source_commit),
    }
    for key in STRUCTURAL_SOURCE_KEYS:
        checks[key] = sources[key]["status"] == "PRESENT"
    failures = sorted(key for key, passed in checks.items() if not passed)
    structural_ok = not failures
    binding = {"source_commit": source_commit, "source_tree": source_tree}
    evidence_class, runtime_ids, customer_ids = classify_evidence(
        structural_ok, receipts, artifact, binding
    )
    acceptance_checks = []
    for check_id, passed in sorted(checks.items()):
        source = sources.get(check_id, {})
        if check_id.startswith("artifact") or check_id == "header":
            source = artifact
        acceptance_checks.append(
            {
                "id": check_id,
                "status": "PASS" if passed else "FAIL",
                "evidence_path": source.get("path"),
                "evidence_sha256": source.get("sha256"),
            }
        )
    return {
        "name": name,
        "path": artifact["path"],
        "bytes": artifact.get("bytes"),
        "magic": parsed.get("magic") or "",
        "n_gate": parsed.get("n_gate"),
        "n_wires": parsed.get("n_wires"),
        "n_in": parsed.get("n_in"),
        "n_out": parsed.get("n_out"),
        "depth": parsed.get("depth"),
        "sha256": artifact.get("sha256"),
        "packet_sha256": packet_sha,
        "hash_match": checks["artifact_hash"],
        "label": evidence_class,
        "runtime_measured": evidence_class in ("RUNTIME_MEASURED", "CUSTOMER_READY"),
        "evidence_class": evidence_class,
        "artifact": artifact,
        "header": {
            "status": "MATCH" if checks["header"] else "MISMATCH",
            "actual": header_actual,
            "expected": header_expected,
        },
        "sources": sources,
        "offer_refs": list(OFFER_REFS),
        "acceptance": {
            "status": "PASS" if structural_ok else "FAIL",
            "checks": acceptance_checks,
            "failures": failures,
            "falsifiers": [
                "artifact SHA-256 differs from the packet",
                "stored header differs from the packet",
                "fabricator, structural test, sidecar, or card evidence is missing or stale",
                "named source is not the Git blob at the pinned commit",
                "runtime receipt is not bound to this artifact and source tree",
                "buyer PASS receipt is not bound to this artifact and source tree",
            ],
        },
        "receipts": {"runtime": runtime_ids, "customer": customer_ids},
    }


def _load_packet(root):
    try:
        packet = json.loads(_read(root, PACKET) or "{}")
    except ValueError as exc:
        raise ValueError("packet is not JSON") from exc
    organs = packet.get("organs") if isinstance(packet, dict) else None
    if not isinstance(organs, list) or len(organs) != EXPECTED_EXCERPTS:
        raise ValueError("packet organ search is uncalibrated")
    if len({str(item.get("name")) for item in organs if isinstance(item, dict)}) != EXPECTED_EXCERPTS:
        raise ValueError("packet organ names are not unique")
    return packet, organs


def _load_receipts(paths):
    receipts = []
    for path in paths or []:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        if isinstance(value, list):
            receipts.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            receipts.append(value)
    return receipts


def build_catalog(root, source_commit, source_tree, receipts=()):
    source_commit, source_tree = resolve_source_objects(root, source_commit, source_tree)
    packet, organs = _load_packet(root)
    calibration_hits = [_norm(rel) for rel in CALIBRATION if _exists(root, rel)]
    calibration_misses = [_norm(rel) for rel in CALIBRATION if not _exists(root, rel)]
    calibrated = len(calibration_hits) == len(CALIBRATION)
    rows = [
        build_artifact_row(
            root,
            expected,
            source_commit,
            source_tree,
            receipts=receipts,
            calibrated=calibrated,
        )
        for expected in organs
    ]
    search_paths = set(_norm(rel) for rel in BASE_SEARCH_SPACE)
    for row in rows:
        search_paths.add(row["artifact"]["path"])
        for value in row["sources"].values():
            if isinstance(value, dict) and value.get("path"):
                search_paths.add(value["path"])
            elif isinstance(value, list):
                search_paths.update(item["path"] for item in value if item.get("path"))
    class_counts = {name: 0 for name in EVIDENCE_CLASSES}
    for row in rows:
        class_counts[row["evidence_class"]] += 1
    generator = source_evidence(root, "host/subzero_explorer.py", source_commit)
    receipt_schema = source_evidence(root, RECEIPT_SCHEMA, source_commit)
    offer_catalog = source_evidence(root, "revenue/subzero_buyers/pack.json", source_commit)
    packet_source = source_evidence(root, PACKET, source_commit)
    v2 = {
        "schema_version": 2,
        "spec_id": V2_SPEC_ID,
        "slack_ts": V2_SLACK_TS,
        "source_commit": source_commit,
        "source_tree": source_tree,
        "writer": "host/subzero_explorer.py:build_catalog",
        "deterministic": True,
        "evidence_classes": list(EVIDENCE_CLASSES),
        "search_space": sorted(search_paths),
        "schema": _norm(RECEIPT_SCHEMA),
        "artifact_rows": "rows",
        "presence_never_escalates": True,
        "no_auth": True,
        "no_gate": True,
        "login_required": False,
        "privileged_tier": False,
        "do_not_duplicate_explorer": True,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "SUBZERO_EXPLORER",
        "repository": REPOSITORY,
        "source_commit": source_commit,
        "source_tree": source_tree,
        "slack_ts": SLACK_TS,
        "handoff_id": HANDOFF_ID,
        "subject": "Read-only Subzero Artifact Explorer + validation packet",
        "expected_excerpts": EXPECTED_EXCERPTS,
        "evidence_classes": list(EVIDENCE_CLASSES),
        "source_class_aliases": {
            "CROSS_PROCESS/RUNTIME_MEASURED": "RUNTIME_MEASURED"
        },
        "label": "STRUCTURAL_ONLY" if class_counts["UNKNOWN"] == 0 else "UNKNOWN",
        "host_training": "NOT_SOLD",
        "lda_protocol": {
            "repo": "woahwhattheheck/LocalDeviceAgent",
            "sha": LDA_SHA,
            "path": "host/muhl_subagent_protocol.py",
            "state": LDA_BLOCK,
            "copy_private_lda_source": False,
        },
        "do_not_remint": [
            "demon-redteam-subzero-tech-ip-20260825-04",
            "demon-redteam-subzero-buyers-20260825-05",
            "demon-redteam-subzero-gtm-20260825-06",
            "grok-subzero-buyers-panel-20260825-01",
        ],
        "posting": "OPEN",
        "no_auth": True,
        "no_gate": True,
        "login_required": False,
        "privileged_tier": False,
        "presence_never_escalates": True,
        "v2": v2,
        "generator": generator,
        "receipt_schema": receipt_schema,
        "offer_catalog": offer_catalog,
        "offer_refs": list(OFFER_REFS),
        "packet": {
            "path": _norm(PACKET),
            "sha256": packet_source["sha256"],
            "source": packet_source,
        },
        "search_space": {
            "scope": "explicit public-tree paths only",
            "paths": sorted(search_paths),
            "calibration": {
                "status": "PASS" if calibrated else "FINDER_UNVERIFIED",
                "known_present": [_norm(rel) for rel in CALIBRATION],
                "hits": calibration_hits,
                "misses": calibration_misses,
            },
        },
        "archetypes": count_archetypes(root),
        "summary": {
            "artifact_count": len(rows),
            "hash_match_count": sum(1 for row in rows if row["hash_match"]),
            "class_counts": class_counts,
            "claim_boundary": "synthetic repository evidence only",
        },
        "receipt_template": {
            "schema_version": RECEIPT_VERSION,
            "kind": "SUBZERO_VALIDATION_RECEIPT",
            "catalog": {"source_commit": source_commit, "source_tree": source_tree},
            "buyer_acceptance": {"status": "PENDING"},
        },
        "rows": rows,
    }


def load_catalog(text):
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON", "rows": []}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object", "rows": []}
    if data.get("schema_version") != SCHEMA_VERSION:
        return {"error": "catalog schema_version is not v2", "rows": []}
    if data.get("evidence_classes") != list(EVIDENCE_CLASSES):
        return {"error": "catalog evidence enum differs", "rows": []}
    rows = data.get("rows") or []
    if not isinstance(rows, list) or any(
        row.get("evidence_class") not in EVIDENCE_CLASSES
        or row.get("label") != row.get("evidence_class")
        for row in rows
        if isinstance(row, dict)
    ):
        return {"error": "catalog row evidence class differs", "rows": []}
    data["error"] = ""
    return data


def measure_root(root):
    root = os.path.abspath(root)
    catalog = load_catalog(_read(root, DEFAULT_CATALOG))
    if catalog.get("error"):
        return {
            "measured": False,
            "state": "UNMEASURED",
            "error": catalog["error"],
            "search_space": list(BASE_SEARCH_SPACE),
        }
    try:
        expected = build_catalog(root, catalog.get("source_commit"), catalog.get("source_tree"))
    except ValueError as exc:
        return {
            "measured": False,
            "state": "UNMEASURED",
            "error": str(exc),
            "search_space": list(BASE_SEARCH_SPACE),
        }
    comparable = dict(catalog)
    comparable.pop("error", None)
    matches = canonical_json(comparable) == canonical_json(expected)
    calibration = expected["search_space"]["calibration"]
    return {
        "measured": True,
        "state": "INTEGRATED" if matches and calibration["status"] == "PASS" else "NOT_LANDED",
        "catalog_matches_generator": matches,
        "source_commit": catalog.get("source_commit"),
        "source_tree": catalog.get("source_tree"),
        "calibration": calibration,
        "summary": expected["summary"],
    }


def classify(row):
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "Explorer measurement failed calibration; FINDER_UNVERIFIED, never 0.",
        }
    return {
        "state": row.get("state", "NOT_LANDED"),
        "note": (
            "Catalog deterministically matches its public-tree evidence."
            if row.get("state") == "INTEGRATED"
            else "Catalog differs from deterministic evidence; FINDER_FAILED, never 0."
        ),
    }


def self_test():
    artifact = {"name": "muhl_test", "path": "x.mno", "sha256": "a" * 64}
    catalog = {"source_commit": "b" * 40, "source_tree": "c" * 40}
    payment_only = {
        "schema_version": RECEIPT_VERSION,
        "kind": "SUBZERO_VALIDATION_RECEIPT",
        "receipt_id": "payment-only",
        "artifact": artifact,
        "catalog": catalog,
        "checks": [],
        "payment": {"status": "PAID", "reference": "synthetic"},
        "titan": "PRESENT",
    }
    assert classify_evidence(True, [payment_only], artifact, catalog)[0] == "STRUCTURAL_ONLY"
    assert classify_evidence(False, [], artifact, catalog)[0] == "UNKNOWN"
    assert list(EVIDENCE_CLASSES) == [
        "STRUCTURAL_ONLY",
        "RUNTIME_MEASURED",
        "CUSTOMER_READY",
        "UNKNOWN",
    ]
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build or verify the synthetic Subzero Artifact Explorer"
    )
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--source-commit")
    parser.add_argument("--source-tree")
    parser.add_argument("--receipt", action="append", default=[])
    parser.add_argument(
        "--write-catalog",
        nargs="?",
        const=DEFAULT_CATALOG,
        help="write canonical v2 JSON to PATH (default: ground catalog)",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    if args.write_catalog:
        if not args.source_commit or not args.source_tree:
            parser.error("--write-catalog requires --source-commit and --source-tree")
        catalog = build_catalog(
            os.path.abspath(args.root),
            args.source_commit,
            args.source_tree,
            receipts=_load_receipts(args.receipt),
        )
        destination = _path(os.path.abspath(args.root), args.write_catalog)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with open(destination, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(catalog))
        print(destination)
        return 0
    row = measure_root(args.root)
    payload = {"verdict": classify(row), "row": row}
    print(canonical_json(payload), end="")
    return 0 if payload["verdict"]["state"] == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
