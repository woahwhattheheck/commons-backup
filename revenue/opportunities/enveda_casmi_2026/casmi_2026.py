"""Enveda CASMI 2026 public-fact qualification carrier.

Binds only verified public competition identity. Does not join Kaggle,
submit, contact organizers, or claim prize/cash/revenue.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from typing import Any

COMPETITION_ID = "enveda-CASMI26-molecule-id-mass-spectra"
KAGGLE_URL = (
    "https://www.kaggle.com/competitions/enveda-CASMI26-molecule-id-mass-spectra"
)
OPENED = "2026-09-14"
CLOSES = "2026-12-14"
PRIZE_POOL_USD_PUBLIC_FACT = 50000
FIRST_PLACE_USD_PUBLIC_FACT = 16000
ORGANIZER = "Enveda"
QUALIFY_HOLD = "HOLD_KAGGLE_TERMS_UNACCEPTED"
SCHEMA = "commons-enveda-casmi-2026-qualify/v1"

REQUIRED_SPECTRUM_FIELDS = (
    "spectrum_id",
    "precursor_mz",
    "peaks",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def public_facts() -> dict[str, Any]:
    return {
        "competition_id": COMPETITION_ID,
        "kaggle_url": KAGGLE_URL,
        "opened": OPENED,
        "closes": CLOSES,
        "organizer": ORGANIZER,
        "prize_pool_usd": PRIZE_POOL_USD_PUBLIC_FACT,
        "first_place_usd": FIRST_PLACE_USD_PUBLIC_FACT,
        "prize_is": "PUBLIC_FACT_NOT_CASH",
        "contact_public": "casmi-2026@enveda.com",
    }


def qualify(evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    evidence = dict(evidence or {})
    facts = public_facts()
    kaggle_terms_accepted = bool(evidence.get("kaggle_terms_accepted") is True)
    owner_team_name = evidence.get("owner_team_name")
    owner_go = evidence.get("owner_submission_authorized") is True
    missing = []
    if not kaggle_terms_accepted:
        missing.append("kaggle_terms_accepted")
    if not isinstance(owner_team_name, str) or not owner_team_name.strip():
        missing.append("owner_team_name")
    if not owner_go:
        missing.append("owner_submission_authorized")

    decision = QUALIFY_HOLD if missing else "INTERNAL_READY_NOT_SUBMITTED"
    packet = {
        "schema": SCHEMA,
        "decision": decision,
        "missing": missing,
        "facts": facts,
        "authority": {
            "kaggle_join": False,
            "kaggle_submit": False,
            "organizer_contact": False,
            "prize_claim": False,
            "cash": False,
            "revenue": False,
        },
        "evaluated_at_utc": _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    raw = json.dumps(packet, sort_keys=True, separators=(",", ":")).encode("utf-8")
    packet["packet_sha256"] = hashlib.sha256(raw).hexdigest()
    return packet


def parse_spectrum(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("spectrum must be an object")
    missing = [k for k in REQUIRED_SPECTRUM_FIELDS if k not in record]
    if missing:
        raise ValueError("missing spectrum fields: " + ",".join(missing))
    precursor = record["precursor_mz"]
    if not isinstance(precursor, (int, float)) or precursor <= 0:
        raise ValueError("precursor_mz must be a positive number")
    peaks = record["peaks"]
    if not isinstance(peaks, list) or not peaks:
        raise ValueError("peaks must be a nonempty list")
    cleaned = []
    for peak in peaks:
        if not isinstance(peak, (list, tuple)) or len(peak) != 2:
            raise ValueError("each peak must be [mz, intensity]")
        mz, intensity = peak
        if not isinstance(mz, (int, float)) or mz <= 0:
            raise ValueError("peak mz must be a positive number")
        if not isinstance(intensity, (int, float)) or intensity < 0:
            raise ValueError("peak intensity must be a non-negative number")
        cleaned.append([float(mz), float(intensity)])
    return {
        "kind": "DEMO_CAPABILITY",
        "spectrum_id": str(record["spectrum_id"]),
        "precursor_mz": float(precursor),
        "n_peaks": len(cleaned),
        "cannot_satisfy_unknown_mandatory": True,
        "not_a_submission": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualify", action="store_true")
    parser.add_argument("--demo-spectrum", metavar="JSON")
    args = parser.parse_args(argv)
    if args.qualify:
        json.dump(qualify(), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    if args.demo_spectrum:
        record = json.loads(args.demo_spectrum)
        json.dump(parse_spectrum(record), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
