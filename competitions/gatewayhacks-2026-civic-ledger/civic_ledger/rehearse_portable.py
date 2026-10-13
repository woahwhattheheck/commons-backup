"""Create six fictional meetings and exercise the portable handoff CLI.

Run from the component root with ``python -m civic_ledger.rehearse_portable
--output-dir NEW_DIRECTORY``. This is an operator rehearsal, not a replacement
compiler or an independent source-authenticity check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .core import DocumentSnapshot, Ledger


AS_OF = "2026-09-13T16:30:00Z"
AGENDA = """Fictional Riverton agenda — no real public records
[ITEM 4.2] Bibliothèque accessibilité — north entrance
Owner: Public Works
Deadline: 2026-10-22
Action: Publish the revised route map.
[ITEM 7.1] Evening reading room
"""
ADDENDUM = """Fictional Riverton addendum — no real public records
[ITEM 4.2] Bibliothèque accessibilité — north entrance
Assigned: Équipe accessibilité
Due: 2026-11-05
Action: Publish the revised route map in français & English.
"""
MINUTES_APPROVED = """Fictional Riverton minutes — no real public records
[ITEM 4.2] Bibliothèque accessibilité — north entrance
Decision: APPROVED
"""
MINUTES_DENIED = """Fictional competing minutes — no real public records
[ITEM 4.2] Bibliothèque accessibilité — north entrance
Decision: DENIED
"""
MINUTES_NO_DECISION = """Fictional Riverton minutes — no real public records
[ITEM 4.2] Bibliothèque accessibilité — north entrance
The fictional discussion note supplies no explicit Decision field.
"""
CONTINUED = """Fictional Riverton minutes — no real public records
[ITEM 8.3] Café culturel — réunion publique
Decision: CONTINUED
"""


def case_definitions() -> list[dict[str, Any]]:
    """Return editable examples and their intended existing-core observations."""
    agenda = ("agenda-v1", "agenda", "2026-09-09T14:00:00Z", AGENDA)
    addendum = ("addendum-v1", "addendum", "2026-09-10T14:00:00Z", ADDENDUM)
    approved = ("minutes-v1", "minutes", "2026-09-12T20:00:00Z", MINUTES_APPROVED)
    denied = ("minutes-competing", "minutes", "2026-09-12T21:00:00Z", MINUTES_DENIED)
    base = [agenda, addendum, approved]
    return [
        {
            "slug": "01-agenda-only", "title": "An agenda is a proposal",
            "snapshots": [agenda], "as_of": AS_OF, "freshness": "CURRENT",
            "expected_states": {"4.2": "PROPOSED", "7.1": "PROPOSED"},
            "question": "Is an explicit minutes decision available?",
            "interpretation": "Both items remain PROPOSED. An owner or deadline is not a decision.",
        },
        {
            "slug": "02-decision-absent", "title": "Minutes do not imply a decision",
            "snapshots": [agenda, ("minutes-v1", "minutes", "2026-09-12T20:00:00Z", MINUTES_NO_DECISION)],
            "as_of": AS_OF, "freshness": "CURRENT",
            "expected_states": {"4.2": "UNKNOWN_DECISION", "7.1": "UNKNOWN_DECISION"},
            "question": "Which explicit decision, if any, is recorded for each item?",
            "interpretation": "The core labels all undecided items UNKNOWN_DECISION when any minutes snapshot exists. Item 7.1 is absent from these minutes; its state does not prove it was discussed.",
        },
        {
            "slug": "03-owner-deadline-change", "title": "A revised assignment keeps its history",
            "snapshots": base, "as_of": AS_OF, "freshness": "CURRENT",
            "expected_states": {"4.2": "DECIDED_APPROVED", "7.1": "UNKNOWN_DECISION"},
            "question": "Which source supplies the current owner and deadline, and what did it replace?",
            "interpretation": "The later addendum supplies Équipe accessibilité and 2026-11-05. Public Works and 2026-10-22 remain in changes. Approval comes from the explicit minutes decision.",
        },
        {
            "slug": "04-competing-decisions", "title": "A later conflicting record does not settle the dispute",
            "snapshots": [*base, denied], "as_of": AS_OF, "freshness": "CURRENT",
            "expected_states": {"4.2": "HOLD_CONFLICT", "7.1": "UNKNOWN_DECISION"},
            "question": "What source can explain the conflicting APPROVED and DENIED records?",
            "interpretation": "Item 4.2 has no single decision. Both competing minutes citations survive; the later DENIED record does not erase APPROVED.",
        },
        {
            "slug": "05-stale-assessment", "title": "Age changes the snapshot label, not the recorded decision",
            "snapshots": base, "as_of": "2027-01-01T16:30:00Z", "freshness": "STALE_SOURCE",
            "expected_states": {"4.2": "DECIDED_APPROVED", "7.1": "UNKNOWN_DECISION"},
            "question": "Are newer records available after the latest retained observation?",
            "interpretation": "With the same sources and a 90-day age limit, the later assessment is STALE_SOURCE. The recorded approval remains; freshness does not establish present-day legal effect or source completeness.",
        },
        {
            "slug": "06-continued-unassigned", "title": "A known decision can have unknown follow-through",
            "snapshots": [("minutes-v1", "minutes", "2026-09-12T20:00:00Z", CONTINUED)],
            "as_of": AS_OF, "freshness": "CURRENT",
            "expected_states": {"8.3": "DECIDED_CONTINUED"},
            "question": "Does any retained source identify an owner, deadline or action?",
            "interpretation": "CONTINUED is explicit. Owner, deadline and action remain null. Accented text must survive the source view and downloadable artifacts.",
        },
    ]


def _write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        handle.write("\n")


def _source_identities(component: Path) -> dict[str, dict[str, Any]]:
    result = {}
    for name in ("__init__.py", "core.py", "handoff.py", "rehearse_portable.py"):
        path = component / "civic_ledger" / name
        data = path.read_bytes()
        result[f"civic_ledger/{name}"] = {
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "git_blob": hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest(),
        }
    return result


def _observe(compiled: dict[str, Any]) -> dict[str, Any]:
    return {
        "meeting_id": compiled["meeting_id"], "as_of": compiled["as_of"],
        "freshness": compiled["freshness"], "compile_sha256": compiled["compile_sha256"],
        "documents": len(compiled["documents"]),
        "items": compiled["items"],
        "authority": compiled["authority"],
    }


def rehearse(output_dir: Path) -> dict[str, Any]:
    component = Path(__file__).resolve().parents[1]
    before = _source_identities(component)
    output_dir = output_dir.absolute()
    output_dir.mkdir(parents=False, exist_ok=False)
    records = []
    for case in case_definitions():
        case_dir = output_dir / case["slug"]
        case_dir.mkdir()
        workspace = case_dir / "input-workspace.json"
        ledger = Ledger("fictional-riverton-2026-09-12")
        for doc_id, kind, observed_at, text in case["snapshots"]:
            ledger.add(DocumentSnapshot.create(
                meeting_id=ledger.meeting_id, doc_id=doc_id, kind=kind,
                source_url=f"https://civic.example/fictional/{doc_id}",
                observed_at=observed_at, text=text,
            ))
        _write_json(workspace, ledger.to_dict())
        commands = []
        handoff = case_dir / "handoff"
        python = [sys.executable, "-B"]
        if sys.flags.optimize:
            python.append("-O" if sys.flags.optimize == 1 else "-OO")
        invocations = [
            [*python, "-m", "civic_ledger.handoff", "export", "--workspace", str(workspace),
             "--output-dir", str(handoff), "--as-of", case["as_of"],
             "--max-source-age-days", "90", "--classification", "synthetic"],
            [*python, "-m", "civic_ledger.handoff", "verify", "--output-dir", str(handoff)],
        ]
        for argv in invocations:
            run = subprocess.run(argv, cwd=component, capture_output=True, text=True, encoding="utf-8", check=False)
            commands.append({"argv": argv, "returncode": run.returncode, "stdout": run.stdout, "stderr": run.stderr})
            _write_json(case_dir / f"command-{len(commands)}.json", commands[-1])
            if run.returncode != 0:
                raise RuntimeError(f"{case['slug']}: command failed; retained command-{len(commands)}.json")
        compiled = json.loads((handoff / "ledger.json").read_text("utf-8"))
        actual_states = {row["item_id"]: row["state"] for row in compiled["items"]}
        if actual_states != case["expected_states"] or compiled["freshness"] != case["freshness"]:
            raise RuntimeError(f"{case['slug']}: output differs from the described existing-core observation")
        actual = _observe(compiled)
        record = {"case": case["slug"], "title": case["title"],
                  "interpretation": case["interpretation"], "next_question": case["question"],
                  "reader": f"{case['slug']}/handoff/reader.html", "observed": actual}
        _write_json(case_dir / "OBSERVED.json", record)
        records.append(record)
    after = _source_identities(component)
    if after != before:
        raise RuntimeError("Source files changed during the rehearsal; case artifacts remain but no completed INDEX is written")
    index = {
        "schema": "civic-portable-rehearsal/v1", "classification": "synthetic",
        "python_version": sys.version, "driver_optimization": sys.flags.optimize,
        "source_files_before_and_after": before,
        "source_identity_scope": "Disk bytes were equal before and after fresh CLI subprocesses; this is not interpreter attestation or source authenticity.",
        "browser_execution": "NOT_PERFORMED_BY_THIS_REHEARSAL",
        "cases": records,
    }
    _write_json(output_dir / "INDEX.json", index)
    lines = ["# Six fictional Civic Action Ledger handoffs", "",
             "These observations came from actual export and verify CLI calls. No real records or browser execution are claimed.", "",
             "| Case | Freshness at assessment | Observed item states | Open reader |", "|---|---|---|---|"]
    for record in records:
        observation = record["observed"]
        states = "; ".join(f"{row['item_id']}: {row['state']}" for row in observation["items"])
        lines.append(f"| {record['title']} | {observation['freshness']} | {states} | [Open]({record['reader']}) |")
    for record in records:
        lines.extend(["", f"## {record['title']}", "", record["interpretation"], "", f"Next question: {record['next_question']}"])
    lines.extend(["", "Full inputs, canonical exports, retained source text and both literal CLI outcomes are in each case directory. INDEX.json retains source-file identities and full observed item records.", ""])
    with (output_dir / "INDEX.md").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))
    return index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="New directory with an existing parent")
    args = parser.parse_args(argv)
    try:
        result = rehearse(args.output_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Rehearsal incomplete: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "cases": len(result["cases"]), "index": str(args.output_dir / "INDEX.md")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
