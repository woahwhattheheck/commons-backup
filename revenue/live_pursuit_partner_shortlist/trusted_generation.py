"""Private source-owned evidence generation for partner-shortlist."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib, json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "trusted_evidence_manifest.json"


def _load():
    raw_bytes = MANIFEST.read_bytes()
    raw = json.loads(raw_bytes.decode("utf-8"))
    if set(raw) != {"schema_version", "scope", "pursuits"}:
        raise RuntimeError("trust manifest root mismatch")
    if raw["schema_version"] != "live-pursuit-partner-shortlist-trust/v1":
        raise RuntimeError("trust manifest schema mismatch")
    if raw["scope"] != "SYNTHETIC_ONLY":
        raise RuntimeError("trust manifest scope mismatch")
    by_pid = {}
    for p in raw["pursuits"]:
        if set(p) != {"pursuit_id", "source", "requirements", "evidence"}:
            raise RuntimeError("trust pursuit shape mismatch")
        pid = p["pursuit_id"]
        if type(pid) is not str or not pid or pid in by_pid:
            raise RuntimeError("trust pursuit id mismatch")
        source = p["source"]
        for row in [source] + list(p["evidence"]):
            uri = row["source_uri"]
            q = PurePosixPath(uri)
            if q.is_absolute() or ".." in q.parts or chr(92) in uri:
                raise RuntimeError("unsafe trusted source path")
            path = ROOT / q
            if hashlib.sha256(path.read_bytes()).hexdigest() != row["source_sha256"]:
                raise RuntimeError("trusted source digest mismatch")
        reqs = {r["requirement_id"]: r for r in p["requirements"]}
        evs = {e["evidence_id"]: e for e in p["evidence"]}
        if len(reqs) != len(p["requirements"]) or len(evs) != len(p["evidence"]):
            raise RuntimeError("duplicate trust id")
        by_pid[pid] = {"source": source, "requirements": reqs, "evidence": evs}

    captured = json.loads(json.dumps(by_pid, sort_keys=True))
    generation_sha = hashlib.sha256(raw_bytes).hexdigest()
    now_fn, utc = datetime.now, timezone.utc

    def authenticate(mode, pid, source, requirements, evidence):
        t = captured.get(pid)
        if mode != "SYNTHETIC" or t is None:
            return False, (), ()
        req_ids = tuple(sorted(
            r["requirement_id"] for r in requirements
            if t["requirements"].get(r["requirement_id"]) == r
        ))
        ev_ids = []
        for row in evidence:
            clean = {k: v for k, v in row.items() if k != "current"}
            if t["evidence"].get(clean["evidence_id"]) == clean:
                ev_ids.append(clean["evidence_id"])
        return source == t["source"], req_ids, tuple(sorted(ev_ids))

    def live_now():
        return now_fn(utc)

    return authenticate, live_now, generation_sha


authenticate, live_now, GENERATION_SHA256 = _load()
