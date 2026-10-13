# UIOWA-023 — Evidence confidence and provenance method

Status: PROPOSED ASSESSMENT METHOD / NOT A UNIVERSITY FINDING  
Owner: ZZ-Semaphore / GPT-5.6 Sol  
Scope: University of Iowa RFQ 18649 preparation assets

This method defines how an assessment team can describe the strength of evidence without turning confidence into a maturity score. It is designed for the ESS, RIS, and IAM workstreams and the four assessment areas: software development, security, deployment/operations, and AI readiness.

The method is deliberately conservative. A polished interview answer is not treated as proof of implementation. A missing artifact is not treated as proof that a practice does not exist. A current artifact from one service is not silently generalized to every service. Materially contradictory evidence remains unresolved until the contradiction is explained or bounded.

## 1. Evidence chain

Every material recommendation should be traceable through four distinct layers:

1. **Evidence item (EV-)** — a source that was actually observed: interview note, policy, configuration export, change record, runbook, metric extract, inventory query, incident record, or other authorized artifact.
2. **Observation (OBS-)** — a narrow statement of what that evidence establishes, including scope and time.
3. **Finding (FND-)** — a synthesis across one or more observations. Findings include support, counter-evidence, confidence, and an inference boundary.
4. **Recommendation (REC-)** — a proposed action linked to one or more findings. Recommendations do not inherit certainty automatically; they state which findings motivate them.

The chain is many-to-many. One evidence item can support more than one observation only when each observation stays inside the source's actual scope. A finding may have both supporting and contradicting observations. A recommendation may depend on several findings.

## 2. Identifier convention

Use stable identifiers that survive document moves and report revisions.

- Evidence: EV-<GROUP>-<AREA>-<TYPE>-NNN
- Observation: OBS-<GROUP>-<AREA>-NNN
- Finding: FND-<GROUP>-<AREA>-NNN
- Recommendation: REC-<GROUP>-<AREA>-NNN

GROUP is ESS, RIS, or IAM. AREA is SD, SEC, DEP, or AI. TYPE is a short source class such as INT, CFG, POL, MET, CHG, INV, INC, or DOC.

Synthetic examples in the companion register use a SYN marker so they cannot be confused with University evidence.

## 3. Required provenance fields

Every evidence item must record, at minimum:

- evidence_id
- observation_id
- group and assessment area
- source_type
- source reference or authorized artifact locator
- capture time
- period or point in time represented by the source
- the exact narrow claim the source supports
- source scope and known exclusions
- source owner or authority class when known
- directness
- recency status
- representativeness
- corroboration
- conflict group, when applicable
- evidence state
- confidence classification
- linked finding identifier

Sensitive source locations can be replaced with controlled internal locators in deliverables, but the evidence register used by the assessment team must retain enough custody metadata to re-open or re-request the source.

## 4. Five confidence dimensions

Confidence is a statement about **support for an observation or finding**, not a statement about process maturity.

### 4.1 Source type / authority

Record what kind of source is being relied upon and why it is authoritative for the narrow claim.

Examples:
- A system-generated configuration export is strong for what that configuration contained at capture time.
- A policy is strong for documented intent, but not for actual implementation.
- An interview is strong for participant perspective, but not automatically for organization-wide practice.
- A bounded inventory query can be strong for existence/non-existence inside the exact queried universe.

Do not convert source type into a universal numeric trust score. Authority depends on the claim.

### 4.2 Directness

Classify how directly the evidence bears on the claim.

- **Direct** — the source records the practice, event, state, or control being assessed.
- **Near-direct** — the source records an adjacent mechanism or outcome from which a limited inference is reasonable.
- **Indirect** — the source is testimony, summary, policy intent, or contextual material that does not itself demonstrate the claimed practice.

Direct evidence can still be narrow, stale, or unrepresentative.

### 4.3 Recency

Recency answers whether the source is recent enough for the claim being made.

The review team must define the relevant freshness window before interpreting a source. Volatile configuration and deployment evidence normally needs a shorter window than stable governance documents. The existing RFQ workshare compiler uses a 120-day freshness rule for its synthetic technical evidence model; that rule is not automatically a University-wide standard.

