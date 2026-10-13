# Technical Narrative — FerroFrame
## Supplier-flexible manufacturing architecture for alkaline all-soluble iron flow storage

> Phase 1 draft. Quantitative performance cited from literature is third-party evidence, not entrant test data.
> Checked-in manufacturing-cost examples are synthetic sensitivity cases, not supplier quotations.

### 1. Energy-storage solution and novelty

FerroFrame is a proposed design-for-manufacture architecture for a stationary, rechargeable aqueous all-soluble
iron redox-flow battery. It uses the power/energy decoupling inherent to flow systems: electrochemical stack area
sets power while externally stored electrolyte volume sets energy duration. The chemistry anchor is deliberately
not presented as new. Liu et al. reported an alkaline ferri/ferrocyanide and ferric/ferrous-gluconate system with
>99% coulombic efficiency, approximately 83% energy efficiency at 80 mA/cm², more than 950 cycles, and 12-, 16-,
and 20-hour cycling demonstrations. Their 10-hour, 9.9 kW system study projected $76.11/kWh. Those published
results establish technical plausibility and a cost reference; they are not FerroFrame measurements.

The proposed novelty is at the production architecture boundary. FerroFrame organizes the stack as a standardized
serviceable cassette with a common mechanical envelope, fewer bespoke wetted SKUs, controlled interfaces for
electrode/current-collection modules, and a membrane qualification envelope intended to support more than one
qualified source. The architecture also investigates factory-dry system integration and controlled site electrolyte
fill to avoid shipping water *only if* EHS, chemical stability, transport classification, and repeatability testing
support that route. We explicitly do not claim the membrane alternatives are interchangeable today.

Earlier all-soluble all-iron work and recent reviews identify membrane/ligand crossover, membrane resistance,
electrolyte stability, electrode behavior, and capacity fade as central technical constraints. A 2024 study also
shows that flow-over versus flow-through cell architecture materially changes performance. These findings make
mechanical/electrochemical interface design a first-order engineering variable rather than packaging decoration.

### 2. Production challenges that block scale

**Bespoke stack hardware and manual assembly.** Flow stacks can accumulate unique frame, gasket, flow-field,
electrode, current-collector, fastener, compression, and manifold parts. Each unique wetted SKU expands tooling,
incoming inspection, sealing validation, work instructions, and field spares. A design that works in a laboratory
fixture can therefore carry a conversion-cost penalty at production scale.

**Membrane dependence.** Ion-selective membranes are performance-critical. Prior all-soluble iron studies identify
ligand crossover and membrane resistance as failure mechanisms. A product architecture that silently assumes one
material or one vendor risks both technical lock-in and supply interruption. Conversely, “drop-in second source”
language would be unsafe without electrochemical qualification because transport/selectivity can change cell behavior.

**Liquid logistics and commissioning.** Aqueous flow storage moves substantial liquid mass. Factory filling can
simplify commissioning but increases shipped mass and may complicate packaging/transport. Site blending from
qualified inputs could reduce transported water but introduces chemical handling, concentration, water-quality,
QA, EHS, and operator-error risks. FerroFrame treats this as a testable make-versus-fill decision, not a presumed
saving.

**Evidence-poor cost claims.** A low-cost active material does not guarantee a low-cost manufactured system.
Membranes, electrodes, molded/machined hardware, pumps, tanks, tooling, labor, scrap, QA, and commissioning can
dominate or erase chemistry savings. STEP should reward a design that makes these cost drivers measurable before
scale-up.

### 3. Strategic design changes

**A. Standard cassette geometry.** Use a repeated cassette geometry so compression, port location, sealing lands,
electrode envelope, and service access are invariant across stack increments. The target is to move nonfunctional
variation out of the wetted stack and into configurable external manifolding. Candidate molded polymers, seal
materials, current collectors, and electrodes remain subject to alkaline/ferrocyanide/gluconate compatibility
testing.

**B. Qualification envelope rather than single membrane prescription.** Define mechanical dimensions, allowable
pressure drop, area resistance, selectivity/crossover, swelling, alkaline stability, and cycle-aging acceptance
tests for the separator/membrane interface. A second membrane becomes a qualified source only after passing the
same electrochemical and dimensional gates. This converts “multi-source” from a procurement assertion into a
repeatable technical process.

**C. Assembly simplification targets.** The Phase 2 design target is at least a 30% reduction in unique bespoke
wetted SKUs and at least a 25% reduction in direct stack assembly minutes relative to the selected reference build.
These are design targets, not achieved results. They will be measured by released BOM/router revisions and
time-stamped build observations.

**D. Quote-backed source-concentration gate.** The included exact-decimal model records component quantity,
unit price, qualified-supplier count, direct labor, and annualized tooling. It reports conversion cost per kW/kWh
and the percent of material value exposed to single-source components. Checked-in values are synthetic to exercise
the model. Phase 2 passes the manufacturing gate only with supplier-quote or purchase-evidence inputs and a
traceable baseline.

