#!/usr/bin/env python3
"""host/unused_invoke.py — what was built, and whether anything invokes it.

Slack 1787633805.754249 (DEMON resource-utilization sweep): treat each
finding as an action queue. This leftover measures checked-in host
instruments and already-provisioned CI configs. It does not invent
access, credentials, success, or usage. A config file is not a run.

Talk about the sweep without this census is CLAIMED. Missing instrument
is NOT_LANDED. A measured unused list is INTEGRATED for this leftover;
unused is the finding, not a gate.

  python3 host/unused_invoke.py
  python3 host/unused_invoke.py --root .
  python3 host/unused_invoke.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys


SEARCH_SUFFIXES = (".py", ".js", ".yml", ".yaml", ".md", ".html", ".json")
SKIP_DIRS = {
    ".git",
    "node_modules",
    "p",
    "chunks",
    "d",
    "to",
    "by",
    "conflicts",
    "evidence",
    "infra",
    "muhl",
    "excerpts",
}
TEXT_CAP = 400000
PROVIDER_ROWS = (
    {
        "road": "Cirrus",
        "config": ".cirrus.yml",
        "probe": "https://api.cirrus-ci.com/github/woahwhattheheck/commons",
    },
    {
        "road": "GitLab",
        "config": ".gitlab-ci.yml",
        "probe": "https://gitlab.com/api/v4/projects/woahwhattheheck%2Fcommons",
    },
    {
        "road": "Woodpecker",
        "config": ".woodpecker.yml",
        "probe": "https://codeberg.org/api/v1/repos/woahwhattheheck/commons",
    },
    {
        "road": "GitHub Actions",
        "config": ".github/workflows/header-census.yml",
        "probe": "",
    },
)


def stems_from_listing(names):
    """Return sorted host module stems from a filename listing."""
    stems = []
    for name in names or []:
        base = os.path.basename(str(name or ""))
        if not base.endswith(".py") or base.startswith("_"):
            continue
        stems.append(base[:-3])
    return sorted(set(stems))


_REFERENCE_PATTERNS = {}


def _reference_patterns(stem):
    """The four caller shapes for one stem, compiled once per stem.

    re's own cache holds 512 patterns; a census of ~550 instruments x 4 shapes
    thrashed it, so every references() call recompiled. Same patterns, same
    matches, compiled once.
    """
    pats = _REFERENCE_PATTERNS.get(stem)
    if pats is None:
        escaped = re.escape(stem)
        pats = tuple(
            re.compile(pat)
            for pat in (
                r"host/" + escaped + r"\.py",
                r"\bimport " + escaped + r"\b",
                r"\bfrom " + escaped + r" import\b",
                r"python3?\s+host/" + escaped + r"\.py",
            )
        )
        _REFERENCE_PATTERNS[stem] = pats
    return pats


def references(stem, text):
    """True when a body names this host instrument as a caller."""
    body = str(text or "")
    if not stem or not body:
        return False
    if stem not in body:
        # every caller shape contains the stem verbatim; a body without it
        # cannot match any of them. Identical result, one substring scan.
        return False
    return any(pat.search(body) for pat in _reference_patterns(stem))


def is_self_or_test(path, stem):
    rel = str(path or "").replace("\\", "/")
    return rel in {
        "host/%s.py" % stem,
        "test_%s.py" % stem,
        "host/test_%s.py" % stem,
    }


def callers_for(stem, texts):
    """Return caller paths that reference stem, skipping self and its test."""
    found = []
    for path, body in texts or []:
        if is_self_or_test(path, stem):
            continue
        if references(stem, body):
            found.append(str(path))
    return found


def measure_from_rows(instruments, texts):
    """Pure census so tests do not need the live tree."""
    unused = []
    invoked = []
    for stem in instruments or []:
        callers = callers_for(stem, texts)
        if callers:
            invoked.append({"stem": stem, "callers": callers})
        else:
            unused.append(stem)
    return {
        "measured": True,
        "instrument_count": len(list(instruments or [])),
        "unused_count": len(unused),
        "invoked_count": len(invoked),
        "unused": unused,
        "invoked": invoked,
        "titan": "NOT_WRITTEN",
    }


def classify(row):
    """Turn a measured census into a land-desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "unused-invoke census not read. Absence was not stillness.",
        }
    unused = int(row.get("unused_count") or 0)
    invoked = int(row.get("invoked_count") or 0)
    total = int(row.get("instrument_count") or 0)
    return {
        "state": "INTEGRATED",
        "note": (
            "census measured %s host instrument(s): %s invoked, %s unused. "
            "Unused is the finding. A config is not a run. Talk is not a land."
        )
        % (total, invoked, unused),
    }


