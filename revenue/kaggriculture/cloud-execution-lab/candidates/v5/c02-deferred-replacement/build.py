# SPDX-License-Identifier: Apache-2.0
"""Build C02 by suppressing delivery-carrot replacement buys in production20f."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
SELECTIVE_CARROT = HERE.parent / "selective-carrot"
if str(SELECTIVE_CARROT) not in sys.path:
    sys.path.insert(0, str(SELECTIVE_CARROT))

from build_delivery import archive_bytes, digest, members
from publication_custody import publish_exclusive


BASELINE_SHA256 = "20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239"
DELIVERY_CHOICE_SHA256 = "4d3f9729d7fa52a9c221e9d9ffcc434dee55a7dcd22d92f15ad4728103e6c924"
TARGET = "delivery_choice.py"
PURCHASE_ANCHOR = b"        quantity = min(due, room)\n"
TREATMENT = b"        quantity = 0\n"


def compose(
    baseline: dict[str, bytes],
    *,
    expected_delivery_sha256: str = DELIVERY_CHOICE_SHA256,
) -> tuple[dict[str, bytes], bytes, bytes]:
    """Return the one-member C02 postimage over an authenticated baseline."""
    if TARGET not in baseline:
        raise ValueError(f"baseline is missing {TARGET}")
    before = baseline[TARGET]
    if digest(before) != expected_delivery_sha256:
        raise ValueError("production20f delivery_choice.py identity drift")
    if before.count(PURCHASE_ANCHOR) != 1:
        raise ValueError("expected exactly one replacement-purchase seam")
    if TREATMENT in before:
        raise ValueError("C02 treatment is already present")

    after = before.replace(PURCHASE_ANCHOR, TREATMENT, 1)
    files = dict(baseline)
    files[TARGET] = after
    if set(files) != set(baseline):
        raise ValueError("C02 changed the archive member set")
    for name, body in baseline.items():
        if name != TARGET and files[name] != body:
            raise ValueError(f"C02 changed unrelated member {name}")
    return files, before, after


def build(baseline_archive: Path):
    baseline = members(baseline_archive, BASELINE_SHA256)
    if len(baseline) != 92:
        raise ValueError(f"expected 92 production20f members, found {len(baseline)}")
    if digest(archive_bytes(baseline)) != BASELINE_SHA256:
        raise ValueError("production20f deterministic archive identity drift")
    files, before, after = compose(baseline)
    packed = archive_bytes(files)
    return files, before, after, packed


def publish_pair(tar_path: Path, receipt_path: Path, packed: bytes, receipt: dict):
    receipt_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    publish_exclusive([(tar_path, packed), (receipt_path, receipt_bytes)])
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--tar", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        files, before, after, packed = build(args.baseline)
        receipt = {
            "schema": "titan-v5-c02-deferred-replacement/v1",
            "baseline_archive_sha256": BASELINE_SHA256,
            "candidate_archive_sha256": digest(packed),
            "members": len(files),
            "changed_members": [TARGET],
            "delivery_choice_before_sha256": digest(before),
            "delivery_choice_after_sha256": digest(after),
            "treatment": "suppress delivery-carrot automatic replacement-wheat purchases",
            "canonical_default_unchanged": True,
            "kaggle_submission_hold": True,
            "files": {name: digest(body) for name, body in sorted(files.items())},
        }
        publish_pair(args.tar, args.receipt, packed, receipt)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))

    print(json.dumps({
        "candidate_archive_sha256": receipt["candidate_archive_sha256"],
        "delivery_choice_after_sha256": receipt["delivery_choice_after_sha256"],
        "members": receipt["members"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
