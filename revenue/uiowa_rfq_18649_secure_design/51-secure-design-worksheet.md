# Secure-design requirements worksheet

**SYNTHETIC.** Every requirement, design decision, data flow and artifact below is fictional, written to exercise the instrument. Nothing here describes the University of Iowa, and no row is a finding.

## Reference frame

NIST SP 800-218, Secure Software Development Framework (SSDF) — https://csrc.nist.gov/Projects/ssdf

| practice | paraphrase written for this worksheet |
|---|---|
| `PO.1.1` | PARAPHRASE: identify and document the security requirements that apply to the organization's software development. |
| `PW.1.1` | PARAPHRASE: use risk modelling -- threat modelling, data-flow modelling, attack surface analysis -- to inform design. |
| `PW.1.2` | PARAPHRASE: track and maintain the software's security requirements, risks and design decisions. |
| `PW.2.1` | PARAPHRASE: have a qualified person review the design to confirm it meets the security requirements and addresses the identified risks. |

**SSDF practice identifiers organize this instrument only. No output here is a conformance statement, certification, attestation, compliance verdict or assessment against the framework. The descriptions above are paraphrases written for this worksheet, not quotations; the authoritative wording is at https://csrc.nist.gov/Projects/ssdf.**

## The three states, and the fourth

| state | meaning |
|---|---|
| `OBSERVED_PRACTICE` | An artifact exists for this requirement at its current version. What it shows is a matter for the reviewer; that it exists is observed. |
| `TRACED_STALE` | A design artifact cites this requirement, but at a superseded version. The link still resolves, and it resolves to text that has since changed. Neither traced nor untraced. |
| `DOCUMENTED_INTENT` | A standard, template or policy says this should happen. That is evidence about an intention. It says nothing about whether this design decision did it. |
| `UNKNOWN` | Nothing has been supplied for this requirement and this design decision. An open question -- not a gap, and not a pass. |

`TRACED_STALE` is the state worth building the worksheet around. It is the case that looks correct in a traceability matrix: the link resolves, the artifact exists, and it cites a version of the requirement that has since changed. Nothing errors. Nothing is missing. The trace is simply pointing at the wrong text.

## Result

4 requirements, 5 design decisions, 6 requirement-to-decision links assessed. 2 requirement(s) have changed since version 1.

| state | links |
|---|---:|
| `OBSERVED_PRACTICE` | 2 |
| `TRACED_STALE` | 1 |
| `DOCUMENTED_INTENT` | 2 |
| `UNKNOWN` | 1 |

## The matrix

| decision | requirement | v | flow | state | next step |
|---|---|---:|---|---|---|
| `DD-SYN-01` | `SEC-REQ-SYN-01` | 3 | FLOW-SYN-01 | **TRACED_STALE** | The trace points at SEC-REQ-SYN-01 v2, superseded by v3. Ask what changed between those versions and whether DD-SYN-01 was revisited. This is the case that looks fine in a traceability matrix. |
| `DD-SYN-01` | `SEC-REQ-SYN-03` | 2 | FLOW-SYN-01 | **OBSERVED_PRACTICE** | — |
| `DD-SYN-02` | `SEC-REQ-SYN-02` | 1 | FLOW-SYN-02 | **OBSERVED_PRACTICE** | — |
| `DD-SYN-03` | `SEC-REQ-SYN-03` | 2 | FLOW-SYN-03 | **DOCUMENTED_INTENT** | A standard requires this; nothing shows DD-SYN-03 applied it. Ask for the design record or review note for this decision specifically. A template that says a section should exist is not that section. |
| `DD-SYN-04` | `SEC-REQ-SYN-04` | 1 | FLOW-SYN-04 | **DOCUMENTED_INTENT** | A standard requires this; nothing shows DD-SYN-04 applied it. Ask for the design record or review note for this decision specifically. A template that says a section should exist is not that section. |
| `DD-SYN-05` | `SEC-REQ-SYN-01` | 3 | FLOW-SYN-01 | **UNKNOWN** | Ask for any artifact that shows DD-SYN-05 considered SEC-REQ-SYN-01: a design decision record, a data-flow or threat model covering the flow, or a design review note. If none exists, that is the finding -- do not infer one from the standard. |

## Gaps that are not link states

_Every requirement is cited by at least one decision._

**Data flows no requirement claims** — the ones crossing a trust boundary are the interview question:

| flow | description | data | crosses trust boundary |
|---|---|---|---|
| `FLOW-SYN-05` | Nightly copy of the reporting store to an analytics sandbox | identifiable records | **yes** |

**Decisions naming a requirement that is not in the register** — not counted as traced or untraced, because the link cannot be assessed at all:

- `DD-SYN-04` → `SEC-REQ-SYN-99` — the decision names a requirement that is not in the register; the link cannot be assessed and is not counted as either traced or untraced

## Interview questions

Each asks for an artifact, because a description of the process is not evidence about a decision.

1. Take one requirement that has changed. Which design decisions were revisited, and what record shows that?
2. When a security requirement is revised, what makes the design decisions that cited the old version visible?
3. For one data flow crossing a trust boundary, which requirements apply, and which artifact shows the design considered them?
4. Who reviews a design against its security requirements, and what do they leave behind?
5. Where a standard requires a design section, can you show that section for a recent change?

## Limits

- Every requirement, decision, flow and artifact here is fictional. Nothing describes the University of Iowa and no row is a finding.
- OBSERVED_PRACTICE means an artifact exists and cites the current requirement version. Whether the artifact is any good is a matter for the reviewer; this instrument does not read its contents.
- DOCUMENTED_INTENT is never upgraded by volume. Ten standards are still zero design records.
- UNKNOWN is never scored as a gap or as a pass. It is an open question and is reported as one.
- SSDF is a reference frame here. No output is a conformance, certification or compliance claim.
- No individual is assessed. The subject is always an artifact's existence and what it cites.
