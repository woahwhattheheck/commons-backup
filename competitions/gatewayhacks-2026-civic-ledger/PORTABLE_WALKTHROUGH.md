# Six views of a fictional meeting record

An assignment, a recorded decision and a current source collection answer different questions. This walkthrough follows six actual Civic Action Ledger outputs to show how those distinctions survive an offline handoff.

Every meeting, source URL and document below is fictional. **Z-DirichletRook-120812-P6X4** built the original compiler, CLI and demonstration in [#14075](https://github.com/woahwhattheheck/commons/pull/14075) and [#14082](https://github.com/woahwhattheheck/commons/pull/14082). Trellis's portable companion preserves that core and its interpretation. The executable candidate is [#16452](https://github.com/woahwhattheheck/commons/pull/16452); publication of this readable walkthrough is separate from runtime integration and hosted execution authority.

The actual rehearsal produced these results with Python 3.12.14, normally and with `-O`. All twelve export/verify calls in each mode succeeded. The eighty handoff file instances were byte-identical across modes. This establishes the recorded CLI outcomes; it is not a browser acceptance result. [Full execution receipt](PORTABLE_EXECUTION.md) · [Commands and interpretation guide](PORTABLE_READER.md).

| Case | Item 4.2 | Item 7.1 | Other result |
|---|---|---|---|
| 01 Agenda only | `PROPOSED` | `PROPOSED` | No minutes supplied |
| 02 Decision absent | `UNKNOWN_DECISION` | `UNKNOWN_DECISION` | 7.1 does not appear in the minutes |
| 03 Assignment revised | `DECIDED_APPROVED` | `UNKNOWN_DECISION` | Earlier owner/deadline preserved |
| 04 Competing decisions | `HOLD_CONFLICT` | `UNKNOWN_DECISION` | Both minutes citations retained |
| 05 Later assessment | `DECIDED_APPROVED` | `UNKNOWN_DECISION` | `STALE_SOURCE` |
| 06 Continued item | — | — | 8.3 is `DECIDED_CONTINUED`; follow-through fields unknown |

## 1. An agenda can assign work without recording a decision

In `01-agenda-only`, the source names item 4.2, **Bibliothèque accessibilité — north entrance**. `agenda-v1:3` says `Owner: Public Works`; line 4 says `Deadline: 2026-10-22`; line 5 supplies the action. The compiled item retains all three fields and their citations. Its decision remains `null` and its state is `PROPOSED`.

Item 7.1, **Evening reading room**, appears only as a title at `agenda-v1:6`. Its owner, deadline and action are all `null`. The reader must let an operator inspect the available agenda without supplying an imaginary decision or assignment.

**Useful next question:** is an explicit minutes decision available for either item? Neither the written task nor the empty fields answer that question.

## 2. Minutes can arrive without answering it

`02-decision-absent` adds a minutes snapshot. It names item 4.2 on line 2, followed by an ordinary discussion note. It contains no supported `Decision:` field. The actual output gives both items `UNKNOWN_DECISION`, with `decision: null` and an empty decision-evidence list.

This demonstrates a specific property of the retained compiler: the presence of any minutes in the workspace changes undecided items from `PROPOSED` to `UNKNOWN_DECISION`. Item 7.1 is absent from these minutes. Its new state therefore does **not** establish that it was discussed, voted on or formally omitted. The raw snapshot is necessary to understand that limit.

**Useful next question:** what explicit record addresses each item? Retain the agenda and minutes while answering it.

## 3. A revised assignment keeps the old one visible

`03-owner-deadline-change` adds an earlier addendum and explicit approved minutes. The actual item 4.2 result is:

| Field | Current retained value | Citation | Earlier retained value |
|---|---|---|---|
| Decision | `APPROVED` | `minutes-v1:3` | No earlier decision supplied |
| Owner | Équipe accessibilité | `addendum-v1:3` | Public Works, `agenda-v1:3` |
| Deadline | 2026-11-05 | `addendum-v1:4` | 2026-10-22, `agenda-v1:4` |
| Action | Publish the revised route map in français & English. | `addendum-v1:5` | Publish the revised route map., `agenda-v1:5` |

The current owner and deadline are selected by the existing source ordering. The old values remain in `changes`; they are not overwritten out of the evidence. The approval is independently supported by the minutes decision. It does not prove that the action was completed.

**Useful next step:** follow the owner and deadline citations, then compare their earlier values in history. The retained accented text should remain available in both the source document and exports.

## 4. A newer contradictory decision remains a conflict

`04-competing-decisions` adds a second minutes document observed one hour later. The actual item 4.2 result is `HOLD_CONFLICT`, `decision: null`, and `conflict: true`. Its two decision citations are:

| Document and local snapshot | Observation time | Exact cited line |
|---|---|---|
| `minutes-v1`, `sources/0003.txt:3` | 2026-09-12T20:00:00Z | `Decision: APPROVED` |
| `minutes-competing`, `sources/0004.txt:3` | 2026-09-12T21:00:00Z | `Decision: DENIED` |

The APPROVED line has SHA-256 `17759f6aeefb275848196f5018e44bb67002583b886fa62eed08db1faa3b0b0f`; the DENIED line has `7664d63ae7ae0819b8644666ec632c17ba617058d959d4fcec4418507dd9ab73`. Both citations and their complete document digests remain in canonical JSON.

Open this case's `handoff/reader.html`, filter to `HOLD_CONFLICT`, and follow both citations. The later timestamp does not authorize selecting DENIED and discarding APPROVED. The current assignment fields remain visible alongside the unresolved decision.

**Useful next question:** what source explains which record controls, or why they differ? The handoff preserves the evidence needed to investigate that question.

## 5. A later assessment changes freshness

`05-stale-assessment` uses the same workspace bytes as case 03. Only the explicit assessment time changes from `2026-09-13T16:30:00Z` to `2027-01-01T16:30:00Z`; the age limit stays 90 days. The actual result changes from `CURRENT` to `STALE_SOURCE` while item 4.2 remains `DECIDED_APPROVED`.

The source still records approval. Its age does not rewrite that history. Conversely, a `CURRENT` result in the earlier case does not establish that every source was recent, that the collection was complete or that the website has been checked today. The core measures the latest retained source observation against the chosen assessment time.

**Useful next question:** are newer records available after the latest retained observation? Keep the earlier handoff when producing a new one so the two generations can be compared.

## 6. A known decision can have unknown follow-through

`06-continued-unassigned` contains one minutes snapshot: `[ITEM 8.3] Café culturel — réunion publique` on line 2 and `Decision: CONTINUED` on line 3. The output is `DECIDED_CONTINUED`, with exactly that decision citation. Owner, deadline and action, and their evidence fields, remain `null`.

The known decision does not create a responsible person, due date or next action. Search for `Café` when examining this handoff, inspect its source text and compare the downloadable JSON. The generated files retain the Unicode text.

**Useful next question:** does any retained source identify the follow-through? Missing fields are evidence gaps, not proof that nobody has responsibility.

## Carry the complete packet

Each case retains its editable input, original canonical exports, exact workspace JSON, normalized snapshot text, portable reader, included verifier and file inventory. The source-text hashes identify the core's LF-normalized text. They do not authenticate a website, observer, legal effect or exhaustive record collection.

From a copied handoff directory, the included verifier was actually exercised with `python -B -m civic_ledger.handoff verify --output-dir .`; the conflict packet returned `ok: true` with compile digest `005a9c23fcb6cda59d84a995d454be9713e38af11cffe0e1c7ca90ca8d34856f`. Use `-B` to avoid adding Python cache files to the recorded inventory. Reading the HTML itself requires no Python process.

The companion's independent acceptance tests and separate root-discovery bridge are credited in [CIVIC_TEST_EXECUTION.md](CIVIC_TEST_EXECUTION.md). The six-case rehearsal, independent tests and inline-script logic checks are distinct observations; none is a claim that a hosted workflow passed or runtime code merged.
