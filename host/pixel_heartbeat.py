#!/usr/bin/env python3
"""host/pixel_heartbeat.py — pixels/{name}.json freshness and provenance.

Slack 1787635078.168629 (DEMON): honest session-state → pixels/{name}.json
with freshness/provenance and no fabricated presence, plus a reusable
stale-artifact reconciliation receipt. DEMON takes local exact-SHA
verification after this contract is on current main. RIVET owns render CI.
This leftover measures. It does not invent a heartbeat. It does not
remint demon-side-harness-offer-20260825-01.

A Slack offer is CLAIMED. Missing pixels/ or index is NOT_LANDED.
Stale or unlisted artifacts are CANDIDATE. Fresh valid heartbeats
that match the index are INTEGRATED. titan: NOT_WRITTEN.

  python3 host/pixel_heartbeat.py
  python3 host/pixel_heartbeat.py --root .
  python3 host/pixel_heartbeat.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone


REQUIRED = ("from", "ts", "src")
OPTIONAL = ("path", "verb", "on", "sha")
HOT_SECONDS = 2 * 3600
QUIET_SECONDS = 12 * 3600
DEFAULT_CATALOG = os.path.join("ground", "PIXEL_HEARTBEAT.json")


def utc_now(now=None):
    """Return an aware UTC datetime. Invalid now falls back to wall clock."""
    if now is None:
        return datetime.now(timezone.utc)
    if isinstance(now, datetime):
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc)
    parsed = parse_ts(now)
    if parsed is None:
        return datetime.now(timezone.utc)
    return parsed


def parse_ts(value):
    """Parse an ISO timestamp. Invalid is None, not stillness."""
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def claim_from_name(name):
    """PLAYER2.json → PLAYER2. Empty name is empty claim."""
    stem = os.path.basename(str(name or "")).strip()
    if stem.lower().endswith(".json"):
        stem = stem[:-5]
    return stem.upper()


def load_index(text):
    """Parse pixels/index.json. Invalid input fails closed, never as empty."""
    raw = str(text if text is not None else "")
    if not raw.strip():
        raise ValueError("pixels/index.json is blank")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ValueError("pixels/index.json is not JSON") from exc
    if not isinstance(data, list):
        raise ValueError("pixels/index.json is not a list")
    names = []
    seen = set()
    for item in data:
        name = str(item or "").strip()
        if not name.endswith(".json"):
            name = name + ".json"
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def parse_heartbeat(name, text):
    """Parse one pixels/{name}.json body. Invalid is measured, not invented."""
    claim = claim_from_name(name)
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {
            "name": os.path.basename(str(name or "")),
            "claim": claim,
            "valid": False,
            "fabricated": False,
            "freshness": "INVALID",
            "missing": list(REQUIRED),
            "error": "heartbeat is not JSON",
        }
    if not isinstance(data, dict):
        return {
            "name": os.path.basename(str(name or "")),
            "claim": claim,
            "valid": False,
            "fabricated": False,
            "freshness": "INVALID",
            "missing": list(REQUIRED),
            "error": "heartbeat is not an object",
        }
    missing = [key for key in REQUIRED if not str(data.get(key) or "").strip()]
    src = str(data.get("src") or "").strip()
    from_claim = str(data.get("from") or "").strip().upper()
    guessed = "guessed" in src.lower() and not str(data.get("path") or "").strip()
    mismatch = bool(from_claim and claim and from_claim != claim)
    fabricated = (not src) or guessed or mismatch
    return {
        "name": os.path.basename(str(name or "")),
        "claim": claim,
        "from": from_claim,
        "path": str(data.get("path") or "").strip(),
        "verb": str(data.get("verb") or "").strip(),
        "on": str(data.get("on") or "").strip(),
        "ts": str(data.get("ts") or "").strip(),
        "src": src,
        "sha": str(data.get("sha") or "").strip(),
        "valid": not missing,
        "fabricated": fabricated,
        "freshness": "INVALID" if missing else "UNMEASURED",
        "missing": missing,
        "error": "",
    }


def freshness_of(row, now=None):
    """HOT < 2h, QUIET < 12h, else STALE. Invalid ts is INVALID."""
    row = dict(row or {})
    if not row.get("valid"):
        row["freshness"] = "INVALID"
        row["age_seconds"] = None
        return row
    stamp = parse_ts(row.get("ts"))
    if stamp is None:
        row["valid"] = False
        row["freshness"] = "INVALID"
        row["age_seconds"] = None
        row["error"] = "ts is not ISO"
        return row
    age = (utc_now(now) - stamp).total_seconds()
    row["age_seconds"] = int(age)
    if age < HOT_SECONDS:
        row["freshness"] = "HOT"
    elif age < QUIET_SECONDS:
        row["freshness"] = "QUIET"
    else:
        row["freshness"] = "STALE"
    return row


def reconcile_index(index_names, file_names):
    """Listed-missing and unlisted files. Absence is a measurement."""
    listed = [str(name or "").strip() for name in (index_names or []) if str(name or "").strip()]
    files = [str(name or "").strip() for name in (file_names or []) if str(name or "").strip()]
    listed_set = set(listed)
    file_set = set(files)
    return {
        "listed": listed,
        "files": files,
        "listed_missing": [name for name in listed if name not in file_set],
        "unlisted": [name for name in files if name not in listed_set],
    }


def finder_failure(error, index_present=False, root="", pixels_dir=""):
    """Return an explicit unmeasured finder result with nullable counts."""
    row = {
        "measured": False,
        "index_present": bool(index_present),
        "heartbeats": None,
        "heartbeat_count": None,
        "stale": None,
        "hot": None,
        "quiet": None,
        "invalid": None,
        "fabricated": None,
        "listed": None,
        "files": None,
        "listed_missing": None,
        "unlisted": None,
        "fabricate": False,
        "titan": "NOT_WRITTEN",
        "error": str(error or "pixel heartbeat finder failed")
        + ". FINDER-FAILED, never an empty heartbeat census.",
    }
    if root:
        row["root"] = root
    if pixels_dir:
        row["pixels_dir"] = pixels_dir
    return row


def classify(row):
    """Turn a measured pixel census into a land-desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "pixels/ listing not read. Absence was not measured, "
                "not stillness."
            ),
        }
    if not row.get("index_present"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "pixels/index.json missing. Pixel-heartbeat / "
                "session-state / freshness-provenance talk is CLAIMED "
                "until the contract ships."
            ),
        }
    hearts = list(row.get("heartbeats") or [])
    if not hearts and not (row.get("listed") or []):
        return {
            "state": "NOT_LANDED",
            "note": (
                "pixels/ has no committed heartbeats. Do not invent "
                "presence. A Slack offer is not a file."
            ),
        }
    fabricated = [item["name"] for item in hearts if item.get("fabricated")]
    invalid = [item["name"] for item in hearts if not item.get("valid")]
    stale = [item["name"] for item in hearts if item.get("freshness") == "STALE"]
    missing = list(row.get("listed_missing") or [])
    unlisted = list(row.get("unlisted") or [])
    if fabricated:
        return {
            "state": "CANDIDATE",
            "note": (
                "fabricated or claim-mismatched heartbeat: %s. "
                "Do not invent presence."
            )
            % ", ".join(fabricated),
        }
    if invalid or missing or unlisted or stale:
        parts = []
        if stale:
            parts.append("stale: " + ", ".join(stale))
        if invalid:
            parts.append("invalid: " + ", ".join(invalid))
        if missing:
            parts.append("listed-missing: " + ", ".join(missing))
        if unlisted:
            parts.append("unlisted: " + ", ".join(unlisted))
        return {
            "state": "CANDIDATE",
            "note": (
                "pixel-heartbeat contract measured. "
                + "; ".join(parts)
                + ". Slack is not HEAD. Do not fabricate a refresh."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "all %s listed heartbeats are valid, indexed, and fresh. "
            "Committed, not guessed. titan NOT_WRITTEN."
        )
        % len(hearts),
    }


