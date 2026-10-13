"""Reconstruct the exact T04 raw experiment evidence without network or execution."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
from pathlib import Path, PurePosixPath
import tarfile

HERE = Path(__file__).resolve().parent
ARCHIVE_BYTES = 22860
ARCHIVE_SHA256 = "7035aca6ff94349c98168b0db69d059461c1ac2fa335550748f73e7625fd8f25"


def unpack(destination: Path) -> list[str]:
    """Verify all four parts and extract regular relative files to a new directory."""
    encoded = "".join((HERE / "results" / f"evidence-{i:02d}.b64").read_text().strip()
                      for i in range(4))
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) != ARCHIVE_BYTES or hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("T04 evidence archive size or SHA-256 mismatch")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:xz") as archive:
        members = archive.getmembers()
        names = [m.name for m in members]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate archive member")
        for member in members:
            path = PurePosixPath(member.name)
            if not member.isfile() or path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Unexpected archive member: {member.name}")
        destination.mkdir(parents=True, exist_ok=False)
        for member in members:
            target = destination / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"Missing regular-file data: {member.name}")
            with target.open("xb") as output:
                output.write(stream.read())
    return names


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "evidence",
                        help="New output directory; existing paths are never overwritten")
    args = parser.parse_args()
    try:
        names = unpack(args.output)
    except (OSError, ValueError, tarfile.TarError) as exc:
        parser.exit(1, f"Evidence extraction failed: {exc}\n")
    print(f"SHA256 {ARCHIVE_SHA256}; {len(names)} files in {args.output}")


if __name__ == "__main__":
    main()
