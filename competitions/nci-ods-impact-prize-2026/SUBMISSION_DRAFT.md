# ReuseLedger: Portable handoffs for cancer research outputs

**Track 1 - Research Output Sharing and Reuse Ideas**  
**Review draft, October 3, 2026. Not submitted.**

The four sections below follow the official August 12 NCI webinar and fit within its 2,500-word total. Exact written prompt wording, the registration form, complete terms and the current deadline remain to be reconciled; see [EVIDENCE_LEDGER.md](EVIDENCE_LEDGER.md). This draft does not assert entrant identity, eligibility or institutional participation.

## 1. Significance and approach

A cancer research result can depend on a dataset, analysis code, a trained model, a protocol and a publication held in different repositories. A downstream researcher needs the right combination: which version of the code used which data, which dependencies are required, where access is controlled, and how to credit the originating work. A set of landing-page links can leave these questions unresolved even when each output has been shared.

ReuseLedger addresses this handoff problem with a small, portable manifest and an executable metadata check. Its intended first users are research teams preparing a release, data stewards and librarians helping curate it, and researchers trying to reuse it. The proposal fits NCI's stated interest in broad, rapid and equitable reuse of research outputs beyond datasets, including software, tools, models and protocols [1].

A curator records stable output identifiers, research-output types, landing pages, access and rights statements, optional byte-level digests, and dependencies. The existing compiler checks the graph and creates a canonical packet plus readable findings. It exposes missing dependency references, absent reuse conditions and incomplete fixity metadata. A recipient can verify that the packet was derived from the exact supplied manifest, rather than trust an edited summary.

The existing companion adds a journal of planned or reported downstream reuse, tied to the original manifest and output versions. A downstream work identifier, purpose and stated credit references travel with the handoff. Unknown credit remains unknown. These records are declarations; they become evidence of actual reuse only when independently supported.

The workflow carries metadata. Research data, software and controlled assets stay in their authoritative repositories. It grants no access permission and does not infer consent or legal rights. A digest checks byte identity, and a complete metadata graph does not establish scientific validity. These limits support a staged evaluation using public project descriptions before any institution considers broader deployment.

## 2. Innovation and awareness

The approach builds on established infrastructure. DataCite provides metadata for identifying and citing research resources and expressing their relationships [2]. RO-Crate already packages research data and metadata, including workflow and software use cases [3]. Their identifiers and conventions should remain authoritative.

The contribution to evaluate is an operational combination: deterministic checks at the point of handoff; an exact binding between a supplied manifest and its derived findings; and a downstream reuse journal that distinguishes intention, reported use and explicit credit evidence. A researcher should be able to see both what is missing before reuse and what support exists for a later reuse claim.

This is a narrow proposition about making a handoff understandable and checkable. Metadata graphs, provenance and research-object packaging are established ideas. The next implementation step would map existing DataCite and RO-Crate fields into the minimal manifest, retaining source identifiers and exposing unrepresentable or missing fields. Those adapters are proposed, not shipped.

The comparative evaluation must include existing repository materials and established research-object packaging. If the additional convention duplicates available metadata without improving task success or reducing ambiguity, the useful checks should be simplified or contributed to existing tools. This provides a route to value without requiring a competing repository or new central service.

## 3. Impact

The potential benefit is fewer failed or ambiguous handoffs between research producers and downstream users. That could help stewards identify a missing version, dependency or rights statement before another researcher spends time reconstructing it. A local, standard-library implementation provides a starting point for teams that cannot operate a new hosted platform. Neither time savings nor equitable benefit has yet been measured.

The current repository contains the compiler, report renderer and declared-reuse companion, with an executed fictional handoff and portable replay described in retained operator documentation [4,5]. This demonstrates software feasibility. The examples contain no patient records and establish no cancer-research adoption, independent credit observation or scientific impact.

The proposed evaluation has two stages. First, independent curators would assemble manifests for a disclosed sample of heterogeneous public cancer-research projects spanning data, software and protocols. They would record source URLs, unresolved fields, disagreements and curation time. Inclusion rules would be fixed before assessing results, and projects with missing information would remain in the analysis.

Second, downstream users with different levels of repository experience would perform matched handoff tasks using ordinary project materials, existing research-object packages where available, and the proposed packet. Tasks would ask users to identify required output versions, locate access conditions, trace dependencies and identify the appropriate credit path. A task would count as successful only when its answer is supported by retained source evidence; speed alone would not be success.

Outcomes would include correct task completion, unresolved dependencies, incorrect version or access assumptions, and time to a supported answer. Author burden, inter-curator agreement and failure rates would be reported alongside recipient benefit. Results would be separated by output type and participant experience, with denominators and negative findings retained. Upload and declaration counts would remain activity measures, not proxies for scientific impact.

This design can establish whether the approach helps users beyond its developers. It can also reveal that it does not: a higher local metadata score might coexist with difficult access, poor documentation or no improvement over an existing RO-Crate package. Such findings would guide whether to continue, narrow or retire individual checks.

## 4. Transferability and sustainability

The smallest adoption unit is one project, its manifest and a local command. An institution could begin with public metadata and a static packet linked from its existing project page. The compiler and companion are available in the current source tree; no new service account or central data migration is required for this local workflow [4,5].

A pilot would need a software maintainer, a data steward or librarian familiar with the selected outputs, and downstream participants willing to attempt realistic reuse tasks. These are proposed roles, not committed partners. Teams would need time to resolve ambiguous identifiers and rights statements; low infrastructure requirements do not eliminate this work. An institution using controlled resources would continue its own access, privacy and governance processes.

Initial engineering priorities are interoperable field mappings, clear explanations of findings, and a stable versioned format. Maintainers should document compatibility changes, keep older manifests readable where feasible, and allow packets to be checked without a continuously running service. Each packet should retain the source generation it describes so a later release does not silently rewrite an earlier handoff.

Continued use depends on the proposed benefit exceeding curation and maintenance cost. A pilot should budget both author and recipient effort, publish the resulting evidence, and identify a responsible maintainer before promising ongoing support. Optional integration with repository release workflows can follow if users find the local approach useful; it is not a prerequisite for the initial study.

Longer-term governance should be developed with research-software and metadata communities rather than assumed by the prototype's authors. Published mappings, documented limitations and reusable checks would let other institutions adapt the approach even if the original project stops operating. The goal is a transferable improvement in handoff practice, supported by measured user outcomes and compatible with existing infrastructure.

## Supporting references

The separate [supporting-evidence document](SUPPORTING_EVIDENCE.md) maps references [1]-[5] to public sources and retained implementation evidence. It separates feasibility and proposed evaluation from real-world impact.

## AI-use disclosure for entrant review

OpenAI ChatGPT (GPT-6 Astra Pro) assisted this October 3 preparation with public-source research, recovery and interpretation of official webinar instructions, proposal organization, drafting, editing and document preparation. Earlier retained development records identify additional AI-assisted engineering, including GPT-5.6 Sol; the entrant must confirm the complete tool and role history before submitting the required disclosure. No patient or controlled NIH research data were used in this preparation. The entrant must substantively review and own the final statements and follow the written announcement's exact disclosure instructions.

## Entry completion still required

Recover the complete written announcement and registration form; reconcile exact prompts, subject line and formatting; confirm the closing time for the currently advertised October 19 date, retaining older October 5 material as history; establish the actual entrant category and eligibility; confirm institutional, rights and funding-source facts; finalize the disclosure; sign the required form; and obtain the already-required external submission authorization. No registration, signature, terms acceptance, email submission or award is represented here.
