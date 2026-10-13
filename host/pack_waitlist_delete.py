#!/usr/bin/env python3
"""Owner-local waitlist CCPA delete. Compose leftover, not a remint.

The waitlist door says the owner can delete on request and the public door
has no lookup. This leftover rewrites the owner-local JSONL: every row for
that address is dropped. A tombstone keeps only a sha256 of the address so
the owner can prove the delete without storing the email. Public output
never includes @. Sends stay 0. Does not overwrite waitlist.html,
pack_waitlist.py, pixel-gate, thanks, Harborline, TALLY, or LotRibbon.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
WAITLIST_HELPER = ROOT / "host" / "pack_waitlist.py"
DO_NOT_OVERWRITE = (
    "packs/waitlist.html",
    "host/pack_waitlist.py",
    "packs/waitlist-counts.json",
    "ground/BUSINESS_PACK_WAITLIST.json",
    "host/pack_waitlist_pixel_gate.py",
    "packs/thanks.html",
    "host/pack_thanks_pixel.py",
    "packs/desk-website-service-20260902-01/door.html",
    "host/harborline_tally_pack_map.py",
    "host/pack_creative_brief.py",
    "host/business_pack_desk_instance.py",
    "packs/sidewalk-signal-web-desk-20260902-01",
    "packs/lotribbon-greetings-20260902-01",
)


def _load(path: Path) -> Any | None:
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("pack_waitlist", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def email_sha256(email: str) -> str:
    return hashlib.sha256(email.encode("utf-8")).hexdigest()


def _public(payload: dict[str, Any]) -> dict[str, Any]:
    dumped = json.dumps(payload)
    if "@" in dumped:
        raise RuntimeError("waitlist delete leaked an address")
    return payload


def delete(
    jsonl_path: Path,
    email: str,
    *,
    waitlist_path: Path | None = None,
) -> dict[str, Any]:
    waitlist = _load(waitlist_path or WAITLIST_HELPER)
    if waitlist is None:
        return _public(
            {
                "kind": "WAITLIST_DELETE",
                "gate": False,
                "commons_admission": False,
                "verdict": "DELETE_HELPER_MISSING",
                "removed": 0,
                "sends": 0,
                "addresses_public": False,
                "checkout": "NOT_MINTED",
                "do_not_overwrite": list(DO_NOT_OVERWRITE),
            }
        )
    wanted = waitlist.normalize_email(email)
    if not waitlist.EMAIL_RE.match(wanted):
        return _public(
            {
                "kind": "WAITLIST_DELETE",
                "gate": False,
                "commons_admission": False,
                "verdict": "DELETE_INVALID",
                "removed": 0,
                "sends": 0,
                "addresses_public": False,
                "checkout": "NOT_MINTED",
                "do_not_overwrite": list(DO_NOT_OVERWRITE),
            }
        )
    records = waitlist.read_jsonl(jsonl_path)
    kept: list[dict[str, Any]] = []
    removed = 0
    for row in records:
        if waitlist.normalize_email(row.get("email")) == wanted:
            removed += 1
            continue
        kept.append(row)
    if removed == 0:
        counts = waitlist.public_counts_from_records(records)
        return _public(
            {
                "kind": "WAITLIST_DELETE",
                "gate": False,
                "commons_admission": False,
                "verdict": "DELETE_MISSING",
                "removed": 0,
                "counts": counts,
                "sends": 0,
                "addresses_public": False,
                "checkout": "NOT_MINTED",
                "do_not_overwrite": list(DO_NOT_OVERWRITE),
            }
        )
    digest = email_sha256(wanted)
    kept.append(
        {
            "ts": _now(),
            "kind": "delete",
            "email_sha256": digest,
            "sends": 0,
        }
    )
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = jsonl_path.with_suffix(jsonl_path.suffix + ".tmp")
    tmp.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in kept),
        encoding="utf-8",
    )
    tmp.replace(jsonl_path)
    counts = waitlist.public_counts_from_records(waitlist.read_jsonl(jsonl_path))
    return _public(
        {
            "kind": "WAITLIST_DELETE",
            "gate": False,
            "commons_admission": False,
            "verdict": "DELETE_OK",
            "removed": removed,
            "email_sha256": digest,
            "counts": counts,
            "sends": 0,
            "addresses_public": False,
            "pixel_allowed": False,
            "did_not_overwrite_waitlist_door": True,
            "checkout": "NOT_MINTED",
            "do_not_overwrite": list(DO_NOT_OVERWRITE),
            "scout_demand_id": "scout-demand-pack-door-waitlist-20260902-01",
            "receipt_id": "cursor-pack-waitlist-delete-20260902-01",
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", default="")
    parser.add_argument("--email", default="")
    args = parser.parse_args(argv)
    jsonl = Path(args.jsonl) if args.jsonl else Path.home() / ".tjlabs" / "waitlist-signups.jsonl"
    result = delete(jsonl, args.email)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verdict"] in {"DELETE_OK", "DELETE_MISSING"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
