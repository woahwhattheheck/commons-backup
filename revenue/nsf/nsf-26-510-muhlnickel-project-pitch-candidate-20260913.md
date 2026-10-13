# NSF 26-510 · Muhlnickel Project Pitch candidate

**Operation:** `NSF-SBIR-26-510-PITCH-PACKET-ZNST6K8-20260913`  
**Prepared by:** Z-NoetherSundial-2315-T6K8 (`ZNS-T6K8`) / GPT-5.6 Sol  
**Status:** `PREP_ONLY_DO_NOT_SUBMIT`  
**External actions performed:** none. No NSF account creation, portal use, Project Pitch submission, full proposal, contact, registration, award, payment, or revenue claim.

## Why this exists

The current NSF 26-510 solicitation is active. Phase I proposals may request up to **$305,000** and the next listed full-proposal deadline is **November 4, 2026 at 5 p.m. submitting-organization local time**, but Phase I requires an official invitation obtained through the Project Pitch process first.

Current Project Pitch instructions ask for four bounded fields:

| Field | Current ceiling | Candidate below |
| --- | ---: | ---: |
| Technology Innovation | 3,500 characters | 2,093 |
| Technical Objectives and Challenges | 3,500 characters | 2,227 |
| Market Opportunity | 1,750 characters | 1,485 |
| Company and Team | 1,750 characters | 1,320 |

Official sources checked for this packet:

- NSF 26-510 current solicitation: https://www.nsf.gov/funding/opportunities/small-business-innovation-research-small-business-technology/nsf26-510/solicitation
- NSF Project Pitch current instructions: https://seedfund.nsf.gov/apply/project-pitch/
- NSF technology-fit assessment: https://seedfund.nsf.gov/apply/the-basics/
- NSF R&D definition: https://seedfund.nsf.gov/research-and-development/

This is a **candidate drafting artifact**, not evidence that the company or project is eligible. NSF currently restricts concurrent Project Pitches and invitations/proposals; submission is therefore a scarce external act and must not be triggered by this file.

## Submission STOP conditions

Do **not** copy this into an NSF portal until all of these are separately verified against current provider truth and owner records:

1. Legal proposing-company name, U.S. location, organization status, and qualifying small-business status.
2. Ownership satisfies the current SBIR/STTR eligibility rule.
3. Proposed PI has the required legal work status, company employment relationship, and effort commitment for the contemplated award period.
4. The company has no pending Project Pitch, open invitation/full proposal, or other state that forbids another pitch; annual and same-technology submission limits are checked immediately before submission.
5. The owner approves what technical/IP information may be disclosed in the Project Pitch and what must remain private.
6. The first commercial wedge is chosen and the strongest available customer-discovery evidence is inserted. This draft does **not** invent market size, willingness-to-pay, customer commitments, or partner commitments.
7. Company founding date/status, revenue/funding history, team roles, facilities/resources, consultants/subawardees, and IP strategy are supplied from evidence rather than guessed.
8. Current NSF instructions are reread on the day of any submission. If the provider fields/limits have changed, this packet is stale.

## NSF fit gate — candidate assessment, not eligibility

| NSF fit question | Candidate state | What still has to be proven |
| --- | --- | --- |
| Real technological innovation | `CANDIDATE_YES` | State-of-art comparison and prior-art/competitive evidence. |
| Risky, unproven R&D | `CANDIDATE_YES` | Pre-register quantitative go/no-go thresholds and benchmark corpus. |
| Significant national/economic impact | `HYPOTHESIS` | Choose first use case and quantify credible impact without invented numbers. |
| Durable competitive advantage | `UNKNOWN` | Prior art, replication difficulty, IP/open-source strategy, and freedom-to-operate work. |
| Commercial potential | `UNKNOWN` | Customer discovery, market sizing, procurement path, pricing evidence. |
| Qualified/dedicated team | `PARTIAL` | Evidence team capacity, adviser gaps, facilities/resources, PI effort. |
| Engaged technical project lead | `CANDIDATE_YES` | Verify PI employment/eligibility facts before portal use. |

A `CANDIDATE_YES` is a drafting judgment only. It is not an NSF eligibility finding.

---

## Candidate field 1 — Technology Innovation

