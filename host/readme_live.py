#!/usr/bin/env python3
"""host/readme_live.py — README is the live door, not a closed roster.

Slack 1787643027.186729 (Bryce flag): the GitHub mobile README still
named the day-one nine-home list. That list is historical .mno mail
rings, not who may post. A bake (orient.json) is not who is present.

This leftover measures README.md against current Commons architecture.
A miss prints FINDER-FAILED plus the search space. Never 0. Talk that
restates the screenshot is CLAIMED until this leftover is on main.

  python3 host/readme_live.py
  python3 host/readme_live.py --root .
  python3 host/readme_live.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_README = "README.md"
DEFAULT_CARD = os.path.join("ground", "README_LIVE.md")
DEFAULT_CATALOG = os.path.join("ground", "README_LIVE.json")
DEVICE_CYCLE_PATH = os.path.join(".github", "workflows", "commons-device-cycle.yml")
SLACK_TS = "1787643027.186729"
STALE_ROSTER = "ZERO GROK KITE CAIRN SPALL GRAVE AXIOM SHARD SCREE"
CATALOG_REQUIRED_PATHS = (
    "START.md",
    "boards.html",
    "ground/PICK.md",
    "action.html",
    "reply.html",
    "names.html",
    ".github/workflows/commons-device-cycle.yml",
)
DEVICE_CYCLE_REQUIREMENTS = (
    ("prepare", "reservation output", None, "reservation_count: ${{ steps.prepare.outputs.reservation_count }}", "exact"),
    ("prepare", "prepared commit output", None, "prepared_commit: ${{ steps.prepare.outputs.prepared_commit }}", "exact"),
    ("prepare", "batch path output", None, "batch_path: ${{ steps.prepare.outputs.batch_path }}", "exact"),
    ("prepare", "batch hash output", None, "batch_sha256: ${{ steps.prepare.outputs.batch_sha256 }}", "exact"),
    ("prepare", "prepare checkout action", "- uses: actions/checkout@", "- uses: actions/checkout@", "prefix"),
    ("prepare", "prepare checkout inputs", "- uses: actions/checkout@", "with:", "exact"),
    ("prepare", "prepare fresh main checkout", "- uses: actions/checkout@", "ref: main", "exact"),
    ("prepare", "prepare step", "- id: prepare", "- id: prepare", "exact"),
    ("prepare", "prepare command", "- id: prepare", "if python3 device_action_state.py prepare", "prefix"),
    ("prepare", "prepare output binding", "- id: prepare", "--github-output \"$GITHUB_OUTPUT\"; then", "exact"),
    ("execute", "prepare dependency", None, "needs: prepare", "exact"),
    ("execute", "pending reservation condition", None, "if: needs.prepare.outputs.reservation_count != '0'", "exact"),
    ("execute", "self-hosted receiver", None, "runs-on: [self-hosted, commons-device]", "exact"),
    ("execute", "execute checkout action", "- uses: actions/checkout@", "- uses: actions/checkout@", "prefix"),
    ("execute", "execute checkout inputs", "- uses: actions/checkout@", "with:", "exact"),
    ("execute", "prepared commit checkout", "- uses: actions/checkout@", "ref: ${{ needs.prepare.outputs.prepared_commit }}", "exact"),
    ("execute", "execute step", "- name: execute the prepared batch", "- name: execute the prepared batch", "prefix"),
    ("execute", "execute command", "- name: execute the prepared batch", "python3 device_action_state.py execute-batch", "exact"),
    ("execute", "execute commit binding", "- name: execute the prepared batch", "--prepared-commit \"${{ needs.prepare.outputs.prepared_commit }}\"", "exact"),
    ("execute", "execute batch path binding", "- name: execute the prepared batch", "--batch-path \"${{ needs.prepare.outputs.batch_path }}\"", "exact"),
    ("execute", "execute batch hash binding", "- name: execute the prepared batch", "--batch-sha256 \"${{ needs.prepare.outputs.batch_sha256 }}\"", "exact"),
    ("execute", "receipt upload", "- uses: actions/upload-artifact@", "- uses: actions/upload-artifact@", "prefix"),
    ("execute", "receipt upload inputs", "- uses: actions/upload-artifact@", "with:", "exact"),
    ("execute", "receipt upload name", "- uses: actions/upload-artifact@", "name: commons-device-receipts-${{ github.run_id }}-${{ github.run_attempt }}", "exact"),
    ("execute", "receipt upload path", "- uses: actions/upload-artifact@", "path: ${{ runner.temp }}/device-receipts", "exact"),
    ("execute", "receipt required", "- uses: actions/upload-artifact@", "if-no-files-found: error", "exact"),
    ("finalize", "execute success dependency", None, "needs: [prepare, execute]", "exact"),
    ("finalize", "execute success condition", None, "if: ${{ always() && needs.prepare.result == 'success' && needs.execute.result == 'success' && needs.prepare.outputs.reservation_count != '0' }}", "exact"),
    ("finalize", "finalize checkout action", "- uses: actions/checkout@", "- uses: actions/checkout@", "prefix"),
    ("finalize", "finalize checkout inputs", "- uses: actions/checkout@", "with:", "exact"),
    ("finalize", "finalize fresh main checkout", "- uses: actions/checkout@", "ref: main", "exact"),
    ("finalize", "receipt download", "- uses: actions/download-artifact@", "- uses: actions/download-artifact@", "prefix"),
    ("finalize", "receipt download inputs", "- uses: actions/download-artifact@", "with:", "exact"),
    ("finalize", "receipt download name", "- uses: actions/download-artifact@", "name: commons-device-receipts-${{ github.run_id }}-${{ github.run_attempt }}", "exact"),
    ("finalize", "receipt download path", "- uses: actions/download-artifact@", "path: ${{ runner.temp }}/device-receipts", "exact"),
    ("finalize", "finalize step", "- name: validate every receipt", "- name: validate every receipt", "prefix"),
    ("finalize", "finalize commit env", "- name: validate every receipt", "COMMONS_PREPARED_COMMIT: ${{ needs.prepare.outputs.prepared_commit }}", "exact"),
    ("finalize", "finalize batch path env", "- name: validate every receipt", "COMMONS_BATCH_PATH: ${{ needs.prepare.outputs.batch_path }}", "exact"),
    ("finalize", "finalize batch hash env", "- name: validate every receipt", "COMMONS_BATCH_SHA256: ${{ needs.prepare.outputs.batch_sha256 }}", "exact"),
    ("finalize", "fresh main reset", "- name: validate every receipt", "git reset --hard origin/main", "exact"),
    ("finalize", "finalize command", "- name: validate every receipt", "if python3 device_action_state.py finalize", "prefix"),
    ("finalize", "receipt source binding", "- name: validate every receipt", "--source \"$RUNNER_TEMP/device-receipts\"", "prefix"),
    ("finalize", "finalize commit binding", "- name: validate every receipt", "--prepared-commit \"$COMMONS_PREPARED_COMMIT\"", "prefix"),
    ("finalize", "finalize batch path binding", "- name: validate every receipt", "--batch-path \"$COMMONS_BATCH_PATH\"", "prefix"),
    ("finalize", "finalize batch hash binding", "- name: validate every receipt", "--batch-sha256 \"$COMMONS_BATCH_SHA256\"; then", "exact"),
)
DEVICE_CYCLE_STEP_ORDER = {
    "prepare": ("- uses: actions/checkout@", "- id: prepare"),
    "execute": (
        "- uses: actions/checkout@",
        "- name: execute the prepared batch",
        "- uses: actions/upload-artifact@",
    ),
    "finalize": (
        "- uses: actions/checkout@",
        "- uses: actions/download-artifact@",
        "- name: validate every receipt",
    ),
}
SEARCH_SPACE = (
    DEFAULT_README,
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "readme_live.py"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
    DEVICE_CYCLE_PATH,
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_PHRASES = (
    "open public board and action surface",
    "anyone with the link",
    "start.md",
    "boards.html",
    "ground/pick.md",
    "unseated",
    "no seat",
    "no auth",
    "possessing the link",
    "action.html",
    "reply.html",
    "p/{id}.md",
    "ship to current main",
    "talk is not landed",
    "http is not the computer",
    "any nonblank read, write, or execute verb",
    "addressed device actions",
    "self-hosted",
    "commons-device",
    "durable device result proves pc execution",
    "names.html",
)
FORBIDDEN_PHRASES = (
    STALE_ROSTER,
    "who is present: orient.json",
    "do not write the owner's pc",
)
BAKE_WHO = "orient.json"


def _read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def load_catalog(text):
    """Parse the readme-live catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON", "stale_roster": ""}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object", "stale_roster": ""}
    return {
        "id": str(data.get("id") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "stale_roster": str(data.get("stale_roster") or "").strip(),
        "stale_roster_role": str(data.get("stale_roster_role") or "").strip(),
        "bake_who_is_present": str(data.get("bake_who_is_present") or "").strip(),
        "required_paths": [
            str(item or "").strip()
            for item in (data.get("required_paths") or [])
            if str(item or "").strip()
        ],
        "no_auth": data.get("no_auth") is True,
        "no_gate": data.get("no_gate") is True,
        "posting_open": data.get("posting_open") is True,
        "device_bridge": str(data.get("device_bridge") or "").strip(),
        "device_proof": str(data.get("device_proof") or "").strip(),
    }


def _lower(text):
    return str(text or "").lower()


def measure_readme(text):
    """Score one README body. Does not invent stillness."""
    body = str(text or "")
    low = _lower(body)
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in low]
    forbidden = [phrase for phrase in FORBIDDEN_PHRASES if phrase.lower() in low]
    treats_bake_as_presence = (
        "who is present" in low and BAKE_WHO in low and "do not treat" not in low
    )
    return {
        "readme_bytes": len(body.encode("utf-8")),
        "found_phrases": found,
        "missing_phrases": [p for p in REQUIRED_PHRASES if p not in found],
        "forbidden_hits": forbidden,
        "stale_roster": STALE_ROSTER in body,
        "treats_bake_as_presence": treats_bake_as_presence,
        "open_door": "open door" in low,
        "no_auth": "no auth" in low,
        "no_gate": all(phrase in low for phrase in (
            "no seat", "no auth", "no action tier",
        )),
        "posting_open": "possessing the link" in low and "unseated" in low,
        "action_pad": "action.html" in low,
        "head_truth": "p/{id}.md" in low or "p/{id}.md" in body,
        "ship_main": "ship to current main" in low,
    }


