# UIOWA-103 — deterministic cross-component identity map

**Synthetic preparation and offline inspection only.** This component preserves evidence identity when independently built tools reuse local IDs. It does not evaluate University maturity, certify a source, approve a release, or decide that two findings are factually equivalent. It performs no network request or source execution.

## Run the complete examples

Python 3.10+ and the standard library are sufficient. From this directory:

```sh
python -m unittest discover -s tests -v
python -O -m unittest discover -s tests -v
python identity_map.py examples/collisions.json --output /tmp/uiowa103-collisions.json --markdown /tmp/uiowa103-collisions.md
```

The collision command intentionally exits **1**, while producing both reports: 10 occurrences, 2 collision groups, 9 links, 4 unresolved links. Exit 1 means inspectable missing/ambiguous references, not malformed input. Do not hide this result in a pipeline. The fixture covers all five record kinds, two origins reusing `EV-1` and `F-1`, two versions of one source, two visually similar but byte-distinct Unicode IDs, explicit same/different-entity decisions, and a missing finding. All source locators in this fictional collision packet are illustrative retained metadata; no underlying source file is asserted to exist.

The actual published evidence-register integration runs separately:

```sh
python register_adapter.py examples/register_023.csv --namespace methodology-023 --source-path examples/register_023.csv --synthetic --expected-blob fc2ef567e3f9b3f5a5031c74994e62c62b1d9c7e --output /tmp/uiowa103-register-packet.json
python identity_map.py /tmp/uiowa103-register-packet.json --output /tmp/uiowa103-register-report.json --markdown /tmp/uiowa103-register-report.md
```

Both commands exit **0**. The adapter retains 7 evidence rows as source records, 7 observations and 5 findings: **19 occurrences and 14 resolved links**. The two rows on the fictional IAM deployment disagreement remain attached to their shared finding, with `CONFLICTING` and `UNRESOLVED` unchanged. An identity-resolved link is not a judgment that its evidence supports the conclusion.

The checked-in `examples/register_023.csv` is a byte-exact portable copy of `../uiowa_rfq_18649_workshare/methodology/23-synthetic-evidence-register.csv`, Git blob `fc2ef567e3f9b3f5a5031c74994e62c62b1d9c7e`, read on September 19, 2026. Original methodology/source attribution stays with that component. The adapter also accepts an explicitly supplied new version; the input's exact bytes determine its revision. The optional expected-blob check detects a changed sample rather than silently using its old revision. Underlying `source_ref` documents were not fetched by this adapter, and ESS/RIS/IAM group labels are not manufactured service IDs.

## Library contract

See [INTERFACE.md](INTERFACE.md) for the exact v1 record, selector, decision, link and output shapes. Import `IdentityMap` for direct resolution or `reconcile` for an envelope retaining extension metadata. `MappingError` identifies invalid input. There is no installation step; the module can be loaded by path or as a package without a global generic `core` module.

Occurrence identity is `(namespace, kind, id, revision)`, encoded as domain-separated canonical JSON before SHA-256. A distinct navigation `entity_id` omits revision. Neither existing ID changes under an unrelated import. A snapshot equivalence-group ID is deliberately membership-dependent and must not be used as a durable entity ID. Records keep original JSON types, extension fields, locator order and duplicate locators; exact duplicate occurrences have an explicit count. Conflicting duplicates fail rather than overwrite.

Qualifiers omitted from a reference are unknown, never guessed. Namespace collisions or multiple source revisions remain ambiguous, even if a declared equivalence group connects them. A positive equivalence declaration does not merge payloads, select a latest version, upgrade synthetic material, or validate the declaration's reason. Negative declarations are checked against the full positive transitive closure.

## Inspect the result

The JSON report retains every original record and link, candidate occurrence IDs, explicit equivalence decisions, summary counts and a deterministic snapshot digest. The Markdown report is a compact index/diagnostic view; the JSON remains the lossless source for payloads. `assessment_authority` is always false. A report with no links has nothing to resolve and is not evidence of adequate coverage.

Unknown synthetic classification is not silently converted to true or false. An adapter encountering unknown/mixed input labels should preserve a separate rejected/unclassified record and diagnostic, rather than send an invented boolean to this core. The core v1 requires an explicit boolean on admitted records; this is a data contract, not an access restriction.

## Coordination

Canonical core: **ZZ-LODESTONE-47 / GPT-6 Astra Pro**, issue #16162, operation `uiowa-103-lodestone47-20260919`. QUARTZ-731 owns Handoff/Outcome adapters and replay; CIRRUS owns incremental-import conformance; HALYARD-86 owns equivalence/provenance challenge cases; KESTREL-6D9F owns conservation/CLI integrity. The native workshare and 047 component adapters have separate owners. They consume this interface instead of adding interchangeable mapper implementations. No shared assessment/compiler/workbench files are edited here.

## Measured validation scope

The initial core/register battery executed 30 tests normally and 30 with a real optimized Python interpreter; both passed. It covers deterministic permutations, qualified/unqualified resolution, transitive contradictions, revision isolation, Unicode/delimiter distinctions, duplicate conflicts, extension conservation, input/output isolation, strict malformed JSON/CSV, the exact 023 source blob and real CLI-to-CLI composition. See PR evidence for subsequent exact-head corrections and independent review results. These measurements are local ephemeral-cloud execution, not hosted-CI or live-University results.
