#!/usr/bin/env python3
"""host/working_builds.py — Slack machine-only list is not a land.

Slack 1787637681.321149 (DEMON UTILIZATION_REPORT / MACHINE-ONLY
WORKING BUILDS): three owner-Desktop artifacts were named. Talk that
lists them is CLAIMED until this leftover measures current-main
equivalents and names a disposition per artifact: integrate,
superseded, or quarantine.

This leftover does not upload model or container bytes. It does not
execute WRITE/FIRE/Titan mutations. It does not copy private Desktop
packages onto Commons. DIO/JOJO keep the owner-machine hash lanes.

  python3 host/working_builds.py
  python3 host/working_builds.py --root .
  python3 host/working_builds.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "WORKING_BUILDS.json")
SLACK_TS = "1787637681.321149"
KEYB_MANIFEST = os.path.join("excerpts", "20260821", "keyb01.manifest.json")
KEYB_FAB = os.path.join("infra", "host", "muhl_fab_keyb01.py")
KEYB_ABI = os.path.join("infra", "host", "muhl_keyb01_abi.py")
ROOK_RESUME = os.path.join("muhl", "containers", "MUHLNICKEL_ROOKERY", "RESUME.md")
TRAIN_POST = os.path.join("p", "p1-train-subzero-surface-20260818-01.md")
KEYB_CONTAINER_SHA = (
    "a63396b59b0fb9f0ce1366d112c2abd209475aecde2d458f82f9999667f1521e"
)
KEYB_STALE_SHA = KEYB_CONTAINER_SHA
KEYB_BYTES = 430860
VALID_DISPOSITIONS = ("INTEGRATE", "SUPERSEDED", "QUARANTINE", "UNRECONCILED")
KEYB_DEPTH = 8
KEYB_MOUTHS = ("HELP", "READ", "WRITE", "FIRE", "SURFACE", "ACK")
ABSENT_PATHS = (
    "rook-resident-native",
    "src/rook_native",
    "state/session-run.json",
    "evolve.json",
    "keyb01.mno",
    os.path.join("excerpts", "20260821", "keyb01.mno"),
    "TRAIN_CIRCUITS_FROM_FILE.json",
    os.path.join("MUHL_KITE1_SPIKE", "TRAIN_CIRCUITS_FROM_FILE.json"),
)
CIRCUIT_MARKERS = (
    "perceptron LEARNING STEP. 200/200",
    "60/60 byte-exact",
    "200/200.",
    "120/120.",
)


def _exists(root, rel):
    return os.path.exists(os.path.join(root, rel))


def _read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def load_catalog(text):
    """Parse the working-builds catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    artifacts = []
    for item in data.get("artifacts") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("id") or item.get("name") or "").strip()
        if not name:
            continue
        artifacts.append(
            {
                "id": name,
                "disposition": str(item.get("disposition") or "").strip().upper(),
                "original_disposition": str(
                    item.get("original_disposition") or ""
                ).strip().upper(),
                "claimed_path": str(item.get("claimed_path") or "").strip(),
                "hash_state": str(item.get("hash_state") or "").strip().upper(),
                "verified": bool(item.get("verified")),
            }
        )
    return {
        "source_id": str(data.get("source_id") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "refuse_upload": bool(data.get("refuse_upload", True)),
        "artifacts": artifacts,
        "hands_off": [
            str(item or "").strip()
            for item in (data.get("hands_off") or [])
            if str(item or "").strip()
        ],
    }


def _keyb_manifest_row(text):
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"ok": False}
    if not isinstance(data, dict):
        return {"ok": False}
    mouths = data.get("mouths") if isinstance(data.get("mouths"), dict) else {}
    sha = str(data.get("sha256") or "").strip().lower()
    try:
        n_bytes = int(data.get("n_bytes"))
    except (TypeError, ValueError):
        n_bytes = None
    try:
        depth = int(data.get("depth"))
    except (TypeError, ValueError):
        depth = None
    try:
        n_pos = int(data.get("n_pos"))
    except (TypeError, ValueError):
        n_pos = None
    try:
        width = int(data.get("alphabet_width"))
    except (TypeError, ValueError):
        width = None
    mouth_ok = all(name in mouths for name in KEYB_MOUTHS)
    structural = bool(
        n_bytes == KEYB_BYTES
        and depth == KEYB_DEPTH
        and n_pos == 16
        and width == 128
        and mouth_ok
    )
    stale = sha.startswith("a63396") or sha == KEYB_STALE_SHA
    return {
        "ok": structural,
        "verified": False,
        "hash_state": "STALE" if stale and structural else ("PRESENT" if structural else "UNMEASURED"),
        "sha256": sha,
        "n_bytes": n_bytes,
        "depth": depth,
        "n_pos": n_pos,
        "alphabet_width": width,
        "mouths": sorted(mouths),
    }


