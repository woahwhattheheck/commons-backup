#!/usr/bin/env python3
"""Add sourced work observations to the existing native TITAN export."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from adapter import parse_time

SCHEMA = "titan.work-items.v1"
HERE = Path(__file__).resolve().parent
STATUS_KEYS = ("landed", "selected", "hosted")


def build_work_items(catalog):
    """Return detached records; fetching or rendering never refreshes activity."""
    if catalog.get("schema_version") != SCHEMA:
        raise ValueError("unsupported work catalog schema")
    items = copy.deepcopy(catalog.get("work_items", []))
    seen = set()
    for item in items:
        if not item.get("id") or item["id"] in seen:
            raise ValueError("work item IDs must be present and unique")
        seen.add(item["id"])
        for key in ("observed_at", "latest_activity_at"):
            parse_time(item.get(key))
        # Unknown activity remains unknown even when the catalog was fetched now.
        if item.get("latest_activity_at") is not None and not item.get("latest_activity_source"):
            raise ValueError("dated activity needs its source reference")
        for key in STATUS_KEYS:
            status = item.setdefault(key, {"state": None, "observed_at": None,
                                           "completed_at": None, "source_ref": None})
            parse_time(status.get("observed_at"))
            parse_time(status.get("completed_at"))
        item.setdefault("provider_completion", {"status": None, "completed_at": None,
                                              "receipt_ref": None})
        parse_time(item["provider_completion"].get("completed_at"))
    return items


def activity_freshness(item, *, as_of, max_age_seconds=1800):
    """Age the meaningful activity, independently of hardware or fetch times."""
    now = parse_time(as_of)
    if now is None or max_age_seconds < 0:
        raise ValueError("dated as_of and nonnegative max age required")
    activity = parse_time(item.get("latest_activity_at"))
    if activity is None:
        return {"state": "unknown", "age_seconds": None}
    age = (now - activity).total_seconds()
    state = "future" if age < 0 else "stale" if age > max_age_seconds else "fresh"
    return {"state": state, "age_seconds": age}


def load_catalog(path=None):
    return json.loads(Path(path or HERE / "work-records.json").read_text())


def native_source_check(native_directory, document):
    """Check new work payload persistence through the actual native consumer.

    This intentionally exercises no old session tests, provider calls or native
    application suites. Direct work-item presentation belongs to that consumer.
    """
    import hashlib
    import importlib.util
    import tempfile
    path = Path(native_directory) / "core.py"
    raw = path.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if blob != "b8a4479fb42c180f95d41cc41f8fff71acbc36a3":
        raise ValueError("consumer source differs from the recorded work-contract pin")
    spec = importlib.util.spec_from_file_location("titan_work_native_core", path)
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    def no_network(*args, **kwargs):
        raise AssertionError("work compatibility has no provider fetch")
    with tempfile.TemporaryDirectory(prefix="titan-work-source-") as tmp:
        center = core.CommandCenter(Path(tmp), fetcher=no_network)
        center._save_source("titan", "revenue/kaggriculture/command-center-adapter/adapter.json",
                            "2bcdd15bd1822eecb694bebe9a830ee5b3fb4a50", document)
        first = center._source("titan")
        assert first["data"]["work_items"] == document["work_items"]
        center._save_source("titan", first["path"], None, error="synthetic delayed fetch")
        stale = center._source("titan")
        assert stale["status"] == "stale"
        assert stale["data"]["work_items"] == document["work_items"]
        assert stale["observed_at"] == first["observed_at"]
    return {"core_git_blob": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
            "work_items": len(document["work_items"]), "checks_passed": 2,
            "checks": ["native_source_roundtrip", "failed_fetch_preserves_work_activity"],
            "provider_calls": 0, "native_full_suite_reexecuted": False}