def measure_device_cycle(text):
    """Require ordered, uncommented prepare -> receiver -> finalize bindings."""
    lines = []
    for raw in str(text or "").splitlines():
        if raw.lstrip().startswith("#"):
            continue
        code = raw.split(" #", 1)[0].rstrip()
        if code.strip():
            lines.append(code)

    try:
        jobs_index = lines.index("jobs:")
    except ValueError:
        jobs_index = -1
    job_headers = []
    if jobs_index >= 0:
        for index, line in enumerate(lines[jobs_index + 1:], jobs_index + 1):
            stripped = line.strip()
            if (
                line.startswith("  ")
                and not line.startswith("    ")
                and stripped.endswith(":")
                and " " not in stripped[:-1]
            ):
                job_headers.append((index, stripped[:-1]))
    starts = {job: index for index, job in job_headers}
    ordered_jobs = (
        all(job in starts for job in ("prepare", "execute", "finalize"))
        and starts.get("prepare", -1) < starts.get("execute", -1) < starts.get("finalize", -1)
    )

    blocks = {}
    if ordered_jobs:
        header_positions = [index for index, _job in job_headers]
        for job in ("prepare", "execute", "finalize"):
            start = starts[job] + 1
            end = next(
                (index for index in header_positions if index > starts[job]),
                len(lines),
            )
            blocks[job] = lines[start:end]

    step_blocks = {}
    job_metadata = {}
    for job, block in blocks.items():
        step_starts = [
            index
            for index, line in enumerate(block)
            if line.startswith("      - ")
        ]
        job_metadata[job] = [
            line.strip()
            for line in block[:step_starts[0] if step_starts else len(block)]
        ]
        parsed_steps = []
        for offset, start in enumerate(step_starts):
            end = step_starts[offset + 1] if offset + 1 < len(step_starts) else len(block)
            parsed_steps.append([line.strip() for line in block[start:end]])
        step_blocks[job] = parsed_steps

    def scope_lines(job, anchor):
        if anchor is None:
            return job_metadata.get(job, [])
        for step in step_blocks.get(job, []):
            if step and step[0].startswith(anchor):
                return step
        return []

    found = []
    missing = []
    scope_positions = {}
    for job, label, anchor, token, mode in DEVICE_CYCLE_REQUIREMENTS:
        block = scope_lines(job, anchor)
        matches = (
            [index for index, line in enumerate(block) if line.startswith(token)]
            if mode == "prefix"
            else [index for index, line in enumerate(block) if line == token]
        )
        if matches:
            found.append(label)
        else:
            missing.append(label)
        scope_positions.setdefault((job, anchor), []).append(
            matches[0] if matches else -1
        )

    stage_order_ok = ordered_jobs
    for positions in scope_positions.values():
        if any(position < 0 for position in positions) or positions != sorted(positions):
            stage_order_ok = False
    for job, anchors in DEVICE_CYCLE_STEP_ORDER.items():
        steps = step_blocks.get(job, [])
        positions = []
        for anchor in anchors:
            matches = [
                index
                for index, step in enumerate(steps)
                if step and step[0].startswith(anchor)
            ]
            positions.append(matches[0] if matches else -1)
        if any(position < 0 for position in positions) or positions != sorted(positions):
            stage_order_ok = False

    return {
        "device_cycle_found": found,
        "device_cycle_missing": missing,
        "device_cycle_stage_order": stage_order_ok,
        "device_cycle_grounded": ordered_jobs and stage_order_ok and not missing,
    }


