"""Submission packaging with provider-pinned real-fold authority and an explicit fixture path."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Iterable, Mapping, Sequence
import zipfile

import numpy as np

try:
    from .contract import (
        BundleReceipt,
        ContractError,
        D3D_PUBLIC_TEST_SHOTS,
        HF_DATASET,
        MAST_PUBLIC_TEST_SHOTS,
        OFFICIAL_STARTER_SHA,
        Prediction,
        contract_snapshot,
    )
    from .npz_packaging import compile_submission_npz, read_npz_strict, validate_prediction_arrays
except ImportError:
    from contract import (
        BundleReceipt,
        ContractError,
        D3D_PUBLIC_TEST_SHOTS,
        HF_DATASET,
        MAST_PUBLIC_TEST_SHOTS,
        OFFICIAL_STARTER_SHA,
        Prediction,
        contract_snapshot,
    )
    from npz_packaging import compile_submission_npz, read_npz_strict, validate_prediction_arrays


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_PROVIDER_AUTHORITY_PATH = Path(__file__).with_name("provider_fold_authority.json")
# Exact hash of the checked-in capture-required authority file. Terminal real
# compilation stays fail-closed until a separately reviewed provider capture
# replaces that file and this source-pinned digest in the same commit.
_PROVIDER_AUTHORITY_SHA256 = "cb40cf0f0a764a3e23cbb59626503d4b02e2c303bcf48c66e1761cbc87343a21"
_PROVIDER_AUTHORITY_SCHEMA = "sophelio-fusion-equilibrium/provider-fold-authority-v1"
_PROVIDER_SOURCE_SCHEMA = "sophelio-fusion-equilibrium/provider-source-receipt-v1"


@dataclass(frozen=True)
class PublicFoldManifest:
    machine: str
    config: str
    lengths: tuple[int, ...]
    source_receipt_sha256: str
    sha256: str


@dataclass(frozen=True)
class ProviderFoldAuthority:
    provider_revision: str
    authority_sha256: str
    d3d_fold: PublicFoldManifest
    mast_fold: PublicFoldManifest

    def fold_for(self, machine: str) -> PublicFoldManifest:
        if machine == "DIII-D":
            return self.d3d_fold
        if machine == "MAST":
            return self.mast_fold
        raise ContractError(f"unknown machine {machine}")


def _canonical_json_bytes(obj: object) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def _pairs_strict(items):
    out = {}
    for key, value in items:
        if key in out:
            raise ContractError(f"duplicate manifest key {key!r}")
        out[key] = value
    return out


def _parse_json_bytes_strict(raw: bytes, label: str) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs_strict)
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError(f"invalid {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be an object")
    return value


def _load_json_strict(path: Path) -> dict:
    try:
        raw = path.read_bytes()
    except Exception as exc:
        raise ContractError(f"cannot read manifest: {exc}") from exc
    return _parse_json_bytes_strict(raw, "manifest")


def _fold_contract(machine: str) -> tuple[str, int]:
    if machine == "DIII-D":
        return "diii_d_public_test", D3D_PUBLIC_TEST_SHOTS
    if machine == "MAST":
        return "mast_public_test", MAST_PUBLIC_TEST_SHOTS
    raise ContractError(f"unknown machine {machine}")


def _fold_payload(machine: str, config: str, lengths: Sequence[int], source_receipt_sha256: str) -> dict:
    return {
        "schema": "sophelio-fusion-equilibrium/public-fold-lengths-v1",
        "machine": machine,
        "config": config,
        "dataset": HF_DATASET,
        "starter_sha": OFFICIAL_STARTER_SHA,
        "shots": len(lengths),
        "lengths": [int(v) for v in lengths],
        "source_receipt_sha256": source_receipt_sha256,
    }


def _manifest_from_lengths(
    machine: str,
    lengths: Sequence[int],
    source_receipt_sha256: str,
) -> PublicFoldManifest:
    config, expected = _fold_contract(machine)
    if not _SHA256_RE.fullmatch(str(source_receipt_sha256)):
        raise ContractError("source receipt must be lowercase SHA-256")
    normalized = tuple(int(v) for v in lengths)
    if len(normalized) != expected:
        raise ContractError(f"{machine} fold has {len(normalized)} shots, expected {expected}")
    if any(v <= 0 for v in normalized):
        raise ContractError("public-test shot lengths must be positive")
    payload = _fold_payload(machine, config, normalized, source_receipt_sha256)
    digest = sha256(_canonical_json_bytes(payload)).hexdigest()
    return PublicFoldManifest(machine, config, normalized, source_receipt_sha256, digest)


def capture_public_test_lengths(
    rows: Iterable[Mapping[str, object]],
    machine: str,
    *,
    source_receipt_sha256: str,
) -> PublicFoldManifest:
    """Capture a candidate T ledger; this helper never grants terminal authority.

    ``source_receipt_sha256`` is retained for offline capture bookkeeping only.
    ``compile_real_bundle`` ignores caller-produced manifests and roots and loads
    its fold authority exclusively from the source-pinned provider authority file.
    """
    _, expected = _fold_contract(machine)
    lengths: list[int] = []
    for row in rows:
        if not isinstance(row, Mapping) or "efit_times" not in row:
            raise ContractError("public-test row missing efit_times")
        times = np.asarray(row["efit_times"], dtype=np.float64)
        if times.ndim != 1 or times.size < 1 or not np.isfinite(times).all():
            raise ContractError("invalid public-test efit_times")
        lengths.append(int(times.size))
        if len(lengths) > expected:
            raise ContractError(f"{machine} public-test stream has extra shots")
    return _manifest_from_lengths(machine, lengths, source_receipt_sha256)


def _validated_provider_shards(value: object) -> tuple[dict, ...]:
    if not isinstance(value, list) or not value:
        raise ContractError("provider authority requires a non-empty shard ledger")
    shards: list[dict] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}:
            raise ContractError("provider shard receipt shape drift")
        path = item["path"]
        size = item["size"]
        digest = item["sha256"]
        if not isinstance(path, str) or not path or "\\" in path or path.startswith("/"):
            raise ContractError("provider shard path is not repository-relative")
        parts = path.split("/")
        if any(part in {"", ".", ".."} for part in parts) or not path.endswith(".parquet"):
            raise ContractError("provider shard path is not a canonical parquet path")
        if path in seen:
            raise ContractError("duplicate provider shard path")
        seen.add(path)
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ContractError("provider shard size must be a positive integer")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise ContractError("provider shard digest must be lowercase SHA-256")
        shards.append({"path": path, "size": size, "sha256": digest})
    shards.sort(key=lambda item: item["path"])
    return tuple(shards)


def _provider_source_receipt_sha256(
    machine: str,
    config: str,
    provider_revision: str,
    shards: Sequence[Mapping[str, object]],
) -> str:
    payload = {
        "schema": _PROVIDER_SOURCE_SCHEMA,
        "dataset": HF_DATASET,
        "starter_sha": OFFICIAL_STARTER_SHA,
        "provider_revision": provider_revision,
        "machine": machine,
        "config": config,
        "shards": [dict(item) for item in shards],
    }
    return sha256(_canonical_json_bytes(payload)).hexdigest()


def _fold_from_authority_entry(
    config: str,
    value: object,
    provider_revision: str,
) -> PublicFoldManifest:
    if not isinstance(value, dict) or set(value) != {"machine", "shots", "lengths", "shards"}:
        raise ContractError(f"provider fold authority shape drift for {config}")
    machine = value["machine"]
    if not isinstance(machine, str):
        raise ContractError("provider authority machine must be text")
    expected_config, expected_count = _fold_contract(machine)
    if config != expected_config:
        raise ContractError("provider fold machine/config drift")
    shots = value["shots"]
    lengths = value["lengths"]
    if isinstance(shots, bool) or not isinstance(shots, int) or shots != expected_count:
        raise ContractError("provider fold shot-count drift")
    if not isinstance(lengths, list) or any(isinstance(v, bool) or not isinstance(v, int) for v in lengths):
        raise ContractError("provider fold lengths malformed")
    if len(lengths) != shots:
        raise ContractError("provider fold length-count drift")
    shards = _validated_provider_shards(value["shards"])
    source_receipt = _provider_source_receipt_sha256(machine, config, provider_revision, shards)
    return _manifest_from_lengths(machine, lengths, source_receipt)


def _parse_provider_authority_bytes(raw: bytes, expected_sha256: str) -> ProviderFoldAuthority:
    """Parse exact provider authority bytes against an independently pinned hash.

    This private parser is exposed to tests so the verified-path architecture can
    be exercised with a synthetic fixed fixture. Production calls only
    ``_load_provider_authority``, whose expected hash is a source literal.
    """
    if not _SHA256_RE.fullmatch(str(expected_sha256)):
        raise ContractError("provider authority pin must be lowercase SHA-256")
    actual = sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise ContractError("provider authority file digest mismatch")
    value = _parse_json_bytes_strict(raw, "provider fold authority")
    required = {"schema", "status", "dataset", "starter_sha", "provider_revision", "folds"}
    if set(value) != required:
        raise ContractError("provider authority top-level shape drift")
    if value["schema"] != _PROVIDER_AUTHORITY_SCHEMA:
        raise ContractError("provider authority schema drift")
    if value["dataset"] != HF_DATASET or value["starter_sha"] != OFFICIAL_STARTER_SHA:
        raise ContractError("provider authority source identity drift")
    if value["status"] != "verified":
        raise ContractError(
            "provider fold authority is not verified; capture the complete provider shards "
            "and pin their exact ledger before terminal compilation"
        )
    revision = value["provider_revision"]
    if not isinstance(revision, str) or not _REVISION_RE.fullmatch(revision):
        raise ContractError("provider authority revision must be a 40-hex provider commit")
    folds = value["folds"]
    if not isinstance(folds, dict) or set(folds) != {"diii_d_public_test", "mast_public_test"}:
        raise ContractError("provider authority fold set drift")
    d3d = _fold_from_authority_entry("diii_d_public_test", folds["diii_d_public_test"], revision)
    mast = _fold_from_authority_entry("mast_public_test", folds["mast_public_test"], revision)
    return ProviderFoldAuthority(revision, actual, d3d, mast)


def _load_provider_authority() -> ProviderFoldAuthority:
    try:
        raw = _PROVIDER_AUTHORITY_PATH.read_bytes()
    except Exception as exc:
        raise ContractError(f"cannot read provider fold authority: {exc}") from exc
    # Keep the pin literal at the production trust boundary. A candidate caller
    # cannot unlock compilation by passing a matching digest alongside its own rows.
    return _parse_provider_authority_bytes(
        raw,
        "cb40cf0f0a764a3e23cbb59626503d4b02e2c303bcf48c66e1761cbc87343a21",
    )


def _validate_fold_manifest(fold: PublicFoldManifest, machine: str) -> None:
    if not isinstance(fold, PublicFoldManifest):
        raise ContractError("real bundle requires a provider-pinned PublicFoldManifest")
    rebuilt = _manifest_from_lengths(fold.machine, fold.lengths, fold.source_receipt_sha256)
    expected_config, expected_count = _fold_contract(machine)
    if fold.machine != machine or fold.config != expected_config:
        raise ContractError("public-fold machine/config drift")
    if len(fold.lengths) != expected_count:
        raise ContractError("public-fold shot-count drift")
    if fold.sha256 != rebuilt.sha256:
        raise ContractError("public-fold manifest digest drift")


def _write_direct_zip(out: Path, d3d: Path, mast: Path) -> str:
    submission = out / "submission.zip"
    with zipfile.ZipFile(submission, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in (d3d.name, mast.name):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            zf.writestr(info, (out / name).read_bytes())
    return sha256(submission.read_bytes()).hexdigest()


def _verify_direct_zip(out: Path, direct: object) -> None:
    submission = out / "submission.zip"
    if not isinstance(direct, dict) or direct.get("name") != submission.name:
        raise ContractError("direct submission receipt drift")
    if not submission.is_file() or sha256(submission.read_bytes()).hexdigest() != direct.get("sha256"):
        raise ContractError("direct submission zip digest mismatch")
    try:
        with zipfile.ZipFile(submission, "r") as zf:
            names = zf.namelist()
            if names != ["diii_d_public_test.npz", "mast_public_test.npz"]:
                raise ContractError(f"direct submission member drift: {names}")
            for name in names:
                if zf.read(name) != (out / name).read_bytes():
                    raise ContractError(f"direct submission member bytes drift: {name}")
    except zipfile.BadZipFile as exc:
        raise ContractError("invalid direct submission zip") from exc


def compile_real_bundle(
    out_dir: Path | str,
    d3d_predictions: Sequence[Prediction],
    mast_predictions: Sequence[Prediction],
) -> BundleReceipt:
    """Build terminal artifacts only from source-pinned provider fold authority.

    There is intentionally no fold/root/source-receipt argument. Until the
    checked-in provider authority is independently captured and marked verified,
    this function fails before creating any output path.
    """
    authority = _load_provider_authority()
    d3d_fold = authority.d3d_fold
    mast_fold = authority.mast_fold
    _validate_fold_manifest(d3d_fold, "DIII-D")
    _validate_fold_manifest(mast_fold, "MAST")
    if len(d3d_predictions) != D3D_PUBLIC_TEST_SHOTS:
        raise ContractError("DIII-D predictions do not cover the complete public test fold")
    if len(mast_predictions) != MAST_PUBLIC_TEST_SHOTS:
        raise ContractError("MAST predictions do not cover the complete public test fold")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    d3d = out / "diii_d_public_test.npz"
    mast = out / "mast_public_test.npz"
    d3d_sha = compile_submission_npz(d3d, d3d_predictions, d3d_fold.lengths, "DIII-D")
    mast_sha = compile_submission_npz(mast, mast_predictions, mast_fold.lengths, "MAST")
    submission_sha = _write_direct_zip(out, d3d, mast)

    manifest = {
        "schema": "sophelio-fusion-equilibrium/tjlabs-real-bundle-v3",
        "contract": contract_snapshot(),
        "provider_authority": {
            "sha256": authority.authority_sha256,
            "provider_revision": authority.provider_revision,
        },
        "folds": {
            d3d_fold.config: {
                **_fold_payload(
                    d3d_fold.machine,
                    d3d_fold.config,
                    d3d_fold.lengths,
                    d3d_fold.source_receipt_sha256,
                ),
                "sha256": d3d_fold.sha256,
            },
            mast_fold.config: {
                **_fold_payload(
                    mast_fold.machine,
                    mast_fold.config,
                    mast_fold.lengths,
                    mast_fold.source_receipt_sha256,
                ),
                "sha256": mast_fold.sha256,
            },
        },
        "files": {
            d3d.name: {
                "sha256": d3d_sha,
                "shots": D3D_PUBLIC_TEST_SHOTS,
                "fold_sha256": d3d_fold.sha256,
            },
            mast.name: {
                "sha256": mast_sha,
                "shots": MAST_PUBLIC_TEST_SHOTS,
                "fold_sha256": mast_fold.sha256,
            },
        },
        "direct_submission_zip": {"name": "submission.zip", "sha256": submission_sha},
        "truth": {
            "fixture_only": False,
            "provider_authority_verified": True,
            "codabench_submission_performed": False,
            "leaderboard_score_known": False,
            "award_or_payment_received": False,
        },
    }
    manifest_bytes = _canonical_json_bytes(manifest)
    (out / "manifest.json").write_bytes(manifest_bytes)
    manifest_sha = sha256(manifest_bytes).hexdigest()
    return BundleReceipt(d3d_sha, mast_sha, manifest_sha, submission_sha)


def _fold_from_json(value: object) -> PublicFoldManifest:
    if not isinstance(value, dict):
        raise ContractError("fold manifest must be an object")
    required = {
        "schema",
        "machine",
        "config",
        "dataset",
        "starter_sha",
        "shots",
        "lengths",
        "source_receipt_sha256",
        "sha256",
    }
    if set(value) != required:
        raise ContractError("fold manifest shape drift")
    lengths = value.get("lengths")
    if not isinstance(lengths, list) or any(isinstance(v, bool) or not isinstance(v, int) for v in lengths):
        raise ContractError("fold lengths malformed")
    fold = _manifest_from_lengths(str(value["machine"]), lengths, str(value["source_receipt_sha256"]))
    if value["schema"] != "sophelio-fusion-equilibrium/public-fold-lengths-v1":
        raise ContractError("fold schema drift")
    if value["config"] != fold.config or value["dataset"] != HF_DATASET or value["starter_sha"] != OFFICIAL_STARTER_SHA:
        raise ContractError("fold source identity drift")
    if value["shots"] != len(fold.lengths) or value["sha256"] != fold.sha256:
        raise ContractError("fold receipt drift")
    return fold


def verify_real_bundle(out_dir: Path | str) -> dict:
    authority = _load_provider_authority()
    out = Path(out_dir)
    manifest = _load_json_strict(out / "manifest.json")
    if manifest.get("schema") != "sophelio-fusion-equilibrium/tjlabs-real-bundle-v3":
        raise ContractError("wrong real manifest schema")
    if manifest.get("contract") != contract_snapshot():
        raise ContractError("contract snapshot drift")
    if manifest.get("provider_authority") != {
        "sha256": authority.authority_sha256,
        "provider_revision": authority.provider_revision,
    }:
        raise ContractError("provider authority receipt drift")
    folds = manifest.get("folds")
    if not isinstance(folds, dict) or set(folds) != {"diii_d_public_test", "mast_public_test"}:
        raise ContractError("fold set drift")
    d3d_fold = _fold_from_json(folds["diii_d_public_test"])
    mast_fold = _fold_from_json(folds["mast_public_test"])
    for embedded, pinned, machine in (
        (d3d_fold, authority.d3d_fold, "DIII-D"),
        (mast_fold, authority.mast_fold, "MAST"),
    ):
        _validate_fold_manifest(embedded, machine)
        if embedded != pinned:
            raise ContractError("embedded fold does not match provider-pinned authority")

    expected_files = {
        "diii_d_public_test.npz": ("DIII-D", d3d_fold, D3D_PUBLIC_TEST_SHOTS),
        "mast_public_test.npz": ("MAST", mast_fold, MAST_PUBLIC_TEST_SHOTS),
    }
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != set(expected_files):
        raise ContractError("manifest file set drift")
    for name, (machine, fold, shots) in expected_files.items():
        meta = files[name]
        if not isinstance(meta, dict) or set(meta) != {"sha256", "shots", "fold_sha256"}:
            raise ContractError(f"file receipt shape drift for {name}")
        path = out / name
        if meta["shots"] != shots or meta["fold_sha256"] != fold.sha256:
            raise ContractError(f"file completeness receipt drift for {name}")
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != meta["sha256"]:
            raise ContractError(f"digest mismatch for {name}")
        arrays = read_npz_strict(path)
        validate_prediction_arrays(arrays, fold.lengths, machine)

    _verify_direct_zip(out, manifest.get("direct_submission_zip"))
    if manifest.get("truth") != {
        "fixture_only": False,
        "provider_authority_verified": True,
        "codabench_submission_performed": False,
        "leaderboard_score_known": False,
        "award_or_payment_received": False,
    }:
        raise ContractError("truth boundary drift")
    return manifest


def compile_bundle(
    out_dir: Path | str,
    d3d_predictions: Sequence[Prediction],
    d3d_lengths: Sequence[int],
    mast_predictions: Sequence[Prediction],
    mast_lengths: Sequence[int],
) -> BundleReceipt:
    """Synthetic/partial fixture helper. Its output is never terminal submission evidence."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    d3d = out / "diii_d_public_test.npz"
    mast = out / "mast_public_test.npz"
    d3d_sha = compile_submission_npz(d3d, d3d_predictions, d3d_lengths, "DIII-D")
    mast_sha = compile_submission_npz(mast, mast_predictions, mast_lengths, "MAST")
    submission_sha = _write_direct_zip(out, d3d, mast)
    manifest = {
        "schema": "sophelio-fusion-equilibrium/tjlabs-fixture-bundle-v2",
        "contract": contract_snapshot(),
        "files": {
            d3d.name: {"sha256": d3d_sha, "shots": len(d3d_lengths)},
            mast.name: {"sha256": mast_sha, "shots": len(mast_lengths)},
        },
        "direct_submission_zip": {"name": "submission.zip", "sha256": submission_sha},
        "truth": {
            "fixture_only": True,
            "codabench_submission_performed": False,
            "leaderboard_score_known": False,
            "award_or_payment_received": False,
        },
    }
    manifest_bytes = _canonical_json_bytes(manifest)
    (out / "manifest.json").write_bytes(manifest_bytes)
    manifest_sha = sha256(manifest_bytes).hexdigest()
    return BundleReceipt(d3d_sha, mast_sha, manifest_sha, submission_sha)


def verify_bundle(out_dir: Path | str) -> dict:
    """Verify only a fixture bundle; use ``verify_real_bundle`` for terminal artifacts."""
    out = Path(out_dir)
    manifest = _load_json_strict(out / "manifest.json")
    if manifest.get("schema") != "sophelio-fusion-equilibrium/tjlabs-fixture-bundle-v2":
        raise ContractError("wrong fixture manifest schema")
    if manifest.get("contract") != contract_snapshot():
        raise ContractError("contract snapshot drift")
    expected = {"diii_d_public_test.npz", "mast_public_test.npz"}
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != expected:
        raise ContractError("manifest file set drift")
    for name in sorted(expected):
        path = out / name
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != files[name].get("sha256"):
            raise ContractError(f"digest mismatch for {name}")
    _verify_direct_zip(out, manifest.get("direct_submission_zip"))
    if manifest.get("truth") != {
        "fixture_only": True,
        "codabench_submission_performed": False,
        "leaderboard_score_known": False,
        "award_or_payment_received": False,
    }:
        raise ContractError("fixture truth boundary drift")
    return manifest
