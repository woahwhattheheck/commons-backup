"""Isolated access to the existing workshare compiler; never a replacement scorer."""
from __future__ import annotations
import json
from functools import lru_cache
import hashlib
from pathlib import Path
import subprocess
import sys

LIMIT = 2 * 1024 * 1024


def call_parent(action: str, payload: dict) -> dict:
    if action not in {"compile", "verify"}:
        raise ValueError("unsupported parent action")
    raw = json.dumps(payload, allow_nan=False, sort_keys=True).encode("utf-8")
    if len(raw) > LIMIT:
        raise ValueError("parent input exceeds 2 MiB")
    parent = Path(__file__).resolve().parent.parent / "uiowa_rfq_18649_workshare"
    revision = hashlib.sha256(b"".join(p.name.encode() + p.read_bytes()
                                     for p in sorted(parent.glob("workshare_*.py")))).hexdigest()
    return json.loads(_execute(action, raw, revision))


@lru_cache(maxsize=16)
def _execute(action: str, raw: bytes, parent_revision: str) -> bytes:
    # Cache exact immutable payload bytes only, invalidated by parent source changes.
    # Return bytes so callers cannot mutate a previously verified cached object.
    try:
        run = subprocess.run(
            [sys.executable, "-I", *(["-O"] if sys.flags.optimize else []), str(Path(__file__).resolve()), action],
            input=raw, capture_output=True, timeout=30, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("parent compiler timed out") from exc
    if run.returncode:
        raise ValueError("parent compiler rejected input: " + run.stderr.decode("utf-8", "replace")[:2000])
    return run.stdout


def compile_inspection(candidate: dict, authority: dict) -> dict:
    return call_parent("compile", {"candidate": candidate, "authority": authority})


def verify_inspection(report: dict) -> dict:
    result = call_parent("verify", report)
    if result.get("semantic_recompile_valid") is not True or result.get("current_authority_verified") is not False:
        raise ValueError("parent verification did not establish non-authoritative integrity")
    return result


def worker(action: str) -> None:
    parent = Path(__file__).resolve().parent.parent / "uiowa_rfq_18649_workshare"
    if not (parent / "workshare_compile.py").is_file():
        raise ValueError("existing parent compiler is required; run inside the Commons checkout")
    sys.path.insert(0, str(parent))
    from workshare_core import loads_strict, canonical_json_bytes, _parse_utc
    from workshare_compile import compile_untrusted_inspection
    from workshare_authority import normalize_authority
    from workshare_verify import verify_report_integrity
    raw = sys.stdin.buffer.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("parent input exceeds 2 MiB")
    payload = loads_strict(raw.decode("utf-8"))
    if action == "compile":
        if type(payload) is not dict or set(payload) != {"candidate", "authority"}:
            raise ValueError("compile requires candidate and authority only")
        authority = normalize_authority(payload["authority"])
        # Same deterministic non-current clock policy as the parent's public CLI.
        now = max(_parse_utc(r["observed_at"], "source.observed_at") for r in authority["sources"])
        result = compile_untrusted_inspection(payload["candidate"], authority, now=now)
    elif action == "verify":
        if type(payload) is not dict or payload.get("mode") != "UNTRUSTED_INSPECTION":
            raise ValueError("only actual UNTRUSTED_INSPECTION reports are accepted")
        result = verify_report_integrity(payload)
        if payload["trust"]["current_evidence_review_authority"] is not False:
            raise ValueError("review workflow must not carry current authority")
    else:
        raise ValueError("unsupported parent action")
    sys.stdout.buffer.write(canonical_json_bytes(result))


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("expected compile or verify")
        worker(sys.argv[1])
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
