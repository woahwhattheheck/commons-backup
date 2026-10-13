# SPDX-License-Identifier: Apache-2.0
"""Materialize P02 over the exact production-v3 archive."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
SELECTIVE_CARROT = HERE.parent / "selective-carrot"
if str(SELECTIVE_CARROT) not in sys.path:
    sys.path.insert(0, str(SELECTIVE_CARROT))

from build_delivery import archive_bytes, digest, members
from publication_custody import publish_exclusive

BASELINE_SHA = "20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239"
MAIN_SHA256 = "b98aec64f83ea9a216def7ab1fef320a6498ae37816f506af1f891c934027035"
HELPER_GIT_BLOB = "d13d255d1e24695b758791233b34445ad828dd29"
MAIN = "main.py"
HELPER = "goose_capacity_economy.py"


def _git_blob(raw: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def compose(
    baseline,
    helper,
    *,
    expected_main_sha=MAIN_SHA256,
    expected_helper_blob=HELPER_GIT_BLOB,
):
    """Patch only the exact public production-v3 return seam and add P02."""
    if MAIN not in baseline:
        raise ValueError("production-v3 main.py missing")
    if HELPER in baseline:
        raise ValueError("P02 helper already exists in baseline")
    parent = baseline[MAIN]
    if digest(parent) != expected_main_sha:
        raise ValueError("production-v3 main.py identity drift")
    if _git_blob(helper) != expected_helper_blob:
        raise ValueError("P02 helper identity drift")

    import_anchor = b"import baseline_main as baseline\n"
    return_anchor = b"    return returned\n"
    if parent.count(import_anchor) != 1:
        raise ValueError("expected one production-v3 baseline import seam")
    if parent.count(return_anchor) != 1:
        raise ValueError("expected one production-v3 public return seam")

    patched = parent.replace(
        import_anchor,
        import_anchor + b"import goose_capacity_economy as p02\n",
        1,
    )
    patched = patched.replace(
        return_anchor,
        b"    return p02.apply_goose_capacity_economy(\n"
        b"        returned, observation, configuration, enabled=True\n"
        b"    )\n",
        1,
    )

    files = dict(baseline)
    files[MAIN] = patched
    files[HELPER] = helper
    if files.get("baseline_main.py") != baseline.get("baseline_main.py"):
        raise ValueError("embedded baseline_main.py changed")
    return files, parent, patched


def build(baseline_archive: Path):
    baseline = members(baseline_archive, BASELINE_SHA)
    if digest(archive_bytes(baseline)) != BASELINE_SHA:
        raise ValueError("production-v3 deterministic archive identity drift")
    helper = (HERE / HELPER).read_bytes()
    return compose(baseline, helper)


def publish_pair(tar_path, receipt_path, packed, receipt):
    """Publish P02 archive+receipt through the canonical shared custody helper."""
    receipt_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    publish_exclusive([
        (Path(tar_path), packed),
        (Path(receipt_path), receipt_bytes),
    ])
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--tar", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        files, before, after = build(args.baseline)
        packed = archive_bytes(files)
        receipt = {
            "schema": "titan-v5-p02-goose-capacity-economy/v2",
            "baseline_candidate_archive_sha256": BASELINE_SHA,
            "candidate_archive_sha256": digest(packed),
            "members": len(files),
            "changed_members": [MAIN],
            "new_members": [HELPER],
            "main_before_sha256": digest(before),
            "main_after_sha256": digest(after),
            "helper_git_blob": _git_blob(files[HELPER]),
            "candidate_treatment_enabled": True,
            "canonical_default_unchanged": True,
            "kaggle_submission_hold": True,
            "files": {name: digest(body) for name, body in sorted(files.items())},
        }
        publish_pair(args.tar, args.receipt, packed, receipt)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))

    print(json.dumps({
        "candidate_archive_sha256": receipt["candidate_archive_sha256"],
        "members": receipt["members"],
        "changed_members": receipt["changed_members"],
        "new_members": receipt["new_members"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())