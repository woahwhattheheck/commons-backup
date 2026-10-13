#!/usr/bin/env python3
"""Sprint integration: exact verdicts, exact evidence, pulse wiring preserved."""
from __future__ import annotations

import ast
import json
import os
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "host"))
import sprint_integration as si

ROOT = os.path.dirname(os.path.abspath(__file__))
FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("ok  ", name)
        return
    FAILED.append(name)
    print("FAIL", name, detail)


def test_fixtures():
    expected = {
        "disjoint": "CLEAR_TO_MERGE",
        "identical_blobs": "DEDUPED",
        "additive_compose": "COMPOSE_AND_MERGE",
        "semantic_conflict": "CONFLICT",
    }
    policy = si.load_policy(ROOT)
    check("policy verdicts", policy["verdicts"] == list(si.VERDICTS))
    check("policy fixtures map", policy["fixtures"] == expected)
    check("policy rule ids", [r["id"] for r in policy["rules"]] == list(si.RULE_IDS))
    for name, verdict in expected.items():
        result = si.classify_fixture(name)
        check("%s verdict" % name, result["verdict"] == verdict, result["verdict"])
        check("%s has SHAs fields" % name, all(k in result for k in (
            "base_sha", "left_sha", "right_sha", "overlapping_paths",
            "blob_hashes", "rule_ids", "reasons",
        )))
        check("%s not_stopping" % name, result["not_stopping"] == list(si.NOT_STOPPING))
        if name == "disjoint":
            check("disjoint overlap empty", result["overlapping_paths"] == [])
            check("disjoint rule", "SI-DISJOINT" in result["rule_ids"])
            check("disjoint left path", "keep.py" in result["left_paths"])
            check("disjoint right path", "other.md" in result["right_paths"])
        if name == "identical_blobs":
            check("identical overlap", result["overlapping_paths"] == ["shared.txt"])
            blob = result["blob_hashes"]["shared.txt"]
            check("identical same blob", blob["left"] == blob["right"] and blob["left"])
            check("identical rule", "SI-IDENTICAL-BLOB" in result["rule_ids"])
            check("identical blob is git sha", len(blob["left"]) == 40)
        if name == "additive_compose":
            check("compose json+py overlap", set(result["overlapping_paths"]) == {"config.json", "util.py"})
            check("compose not conflict", result["verdict"] != "CONFLICT")
            ids = set(result["rule_ids"])
            check("compose uses additive or json", bool(ids & {"SI-ADDITIVE-INSERT", "SI-JSON-KEY-UNION"}))
            for path in result["overlapping_paths"]:
                blobs = result["blob_hashes"][path]
                check("%s blobs differ" % path, blobs["left"] != blobs["right"])
        if name == "semantic_conflict":
            check("conflict path", result["overlapping_paths"] == ["flag.py"])
            check("conflict rule", "SI-SEMANTIC-DISAGREE" in result["rule_ids"])
            blobs = result["blob_hashes"]["flag.py"]
            check("conflict blobs differ", blobs["left"] != blobs["right"] != blobs["base"])


def test_not_stopping():
    result = si.classify_fixture(
        "disjoint",
        meta={"busy_main": True, "stale_base": True, "unrelated_checks": True, "base_sha": "aa" * 20, "left_sha": "bb" * 20, "right_sha": "cc" * 20},
    )
    check("stale base still CLEAR", result["verdict"] == "CLEAR_TO_MERGE")
    check("facts recorded", result["facts"]["stale_base"] is True and result["facts"]["busy_main"] is True)
    check("facts are not verdicts", result["verdict"] not in si.NOT_STOPPING)
    conflict = si.classify_fixture("semantic_conflict", meta={"unrelated_checks": True, "busy_main": True})
    check("unrelated checks do not hide CONFLICT", conflict["verdict"] == "CONFLICT")
    check("unrelated checks still a fact", conflict["facts"]["unrelated_checks"] is True)


