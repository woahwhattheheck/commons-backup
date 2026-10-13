#!/usr/bin/env python3
"""Execute the real untrusted compiler and recipient transport on pinned fiction.

This is a local operator rehearsal, not a browser or an authority service.
A new output directory is required; prior runs and source fixtures are retained.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

from . import bundle

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "uiowa_rfq_18649_workshare"
MODULES = (
    "workshare_constants.py", "workshare_core.py", "workshare_contract.py",
    "workshare_candidate.py", "workshare_authority.py", "workshare_assessment.py",
    "workshare_compile.py", "workshare_verify.py",
)
FIXTURES = {
    "synthetic_packet.json": "92e38c01c5d45fc7e0172387fce037f611042f26",
    "synthetic_authority.json": "1d58638c067b35dbdc210365ac3f30d6e72c9548",
}
COUNTS = {"HOLD_CONFLICT": 1, "HOLD_MISSING_EVIDENCE": 1,
          "HOLD_STALE_EVIDENCE": 1, "UNTRUSTED_EVIDENCE_CONSISTENT": 9}
WORKER = '''import json,sys
sys.path.insert(0,sys.argv[1])
from workshare_compile import compile_untrusted_inspection
from workshare_verify import verify_report_integrity
from workshare_core import canonical_json_bytes,loads_strict
payload=loads_strict(sys.stdin.buffer.read().decode("utf-8"))
authority=payload["authority"]
report=compile_untrusted_inspection(payload["candidate"],authority,
    now=max(row["observed_at"] for row in authority["sources"]))
verification=verify_report_integrity(report)
sys.stdout.buffer.write(canonical_json_bytes({
    "report_utf8":canonical_json_bytes(report).decode("utf-8"),
    "verification":verification}))
'''


class RehearsalError(ValueError):
    """An actual failed acceptance step, never a successful partial rehearsal."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RehearsalError(message)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def python_command() -> list[str]:
    return [sys.executable, "-B"] + (["-" + "O" * sys.flags.optimize] if sys.flags.optimize else [])


def execute(args: list[str], *, cwd: Path, stdin: bytes | None = None,
            expected: int = 0) -> dict:
    result = subprocess.run(python_command() + args, input=stdin, cwd=cwd,
                            capture_output=True, timeout=20)
    require(result.returncode == expected,
            f"Child exit {result.returncode}; expected {expected}: "
            + result.stderr.decode("utf-8", errors="replace")[:1500])
    stream = result.stdout if expected == 0 else result.stderr
    return bundle.parse_object(stream, "child receipt")


def snapshot() -> tuple[dict[str, bytes], dict[str, str]]:
    inputs = {name: bundle.read_bounded(PARENT / "fixtures" / name, bundle.MAX_JSON_BYTES)
              for name in FIXTURES}
    for name, raw in inputs.items():
        require(git_blob(raw) == FIXTURES[name], f"Pinned synthetic fixture changed: {name}")
    sources = {name: git_blob((PARENT / name).read_bytes()) for name in MODULES}
    for name in ("bundle.py", "compiler_rehearsal.py"):
        sources["delivery_bundle/" + name] = git_blob((HERE / name).read_bytes())
    return inputs, sources


