from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .core import ReferenceProfile

CLEAN_REFERENCE_ROLE = "ORGANIZER_CLEAN_REFERENCE"
TEST_ROLE = "ORGANIZER_TEST"
UNSCOPED_ROLE = "UNSCOPED_QC"
BOUND_REFERENCE_VERSION = "wuhu-bound-reference/v2"
MANIFEST_VERSION = "wuhu-corpus-manifest/v1"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _validate_episode_indices(values: Iterable[int]) -> tuple[int, ...]:
    out = tuple(int(v) for v in values)
    if not out:
        raise ValueError("episode selection must not be empty")
    if any(v < 0 for v in out):
        raise ValueError("episode indices must be nonnegative")
    if len(set(out)) != len(out):
        raise ValueError("episode selection contains duplicates")
    return tuple(sorted(out))


@dataclass(frozen=True)
class CorpusManifest:
    version: str
    role: str
    corpus_sha256: str
    selected_sha256: str
    info_sha256: str
    episodes_metadata_sha256: str | None
    declared_episode_count: int
    selected_episode_indices: tuple[int, ...]
    selected_episode_files: tuple[tuple[int, str], ...]
    all_episode_files: tuple[tuple[int, str | None], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "role": self.role,
            "corpus_sha256": self.corpus_sha256,
            "selected_sha256": self.selected_sha256,
            "info_sha256": self.info_sha256,
            "episodes_metadata_sha256": self.episodes_metadata_sha256,
            "declared_episode_count": self.declared_episode_count,
            "selected_episode_indices": list(self.selected_episode_indices),
            "selected_episode_files": [
                {"episode_index": ep, "sha256": digest} for ep, digest in self.selected_episode_files
            ],
            "all_episode_files": [
                {"episode_index": ep, "sha256": digest} for ep, digest in self.all_episode_files
            ],
        }


def build_corpus_manifest(
    root: Path,
    *,
    role: str,
    declared_episode_indices: Sequence[int],
    selected_episode_indices: Sequence[int],
    data_paths: Mapping[int, Path],
) -> CorpusManifest:
    root = root.resolve()
    if role not in {CLEAN_REFERENCE_ROLE, TEST_ROLE, UNSCOPED_ROLE}:
        raise ValueError(f"unsupported dataset role {role!r}")
    declared = _validate_episode_indices(declared_episode_indices)
    selected = _validate_episode_indices(selected_episode_indices)
    if not set(selected).issubset(declared):
        extra = sorted(set(selected) - set(declared))
        raise ValueError(f"selected episodes are not declared by dataset metadata: {extra}")

    info_path = root / "meta" / "info.json"
    if not info_path.is_file():
        raise FileNotFoundError(info_path)
    info_sha = _sha256_file(info_path)
    episodes_path = root / "meta" / "episodes.jsonl"
    episodes_sha = _sha256_file(episodes_path) if episodes_path.is_file() else None

    all_files: list[tuple[int, str | None]] = []
    by_episode: dict[int, str | None] = {}
    for ep in declared:
        path = data_paths[ep]
        digest = _sha256_file(path) if path.is_file() else None
        by_episode[ep] = digest
        all_files.append((ep, digest))

    selected_files: list[tuple[int, str]] = []
    for ep in selected:
        digest = by_episode[ep]
        if digest is None:
            raise FileNotFoundError(data_paths[ep])
        selected_files.append((ep, digest))

    corpus_payload = {
        "version": MANIFEST_VERSION,
        "info_sha256": info_sha,
        "episodes_metadata_sha256": episodes_sha,
        "declared_episode_indices": list(declared),
        "episode_files": [{"episode_index": ep, "sha256": digest} for ep, digest in all_files],
    }
    selected_payload = {
        "version": MANIFEST_VERSION,
        "role": role,
        "corpus_sha256": _canonical_digest(corpus_payload),
        "selected_episode_files": [
            {"episode_index": ep, "sha256": digest} for ep, digest in selected_files
        ],
    }
    return CorpusManifest(
        MANIFEST_VERSION,
        role,
        _canonical_digest(corpus_payload),
        _canonical_digest(selected_payload),
        info_sha,
        episodes_sha,
        len(declared),
        selected,
        tuple(selected_files),
        tuple(all_files),
    )