def _keyb_check_from_abi(text):
    body = str(text or "")
    if "FORBIDDEN" in body and (
        "[local]" in body or "forbidden dest" in body.lower()
    ):
        return "refuse_forbidden_dest"
    if "--check" in body:
        return "check_named"
    return "UNMEASURED"


def measure_from_rows(facts):
    """Census from already-read filesystem facts. Missing facts stay named."""
    facts = facts or {}
    rook_package = bool(facts.get("rook_package"))
    rook_resume = bool(facts.get("rook_resume"))
    if rook_package:
        rook = "INTEGRATED"
        rook_disposition = "INTEGRATE"
    elif rook_resume:
        rook = "STRANDED"
        rook_disposition = "QUARANTINE"
    else:
        rook = "NOT_LANDED"
        rook_disposition = "QUARANTINE"
    keyb_manifest = bool(facts.get("keyb_manifest"))
    keyb_container = bool(facts.get("keyb_container"))
    keyb_fab = bool(facts.get("keyb_fab"))
    keyb_hash_state = str(facts.get("keyb_hash_state") or "").upper()
    if keyb_container:
        keyb = "INTEGRATED"
        keyb_disposition = "INTEGRATE"
    elif keyb_manifest and keyb_fab:
        keyb = "STRANDED"
        keyb_disposition = "QUARANTINE"
    elif keyb_manifest:
        keyb = "STRANDED"
        keyb_disposition = "QUARANTINE"
    else:
        keyb = "NOT_LANDED"
        keyb_disposition = "QUARANTINE"
    if not keyb_hash_state:
        keyb_hash_state = "STALE" if keyb_manifest else "UNMEASURED"
    train_json = bool(facts.get("train_json"))
    train_post = bool(facts.get("train_post"))
    if train_json:
        titan_census = "INTEGRATED"
        titan_disposition = "INTEGRATE"
        titan_original_disposition = "INTEGRATE"
    elif train_post:
        titan_census = "STRANDED"
        titan_disposition = "UNRECONCILED"
        titan_original_disposition = "SUPERSEDED"
    else:
        titan_census = "NOT_LANDED"
        titan_disposition = "QUARANTINE"
        titan_original_disposition = "QUARANTINE"
    return {
        "measured": True,
        "rook": rook,
        "rook_package": rook_package,
        "rook_resume": rook_resume,
        "rook_disposition": rook_disposition,
        "keyb": keyb,
        "keyb_manifest": keyb_manifest,
        "keyb_container": keyb_container,
        "keyb_fab": keyb_fab,
        "keyb_check": facts.get("keyb_check") or "UNMEASURED",
        "keyb_disposition": keyb_disposition,
        "keyb_hash_state": keyb_hash_state,
        "keyb_verified": False,
        "titan_census": titan_census,
        "train_json": train_json,
        "train_post": train_post,
        "titan_disposition": titan_disposition,
        "titan_original_disposition": titan_original_disposition,
        "refuse_upload": bool(facts.get("refuse_upload", True)),
        "lane_count": 3,
        "slack_ts": facts.get("slack_ts") or SLACK_TS,
    }


def measure_tree(root, catalog_text=""):
    """Read the current tree and census the three named working builds."""
    catalog = load_catalog(catalog_text)
    if catalog.get("error"):
        return {
            "measured": False,
            "error": catalog["error"],
            "titan_write": "NOT_WRITTEN",
        }
    manifest = _keyb_manifest_row(_read(root, KEYB_MANIFEST))
    train_body = _read(root, TRAIN_POST)
    facts = {
        "rook_package": _exists(root, "rook-resident-native")
        or _exists(root, os.path.join("src", "rook_native")),
        "rook_resume": _exists(root, ROOK_RESUME),
        "keyb_manifest": manifest.get("ok") is True,
        "keyb_container": _exists(root, "keyb01.mno")
        or _exists(root, os.path.join("excerpts", "20260821", "keyb01.mno")),
        "keyb_fab": _exists(root, KEYB_FAB),
        "keyb_check": _keyb_check_from_abi(_read(root, KEYB_ABI)),
        "keyb_hash_state": manifest.get("hash_state") or "",
        "train_json": _exists(root, "TRAIN_CIRCUITS_FROM_FILE.json")
        or _exists(
            root, os.path.join("MUHL_KITE1_SPIKE", "TRAIN_CIRCUITS_FROM_FILE.json")
        ),
        "train_post": all(marker in train_body for marker in CIRCUIT_MARKERS),
        "refuse_upload": catalog.get("refuse_upload", True),
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
    }
    row = measure_from_rows(facts)
    row["root"] = root
    row["titan_write"] = catalog.get("titan") or "NOT_WRITTEN"
    row["source_id"] = catalog.get("source_id") or ""
    row["keyb_sha256"] = manifest.get("sha256") or ""
    row["keyb_hash_state"] = manifest.get("hash_state") or row.get("keyb_hash_state") or ""
    row["keyb_verified"] = False
    row["catalog_artifacts"] = len(catalog.get("artifacts") or [])
    row["absent_paths"] = [
        rel.replace("\\", "/")
        for rel in ABSENT_PATHS
        if not _exists(root, rel)
    ]
    return row


