# SPDX-License-Identifier: Apache-2.0
"""Build a hash-gated E11 semantic-safety candidate from canonical 3b4b.

The source archive is never modified.  The builder extracts into a new directory,
adds the safe E11 module, and inserts the hook *before* seller pending-accounting
in both supported seller implementations.  It intentionally does not wire O01,
E20, or SHOP into production; those require their capital/route/scoring owners.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import inspect
from pathlib import Path
import py_compile
import shutil
import tarfile
from typing import Iterable

EXPECTED_ARCHIVE_SHA256 = "3b4b083ec2647bb0e715978c2565e916da0ee94c08b234902e3a7e4d3418c320"
MARKER = "# ARGUS_G01_E11_SEMANTIC_SAFETY"

SCHEDULER_ANCHOR = """        out['market']=market
        for item,q in targets.items():
"""
SCHEDULER_REPLACEMENT = """        out['market']=market
""" + MARKER + """
        out = self._argus_e11_before_pending(obs, config, out, now)
        for item,q in targets.items():
"""

FROZEN_ANCHOR = """        if funding is not None:self.diagnostics['same_turn_funding']=funding
        for item,q in targets.items():
"""
FROZEN_REPLACEMENT = """        if funding is not None:self.diagnostics['same_turn_funding']=funding
""" + MARKER + """
        out = self._argus_e11_before_pending(obs, config, out, now)
        for item,q in targets.items():
"""

# Inserted immediately before each seller class's act/transform method.  It owns
# only public price history and preserves the caller's queue indexes.
METHOD = r'''
    def _argus_e11_before_pending(self, obs, config, out, now):
        try:
            from e11_rival_sell import apply_e11, enabled as _argus_e11_enabled
            if not _argus_e11_enabled():
                return out
            history = list(getattr(self, '_argus_price_history', []))
            out, report = apply_e11(obs, out, history, config, absorption)
            self.diagnostics['argus_e11'] = report
            prices = dict((obs.get('market') or {}).get('prices') or {})
            history.append((int(now), prices))
            lookback = max(0, int(config.get('rival_dump_lookback_steps', 8)))
            self._argus_price_history = [
                entry for entry in history
                if 0 <= int(now) - int(entry[0]) <= lookback
            ]
            return out
        except Exception as error:
            self.diagnostics['argus_e11'] = {
                'enabled': True,
                'changed': False,
                'reason': 'ARGUS_E11_ERROR_' + type(error).__name__,
            }
            return out

'''


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_members(archive: tarfile.TarFile, destination: Path) -> Iterable[tarfile.TarInfo]:
    root = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if target != root and root not in target.parents:
            raise ValueError(f"unsafe archive member: {member.name}")
        if member.issym() or member.islnk():
            raise ValueError(f"links are not accepted in candidate archive: {member.name}")
        yield member


def _unique(root: Path, filename: str) -> Path:
    matches = [path for path in root.rglob(filename) if path.is_file()]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {filename}; found {len(matches)}")
    return matches[0]


def _insert_method_once(source: str, method_anchor: str) -> str:
    if "def _argus_e11_before_pending" in source:
        raise ValueError("ARGUS method already present")
    count = source.count(method_anchor)
    if count != 1:
        raise ValueError(f"method anchor count {count}, expected 1")
    return source.replace(method_anchor, METHOD + method_anchor, 1)


def _patch_file(path: Path, anchor: str, replacement: str, method_anchor: str) -> None:
    source = path.read_text(encoding="utf-8")
    if MARKER in source:
        raise ValueError(f"{path.name} already contains ARGUS marker")
    if source.count(anchor) != 1:
        raise ValueError(f"{path.name}: pending anchor count {source.count(anchor)}, expected 1")
    source = _insert_method_once(source, method_anchor)
    source = source.replace(anchor, replacement, 1)
    path.write_text(source, encoding="utf-8", newline="\n")


def build(
    archive_path: Path,
    output_dir: Path,
    *,
    expected_sha256: str | None = EXPECTED_ARCHIVE_SHA256,
    module_dir: Path | None = None,
) -> dict:
    archive_path = archive_path.resolve()
    output_dir = output_dir.resolve()
    module_dir = (module_dir or Path(__file__).resolve().parent).resolve()
    observed = sha256_file(archive_path)
    if expected_sha256 is not None and observed != expected_sha256:
        raise ValueError(f"archive SHA256 mismatch: expected {expected_sha256}, observed {observed}")
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite output: {output_dir}")
    output_dir.mkdir(parents=True)

    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            kwargs = {"filter": "data"} if "filter" in inspect.signature(archive.extractall).parameters else {}
            archive.extractall(output_dir, members=_safe_members(archive, output_dir), **kwargs)

        scheduler = _unique(output_dir, "scheduler.py")
        frozen = _unique(output_dir, "frozen_selected.py")
        _patch_file(scheduler, SCHEDULER_ANCHOR, SCHEDULER_REPLACEMENT, "    def act(self, obs, configuration=None):\n")
        _patch_file(frozen, FROZEN_ANCHOR, FROZEN_REPLACEMENT, "    def transform(self, obs, config, base):\n")

        copied = []
        for filename in ("e11_rival_sell.py", "rival_model.py", "e20_hire_guard.py", "shop_arb.py"):
            source = module_dir / filename
            if not source.is_file():
                raise FileNotFoundError(source)
            target = scheduler.parent / filename
            shutil.copyfile(source, target)
            copied.append(target)

        compiled = [scheduler, frozen, *copied]
        for path in compiled:
            py_compile.compile(str(path), doraise=True)

        manifest = {
            "operation": "titan-v3-g01-semantic-safety-20260909-sol-argus-01",
            "source_archive_sha256": observed,
            "production_enabled": ["E11 public-price-drop deferral at seller-owned pre-pending seam"],
            "production_quarantined": [
                "O01 BUY_LAND until capital/route owner composition",
                "E20 HIRE suppression until capital/route owner composition",
                "SHOP priority until a scoring-only seam exists",
            ],
            "patched_files": [str(scheduler.relative_to(output_dir)), str(frozen.relative_to(output_dir))],
            "copied_modules": [str(path.relative_to(output_dir)) for path in copied],
            "sha256": {
                str(path.relative_to(output_dir)): sha256_file(path)
                for path in sorted(compiled)
            },
        }
        manifest_path = scheduler.parent / "ARGUS-G01-BUILD.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return manifest
    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    manifest = build(args.archive, args.output)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
