#!/usr/bin/env python3
"""host/stale_manifest.py — KEYB size-agree / hash-disagree is not verified.

Slack 1787638201.498979 (DEMON CORRECTION):
C:\\Users\\lucys\\Desktop\\MUHL_KEYB\\keyb01.manifest.json is dated
2026-08-21T14:23:58Z and claims 430,860 bytes with SHA-256 prefix
a63396.... keyb01.mno is still 430,860 bytes but was modified later
at 2026-08-21T14:25:19Z; measured SHA-256 is
cca2b76224eaab93ed69b42a9b464d42f493ca9d233d693b02cb803bb5cbdfed.

Size agrees. Bytes do not. The public Commons copy of that manifest
is excerpts/20260821/keyb01.manifest.json. This leftover records the
mismatch. It does not rewrite the original manifest. It does not
produce a replacement verified manifest. Intent of the 81-second
post-manifest mutation stays UNRECONCILED. The container is
NOT_VERIFIED. Rook and Titan-census dispositions stay unchanged.

  python3 host/stale_manifest.py
  python3 host/stale_manifest.py --catalog ground/STALE_MANIFEST.json
  python3 host/stale_manifest.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_CATALOG = os.path.join("ground", "STALE_MANIFEST.json")
DEFAULT_MANIFEST = os.path.join("excerpts", "20260821", "keyb01.manifest.json")
CLAIMED_SHA = (
    "a63396b59b0fb9f0ce1366d112c2abd209475aecde2d458f82f9999667f1521e"
)
CITED_SHA = (
    "cca2b76224eaab93ed69b42a9b464d42f493ca9d233d693b02cb803bb5cbdfed"
)
CLAIMED_BYTES = 430860
SLACK_TS = "1787638201.498979"
MOUTHS = ("HELP", "READ", "WRITE", "FIRE", "SURFACE", "ACK")


def load_manifest(text):
    """Parse the public KEYB01 manifest. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "manifest is not JSON"}
    if not isinstance(data, dict):
        return {"error": "manifest is not an object"}
    mouths = data.get("mouths") if isinstance(data.get("mouths"), dict) else {}
    try:
        n_bytes = int(data.get("n_bytes"))
    except (TypeError, ValueError):
        n_bytes = None
    try:
        n_gate = int(data.get("n_gate"))
    except (TypeError, ValueError):
        n_gate = None
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
    return {
        "magic": str(data.get("magic") or "").strip(),
        "path": str(data.get("path") or "").strip(),
        "sha256": str(data.get("sha256") or "").strip().lower(),
        "n_bytes": n_bytes,
        "n_gate": n_gate,
        "depth": depth,
        "n_pos": n_pos,
        "alphabet_width": width,
        "mouths": sorted(str(name) for name in mouths),
        "mouth_ok": all(name in mouths for name in MOUTHS),
    }