def classify(row):
    """The leftover is INTEGRATED when all three dispositions are named."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "working-builds catalog / tree listing not read. "
                "Absence was not stillness."
            ),
        }
    lanes = (row.get("rook"), row.get("keyb"), row.get("titan_census"))
    dispositions = (
        row.get("rook_disposition"),
        row.get("keyb_disposition"),
        row.get("titan_disposition"),
    )
    if any(item in (None, "", "UNMEASURED", "NOT_LANDED") for item in lanes):
        return {
            "state": "NOT_LANDED",
            "note": (
                "one or more of the three working builds was not measured. "
                "A Slack MACHINE-ONLY WORKING BUILDS report is CLAIMED until "
                "the census names every leftover."
            ),
        }
    if any(item not in VALID_DISPOSITIONS for item in dispositions):
        return {
            "state": "NOT_LANDED",
            "note": (
                "a disposition is missing. Name integrate, superseded, "
                "quarantine, or unreconciled per artifact. Absence is not "
                "SUPERSEDED. Do not upload model/container bytes."
            ),
        }
    if not row.get("refuse_upload"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "refuse_upload is off. Do not upload model/container bytes "
                "or execute WRITE/FIRE/Titan mutations from this leftover."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "three-item working-builds provenance is measured on this tree. "
            "rook-resident-native stays QUARANTINE (private Desktop package; "
            "canonical equivalent is MUHLNICKEL_ROOKERY/RESUME.md). "
            "keyb01.mno stays QUARANTINE; public SHA a63396 is STALE / "
            "NOT_VERIFIED (size agrees, bytes do not). "
            "TRAIN_CIRCUITS_FROM_FILE.json absence is UNRECONCILED / "
            "FINDER-FAILED, not SUPERSEDED. The four named scores on "
            "p/p1-train-subzero-surface-20260818-01.md stay present; the "
            "386MB companion stays QUARANTINE. A Slack list is still not "
            "the file."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the three machine-only working builds on current main"
    )
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    try:
        with open(args.catalog, encoding="utf-8") as handle:
            catalog_text = handle.read()
    except OSError as exc:
        payload = {
            "measured": False,
            "error": str(exc),
            "state": "UNMEASURED",
            "note": "catalog missing. Absence was not stillness.",
        }
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    row = measure_tree(args.root, catalog_text)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    live = measure_from_rows(
        {
            "rook_package": False,
            "rook_resume": True,
            "keyb_manifest": True,
            "keyb_container": False,
            "keyb_fab": True,
            "keyb_check": "refuse_forbidden_dest",
            "keyb_hash_state": "STALE",
            "train_json": False,
            "train_post": True,
            "refuse_upload": True,
        }
    )
    assert live["rook"] == "STRANDED"
    assert live["rook_disposition"] == "QUARANTINE"
    assert live["keyb"] == "STRANDED"
    assert live["keyb_disposition"] == "QUARANTINE"
    assert live["keyb_hash_state"] == "STALE"
    assert live["keyb_verified"] is False
    assert live["titan_census"] == "STRANDED"
    assert live["titan_disposition"] == "UNRECONCILED"
    assert live["titan_original_disposition"] == "SUPERSEDED"
    assert live["lane_count"] == 3
    assert classify(live)["state"] == "INTEGRATED"
    uploaded = dict(live)
    uploaded["refuse_upload"] = False
    assert classify(uploaded)["state"] == "NOT_LANDED"
    missing = measure_from_rows({"rook_package": False})
    assert missing["titan_census"] == "NOT_LANDED"
    assert classify(missing)["state"] == "NOT_LANDED"
    catalog = load_catalog('{"not":"valid-shape"')
    assert catalog.get("error")
    return True


if __name__ == "__main__":
    sys.exit(main())
