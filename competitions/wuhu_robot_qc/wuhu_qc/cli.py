from __future__ import annotations

import argparse
import json
from pathlib import Path

from .lerobot_v21 import fit_dataset_reference, scan_dataset
from .provenance import (
    CLEAN_REFERENCE_ROLE,
    TEST_ROLE,
    UNSCOPED_ROLE,
    BoundReferenceProfile,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="LeRobot v2.1 trajectory quality detector for the Wuhu embodied-data challenge"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    profile = sub.add_parser("profile")
    profile.add_argument("dataset", type=Path)
    profile.add_argument("--out", type=Path, default=Path("reference.json"))
    profile.add_argument("--episodes", type=int, nargs="*")
    profile.add_argument(
        "--source-role",
        choices=[CLEAN_REFERENCE_ROLE],
        required=True,
        help="explicit organizer clean-reference role; any other role is rejected",
    )

    scan = sub.add_parser("scan")
    scan.add_argument("dataset", type=Path)
    scan.add_argument("--out", type=Path, default=Path("wuhu-qc-report"))
    scan.add_argument("--episodes", type=int, nargs="*")
    scan.add_argument("--reference", type=Path)
    scan.add_argument(
        "--dataset-role",
        choices=[TEST_ROLE, UNSCOPED_ROLE],
        default=UNSCOPED_ROLE,
        help="ORGANIZER_TEST is mandatory when a bound reference is supplied",
    )

    args = parser.parse_args(argv)
    if args.cmd == "profile":
        ref = fit_dataset_reference(
            args.dataset,
            episodes=args.episodes,
            role=args.source_role,
        )
        args.out.write_text(json.dumps(ref.as_dict(), indent=2) + "\n", encoding="utf-8")
        print(
            f"reference_features={len(ref.feature_keys)} "
            f"selected_episodes={len(ref.provenance.selected_episode_indices)} "
            f"corpus_sha256={ref.provenance.corpus_sha256} output={args.out}"
        )
        return 0

    ref = None
    if args.reference:
        ref = BoundReferenceProfile.from_dict(
            json.loads(args.reference.read_text(encoding="utf-8"))
        )
    reports = scan_dataset(
        args.dataset,
        args.out,
        episodes=args.episodes,
        reference=ref,
        dataset_role=args.dataset_role,
    )
    holds = sum(r.quality_score < 70 for r in reports)
    print(f"episodes={len(reports)} quality_lt_70={holds} report={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
