# Scientific basis and development plan — RBP-EIS CleanTrace

## 1. Scientific mechanism

Bacteriophages attach to host bacteria through highly selective interactions between phage structures and bacterial surface receptors. Receptor-binding proteins (RBPs), tail fibers and related phage-derived binding domains can therefore serve as biorecognition elements. Immobilizing such binders on an electrode creates a route to translate target capture into a measurable electrochemical change.

The proposed cartridge uses several individually addressable sensing lanes:

- one or more **target lanes**, each functionalized with a validated phage-derived binder;
- a **negative/non-binding lane** to quantify non-specific matrix effects;
- a **positive/electrode-control lane** to detect cartridge or reader failure; and
- optional replicate lanes when the error budget requires them.

After a standardized surface sample is eluted onto the cartridge, target organisms bind to the cognate lane. The reader measures differential pulse voltammetry (DPV), electrochemical impedance spectroscopy (EIS), or another experimentally selected electrochemical response. Software evaluates control validity before reporting any target call.

The exact transduction chemistry is **not frozen by this proposal**. DPV and EIS are both supported by published precedent; bench work should select the simpler, more reproducible path for the final organism panel.

## 2. Published precedent

### Salmonella / RBP 41 / DPV

Ding et al. constructed a graphene-oxide / gold-nanoparticle electrode functionalized with phage-encoded RBP 41. The paper reports specific Salmonella detection in approximately 30 minutes and application to food matrices.

- DOI: https://doi.org/10.1016/j.talanta.2023.125561
- PubMed: https://pubmed.ncbi.nlm.nih.gov/38128279/

### E. coli / oriented whole-phage electrochemistry

A 2026 study reports electric-field-assisted orientation of T4 phage on ITO electrodes and 15-minute E. coli detection in PBS and non-fat milk without pre-enrichment. It also reports a substantially smaller response to non-host *Staphylococcus aureus* under the tested conditions.

- PubMed: https://pubmed.ncbi.nlm.nih.gov/42107219/

### E. coli O157:H7 / phage electrochemical sensor

A published phage-electrochemical sensor reports detection of E. coli O157:H7 in less than 30 minutes in fresh milk and raw pork matrices.

- PubMed: https://pubmed.ncbi.nlm.nih.gov/36495704/

### Campylobacter / phage protein / EIS

A phage-protein impedimetric sensor using the engineered bioreceptor FlaGrab reports selective response to *Campylobacter jejuni* with non-target organisms used as specificity controls.

- PubMed: https://pubmed.ncbi.nlm.nih.gov/39194631/

These papers establish component-level feasibility. They do **not** establish that the proposed cartridge meets any performance target.

## 3. Proposed operational workflow

All times below are design allocations, not measurements.

1. **Surface sample — 0–5 min.** Operator wipes a defined area using a pre-wetted standardized sampler and inserts it into a closed elution vial/cartridge inlet.
2. **Load / mix — 5–7 min.** A measured aliquot contacts all sensing and control lanes.
3. **Capture — 7–17 min.** Passive or assisted binding occurs. Bench work determines whether flow, agitation, field orientation, or magnetic concentration is required.
4. **Electrochemical read — 17–22 min.** Reader obtains lane signals and control values.
5. **QC + result — 22–25 min.** Software rejects invalid controls, compares target lanes only against validated thresholds, records provenance and emits a human-readable result.

**Integrated target: ≤25 minutes**, leaving five minutes of margin against the challenge's 30-minute maximum. Until measured, this remains a target.

## 4. What is novel here — and what is not

No patentability claim is made. RBP/phage biosensors and electrochemical pathogen detection already exist in the literature.

The proposed product-level differentiation to investigate is a **professional-cleaning operational system**, not the assertion that any one sensing chemistry is new:

- multiplexed organism-specific phage-protein lanes in one sealed disposable;
- a standardized surface-cleaning sample protocol rather than a food-lab workflow;
- mandatory positive/negative controls with fail-closed reader behavior;
- result provenance (sample location, time, operator, cartridge lot, calibration, raw/control signal, human disposition);
- a pathway to integrate into cleaning QA without treating the sensor as an autonomous regulatory authority.

