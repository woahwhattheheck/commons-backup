#!/usr/bin/env python3
"""Fail-closed Shipaton readiness compiler.

This source carrier intentionally has NO path to competition READY. Caller-authored
files can preserve and validate claimed observations, but cannot authenticate
RevenueCat, store publication, demo media, or Devpost state. A future host adapter
must reacquire those facts from authenticated provider surfaces and own the READY
decision outside this source-controlled compiler.
"""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

EXTERNAL_FIELDS = (
    "revenuecat_account_verified",
    "revenuecat_product_offering_verified",
    "store_developer_account_verified",
    "store_publication_verified",
    "public_store_url",
    "demo_video_url",
    "screenshot_evidence",
    "devpost_submission_verified",
)


def parse_utc(s: str) -> datetime:
    value = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("timestamp missing timezone")
    return value.astimezone(timezone.utc)


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def compile_readiness(manifest: dict, witness: dict | None) -> dict:
    """Compile source-local readiness facts without granting external authority.

    `witness` is deliberately treated as SELF_ASSERTED evidence history. Even a
    fully populated, internally consistent witness remains HOLD because the caller
    controls the file and every field inside it.
    """
    reasons: list[str] = []
    if manifest.get("submission_ready") is True:
        reasons.append("manifest may not self-assert submission_ready")

    app = manifest.get("app", {})
    if app.get("platform") != "android":
        reasons.append("carrier is not Android")
    if not app.get("first_public_release_required"):
        reasons.append("new-first-release requirement not bound")

    source = manifest.get("source", {})
    if source.get("status") != "implemented":
        reasons.append("source not implemented")
    if source.get("entitlement") != "pro":
        reasons.append("RevenueCat entitlement mismatch")

    try:
        deadline = parse_utc(manifest["deadline_utc"])
    except Exception:
        reasons.append("invalid deadline")
        deadline = datetime.min.replace(tzinfo=timezone.utc)

    witness_digest = None
    witness_findings: list[str] = []
    if witness is None:
        witness_findings.append("no self-asserted witness supplied")
    else:
        witness_digest = canonical_sha256(witness)
        if witness.get("authority") not in {"external-provider-observation", "self-asserted-observation"}:
            witness_findings.append("witness authority label is unrecognized")
        if witness.get("package") != app.get("package"):
            witness_findings.append("witness package identity drift")
        if witness.get("version_code") != app.get("version_code"):
            witness_findings.append("witness version identity drift")
        try:
            observed_at = parse_utc(witness["observed_at_utc"])
            if observed_at > deadline:
                witness_findings.append("witness observation is after competition deadline")
        except Exception:
            witness_findings.append("invalid witness timestamp")
        for key in EXTERNAL_FIELDS:
            value = witness.get(key)
            if key.endswith("_url"):
                if not isinstance(value, str) or not value.startswith("https://"):
                    witness_findings.append(f"missing/invalid claimed {key}")
            elif key == "screenshot_evidence":
                if not isinstance(value, str) or not value.strip():
                    witness_findings.append("missing claimed screenshot_evidence")
            elif value is not True:
                witness_findings.append(f"claimed external gate not true: {key}")

    reasons.append(
        "authenticated provider/store/submission authority absent; "
        "caller-authored witness is SELF_ASSERTED and cannot mint READY"
    )
    reasons.extend(witness_findings)

    identity = {"app": app, "source": source}
    return {
        "status": "HOLD_EXTERNAL_AUTHORITY",
        "ready_authorized": False,
        "identity_sha256": canonical_sha256(identity),
        "self_asserted_witness_sha256": witness_digest,
        "reasons": reasons,
        "required_authenticated_authorities": [
            "RevenueCat account + exact app/product/offering/entitlement readback",
            "eligible store developer authority + exact public package/version readback",
            "demo/screenshot evidence bound by authenticated retained digests",
            "Devpost submission identity + timestamp readback",
            "host-owned current-time/deadline evaluation",
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("manifest", type=Path)
    p.add_argument(
        "--witness",
        type=Path,
        help="optional caller-authored observation file; integrity/history only, never READY authority",
    )
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    manifest = json.loads(args.manifest.read_text())
    witness = json.loads(args.witness.read_text()) if args.witness else None
    result = compile_readiness(manifest, witness)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['status']} {result['identity_sha256']}")
        print("\n".join(f"- {x}" for x in result["reasons"]))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
