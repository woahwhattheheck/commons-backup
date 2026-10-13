from __future__ import annotations

import argparse
from pathlib import Path

from .fixture import build_synthetic_case
from .gate import build_gate_artifacts, verify_gate_artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the deterministic Peapod compound-transfer provenance acceptance fixture."
    )
    parser.add_argument("--out", type=Path, required=True, help="Output directory")
    args = parser.parse_args(argv)

    transfers, context, _ = build_synthetic_case()
    artifacts = build_gate_artifacts(transfers, context)
    args.out.mkdir(parents=True, exist_ok=True)

    json_path = args.out / "provenance-manifest.json"
    csv_path = args.out / "provenance-manifest.csv"
    sha_path = args.out / "SHA256SUMS"
    json_path.write_bytes(artifacts.json_bytes)
    csv_path.write_bytes(artifacts.csv_bytes)
    sha_path.write_text(
        f"{artifacts.manifest_sha256}  {json_path.name}\n"
        f"{artifacts.csv_sha256}  {csv_path.name}\n",
        encoding="utf-8",
        newline="\n",
    )

    valid = verify_gate_artifacts(
        artifacts.json_bytes,
        artifacts.csv_bytes,
        manifest_sha256=artifacts.manifest_sha256,
        csv_sha256=artifacts.csv_sha256,
    )
    print(
        f"VALID={str(valid).lower()} "
        f"transfers={artifacts.manifest['summary']['transfer_count']} "
        f"ready={artifacts.ready_count} hold={artifacts.hold_count} "
        f"manifest_sha256={artifacts.manifest_sha256}"
    )
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
