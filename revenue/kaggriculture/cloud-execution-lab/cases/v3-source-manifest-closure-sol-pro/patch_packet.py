# SPDX-License-Identifier: Apache-2.0
"""Apply the bounded SOURCE.json-closure repair to the authenticated V3 packet."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil

EXPECTED_BUILD_SHA256 = "cfcb383e6cba811e17d687cb080fea1f55723c8aa734edbe9c37ec3743f923d0"
EXPECTED_HELPER_SHA256 = "5885e872ffaa3889163df1ee9694a5f4656081420be471c8176ebed5793e99e9"
HELPER_NAME = "source_manifest_closure.py"

IMPORT_OLD = "import apply_v3  # noqa: E402\n"
IMPORT_NEW = (
    "import apply_v3  # noqa: E402\n"
    "import source_manifest_closure  # noqa: E402\n"
)
RETURN_OLD = (
    "        for path in sorted(p for p in work.rglob(\"*\") if p.is_file()):\n"
    "            files[path.relative_to(work).as_posix()] = path.read_bytes()\n"
    "        return files\n"
)
RETURN_NEW = (
    "        for path in sorted(p for p in work.rglob(\"*\") if p.is_file()):\n"
    "            files[path.relative_to(work).as_posix()] = path.read_bytes()\n"
    "        files[\"SOURCE.json\"] = source_manifest_closure.refresh_source_manifest(files)\n"
    "        source_manifest_closure.verify_source_manifest(files)\n"
    "        return files\n"
)
SOURCE_SHAS_OLD = (
    "    shas[\"apply_v3.py\"] = hashlib.sha256((HERE / \"apply_v3.py\").read_bytes()).hexdigest()\n"
    "    return shas\n"
)
SOURCE_SHAS_NEW = (
    "    shas[\"apply_v3.py\"] = hashlib.sha256((HERE / \"apply_v3.py\").read_bytes()).hexdigest()\n"
    "    shas[\"build_v3.py\"] = hashlib.sha256((HERE / \"build_v3.py\").read_bytes()).hexdigest()\n"
    "    shas[\"source_manifest_closure.py\"] = hashlib.sha256(\n"
    "        (HERE / \"source_manifest_closure.py\").read_bytes()\n"
    "    ).hexdigest()\n"
    "    return shas\n"
)


class PatchError(RuntimeError):
    pass


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected one preimage, found {count}")
    return text.replace(old, new)


def patch(packet_root: Path, helper_source: Path) -> dict[str, str]:
    root = packet_root.resolve()
    build = root / "build_v3.py"
    if not build.is_file() or build.is_symlink():
        raise PatchError(f"not a regular build_v3.py: {build}")
    actual = sha256_path(build)
    if actual != EXPECTED_BUILD_SHA256:
        raise PatchError(f"build_v3.py drift: expected {EXPECTED_BUILD_SHA256}, got {actual}")
    if not helper_source.is_file() or helper_source.is_symlink():
        raise PatchError(f"not a regular helper source: {helper_source}")
    helper_digest = sha256_path(helper_source)
    if helper_digest != EXPECTED_HELPER_SHA256:
        raise PatchError(
            f"helper drift: expected {EXPECTED_HELPER_SHA256}, got {helper_digest}"
        )
    helper_target = root / HELPER_NAME
    if helper_target.exists():
        raise PatchError(f"refusing to replace existing {helper_target}")

    text = build.read_text(encoding="utf-8")
    text = replace_once(text, IMPORT_OLD, IMPORT_NEW, "helper import")
    text = replace_once(text, RETURN_OLD, RETURN_NEW, "final SOURCE closure")
    text = replace_once(text, SOURCE_SHAS_OLD, SOURCE_SHAS_NEW, "builder source receipt")

    # Stage and verify both byte streams before publishing either one.
    staged_build = root / ".build_v3.py.source-closure.tmp"
    staged_helper = root / ".source_manifest_closure.py.tmp"
    try:
        staged_build.write_text(text, encoding="utf-8", newline="")
        shutil.copyfile(helper_source, staged_helper)
        if sha256_path(build) != EXPECTED_BUILD_SHA256:
            raise PatchError("build_v3.py changed during staging")
        staged_helper.replace(helper_target)
        staged_build.replace(build)
    finally:
        staged_build.unlink(missing_ok=True)
        staged_helper.unlink(missing_ok=True)

    return {
        "preimage_build_sha256": actual,
        "patched_build_sha256": sha256_path(build),
        "helper_sha256": sha256_path(helper_target),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("packet_root", type=Path)
    parser.add_argument(
        "--helper",
        type=Path,
        default=Path(__file__).with_name(HELPER_NAME),
    )
    args = parser.parse_args()
    receipt = patch(args.packet_root, args.helper)
    for key in sorted(receipt):
        print(f"{key}={receipt[key]}")


if __name__ == "__main__":
    main()
