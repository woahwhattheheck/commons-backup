# UIOWA-089 — searchable evidence discussion kit

Ask a leadership or practitioner question, follow an exact source record, and see
what is missing before using the answer. This offline preparation tool composes
the existing local evidence search, workshare report validator and recommendation
register. It assigns no new assessment rating, priority or authority.

The delivered example is wholly synthetic. It contains **27 cards and 63 source
citations**: three traceability findings, twelve assessment cells, six illustrative
register findings, five recommendations and one effort summary. Open
`examples/discussion.html` directly in a browser. Its search and local source links
work without a server or network. The complete `examples/` directory is portable;
keep its `inputs/` snapshots with the exports.

## Run

Python 3.10+ and the standard library, from the repository root:

```sh
python revenue/uiowa_rfq_18649_discussion/discussion.py verify revenue/uiowa_rfq_18649_discussion/examples
python revenue/uiowa_rfq_18649_discussion/discussion.py query revenue/uiowa_rfq_18649_discussion/examples "RIS security disagreement" --limit 1
python revenue/uiowa_rfq_18649_discussion/discussion.py show revenue/uiowa_rfq_18649_discussion/examples finding:F-001
python revenue/uiowa_rfq_18649_discussion/discussion.py show revenue/uiowa_rfq_18649_discussion/examples recommendation:REC-SYN-03
```

Build another export using the existing public compiler. Both destinations must
be new. The defaults use the existing synthetic search manifest and recommendation
register; pass `--manifest` and `--register` to select other explicitly synthetic
preparation inputs.

```sh
python revenue/uiowa_rfq_18649_workshare/compiler.py compile \
  revenue/uiowa_rfq_18649_workshare/fixtures/synthetic_packet.json \
  revenue/uiowa_rfq_18649_workshare/fixtures/synthetic_authority.json \
  /tmp/discussion-report.json
python revenue/uiowa_rfq_18649_discussion/discussion.py build \
  --report /tmp/discussion-report.json --out /tmp/discussion-kit
```

`build` writes `discussion.json`, `discussion.md`, `discussion.html` and exact input
snapshots. `verify`, `query` and `show` re-run the canonical source checks, semantic
report validation and register normalization, then compare the regenerated data
and both rendered exports with the saved bundle. They refuse changed or stale
bundles rather than answering from an old derived index. Exports are deterministic
for the same bytes and component versions; no current clock enters the result.

Exit codes: 0 for a successful export, integrity check or matching card; 1 for no
matching card; 2 for malformed, altered or stale input, changed output, or an I/O
error. Successful integrity checking does not mean current evidence or approval.
Inputs and the derived JSON are limited to 2 MiB each. Use an operator-controlled
output directory; publication is exclusive but not a transactional directory swap.
Partial output is retained after an I/O failure.

## A second operator's route

1. Search `RIS security disagreement`. The first CLI match is
   `cell:RIS:security`, carrying the compiler's `HOLD_CONFLICT`. Expand its two
   authority citations to read the differing claims and native source values.
   Neither a mean maturity nor a winning account is manufactured.
2. Open `finding:F-001` for the ESS strength. Its statement, limitation and three
   evidence observations retain the source CSV's physical line locators. The
   exact excerpt is the native field value; JSON record displays are normalized
   views, while the linked snapshot is the exact original file bytes.
3. Open `recommendation:REC-SYN-03`. Effort, owner, maturity step and phase remain
   null/UNKNOWN. Follow its prerequisite `REC-SYN-01` or its register finding.
   `planning:effort` retains the known 6–12 person-day subtotal with an UNKNOWN
   complete total. The explicitly assumed zero for `REC-SYN-04` stays zero.
4. Open `cell:IAM:deployment` for stale evidence and `cell:ESS:ai_readiness` for
   missing evidence. These are statuses at the report's embedded evaluation time,
   not a new currentness determination.

The traceability findings (`F-001` etc.) and recommendation sample findings
(`F-SYN-01` etc.) are different fictional populations. They are not silently
joined by similar wording or group. A traceability finding links to a recommendation
only when its ID and statement match the register's finding exactly; otherwise
`NO_EXACT_RECOMMENDATION_MAPPING` remains visible. Register placeholders such as
`SYNTHETIC-ILLUSTRATION` are unresolved evidence references. Proposed recommendations
are still navigable through their own native findings and prerequisites.

## Component and field mapping

| Canonical component | Native input | Discussion use |
| --- | --- | --- |
| `uiowa_rfq_18649_local_search` | Verified manifest, native IDs, original fields, locators, linked IDs | Exact excerpts, missing-link diagnostics, canonical lexical CLI ranking |
| `uiowa_rfq_18649_workshare` | `assessment_matrix`, `evidence_authority.sources`, `evaluated_at`, receipt | Semantic integrity check; retain status/reason/source IDs; no trusted-root input |
| `uiowa_rfq_18649_recommendation_register` | Findings, recommendations, null planning fields, dependencies | Native recommendation navigation, existing effort summary and roadmap projection |
| `uiowa_rfq_18649_workbench` | Public inspection report from its inspection workflow | Save the report object and pass it as `--report`; this tool does not import a draft wrapper or modify the workbench |

CLI search uses the retained local-search ranking; a matching card is navigation,
not a free-form generated answer. HTML search uses all entered words to filter
visible cards and cited records. Clicking a related-card link clears the filter
so the destination remains visible. There are no external links in generated
reader navigation. JSON contains the original records, SHA-256 file bindings,
Git blob identifiers, the retained immutable source manifest and local snapshots.
Digest consistency is not publisher authentication. Underlying fictional documents
not delivered by the canonical packet remain explicitly absent.

## Lineage and execution

Work order #16135 requested this missing discussion surface. The original
`swarm-zz/uiowa-089-halyard314-discussion` branch remained at its starting snapshot;
there was no implementation to recover. This implementation reuses the existing
search, compiler and register owners' code without changing those components.

The public compiler's existing synthetic inputs produced receipt
`3b58382daa78e4c152ff87111e17322bc6f86fe0d92abc4cf69412ee8bb11530` and
`HOLD_TRUSTED_AUTHORITY_REQUIRED`. The delivered kit was built and verified against
that report. Real CLI retrieval returned the conflict card and its two source
claims; the unknown planning fields and separate finding populations were retained.
No new test suite or fixture population was created. Browser execution is not
claimed. The existing synthetic component inputs are copied unchanged into the
portable output, not replaced by a new evidence corpus.

No real University finding, outreach, meeting, submission, purchase, commercial
commitment, invoice, payment or revenue is represented or performed.
