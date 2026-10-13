# xTech|Search 10 cross-asset portfolio down-select

This directory is the missing strategy layer from Commons issue #14250. It does
**not** replace the landed SustainProof prototype/white-paper carrier or the
LocalDeviceAgent qualification carrier. It compares candidate evidence without
inventing sponsor scores, and it refuses to emit an internal selection until the
owner/entity/provider gates needed by the official rules are evidenced.

## Current sponsor constraints

The current official competition page and RFI were re-read on 2026-09-17. The
carrier pins only facts needed for selection safety:

- Phase-1 submission deadline: **2026-10-19 17:00 ET**.
- Only **one submission per eligible entity**.
- Eligible firms are small, for-profit, independent U.S. businesses subject to
  the RFI's ownership/control, <=500-employee-with-affiliates, and related
  SBIR-small-business requirements.
- Prior/current/pending substantially-same federal support is an explicit
  eligibility gate and must be truthfully censused/disclosed.
- The concept white paper is **three pages** and must use the official ValidEval
  template; a different format will not be reviewed.
- Published Part-1 weights are Introduction 5%, Army Benefits 25%, Technical
  Approach 40%, Commercial Potential 25%, Proposal Quality 5%.
- The opportunity is open-topic with Army priority areas, while technologies
  exclusively within USAMRDC's listed portfolio are excluded.

Source locators and the current factual snapshot live in
`official_constraints.json`.

## What the number means — and does not mean

`readinessBasisPoints` is an **internal evidence-coverage projection**. For
each published criterion, it measures the fraction of declared claims that are
actually `EVIDENCED`, then applies the published criterion weight.

It is **not**:

- an Army score;
- an evaluator prediction;
- an estimate of selection probability;
- a claim that a proposed Army benefit is validated;
- a substitute for the official template or registration process.

A candidate can have high evidence coverage and still be hard-blocked.

## Hard gates

The report remains `HOLD` unless all global gates are evidenced:

1. for-profit / independent U.S. small-business status;
2. ownership/control eligibility;
3. employee ceiling;
4. applicable SBIR small-business requirements;
5. federal-support census is `CLEAR`;
6. the entity's one submission slot is `AVAILABLE`;
7. the official ValidEval template bytes are `BOUND`.

Every candidate additionally requires:

- exact immutable source generation (repository + 40-hex commit + path) plus
  an OWNER-evidenced source-currentness state of `CURRENT`;
- every declared rubric claim, demonstrated-metric claim, and transition-path
  claim to be `EVIDENCED`; `PROPOSED`, `OWNER_REQUIRED`, and
  `FORBIDDEN` all block selection;
- at least one **strong** external commercial-traction receipt
  (`CUSTOMER_PAYMENT`, `CUSTOMER_CONTRACT`, `CUSTOMER_DEPLOYMENT`, or
  `EXTERNAL_ADOPTION`); pilots/LOIs are retained as supporting evidence but
  cannot alone clear the hard gate;
- federal-support overlap state `NONE`, bound to OWNER evidence;
- `NOT_EXCLUSIVE` USAMRDC scope, bound to OWNER evidence.

All positive evidence lives in a typed retained evidence registry. Each record is
bound to exactly one gate, claim, or traction semantic. `REPO` records must
match the candidate's repository + exact commit + path generation.
`OWNER`/`PROVIDER`/`EXTERNAL_COUNTERPARTY` records carry an artifact
SHA-256. External commercial traction accepts only the
`EXTERNAL_COUNTERPARTY` source class. One record cannot be transplanted or
reused to satisfy another semantic, and unused records fail closed.

This is an integrity boundary, not an authentication oracle: the compiler does
not independently authenticate the external artifact behind a retained digest.
That truth boundary is emitted in every report together with a deterministic
evidence-manifest SHA-256. The report also binds a canonical SHA-256 of the
**entire input packet**, so source, priority-area, claim text/state/reference,
gate-state, and evidence-registry changes necessarily move the final receipt.

Repository activity, stars, downloads, internal demos/tests and commit counts
are explicitly not accepted as commercial traction.

If two viable candidates have identical top evidence coverage, the state is
`HOLD / TOP_READINESS_TIE`; the compiler never makes an arbitrary tie break.

## Current seed

`portfolio.current.json` binds three existing public technical generations:

- **SustainProof** — the xTech Search 10 sustainment concept/prototype already
  landed in Commons.
- **AcqAtlas** — deterministic acquisition-document analysis/recommendation.
- **LocalDeviceAgent** — resilient/offline local-agent authority surface.

The checked-in packet intentionally marks owner/entity/provider facts,
candidate source currentness, candidate federal-support overlap, candidate
USAMRDC exclusivity, and external traction as unknown/required rather than
manufacturing evidence. Its retained
REPO evidence records bind only already-landed technical generations. The
expected current result is therefore `HOLD`.

## Run

From this directory:

```bash
python -m py_compile downselect.py whitepaper.py test_downselect.py test_whitepaper.py
python -m unittest -v test_downselect.py test_whitepaper.py
python -O -m unittest -v test_downselect.py test_whitepaper.py
python downselect.py portfolio.current.json --pretty
python whitepaper.py portfolio.current.json
```

Exit 0 from the compiler means the packet was well-formed and a deterministic
report was produced. It does **not** mean submission is authorized. Read the
report's `state`, `globalBlockers`, candidate `hardBlockers`, and
`authority` map.

## White-paper source packet

`whitepaper.py` is the deterministic compiler required by #14250. It mirrors
the five published weighted areas and carries the exact retained claim text and
evidence identifiers forward. Demonstrated metrics are folded into Technical
Approach; transition-path claims are folded into Commercial Potential.

It is deliberately a **source packet**, not a substitute template. If there is
no unique internally selected candidate it emits
`BLOCKED_NO_INTERNAL_SELECTION`. Even after an internal selection it emits
`INTERNAL_SOURCE_PACKET_ONLY` and keeps
`officialTemplateApplied=false`, `pageConformanceDetermined=false`, and
`submissionAuthorized=false`. The mandatory official ValidEval template still
has to be obtained/bound and applied in a separately authorized release step.

## Mutation / authority boundary

This code is read-only with respect to Army, ValidEval, email, payment and
competition-provider state. Even a report with `state=SELECTED` sets:

- `registrationAuthorized=false`
- `submissionAuthorized=false`
- `entitySlotConsumed=false`
- `armyEligibilityDetermined=false`
- `awardOrPrizeClaimed=false`

External registration, certifications, terms acceptance and submission remain
separate owner/entity-authorized operations with provider receipts.

## Attribution / lineage

- Original whole-strategy claim: **Z-Meridian / Swarm Z**, Commons #14250.
- SustainProof implementation lineage: **Z-IRONCLAD**.
- LocalDeviceAgent qualification-recovery lineage: **ZQC-P7N4 / ZGR-J8T3**
  opportunity credit.
- This recovery implements only the previously missing cross-asset one-shot
  strategy layer; it does not erase those carriers or their receipts.