def load_catalog(text):
    """Parse the stale-manifest catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    cited = data.get("cited_desktop") if isinstance(data.get("cited_desktop"), dict) else {}
    public = data.get("public_manifest") if isinstance(data.get("public_manifest"), dict) else {}
    unchanged = [
        str(item or "").strip()
        for item in (data.get("unchanged_dispositions") or [])
        if str(item or "").strip()
    ]
    return {
        "source_id": str(data.get("source_id") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "claimed_sha256": str(
            public.get("claimed_sha256") or data.get("claimed_sha256") or ""
        )
        .strip()
        .lower(),
        "cited_sha256": str(
            cited.get("sha256") or data.get("cited_sha256") or ""
        )
        .strip()
        .lower(),
        "cited_n_bytes": _as_int(cited.get("n_bytes") or data.get("cited_n_bytes")),
        "manifest_ts": str(cited.get("manifest_ts") or "").strip(),
        "mno_mtime": str(cited.get("mno_mtime") or "").strip(),
        "intent": str(data.get("intent") or "UNRECONCILED").strip() or "UNRECONCILED",
        "refuse_verified": bool(data.get("refuse_verified", True)),
        "refuse_rewrite": bool(data.get("refuse_rewrite", True)),
        "public_container": str(data.get("public_container") or "ABSENT").strip()
        or "ABSENT",
        "unchanged_dispositions": unchanged,
        "supersedes_hash_only": bool(data.get("supersedes_hash_only", True)),
    }


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def measure_from_parts(manifest_text, catalog_text):
    """Census from already-read public manifest + correction catalog."""
    manifest = load_manifest(manifest_text)
    catalog = load_catalog(catalog_text)
    if manifest.get("error") or catalog.get("error"):
        return {
            "measured": False,
            "error": manifest.get("error") or catalog.get("error"),
            "titan": catalog.get("titan") or "NOT_WRITTEN",
        }
    claimed_sha = manifest.get("sha256") or catalog.get("claimed_sha256") or ""
    cited_sha = catalog.get("cited_sha256") or ""
    claimed_bytes = manifest.get("n_bytes")
    cited_bytes = catalog.get("cited_n_bytes")
    size_agrees = (
        claimed_bytes is not None
        and cited_bytes is not None
        and claimed_bytes == cited_bytes
    )
    hash_agrees = bool(claimed_sha) and bool(cited_sha) and claimed_sha == cited_sha
    public_ok = (
        manifest.get("magic") == "KEYB01v1"
        and claimed_sha == CLAIMED_SHA
        and claimed_bytes == CLAIMED_BYTES
        and manifest.get("mouth_ok") is True
    )
    return {
        "measured": True,
        "public_ok": public_ok,
        "magic": manifest.get("magic") or "",
        "claimed_sha256": claimed_sha,
        "cited_sha256": cited_sha,
        "claimed_n_bytes": claimed_bytes,
        "cited_n_bytes": cited_bytes,
        "size_agrees": size_agrees,
        "hash_agrees": hash_agrees,
        "n_gate": manifest.get("n_gate"),
        "depth": manifest.get("depth"),
        "n_pos": manifest.get("n_pos"),
        "alphabet_width": manifest.get("alphabet_width"),
        "mouths": list(manifest.get("mouths") or []),
        "manifest_ts": catalog.get("manifest_ts") or "",
        "mno_mtime": catalog.get("mno_mtime") or "",
        "intent": catalog.get("intent") or "UNRECONCILED",
        "refuse_verified": bool(catalog.get("refuse_verified")),
        "refuse_rewrite": bool(catalog.get("refuse_rewrite")),
        "public_container": catalog.get("public_container") or "ABSENT",
        "unchanged_count": len(catalog.get("unchanged_dispositions") or []),
        "supersedes_hash_only": bool(catalog.get("supersedes_hash_only")),
        "source_id": catalog.get("source_id") or "",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "verified": False,
        "verdict": "STALE" if size_agrees and not hash_agrees else "UNRECONCILED",
    }


def measure_paths(catalog_path, manifest_path):
    """Read the two files from disk and census them."""
    try:
        with open(catalog_path, encoding="utf-8") as handle:
            catalog_text = handle.read()
        with open(manifest_path, encoding="utf-8") as handle:
            manifest_text = handle.read()
    except OSError as exc:
        return {
            "measured": False,
            "error": str(exc),
            "titan": "NOT_WRITTEN",
        }
    row = measure_from_parts(manifest_text, catalog_text)
    row["catalog_path"] = catalog_path
    row["manifest_path"] = manifest_path
    return row


def classify(row):
    """Turn a measured KEYB hash mismatch into a land-desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "stale-manifest catalog / public keyb01.manifest.json not read. "
                "Absence was not measured."
            ),
        }
    if not row.get("public_ok") or not row.get("cited_sha256"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "public KEYB manifest or cited desktop SHA missing. A Slack "
                "correction is CLAIMED until both sides are named on current main."
            ),
        }
    if not row.get("refuse_verified") or not row.get("refuse_rewrite"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "refuse_verified / refuse_rewrite missing. Do not describe KEYB "
                "as manifest-verified. Do not rewrite the original manifest."
            ),
        }
    if row.get("hash_agrees"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "claimed SHA now equals the cited SHA, but the desktop "
                "container is still UNMEASURED here and intent stays "
                "UNRECONCILED. Do not mint a verified replacement."
            ),
        }
    if not row.get("size_agrees") or row.get("hash_agrees"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "size/hash relationship not the DEMON correction. Record the "
                "exact cited bytes before calling KEYB stale."
            ),
        }
    if row.get("intent") != "UNRECONCILED":
        return {
            "state": "NOT_LANDED",
            "note": (
                "intent must stay UNRECONCILED until an owner-machine inspect "
                "says whether the 81-second post-manifest mutation was intended."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "KEYB leftover is on this file. Size agrees, bytes do not. "
            "Container is NOT_VERIFIED. Do not land, wire, execute, or "
            "describe it as manifest-verified. Original manifest preserved. "
            "Rook and Titan-census stay unchanged. titan NOT_WRITTEN."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record the KEYB stale-manifest hash mismatch"
    )
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_paths(args.catalog, args.manifest)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    manifest = json.dumps(
        {
            "magic": "KEYB01v1",
            "sha256": CLAIMED_SHA,
            "n_bytes": CLAIMED_BYTES,
            "n_gate": 16489,
            "depth": 8,
            "n_pos": 16,
            "alphabet_width": 128,
            "mouths": {name: 1 for name in MOUTHS},
        }
    )
    catalog = json.dumps(
        {
            "slack_ts": SLACK_TS,
            "claimed_sha256": CLAIMED_SHA,
            "cited_sha256": CITED_SHA,
            "cited_n_bytes": CLAIMED_BYTES,
            "cited_desktop": {
                "sha256": CITED_SHA,
                "n_bytes": CLAIMED_BYTES,
                "manifest_ts": "2026-08-21T14:23:58Z",
                "mno_mtime": "2026-08-21T14:25:19Z",
            },
            "public_manifest": {"claimed_sha256": CLAIMED_SHA},
            "intent": "UNRECONCILED",
            "refuse_verified": True,
            "refuse_rewrite": True,
            "public_container": "ABSENT",
            "unchanged_dispositions": ["rook", "titan_census"],
            "supersedes_hash_only": True,
            "titan": "NOT_WRITTEN",
        }
    )
    row = measure_from_parts(manifest, catalog)
    assert row["measured"] is True
    assert row["size_agrees"] is True
    assert row["hash_agrees"] is False
    assert row["verified"] is False
    assert row["verdict"] == "STALE"
    assert row["intent"] == "UNRECONCILED"
    assert row["titan"] == "NOT_WRITTEN"
    assert classify(row)["state"] == "INTEGRATED"
    missing = measure_from_parts(manifest, "{}")
    assert classify(missing)["state"] == "NOT_LANDED"
    matched = json.loads(catalog)
    matched["cited_desktop"]["sha256"] = CLAIMED_SHA
    matched["cited_sha256"] = CLAIMED_SHA
    agree = measure_from_parts(manifest, json.dumps(matched))
    assert agree["hash_agrees"] is True
    assert classify(agree)["state"] == "NOT_LANDED"
    return True


if __name__ == "__main__":
    sys.exit(main())
