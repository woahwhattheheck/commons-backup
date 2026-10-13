# Review your supplied evidence manifests in a browser

`render_review.py` turns a before manifest, an after manifest and optional original findings into a self-contained HTML review. Unlike `build_reader.py`, it is not tied to the seven-case demonstration. It invokes the existing `lineage.compare()` engine; it does not implement another classifier or accept a precomputed verdict as fact.

## Generate the review

Python 3.10 or later, standard library only. From the repository root:

```sh
python revenue/uiowa_rfq_18649_evidence_lineage/render_review.py \
  /path/to/before.json /path/to/after.json \
  --findings /path/to/findings.json \
  --output /path/to/NEW_REVIEW.html \
  --title "Evidence collection revision review"
```

Omit `--findings` when no findings file is supplied. That produces zero finding rows, not a claim that no findings exist outside these inputs. Manifest and citation formats are documented in [README.md](README.md). The same command also works as `python -m revenue.uiowa_rfq_18649_evidence_lineage.render_review` with the arguments above.

Choose an output path that does not exist. The parent directory must already exist. The command reads and validates the inputs, computes the report and builds the complete page before opening the output with exclusive creation. It never replaces an existing file, including an input file or an occupied final output symlink. An I/O failure during writing can leave an incomplete new file; use a different output name after correcting the cause. No cleanup deletes an operator's files.

Exit `0` means the page was written, including when the comparison reports conflicts or missing evidence. Exit `2` means an input or output error, with a diagnostic on stderr. A successful comparison is not an accepted assessment. The existing engine's 16 MiB per-JSON-input limit applies; use a quiescent input collection. This is not an adversarial filesystem snapshot protocol.

## Read the result

Open the generated HTML directly in a browser. It needs no server, installation, account, external assets or network connection. It uses no browser storage. The output contains supplied metadata, not copies of the referenced source files, and it does not follow metadata locations or execute their contents.

The overview keeps the data-kind declaration, draft status and global counts visible. Distinct finding count is separate from citation/uncited-row count. An uncited finding contributes one follow-up row; a finding with three citations contributes three.

Collection changes link to both snapshots' exact record-ID/content-digest metadata. Each citation retains its original locator, exact copies and the entire known terminal-successor frontier. Omitted terminal records remain explicitly absent, including an omitted competitor in a branching history. A matching title, higher-looking version label or missing file never becomes an automatic successor or deletion decision.

Search and classification filters apply only to collection-change and citation-follow-up rows. Search covers text rendered in those rows, including collapsed row details; it is not a search over every field in the retained source manifests. Global anomalies, absent records, duplicate groups and retained inputs are never filtered. The visible/total row counter describes the filtered sections only. Reset restores their full display.

Internal metadata links expand the relevant record before focusing it. Complete original manifest fields and findings remain inspectable in the retained-input section, including extra operator metadata. Metadata locations are plain text, not automatic external links. Without JavaScript, all rows and expandable metadata remain readable, but search, automatic expansion of linked records and JSON download are unavailable.

**Print full report** includes all change/citation rows regardless of active filters and opens the retained details for printing. It restores the prior detail-open state after the print dialog. The page supplies print styling; browser pagination and the chosen printer remain browser-controlled.

**Download comparison JSON** returns the exact UTF-8 bytes of the comparator's canonical JSON output. JavaScript decodes an embedded byte sequence, not JSON numbers; large integer metadata is not converted through browser `Number`. This is the comparison output, not a byte-for-byte archive of original input JSON formatting. Input bindings refer to the comparator's canonical JSON representation.

## Privacy and interpretation

The complete supplied metadata is embedded in both the HTML and its JSON download. A manifest marked `synthetic: false`, or a mixed pair, is visibly labelled private/mixed. The synthetic label is only what the operator declared; the tool does not detect sensitive data hidden in a nominally synthetic record. Keep generated reviews on a surface appropriate for their actual contents. Do not commit private reviews to the public repository or attach them to a public issue.

No record, citation or finding is rewritten. Hashes remain manifest assertions unless separately checked against source bytes. Locators are not validated against passages. Supersession remains a supplied declaration, not approval, authenticity, semantic adequacy, compliance or a commercial decision. Printing, filtering and downloading do not resolve findings.

## Relationship to the existing tools

ORBIT's comparator, X6J4's missing-terminal repair and the recovered fixed-case presentation remain unchanged. The seven-arrival instructional walkthrough continues through [RUN_READER.md](RUN_READER.md). This new command projects arbitrary valid inputs with no changes to the engine, the fixed reader, the assessment workbench or repository workflows.

No new test files, fixtures, execution archive or workflow accompany this extension. No additional execution was performed during publication; the earlier Action Pad browser run is not evidence for this renderer. Operation: `yz-kestrel-ap47-lineage-general-reader-20260923`.