def measure_from_rows(rows):
    """Fold pre-measured rows. Missing keys stay unknown, never 0."""
    data = dict(rows or {})
    data.setdefault("measured", True)
    data.setdefault("misses", list(data.get("misses") or []))
    data.setdefault("found_phrases", list(data.get("found_phrases") or []))
    data.setdefault("missing_phrases", list(data.get("missing_phrases") or []))
    data.setdefault("forbidden_hits", list(data.get("forbidden_hits") or []))
    data.setdefault("calibration_hits", list(data.get("calibration_hits") or []))
    return data


def measure_root(root=DEFAULT_ROOT):
    """Read the live tree. A missing file is a miss, not stillness."""
    root = os.path.abspath(root)
    misses = [rel for rel in SEARCH_SPACE if not _exists(root, rel)]
    calibration_hits = [
        rel for rel in CALIBRATION if "execute immediately" in _lower(_read(root, rel))
        or "action pad" in _lower(_read(root, rel))
        or "a bake is not the board" in _lower(_read(root, rel))
    ]
    catalog = load_catalog(_read(root, DEFAULT_CATALOG))
    readme = measure_readme(_read(root, DEFAULT_README))
    card = _read(root, DEFAULT_CARD)
    device_cycle = measure_device_cycle(_read(root, DEVICE_CYCLE_PATH))
    catalog_paths = set(catalog.get("required_paths") or [])
    catalog_path_misses = [
        rel for rel in CATALOG_REQUIRED_PATHS
        if rel not in catalog_paths or not _exists(root, rel)
    ]
    for rel in catalog_path_misses:
        if rel not in misses:
            misses.append(rel)
    device_catalog_grounded = (
        all(token in _lower(catalog.get("device_bridge")) for token in (
            "addressed device action",
            "current-main prepare",
            "self-hosted commons-device cycle",
            "durable result",
        ))
        and "only a durable device result proves pc execution"
        in _lower(catalog.get("device_proof"))
    )
    measured = measure_from_rows(
        {
            "card_present": _exists(root, DEFAULT_CARD),
            "catalog_present": _exists(root, DEFAULT_CATALOG) and not catalog.get("error"),
            "readme_present": _exists(root, DEFAULT_README),
            "misses": misses,
            "calibration_ok": len(calibration_hits) == len(CALIBRATION),
            "calibration_hits": calibration_hits,
            "catalog_id": catalog.get("id") or "",
            "catalog_roster": catalog.get("stale_roster") or "",
            "card_names_slack": SLACK_TS in card,
            "catalog_paths_ok": not catalog_path_misses,
            "device_catalog_grounded": device_catalog_grounded,
            **readme,
            **device_cycle,
        }
    )
    measured["no_auth"] = bool(readme.get("no_auth") and catalog.get("no_auth"))
    measured["no_gate"] = bool(readme.get("no_gate") and catalog.get("no_gate"))
    measured["posting_open"] = bool(
        readme.get("posting_open") and catalog.get("posting_open")
    )
    measured["device_bridge_grounded"] = bool(
        measured.get("device_cycle_grounded")
        and measured.get("device_catalog_grounded")
    )
    measured["search_space"] = list(SEARCH_SPACE)
    return measured