Muhlnickel is a research-stage file-native computation substrate: instead of treating a file only as passive data or as source/bytecode that must be interpreted by a conventional program, the serialized artifact encodes an addressable computational topology whose state transitions are the computation. The research question is whether useful deterministic computation can be reduced to a bounded, portable topology in which an addressed read/trigger activates the encoded circuit without a host-side polling loop or a farm of subprocesses standing in for the computation.

The origin of the work is a series of prototype artifacts and related topological components developed in Commons. Those prototypes motivate, but do not yet prove, the general claim. The unproven innovation is a rigorous execution model that makes the artifact itself the durable computational object: topology, state, provenance, and reproducible transition behavior travel together. If successful, this could narrow the gap between “the bytes that were reviewed” and “the computation that later ran,” which is difficult to guarantee in layered software stacks where behavior depends on mutable runtimes, package graphs, services, and orchestration.

The Phase I R&D would focus on the substrate, not on a conventional application wrapper. The scientific/engineering novelty to test is whether a constrained cell/topology algebra can express nontrivial stateful computations while preserving deterministic serialization, bounded activation semantics, exact replay, and analyzable depth/resource growth. The work is high-risk because the approach may fail to scale, may require hidden host computation that defeats the premise, or may exhibit depth/file-size growth that erases any practical advantage. Those are explicit go/no-go questions, not assumptions.

A successful result would be a measured, falsifiable execution model and prototype toolkit for creating, validating, and replaying file-native compute artifacts, with clear limits where the model does not outperform or simplify conventional approaches.

**Character count:** 2,093 / 3,500.

---

## Candidate field 2 — Technical Objectives and Challenges

Phase I would answer four technical questions.

1. Semantics and equivalence. Define a small formal cell/topology model, serialization rules, activation semantics, and a reference evaluator. Build differential tests that compare artifact behavior with independently implemented reference functions. Go/no-go: identical outputs and state transitions for a fixed benchmark corpus across independently built evaluators, with any nondeterminism treated as failure.

2. Host-independence boundary. Instrument the prototype so every host operation used to load, trigger, and observe an artifact is enumerated. Test whether computation is actually carried by the encoded topology rather than hidden loops, polling, subprocess fan-out, or external services. Go/no-go: the claimed file-native path must have a bounded, auditable host boundary; if substantial application logic remains in the host, the core hypothesis is rejected or narrowed.

3. Scaling laws. Construct benchmark families that increase topology width, dependency depth, state size, and fan-out. Measure serialized bytes, build cost, activation steps, memory use, and replay latency. Fit empirical growth curves and identify breakpoints. Go/no-go thresholds will be fixed before benchmark execution so the project cannot redefine success after observing results.

4. Reproducibility and fault behavior. Test byte-stable serialization, corruption detection, partial-write handling, state provenance, and replay across supported host environments. Introduce controlled bit/record mutations and verify that changed artifacts are detected or produce explicitly different receipts rather than silently aliasing prior results.

These tasks are R&D because the central feasibility and scaling properties are unknown. The deliverable is not merely a polished compiler or UI; it is experimental evidence establishing where the topology model works, where it fails, and whether its execution/provenance properties justify a commercial product. Positive Phase I results would support a product path for verifiable compute capsules and domain-specific file-native engines; negative results would still establish quantitative limits and prevent unsupported commercialization claims.

**Character count:** 2,227 / 3,500.

---

## Candidate field 3 — Market Opportunity

Near-term customers are teams that need deterministic, inspectable computation to survive handoffs, audits, offline operation, or long-lived reproducibility requirements: infrastructure/tooling teams, regulated or high-assurance engineering groups, edge/offline systems builders, and developers of autonomous-agent workflows. Their pain is not a lack of general-purpose compute; it is the difficulty of proving that the computation executed later is the same reviewed artifact and dependency state that was approved earlier.

Current approaches rely on containers, lockfiles, virtual machines, workflow engines, or signed packages. These are powerful but still compose multiple mutable layers and often separate executable logic from its evidence trail. Muhlnickel’s proposed wedge is narrower: a deterministic compute capsule in which serialized topology, state, and replay receipt are designed as one object.

The initial commercial hypothesis is tooling and paid engineering for high-assurance reproducible workflows, followed by licensing/support for domain-specific file-native engines if Phase I establishes a durable technical advantage. Market size, willingness-to-pay, procurement requirements, and the strongest first vertical remain validation tasks; this draft intentionally does not invent them. Existing paid diagnostic/outreach activity in the broader business is evidence of commercialization effort, not evidence that customers have validated this specific technology.

**Character count:** 1,485 / 1,750.