def measure_from_rows(index_text, files, now=None):
    """Pure measurer so tests do not need a live clock."""
    if index_text is None:
        listed = []
    else:
        try:
            listed = load_index(index_text)
        except (TypeError, ValueError) as exc:
            return finder_failure(exc, index_present=True)
    names = []
    hearts = []
    for item in files or []:
        name = os.path.basename(str(item.get("name") or "").strip())
        if not name or name == "index.json":
            continue
        if not name.endswith(".json"):
            continue
        names.append(name)
        row = freshness_of(parse_heartbeat(name, item.get("text")), now)
        hearts.append(row)
    recon = reconcile_index(listed, names)
    return {
        "measured": True,
        "index_present": index_text is not None,
        "heartbeats": hearts,
        "heartbeat_count": len(hearts),
        "stale": [item["name"] for item in hearts if item.get("freshness") == "STALE"],
        "hot": [item["name"] for item in hearts if item.get("freshness") == "HOT"],
        "quiet": [item["name"] for item in hearts if item.get("freshness") == "QUIET"],
        "invalid": [item["name"] for item in hearts if not item.get("valid")],
        "fabricated": [item["name"] for item in hearts if item.get("fabricated")],
        "listed": recon["listed"],
        "files": recon["files"],
        "listed_missing": recon["listed_missing"],
        "unlisted": recon["unlisted"],
        "fabricate": False,
        "titan": "NOT_WRITTEN",
    }


