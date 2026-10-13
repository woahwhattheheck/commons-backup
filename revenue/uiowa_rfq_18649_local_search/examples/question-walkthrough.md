# UIOWA-127 — sample reviewer question-to-result walkthrough

All records below are synthetic preparation material. A search hit is a navigation result, not an assessment conclusion.

## 1. “Where is vulnerability ownership represented?”

```bash
python3 evidence_search.py query examples/index.json "vulnerability ownership"
```

Top hit: `RIS-SEC-01` (`source_metadata`). The result preserves:

- native source reference: `synthetic://uiowa-rfq18649/RIS-SEC-01`;
- upstream repository file: `revenue/uiowa_rfq_18649_workshare/fixtures/synthetic_authority.json`;
- pinned upstream Git blob: `1d58638c067b35dbdc210365ac3f30d6e72c9548`;
- locator: `sources[source_id=RIS-SEC-01]`.

The snippet says the *synthetic interview* maps vulnerability ownership to a defined operating role. It does not turn that source statement into an Iowa finding.

## 2. “What says end-to-end propagation evidence is incomplete?”

```bash
python3 evidence_search.py query examples/index.json "end to end propagation"
```

The first two useful hits are:

1. `F-002` — finding “Propagation evidence remains incomplete,” linked to `E-004`, `E-005`, and `E-006`.
2. `E-005` — observation located at `row reporting-contract-04`, stating that contract compatibility is covered while no end-to-end propagation scenario is listed.

Because finding → evidence IDs remain in the result, a reviewer can move from synthesized wording back to the observations without reconstructing the chain by hand.

## 3. “Where does the extracted sample say review is required before merge?”

```bash
python3 evidence_search.py query examples/index.json "independent review before merge"
```

Top hit: `EXTRACT:sample.txt:text-0002`, locator **`lines 2-2`** in the merged synthetic document-extraction fixture. The source link goes directly to `sample.txt`; the index also pins its Git blob `78cb8df251b9b840b9b8074fd4f7f92d32d139f5`.

This exercises the document-extraction locator contract rather than pretending TXT has page numbers.

## 4. “Which source says the deployment runbook is stale?”

```bash
python3 evidence_search.py query examples/index.json "deployment runbook intentionally stale"
```

Top hit: `IAM-DEP-01`, the synthetic authority record whose claim explicitly says the deployment runbook is intentionally stale for the proof fixture. The search returns its native synthetic source reference and the pinned workshare authority blob.

## 5. No supporting record

```bash
python3 evidence_search.py query examples/index.json "nonexistentquasarword"
```

Result: an empty result list. The component does not make up an answer, a locator, or a “closest” unsupported claim when there is no lexical match.

## What this demonstrates

The component provides fast local discovery across several existing artifact types while preserving exact IDs, source paths, locators, linked evidence IDs, and pinned source versions. It requires no embedding API or external model service and remains deterministic across runs.
