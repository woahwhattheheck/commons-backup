#!/usr/bin/env python3
"""host/stale_spec.py — local SESSION_GROUNDING is not standing law.

Slack 1787635067.695619 (DEMON errata / stale-spec reconciliation):
the local Desktop/MUHL_GO/SESSION_GROUNDING.md copy is one
historical/session-bound specification input. Fresher owner Slack
and current-main HEAD say there is no blanket non-actuation /
never-touch-Muhlnickel-or-Titan rule. Substrate work is first-class.

This leftover measures the catalog, the repo grounding copy, and
ground/HEAD.md. It does not write titan.gguf. It does not smash
commons.mno. It does not infer authorization for an unrelated
destructive mutation. Talk that treats the local file as absolute
law is CLAIMED until this leftover is on current main.

  python3 host/stale_spec.py
  python3 host/stale_spec.py --catalog ground/STALE_SPEC.json
  python3 host/stale_spec.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_CATALOG = os.path.join("ground", "STALE_SPEC.json")
DEFAULT_GROUNDING = os.path.join("muhl", "lda-docs", "SESSION_GROUNDING.md")
DEFAULT_HEAD = os.path.join("ground", "HEAD.md")
OWNER_SLACK = (
    "1787628542.573719",
    "1787628900.201179",
    "1787629309.162109",
)


def load_catalog(text):
    """Parse the stale-spec catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {
            "historical_path": "",
            "current_slack": [],
            "error": "catalog is not JSON",
        }
    if not isinstance(data, dict):
        return {
            "historical_path": "",
            "current_slack": [],
            "error": "catalog is not an object",
        }
    historical = data.get("historical_input")
    if not isinstance(historical, dict):
        historical = {}
    authority = data.get("current_authority") or []
    slack = []
    seen = set()
    head_paths = []
    for item in authority:
        if not isinstance(item, dict):
            continue
        ts = str(item.get("slack_ts") or "").strip()
        if ts and ts not in seen:
            seen.add(ts)
            slack.append(ts)
        path = str(item.get("path") or "").strip()
        if path:
            head_paths.append(path)
    refused = [
        str(item or "").strip()
        for item in (data.get("still_refused") or [])
        if str(item or "").strip()
    ]
    return {
        "historical_path": str(historical.get("path") or "").strip(),
        "historical_pointer": str(historical.get("pointer") or "").strip(),
        "historical_role": str(historical.get("role") or "").strip(),
        "historical_not": str(historical.get("not") or "").strip(),
        "current_slack": slack,
        "current_paths": head_paths,
        "still_refused": refused,
        "lawful_lanes": [
            str(item or "").strip()
            for item in (data.get("lawful_lanes") or [])
            if str(item or "").strip()
        ],
        "source_id": str(data.get("source_id") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
    }


def grounding_is_input(text):
    """True when the body is a SESSION_GROUNDING copy, not a bake."""
    body = str(text or "")
    return "SESSION GROUNDING" in body and "Host = inject" in body


def head_is_current(text):
    """True when HEAD.md carries the fresher owner first-class rule."""
    body = str(text or "")
    first_class = "first-class" in body.lower()
    smash = "Smash/wipe of `commons.mno` is refused" in body or (
        "commons.mno" in body and "refused" in body
    )
    return first_class and smash


def owner_slack_present(slack):
    """True when the catalog cites the three owner correction timestamps."""
    have = set(str(item or "").strip() for item in (slack or []))
    return all(ts in have for ts in OWNER_SLACK)


def smash_refused_in_catalog(refused):
    """True when the catalog still names smash/wipe as refused."""
    blob = " ".join(str(item or "") for item in (refused or [])).lower()
    return "smash" in blob and "commons.mno" in blob


def measure_from_parts(catalog_text, grounding_text, head_text):
    """Census from already-read catalog / grounding / HEAD bodies."""
    catalog = load_catalog(catalog_text)
    row = {
        "measured": "error" not in catalog,
        "historical_path": catalog.get("historical_path") or "",
        "historical_present": grounding_is_input(grounding_text),
        "current_slack": list(catalog.get("current_slack") or []),
        "current_slack_complete": owner_slack_present(catalog.get("current_slack")),
        "head_current": head_is_current(head_text),
        "smash_refused": smash_refused_in_catalog(catalog.get("still_refused"))
        and ("commons.mno" in str(head_text or "") and "refused" in str(head_text or "")),
        "source_id": catalog.get("source_id") or "",
        "slack_ts": catalog.get("slack_ts") or "",
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "lawful_lane_count": len(catalog.get("lawful_lanes") or []),
        "historical_role": catalog.get("historical_role") or "",
        "historical_not": catalog.get("historical_not") or "",
    }
    if catalog.get("error"):
        row["error"] = catalog["error"]
        row["measured"] = False
    return row


def measure_paths(catalog_path, grounding_path, head_path):
    """Read the three files from disk and census them."""
    try:
        with open(catalog_path, encoding="utf-8") as handle:
            catalog_text = handle.read()
        with open(grounding_path, encoding="utf-8") as handle:
            grounding_text = handle.read()
        with open(head_path, encoding="utf-8") as handle:
            head_text = handle.read()
    except OSError as exc:
        return {
            "measured": False,
            "error": str(exc),
            "titan": "NOT_WRITTEN",
        }
    row = measure_from_parts(catalog_text, grounding_text, head_text)
    row["catalog_path"] = catalog_path
    row["grounding_path"] = grounding_path
    row["head_path"] = head_path
    return row


def classify(row):
    """Turn a measured reconciliation into a land-desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "stale-spec catalog / SESSION_GROUNDING / HEAD.md not read. "
                "Absence was not measured."
            ),
        }
    if not row.get("historical_path") or not row.get("historical_present"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "historical SESSION_GROUNDING input missing. A Slack errata "
                "is CLAIMED until the repo copy is named on current main."
            ),
        }
    if not row.get("current_slack_complete") or not row.get("head_current"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "current owner authority missing. Cite Slack "
                "1787628542.573719 / 1787628900.201179 / 1787629309.162109 "
                "and first-class substrate on ground/HEAD.md."
            ),
        }
    if not row.get("smash_refused"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "refused smash/wipe of commons.mno missing. The general "
                "correction is not authorization for an unrelated "
                "destructive mutation."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "local SESSION_GROUNDING is historical input. Current owner "
            "Slack plus HEAD.md make substrate first-class. Smash/wipe "
            "stays refused. A Slack errata is still not the file."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Reconcile local SESSION_GROUNDING against current owner law"
    )
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument("--grounding", default=DEFAULT_GROUNDING)
    parser.add_argument("--head", default=DEFAULT_HEAD)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_paths(args.catalog, args.grounding, args.head)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    catalog = json.dumps(
        {
            "slack_ts": "1787635067.695619",
            "historical_input": {
                "path": "muhl/lda-docs/SESSION_GROUNDING.md",
                "role": "historical/session-bound specification input",
                "not": "standing never-touch / blanket non-actuation rule",
            },
            "current_authority": [
                {"slack_ts": "1787628542.573719"},
                {"slack_ts": "1787628900.201179"},
                {"slack_ts": "1787629309.162109"},
                {"path": "ground/HEAD.md"},
            ],
            "still_refused": ["smash/wipe of commons.mno"],
            "titan": "NOT_WRITTEN",
        }
    )
    grounding = "# SESSION GROUNDING\nHost = inject ∨ surface ∨ die.\n"
    head = (
        "Smash/wipe of `commons.mno` is refused. Substrate / organ / "
        "titan / address work is first-class.\n"
    )
    row = measure_from_parts(catalog, grounding, head)
    assert row["measured"] is True
    assert row["historical_present"] is True
    assert row["current_slack_complete"] is True
    assert row["head_current"] is True
    assert row["smash_refused"] is True
    assert row["titan"] == "NOT_WRITTEN"
    assert classify(row)["state"] == "INTEGRATED"
    missing_head = measure_from_parts(catalog, grounding, "bake only")
    assert classify(missing_head)["state"] == "NOT_LANDED"
    missing_ground = measure_from_parts(catalog, "", head)
    assert classify(missing_ground)["state"] == "NOT_LANDED"
    return True


if __name__ == "__main__":
    sys.exit(main())
