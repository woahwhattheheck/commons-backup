#!/usr/bin/env python3
"""Fail-closed validator for the Commons board feed corpus sample.

Re-hashes the frozen sample file, recomputes the recorded window statistics
from the sample bytes, re-runs the secret/PII scan, and refuses any drift,
license promotion, release readiness, or invented commercial truth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


DATA_PATH = "revenue/data/board_feed_corpus.json"
SCHEMA_PATH = "revenue/data/board_feed_corpus.schema.json"
ENTRY_IDS = ("board-feed-sample-20260830",)

RULES = {
    "PRIVATE_KEY": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GITHUB_TOKEN": re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}"),
    "SLACK_TOKEN": re.compile(rb"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "AWS_KEY": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "STRIPE_SECRET": re.compile(rb"[sr]k_live_[A-Za-z0-9]{10,}"),
    "BEARER": re.compile(rb"Bearer [A-Za-z0-9._-]{20,}"),
    "PASSWORD": re.compile(rb"(?i)password\s*[:=]\s*\S+"),
    "EMAIL": re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "PHONE": re.compile(rb"(?<!\d)(?:\+1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)"),
}


class CorpusError(Exception):
    pass


def scan_bytes(raw: bytes) -> dict:
    return {name: len(rule.findall(raw)) for name, rule in RULES.items()}


def load(root: Path):
    data = json.loads((root / DATA_PATH).read_text(encoding="utf-8"))
    schema = json.loads((root / SCHEMA_PATH).read_text(encoding="utf-8"))
    return data, schema


def _git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _window_stats(rows: list) -> dict:
    froms = {}
    kinds = {"ACTION": 0, "POST": 0, "slack_message": 0, "slack_thread_reply": 0, "untyped": 0}
    tss = []
    for row in rows:
        seat = str(row.get("from", ""))
        froms[seat] = froms.get(seat, 0) + 1
        kind = str(row.get("kind", "") or "")
        kinds[kind if kind in kinds else "untyped"] += 1
        tss.append(str(row.get("ts", "")))
    tss.sort()
    top = sorted(froms.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    return {
        "rows": len(rows),
        "first_ts": tss[0] if tss else "",
        "last_ts": tss[-1] if tss else "",
        "distinct_froms": len(froms),
        "kinds": kinds,
        "top_seats": dict(top),
    }


def validate(root: Path, data: dict, schema: dict) -> dict:
    if data.get("schema_version") != "commons-board-feed-corpus/v1":
        raise CorpusError("schema version drift")
    if [entry["entry_id"] for entry in data["entries"]] != list(ENTRY_IDS):
        raise CorpusError("entry set drift")

    recorded_scan = data["scan"]["hit_counts"]
    if any(count != 0 for count in recorded_scan.values()):
        raise CorpusError("recorded scan contains hits")

    for entry in data["entries"]:
        sample = root / entry["sample_path"]
        if not sample.is_file():
            raise CorpusError("sample file missing: " + entry["sample_path"])
        raw = sample.read_bytes()
        if len(raw) != entry["sample_bytes"]:
            raise CorpusError("sample byte drift: " + entry["entry_id"])
        if hashlib.sha256(raw).hexdigest() != entry["sample_sha256"]:
            raise CorpusError("sample SHA-256 drift: " + entry["entry_id"])
        if _git_blob_sha(raw) != entry["sample_blob_sha"]:
            raise CorpusError("sample blob drift: " + entry["entry_id"])
        live_hits = scan_bytes(raw)
        if any(live_hits.values()):
            raise CorpusError("live scan contains hits: " + entry["entry_id"])
        for key in ("customer_material", "outreach_material"):
            if entry[key]:
                raise CorpusError("excluded material present: " + key)

        rows = json.loads(raw.decode("utf-8"))
        if not isinstance(rows, list):
            raise CorpusError("sample is not a row array")
        stats = _window_stats(rows)
        window = data["window"]
        for key in ("rows", "first_ts", "last_ts", "distinct_froms", "kinds", "top_seats"):
            if stats[key] != window[key]:
                raise CorpusError("window stats drift: " + key)

    review = data["sensitivity_review"]
    if review["status"] != "PASS" or review["files_reviewed"] != len(data["entries"]):
        raise CorpusError("sensitivity review incomplete")

    license_block = data["license"]
    if license_block["status"] != "NOASSERTION" or license_block["reuse_rights_verified"]:
        raise CorpusError("license must remain NOASSERTION until a rights-holder decision is recorded")

    release = data["release"]
    if release["state"] != "BLOCKED_LICENSE_REQUIRED" or release["transfer_ready"]:
        raise CorpusError("release must remain license-blocked")

    truth = data["truth"]
    if any(truth.values()):
        raise CorpusError("record may not invent buyer, agreement, delivery, or cash truth")

    return {
        "status": "VALID",
        "entries": len(data["entries"]),
        "rows": data["window"]["rows"],
        "distinct_froms": data["window"]["distinct_froms"],
        "scan_hits": 0,
        "release_state": release["state"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate the Commons board feed corpus sample.")
    parser.add_argument("command", choices=["validate"])
    parser.add_argument("--root", default=".", help="repository root")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    data, schema = load(root)
    result = validate(root, data, schema)
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
