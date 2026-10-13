"""Generate a repeatable, entirely synthetic consolidated-review import.

No source data is downloaded. A new output directory is required.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import io
import json

from comment_import import canonical, render_report, stage_comments


def synthetic_inputs():
    columns = ["comment_id", "reviewer_role", "comment_text", "finding_id", "report_version",
               "finding_namespace", "comment_kind", "proposed_edit", "context_label", "extra_note"]
    def comment(cid, text, finding="FND-SYN-01", revision="draft-synthetic-1", namespace="assessment", **extra):
        r = dict.fromkeys(columns, "")
        r.update(comment_id=cid, reviewer_role="Fictional practitioner role", comment_text=text,
                 finding_id=finding, report_version=revision, finding_namespace=namespace,
                 comment_kind="wording", context_label="SYNTHETIC — NOT UNIVERSITY EVIDENCE")
        r.update(extra)
        return r
    rows = [
        comment("REV-SYN-01", 'The word "always" exceeds this example.\r\nPlease retain the exception — it matters.',
                proposed_edit="In the supplied example, review preceded release.", extra_note="Keep exact CRLF."),
        comment("REV-SYN-02", "Please attach the actual support record.", finding="FND-SYN-02", comment_kind="evidence"),
        comment("REV-SYN-03", "Which team's finding is this?", namespace=""),
        comment("REV-SYN-04", "This review was written against the old report.", revision="draft-synthetic-0"),
        comment("REV-SYN-05", "No matching finding was supplied.", finding="FND-SYN-99"),
        comment("REV-SYN-06", "Keep both interpretations."),
        comment("REV-SYN-06", "Replace that comment without recording the change."),
        comment("", "Do not drop this unnumbered comment.", extra_note="Original source needs an ID."),
    ]
    rows.insert(2, dict(rows[0]))  # Repeated spreadsheet row, not an independent opinion.
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\r\n")
    writer.writeheader(); writer.writerows(rows)
    catalog = {"context_label": "SYNTHETIC — NOT UNIVERSITY EVIDENCE", "findings": [
        {"finding_id": "FND-SYN-01", "namespace": "assessment", "report_version": "draft-synthetic-1",
         "locator": "synthetic-report.json#/findings/0"},
        {"finding_id": "FND-SYN-02", "namespace": "assessment", "report_version": "draft-synthetic-1",
         "locator": "synthetic-report.json#/findings/1"},
        {"finding_id": "FND-SYN-01", "namespace": "alternate-assessment", "report_version": "draft-synthetic-1",
         "locator": "synthetic-alternate-report.json#/findings/0"},
    ]}
    return stream.getvalue().encode("utf-8"), catalog


def run(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    raw, catalog = synthetic_inputs()
    first = stage_comments(raw, "synthetic-round-one", "comments.csv", catalog)
    replay = stage_comments(raw, "synthetic-round-one", "comments.csv", catalog, first["state"])
    if canonical(first) != canonical(replay):
        raise RuntimeError("identical reimport changed the result")
    expected = dict(input_records=9, unique_comments=6, ready=2, unresolved=4, unkeyed_rows=1)
    if first["summary"] != expected:
        raise RuntimeError(f"unexpected sample: {first['summary']}")
    outputs = {
        "comments.csv": raw,
        "catalog.json": (json.dumps(catalog, ensure_ascii=False, indent=2) + "\n").encode(),
        "import-result.json": canonical(first) + b"\n",
        "import-report.md": ("SYNTHETIC DEMONSTRATION — NOT UNIVERSITY FINDINGS\n\n" + render_report(first)).encode(),
    }
    for name, data in outputs.items():
        (out / name).write_bytes(data)
    receipt = {"schema": "uiowa-review-import-rehearsal/v1", "context_label": "SYNTHETIC",
               "summary": first["summary"], "identical_reimport": True,
               "files_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in outputs.items()},
               "integration": "CSV staging only; native tracker bridge is exercised separately."}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.out), indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"rehearsal error: {exc}\n")