def test_json_and_text_in_memory():
    base = {"a.json": b'{"k": 1}'}
    left = {"a.json": b'{"k": 1, "l": 2}'}
    right = {"a.json": b'{"k": 1, "r": 3}'}
    got = si.classify_pair(base, left, right)
    check("json key union", got["verdict"] == "COMPOSE_AND_MERGE", got)
    left_c = {"a.json": b'{"k": 2}'}
    right_c = {"a.json": b'{"k": 3}'}
    got = si.classify_pair(base, left_c, right_c)
    check("json scalar conflict", got["verdict"] == "CONFLICT", got)
    base_t = {"x.py": b"A = 1\n"}
    left_t = {"x.py": b"A = 1\nB = 2\n"}
    right_t = {"x.py": b"A = 1\nC = 3\n"}
    got = si.classify_pair(base_t, left_t, right_t)
    check("insert-only compose", got["verdict"] == "COMPOSE_AND_MERGE", got)


def test_pulse_scan_mock():
    head = "m" * 40
    left_body = b'{"keep": 1, "left_only": true}'
    right_body = b'{"keep": 1, "right_only": true}'
    base_body = b'{"keep": 1}'
    blobs = {
        si.git_blob_sha(left_body): left_body,
        si.git_blob_sha(right_body): right_body,
        si.git_blob_sha(base_body): base_body,
    }

    def fetch_json(path, **params):
        if path.endswith("/pulls") and params.get("state") == "open":
            return [
                {"number": 1, "title": "left", "base": {"sha": "old" * 10}, "head": {"sha": "l" * 40}},
                {"number": 2, "title": "right", "base": {"sha": head}, "head": {"sha": "r" * 40}},
                {"number": 3, "title": "other", "base": {"sha": head}, "head": {"sha": "o" * 40}},
            ]
        if path.endswith("/pulls/1/files"):
            return [{"filename": "config.json", "sha": si.git_blob_sha(left_body), "status": "modified"}]
        if path.endswith("/pulls/2/files"):
            return [{"filename": "config.json", "sha": si.git_blob_sha(right_body), "status": "modified"}]
        if path.endswith("/pulls/3/files"):
            return [{"filename": "only-right.md", "sha": "d" * 40, "status": "added"}]
        if "/git/blobs/" in path:
            sha = path.rsplit("/", 1)[-1]
            if sha in blobs:
                import base64
                return {"content": base64.b64encode(blobs[sha]).decode("ascii"), "encoding": "base64"}
            return None
        if path.endswith("/contents/config.json"):
            import base64
            return {"type": "file", "sha": si.git_blob_sha(base_body), "content": base64.b64encode(base_body).decode("ascii"), "encoding": "base64"}
        return None

    scan = si.pulse_scan(fetch_json, "woahwhattheheck/commons", head)
    check("pulse three prs", len(scan["prs"]) == 3, scan["prs"])
    check("pulse one overlapping pair", len(scan["pairs"]) == 1, scan["pairs"])
    pair = scan["pairs"][0]
    check("pulse pair compose", pair["verdict"] == "COMPOSE_AND_MERGE", pair)
    check("pulse pair stale fact", pair["facts"]["stale_base"] is True)
    check("pulse #3 clear", scan["by_pr"]["3"]["verdict"] == "CLEAR_TO_MERGE", scan["by_pr"])
    check("pulse slack teaches", "MERGE DEFAULT" in scan["slack_lines"][0])
    check("pulse slack policy link", "ground/SPRINT_INTEGRATION.json" in scan["slack_lines"][0])
    text = "\n".join(scan["slack_lines"])
    check("pulse slack has verdicts", "COMPOSE_AND_MERGE" in text and "CLEAR_TO_MERGE" in text, text)