A freedom-to-operate and novelty review is required before any IP representation.

## 5. Initial target-organism strategy

Do not choose organisms solely because published binders are convenient. Diversey/customer context should determine the first panel. Candidate classes for discussion include food-safety and healthcare/facility organisms for which validated phage/RBP binders exist.

Selection gates:

1. material relevance to a professional-cleaning use case;
2. availability/licensability of a sufficiently selective binder;
3. compatible electrochemical immobilization chemistry;
4. expected environmental concentration and recovery from relevant surfaces;
5. cross-reactivity / host-range characterization;
6. stability and manufacturing pathway.

Strain-level identification is **not** a baseline claim. If the selected binder cannot establish strain specificity, the product should report species/group level only.

## 6. Development plan

### Phase A — target + assay architecture (weeks 0–2)

- Diversey/partner selects 1–2 high-value organisms and surface classes.
- Freeze success metrics, sample-area definition and false-result cost model.
- Select binder candidates and confirm access/IP path.
- Compare DPV vs EIS transduction for reader simplicity and robustness.

**Exit:** signed experiment plan; no performance claim yet.

### Phase B — single-target bench proof (weeks 3–6)

- Fabricate single-target + negative/control electrodes.
- Characterize response to target/non-target organisms in buffer.
- Measure time-to-result, repeatability, preliminary limit of detection and invalid-control behavior.

**Exit:** raw dataset + predefined analysis; kill/redesign if specificity or time target is not credible.

### Phase C — surface recovery + multiplex proof (weeks 7–10)

- Test representative stainless steel/polymer/food-contact surfaces as appropriate.
- Quantify sample recovery and matrix effects from cleaning residues.
- Add second target lane only after single-target behavior is stable.

**Exit:** measured end-to-end surface workflow or explicit failure report.

### Phase D — field-like pilot (weeks 11–16)

- Harden enclosure/cartridge handling.
- Blind samples and include negative/positive controls.
- Compare against an appropriate reference method selected with the domain partner.
- Evaluate basic-training usability and digital audit workflow.

**Exit:** go/no-go for product development, with all limitations retained.

## 7. Principal risks

| Risk | Why it matters | Mitigation / experiment |
|---|---|---|
| Binder host range is too narrow/broad | False negatives or false positives | Select binder from target-use-case panel; characterize against realistic near-neighbor strains |
| Surface recovery dominates sensor sensitivity | Clean-looking sensor may simply miss organisms | Separate recovery efficiency from electrode LoD; test surface/material/cleaner combinations |
| Dead cells remain detectable | Presence may not equal viable contamination | Decide whether use case needs viability; if yes, investigate a viability-specific adjunct rather than hiding limitation |
| Cleaning chemicals foul electrodes | Professional environments contain detergents/disinfectants | Negative/control lane + matrix challenge panel + sample-buffer optimization |
| Multiplex lanes cross-couple | One target could distort others | Prove single-target lanes first; physical/electrical isolation; randomized mixed-target tests |
| Sub-30-minute target fails | Challenge hard requirement | Time-budget every step; reject workflows needing enrichment/culture |
| Reader/cartridge cost too high | Blocks operational adoption | Screen-printed/economical electrode exploration and explicit BOM gate |
| Binder/electrode IP is encumbered | Could prevent prize license or partnership | Human/legal FTO before submission; prefer partner/licensable components |
| Solely AI-authored proposal is disfavored | Challenge explicitly says such submissions are not of interest | Human applicant materially rewrites and owns final narrative; record review gate |

## 8. Role split for a partnership

Commons' credible role is strongest in **evidence architecture, control logic, reader software, result provenance, auditability, reproducible analysis and fail-closed release boundaries**. Commons should not imply existing wet-lab biosensor expertise.

A wet-lab / biosensor partner or Diversey-side technical collaborator should own bioreceptor selection, electrode chemistry, microbiology protocol, experimental design review and laboratory validation. This division makes the collaboration path more truthful and potentially more valuable than pretending a software team already possesses every capability needed to commercialize the sensor.