Classify each item as:
- CURRENT — within the defined window for this source/claim.
- AGING — still usable but close to the declared boundary.
- STALE — outside the declared window or superseded.
- UNKNOWN — source date or represented period is not reliable enough to classify.

A stale source may still establish historical context. It should not be represented as current practice without additional support.

### 4.4 Representativeness

Representativeness answers how far the evidence may be generalized.

- **Population-bounded** — the source covers a declared complete universe, such as an authoritative inventory query over all in-scope repositories at a stated time.
- **Sampled** — the source covers a documented sample with a selection rationale.
- **Single-service / single-event** — useful evidence, but local to one service, repository, team, change, or incident.
- **Unknown** — the source's coverage cannot be established.

Do not silently generalize single-service evidence across ESS, RIS, IAM, or across all applications within a group.

### 4.5 Corroboration

Corroboration asks whether materially independent evidence points the same way.

- **Independent corroboration** — another source produced through a meaningfully different mechanism supports the same narrow claim.
- **Same-system corroboration** — another record from the same system supports the claim but shares failure modes.
- **No corroboration observed** — no second source has been reviewed.
- **Contradicted** — a material source points the other way.

Two copies of the same policy, or an interview quoting the same dashboard, are not independent corroboration.

## 5. Confidence classifications

Confidence is assigned after the five dimensions are recorded. Do not average the dimensions into a hidden score.

### HIGH

Use HIGH only when the finding has direct, current evidence; its scope is representative of the claim being made; and either:
- there is independent corroboration, or
- the source is an authoritative population-bounded record whose completeness is itself documented.

HIGH does not mean the underlying practice is mature. It means the stated finding is strongly supported.

### MODERATE

Use MODERATE when the core claim is supported by current evidence but one material limitation remains, such as:
- narrow sample coverage;
- a single-service artifact being used only for a single-service finding;
- near-direct evidence plus independent corroboration; or
- an authoritative bounded query whose completeness is credible but not fully demonstrated.

The limitation must be stated next to the finding.

### LOW

Use LOW when evidence is plausible but materially limited, such as:
- interview-only support;
- stale documentation with no current implementation evidence;
- a very narrow convenience sample;
- indirect evidence without corroboration.

LOW findings can still be useful as discovery leads. They should not be presented as settled facts.

### UNRESOLVED

Use UNRESOLVED when credible evidence materially conflicts and the conflict changes the interpretation. Preserve both sides and issue a focused follow-up request. Do not select whichever source sounds more formal.

### NOT_EVIDENCED

Use NOT_EVIDENCED when the team has not obtained evidence that supports the claim. This is a statement about the assessment evidence set, not a statement that the practice is absent.

## 6. Missing evidence is not evidence of absence

Use **NOT_EVIDENCED** when:
- an artifact was requested but not supplied;
- a keyword search returned no result;
- an interview participant did not know;
- the sample did not encounter an example;
- a repository or service was not in the reviewed sample.

A true **EVIDENCE_OF_ABSENCE** statement requires all of the following:

1. **Defined universe** — the exact population being queried is named.
2. **Authoritative enumerator** — the source is capable of enumerating that population.
3. **Completeness basis** — there is a reason to believe the query/export covers the declared universe.
4. **Current capture** — the source is fresh enough for the negative claim.
5. **Negative semantics** — the source's absence result actually means “not present” rather than “not indexed”, “not visible to this user”, “not sampled”, or “not retained”.

If any condition is missing, use NOT_EVIDENCED or a narrower statement.

Example:
- Supportable: “As of 2026-09-18, the synthetic authoritative inventory covering all 14 in-scope ESS repositories returned zero approved AI-assistant integrations.”
- Not supportable: “No ESS team uses AI” because two repositories did not contain an AI configuration file.

## 7. Contradictory evidence protocol

When material sources conflict:

1. Create separate evidence items for each source.
2. Link them to separate observations.
3. Assign the same conflict_group.
4. Keep each observation's source scope and period explicit.
5. Set the affected synthesis to UNRESOLVED unless the conflict can be bounded by time, service, role, or exception class.
6. Request the smallest follow-up evidence that can discriminate between explanations.

