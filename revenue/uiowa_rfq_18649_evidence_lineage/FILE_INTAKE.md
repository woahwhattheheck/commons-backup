# Reconcile two file collections from CSV registers

`reconcile_files.py` turns explicit CSV evidence registers and local source files
into one complete offline review bundle. It calls the existing `lineage.snapshot`,
`lineage.compare` and `lineage.markdown` functions, not a second lineage engine.
Python 3.10+, standard library only. Run from this directory in a cloud workspace
or another approved evidence-processing environment.

```sh
python reconcile_files.py \
  --before-csv /evidence/before.csv --before-root /evidence/before \
  --before-id september-original \
  --after-csv /evidence/after.csv --after-root /evidence/after \
  --after-id september-revised \
  --findings-csv /evidence/citations.csv \
  --output /evidence/reconciliation-01
```

The output parent must exist; the final directory must not. Open `review.html`
directly: no server, JavaScript, dependency installation or external request is
needed. It shows changes, original citations, supplied and missing successors,
absent records, duplicate byte groups and anomalies. The full original report is
also embedded in an expandable section. JSON/Markdown links work when the six
files stay together. Moving only the HTML retains the embedded report, but its
relative download links no longer work.

**Private is the default.** The bundle contains register metadata and findings,
not source-file bytes. Keep it on your approved evidence surface, not public
GitHub or a public demo. `--data-kind synthetic` is only for fictional material;
classification is supplied by the operator, not authenticated. On systems that
honor POSIX modes, the new directory is owner-only and files are owner-readable
and writable. Platform ACLs and the surrounding storage policy still matter.

## Source register columns

Both CSVs require exactly named columns:

```csv
record_id,document_id,version,title,location
SUPPORT-1,SUPPORT-HANDOFF,v1,Support handoff notes,support.txt
```

All five values are required. IDs and version labels are preserved literally,
including leading zeros. A document ID declares identity; the program never
infers it from filenames, dates, titles or content. `location` is a path relative
to that side's root; binary documents are supported without extraction.
A header-only register explicitly supplies an empty collection.

Optional columns:

| Column | Meaning |
| --- | --- |
| `sha256` | An expected lowercase SHA-256; blank means calculate it. A supplied mismatch fails. |
| `supersedes_record_id`, `supersedes_sha256` | One explicit predecessor, supplied together. Never inferred from the version label. |
| `metadata.owner_role`, `metadata.source_context`, or another `metadata.NAME` | Retained text metadata, including empty values. These are assertions, not authenticated facts. |
| `metadata_json` | Optional JSON object for existing structured metadata. Duplicate keys, non-finite constants and collisions with `metadata.NAME` fail. |

For convergence or multiple predecessors, use `--before-links links-before.csv`
or `--after-links links-after.csv`. Link CSV columns are
`record_id,predecessor_record_id,predecessor_sha256`. Each row adds one declaration
to a successor in that side's register. Repeat the successor for multiple
predecessors. Do not repeat an edge in both the register and link CSV.
Predecessors must be identified by an explicit exact digest. The existing engine
reports dangling/cross-document declarations and rejects cycles and duplicate
edges; no link becomes an approval or a claim of semantic equivalence.

Spreadsheet exports must be UTF-8 CSV (a UTF-8 BOM is accepted). Use standard CSV
quoting for commas, quotes and multiline text; export identity and hash columns
as text so the spreadsheet does not rewrite them. Values are not silently
trimmed, normalized or coerced. Duplicate/unknown headers, missing/extra cells,
duplicate record IDs, malformed digests and partially supplied predecessors
fail with a diagnostic. Each CSV is limited to 16 MiB and 10,000 rows; source
files retain the engine's 16 MiB per-file limit. Oversize input fails, never
truncates. Only listed files are read: this does not scan directories or certify
that a register enumerates every stored file.

## Finding citations

`--findings-csv` accepts `finding_id,record_id,sha256,locator`. Repeat the finding
ID for multiple citations. The digest is required and binds the original cited
bytes; a changed ID cannot silently move the citation. To retain an explicitly
uncited finding, include its ID with all three citation cells empty. Do not mix
an uncited declaration and citation rows for one finding. Duplicate citations
and partial references fail rather than being silently merged.

Existing native findings JSON can instead be passed through `--findings`. The
two forms are mutually exclusive. Omit both to compare collections without
claiming any finding coverage. Locators are retained, not checked against source
text. Finding status counts are citation-review rows plus uncited findings, not
necessarily unique findings.

## Outputs and error handling

The six outputs are `before.json`, `after.json`, `findings.json`, `review.json`,
`review.md`, and `review.html`. Manifests contain actual source-byte hashes and a
digest of the supplied CSV bytes; no source text is copied unless you placed it
in metadata. CSV digests identify inputs, not their author or authenticity.

Exit **0** means all reports were written, including reports with conflicts or
missing evidence. It is not an assessment pass. Exit **2** means invalid input,
unreadable source or failed publication; stderr explains the cause. No bundle
is created until both snapshots, findings and comparison are valid. A filesystem
write failure can leave a partial new directory; the program reports that
location, leaves all bytes intact and requires a new output directory on retry.
It never overwrites, deletes, uploads or modifies a source or prior output.

Use a quiescent source collection: the underlying snapshot reader detects
incidental changes during each read, not an adversarial filesystem snapshot.
The two collections are read sequentially, not at one atomic instant. No source
authenticity, semantic interpretation, completeness, institutional result,
submission, approval or payment is established by this command.

The existing seven-case `build_reader.py`/`reader.html` walkthrough remains
unchanged and synthetic-only. This command's script-free report renderer works
with arbitrary real or fictional collections without relabeling private data as
that demonstration. Original comparison and recovery work: ORBIT47 and X6J4.
