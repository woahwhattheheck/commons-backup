# UIOWA-114 — Follow-up interview question cards

Built for work order **UIOWA-114** (University of Iowa RFQ 18649 preparation) by seat
`OP5-FLINT`, Claude Opus 5.

Turns **one unresolved observation** into **the one question that would resolve it** — with
the context a practitioner needs, a concrete artifact to ask for, and the decision the answer
would change. Cards are searchable and linked back to the evidence and interview registers.

> **Everything in `data/` is FICTION.** The observations, sources, locators, roles, incidents
> and services (ESS / RIS / IAM) are invented for this kit. Nothing here is a University of
> Iowa finding, document or person, and **no interview has been conducted, requested or
> scheduled.**

## Run it

```
cd revenue/uiowa_rfq_18649_question_cards

python3 question_cards.py build                              # write examples/
python3 question_cards.py check                              # exit 1 if any card is rejected
python3 question_cards.py check --observations observations_hostile.json --out /tmp/h
python3 question_cards.py search --query "role:iam_administrator"
python3 question_cards.py search --query "type:ABSENT_EVIDENCE inventory"
python3 question_cards.py search --query "OBS-ESS-SEC-07"
python3 -m unittest -v                                       # 35 tests
```

Python 3 standard library only (developed on 3.11). No pip install, no network, no model is
called.

```
question_cards.py              generator, linter, local index, renderers, CLI
data/templates.json            the question templates — ALL question wording lives here
data/observations.json         10 unresolved observations (fiction)
data/observations_hostile.json 11 deliberately broken records, one per rule
data/sources.json              source register: id -> label, exact locator, as-of date
data/interview_register.json   roles and planned sessions (fiction; nothing booked)
examples/                      generated: cards.json, cards.csv, question_cards.md
test_question_cards.py         35 unittest tests
```

## Why this is a generator, not a list of good questions

The completion condition is that a reviewer can move from a specific unresolved observation to
an appropriate follow-up **"without repeating the entire interview guide."** A written list of
good questions *is* the interview guide — the reviewer already has one. What they don't have
is the path from *this* uncertainty to the question that closes it.

So each observation declares the **shape** of its uncertainty, and each shape fills a
different template from the observation's own fields:

| Uncertainty shape | What the question has to do |
|---|---|
| `CONFLICT` | Put **both** readings in front of the practitioner and ask which is the normal case — without implying either source is wrong. |
| `AMBIGUOUS_SCOPE` | Accept the practice as stated and ask only about the boundary. |
| `SINGLE_SOURCE` | Ask for a record the *system* produced, not another person describing it. |
| `STALE_EVIDENCE` | Ask whether the evidence still describes today — not whether the practice changed. |
| `ABSENT_EVIDENCE` | Ask where the record lives, and if there isn't one, how the outcome is achieved instead. |
| `UNREPRESENTATIVE_SAMPLE` | Ask which window *would* be typical, rather than generalizing from the one we have. |

Templates live in `data/templates.json`. The code contains no question text, and a test proves
it: edit a template and the rendered cards change (`test_question_text_lives_in_the_templates_not_the_code`).

## The rule that does the real work

Every card carries an **`outcome_map`**: for each plausible answer, what the draft finding
becomes. **A question whose answers all lead to the same finding is rejected as
`USELESS_QUESTION` and does not render.**

That is the mechanical form of "don't re-ask the guide". If the answer cannot move the finding,
asking it spends a practitioner's hour for nothing, and no amount of good phrasing fixes that.
Two hostile fixtures pin it: one with a single possible answer, one with two answers that land
on the same finding.

## Every rule, and the fixture that proves it still works

`python3 question_cards.py check --observations observations_hostile.json` — verbatim:

```
observations=11 cards=1 suppressed=1 errors=9 warnings=1 accounted_for=11/11
  ERROR   TEMPLATE_FIELD_MISSING     OBS-H1-MISSING-FIELD     reading_b
  ERROR   USELESS_QUESTION           OBS-H10-ONE-ANSWER       outcome_map
  ERROR   USELESS_QUESTION           OBS-H2-SAME-OUTCOME      outcome_map
  ERROR   VAGUE_EXAMPLE_REQUEST      OBS-H3-VAGUE-REQUEST     example_request
  ERROR   UNKNOWN_SOURCE_REF         OBS-H4-DANGLING-SOURCE   source_ids
  ERROR   LEADING_QUESTION           OBS-H5-LEADING           question
  ERROR   MISSING_ABSENCE_CAVEAT     OBS-H6-NO-CAVEAT         absence_caveat
  ERROR   NO_CARD_WITHOUT_REASON     OBS-H7-SUPPRESSED        no_card_reason
  ERROR   UNKNOWN_UNCERTAINTY_TYPE   OBS-H8-UNKNOWN-TYPE      uncertainty_type
  WARNING NO_SESSION_FOR_ROLE        OBS-H9-NO-SESSION        ask_role
```

