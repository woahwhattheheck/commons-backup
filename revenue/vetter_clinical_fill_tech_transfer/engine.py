from __future__ import annotations

"""Current-candidate facade for the Vetter tech-transfer evidence gate.

Compilation produces a non-authoritative candidate at process UTC. Only a
fresh process-time verification can emit ``CURRENT_OWNER_REVIEW`` authority or
render current Markdown. Deterministic explicit-time replay remains isolated in
``historical.py`` under a distinct non-current schema/mode.

Python same-process introspection is not treated as a secrecy boundary. The
mechanical boundary is semantic: even if a caller recovers the retained
explicit-time classifier from a function closure, it can at most construct a
candidate-shaped object. Current authority and current Markdown independently
re-evaluate the candidate at fresh process UTC.
"""

import argparse
import errno
import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CURRENT_CANDIDATE_SCHEMA = "vetter-clinical-fill-tech-transfer-current-candidate/v3"
CURRENT_VERIFY_SCHEMA = "vetter-clinical-fill-tech-transfer-current-verification/v3"
CURRENT_CANDIDATE_MODE = "CURRENT_EVIDENCE_CANDIDATE"
CURRENT_AUTHORITY_MODE = "CURRENT_OWNER_REVIEW"
CURRENT_CANDIDATE_KEYS = frozenset(
    {
        "schema",
        "authority_mode",
        "evaluated_at_utc",
        "decision",
        "candidate_receipt_sha256",
    }
)


def _load_private_core() -> dict[str, Any]:
    source_path = Path(__file__).with_name("_engine_v1.txt")
    source = source_path.read_text(encoding="utf-8")
    namespace: dict[str, Any] = {
        "__name__": "vetter_tech_transfer_retained_core",
        "__file__": str(source_path),
    }
    exec(compile(source, str(source_path), "exec"), namespace, namespace)
    return namespace


def _install_snapshot_chronology(core: dict[str, Any]) -> None:
    original = core["normalize_snapshot"]
    parse_utc = core["parse_utc"]
    transfer_error = core["TransferError"]

    def repaired(
        value: object,
        name: str,
        *,
        expected_role: str,
        as_of: object,
    ) -> dict[str, object]:
        if type(value) is dict:
            captured_raw = value.get("captured_at_utc")
            rows = value.get("rows")
            if captured_raw is not None and type(rows) is list:
                captured = parse_utc(captured_raw, f"{name}.captured_at_utc")
                for idx, row in enumerate(rows):
                    if type(row) is not dict or "last_updated_utc" not in row:
                        continue
                    updated = parse_utc(
                        row["last_updated_utc"],
                        f"{name}.rows[{idx}].last_updated_utc",
                    )
                    if updated > captured:
                        raise transfer_error(
                            f"{name}.rows[{idx}].last_updated_utc is later than snapshot capture"
                        )
        return original(value, name, expected_role=expected_role, as_of=as_of)

    core["normalize_snapshot"] = repaired


_core = _load_private_core()
_install_snapshot_chronology(_core)
TransferError = _core["TransferError"]
MAX_JSON_BYTES = int(_core["MAX_JSON_BYTES"])
_COMPILE_INPUT_KEYS = frozenset(_core["COMPILE_INPUT_KEYS"])


