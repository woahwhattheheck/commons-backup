# Seven evidence-arrival decisions

**Fictional records; not an assessment or approval.**

| Case | Actual queue status | Supplied terminal IDs | Omitted terminal IDs |
| --- | --- | --- | --- |
| 01-original-retained | DECLARED_SUCCESSOR_MISSING_REVIEW | None | C |
| 02-intermediate-retained | DECLARED_SUCCESSOR_MISSING_REVIEW | None | C |
| 03-no-records-supplied | DECLARED_SUCCESSOR_MISSING_REVIEW | None | C |
| 04-terminal-arrives | DECLARED_SUPERSEDED_REVIEW | C | None |
| 05-one-branch-omitted | BRANCHED_SUCCESSION_REVIEW | C | D |
| 06-both-branches-arrive | BRANCHED_SUCCESSION_REVIEW | C, D | None |
| 07-declared-convergence | DECLARED_SUPERSEDED_REVIEW | E | None |

## 01-original-retained

A is still supplied, but the declared terminal C is omitted. Request C or explain the export boundary; do not silently treat A as the selected revision.

## 02-intermediate-retained

B remains an intermediate declaration, not the terminal. Preserve the request for C without inferring its deletion.

## 03-no-records-supplied

No after records were supplied. The known declaration ending at C remains relevant; reconcile the collection before selecting a citation.

## 04-terminal-arrives

C is now present by exact record ID and digest. Read its passage and decide whether the original finding concerns the old or new period. Presence is not approval.

## 05-one-branch-omitted

C and D are both known terminal declarations. Only C was supplied; omission of D does not choose a winner.

## 06-both-branches-arrive

Both drafts are present. Determine whether they are competing revisions or legitimately parallel scopes; retain the disagreement.

## 07-declared-convergence

E explicitly references both prior branches. This resolves the graph to one supplied terminal, not the substantive review or approval decision.

Every case contains editable before/after/findings JSON, the fictional source files, and real engine reports.
An omitted record is not proof of deletion. A declared terminal is not an approved or current source.
If an I/O failure interrupts creation, treat the directory as incomplete and choose a new destination; it is not an atomic bundle install.