@dataclass(frozen=True)
class BoundReferenceProfile:
    version: str
    provenance: CorpusManifest
    feature_keys: tuple[str, ...]
    profile: ReferenceProfile

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "provenance": self.provenance.as_dict(),
            "feature_keys": list(self.feature_keys),
            "profile": self.profile.as_dict(),
        }

    @staticmethod
    def from_dict(value: Mapping[str, Any]) -> "BoundReferenceProfile":
        if value.get("version") != BOUND_REFERENCE_VERSION:
            raise ValueError("reference profile is not provenance-bound v2")
        p = value.get("provenance")
        if not isinstance(p, Mapping):
            raise ValueError("reference profile lacks provenance")
        if p.get("version") != MANIFEST_VERSION or p.get("role") != CLEAN_REFERENCE_ROLE:
            raise ValueError("reference provenance must be organizer clean-reference v1")
        for key in ("corpus_sha256", "selected_sha256", "info_sha256"):
            if not isinstance(p.get(key), str) or not _HEX64.fullmatch(str(p[key])):
                raise ValueError(f"invalid provenance digest {key}")
        episodes_meta = p.get("episodes_metadata_sha256")
        if episodes_meta is not None and (not isinstance(episodes_meta, str) or not _HEX64.fullmatch(episodes_meta)):
            raise ValueError("invalid episodes metadata digest")

        selected_indices = _validate_episode_indices(p.get("selected_episode_indices", []))
        selected_rows = p.get("selected_episode_files")
        all_rows = p.get("all_episode_files")
        if not isinstance(selected_rows, list) or not isinstance(all_rows, list):
            raise ValueError("reference provenance file manifests missing")
        selected_files: list[tuple[int, str]] = []
        for row in selected_rows:
            if not isinstance(row, Mapping):
                raise ValueError("invalid selected episode manifest row")
            ep = int(row.get("episode_index"))
            digest = row.get("sha256")
            if ep < 0 or not isinstance(digest, str) or not _HEX64.fullmatch(digest):
                raise ValueError("invalid selected episode manifest row")
            selected_files.append((ep, digest))
        if tuple(sorted(ep for ep, _ in selected_files)) != selected_indices:
            raise ValueError("selected episode manifest/index mismatch")

        all_files: list[tuple[int, str | None]] = []
        for row in all_rows:
            if not isinstance(row, Mapping):
                raise ValueError("invalid all-episode manifest row")
            ep = int(row.get("episode_index"))
            digest = row.get("sha256")
            if ep < 0 or (digest is not None and (not isinstance(digest, str) or not _HEX64.fullmatch(digest))):
                raise ValueError("invalid all-episode manifest row")
            all_files.append((ep, digest))
        declared_count = int(p.get("declared_episode_count", -1))
        if declared_count != len(all_files) or declared_count <= 0:
            raise ValueError("declared episode count mismatch")
        all_files = sorted(all_files)
        if len({ep for ep, _ in all_files}) != len(all_files):
            raise ValueError("duplicate all-episode manifest index")
        selected_files = sorted(selected_files)
        all_by_episode = dict(all_files)
        if any(ep not in all_by_episode or all_by_episode[ep] != digest for ep, digest in selected_files):
            raise ValueError("selected episode bytes do not match the declared corpus manifest")

        corpus_payload = {
            "version": MANIFEST_VERSION,
            "info_sha256": str(p["info_sha256"]),
            "episodes_metadata_sha256": episodes_meta,
            "declared_episode_indices": [ep for ep, _ in all_files],
            "episode_files": [
                {"episode_index": ep, "sha256": digest} for ep, digest in all_files
            ],
        }
        computed_corpus_sha = _canonical_digest(corpus_payload)
        if str(p["corpus_sha256"]) != computed_corpus_sha:
            raise ValueError("reference corpus manifest digest mismatch")
        selected_payload = {
            "version": MANIFEST_VERSION,
            "role": CLEAN_REFERENCE_ROLE,
            "corpus_sha256": computed_corpus_sha,
            "selected_episode_files": [
                {"episode_index": ep, "sha256": digest} for ep, digest in selected_files
            ],
        }
        if str(p["selected_sha256"]) != _canonical_digest(selected_payload):
            raise ValueError("reference selected-episode manifest digest mismatch")

        feature_keys_raw = value.get("feature_keys")
        if not isinstance(feature_keys_raw, list) or not feature_keys_raw:
            raise ValueError("reference feature key manifest missing")
        feature_keys = tuple(str(k) for k in feature_keys_raw)
        if len(set(feature_keys)) != len(feature_keys):
            raise ValueError("duplicate reference feature key")
        profile_raw = value.get("profile")
        if not isinstance(profile_raw, Mapping):
            raise ValueError("reference core profile missing")
        profile = ReferenceProfile.from_dict(profile_raw)
        if set(profile.features) != set(feature_keys):
            raise ValueError("reference feature manifest/profile mismatch")

        manifest = CorpusManifest(
            MANIFEST_VERSION,
            CLEAN_REFERENCE_ROLE,
            str(p["corpus_sha256"]),
            str(p["selected_sha256"]),
            str(p["info_sha256"]),
            episodes_meta,
            declared_count,
            selected_indices,
            tuple(selected_files),
            tuple(all_files),
        )
        return BoundReferenceProfile(BOUND_REFERENCE_VERSION, manifest, feature_keys, profile)


def assert_no_reference_overlap(reference: BoundReferenceProfile, scan: CorpusManifest) -> None:
    if reference.provenance.role != CLEAN_REFERENCE_ROLE:
        raise ValueError("reference is not bound to organizer clean-reference role")
    if scan.role != TEST_ROLE:
        raise ValueError("a bound reference may only score an ORGANIZER_TEST dataset")
    if reference.provenance.corpus_sha256 == scan.corpus_sha256:
        raise ValueError("reference and scan resolve to the same corpus generation")
    ref_hashes = {digest for _, digest in reference.provenance.selected_episode_files}
    scan_hashes = {digest for _, digest in scan.all_episode_files if digest is not None}
    overlap = sorted(ref_hashes.intersection(scan_hashes))
    if overlap:
        raise ValueError(
            "reference source overlaps scanned corpus by exact episode bytes: "
            + ",".join(overlap[:3])
        )