# Safe public utilities are implemented outside the retained-core namespace so
# ordinary ``fn.__globals__`` access does not reveal the explicit-time compiler.
def _reject_constant(value: str) -> None:
    raise TransferError(f"non-finite JSON value is forbidden: {value}")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise TransferError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_bytes(raw: bytes) -> Any:
    if type(raw) is not bytes:
        raise TransferError("JSON input must be exact bytes")
    if len(raw) > MAX_JSON_BYTES:
        raise TransferError("JSON input exceeds byte limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TransferError("JSON input must be UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except TransferError:
        raise
    except json.JSONDecodeError as exc:
        raise TransferError(f"invalid JSON: {exc.msg}") from exc


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def format_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise TransferError("trusted time must be timezone-aware")
    return (
        dt.astimezone(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def write_new_bytes(path: str | os.PathLike[str], data: bytes) -> None:
    if type(data) is not bytes:
        raise TransferError("output data must be bytes")
    p = Path(path)
    if p.exists() or p.is_symlink():
        raise TransferError(f"refusing to overwrite existing output: {p}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = None
    try:
        fd = os.open(p, flags, 0o600)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise TransferError("output must be a regular file")
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short output write")
            view = view[written:]
        os.fsync(fd)
    except FileExistsError as exc:
        raise TransferError(f"refusing to overwrite existing output: {p}") from exc
    finally:
        if fd is not None:
            os.close(fd)


def write_new_text(path: str | os.PathLike[str], text: str) -> None:
    if type(text) is not str:
        raise TransferError("output text must be str")
    write_new_bytes(path, text.encode("utf-8"))


def _build_current_capabilities(
    core: dict[str, Any],
    *,
    datetime_type: type[datetime],
    timezone_value: timezone,
):
    raw_compile = core["compile_transfer"]
    raw_verify = core["verify_report"]
    raw_render = core["render_markdown"]
    raw_canonical = core["canonical_sha256"]
    raw_formatter = core["format_utc"]
    transfer_error = core["TransferError"]
    snapshot_keys = frozenset(core["SNAPSHOT_KEYS"])
    candidate_schema = CURRENT_CANDIDATE_SCHEMA
    verify_schema = CURRENT_VERIFY_SCHEMA
    candidate_mode = CURRENT_CANDIDATE_MODE
    authority_mode = CURRENT_AUTHORITY_MODE
    candidate_keys = frozenset(CURRENT_CANDIDATE_KEYS)

    def clock() -> str:
        return raw_formatter(datetime_type.now(timezone_value))

    def validate_candidate(candidate: object) -> dict[str, Any]:
        if type(candidate) is not dict or set(candidate) != set(candidate_keys):
            raise transfer_error("current candidate key set is invalid")
        if candidate["schema"] != candidate_schema:
            raise transfer_error("current candidate schema mismatch")
        if candidate["authority_mode"] != candidate_mode:
            raise transfer_error("current candidate authority mode mismatch")
        receipt = candidate["candidate_receipt_sha256"]
        if type(receipt) is not str or len(receipt) != 64:
            raise transfer_error("current candidate receipt is invalid")
        without = {
            key: candidate[key]
            for key in candidate
            if key != "candidate_receipt_sha256"
        }
        if raw_canonical(without) != receipt:
            raise transfer_error("current candidate receipt mismatch")
        decision = candidate["decision"]
        raw_verify(decision)
        if candidate["evaluated_at_utc"] != decision["as_of"]:
            raise transfer_error("current candidate evaluated time does not bind decision")
        return decision

    def plain_snapshot(snapshot: object, name: str) -> dict[str, Any]:
        if type(snapshot) is not dict:
            raise transfer_error(f"current candidate {name} must be an object")
        expected = set(snapshot_keys) | {"snapshot_sha256"}
        if set(snapshot) != expected:
            raise transfer_error(f"current candidate {name} key set invalid")
        return {key: snapshot[key] for key in snapshot_keys}

    def semantic_projection(decision: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in decision.items()
            if key not in {"as_of", "receipt_sha256"}
        }

    def compile_candidate(
        source: object,
        receiving: object,
        policy: object,
    ) -> dict[str, Any]:
        now = clock()
        decision = raw_compile(source, receiving, policy, as_of=now)
        # Deliberately NON-AUTHORITATIVE. There is no current-authority sealer
        # reachable from this function: compilation creates only a candidate.
        candidate_core = {
            "schema": candidate_schema,
            "authority_mode": candidate_mode,
            "evaluated_at_utc": decision["as_of"],
            "decision": decision,
        }
        candidate = dict(candidate_core)
        candidate["candidate_receipt_sha256"] = raw_canonical(candidate_core)
        return candidate

    def evaluate_fresh(candidate: object) -> tuple[dict[str, Any], dict[str, Any], str]:
        decision = validate_candidate(candidate)
        now = clock()
        rebuilt = raw_compile(
            plain_snapshot(decision["source"], "source"),
            plain_snapshot(decision["receiving"], "receiving"),
            decision["policy"],
            as_of=now,
        )
        if semantic_projection(rebuilt) != semantic_projection(decision):
            raise transfer_error(
                "current candidate is no longer current: decision semantics changed at process UTC"
            )
        return decision, rebuilt, now

    def verify_current(candidate: object) -> dict[str, Any]:
        _decision, rebuilt, now = evaluate_fresh(candidate)
        verification_core = {
            "schema": verify_schema,
            "authority_mode": authority_mode,
            "verified": True,
            "verified_at_utc": now,
            "decision_state": rebuilt["summary"]["state"],
            "candidate_receipt_sha256": candidate["candidate_receipt_sha256"],
            "current_decision_receipt_sha256": rebuilt["receipt_sha256"],
        }
        verification = dict(verification_core)
        verification["verification_receipt_sha256"] = raw_canonical(verification_core)
        return verification

    def render_current(candidate: object) -> str:
        # Rendering is itself a current-authority operation. It MUST cross the
        # fresh process-time gate rather than merely replay candidate integrity.
        _decision, rebuilt, now = evaluate_fresh(candidate)
        legacy = raw_render(rebuilt)
        prefix = [
            "# Current Verified Owner-Review Projection",
            "",
            f"- Verification schema: `{verify_schema}`",
            f"- Authority mode: `{authority_mode}`",
            f"- Verified at process UTC: `{now}`",
            f"- Candidate receipt: `{candidate['candidate_receipt_sha256']}`",
            f"- Current decision receipt: `{rebuilt['receipt_sha256']}`",
            "",
        ]
        return "\n".join(prefix) + legacy

    return compile_candidate, verify_current, render_current


compile_transfer, verify_report_current, render_markdown = _build_current_capabilities(
    _core,
    datetime_type=datetime,
    timezone_value=timezone.utc,
)

# Raw retained namespace and construction factory are not module API. Reflection
# can still inspect Python closure cells, so authority does not depend on hiding
# them: recovered explicit-time classification can only produce historical/raw
# decisions or candidate-shaped data; fresh verification/rendering owns current
# authority.
del _core
del _build_current_capabilities
del _load_private_core
del _install_snapshot_chronology


def _fd_fingerprint(st: object) -> tuple[int, int, int, int, int, int]:
    return (
        int(st.st_dev),
        int(st.st_ino),
        int(st.st_mode),
        int(st.st_size),
        int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))),
        int(getattr(st, "st_ctime_ns", int(st.st_ctime * 1_000_000_000))),
    )


def _read_bounded(path: str | os.PathLike[str]) -> bytes:
    """Read one retained regular-file generation with an in-read hard cap."""
    if not hasattr(os, "O_NOFOLLOW"):
        raise TransferError("secure no-follow input open is unavailable")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.EMLINK}:
            raise TransferError("input final symlink is forbidden") from None
        raise TransferError(
            f"unable to open input safely: {exc.strerror or exc}"
        ) from None
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise TransferError("input must be a regular file")
        if before.st_size > MAX_JSON_BYTES:
            raise TransferError("input exceeds byte limit")
        chunks: list[bytes] = []
        total = 0
        while True:
            remaining = MAX_JSON_BYTES + 1 - total
            if remaining <= 0:
                raise TransferError("input exceeds byte limit during read")
            chunk = os.read(fd, min(64 * 1024, remaining))
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_JSON_BYTES:
                raise TransferError("input exceeds byte limit during read")
            chunks.append(chunk)
        after = os.fstat(fd)
        if _fd_fingerprint(before) != _fd_fingerprint(after):
            raise TransferError("input generation changed during read")
        if total != after.st_size:
            raise TransferError("input size changed during read")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _build_cli(
    current_compile,
    current_verify,
    current_render,
    reader,
    loader,
    writer_bytes,
    writer_text,
    canonical_bytes,
    transfer_error,
    compile_input_keys,
):
    keys = frozenset(compile_input_keys)

    def compile_cli(args: argparse.Namespace) -> int:
        request = loader(reader(args.input))
        if type(request) is not dict or set(request) != set(keys):
            raise transfer_error("compile input key set is invalid")
        candidate = current_compile(
            request["source"], request["receiving"], request["policy"]
        )
        # Current Markdown independently verifies at fresh process time before
        # any bytes are written. If freshness crosses a boundary here, fail.
        markdown = current_render(candidate)
        writer_bytes(args.report, canonical_bytes(candidate))
        writer_text(args.markdown, markdown)
        print(
            json.dumps(
                {
                    "authority_mode": candidate["authority_mode"],
                    "state": candidate["decision"]["summary"]["state"],
                    "candidate_receipt_sha256": candidate["candidate_receipt_sha256"],
                },
                sort_keys=True,
            )
        )
        return 0

    def verify_cli(args: argparse.Namespace) -> int:
        candidate = loader(reader(args.report))
        result = current_verify(candidate)
        if args.markdown:
            actual = reader(args.markdown).decode("utf-8")
            expected = current_render(candidate)
            if actual != expected:
                raise transfer_error(
                    "Markdown projection mismatch or stale verification generation"
                )
        print(json.dumps(result, sort_keys=True))
        return 0

    def run(argv: list[str] | None = None) -> int:
        parser = argparse.ArgumentParser(
            description="Read-only cross-site clinical fill tech-transfer current evidence candidate compiler"
        )
        subs = parser.add_subparsers(dest="command", required=True)
        cp = subs.add_parser("compile")
        cp.add_argument("--input", required=True)
        cp.add_argument("--report", required=True)
        cp.add_argument("--markdown", required=True)
        cp.set_defaults(func=compile_cli)
        vp = subs.add_parser("verify")
        vp.add_argument("--report", required=True)
        vp.add_argument("--markdown")
        vp.set_defaults(func=verify_cli)
        args = parser.parse_args(argv)
        try:
            return args.func(args)
        except transfer_error as exc:
            parser.error(str(exc))
        return 2

    return run, compile_cli, verify_cli


main, _compile_cli, _verify_cli = _build_cli(
    compile_transfer,
    verify_report_current,
    render_markdown,
    _read_bounded,
    load_json_bytes,
    write_new_bytes,
    write_new_text,
    canonical_json_bytes,
    TransferError,
    _COMPILE_INPUT_KEYS,
)
del _build_cli
del _COMPILE_INPUT_KEYS

__all__ = [
    "TransferError",
    "CURRENT_CANDIDATE_SCHEMA",
    "CURRENT_VERIFY_SCHEMA",
    "CURRENT_CANDIDATE_MODE",
    "CURRENT_AUTHORITY_MODE",
    "compile_transfer",
    "verify_report_current",
    "render_markdown",
    "canonical_json_bytes",
    "canonical_sha256",
    "format_utc",
    "load_json_bytes",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