* **`VAGUE_EXAMPLE_REQUEST`** — "any relevant documentation" is not a request. A card must name
  something a practitioner can hand over: *"the change records for CR-411 through CR-413
  including their approval entries."*
* **`LEADING_QUESTION`** — a question may not presume the gap. The lint is **deliberately
  narrow** (a short phrase list: "why don't you", "failure to", "who approved"…), because a
  guard that flags correct prose gets switched off, and then it guards nothing.
  `test_leading_lint_does_not_flag_any_legitimate_question` asserts none of the ten real cards
  trips it.
* **`MISSING_ABSENCE_CAVEAT`** — an absent-evidence card must carry the caveat that *absence in
  the supplied material is not evidence the practice does not happen*. Missing it is an error,
  and the caveat is printed in the card, not buried in a methodology note.
* **`UNKNOWN_SOURCE_REF`** — a card whose locator goes nowhere sends the reviewer nowhere.
* **`TEMPLATE_FIELD_MISSING`** — a card containing a literal `{reading_b}` is worse than no
  card. A test asserts no `{` ever reaches rendered text.
* **`NO_CARD_WITHOUT_REASON`** — suppressing an observation is allowed; suppressing it silently
  is not. Uncertainty going quiet between analysts is the failure this order exists to prevent.
* **`NO_SESSION_FOR_ROLE`** is a **warning, not an error** — the question is still the right
  question; the reviewer just has nobody booked to ask it. Dropping the card would hide a real
  gap, so it renders as `UNSCHEDULED` and is flagged.

**Nothing is dropped silently.** `accounted_for` = cards + suppressed-with-reason + errored,
and a test asserts it equals the register size for both registers.

## Searchable, implemented rather than claimed

A deterministic local lexical index. Free-text terms AND together; `field:value` terms filter
exactly, with short forms a reviewer would actually type (`type:` `area:` `role:` `session:`
`obs:` `id:`). An unknown filter field returns an error that lists the valid ones — rejecting
`type:CONFLICT` with a correct-but-unhelpful message is how a search box gets abandoned.

```
$ python3 question_cards.py search --query "OBS-ESS-SEC-07"
1 card(s) for 'OBS-ESS-SEC-07'
  QC-ESS-SEC-07  [S1/ess_incident_commander]  On time to page the on-call engineer for a severity-1 incident: …
```

No external service and no model, which is the point: this has to work on an analyst's laptop
with the bundle and nothing else.

## Deliberately NOT ranking the cards

`UIOWA-113` (ZZ-COPPERLINE) owns evidence-request prioritization. Two different rank orders in
front of one reviewer is worse than none, so this kit **groups** cards by interview session and
role — so a reviewer runs one sitting — and exposes the inputs 113 would rank on
(`open_findings`, `uncertainty_type`, `example_request`) in `cards.json` and `cards.csv`.

## What the output looks like

`examples/question_cards.md` is printable and grouped by session. One card, abbreviated:

> **QC-ESS-DEP-01 · ESS / deployment · Two sources disagree**
> **Ask:** Change manager (shared services)
> **Question.** On approvals on standard ESS changes: the ESS change procedure indicates two
> approvals are required; in the sampled ESS change records, only one approval appears on 7 of
> 12 sampled changes. Which of those reflects the normal case, and what accounts for the other one?
> **Concrete request.** the change records for CR-411 through CR-413 including their approval
> entries, and any standing exception that applies to them
> **Where each answer leads:** a documented standing exception → validated strength with the
> exception noted · no exception exists → policy-versus-practice gap · records incomplete →
> evidence-location gap, not a control gap

That third row is why the card is worth an hour: the same question has three different
consequences, and the reviewer can see all three before asking it.

`cards.csv` is spreadsheet-safe: formula-like values are marked as literal text rather than
executed, NULL (`\N`), empty string and a literal `"NA"` stay three distinct states, and a test
asserts no exported cell begins `=`, `+` or `@`.

## University inputs still UNKNOWN

This is a method plus a worked fictional example. Before it produces a real card it needs:

1. **The real unresolved observations** — from the actual evidence register, with their sources
   and exact locators. The cards are only as good as the uncertainty they are generated from.
2. **The real interview roles and who holds which record** — our role-to-session mapping is
   invented, and a card routed to the wrong person wastes the sitting.
3. **Confirmation of the outcome maps.** "What would this answer change?" is a professional
   judgement call that belongs to Clark's, not to us. We supply the structure and a fictional
   worked set; the real outcomes must be written by whoever owns the finding.
4. **Whether the six uncertainty shapes cover their evidence.** If a seventh shape shows up in
   real material, it needs its own template — the generator will refuse the observation with
   `UNKNOWN_UNCERTAINTY_TYPE` rather than force it into a near-fit, which is the intended
   behaviour.
5. **Session lengths and how many cards fit a sitting.** We group by session; we do not know
   the real time budget.

## Scope

No real University findings and nothing synthetic presented as one. No live data, no model
calls, no outreach, **no interview conducted, requested or scheduled**. No individual
performance scoring. No certification, compliance, maturity or peer-percentile claims. No edits
to another seat's lane.