def classify(row):
    """State from a measured row. Unmeasured is not stillness."""
    data = dict(row or {})
    if not data.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "not stillness; run the README measure. never 0.",
            "search_space": list(SEARCH_SPACE),
        }
    if not data.get("calibration_ok"):
        return {
            "state": "UNMEASURED",
            "note": "instrument failure: calibration missed EXECUTE/HEAD/Action Pad. never 0.",
            "search_space": list(data.get("search_space") or SEARCH_SPACE),
            "calibration_hits": list(data.get("calibration_hits") or []),
        }
    misses = list(data.get("misses") or [])
    missing = list(data.get("missing_phrases") or [])
    forbidden = list(data.get("forbidden_hits") or [])
    if (
        misses
        or missing
        or forbidden
        or data.get("stale_roster")
        or data.get("treats_bake_as_presence")
        or not data.get("card_present")
        or not data.get("catalog_present")
        or not data.get("readme_present")
        or not data.get("posting_open")
        or not data.get("no_auth")
        or not data.get("no_gate")
        or not data.get("action_pad")
        or not data.get("device_bridge_grounded")
        or not data.get("device_cycle_grounded")
        or not data.get("device_catalog_grounded")
        or not data.get("catalog_paths_ok")
        or not data.get("head_truth")
        or not data.get("ship_main")
        or data.get("catalog_roster") != STALE_ROSTER
        or not data.get("card_names_slack")
    ):
        parts = []
        if misses:
            parts.append("FINDER-FAILED paths " + ",".join(misses))
        if missing:
            parts.append("FINDER-FAILED phrases " + ",".join(missing))
        if forbidden or data.get("stale_roster"):
            parts.append("stale closed roster still printed")
        if data.get("treats_bake_as_presence"):
            parts.append("orient.json treated as who is present")
        if not parts:
            parts.append("FINDER-FAILED live README invariants")
        return {
            "state": "NOT_LANDED",
            "note": "; ".join(parts) + ". never 0.",
            "search_space": list(data.get("search_space") or SEARCH_SPACE),
        }
    return {
        "state": "INTEGRATED",
        "note": "README names the live open door. day-one roster absent. never 0.",
        "search_space": list(data.get("search_space") or SEARCH_SPACE),
    }


def _self_test():
    stale = classify(
        measure_from_rows(
            {
                "calibration_ok": True,
                "stale_roster": True,
                "forbidden_hits": [STALE_ROSTER],
                "card_present": True,
                "catalog_present": True,
                "readme_present": True,
            }
        )
    )
    if stale["state"] != "NOT_LANDED":
        raise SystemExit("self-test: stale roster must be NOT_LANDED")
    empty = classify({})
    if empty["state"] != "UNMEASURED":
        raise SystemExit("self-test: empty measure must be UNMEASURED")
    print("SELF-TEST OK")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure live README architecture")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    measured = measure_root(args.root)
    verdict = classify(measured)
    print(json.dumps({"measure": measured, "verdict": verdict}, indent=2, sort_keys=True))
    return 0 if verdict["state"] == "INTEGRATED" else 2


if __name__ == "__main__":
    sys.exit(main())
