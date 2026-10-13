#!/usr/bin/env python3
"""host/titan_append_guard.py — triple-identical Titan appends are a pause.

Slack 1787638151.184599 (DEMON P0_UTILIZATION_INCIDENT): live
C:\\llm\\models\\titan.gguf measured 103,831,308,164 bytes with three
consecutive 9,319,291-byte spans, all SHA-256
3754028086cd42e00131bea88f0e7fcf6dba2f84ad31cb70b88e655bbdd84e8c.

`--go` only fail-closed when live size equalled claimed_append_end
(103812669582). At the measured size it reallocated and would append
a fourth copy. This leftover is the fixture + refuse-close. It does
not truncate, dedupe, overwrite, or write titan.gguf.

DIO + JOJO keep the owner-machine hash / live reread lane.

  python3 host/titan_append_guard.py
  python3 host/titan_append_guard.py --root .
  python3 host/titan_append_guard.py --self-test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "TITAN_APPEND_GUARD.json")
SLACK_TS = "1787638151.184599"
INCIDENT_BASE = 103803350291
INCIDENT_FIRST_END = 103812669582
INCIDENT_SECOND_END = 103821988873
INCIDENT_LIVE_SIZE = 103831308164
INCIDENT_PAYLOAD = 9319291
INCIDENT_SHA256 = (
    "3754028086cd42e00131bea88f0e7fcf6dba2f84ad31cb70b88e655bbdd84e8c"
)
INCIDENT_COPY_COUNT = 3
APPLY_FALSE = True


def load_catalog(text):
    """Parse the frozen incident catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    try:
        live_size = int(data.get("live_size") or 0)
    except (TypeError, ValueError):
        live_size = 0
    try:
        payload_len = int(data.get("payload_len") or 0)
    except (TypeError, ValueError):
        payload_len = 0
    try:
        copy_count = int(data.get("copy_count") or 0)
    except (TypeError, ValueError):
        copy_count = 0
    plan = data.get("repair_plan") if isinstance(data.get("repair_plan"), dict) else {}
    return {
        "source_id": str(data.get("source_id") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "live_size": live_size,
        "payload_len": payload_len,
        "copy_count": copy_count,
        "span_sha256": str(data.get("span_sha256") or "").strip().lower(),
        "apply": bool(data.get("apply", False)),
        "preserve_exact": bool(data.get("preserve_exact", True)),
        "refuse_truncate": bool(data.get("refuse_truncate", True)),
        "refuse_dedupe": bool(data.get("refuse_dedupe", True)),
        "refuse_overwrite": bool(data.get("refuse_overwrite", True)),
        "repair_plan_apply": bool(plan.get("apply", False)),
        "hands_off": [
            str(item or "").strip()
            for item in (data.get("hands_off") or [])
            if str(item or "").strip()
        ],
    }


def payload_len(packet):
    """Claimed one-copy length. Prefer written_bytes, then end-base."""
    packet = packet or {}
    try:
        written = int(packet.get("written_bytes") or 0)
    except (TypeError, ValueError):
        written = 0
    if written > 0:
        return written
    try:
        base = int(packet.get("claimed_append_base") or 0)
        end = int(packet.get("claimed_append_end") or 0)
    except (TypeError, ValueError):
        base, end = 0, 0
    if end > base:
        return end - base
    return INCIDENT_PAYLOAD


def measure_spans(path, baseline, length):
    """Hash consecutive length-byte spans from baseline. Does not write."""
    spans = []
    if not path or not os.path.isfile(path):
        return spans
    try:
        size = os.path.getsize(path)
        baseline = int(baseline)
        length = int(length)
    except (OSError, TypeError, ValueError):
        return spans
    if length <= 0 or size < baseline + length:
        return spans
    copies = (size - baseline) // length
    with open(path, "rb") as handle:
        for index in range(copies):
            start = baseline + (index * length)
            handle.seek(start)
            blob = handle.read(length)
            if len(blob) != length:
                break
            spans.append(
                {
                    "index": index + 1,
                    "start": start,
                    "end": start + length,
                    "len": length,
                    "sha256": hashlib.sha256(blob).hexdigest(),
                }
            )
    return spans


def identical_copy_count(spans):
    """How many leading consecutive spans share the first hash."""
    if not spans:
        return 0
    first = str(spans[0].get("sha256") or "")
    if not first:
        return 0
    count = 0
    for row in spans:
        if str(row.get("sha256") or "") != first:
            break
        count += 1
    return count


def refuse_further_append(packet, live_size, path=None):
    """True when another titan append would duplicate or grow an incident.

    First write at claimed_append_base stays allowed. Unexpected live
    size must not reallocate. Incident size is a hard pause. Unknown
    or unreadable live size fail-closes. Does not truncate or rewrite
    the artifact.
    """
    if live_size is None:
        return True, "no live size"
    try:
        live = int(live_size)
    except (TypeError, ValueError):
        return True, "live size unreadable"
    packet = packet or {}
    try:
        base = int(packet.get("claimed_append_base") or INCIDENT_BASE)
    except (TypeError, ValueError):
        base = INCIDENT_BASE
    try:
        end = int(packet.get("claimed_append_end") or 0)
    except (TypeError, ValueError):
        end = 0
    length = payload_len(packet)
    if live == INCIDENT_LIVE_SIZE:
        return True, (
            "frozen incident live_size=%s with %s byte-identical copies. "
            "preserve the artifact. no truncate/dedupe/overwrite"
            % (INCIDENT_LIVE_SIZE, INCIDENT_COPY_COUNT)
        )
    if end > base and live == end:
        return True, (
            "already at claimed_append_end=%s. fail-closed against duplicate append"
            % end
        )
    if end > base and live != base and live != end:
        return True, (
            "unexpected live_size=%s (base=%s end=%s). will not reallocate"
            % (live, base, end)
        )
    if length > 0 and live > base:
        extra = live - base
        copies = extra // length
        if extra % length == 0 and copies >= 2:
            return True, (
                "%s payload-sized copies already present (%s bytes each). "
                "will not append another"
                % (copies, length)
            )
        if extra > length:
            return True, (
                "live_size=%s larger than one claimed payload %s. will not reallocate"
                % (live, length)
            )
    if path:
        spans = measure_spans(path, base if end > base else 0, length)
        copies = identical_copy_count(spans)
        if copies >= 2:
            return True, (
                "fixture/file has %s byte-identical trailing spans. "
                "will not append another"
                % copies
            )
    return False, "write still allowed at claimed base"


def build_fixture(directory, prefix=b"HEAD", payload=b"PAYLOAD!!", copies=3):
    """Small byte-identical-append fixture. Not titan.gguf."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "triple_append.bin")
    with open(path, "wb") as handle:
        handle.write(prefix)
        for _ in range(copies):
            handle.write(payload)
    return path, len(prefix), len(payload), hashlib.sha256(payload).hexdigest()


def repair_plan():
    """Owner-authorized measured plan. apply stays false."""
    return {
        "kind": "TITAN_APPEND_REPAIR_PLAN",
        "apply": False,
        "preserve_bytes": INCIDENT_LIVE_SIZE,
        "canonical_first_copy": "UNDECIDED",
        "do_not": [
            "truncate",
            "dedupe",
            "overwrite",
            "rerun the append",
            "label the first copy canonical without owner authorization",
        ],
        "preimage": {
            "aug18_baseline": INCIDENT_BASE,
            "first_claimed_end": INCIDENT_FIRST_END,
            "payload_len": INCIDENT_PAYLOAD,
            "span_sha256": INCIDENT_SHA256,
        },
        "byte_boundaries": [
            {"copy": 1, "start": INCIDENT_BASE, "end": INCIDENT_FIRST_END},
            {"copy": 2, "start": INCIDENT_FIRST_END, "end": INCIDENT_SECOND_END},
            {"copy": 3, "start": INCIDENT_SECOND_END, "end": INCIDENT_LIVE_SIZE},
        ],
        "backup_rollback": (
            "copy-on-write snapshot of the exact 103831308164-byte artifact "
            "before any future mutation. rollback = restore that snapshot. "
            "no in-place shrink."
        ),
        "before_after_tail": {
            "packet_live_size_after": INCIDENT_FIRST_END,
            "measured_live_size": INCIDENT_LIVE_SIZE,
            "tail_sha256": INCIDENT_SHA256,
            "packet_state": "STALE",
        },
        "downstream": {
            "packet": "excerpts/20260823/titan_move_packet.json still 103812669582",
            "organ_map": "only span 1 sits on claimed organ offsets; spans 2-3 are outside",
            "stranded_map": "titan_later_size already 103831308164",
            "circuits_registry": "do not remap dest FROM FILE until owner picks a size",
        },
        "owner_gate": (
            "BRYCE/ZERO must authorize any repair that picks a canonical "
            "size or drops copies 2-3. This leftover only pause-closes writes."
        ),
    }


def measure_from_rows(facts):
    """Classify frozen numbers + fixture result. Does not open titan.gguf."""
    facts = facts or {}
    try:
        live_size = int(facts.get("live_size") or 0)
    except (TypeError, ValueError):
        live_size = 0
    try:
        payload = int(facts.get("payload_len") or 0)
    except (TypeError, ValueError):
        payload = 0
    try:
        copies = int(facts.get("copy_count") or 0)
    except (TypeError, ValueError):
        copies = 0
    sha = str(facts.get("span_sha256") or "").strip().lower()
    arithmetic_ok = (
        live_size == INCIDENT_LIVE_SIZE
        and payload == INCIDENT_PAYLOAD
        and copies == INCIDENT_COPY_COUNT
        and (INCIDENT_LIVE_SIZE - INCIDENT_BASE) == (INCIDENT_PAYLOAD * INCIDENT_COPY_COUNT)
    )
    sha_ok = sha == INCIDENT_SHA256
    refused = bool(facts.get("refused"))
    fixture_copies = int(facts.get("fixture_copies") or 0)
    fixture_identical = bool(facts.get("fixture_identical"))
    apply_off = facts.get("apply") is False and facts.get("repair_plan_apply") is False
    preserve = bool(facts.get("preserve_exact", True))
    refuse_mutate = (
        bool(facts.get("refuse_truncate", True))
        and bool(facts.get("refuse_dedupe", True))
        and bool(facts.get("refuse_overwrite", True))
    )
    return {
        "measured": True,
        "live_size": live_size,
        "payload_len": payload,
        "copy_count": copies,
        "span_sha256": sha,
        "arithmetic_ok": arithmetic_ok,
        "sha_ok": sha_ok,
        "refused": refused,
        "fixture_copies": fixture_copies,
        "fixture_identical": fixture_identical,
        "apply": bool(facts.get("apply", False)),
        "repair_plan_apply": bool(facts.get("repair_plan_apply", False)),
        "preserve_exact": preserve,
        "refuse_truncate": bool(facts.get("refuse_truncate", True)),
        "refuse_dedupe": bool(facts.get("refuse_dedupe", True)),
        "refuse_overwrite": bool(facts.get("refuse_overwrite", True)),
        "apply_off": apply_off,
        "refuse_mutate": refuse_mutate,
        "titan_write": facts.get("titan_write") or "NOT_WRITTEN",
        "slack_ts": facts.get("slack_ts") or SLACK_TS,
    }


def measure_tree(root, catalog_text=""):
    """Read the catalog and run the in-process fixture. Never opens titan.gguf."""
    catalog = load_catalog(catalog_text)
    if catalog.get("error"):
        return {
            "measured": False,
            "error": catalog["error"],
            "titan_write": "NOT_WRITTEN",
        }
    with tempfile.TemporaryDirectory(prefix="titan-append-guard-") as tmp:
        path, baseline, length, sha = build_fixture(tmp)
        spans = measure_spans(path, baseline, length)
        copies = identical_copy_count(spans)
        packet = {
            "claimed_append_base": baseline,
            "claimed_append_end": baseline + length,
            "written_bytes": length,
            "titan": "WRITTEN",
        }
        refused, reason = refuse_further_append(
            packet, baseline + (length * copies), path=path
        )
        incident_packet = {
            "claimed_append_base": INCIDENT_BASE,
            "claimed_append_end": INCIDENT_FIRST_END,
            "written_bytes": INCIDENT_PAYLOAD,
            "titan": "WRITTEN",
        }
        incident_refused, incident_reason = refuse_further_append(
            incident_packet, INCIDENT_LIVE_SIZE
        )
    facts = {
        "live_size": catalog.get("live_size") or INCIDENT_LIVE_SIZE,
        "payload_len": catalog.get("payload_len") or INCIDENT_PAYLOAD,
        "copy_count": catalog.get("copy_count") or INCIDENT_COPY_COUNT,
        "span_sha256": catalog.get("span_sha256") or INCIDENT_SHA256,
        "refused": refused and incident_refused,
        "fixture_copies": copies,
        "fixture_identical": copies >= 2
        and len({row["sha256"] for row in spans}) == 1,
        "apply": catalog.get("apply", False),
        "repair_plan_apply": catalog.get("repair_plan_apply", False),
        "preserve_exact": catalog.get("preserve_exact", True),
        "refuse_truncate": catalog.get("refuse_truncate", True),
        "refuse_dedupe": catalog.get("refuse_dedupe", True),
        "refuse_overwrite": catalog.get("refuse_overwrite", True),
        "titan_write": catalog.get("titan") or "NOT_WRITTEN",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
    }
    row = measure_from_rows(facts)
    row["root"] = root
    row["source_id"] = catalog.get("source_id") or ""
    row["fixture_sha256"] = sha
    row["refuse_reason"] = reason
    row["incident_reason"] = incident_reason
    row["repair_plan"] = repair_plan()
    row["hands_off"] = catalog.get("hands_off") or []
    return row


def classify(row):
    """Leftover is INTEGRATED when freeze + fixture refuse-close are measured."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "titan-append-guard catalog / fixture not read. "
                "Absence was not stillness."
            ),
        }
    if row.get("titan_write") == "WRITTEN" and row.get("apply"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "this leftover wrote or applied a repair. "
                "Do not truncate, dedupe, overwrite, or write titan.gguf."
            ),
        }
    if not row.get("arithmetic_ok") or not row.get("sha_ok"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "frozen incident numbers missing or wrong. "
                "Triple-append talk is CLAIMED until the catalog matches "
                "103831308164 / 9319291 / 3 / 3754028086cd42e0."
            ),
        }
    if not row.get("refused") or int(row.get("fixture_copies") or 0) < 2:
        return {
            "state": "NOT_LANDED",
            "note": (
                "fixture did not refuse-close a second/third identical append. "
                "P0 pause is CLAIMED until the guard ships."
            ),
        }
    if not row.get("apply_off") or not row.get("preserve_exact") or not row.get("refuse_mutate"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "repair plan apply is on, or preserve/refuse-mutate flags dropped. "
                "Do not truncate, dedupe, or overwrite."
            ),
        }
    if not row.get("fixture_identical"):
        return {
            "state": "NOT_LANDED",
            "note": "fixture spans were not byte-identical. Guard did not measure the incident shape.",
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "triple-append incident is frozen and the fixture refuse-closes "
            "further --go. live_size 103831308164 preserved. apply:false. "
            "No truncate/dedupe/overwrite. titan NOT_WRITTEN. "
            "A Slack P0 is still not the file."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Freeze the Titan triple-append incident and test the guard"
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
    catalog_path = args.catalog
    if not os.path.isabs(catalog_path):
        catalog_path = os.path.join(args.root, catalog_path)
    try:
        with open(catalog_path, encoding="utf-8") as handle:
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
    packet = {
        "claimed_append_base": INCIDENT_BASE,
        "claimed_append_end": INCIDENT_FIRST_END,
        "written_bytes": INCIDENT_PAYLOAD,
        "titan": "WRITTEN",
    }
    refused, reason = refuse_further_append(packet, INCIDENT_LIVE_SIZE)
    assert refused, reason
    allowed, _ = refuse_further_append(
        {
            "claimed_append_base": 10,
            "claimed_append_end": 14,
            "written_bytes": 4,
        },
        10,
    )
    assert not allowed
    at_end, _ = refuse_further_append(
        {
            "claimed_append_base": 10,
            "claimed_append_end": 14,
            "written_bytes": 4,
        },
        14,
    )
    assert at_end
    with tempfile.TemporaryDirectory(prefix="titan-append-self-") as tmp:
        path, baseline, length, sha = build_fixture(tmp)
        spans = measure_spans(path, baseline, length)
        assert identical_copy_count(spans) == 3
        assert len({row["sha256"] for row in spans}) == 1
        assert sha == spans[0]["sha256"]
        fixture_refused, _ = refuse_further_append(
            {
                "claimed_append_base": baseline,
                "claimed_append_end": baseline + length,
                "written_bytes": length,
            },
            baseline + (length * 3),
            path=path,
        )
        assert fixture_refused
        before = os.path.getsize(path)
        assert before == baseline + (length * 3)
    live = measure_from_rows(
        {
            "live_size": INCIDENT_LIVE_SIZE,
            "payload_len": INCIDENT_PAYLOAD,
            "copy_count": INCIDENT_COPY_COUNT,
            "span_sha256": INCIDENT_SHA256,
            "refused": True,
            "fixture_copies": 3,
            "fixture_identical": True,
            "apply": False,
            "repair_plan_apply": False,
            "preserve_exact": True,
            "refuse_truncate": True,
            "refuse_dedupe": True,
            "refuse_overwrite": True,
            "titan_write": "NOT_WRITTEN",
        }
    )
    assert live["arithmetic_ok"]
    assert classify(live)["state"] == "INTEGRATED"
    wrote = dict(live)
    wrote["apply"] = True
    wrote["titan_write"] = "WRITTEN"
    assert classify(wrote)["state"] == "NOT_LANDED"
    plan = repair_plan()
    assert plan["apply"] is False
    assert plan["preserve_bytes"] == INCIDENT_LIVE_SIZE
    assert plan["canonical_first_copy"] == "UNDECIDED"
    catalog = load_catalog('{"not":"valid-shape"')
    assert catalog.get("error")
    return True


if __name__ == "__main__":
    sys.exit(main())
