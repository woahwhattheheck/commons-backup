"""Hard source/revision pins for the Learn2Design public evidence rail."""
from __future__ import annotations
import hashlib, importlib.util, json, subprocess
from pathlib import Path
from typing import Any

SCHEMA = 1
EVIDENCE_CLASS = "ORGANIZER_PUBLIC_DEVELOPMENT"
ORGANIZER_REPOSITORY = "artificial-scientist-lab/Learn2Design-2026"
ORGANIZER_COMMIT = "84a4b0a4c7e0f3b702459ffc8ba6a1d84d34cefa"
ORGANIZER_PYPROJECT_BLOB = "50f509ac6cfd4e1f4843337410d1fb76d36720c4"
PROBLEM_CLASS = "ConstrainedVoyagerProblem"
AUTHORITY = {"officialScoreClaimed": False, "hiddenTopologyClaimed": False,
             "h100ParityClaimed": False, "prizeClaimed": False, "paymentClaimed": False}
EXPECTED_CANDIDATES = {
    "serial_v1": {"path": "revenue/learn2design2026/submission_v1.py",
        "algorithm": "tjlabs_staged_trust_portfolio_v1",
        "gitBlobSha1": "0e5b0141138c471c9b47163aca4f1a01336dfdf1",
        "sourceMergeCommit": "edb53afa40a081174207b0f8c5a2a47b9aebb197"},
    "vectorized_v2": {"path": "revenue/learn2design2026/submission.py",
        "algorithm": "tjlabs_vectorized_trust_portfolio_v2",
        "gitBlobSha1": "ac814d1f543529a823f7c3afa2a9c4f54c0bfe12",
        "sourceMergeCommit": "de815e79f3ae9acfa380ce6ee91b396c8d6783f4"},
}

class EvidenceError(RuntimeError):
    pass

class _StrictJsonObject(dict):
    """Mapping plus read-bound raw digest metadata, never serialized as JSON."""
    __slots__ = ("_raw_sha256",)

def _strict_object(pairs):
    out = _StrictJsonObject()
    for key, value in pairs:
        if key in out:
            raise EvidenceError(f"duplicate JSON object key: {key!r}")
        out[key] = value
    return out

def _assert_scalar_unicode(value: Any) -> None:
    if isinstance(value, str):
        try:
            value.encode("utf-8", "strict")
        except UnicodeEncodeError as exc:
            raise EvidenceError("JSON contains non-scalar Unicode") from exc
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_scalar_unicode(key)
            _assert_scalar_unicode(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _assert_scalar_unicode(item)

def canonical_bytes(v: Any) -> bytes:
    try:
        _assert_scalar_unicode(v)
        text = json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        return (text + "\n").encode("utf-8", "strict")
    except EvidenceError:
        raise
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise EvidenceError("value must be finite scalar-Unicode JSON") from exc

def canonical_sha256(v: Any) -> str:
    return hashlib.sha256(canonical_bytes(v)).hexdigest()

def git_blob_sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()

def read_json(p: Path) -> dict[str, Any]:
    try:
        raw = p.read_bytes()
        text = raw.decode("utf-8", "strict")
        v = json.loads(text, object_pairs_hook=_strict_object)
        _assert_scalar_unicode(v)
    except EvidenceError:
        raise
    except Exception as exc:
        raise EvidenceError(f"cannot read JSON {p}: {exc}") from exc
    if not isinstance(v, _StrictJsonObject):
        raise EvidenceError(f"expected object in {p}")
    v._raw_sha256 = hashlib.sha256(raw).hexdigest()
    return v

def confined(root: Path, rel: str) -> Path:
    if not rel or Path(rel).is_absolute(): raise EvidenceError("candidate path must be relative")
    rr=root.resolve(); p=(rr/rel).resolve()
    try: p.relative_to(rr)
    except ValueError as e: raise EvidenceError("candidate path escapes repository") from e
    if not p.is_file() or p.is_symlink(): raise EvidenceError(f"candidate source invalid: {rel}")
    return p

def expected_manifest() -> dict[str, Any]:
    return {"schemaVersion":SCHEMA,"evidenceClass":EVIDENCE_CLASS,"authority":dict(AUTHORITY),
      "organizer":{"repository":ORGANIZER_REPOSITORY,"commit":ORGANIZER_COMMIT,
                   "pyprojectGitBlobSha1":ORGANIZER_PYPROJECT_BLOB},
      "cell":{"problemClass":PROBLEM_CLASS,"seed":42,"maxTimeSeconds":30,
              "scope":"public-development","primaryMetric":"best_loss"},
      "candidates":EXPECTED_CANDIDATES}

def validate_manifest(path: Path, repo_root: Path) -> dict[str, Any]:
    m=read_json(path)
    if m != expected_manifest(): raise EvidenceError("manifest differs from hard-pinned evidence contract")
    for label,s in EXPECTED_CANDIDATES.items():
        got=git_blob_sha1_bytes(confined(repo_root,s["path"]).read_bytes())
        if got != s["gitBlobSha1"]: raise EvidenceError(f"{label} source drift: {got}")
    return m

def candidate_spec(m: dict[str,Any], label: str) -> dict[str,Any]:
    if label not in EXPECTED_CANDIDATES or m.get("candidates",{}).get(label) != EXPECTED_CANDIDATES[label]:
        raise EvidenceError(f"invalid candidate pin: {label}")
    return EXPECTED_CANDIDATES[label]

def verify_organizer_source(path: Path) -> dict[str,str]:
    try:
        p=subprocess.run(["git","-C",str(path),"rev-parse","HEAD"],text=True,capture_output=True,timeout=20)
    except Exception as e: raise EvidenceError(f"organizer git check failed: {e}") from e
    if p.returncode: raise EvidenceError(f"organizer git check failed: {p.stderr.strip()}")
    head=p.stdout.strip()
    if head != ORGANIZER_COMMIT: raise EvidenceError(f"organizer revision drift: {head}")
    pp=path/"pyproject.toml"
    if not pp.is_file(): raise EvidenceError("organizer pyproject.toml missing")
    blob=git_blob_sha1_bytes(pp.read_bytes())
    if blob != ORGANIZER_PYPROJECT_BLOB: raise EvidenceError(f"organizer pyproject drift: {blob}")
    return {"repository":ORGANIZER_REPOSITORY,"commit":head,"pyprojectGitBlobSha1":blob}

def load_candidate(repo_root: Path, label: str, spec: dict[str,Any]):
    src=confined(repo_root,spec["path"])
    if git_blob_sha1_bytes(src.read_bytes()) != spec["gitBlobSha1"]: raise EvidenceError("candidate source drift")
    ms=importlib.util.spec_from_file_location(f"_l2d_evidence_{label}",src)
    if ms is None or ms.loader is None: raise EvidenceError("candidate loader unavailable")
    mod=importlib.util.module_from_spec(ms); ms.loader.exec_module(mod)
    cls=getattr(mod,"StagedTrustPortfolio",None)
    if cls is None or getattr(cls,"algorithm_str",None) != spec["algorithm"]: raise EvidenceError("candidate identity mismatch")
    return cls
