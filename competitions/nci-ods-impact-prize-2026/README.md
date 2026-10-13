# ReuseLedger — NCI Office of Data Sharing Impact Prize 2026 / Track 1

ReuseLedger is a competition-isolated prototype for one concrete data-sharing idea: **make the complete bundle of research outputs surrounding a result machine-checkably reusable, not merely findable one artifact at a time.**

A project declares its datasets, software, protocols, models, publications, and other outputs in a small JSON manifest. `reuseledger.py` validates the graph, normalizes it deterministically, records exact manifest-byte and semantic hashes, derives reuse-readiness findings, and emits a tamper-evident packet plus a human-readable report.

This is deliberately **not another repository**. It is a thin handoff/evidence layer that can sit beside repositories already chosen by investigators and institutions.

## Track-1 fit

NCI's public announcement says the ODS Impact Prize seeks ideas and successful strategies that advance broad, rapid, equitable sharing and reuse of NCI-funded research outputs, explicitly including data, software, tools, methods/protocols, models, clinical-trial results, biospecimens, and other research resources. ReuseLedger targets the gap between "an output exists somewhere" and "a new user can identify the exact related outputs, rights, access conditions, dependencies, and immutable version needed to reuse it."

## Prototype contract

Input schema: `nci-reuseledger-manifest/v1`.

Each output declares a persistent/stable identifier, research-output kind and title, HTTPS landing page, access state, license/rights statement, data-use/access statement when relevant, optional SHA-256 plus byte count, and dependencies on other declared outputs.

The compiler:

1. rejects duplicate JSON keys, duplicate output IDs, unknown dependencies, cycles, non-HTTPS landing pages, malformed fixity, Boolean-as-integer aliases, and unknown schema fields;
2. sorts outputs and dependencies canonically and emits a deterministic graph;
3. flags missing reuse license, access/data-use metadata, and open-artifact fixity;
4. binds both exact source-manifest bytes and normalized manifest semantics;
5. emits a semantic SHA-256 over the complete packet;
6. verifies that a packet is the exact deterministic derivation of the supplied manifest, so a caller cannot edit a score/finding and merely reseal it.

## Local demonstration

```bash
cd competitions/nci-ods-impact-prize-2026
python reuseledger.py compile example_outputs.json --out /tmp/reuse-packet.json
python reuseledger.py verify /tmp/reuse-packet.json --manifest example_outputs.json
python reuseledger.py report /tmp/reuse-packet.json --out /tmp/reuse-report.md
python readiness_gate.py
```

The first three commands exercise the actual compiler, verifier and report. Prior execution records remain in the component documentation. The readiness command returns `BLOCKED` while the declared external-entry requirements remain incomplete; a completed local demonstration does not change that result.

## Scope and truth boundaries

- No patient rows, PHI, controlled-access datasets, biospecimen records, or clinical decision support are included.
- The tool performs no network access, scraping, repository upload, challenge submission, account mutation, purchase, contact, or prize claim.
- A `100/100` ReuseLedger score means only that this small metadata contract has no rule-based blocker/warning. It does **not** certify scientific validity, legal sufficiency, consent/privacy, clinical fitness, or repository acceptance.
- Any real project still uses its authoritative repository, institution, IRB/privacy, consent, policy, legal, and scientific review processes.

## Files

- `reuseledger.py` — deterministic compiler/verifier/report renderer.
- `test_reuseledger.py` — hostile and end-to-end tests.
- `example_outputs.json` — synthetic demonstration manifest only.
- `SUBMISSION_DRAFT.md` — Track-1 narrative carrier, explicitly not submitted.
- `SUPPORTING_EVIDENCE.md` — concise references for the separate one-page evidence PDF.
- `EVIDENCE_LEDGER.md` — source/truth boundary.
- `READINESS.json` + `readiness_gate.py` — fail-closed external-action gate.

## October 3 review PDFs

- [Track-1 narrative](reuseledger-track1-narrative-20261003.pdf): three pages, 1,446 extracted words including the running review footer, with the four webinar prompts and concrete AI-use disclosure.
- [Supporting evidence](reuseledger-supporting-evidence-20261003.pdf): one page, single-spaced, with an 11-point minimum font and linked references.

These are dated review copies of the Markdown drafts. All pages were rendered and visually inspected; text, page counts, minimum font size and embedded links were checked. Exact written-rule reconciliation and entrant review remain necessary before an external entry.

## Current external state

As of **2026-10-03**, the compiler and declared-reuse workflow are on main, and the draft follows the four prompts recovered from NCI's official August webinar. The webinar specifies a **2,500-word total narrative** and a **separate one-page evidence PDF**, single-spaced with an 11-point minimum font. It also requires disclosure of the specific generative-AI tool and role.

The complete written announcement and signed registration form remain to be recovered. The current NIH challenges index and NCI's newsletter updated October 1 both advertise **October 19**; the older GDC announcement and August webinar retain **October 5**. The exact closing time and complete current rules remain unresolved; see the dated comparison and timestamped requirements in [EVIDENCE_LEDGER.md](EVIDENCE_LEDGER.md). `READINESS.json` preserves all existing incomplete gates. No entrant eligibility, registration, signature, terms acceptance, external submission or award is claimed.

## Record downstream reuse and hand off a portable bundle

The additive `reuse_workflow.py` companion retains declared planned/reported reuse, exact upstream manifest bindings, downstream versions and explicit credit-reference states. Run the complete four-command journey in [WORKFLOW_GUIDE.md](WORKFLOW_GUIDE.md), read the [executed fictional example](WORKFLOW_EXAMPLE.md), or inspect the [schema and replay contract](WORKFLOW_CONTRACT.md). The original compiler and existing commands remain unchanged. See [WORKFLOW_EXECUTION.md](WORKFLOW_EXECUTION.md) for the exercised source and test scope.