Common explanations to test include:
- policy is stale while practice changed;
- policy is current but exceptions are allowed;
- management describes intended process while practitioner artifacts show operational variance;
- two services use different workflows;
- one artifact captures an emergency exception rather than normal practice.

A resolved contradiction must record why both original sources could have been true, or why one source was not applicable to the final claim.

## 8. Worked synthetic cases

The companion CSV contains synthetic rows only. They are not University findings.

### Case A — interview claim

A synthetic ESS developer says peer review is always required. The interview is current but indirect, represents one person's perspective, and has no artifact corroboration.

Result: LOW.  
Next step: request a branch-protection or pull-request sample before making an organization-wide finding.

### Case B — current artifact

A synthetic ESS repository export shows a required build-and-test status check before merge. The artifact is direct and current, but covers one repository only.

Result: MODERATE for that repository.  
It does not establish that every ESS repository uses the same control.

### Case C — stale artifact

A synthetic RIS security standard is 18 months old and no current implementation evidence has been supplied.

Result: LOW for current-practice claims; usable as historical or policy-intent context.  
Next step: obtain a current configuration, procedure, or recent implementation example.

### Case D — conflicting records

A synthetic IAM deployment procedure requires two approvals, while a current sample of change records repeatedly shows one approval.

Result: UNRESOLVED.  
Next step: determine whether the sample reflects an exception path, a superseded procedure, or a gap between documented and actual practice.

### Case E — evidence of absence

A synthetic authoritative ESS inventory query declares a complete population of 14 in-scope repositories and returns zero approved AI-assistant integrations at a stated capture time.

Result: MODERATE evidence of absence inside that bounded universe.  
The statement must remain bounded to the declared repositories, approval state, and capture time.

## 9. Finding template

Every material finding should contain:

- **Finding ID**
- **Statement**
- **Scope**
- **Supported by** — evidence/observation IDs
- **Counter-evidence** — evidence/observation IDs
- **Confidence** — HIGH / MODERATE / LOW / UNRESOLVED / NOT_EVIDENCED
- **Why this confidence**
- **Inference boundary**
- **Follow-up needed**
- **Related recommendations**

Example language:

“FND-SYN-ESS-SD-001 — One sampled synthetic repository enforces a build-and-test status check before merge. Confidence: MODERATE. Evidence is direct and current for that repository but is not representative of all ESS repositories. Additional repository sampling is required before making a group-wide characterization.”

## 10. Recommendation linkage

A recommendation must not imply stronger evidence than the linked findings.

- If a finding is HIGH or MODERATE, a recommendation may address the documented condition while retaining scope limits.
- If a finding is LOW, frame the recommendation as validation, clarification, or low-regret improvement unless separate evidence supports a stronger action.
- If a finding is UNRESOLVED, recommend targeted follow-up before presenting a definitive root cause.
- If a finding is NOT_EVIDENCED, the first recommendation is usually to obtain or define the missing evidence, not to assume failure.

## 11. Review controls

Before a finding enters a draft report, verify:

- every source has a stable evidence ID;
- every observation cites one or more evidence IDs;
- every finding cites observations, not free-floating narrative;
- confidence is separate from maturity;
- stale evidence is labeled;
- single-service evidence is not generalized;
- contradictions are preserved;
- missing evidence is not rewritten as absence;
- evidence-of-absence claims satisfy the five-condition gate;
- recommendation language does not exceed the linked finding confidence;
- synthetic or rehearsal material is visibly labeled.

## 12. Machine-checkable companion register

The companion file 23-synthetic-evidence-register.csv demonstrates the required fields and cases. The validator validate_23_evidence_register.py checks structural invariants:

- unique EV identifiers;
- syntactically valid OBS/FND links;
- allowed group/area/confidence/state values;
- conflict rows must be UNRESOLVED and carry a conflict_group;
- NO_EVIDENCE_OBSERVED must be NOT_EVIDENCED;
- EVIDENCE_OF_ABSENCE requires a defined universe, authoritative enumerator, and completeness basis;
- stale evidence cannot be labeled HIGH;
- all rows must preserve source scope and claim text.

Passing the validator proves only that the register is structurally coherent. It does not prove that any real-world claim is true.