**E. Controlled electrolyte logistics decision.** Compare factory-filled, concentrate, and dry-input/site-fill
routes on shipping mass, packaging, mixing labor, water specification, QC, hazard classification, chemical
stability, and field error modes. No route is selected until an EHS/hazmat review and repeatability evidence close
the gate. The intent is to avoid transporting unnecessary water without trading that benefit for uncontrolled
chemical risk.

### 4. Likelihood of success and expected production impact

The architecture intentionally separates low-risk manufacturing changes from higher-risk electrochemical changes.
Frame standardization, BOM rationalization, assembly fixtures, traceable torque/compression, and supplier
qualification procedures can be developed before claiming improved cell performance. Membrane alternatives remain
behind cell-level validation. Electrolyte logistics remain behind EHS and chemistry gates.

Our quantitative method is therefore a falsifiable target system:

1. establish one reference stack BOM/router and one candidate cassette BOM/router at the same rated kW/kWh;
2. obtain comparable supplier quotations and record qualified-source count for every material-cost line;
3. measure direct assembly minutes on repeated builds;
4. calculate conversion-cost change and single-source value exposure with the checked-in model;
5. reject the production claim unless candidate cost is lower on quote-backed evidence and electrochemical
   qualification remains within predeclared acceptance limits.

The checked-in synthetic example shows how the calculation works, not what FerroFrame will save. It produces no
DOE score and cannot be promoted to quote-backed authority. Phase 2 target thresholds are ≥15% reduction in
quote-backed stack conversion cost per kW, ≥30% reduction in single-source material-value exposure, and the
SKU/labor targets above. If the actual data miss those thresholds, the design must be revised rather than the
baseline changed after the fact.

Supply resilience is aided by the chemistry’s reliance on iron rather than a scarce redox metal, but that does not
make the entire system domestically secure. DOE supply-chain work emphasizes component-level vulnerability in
battery systems. Membranes, polymers, electrodes, pumps, controls, and power electronics still need supplier
mapping. FerroFrame therefore measures concentration by component value and qualifies alternates where technically
possible instead of making a blanket “abundant chemistry = resilient product” claim.

### 5. Phase 2 validation plan

**Gate 1 — literature/IP/EHS.** Complete an independent patent/prior-art review of the cassette and logistics
claims; create a chemical hazard/compatibility matrix; define handling and waste controls; freeze a no-claim list
for unsupported safety/performance assertions.

**Gate 2 — materials coupons and membrane screen.** Test candidate wetted materials for dimensional/mass change and
visual degradation in representative electrolytes. Screen membranes for area resistance, crossover/selectivity,
swelling, chemical stability, and mechanical fit. Only passing materials enter cells.

**Gate 3 — single-cell electrochemical validation.** Reproduce a literature-grounded control before evaluating
architecture changes. Predeclare current density, temperature, electrolyte concentration, efficiency, capacity
retention, pressure drop, and leak criteria. A manufacturing idea cannot “pass” by degrading cell behavior outside
the declared limits.

**Gate 4 — repeated cassette build.** Build multiple mechanically identical units using released drawings, BOM,
router, fixtures, and QA checks. Record assembly minutes, rework, leakage, compression variation, and dimensional
yield. Compare to the reference build at equivalent rating.

**Gate 5 — supplier and cost evidence.** Obtain comparable quotes for the reference and candidate parts; document
source geography, lead time, minimum order, tooling, and alternate qualification status. Run sensitivity on the
largest cost and source-concentration drivers rather than a single-point estimate.

**Gate 6 — integrated prototype decision.** Only after the prior gates pass should the team scale stack area and
energy inventory. The prototype plan must preserve the truth boundary between chemistry literature, coupon/cell
measurements, stack manufacturing data, and system-level projections.

### 6. Commercialization path

The initial market is stationary long-duration storage where flow architecture’s independent sizing of power and
energy can be valuable and weight/volume constraints are less severe than mobility. The commercialization thesis is
not “iron is cheap, therefore the battery is cheap.” It is that an abundant-active-material chemistry becomes more
credible when paired with a manufacturable stack architecture, auditable supplier qualification, serviceable
modules, and quote-backed production evidence.

A credible partner set would include an electrochemistry laboratory, membrane/material suppliers, polymer or
composite fabricators, pump/tank/BOP suppliers, a contract manufacturer, and a stationary-storage integrator.
No partner commitment is claimed in this Phase 1 draft. The competitor background must identify the actual team
capabilities and gaps before submission.

A Phase 2 success would deliver: released cassette drawings and BOM; materials/membrane qualification matrix;
single-cell and repeated-stack evidence; baseline/candidate manufacturing routers; supplier-quote cost model;
source-concentration map; EHS/logistics decision; and a scale-up plan whose technical and manufacturing assumptions
are independently traceable.

### Generative-AI disclosure

Generative AI (OpenAI GPT-5.6 Sol) was used to help search and synthesize public sources, structure this draft,
develop the transparent scenario-model code and tests, and edit explanatory language. The entrant remains
responsible for every claim, citation, design choice, calculation, and submitted word. No generative system produced
or is represented as having produced laboratory measurements, supplier quotations, eligibility facts, partner
commitments, or prototype evidence.

### References

See `evidence/sources.md`. The official STEP rules control over this draft.
