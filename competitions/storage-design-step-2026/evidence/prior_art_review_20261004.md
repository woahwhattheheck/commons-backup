# FerroFrame manufacturing prior-art review — 2026-10-04

**Finding:** the reviewed packet does not yet demonstrate a design-specific manufacturing distinction. Earlier sources describe the broad features proposed here: integrated stack assemblies, common frames, replaceable units, membrane screening, and transport followed by electrolyte preparation. A particular combination could still differ, but the packet needs defined interfaces and comparative evidence before that difference can be assessed.

This is a bounded engineering source comparison for [original audit #16014](https://github.com/woahwhattheheck/commons/issues/16014), not an official prize score, a completed comprehensive novelty search, or a patentability/freedom-to-operate opinion. It supplies the source-comparison portion of that issue; it does not complete the original issue's broader gate-hardening or human-review work.

## Reviewed packet and attribution

The concept and original source/model package remain credited to **Z-RookVector-913604-Q7M2**, operation `DOE-STORAGE-DESIGN-STEP-ZRVQ7M2-20260913`, [#13766](https://github.com/woahwhattheheck/commons/pull/13766). **Z-Kestrel-0918** retains the original #16014 audit attribution. This dated review was assembled by the A3DEA swarm workstream from separate mechanical and membrane/logistics source readings. Generative AI assisted retrieval, comparison, and drafting; no entrant measurements were generated.

The comparison uses the following complete repository source bodies, identified by Git blob rather than a moving branch:

| Reviewed file | Blob |
| --- | --- |
| `submission/technical_narrative.md` | `f8c84660acf1399e089f8171af790072046496a8` |
| `README.md` | `1b1e33c49c86fe87d573b1fa943af13dd0ccb302` |
| `evidence/sources.md` before this addition | `23001b858efafe1a86a4cf80784baf82c6a98937` |
| `readiness.json` | `afc0f711d1e084dbe4d77eec6e5c819d28a7549b` |

The [narrative](../submission/technical_narrative.md), sections 1 and 3–5, places the proposed contribution at the manufacturing boundary. It already treats the alkaline iron chemistry as prior work and the cost examples as synthetic. The four reviewed source bodies supply no released cassette drawing, actual comparative BOM/router, qualified alternate membrane, supplier quotation, or entrant prototype measurements supporting the proposed architecture. This finding describes the reviewed packet; it does not assert that no such evidence could exist elsewhere.

## Comparison with earlier disclosures and experiments

The numbered sources below correspond to entries **11–19** in the [source ledger](sources.md#manufacturing-prior-art-review--2026-10-04). Publication dates identify when the selected material appeared; they are not legal priority or patent-status determinations. Patent descriptions establish written disclosures, not commercial deployment or successful FerroFrame qualification.

### Mechanical assembly and serviceability

| Earlier source and exact anchor | Relevant precedent and scope | Distinction still needed from FerroFrame |
| --- | --- | --- |
| **[11] Chalamala et al., 2014**, section IV.D; author-copy pp. 11–12, Figs. 10–11. | The paper's UTRC prototype account integrates membrane, electrodes and edge seals into a repeating assembly, paired with a bipolar plate/frame/seal assembly. This is a concrete earlier approach to reducing separately handled stack components. | Define the whole cassette boundary and fixed interfaces. Integration of repeating cell parts does not itself establish a field-replaceable cassette or interoperability across variants. |
| **[12] US20240047710A1, 2024-02-08**, claims 1–2 and 12–15; uniform-main-frame/different-insert description. | Separates the structural/sealing frame from fluid-distribution inserts, allowing a common frame with different configurations. | Identify which dimensions and interfaces are invariant, which inserts or external manifolds vary, and how the proposed arrangement changes the actual wetted SKU count. |
| **[13] US20210083305A1, 2021-03-18**, claims 1 and 6–8. | Describes detachable, replaceable battery-body units containing cells, enclosure and piping. Its specific context is nanomaterial containment and electrolyte exchange hardware. | Specify hydraulic/electrical disconnection, draining, access, containment and reused parts. The shared term “replaceable” does not establish the same design or a distinct one. |
| **[14] US20140060666A1, 2014-03-06**, claims 1–3 and 7–13; Figs. 7A–8B. | Describes internal manifolds and independently fed sub-stacks, including the tradeoff from duplicated pressure plates/current collectors in separate smaller stacks. This is a hybrid all-iron context. | Supply the cassette plumbing/electrical topology and count all additional connectors, seals, endplates and collectors at an equivalent rating. Evaluate hydraulic and shunt-current effects; do not transfer the hybrid-cell results to the proposed all-soluble system. |
| **[15] Richtr et al., 2025-07-15**, sections 3.2, 3.2.3 and 4. | Reports bonded/welded electrode, plate and terminal-current-collector assemblies in vanadium single-cell and two-cell work. It provides an experimental assembly precedent with process-dependent manufacturing economics. | Specify FerroFrame's joining process and module boundary, then measure yield, labor and service consequences in its own materials/chemistry. Published vanadium results are not entrant validation. |

**Counting rule for the proposed comparison:** distinguish physical components, separately handled assembly pieces, and unique wetted SKUs. Bonding several components can reduce handling without reducing underlying material variety; it may create a composite SKU and enlarge the replacement unit. Count the reference and candidate at the same active area or justified rated duty, with the same inclusion rules. Include fixture, inspection, rework and replacement consequences where they affect the claimed benefit.

### Membranes and supplier qualification

| Earlier source and exact anchor | Relevant precedent and scope | Distinction still needed from FerroFrame |
| --- | --- | --- |
| **[16] Zhao et al., 2021-03-17**, section 2.1/Table 1, sections 3.1–3.5, section 4/Table 6. | Compares eight commercial membranes using chemical/mechanical stability, resistance, selectivity/crossover and swelling. The result selects candidates for subsequent in-cell VRFB evaluation. | State numerical acceptance limits, dimensions/tolerances, preparation, operating conditions and aging duration for the FerroFrame electrolyte. A screening category is not a completed qualification. |
| **[17] Van Cauter et al., 2024-08-15**, Table 1, section 2.2, sections 3.4–3.5 and 4. | Screens nine commercial membranes and tests selected products in a common 6.25 cm² cell, including alkaline DHPS/ferrocyanide conditions and one-week thermal-storage assessments. | Demonstrate fit, seals, compression and sustained performance with iron-gluconate chemistry at the proposed stack conditions. A common laboratory fixture does not establish production interchangeability or lifetime. |

The proposed qualification envelope is a useful work plan, but its listed properties overlap existing screening methods. A defensible implementation would show at least two actually qualified products within a drawing-defined interface and predeclared electrochemical limits, including rejection outcomes. Supplier independence requires manufacturer-level evidence: buying through two distributors does not establish two independent manufacturing sources. This is an evidence requirement, not a finding that FerroFrame has qualified any alternative.

### Electrolyte preparation and transport

| Earlier source and exact anchor | Relevant precedent and scope | Distinction still needed from FerroFrame |
| --- | --- | --- |
| **[18] US20180316036A1, 2018-11-01**, description of dry assembly and end-use hydration; Fig. 3; claim 13. | Describes factory dry assembly, transport and field hydration, with precursors preloaded or delivered separately. Its iron-battery example includes plating. | Define the actual all-soluble formulation and preparation sequence, then obtain formulation-specific storage, reconstitution, repeatability and performance evidence. The general logistics sequence is already disclosed. |
| **[19] US20240194918A1, 2024-06-13**, solidification discussion and “EXAMPLE—Introduction”; receiving-site reconstitution passage. | Describes reducing water in vanadium electrolyte for transport and restoring usable electrolyte at the destination. The transported concentrated/solidified material retains water. | Specify what FerroFrame ships, water content, conditions, redissolution limits and field QC. Do not describe this vanadium precedent as an anhydrous route or evidence for alkaline iron compatibility. |

The existing narrative appropriately leaves route selection behind chemistry and EHS evidence. The comparison must account for packaging, shipped mass, preparation labor, water quality, rejects and commissioning outcomes at equivalent delivered usable electrolyte. No reviewed source selects a safe or economical FerroFrame route.

## Evidence assessment and next design decision

**Engineering assessment: distinction unresolved; manufacturing benefit unmeasured.** The current differentiator is a proposed combination and evidence plan. The next useful design deliverable is a specified candidate compared with one fixed reference build.

| Existing target in narrative section 3 or 4 | Current status | Evidence required to assess it |
| --- | --- | --- |
| At least **30% fewer unique bespoke wetted SKUs** | Target only | Released reference/candidate BOMs, consistent wetted/bespoke definitions, included spares and connectors, equivalent rating. |
| At least **25% fewer direct assembly minutes** | Target only | Released routers and repeated observed builds, common start/stop boundaries, operator context, yield/rework records. |
| At least **15% lower stack conversion cost per kW** | Target only; checked-in scenarios are synthetic | Comparable dated quotes or purchase evidence, quantities, production volume, tooling allocation, direct labor and yield assumptions. |
| At least **30% less single-source material-value exposure** | Target only | Qualified manufacturer identities per line, source-independence evidence, consistent value denominator and auditable reference/candidate calculation. |

A concrete contribution would explain **what changed, why existing arrangements do not provide that same benefit under the same constraints, and what was observed**. A common envelope drawing should include ports, sealing lands, compression, current collection, materials and allowable variants. A service procedure should identify the replaced unit and the parts retained. The comparison should show any performance or maintenance cost introduced by consolidation. These are design evidence needs, not new repository test-suite requirements.

Existing exact-decimal arithmetic can support such evidence once real inputs exist. Merely running the synthetic examples cannot establish supplier independence, savings, official scoring or novelty. This review does not rerun or alter the model, validator, examples or tests.

## Competition authority and review limits

The [DOE launch page](https://www.energy.gov/oe/articles/designing-energy-storage-real-world-production-doe-launches-storage-design-step-prize) confirms the program's focus on storage innovation with early attention to manufacturability and supply resilience. The [NLR publication record](https://research-hub.nlr.gov/en/publications/storage-design-strategies-to-ease-production-step-prize-official-/) identifies the 2026 official rules as **NLR/OT-6A42-101135**, 48 pages. Those pages were retrieved on 2026-10-04.

The current official PDF at `https://www.nlr.gov/docs/gen/fy26/101135.pdf` and the HeroX competition page were not accessible through this review's retrieval tool. Consequently, this review does not reverify the current deadline, precise rubric wording, numerical novelty threshold or eligibility terms. Earlier repository/Slack descriptions of these rules remain historical claims. **No official numeric score is assigned.**

The nine-source selection is a targeted comparison of the packet's named manufacturing features. It is not an exhaustive patent-family, jurisdiction, non-English literature or combination-claim search. The 2014 paper was read through its public author copy; the 2021 and 2024 membrane papers through public copies of the primary articles; the 2025 assembly paper through Fraunhofer's primary-paper repository; patent passages through their publication text. The inaccessible IEEE publisher page was not treated as read. Cited sections support only the stated bounded overlaps.

**Release state remains `BLOCKED`.** All ten existing readiness gates remain false, including `independent_novelty_search_complete` and `technical_claims_human_reviewed`. This source review does not supply owner eligibility/background, quote-backed inputs, EHS approval, final media, terms acceptance or submission authorization. The narrative and readiness file are unchanged. Original concept, audit and submission custody remain with their existing owners.