def rehearsal(output: Path) -> dict:
    """Exercise actual compiler functions and pack/verify CLIs, writing fiction only."""
    inputs, sources = snapshot()
    # Refuse an existing path, including a symlink or an old empty run directory.
    output.mkdir(parents=False, exist_ok=False)
    output = output.resolve()
    try:
        sender, recipient = output / "sender", output / "recipient"
        sender.mkdir()
        recipient.mkdir()
        worker_input = bundle.canonical({
            "candidate": bundle.parse_object(inputs["synthetic_packet.json"], "candidate"),
            "authority": bundle.parse_object(inputs["synthetic_authority.json"], "authority"),
        })
        generated = execute(["-c", WORKER, str(PARENT)], cwd=sender, stdin=worker_input)
        require(isinstance(generated.get("report_utf8"), str), "Parent report payload must be text")
        raw_report = generated["report_utf8"].encode("utf-8")
        report = bundle.parse_object(raw_report, "generated report")
        semantic = generated["verification"]
        require(isinstance(semantic, dict), "Parent verification must be an object")
        require(semantic["integrity_valid"] is True and semantic["semantic_recompile_valid"] is True,
                "Parent semantic verification did not pass")
        require(semantic["trusted_authority_root_verified"] is False
                and semantic["current_authority_verified"] is False, "Unexpected parent authority")
        require(report["status_counts"] == COUNTS, "Synthetic evidence holds changed")
        require(report["aggregate_state"] == "HOLD_TRUSTED_AUTHORITY_REQUIRED", "Aggregate changed")
        require(report["evaluated_at"] == "2026-08-26T12:00:00Z", "Fixture inspection instant changed")
        require(all(cell["maturity"] is None and cell["confidence_bp"] is None
                    for cell in report["assessment_matrix"]), "Untrusted report acquired a score")
        handoff = {
            "schema": bundle.HANDOFF_SCHEMA, "status": "DRAFT_NON_AUTHORITATIVE",
            "report_receipt_sha256": report["receipt_sha256"], "report_mode": report["mode"],
            "aggregate_state": report["aggregate_state"], "synthetic_demo": False,
            "authority": {key: False for key in bundle.AUTHORITY_KEYS},
            "cell_notes": [{"group": cell["group"], "dimension": cell["dimension"],
                            "compiler_status": cell["status"], "disposition": "UNREVIEWED",
                            "analyst_note": "SYNTHETIC REHEARSAL: automatically generated draft; "
                                            "no analyst review or University finding."}
                           for cell in report["assessment_matrix"]],
        }
        raw_handoff = bundle.canonical(handoff)
        (sender / "report.json").write_bytes(raw_report)
        (sender / "handoff.json").write_bytes(raw_handoff)
        pack_args = [str(HERE / "bundle.py"), "pack", "--report", "report.json",
                     "--handoff", "handoff.json", "--output", "draft.zip"]
        sent = execute(pack_args, cwd=sender)
        archive = (sender / "draft.zip").read_bytes()
        digest = sent["archive_sha256"]  # Retained from sender, not read from recipient ZIP.
        require(digest == bundle.sha256(archive), "Sender archive digest disagrees")
        (recipient / "draft.zip").write_bytes(archive)
        verify_args = [str(HERE / "bundle.py"), "verify", "draft.zip", "--expected-sha256", digest]
        received = execute(verify_args, cwd=recipient)
        require(received["independent_digest_match"] is True, "Retained sender digest did not match")
        require(received["parent_compiler_receipt_recomputed"] is False, "Transport scope changed")
        require(all(value is False for value in received["authority"].values()), "Transport authority changed")
        with zipfile.ZipFile(io.BytesIO(archive)) as stored:
            require(stored.read("report.json") == raw_report, "Compiler report bytes changed")
            require(stored.read("handoff.json") == raw_handoff, "Draft bytes changed")
        require(bundle.build_bundle(raw_report, raw_handoff) == archive, "Archive rebuild differs")
        duplicate = execute(pack_args, cwd=sender, expected=2)
        require(duplicate.get("error") == "FILE_IO", "Existing archive was not refused")
        require((sender / "draft.zip").read_bytes() == archive, "Prior archive was changed")
        (recipient / "tampered.zip").write_bytes(archive + b"altered")
        wrong = execute([str(HERE / "bundle.py"), "verify", "tampered.zip",
                         "--expected-sha256", digest], cwd=recipient, expected=2)
        require(wrong.get("error") == "ARCHIVE_DIGEST", "Changed recipient bytes were not rejected")
        require(snapshot() == (inputs, sources), "Source files changed during the rehearsal")
        receipt = {
            "status": "SYNTHETIC_COMPILER_TRANSPORT_REHEARSAL_PASSED",
            "synthetic_source_fixtures": True, "draft_notes_automatically_generated": True,
            "browser_import_export_executed": False, "parent_public_cli_executed": False,
            "parent_entrypoint": "workshare_compile.compile_untrusted_inspection",
            "parent_semantic_verifier": "workshare_verify.verify_report_integrity",
            "parent_verification": semantic, "evaluated_at": report["evaluated_at"],
            "status_counts": report["status_counts"], "aggregate_state": report["aggregate_state"],
            "authority": received["authority"], "archive_sha256": digest,
            "report_bytes_sha256": bundle.sha256(raw_report),
            "handoff_bytes_sha256": bundle.sha256(raw_handoff),
            "exact_payload_bytes_preserved": True, "deterministic_archive_rebuilt": True,
            "existing_archive_refused_and_preserved": True, "changed_recipient_archive_rejected": True,
            "fixture_git_blobs": FIXTURES, "source_git_blobs": sources,
            "source_files_unchanged": True, "retained_sender_digest_checked": True,
            "independent_external_channel_exercised": False,
            "python_version": sys.version.split()[0], "optimization_level": sys.flags.optimize,
        }
        pending = output / "RECEIPT.pending"
        with pending.open("xb") as handle:
            handle.write(bundle.canonical(receipt))
        pending.rename(output / "RECEIPT.json")
        return receipt
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        # Publish the successful receipt last; leave any incomplete staging file for diagnosis.
        failure = {"status": "REHEARSAL_FAILED", "error": type(exc).__name__, "message": str(exc)}
        try:
            with (output / "FAILURE.json").open("xb") as handle:
                handle.write(bundle.canonical(failure))
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="A new directory in a private working area")
    args = parser.parse_args(argv)
    try:
        print(bundle.canonical(rehearsal(args.output)).decode("utf-8"), end="")
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "REHEARSAL_FAILED", "error": type(exc).__name__,
                          "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