def classify_provider(row):
    """A config without a run receipt stays UNMEASURED. Do not invent usage."""
    row = row or {}
    road = str(row.get("road") or "provider")
    if not row.get("config_present"):
        return {
            "road": road,
            "state": "NOT_LANDED",
            "note": "%s config absent. Do not invent a worker." % road,
        }
    if row.get("run_url"):
        return {
            "road": road,
            "state": "INTEGRATED",
            "note": "%s has a measured run URL." % road,
        }
    if road == "GitHub Actions":
        return {
            "road": road,
            "state": "LIVE",
            "note": (
                "GitHub Actions config is present. Workflow history is the "
                "existing measurement. This probe does not invent a new run."
            ),
        }
    probe = str(row.get("probe_status") or "UNPROBED")
    return {
        "road": road,
        "state": "UNMEASURED",
        "note": (
            "%s config is present. No run URL. Probe %s. "
            "A 404/000 is not stillness. Do not invent credentials or success."
        )
        % (road, probe),
    }


def measure_providers(rows):
    """Pure provider parser. Live HTTP stays optional."""
    out = []
    for row in rows or []:
        item = dict(row or {})
        verdict = classify_provider(item)
        item.update(verdict)
        out.append(item)
    return out


def _walk_texts(root):
    texts = []
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
        for name in filenames:
            if not name.endswith(SEARCH_SUFFIXES):
                continue
            path = os.path.join(dirpath, name)
            try:
                if os.path.getsize(path) > TEXT_CAP:
                    continue
            except OSError:
                continue
            rel = os.path.relpath(path, root).replace("\\", "/")
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as handle:
                    texts.append((rel, handle.read()))
            except OSError:
                continue
    return texts


def measure_root(root):
    host = os.path.join(os.path.abspath(root), "host")
    if not os.path.isdir(host):
        return {
            "measured": False,
            "error": "host/ missing: %s" % host,
            "titan": "NOT_WRITTEN",
        }
    names = [
        name
        for name in os.listdir(host)
        if name.endswith(".py") and not name.startswith("_")
    ]
    texts = _walk_texts(root)
    row = measure_from_rows(stems_from_listing(names), texts)
    providers = []
    for spec in PROVIDER_ROWS:
        config_path = os.path.join(os.path.abspath(root), spec["config"])
        providers.append(
            {
                "road": spec["road"],
                "config": spec["config"],
                "config_present": os.path.isfile(config_path),
                "run_url": "",
                "probe_status": "UNPROBED",
            }
        )
    row["providers"] = measure_providers(providers)
    row["root"] = os.path.abspath(root)
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure unused host instruments and provisioned CI configs"
    )
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_root(args.root)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    fixtures = measure_from_rows(
        ["used_one", "unused_one"],
        [
            ("host/used_one.py", "def main():\n    return 1\n"),
            ("land.html", "python3 host/used_one.py\n"),
            ("host/unused_one.py", "def main():\n    return 0\n"),
            ("test_unused_one.py", "import unused_one\n"),
        ],
    )
    assert fixtures["instrument_count"] == 2
    assert fixtures["invoked_count"] == 1
    assert fixtures["unused"] == ["unused_one"]
    assert fixtures["invoked"][0]["stem"] == "used_one"
    assert classify(fixtures)["state"] == "INTEGRATED"
    missing = classify_provider({"road": "Cirrus", "config_present": False})
    assert missing["state"] == "NOT_LANDED"
    dark = classify_provider(
        {
            "road": "Cirrus",
            "config_present": True,
            "run_url": "",
            "probe_status": "TLS_000",
        }
    )
    assert dark["state"] == "UNMEASURED"
    assert "Do not invent" in dark["note"]
    gha = classify_provider({"road": "GitHub Actions", "config_present": True})
    assert gha["state"] == "LIVE"
    live = classify_provider(
        {
            "road": "Cirrus",
            "config_present": True,
            "run_url": "https://cirrus-ci.com/build/1",
        }
    )
    assert live["state"] == "INTEGRATED"
    return True


if __name__ == "__main__":
    sys.exit(main())
