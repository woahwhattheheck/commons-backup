#!/usr/bin/env python3
"""Mock-adapter runner for Bid 1421 Attachment F instrument fixtures.

Synthetic only. Not production, not regulated, not deployed, not
instrument-connected. Does not touch AquaTrace product-core.

python3 revenue/billings_bid_1421/instrument_fixtures/runner.py
python3 revenue/billings_bid_1421/instrument_fixtures/runner.py --write-expected
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST_NAME = "manifest.json"
EVENTS_NAME = "events.jsonl"
EXPECTED_NAME = "expected_receipts.json"
CALIBRATION_ADAPTER = "mock-ph-meter-1"
FINDER_UNVERIFIED = "FINDER UNVERIFIED"


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path):
    events = []
    with open(path, encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except ValueError as exc:
                raise ValueError("events.jsonl line %s is not JSON: %s" % (line_no, exc))
    return events


def adapter_index(manifest):
    out = {}
    for row in manifest.get("adapters") or []:
        if isinstance(row, dict) and row.get("adapter_id"):
            out[row["adapter_id"]] = row
    return out


def analyte_index(manifest):
    out = {}
    for row in manifest.get("analysis_list") or []:
        if isinstance(row, dict) and row.get("analyte"):
            out[row["analyte"]] = row
    return out


def find_adapter(adapters, adapter_id):
    """Lookup with same-run calibration. Miss is FINDER UNVERIFIED, never 0."""
    known = sorted(adapters)
    cal_hit = CALIBRATION_ADAPTER in adapters
    space = {
        "query": adapter_id,
        "path": "revenue/billings_bid_1421/instrument_fixtures/manifest.json",
        "pattern": "adapters[].adapter_id",
        "known_adapter_ids": known,
        "known_count": len(known),
        "calibration": {
            "known_present": CALIBRATION_ADAPTER,
            "hit": cal_hit,
        },
    }
    if not cal_hit:
        return {
            "status": FINDER_UNVERIFIED,
            "reason": "same-run calibration missed known-present adapter",
            "search_space": space,
            "count": None,
            "zero": False,
        }
    if adapter_id in adapters:
        return {
            "status": "HIT",
            "adapter": adapters[adapter_id],
            "search_space": space,
        }
    return {
        "status": FINDER_UNVERIFIED,
        "reason": "adapter_id not in mock-adapter manifest",
        "search_space": space,
        "count": None,
        "zero": False,
    }


def find_analyte(analytes, analyte):
    known = sorted(analytes)
    cal_hit = "pH" in analytes
    space = {
        "query": analyte,
        "path": "revenue/billings_bid_1421/instrument_fixtures/manifest.json",
        "pattern": "analysis_list[].analyte",
        "known_analyte_names": known,
        "known_count": len(known),
        "calibration": {"known_present": "pH", "hit": cal_hit},
    }
    if not cal_hit:
        return {
            "status": FINDER_UNVERIFIED,
            "reason": "same-run calibration missed known-present analyte",
            "search_space": space,
            "count": None,
            "zero": False,
        }
    if analyte in analytes:
        return {"status": "HIT", "analyte": analytes[analyte], "search_space": space}
    return {
        "status": FINDER_UNVERIFIED,
        "reason": "analyte not in Attachment F analysis list",
        "search_space": space,
        "count": None,
        "zero": False,
    }


def _receipt(event, **fields):
    row = {
        "event_id": event.get("event_id"),
        "delivery_id": event.get("delivery_id"),
        "adapter_id": event.get("adapter_id"),
        "scenario": event.get("scenario"),
        "sequence_no": event.get("sequence_no"),
        "status": fields.get("status"),
        "commit_id": fields.get("commit_id"),
        "commits_created": fields.get("commits_created", 0),
        "total_commits_for_delivery": fields.get("total_commits_for_delivery", 0),
        "held": fields.get("held", False),
        "qc_status": event.get("qc_status"),
        "finder": fields.get("finder", "HIT"),
        "cash_usd": 0,
    }
    if fields.get("finder_report") is not None:
        row["finder_report"] = fields["finder_report"]
    return row


class MockInstrumentBus:
    """In-memory mock ingest. One commit per delivery_id."""

    def __init__(self, manifest):
        self.manifest = manifest
        self.adapters = adapter_index(manifest)
        self.analytes = analyte_index(manifest)
        self.commits = {}
        self.expected_seq = {aid: 1 for aid in self.adapters}
        self.held = []
        self.receipts = []

    def process(self, event):
        lookup = find_adapter(self.adapters, event.get("adapter_id"))
        if lookup["status"] != "HIT":
            rec = _receipt(
                event,
                status=FINDER_UNVERIFIED,
                commit_id=None,
                commits_created=0,
                total_commits_for_delivery=len(
                    [1 for c in self.commits if c == event.get("delivery_id")]
                ),
                held=False,
                finder=FINDER_UNVERIFIED,
                finder_report=lookup,
            )
            self.receipts.append(rec)
            return rec

        analyte_lookup = find_analyte(self.analytes, event.get("analyte"))
        if analyte_lookup["status"] != "HIT":
            rec = _receipt(
                event,
                status=FINDER_UNVERIFIED,
                commit_id=None,
                commits_created=0,
                total_commits_for_delivery=1 if event.get("delivery_id") in self.commits else 0,
                held=False,
                finder=FINDER_UNVERIFIED,
                finder_report=analyte_lookup,
            )
            self.receipts.append(rec)
            return rec

        delivery_id = event.get("delivery_id")
        adapter_id = event.get("adapter_id")
        scenario = event.get("scenario")
        existing = self.commits.get(delivery_id)
        if existing is not None:
            status = (
                "TIMEOUT_AFTER_COMMIT"
                if scenario == "timeout_after_commit"
                else "DUPLICATE_SUPPRESSED"
            )
            rec = _receipt(
                event,
                status=status,
                commit_id=existing["commit_id"],
                commits_created=0,
                total_commits_for_delivery=1,
                held=False,
                finder="HIT",
            )
            self.receipts.append(rec)
            return rec

        if event.get("qc_status") == "fail" or scenario == "bad_qc":
            rec = _receipt(
                event,
                status="FAIL_CLOSED",
                commit_id=None,
                commits_created=0,
                total_commits_for_delivery=0,
                held=False,
                finder="HIT",
            )
            self.receipts.append(rec)
            return rec

        expected = self.expected_seq[adapter_id]
        seq = int(event.get("sequence_no"))
        if seq != expected:
            self.held.append(
                {
                    "event_id": event.get("event_id"),
                    "adapter_id": adapter_id,
                    "delivery_id": delivery_id,
                    "sequence_no": seq,
                    "expected_next": expected,
                }
            )
            rec = _receipt(
                event,
                status="HELD_OUT_OF_ORDER",
                commit_id=None,
                commits_created=0,
                total_commits_for_delivery=0,
                held=True,
                finder="HIT",
            )
            self.receipts.append(rec)
            return rec

        commit_id = "commit-%s" % delivery_id
        self.commits[delivery_id] = {
            "commit_id": commit_id,
            "event_id": event.get("event_id"),
            "adapter_id": adapter_id,
        }
        self.expected_seq[adapter_id] = expected + 1
        rec = _receipt(
            event,
            status="COMMITTED",
            commit_id=commit_id,
            commits_created=1,
            total_commits_for_delivery=1,
            held=False,
            finder="HIT",
        )
        self.receipts.append(rec)
        return rec


def run_pack(root=HERE):
    manifest = load_json(os.path.join(root, MANIFEST_NAME))
    events = load_jsonl(os.path.join(root, EVENTS_NAME))
    bus = MockInstrumentBus(manifest)
    for event in events:
        bus.process(event)
    return {
        "manifest_id": manifest.get("id"),
        "cash_usd": 0,
        "event_count": len(events),
        "receipts": bus.receipts,
        "commit_count": len(bus.commits),
        "held_count": len(bus.held),
        "commits": bus.commits,
        "held": bus.held,
        "finder_probe": find_adapter(bus.adapters, "no-such-adapter"),
    }


def compare_receipts(got, expected):
    failures = []
    if len(got) != len(expected):
        failures.append(
            "receipt count got=%s expected=%s" % (len(got), len(expected))
        )
    for idx, (g, e) in enumerate(zip(got, expected)):
        for key in (
            "event_id",
            "delivery_id",
            "adapter_id",
            "scenario",
            "status",
            "commit_id",
            "commits_created",
            "total_commits_for_delivery",
            "held",
            "finder",
        ):
            if g.get(key) != e.get(key):
                failures.append(
                    "receipt[%s] %s %s != %s (event %s)"
                    % (idx, key, g.get(key), e.get(key), g.get("event_id"))
                )
    return failures


def summarize(result, expected=None):
    receipts = result["receipts"]
    by_status = {}
    for rec in receipts:
        by_status[rec["status"]] = by_status.get(rec["status"], 0) + 1
    commits_by_delivery = {}
    for rec in receipts:
        if rec.get("commits_created"):
            commits_by_delivery.setdefault(rec["delivery_id"], 0)
            commits_by_delivery[rec["delivery_id"]] += rec["commits_created"]
    second_commits = {
        did: n for did, n in commits_by_delivery.items() if n > 1
    }
    failures = []
    if result["event_count"] != 30:
        failures.append("event_count %s != 30" % result["event_count"])
    if second_commits:
        failures.append("second commit created: %s" % second_commits)
    if result["finder_probe"]["status"] != FINDER_UNVERIFIED:
        failures.append(
            "missing-adapter probe status %s (must be FINDER UNVERIFIED)"
            % result["finder_probe"]["status"]
        )
    if result["finder_probe"].get("count") == 0 or result["finder_probe"].get("zero"):
        failures.append("finder probe reported a zero")
    if expected is not None:
        failures.extend(compare_receipts(receipts, expected.get("receipts") or []))
    return {
        "ok": not failures,
        "event_count": result["event_count"],
        "commit_count": result["commit_count"],
        "held_count": result["held_count"],
        "by_status": by_status,
        "second_commits": second_commits,
        "failures": failures,
        "cash_usd": 0,
    }


def expected_payload(result):
    return {
        "schema": "commons-billings-bid-1421-expected-receipts-v1",
        "id": "billings-bid-1421-instrument-fixtures-20260831-01",
        "cash_usd": 0,
        "event_count": result["event_count"],
        "commit_count": result["commit_count"],
        "held_count": result["held_count"],
        "receipts": [
            {
                "event_id": rec["event_id"],
                "delivery_id": rec["delivery_id"],
                "adapter_id": rec["adapter_id"],
                "scenario": rec["scenario"],
                "status": rec["status"],
                "commit_id": rec["commit_id"],
                "commits_created": rec["commits_created"],
                "total_commits_for_delivery": rec["total_commits_for_delivery"],
                "held": rec["held"],
                "finder": rec["finder"],
            }
            for rec in result["receipts"]
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=HERE)
    parser.add_argument("--write-expected", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = run_pack(args.root)
    expected_path = os.path.join(args.root, EXPECTED_NAME)
    if args.write_expected:
        payload = expected_payload(result)
        with open(expected_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        print("WROTE %s (%s receipts)" % (expected_path, len(payload["receipts"])))
        return 0
    expected = None
    if os.path.exists(expected_path):
        expected = load_json(expected_path)
    summary = summarize(result, expected)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("events=%s commits=%s held=%s cash_usd=0" % (
            summary["event_count"],
            summary["commit_count"],
            summary["held_count"],
        ))
        print("by_status=%s" % json.dumps(summary["by_status"], sort_keys=True))
        if summary["ok"]:
            print("PASS")
        else:
            print("FAIL")
            for item in summary["failures"]:
                print(" - %s" % item)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
