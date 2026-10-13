#!/usr/bin/env python3
"""ACK GOAT MATCH sidewalk door 200 after pages-deploy.

Tallies TALLY sidewalk bytes unread-as-write. Does not write the pack.
Does not remint Pages/allowlist. Checkout NOT_MINTED. Not a Commons gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "packs" / "sidewalk-signal-web-desk-20260902-01"
DOOR_REL = "packs/sidewalk-signal-web-desk-20260902-01/index.html"
DOOR_BLOB = "638e60b4"
DOOR_LIVE_CASH_V1 = (
    '<p id="live-cash" class="note"><strong>Live cash</strong> — '
    '<a href="../../agent-rescue.html">$29 Autopsy</a> · '
    '<a href="../../dealer-service-lead-rescue.html">$199 dealer</a> · '
    '<a href="../../referral-intake-completeness.html">$199 referral</a> · '
    '<a href="../../repair-booking-preflight.html">$199 repair</a> · '
    '<a href="../../plant-downtime-handoff.html">$199 plant</a>.</p>\n'
    '<p class="note"><strong>Larger fixed engagements</strong> (separate product pages; checkout/intent stays there): '
    '<a href="../../diagnostic.html">GGUF diagnostic · $12,000 / 10 days</a> · '
    '<a href="../../commercial.html">White Box pilot · $30,000 / 30 days</a>. '
    'Not remints of tip SKUs.</p>\n\n'
).encode("utf-8")
DOOR_TITANMCP_PAD_POINTER_V1 = (
    '<section id="titanmcp-pad-pointer" class="law" aria-label="titanmcp contest pad">\n'
    '  <strong>titanmcp pad (contest):</strong> '
    '<a href="https://webmcp-pad.vercel.app/">webmcp-pad.vercel.app</a> — '
    '<code>titanmcp 1.4.5</code> · 24 tools · Agent Resources · '
    '<a href="../../titanmcp.html">titanmcp.html</a>. '
    'Commons Shared Pad / <code>/mcp</code> KEEP separate.\n'
    '</section>\n\n'
).encode("utf-8")
DOOR_SOLD_ONCE_CSS_V1 = (
    ".badge{display:inline-block;border:1px solid #d98a00;color:#7a4b00;"
    "border-radius:999px;padding:.2rem .7rem;font-size:.9rem;margin:.2rem 0}\n"
    ".anchor{color:#555;font-size:.92rem}\n"
).encode("utf-8")
DOOR_SOLD_ONCE_COPY_V1 = (
    "<!-- sold-once-badge --><p class=\"badge\">Instance 1 of 1. "
    "This brand, this domain, this door are sold once.</p><!-- /sold-once-badge -->\n"
    '<p class="anchor">Anchor line (owner-paste slot): '
    '<code data-slot="anchor_line">OWNER_UNSET</code></p>\n'
    "<p>One buyer gets this instance: the name <strong>Sidewalk Signal</strong>, "
    "this door, and every file listed below. The next buyer of this vertical gets "
    "a different name, door and instruction set. The badge above is written by the "
    "pack verifier from its own verdict, not by hand.</p>"
).encode("utf-8")
DOOR_SOLD_ONCE_COPY_BASELINE = (
    "<p>One buyer gets this instance: the name <strong>Sidewalk Signal</strong>, "
    "this door, and every file listed below. The next buyer of this vertical gets "
    "a different name, door and instruction set.</p>"
).encode("utf-8")
PAGES_CRON_CURRENT = b"    - cron: '7,17,27,37,47,57 * * * *'\n"
PAGES_CRON_AT_LAND = b"    - cron: '*/10 * * * *'\n"
PAGES_DEPLOY_RUN = "33601287295"
PAGES_DEPLOY_SHA = "e86ff8f3e47fda6d56ee67ac304d8a3e3ce40747"
RECEIPT_ID = "cursor-goat-match-sidewalk-door-200-20260902-01"
TALLY_IDS = (
    "tally-desk-website-service-pack-20260902-01",
    "tally-sidewalk-creative-brief-20260902-01",
    "tally-sidewalk-gems-note-20260902-01",
)
PAGES_IDS = (
    "goat-pages-deploy-queue-unblock-match-20260902-01",
    "cursor-pages-deploy-json-overwrite-20260902-01",
    "cursor-pages-deploy-receipt-intree-20260902-01",
    "commons-pages-workflow-deploy-20260902-01",
)
# Observed-at-land only. This leftover does not pin live TALLY blobs
# except the already-peer-pinned door.
OBSERVED_AT_LAND = {
    DOOR_REL: DOOR_BLOB,
    "host/business_pack_desk_instance.py": "1029faad",
    ".github/workflows/pages-deploy.yml": "7bb72d05",
    "pages-deploy.json": "475d5f24",
}
THIS_SEAT_DOES_NOT_WRITE = (
    DOOR_REL,
    "packs/sidewalk-signal-web-desk-20260902-01",
    "host/business_pack_desk_instance.py",
    "test_business_pack_desk_instance.py",
    ".github/workflows/pages-deploy.yml",
    "pages-deploy.json",
)


def _git_blob_bytes(data: bytes, n: int = 8) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()[:n]


def _committed_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def git_blob(rel: str, n: int = 8) -> str:
    path = ROOT / rel
    if not path.is_file():
        return ""
    return _git_blob_bytes(_committed_bytes(path), n)


def _normalize_successors(
    data: bytes, replacements: tuple[tuple[str, bytes, bytes], ...]
) -> tuple[bytes, list[str]]:
    """Reverse only named, byte-exact successor edits back to the land baseline."""
    applied: list[str] = []
    for label, successor, baseline in replacements:
        count = data.count(successor)
        if count > 1:
            return data, [f"AMBIGUOUS:{label}"]
        if count == 1:
            data = data.replace(successor, baseline, 1)
            applied.append(label)
    return data, applied


def normalized_observation(rel: str) -> dict[str, Any]:
    path = ROOT / rel
    if not path.is_file():
        return {"blob": "", "baseline_blob": "", "successors": []}
    data = _committed_bytes(path)
    replacements: tuple[tuple[str, bytes, bytes], ...] = ()
    if rel == DOOR_REL:
        replacements = (
            ("sold-once-css-v1", DOOR_SOLD_ONCE_CSS_V1, b""),
            ("sold-once-copy-v1", DOOR_SOLD_ONCE_COPY_V1, DOOR_SOLD_ONCE_COPY_BASELINE),
            ("live-cash-v1", DOOR_LIVE_CASH_V1, b""),
            ("titanmcp-pad-pointer-v1", DOOR_TITANMCP_PAD_POINTER_V1, b""),
        )
    elif rel == ".github/workflows/pages-deploy.yml":
        replacements = (("pages-cron-offset-v1", PAGES_CRON_CURRENT, PAGES_CRON_AT_LAND),)
    normalized, successors = _normalize_successors(data, replacements)
    return {
        "blob": _git_blob_bytes(data),
        "baseline_blob": _git_blob_bytes(normalized),
        "successors": successors,
    }


def checkout_status() -> str:
    checkout_md = (PACK / "checkout.md").read_text(encoding="utf-8")
    manifest = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))
    checkout = manifest.get("checkout") if isinstance(manifest, dict) else {}
    status = ""
    if isinstance(checkout, dict):
        status = str(checkout.get("status") or "")
    if "status: NOT_MINTED" not in checkout_md:
        return status or "MISSING"
    return status


def tally_pack() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(PACK.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        blob = hashlib.sha1(
            b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        ).hexdigest()
        rows.append({"path": rel, "blob": blob[:8], "size": len(data)})
    return rows


def classify_match() -> dict[str, Any]:
    files = tally_pack()
    total_bytes = sum(int(row["size"]) for row in files)
    door_blob = git_blob(DOOR_REL)
    checkout = checkout_status()
    tally_present = all((ROOT / "p" / f"{pid}.md").is_file() for pid in TALLY_IDS)
    pages_present = all((ROOT / "p" / f"{pid}.md").is_file() for pid in PAGES_IDS)
    observed = {rel: git_blob(rel) for rel in OBSERVED_AT_LAND}
    door_observation = normalized_observation(DOOR_REL)
    pages_workflow_observation = normalized_observation(
        ".github/workflows/pages-deploy.yml"
    )
    door_match = door_observation["baseline_blob"] == DOOR_BLOB
    pages_untouched = (
        pages_workflow_observation["baseline_blob"]
        == OBSERVED_AT_LAND[".github/workflows/pages-deploy.yml"]
        and observed.get("pages-deploy.json") == OBSERVED_AT_LAND["pages-deploy.json"]
    )
    match_ok = (
        door_match
        and checkout == "NOT_MINTED"
        and tally_present
        and pages_present
        and pages_untouched
        and bool(files)
    )
    return {
        "gate": False,
        "commons_admission": False,
        "no_auth": True,
        "id": RECEIPT_ID,
        "kind": "GOAT_SIDEWALK_DOOR_MATCH",
        "unread_as_write": True,
        "did_not_write_pack": True,
        "did_not_remint_pages_allowlist": True,
        "pages_deploy_run": PAGES_DEPLOY_RUN,
        "pages_deploy_sha": PAGES_DEPLOY_SHA,
        "door": DOOR_REL,
        "door_blob": door_blob,
        "door_baseline_blob": door_observation["baseline_blob"],
        "door_successors": door_observation["successors"],
        "pages_workflow_blob": pages_workflow_observation["blob"],
        "pages_workflow_baseline_blob": pages_workflow_observation["baseline_blob"],
        "pages_workflow_successors": pages_workflow_observation["successors"],
        "door_size": next(
            (int(row["size"]) for row in files if row["path"] == DOOR_REL), 0
        ),
        "checkout": checkout,
        "file_count": len(files),
        "total_bytes": total_bytes,
        "files": files,
        "tally_ids": list(TALLY_IDS),
        "tally_ids_present": tally_present,
        "pages_ids": list(PAGES_IDS),
        "pages_ids_present": pages_present,
        "observed_at_land": OBSERVED_AT_LAND,
        "this_seat_does_not_write": list(THIS_SEAT_DOES_NOT_WRITE),
        "match_ok": match_ok,
        "agents_spend_ads": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Tally TALLY sidewalk bytes unread-as-write. No write."
    )
    parser.add_argument("--json", action="store_true", help="print classify_match JSON")
    args = parser.parse_args()
    result = classify_match()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            f"MATCH_OK={result['match_ok']} files={result['file_count']} "
            f"bytes={result['total_bytes']} door={result['door_blob']} "
            f"checkout={result['checkout']} run={result['pages_deploy_run']}"
        )
    return 0 if result["match_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