def measure_root(root, now=None):
    """Read pixels/ from a tree. Missing dir is measured empty, not invented."""
    base = os.path.abspath(root)
    pixel_dir = os.path.join(base, "pixels")
    index_path = os.path.join(pixel_dir, "index.json")
    if not os.path.isdir(pixel_dir):
        return {
            "measured": True,
            "index_present": False,
            "heartbeats": [],
            "heartbeat_count": 0,
            "stale": [],
            "hot": [],
            "quiet": [],
            "invalid": [],
            "fabricated": [],
            "listed": [],
            "files": [],
            "listed_missing": [],
            "unlisted": [],
            "fabricate": False,
            "titan": "NOT_WRITTEN",
            "root": base,
            "error": "pixels/ missing",
        }
    index_text = None
    index_present = os.path.isfile(index_path)
    if index_present:
        try:
            with open(index_path, "r", encoding="utf-8") as handle:
                index_text = handle.read()
        except OSError as exc:
            return finder_failure(
                "pixels/index.json read failed: %s" % exc,
                index_present=True,
                root=base,
                pixels_dir=pixel_dir,
            )
    files = []
    try:
        listing = sorted(os.listdir(pixel_dir))
    except OSError as exc:
        return finder_failure(
            "pixels/ listing failed: %s" % exc,
            index_present=index_present,
            root=base,
            pixels_dir=pixel_dir,
        )
    for name in listing:
        if name == "index.json" or not name.endswith(".json"):
            continue
        path = os.path.join(pixel_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                files.append({"name": name, "text": handle.read()})
        except OSError as exc:
            return finder_failure(
                "heartbeat read failed for %s: %s" % (name, exc),
                index_present=index_present,
                root=base,
                pixels_dir=pixel_dir,
            )
    row = measure_from_rows(index_text, files, now)
    row["root"] = base
    row["pixels_dir"] = pixel_dir
    return row


def catalog_from_row(row, slack_ts="1787635078.168629"):
    """Reusable stale-artifact reconciliation receipt."""
    row = row or {}
    return {
        "source_id": "demon-side-harness-offer-20260825-01",
        "slack_ts": slack_ts,
        "subject": "DEMON pixel-heartbeat contract — freshness/provenance, no fabricated presence",
        "index": list(row.get("listed") or []),
        "files": list(row.get("files") or []),
        "heartbeats": [
            {
                "name": item.get("name"),
                "from": item.get("from"),
                "ts": item.get("ts"),
                "src": item.get("src"),
                "path": item.get("path"),
                "freshness": item.get("freshness"),
                "age_seconds": item.get("age_seconds"),
                "valid": item.get("valid"),
                "fabricated": item.get("fabricated"),
            }
            for item in (row.get("heartbeats") or [])
        ],
        "stale": list(row.get("stale") or []),
        "listed_missing": list(row.get("listed_missing") or []),
        "unlisted": list(row.get("unlisted") or []),
        "fabricate": False,
        "hands_off": [
            "host/render_check.py",
            "rivet-render-check-ci",
            "codex/cml-latent-speech-20260824",
            "dio titan",
            "grok revenue",
            "claude pfc",
            "demon-side-harness-offer-20260825-01",
        ],
        "titan": "NOT_WRITTEN",
        "note": (
            "Do not remint the DEMON offer id. Do not invent a heartbeat. "
            "Local exact-SHA verification stays with DEMON. "
            "RIVET owns render CI."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure pixels/{name}.json freshness and provenance"
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--now", default="", help="ISO now for deterministic age")
    parser.add_argument(
        "--write-catalog",
        default="",
        help="optional path to write the reconciliation receipt",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    now = args.now or None
    row = measure_root(args.root, now)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    payload["catalog"] = catalog_from_row(row)
    if args.write_catalog:
        dest = os.path.abspath(args.write_catalog)
        with open(dest, "w", encoding="utf-8") as handle:
            json.dump(payload["catalog"], handle, indent=2, sort_keys=True)
            handle.write("\n")
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert "not stillness" in empty["note"]
    missing = measure_from_rows(None, [])
    assert missing["index_present"] is False
    assert classify(missing)["state"] == "NOT_LANDED"
    vacant = measure_from_rows("[]", [])
    assert vacant["index_present"] is True
    assert classify(vacant)["state"] == "NOT_LANDED"
    broken = measure_from_rows("{", [])
    assert broken["measured"] is False
    assert broken["heartbeat_count"] is None
    assert "FINDER-FAILED" in broken["error"]
    assert classify(broken)["state"] == "UNMEASURED"
    now = "2026-08-25T05:18:00Z"
    fresh = measure_from_rows(
        '["PLAYER2.json"]',
        [
            {
                "name": "PLAYER2.json",
                "text": json.dumps(
                    {
                        "from": "PLAYER2",
                        "path": "pixel.html",
                        "verb": "building",
                        "on": "pc",
                        "ts": "2026-08-25T04:00:00Z",
                        "src": "session wrote pixel.html",
                    }
                ),
            }
        ],
        now,
    )
    assert fresh["hot"] == ["PLAYER2.json"]
    assert not fresh["fabricate"]
    assert classify(fresh)["state"] == "INTEGRATED"
    stale = measure_from_rows(
        '["PLAYER2.json"]',
        [
            {
                "name": "PLAYER2.json",
                "text": json.dumps(
                    {
                        "from": "PLAYER2",
                        "path": "pixel.html",
                        "verb": "building pixel floor",
                        "on": "pc",
                        "ts": "2026-08-20T11:05:00Z",
                        "src": "Cursor side chat — PLAYER2.",
                    }
                ),
            }
        ],
        now,
    )
    assert stale["stale"] == ["PLAYER2.json"]
    assert classify(stale)["state"] == "CANDIDATE"
    fake = measure_from_rows(
        '["DEMON.json"]',
        [
            {
                "name": "DEMON.json",
                "text": json.dumps(
                    {
                        "from": "DEMON",
                        "ts": "2026-08-25T04:00:00Z",
                        "src": "guessed search",
                    }
                ),
            }
        ],
        now,
    )
    assert fake["fabricated"] == ["DEMON.json"]
    assert classify(fake)["state"] == "CANDIDATE"
    assert "invent presence" in classify(fake)["note"]
    return True


if __name__ == "__main__":
    sys.exit(main())
