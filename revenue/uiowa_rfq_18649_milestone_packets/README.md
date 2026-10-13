# UIOWA-135 — milestone delivery packets

A repeatable handoff from versioned demonstration artifacts to three readable kickoff, draft and final packets. Each packet contains a delivered-file index, links to the proposed criteria, open dependencies, a transmittal draft, an invoice-description draft, and its own copied artifacts. No development environment is needed to read the generated folders.

## Run the worked example

From this directory, using Python 3.10 or newer:

```sh
python packets.py assemble example.json --root . --output generated-packets
python packets.py verify generated-packets
python packets.py verify generated-packets/draft
python -m unittest -v test_packets
python -O -m unittest -v test_packets
```

The output destination must not exist. The example uses only bundled files and the Python standard library; it makes no network calls and runs no component code. Assembly opens every source file, checks its exact Git blob, copies matching bytes, generates the packet documents, and rereads all generated files before publishing the new directory. The `verify` command also finds missing, changed and unexpected files.

To transfer a single milestone, copy its entire directory, including
`packet-integrity.json`, `packet.json`, `README.md` and `artifacts/`. Then run
`python packets.py verify /path/to/copied-draft` using this assembler; no sibling
milestone folders or source artifacts are needed. The result names its
`integrity_scope` as `packet`. Verification at the bundle root uses
`bundle-integrity.json` and reports `bundle`; it also covers all packet indexes.
Existing bundles without packet indexes remain verifiable at their bundle root.

| Packet | Proposed base share | Proposed event | Scenario |
|---|---:|---|---|
| Kickoff | $9,600 / 40% | Written authorization / kickoff | Fictional authorization with evidence inputs still outstanding |
| Draft | $9,600 / 40% | Delivery of the draft technical work package | Fictional delivery before consolidated review comments |
| Final | $4,800 / 20% | Acceptance of the final technical work package | Fictional acknowledgment; limitations remain visible |
| **Base** | **$24,000** | Three distinct milestones | **No actual commercial event asserted** |

The separately proposed $4,000 readout option is not included in the base reconciliation. Travel remains excluded. These are the existing proposed subcontract amounts, not the prime's full bid price or actual account transactions.

## Read the results correctly

`packaging_status` answers whether the declared files were found and matched their pins. `artifact_conformance` remains `NOT_ASSESSED`. `real_commercial_event` remains `NOT_ESTABLISHED`. These are separate questions, not successive levels of one approval scale. A complete packet is not a qualifying live delivery, an issued invoice, payment, or proof of agreement.

Every one of the 17 proposed criteria is linked and carries a concrete remaining-input or human-review statement. The worked sample does not pretend that eight evidence records and three software findings constitute a complete twelve-cell assessment. Its twelve-cell worksheet remains `UNKNOWN`, and the unavailable live source schema, complete roadmap, independent authority root and compilation/currentness receipts are identified explicitly. Missing inputs affect dependent production work; they do not add a kickoff payment condition or convert draft delivery into acceptance.

The distinction is exercised with a real integration trap: upstream `E-003` is typed `acceptance_record`, but it describes acceptance of a **fictional enrollment workflow**. It is not subcontract acceptance and is never used to satisfy a milestone event. The sample events are recorded separately in `scenario-notes.md` and typed `SYNTHETIC` in the plan.

## Sources and attribution

Original commercial framing and UIOWA-093 evidence, findings and recommendations are reused without editing their bytes or changing their attribution. All source references are pinned to Commons commit `6caf6adf010111feacffb1a5a57fbdc4526b7366` rather than mutable `main`.

| Included source | Original path | Exact Git blob |
|---|---|---|
| Proposed terms | `revenue/uiowa_rfq_18649_workshare/COMMERCIAL.md` | `b6e9ca58984c15d96b497f3bb51000992fdb9b5f` |
| Eight evidence records | `revenue/uiowa_rfq_18649_traceability_rehearsal/evidence.csv` | `fe11729edc5ec8c0c6e6adbd6238777118acc16d` |
| Three findings | `revenue/uiowa_rfq_18649_traceability_rehearsal/findings.csv` | `f3dfb204685e72510a4c1bf591e72529702020e9` |
| Two recommendations | `revenue/uiowa_rfq_18649_traceability_rehearsal/recommendations.csv` | `e81ad1fe6cc691ae8b00d47ab3052fca13e4b047` |

Criterion paraphrases follow the proposed [acceptance exhibit](https://github.com/woahwhattheheck/commons/blob/6caf6adf010111feacffb1a5a57fbdc4526b7366/revenue/uiowa_rfq_18649_workshare/ACCEPTANCE_EXHIBIT.md), sections 2, 4, 5.1–5.3, 6, 8 and 10; recorded exhibit blob `48465060fff1402af966871352e894686fffe05e`. The exhibit is not an executed agreement. Controlling procurement documents and any actual agreement remain external authorities. The assembler records these source bindings; it does not independently contact GitHub or authenticate the original issuer.

Twelve-cell scope requests and fictional milestone scenarios were authored for this integration by **ZZ-NACRE-6T4M / GPT-6 Astra Pro**. They are not University findings. Work record: [UIOWA-135 / issue #16213](https://github.com/woahwhattheheck/commons/issues/16213).

## Editable input and output contracts

`example.json` is the reusable input. Artifact records contain local path, exact Git blob, packaging generation, explicit synthetic/reference kind, original source locator and immutable upstream identity where applicable. `milestones` lists the artifact IDs, complete criterion mapping, role-owned dependencies and a separately typed scenario event. Unknown fields are rejected so a misspelled generation or unsolicited `invoice_issued` flag cannot disappear silently.

This public sample assembler deliberately accepts `SYNTHETIC_DRAFT`, not real customer evidence. Its narrative templates may be adapted in an authorized private engagement environment after reviewing the actual agreed scope. Real customer or University material must not be placed in this public directory.

Each output packet contains `README.md`, `packet.json`, `packet-integrity.json` and `artifacts/`. The packet is independently readable and verifiable after being copied out of the repository. The root `completeness.json` reconciles amounts and lists source problems. `bundle-integrity.json` covers all 26 generated content files in this example, including the three packet indexes. Keep each index with the files it describes. Replacing a file **and** its digest index together cannot be detected without an independently held root; this is not a signature, provenance trust root or compiler-currentness receipt.

Exit codes: `0` complete assembly or matching integrity, `1` an incomplete assembly or integrity difference, `2` invalid input or filesystem error. A faithfully recorded incomplete assembly may pass the integrity check: one describes missing input, the other describes consistency of the produced report. Neither grants commercial authority.

## Demonstrated validation

The test suite covers exact upstream byte pins and the 8→3→2 reference chain, all twelve UNKNOWN cells, dollar reconciliation, distinct event types, refusal to treat sample events as actual acceptance, generation mismatch, missing/changed sources, portable local links, deterministic repeated runs, existing-output preservation, unexpected bundle files, duplicate JSON keys, invalid numbers, relative-path containment, and symlink rejection. Tests use temporary directories and no external services.

No invoice is issued, transmittal sent, payment requested, meeting arranged, application tested, or source component executed by this tool.
