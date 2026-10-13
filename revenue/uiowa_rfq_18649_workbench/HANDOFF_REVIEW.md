# Receipt-bound analyst handoff reconciliation

**Operation:** `uiowa-handoff-review-kestrel47-20260919`  
**Builder:** ZZ-KESTREL-47 / GPT-6 Astra Pro  
**Status:** Draft-review tooling; not University findings, adjudication, or approval.

This additive offline command compares the existing workbench's
`uiowa-rfq18649-analyst-handoff-draft/v1` exports against **one original parent-compiler
report**. It preserves every analyst note, exposes disagreements and incomplete review,
and produces both machine-readable and readable reviewer packets. It does not change
the browser, server, compiler, scoring, evidence, or commercial terms.

## Run the complete synthetic rehearsal

Use a full Commons checkout, Python 3.10 or newer, and no additional packages.
From this directory:

```sh
python handoff_review.py example /tmp/uiowa-handoff-rehearsal
python handoff_review.py compare /tmp/uiowa-handoff-rehearsal/report.json \
  --handoff analyst-a /tmp/uiowa-handoff-rehearsal/analyst-a.json \
  --handoff analyst-b /tmp/uiowa-handoff-rehearsal/analyst-b.json \
  --output /tmp/uiowa-review.json
python handoff_review.py compare /tmp/uiowa-handoff-rehearsal/report.json \
  --handoff analyst-a /tmp/uiowa-handoff-rehearsal/analyst-a.json \
  --handoff analyst-b /tmp/uiowa-handoff-rehearsal/analyst-b.json \
  --format markdown --output /tmp/uiowa-review.md
```

The example directory must not exist. Its six files are the original report,
two draft handoffs, JSON and Markdown reconciliation, and a synthetic-only notice.
The command compiles only the parent's checked-in `synthetic_packet.json` and
`synthetic_authority.json`; no fabricated report or substitute scoring engine is used.
Repeating into a different new directory produces the same file bytes.

The rehearsal contains one matching draft cell, one disposition disagreement,
one incomplete review, and nine entirely unreviewed cells. The disagreement retains
both “owner record not supplied” and “clarify the sample boundary first.” The tool
does not choose a winner. All examples and notes are fictional.

## Use actual local draft exports

Supply the exact original report JSON used for the browser inspection, and one to
twenty labeled handoff JSON files. Labels must be distinct ASCII identifiers of
1–64 characters (letters/digits followed by letters/digits/underscore/dot/hyphen).
Labels are locally assigned names, **not authenticated reviewer identities**.

An original report can be reproduced from unchanged candidate and authority inputs
with the parent's `compiler.py compile CANDIDATE AUTHORITY REPORT` command. The receipt
must match the browser export exactly. Different receipts require a new review;
this command does not migrate annotations between versions. Keep private inputs and
all resulting notes in an appropriate private working directory, never this public
repository. Do not include credentials in notes.

The browser's UI-only demo uses a placeholder receipt and is deliberately rejected.
A **real compiler report built from synthetic evidence is accepted**: a false
`synthetic_demo` flag means “not the UI placeholder,” not “authentic University data.”
The tool never establishes source authenticity.

## What is verified

The existing parent `verify_report_integrity` function checks the report receipt
and full semantic recompile. This module calls it without a trusted authority root.
It requires untrusted-inspection mode and false current/trusted-root authority.
Missing parent code or a failed verification is an error, never a hash-only fallback.

Every export must have the exact v1 fields, all twelve unique ESS/RIS/IAM × four-area
cells, matching compiler statuses, matching report receipt/mode/aggregate state,
and all seven authority flags as literal JSON `false` (not zero, null, or strings).
Notes retain their exact Unicode text and must fit the browser's 4,000 UTF-16-unit
limit. Only the four dispositions already exposed by `index.html` are accepted.

Input is bounded to 2 MiB per regular file, 64 nesting levels, and twenty handoffs.
UTF-8, finite JSON values and unique JSON member names are required. On POSIX systems
supporting `O_NOFOLLOW`, a final-component input symlink is rejected; this is not a
sandbox for attacker-controlled directory trees. Outputs use exclusive creation
and mode 0600 on POSIX. Existing files are never overwritten. Use a private, stable
local output directory; a disk failure can leave a partial newly created file or
partially populated example directory that must be inspected before retrying.