---

## Candidate field 4 — Company and Team

Bryce is the technical lead and originator of the Muhlnickel/file-native computation work. His work centers on systems and computation, including custom computational substrates, deterministic evidence/receipt tooling, and agent-oriented infrastructure. The current prototypes and public Commons artifacts were developed through iterative implementation, adversarial testing, and cross-session engineering rather than as a paper-only concept.

For Phase I, the intended company role is founder/PI leading substrate semantics, prototype implementation, benchmark design, and commercialization discovery. Before any Project Pitch is submitted, the company must separately verify and document NSF eligibility: legal entity and U.S. location, qualifying small-business status and ownership, PI legal work eligibility and primary-employment commitment, the absence/presence of conflicting pending NSF pitches or invitations, and the availability of U.S.-based personnel/resources for the work.

Team gaps are explicit. A strong Phase I plan may require an independent formal-methods/reproducibility reviewer and domain advisers for the first commercial vertical. No adviser, subawardee, registration, IP position, revenue history, or customer commitment is claimed by this draft unless separately evidenced before submission.

**Character count:** 1,320 / 1,750.

---

## Phase I experiment skeleton — prep for later owner review

This section is **not** ready to paste into a portal. It is the next evidence task if the Project Pitch is invited or if the owner decides to strengthen the pitch first.

### Work package A — formal execution model

- Freeze the minimal cell/topology semantics and canonical serializer.
- Define the host boundary and what operations count as substrate work versus harness work.
- Build at least two independently implemented evaluators for the frozen semantics.
- Pre-register equivalence and nondeterminism failure criteria.

### Work package B — benchmark families and scaling

- Select representative stateful kernels before running the funded experiments.
- Generate controlled families varying width, depth, fan-out, state size, and mutation rate.
- Measure artifact size, build cost, activation work, memory, replay latency, and failure mode.
- Publish negative regions and crossover points rather than optimizing only for demonstrations that win.

### Work package C — integrity and reproducibility

- Byte-stable serialization and replay receipts.
- Corruption, partial-write, version drift, and changed-state experiments.
- Cross-environment replay on a frozen support matrix.
- Prove or falsify that the reviewed artifact can carry enough execution/provenance identity to reduce mutable-stack ambiguity.

### Work package D — commercialization discovery

- Pick one first vertical only after evidence, not by narrative preference.
- Interview/observe prospective users about reproducibility, offline execution, audit, and deployment pain.
- Record current workaround, switching cost, purchase authority, required certifications/integration, and willingness-to-pay evidence.
- Use discovery results to narrow the technical benchmark corpus; do not retrofit customer claims that were never observed.

## Evidence that must replace placeholders before submission

- Company legal/eligibility facts: **MISSING / OWNER-PROVIDER RECORD REQUIRED**.
- Pending NSF pitch/invitation/proposal state: **MISSING / CHECK PROVIDER IMMEDIATELY BEFORE SUBMISSION**.
- PI employment and required effort: **MISSING / OWNER RECORD REQUIRED**.
- IP/public-disclosure strategy: **MISSING / OWNER LEGAL-BUSINESS DECISION REQUIRED**.
- Prior-art and competitive technical comparison: **MISSING / RESEARCH REQUIRED**.
- First customer vertical: **MISSING / DISCOVERY REQUIRED**.
- Quantified market size: **MISSING / EVIDENCE REQUIRED**.
- Customer willingness-to-pay/commitments: **MISSING / DO NOT INVENT**.
- Team advisers/subawardees: **NONE CLAIMED**.
- NSF invitation: **NOT CLAIMED**.
- Award: **NOT CLAIMED**.
- Cash/revenue from NSF: **$0 CLAIMED BY THIS PACKET**.

## Last-inch submission fence

Immediately before any future NSF Project Pitch portal mutation:

1. Fresh-check NSF instructions, pitch limits, pending company state, and eligibility.
2. Fresh-check Slack/provider ownership so two swarm seats cannot consume or overwrite the same scarce external submission.
3. Owner-review the exact four final fields and disclosure/IP boundary.
4. Retain a pre-submit immutable copy and hashes of the exact field bytes.
5. Submit exactly once through the verified NSF provider/account; record the provider receipt rather than inferring success from a button click.
6. Do not call a Project Pitch an invitation, proposal, award, payment, or revenue.

Until those conditions are satisfied, the correct action is **improve evidence, not submit**.
