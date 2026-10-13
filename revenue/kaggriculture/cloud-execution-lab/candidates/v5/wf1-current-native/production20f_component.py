# SPDX-License-Identifier: Apache-2.0
"""Build a held WF1 component for the exact production20f archive.

This is an experiment carrier. It authenticates the current V5 archive and the
retained WF1 donor sources, patches the public ``main.py`` return seam after the
parent has committed its action, and emits one staging-composer component. It
does not alter a default, release pointer, or Kaggle submission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
SOURCE_ROOT = HERE.parents[2]
SELECTIVE_CARROT = HERE.parent / "selective-carrot"
if str(SELECTIVE_CARROT) not in sys.path:
    sys.path.insert(0, str(SELECTIVE_CARROT))

import staging_composer
from publication_custody import publish_exclusive


BASELINE_ARCHIVE_SHA256 = staging_composer.BASELINE_SHA256
MAIN_MEMBER = "main.py"
MAIN_PREIMAGE_SHA256 = "b98aec64f83ea9a216def7ab1fef320a6498ae37816f506af1f891c934027035"
COMPONENT_ID = "wf1-production20f-v1"
DONOR_ROOT = SOURCE_ROOT / "candidates/v4/repairs/gameplay/wf1-wheat-fertilize"
DONOR_PINS = {
    "r04_wheat_fert.py": "b35a30431f64c1d6b40d1d599190338a9d50b555",
    "wf1_current_adapter.py": "5b8f4c0144ce43ae449373a6a188ce03409a16ee",
}

_RETURN_SEAM = (
    b"    if _CHOICE is not None:\n"
    b"        _CHOICE.commit(observation, returned)\n"
    b"    return returned\n"
)
_WF1_RETURN_SEAM = (
    b"    if _CHOICE is not None:\n"
    b"        _CHOICE.commit(observation, returned)\n"
    b"    from wf1_current_adapter import apply_wf1_current\n"
    b"    return apply_wf1_current(\n"
    b"        observation, returned, configuration, enabled=True)\n"
)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def git_blob_sha(payload: bytes) -> str:
    header = b"blob " + str(len(payload)).encode("ascii") + b"\0"
    return hashlib.sha1(header + payload).hexdigest()


def source_name(member: str) -> str:
    return "files/" + hashlib.sha256(member.encode("utf-8")).hexdigest() + ".bin"


def transform_main(source: bytes) -> bytes:
    """Insert WF1 after the exact parent-return seam, rejecting source drift."""
    if source.count(_RETURN_SEAM) != 1:
        raise ValueError("production20f main.py return seam must occur exactly once")
    return source.replace(_RETURN_SEAM, _WF1_RETURN_SEAM, 1)


def _donor_payloads(
    donor_root: Path = DONOR_ROOT,
    donor_pins: dict[str, str] = DONOR_PINS,
) -> dict[str, bytes]:
    payloads: dict[str, bytes] = {}
    for member, expected in donor_pins.items():
        path = Path(donor_root) / member
        working_body = path.read_bytes()
        observed = git_blob_sha(working_body)
        body = working_body
        # ``core.autocrlf=true`` expands the checked-out source on Windows.
        # The pins identify Git's canonical LF blob, which is also the byte form
        # required in the cross-platform component payload.
        if observed != expected:
            body = working_body.replace(b"\r\n", b"\n")
            observed = git_blob_sha(body)
        if observed != expected:
            raise ValueError(f"{member} donor blob mismatch: {observed} != {expected}")
        payloads[member] = body
    return payloads


def build_component(
    archive_raw: bytes,
    *,
    expected_archive_sha256: str = BASELINE_ARCHIVE_SHA256,
    expected_main_sha256: str = MAIN_PREIMAGE_SHA256,
    donor_root: Path = DONOR_ROOT,
    donor_pins: dict[str, str] = DONOR_PINS,
) -> tuple[dict, dict[str, bytes]]:
    """Return a canonical component manifest and its source payload mapping.

    Hash overrides exist for synthetic unit fixtures. The command-line path
    exposes no overrides and always binds exact production20f plus pinned donors.
    """
    archive_sha = digest(archive_raw)
    if archive_sha != expected_archive_sha256:
        raise ValueError(
            f"production20f archive SHA256 mismatch: {archive_sha} != "
            f"{expected_archive_sha256}"
        )
    members = staging_composer.archive_members(archive_raw)
    if MAIN_MEMBER not in members:
        raise ValueError("production20f archive is missing main.py")
    for addition in donor_pins:
        if addition in members:
            raise ValueError(f"WF1 addition already exists in baseline: {addition}")

    main_raw = members[MAIN_MEMBER]
    main_sha = digest(main_raw)
    if main_sha != expected_main_sha256:
        raise ValueError(
            f"production20f main.py SHA256 mismatch: {main_sha} != "
            f"{expected_main_sha256}"
        )

    donor_payloads = _donor_payloads(donor_root, donor_pins)
    patched_main = transform_main(main_raw)
    payloads = {MAIN_MEMBER: patched_main, **donor_payloads}

    replacements = {
        MAIN_MEMBER: {
            "source": source_name(MAIN_MEMBER),
            "preimage_sha256": expected_main_sha256,
            "postimage_sha256": digest(patched_main),
        }
    }
    additions = {
        member: {
            "source": source_name(member),
            "postimage_sha256": digest(body),
        }
        for member, body in sorted(donor_payloads.items())
    }
    manifest = {
        "schema": staging_composer.COMPONENT_SCHEMA,
        "component_id": COMPONENT_ID,
        "baseline_archive_sha256": expected_archive_sha256,
        "depends_on": [],
        "conflicts_with": [],
        "overlap_after": {},
        "replacements": replacements,
        "additions": additions,
        "kaggle_submission_hold": True,
    }
    sources = {source_name(member): body for member, body in payloads.items()}
    return manifest, sources


def manifest_bytes(manifest: dict) -> bytes:
    return (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def _preflight(manifest: dict, sources: dict[str, bytes]) -> None:
    """Require the canonical composer to accept the exact generated bytes."""
    with tempfile.TemporaryDirectory(prefix="titan-v5-wf1-component-") as td:
        root = Path(td)
        (root / "COMPONENT.json").write_bytes(manifest_bytes(manifest))
        for source, body in sources.items():
            path = root.joinpath(*source.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        staging_composer.load_component(root / "COMPONENT.json")


def materialize(archive_path: Path, output_dir: Path) -> dict:
    archive_raw = staging_composer.read_regular(archive_path)
    manifest, sources = build_component(archive_raw)
    _preflight(manifest, sources)
    files = [(Path(output_dir) / "COMPONENT.json", manifest_bytes(manifest))]
    files.extend(
        (Path(output_dir).joinpath(*source.split("/")), body)
        for source, body in sorted(sources.items())
    )
    publish_exclusive(files)
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest = materialize(args.baseline, args.out_dir)
    print(json.dumps(manifest, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
