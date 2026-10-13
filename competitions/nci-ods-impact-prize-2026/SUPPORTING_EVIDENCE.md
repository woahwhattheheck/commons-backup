# ReuseLedger - supporting evidence

**Track 1 review draft | October 3, 2026 | Not submitted**

**Proposal:** Portable manifests, deterministic handoff checks and explicit downstream reuse declarations for linked cancer-research outputs. Current evidence supports a runnable prototype and proposed evaluation; adoption, time savings, independently observed reuse and scientific impact are not established.

**[1] Challenge fit.** NCI's Genomic Data Commons announcement identifies broad, rapid and equitable sharing and reuse as the objective and includes software, tools, models and protocols alongside data. [NCI announcement](https://gdc.cancer.gov/turn-data-sharing-ideas-impact-enter-nci-ods-impact-prize).

**[2] Identifier and metadata foundation.** DataCite Metadata Schema 4.7, released March 3, 2026, supports identification and citation of research resources and related objects. The proposed adapter would reuse these fields and identifiers. [DataCite schema](https://schema.datacite.org/).

**[3] Existing research-object packaging.** RO-Crate provides a lightweight approach to packaging research data with metadata and has workflow/software applications. The proposed contribution is the handoff-check and declared-reuse convention; packaging itself is established prior work. [RO-Crate](https://www.researchobject.org/ro-crate/).

**[4] Existing compiler.** The public source validates a declared dependency graph, records exact manifest-byte and semantic hashes, derives metadata findings, and verifies packet derivation. The example is fictional, with no participant or clinical records. [Source and operator commands](https://github.com/woahwhattheheck/commons/tree/main/competitions/nci-ods-impact-prize-2026).

**[5] Existing declared-reuse workflow.** The retained executed example initializes a journal, records declared reuse, exports a portable bundle and replays it. It contains one reported record with two upstream bindings; credit remains unknown. Its outcomes are software-execution evidence, not independently observed research reuse. [Executed example](https://github.com/woahwhattheheck/commons/blob/main/competitions/nci-ods-impact-prize-2026/WORKFLOW_EXAMPLE.md).

**Evaluation proposed, not performed:** Compare supported version/access/dependency/credit identification using ordinary project materials, established research-object packages and ReuseLedger. Retain failed cases; report correct completion, ambiguity, time, curator burden and results by output type and user experience. A metadata score is not scientific, legal or clinical certification.

**Disclosure and entry status:** OpenAI ChatGPT (GPT-6 Astra Pro) assisted this preparation with research, instruction recovery, drafting, editing and document preparation. Earlier engineering tool history needs entrant confirmation. Complete written rules, signed registration, entrant facts and exact closing time remain unresolved. The current NIH index and NCI newsletter advertise October 19; older material retains October 5.