def test_malformed_rows_preserve_valid_prs():
    head = "a" * 40
    calls = []

    def fetch_json(path, **params):
        calls.append(path)
        if path.endswith("/pulls"):
            return [
                None, "not-a-row", {}, {"number": "invalid"}, {"number": 0},
                {"number": "7", "base": {"sha": head}, "head": {"sha": "b" * 40}},
                {"number": 8, "base": {"sha": head}, "head": {"sha": "c" * 40}},
            ]
        if path.endswith("/files"):
            number = path.split("/")[-2]
            return [None, "not-a-file", {"filename": "pr%s.txt" % number, "sha": "d" * 40}]
        return None

    scan = si.pulse_scan(fetch_json, "woahwhattheheck/commons", head)
    check("malformed rows retain valid PRs", [row["number"] for row in scan["prs"]] == [7, 8], scan)
    check("malformed file rows retain valid paths", scan["prs"][0]["paths"] == ["pr7.txt"], scan)
    check("valid disjoint PRs remain clear", all(row["verdict"] == "CLEAR_TO_MERGE" for row in scan["by_pr"].values()), scan)
    before = list(calls)
    check("invalid PR number returns no files", si._pr_files(fetch_json, "woahwhattheheck/commons", None) == {})
    check("invalid PR number causes no fetch", calls == before, calls)
    lines = si.format_slack_lines({
        "by_pr": {"invalid": {}, "7": {"verdict": "DEDUPED"}, "8": None},
        "prs": [None, "not-a-row", {"number": "invalid"}, {"number": 7, "head_sha": "b" * 40}],
    })
    text = "\n".join(lines)
    check("Slack rendering retains valid verdict", "`#7` *DEDUPED*" in text, text)
    check("Slack rendering drops malformed verdict rows", "`#8`" not in text and "invalid" not in text, text)


def test_pulse_yml_preserved():
    yml = open(os.path.join(ROOT, ".github/workflows/repo-pulse.yml"), encoding="utf-8").read()
    engine = open(os.path.join(ROOT, "repo_pulse.py"), encoding="utf-8").read()
    check("pulse still named repo-pulse", "\nname: repo-pulse\n" in yml)
    check("pulse still COMMONS_SLACK_MIRROR", "COMMONS_SLACK_MIRROR" in yml and "COMMONS_SLACK_MIRROR" in engine)
    check("pulse still EVENT_GAP", "EVENT_GAP" in engine)
    check("pulse still compare range", "previous_head" in engine and "commit_range" in engine)
    check("pulse still idle heartbeat", "PULSE_IDLE_HEARTBEAT_MINUTES" in yml)
    check("pulse still artifact not commit", "upload-artifact@v4" in yml)
    check("pulse still no checkout of the 1GB repo", "actions/checkout" not in yml)
    check("pulse still fetches engine", "fetch repo_pulse.py" in yml)
    check("pulse wires checker", "host/sprint_integration.py" in yml and "host/sprint_integration.py" in engine)
    check("pulse wires policy", "ground/SPRINT_INTEGRATION.json" in yml and "ground/SPRINT_INTEGRATION.json" in engine)
    check("pulse wires four verdicts", all(v in engine for v in (
        "CLEAR_TO_MERGE", "COMPOSE_AND_MERGE", "DEDUPED", "CONFLICT",
    )))
    check("pulse status still CLEAR/ATTENTION/BROKEN",
          'return "BROKEN"' in engine and 'return "ATTENTION"' in engine and 'return "CLEAR"' in engine)
    check("classify_status signature unchanged", "def classify_status(health, gaps, exhausted, settings, backup):" in engine)


def main():
    test_fixtures()
    test_not_stopping()
    test_json_and_text_in_memory()
    test_pulse_scan_mock()
    test_malformed_rows_preserve_valid_prs()
    test_pulse_yml_preserved()
    if FAILED:
        print("SPRINT INTEGRATION TEST: FAIL", len(FAILED), ":", ", ".join(FAILED))
        return 1
    print("SPRINT INTEGRATION TEST: ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
