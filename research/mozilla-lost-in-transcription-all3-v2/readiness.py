from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from core import TRACKS, canonical_json
from pack import PROOF_TYPE, VerificationError, verify_bundle


def _load_exact_proof(path: Path) -> dict:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"invalid verification proof {path}: {exc}") from exc
    if not isinstance(obj, dict):
        raise VerificationError("verification proof must be an object")
    proof_sha = obj.get("proof_sha256")
    payload = {k: v for k, v in obj.items() if k != "proof_sha256"}
    expected = sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    if proof_sha != expected:
        raise VerificationError("verification proof self-digest mismatch")
    if obj.get("proof_type") != PROOF_TYPE or obj.get("schema_version") != 2 or obj.get("accepted") is not True:
        raise VerificationError("unsupported or unaccepted verification proof")
    return obj


def aggregate(entries: list[tuple[Path, Path, Path]], output: Path) -> dict:
    """Re-verify three bundle/build-receipt/proof triples, then aggregate.

    A proof file alone is never authority: each proof is compared byte-semantically with
    a fresh derivation from the exact bundle and build receipt supplied to this call.
    """
    reasons: list[str] = []
    derived_rows: list[dict] = []
    if len(entries) != 3:
        reasons.append("exactly three verified bundle triples required")
    else:
        for index, (bundle, build_receipt, proof_path) in enumerate(entries):
            try:
                stored = _load_exact_proof(proof_path)
                derived = verify_bundle(bundle, build_receipt)
                if stored != derived:
                    raise VerificationError("stored proof does not equal fresh bundle derivation")
                derived_rows.append(derived)
            except (VerificationError, OSError, ValueError) as exc:
                reasons.append(f"entry {index}: {exc}")

    if len(derived_rows) == 3:
        tracks = [r.get("track") for r in derived_rows]
        if set(tracks) != TRACKS or len(set(tracks)) != 3:
            reasons.append("verified proofs must cover each track exactly once")
        commits = {r.get("runtime_commit") for r in derived_rows}
        if len(commits) != 1 or None in commits:
            reasons.append("verified runtime commit mismatch")
        runtime_contracts = {r.get("runtime_contract_sha256") for r in derived_rows}
        if len(runtime_contracts) != 1 or None in runtime_contracts:
            reasons.append("verified runtime contract mismatch")
        if any(r.get("internet_at_execution") is not False for r in derived_rows):
            reasons.append("offline runtime contract not proven")

    state = "ALL_THREE_LOCAL_BUNDLES_STRUCTURALLY_READY" if not reasons and len(derived_rows) == 3 else "HOLD"
    canonical = [
        {
            "track": r.get("track"),
            "bundle_sha256": r.get("bundle_sha256"),
            "build_receipt_sha256": r.get("build_receipt_sha256"),
            "proof_sha256": r.get("proof_sha256"),
            "runtime_commit": r.get("runtime_commit"),
            "runtime_contract_sha256": r.get("runtime_contract_sha256"),
        }
        for r in sorted(derived_rows, key=lambda x: str(x.get("track")))
    ]
    result = {
        "schema_version": 2,
        "state": state,
        "provider_submission": False,
        "competition_terms_accepted": False,
        "score_claimed": False,
        "prize_claimed": False,
        "model_execution_proven": False,
        "reasons": reasons,
        "verified_bundles": canonical,
    }
    result["receipt_sha256"] = sha256(canonical_json(result).encode("utf-8")).hexdigest()
    output.write_text(canonical_json(result), encoding="utf-8")
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", nargs=3, action="append", metavar=("BUNDLE", "BUILD_RECEIPT", "PROOF"), required=True)
    ap.add_argument("--output", required=True, type=Path)
    a = ap.parse_args()
    entries = [(Path(x), Path(y), Path(z)) for x, y, z in a.entry]
    aggregate(entries, a.output)


if __name__ == "__main__":
    main()
