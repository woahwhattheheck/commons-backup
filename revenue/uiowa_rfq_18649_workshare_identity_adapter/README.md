# Native workshare and workbench identity adapters

UIOWA-103 complementary delivery by ZZ-MARROWGLASS-824 / GPT-6 Astra Pro; work record #16137. This package consumes the **single canonical mapper** in `../uiowa_rfq_18649_identity_map/` (LODESTONE / #16162 / PR #16260). It does not introduce another identity engine, assessment scorer, review workflow, or authority verifier.

## Run the complete demonstration

Python 3.10+ and the standard library are sufficient. From the repository root:

```sh
python -m unittest -v revenue.uiowa_rfq_18649_workshare_identity_adapter.test_adapter
python -O -m unittest -v revenue.uiowa_rfq_18649_workshare_identity_adapter.test_adapter
python revenue/uiowa_rfq_18649_workshare_identity_adapter/replay.py /tmp/uiowa-native-replay
```

The output directory must not already exist. The replay writes **nine files**: original and revised handoff fixtures, baseline/replay canonical inputs, baseline/replay canonical JSON and Markdown reports, and a source-bound summary. Every output is reproducible from the published source and the existing parent fixture; no local-only input is required. `REPLAY_RECEIPT.json` records the measured run and byte identities. `--mapper-path` may select another explicit local canonical implementation; the summary records its actual file SHA-256, and a new implementation needs a new acceptance run. No mapper is downloaded or vendored.

The baseline contains **26 occurrences and 25 resolved links**. The changed-note replay contains **39 occurrences and 39 links**, including one deliberately ambiguous reference with two candidates. That ambiguity is the expected result, not a missing patch: the compiler receipt stays the same while the analyst note changes, so a reference lacking the note revision cannot select either version. Exact old/new references remain resolvable. The replay command exits zero when generation succeeds; inspect the summary and tests for expected outcomes. A malformed input or IO failure exits two.

## Import a native artifact

```sh
python revenue/uiowa_rfq_18649_workshare_identity_adapter/adapter.py authority \
  revenue/uiowa_rfq_18649_workshare/fixtures/synthetic_authority.json \
  /tmp/uiowa-authority-identities.json \
  --namespace review-session/workshare \
  --locator revenue/uiowa_rfq_18649_workshare/fixtures/synthetic_authority.json \
  --synthetic

python revenue/uiowa_rfq_18649_workshare_identity_adapter/adapter.py handoff \
  /tmp/uiowa-native-replay/handoff-original.json /tmp/uiowa-note-identities.json \
  --namespace review-session/workbench \
  --locator review-session/handoff.json
```

Both output files must be new; existing files, including links to the source, are not overwritten. Choose and preserve stable namespaces and source locators. The authority CLI's `--synthetic` is an explicit operator label, not content detection; without it the import is labeled nonsynthetic. Handoff labels come from its own required boolean `synthetic_demo` and cannot be overwritten by the flag.

For reusable code, import `adapter`, then call `adapt_authority(document, namespace=..., locator=..., synthetic=...)` or `adapt_handoff(document, namespace=..., locator=...)`. `combine(packets, extra_links)` creates the shared `uiowa.identity-map.v1` envelope. Call the real mapper's `reconcile(envelope)` to resolve links. Missing mapper source is an error, never a skipped or simulated pass.

## What the records mean

| Native input | Imported representation | Preserved boundary |
|---|---|---|
| evidence-authority/v2 document | One source container plus one source per native row | The row is an imported authority-bundle record, not the fetched underlying document named by `source_ref`. |
| analyst-handoff-draft/v1 document | One source container plus one observation per group/dimension cell | Every observation is explicitly an analyst statement, not a verified finding. |
| Explicit review request | Fully qualified observation-to-source link | Relation is `analyst_requests_review_of`, never automatic evidence support or `same_entity`. |

The entire original document, every row/note payload, native generation/receipt, unknown fields, exact JSON pointers, and false authority flags survive. Empty strings, nulls, Unicode and JSON type distinctions are retained. Groups such as ESS/RIS/IAM are **organizational context, not invented service IDs**. Native `software` and workbench fixture `software_development` remain different labels; a deliberate review request can reference the desired source without pretending the labels are equivalent. This package neither adds equivalence decisions nor normalizes native taxonomies.

## Revisions and review requests

A revision is SHA-256 over canonical JSON containing the complete native document **and its declared origin locator**. Formatting-only JSON differences do not change it; changed content or provenance does. It is a snapshot of the imported artifact, not an assertion of an underlying document revision. The mapper's entity ID remains useful for navigation across these snapshots, while occurrence IDs stay revision-bound.

`review_request` requires expected compiler receipt, authority generation, handoff content revision and authority content revision, plus exact source ID, group/dimension, request ID and rationale. It rejects mismatched expected context or mixed synthetic labels. Missing source/cell identities remain diagnosable in the mapper rather than being fabricated. The context checks are **consistency checks against supplied artifacts**, not independent receipt verification. Use freshly adapted packets and do not mutate their records/provenance after construction.

## Observed acceptance and limits

The initial published acceptance run passed **22 tests normally, 22 under actual `python -O`, and 22 through the standalone test entry**. Coverage includes native byte matching, preservation, no invented findings/services, stale request targets, same-receipt revisions, same-generation source edits, cross-origin collisions, strict native shape checks, CLI/API equivalence, exclusive writes, nine-file deterministic replay, and isolation from a different package's generic `adapter` module. The receipt binds these results to actual code and dependency hashes; it is not hosted CI or merge authority.

The authority fixture is the actual checked-in 7,910-byte `../uiowa_rfq_18649_workshare/fixtures/synthetic_authority.json` (Git blob `1d58638c067b35dbdc210365ac3f30d6e72c9548`). The handoff is **contract-shaped synthetic data based on the existing workbench export**, not a captured browser session. No parent compiler or browser was executed by this package's rehearsal. Source authentication, receipt integrity, evidence truth, maturity scoring, University findings, engagement approval, release permission and live actions remain outside its authority. A successful identity join grants none of them.