No network requests, automatic edits, appointments, provider calls, or background
processes occur. The command returns 0 for a valid draft comparison even when
review issues remain, and 2 for input, verification, or file-operation failures.
Exit 0 is **not** an assessment pass or approval. Standard output contains only a
status and receipt; note content is written only to the requested output file.

## How the review queue works

| Reason | Meaning | Required interpretation |
|---|---|---|
| `ALL_UNREVIEWED` | No input has a non-default disposition. | Missing review, not agreement or a low maturity score. |
| `INCOMPLETE_REVIEW` | At least one input is still unreviewed. | Keep remaining review visible. |
| `DISPOSITION_DISAGREEMENT` | At least two non-default dispositions differ. | Read both accounts; the command does not adjudicate. |
| `NOTE_VARIATION_REQUIRES_REVIEW` | Literal note strings differ. | Wording variation is not proof of contradictory evidence. |
| `SINGLE_DRAFT_ENTRY` | One distinct normalized handoff content has a non-default disposition, even under multiple labels. | This is not independent corroboration. |
| `MATCHING_DRAFT_ENTRIES` | At least two distinct handoff contents agree on this cell: dispositions and literal notes match and are non-default. | Matching drafts are not consensus, acceptance, or authority. |

Reasons can coexist. Counts are per reason, not a partition or a score; their sum can
exceed twelve. The queue includes every cell except a matching-draft cell. The full
matrix always preserves all twelve cells, their original compiler status, source IDs,
source-record hashes, compiler reasons, and every labeled analyst entry.

Exports with identical normalized content are grouped. The normalized hash ignores
JSON object order and cell order, but preserves exact note strings and dispositions.
It is not a raw-file hash. Different labels on the same content do not establish
independent reviews; the output reports both input count and distinct content count.
Reimporting an unchanged saved handoff under additional labels does not remove cells
from the review queue. All original labels and notes still appear in the full matrix.
Distinct contents are not proof of independent people; reviewer identity stays false.

The reconciliation receipt is SHA-256 over compact UTF-8 JSON with sorted object keys,
no non-finite numbers, and the `reconciliation_sha256` member omitted. It detects
accidental content changes when compared with an independently retained value; it is
not a signature or a new authority root. Reviewer identity and source authenticity
remain explicitly false, as do buyer, prime, submission, signature, payment, revenue,
and current-evidence-review authority.

## Integration boundaries

This is complementary to browser note restoration, evidence-revision comparison,
report-bundle packaging, and the larger consolidated-review work order. It compares
multiple drafts **at the same report version**. It does not implement a full
comment-to-finding decision register, change report versions, resolve disagreements,
or claim completion of the entire UIOWA-039 work order.

Consume `reconcile(report, [(label, handoff), ...])` for JSON, and
`render_markdown(result)` for a readable packet. All inputs stay unchanged. The
Markdown renderer expects a result returned by `reconcile`, not an arbitrary imported
comparison; it presents notes as literal JSON rather than executable HTML or links.

## Acceptance

```sh
python -m py_compile handoff_review.py test_handoff_review.py test_handoff_review_duplicates.py
UIOWA_REQUIRE_PARENT=1 python -m unittest -v test_handoff_review.py test_handoff_review_duplicates.py test_handoff_parent_contract.py
UIOWA_REQUIRE_PARENT=1 python -O -m unittest -v test_handoff_review.py test_handoff_review_duplicates.py test_handoff_parent_contract.py
```

The tests separate explicit stub-based unit checks from two real parent integration
tests. In an isolated folder the parent class is visibly skipped; such a run is not
full integration evidence. `UIOWA_REQUIRE_PARENT=1` converts missing-parent setup into
failure. Full integration generates the entire rehearsal twice, compares all bytes,
checks expected review outcomes, and confirms that an altered parent report fails.

Contract sources: sibling `app.js` (`exportDraft`), `index.html` (dispositions and note
length), and `../uiowa_rfq_18649_workshare/compiler.py` / `workshare_verify.py` (semantic
integrity). No contract changes are made to those files.
