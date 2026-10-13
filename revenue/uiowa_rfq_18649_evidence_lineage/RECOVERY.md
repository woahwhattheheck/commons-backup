# When an omitted draft is still part of the evidence history

UIOWA-033 operator guide. All worked records are fictional; no University practice, maturity, approval, or compliance conclusion is made. Original comparator, manifest contract and demo: **ZZ-ORBIT-47**. Missing-terminal repair and seven-case walkthrough: **ZZ-KESTREL-X6J4**.

## The decision this tool supports

A finding cites a particular record and SHA-256, with its original locator. A new evidence export arrives. The operator needs to know whether those bytes remain available, whether a declared revision needs review, and whether competing or omitted revisions still need to be reconciled. A filename, date, version string, or successful import cannot answer those questions by itself.

The existing engine keeps both complete manifests and original finding records. It follows only supplied predecessor references with exact record ID and digest, within the same logical document. It does not rank drafts, choose the latest filename, read a passage to validate its meaning, or authenticate a source. The adapter to the workshare authority-v2 format imports metadata only, not assessment scores or authority.

The missing-terminal implementation is tracked in [PR #16434](https://github.com/woahwhattheheck/commons/pull/16434). Its first immutable source is [507a4902](https://github.com/woahwhattheheck/commons/commit/507a490240cd8ccaad2a9503ec78911159c8f62b).

## Follow one historical finding through seven arrivals

Start with a fictional finding citing A, and declared succession A to B to C. C is the terminal declaration: it has no known successor in the supplied history. This is a graph property, not a statement that C is approved, current, or substantively correct.

**The original remains, but C is omitted.** The new export contains A. A's exact bytes are retained, but that does not erase the declaration ending at C. The queue now says `DECLARED_SUCCESSOR_MISSING_REVIEW`, while separately retaining the exact copy of A. Ask the custodian for C or the reason the export excludes it. Do not automatically rewrite the historical finding to cite another document.

**Only intermediate B remains.** C is still the known terminal. B does not become terminal merely because it is the newest supplied record. The same missing-successor status remains, with C's exact ID and digest.

**Nothing is supplied.** An empty after collection means no records were supplied in that export. It does not prove source deletion. The known C declaration remains visible and the collection boundary needs reconciliation.

**C arrives.** The queue changes to `DECLARED_SUPERSEDED_REVIEW`. The exact declared terminal is present; the operator must still read its passage, establish its applicable period, and decide whether the finding is historical or needs revision. The original locator remains unchanged and `locator_validation` remains `NOT_PERFORMED`.

**A competing draft D is known, but omitted.** The history now contains A to B to C and A to D. If the export supplies only C, both terminal declarations remain relevant: C is present and D is absent. The queue says `BRANCHED_SUCCESSION_REVIEW`. Omission cannot silently select C as the winner.

**D also arrives.** Both C and D are supplied, but the branch remains. Ask whether they represent competing revisions, parallel scopes, or an unresolved disagreement. Record the answer and its evidence separately rather than selecting a draft by label.

**A declared convergence E arrives.** E explicitly references both C and D with their exact digests. The graph now has one supplied terminal, so the queue changes to `DECLARED_SUPERSEDED_REVIEW`. The graph ambiguity is resolved by a supplied declaration; substantive correctness, custody, approval and the cited passage still require their own evidence.

[ARRIVAL_WALKTHROUGH.md](ARRIVAL_WALKTHROUGH.md) is the generated readout. The runnable generator produces editable inputs, fictional source text, complete engine reports and the combined readout. [RUN_READER.md](RUN_READER.md) explains how to turn the saved arrivals into a self-contained offline page.

## Read the output without losing evidence

`declared_successors` keeps its original meaning: exact terminal records present in the after collection. Existing consumers must not reinterpret that list as the entire known history.

When one or more known terminal records are missing, the report additionally contains `missing_declared_successors` and `declared_terminal_successors`. The first lists the absent exact references. The second lists the complete known terminal frontier with a boolean `present_in_after` for each reference. The Markdown report adds a corresponding section with IDs, full digests and presence.

An equal digest under a different record ID does not silently resolve an omitted record identity. Nor do changed bytes under the same ID count as the original declared record. A citation to C does not treat C itself as its successor. Dangling and cross-document predecessor references remain anomalies, not trusted graph edges. Cycles remain invalid input. Missing terminals in unrelated document histories do not change this finding's queue.

## Reproduce and use the existing CLI

From `revenue/uiowa_rfq_18649_evidence_lineage/`, choose two new destinations:

```sh
python demo.py /tmp/uiowa033-original-example
python walkthrough.py /tmp/uiowa033-arrival-example
```

The original demo and its checked-in example are retained unchanged. Each arrival-case folder contains `before.json`, `after.json`, `findings.json`, `before/` and `after/` fictional source directories, and real `review.json` / `review.md` output. Edit a separate copy of an input packet; keep the original history and citations for comparison.

Re-run one edited packet to standard output:

```sh
python lineage.py compare /tmp/edited-before.json /tmp/edited-after.json --findings /tmp/edited-findings.json --format markdown
```

Manifest hashes supplied by another party remain assertions. To check actual regular files against a catalog, use the existing `snapshot` command with that catalog and its root directory. Do not convert matching bytes into authenticated origin, approved revision, or validated content.

**Never redirect standard output over an input file.** Shell redirection can truncate the file before Python starts. The compare command itself does not offer an output-file switch. Save a copy to a distinct new path only after checking it is not an input or existing evidence.

The walkthrough refuses an existing destination. Semantic evaluation completes before it creates a directory, but later I/O failure can leave a partial directory. Treat that directory as incomplete and choose a new destination. It is not an atomic bundle installer. Do not feed untrusted paths or directories being adversarially changed into this offline example.

## A practical reconciliation note

For each impacted finding, keep the original finding ID, record ID, digest and locator. Record what was supplied, which terminal references remain absent, the question sent to the custodian, the relevant scope and time period, and the operator's eventual decision with its supporting source. Retain disagreement and uncertainty explicitly. A historical finding can legitimately keep citing the original bytes; receipt of a newer declaration does not compel a rewrite.

The entire input manifest and metadata are preserved in JSON. The walkthrough's embedded example text is deliberately fictional. Real metadata may contain private material; review the packet before sharing it outside its authorized evidence context.
