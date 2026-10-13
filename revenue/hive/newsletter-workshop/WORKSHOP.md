# Build a newsletter workflow you can change

## The participant's finished task

Turn three source notes into a complete newsletter. Edit the issue, inspect the
HTML and plain-text versions, change a subscriber preference, and produce a
portable ZIP that contains the editable working file and the appropriate unsent
email drafts. You will then add a new source-linked section without changing the
compiler.

This is a working-file workshop, not a presentation or an income course. The
Mossworks publication, people, source notes, and events in the starter are
original fictional teaching material. The `example.test` links do not point to
real source pages. Nothing in this workshop contacts a subscriber or reserves a
place on an email platform. No live customer outcome is represented.

## Before the session

The participant needs a computer with Python 3.10 or newer, a text editor, and a
browser. Download/extract the entire workshop folder together; keep
`newsletter_workflow.py`, `workshop.html`, and `example.json` beside one another.
No Python packages, email account, API key, login, or paid service is needed to
run the workshop. Optional browser tests have separate dependencies.

Open a terminal in this folder. On Windows, use `py` wherever this guide says
`python` when that is how your Python installation is registered.

```sh
python newsletter_workflow.py serve
```

Open `http://127.0.0.1:8765/` on the same computer. Stop the server with Ctrl+C.
The server binds to loopback by default and keeps no server-side customer
workspace. Applied edits are cached in that browser when storage is available;
a downloaded JSON file is the portable copy. Use fictional material on a shared
workshop computer, and clear that browser's site data after the session.

## Suggested facilitator agenda

| Segment | Participant action | Concrete result |
| --- | --- | --- |
| Orientation · 5 minutes | Inspect the starter and explain what is fictional | Understand source text, editorial copy, preferences, and an unsent draft |
| First edition · 10 minutes | Build and open the ZIP | A working preview, text edition, and two unsent messages |
| Exercise 1 · 10 minutes | Change the headline, date, and edition slug | A revised edition and an editable working file |
| Exercise 2 · 10 minutes | Unsubscribe Alex and rebuild | One draft, with excluded recipients explained |
| Exercise 3 · 15 minutes | Add an original source and matching section | A four-section issue with a source trail |
| Handoff · 10 minutes | Reopen the working file and explain the delivery boundary | A workflow the participant can modify independently |

These are suggested lesson segments, not performance promises. A facilitator
may take longer on setup or adapt the examples to the participant's existing
work. Leave the source files with the participant rather than only the ZIP.

## First edition: follow the entire path

In the browser, the fictional starter loads automatically on first use. Inspect
its introduction and three sections. Open **Edit the full workspace JSON** and
find the source texts and five subscriber records.

Alex and Sam are subscribed to `workshops`. Jo is unsubscribed, Lee is paused,
and Riley chose only `tools`. The issue's topic is `workshops`. Click
**Download edition ZIP**, extract it into a new folder, and open `preview.html`.
Then open `newsletter.txt` and `delivery-plan.csv` in a text editor. The plan has
two `PREPARED_NOT_SENT` rows and three `EXCLUDED` rows. `drafts/` contains two
MIME email files, not sent messages.

The preview and plain-text edition contain the same authored issue. Each quote
links to its source. `source-map.json` records which supplied source text
contains each excerpt; it does not independently verify truth or the editorial
commentary. The ZIP's `workspace.json` is the source you can edit and import
again. `manifest.json` inventories the exported bytes.

Try changing just one word in a quote to a word that is not in its source.
Build again. Read the diagnostic, then restore the quote. Do not solve this by
inventing source text for a real claim: either use an actual supported excerpt
or explicitly rewrite the passage as your own reviewed commentary.

## Prepare the practice files

```sh
python exercises.py prepare work/practice
```

This creates three starter files and three complete worked solutions. The
command requires a new destination directory; rerunning it on the same directory
leaves the existing work intact and reports an error. Choose another directory
for a fresh practice set.

Exercises build on one another, but each starter includes the previous exercise's
solution so participants can begin any segment independently. Import an exercise
JSON file in the browser, or edit it directly in a text editor. Save your version
with **Save editable JSON**; the browser's download name is `workspace.json`, so
rename or place it deliberately before running a checker.

## Exercise 1: make the next edition

Start with `work/practice/exercise-1.json`. Set the edition slug to `edition-02`,
the subject to `Mossworks: what we learned at the bench`, and `planned_at` to
`2026-09-22T09:00:00-05:00`. Preserve the source excerpts and preferences.
The timestamp includes its UTC offset. It is a planning label in the export,
not a job scheduled on this computer or an email provider.

Save the edited file, then check and build it:

```sh
python exercises.py check 1 work/practice/exercise-1.json
python newsletter_workflow.py build work/practice/exercise-1.json --out work/edition-02.zip
python -m zipfile -e work/edition-02.zip work/edition-02
```

Open the new preview and compare it with the first edition. Expect the new
subject and date, with two unsent drafts. An existing output ZIP is never
silently replaced. Use a new output filename for another revision.

**Worked solution:** `work/practice/solution-1.json`.

## Exercise 2: respect a changed preference

Start with `exercise-2.json`. In the `subscribers` array, change Alex's `status`
to `unsubscribed`. Keep Jo unsubscribed, Lee paused, Riley subscribed to tools,
and Sam subscribed to workshops. Do not delete those records merely to make
the count look right: their reasons should stay visible in the delivery plan.

```sh
python exercises.py check 2 work/practice/exercise-2.json
python newsletter_workflow.py build work/practice/exercise-2.json --out work/preferences-updated.zip
```

Expect one unsent draft for Sam and four exclusions. Read the actual plan rather
than counting only the subscriber array. Adding a second record for Alex with
a different status is not a fix: duplicate addresses, compared without case,
are reported for consolidation instead of choosing a preference silently.

**Important:** the earlier ZIP still contains its original two drafts. Exports
are snapshots; changing a preference cannot recall files already downloaded.
Rebuild against current preferences before any external delivery. The draft's
reply-to unsubscribe instruction is text, not an installed preference service.
A real email platform's preference handling remains separate.

**Worked solution:** `work/practice/solution-2.json`.

## Exercise 3: add your own source-backed section

Start with `exercise-3.json`. Add this fourth object to `sources`:

```json
{
  "id": "workspace-review",
  "title": "Original fictional review note",
  "url": "https://example.test/mossworks/review",
  "text": "Review the plain-text edition before exporting email drafts."
}
```

Add a fourth section in `issue.sections` with source ID `workspace-review`,
that exact sentence as its `quote`, a heading of your choosing, and your own
editorial commentary. The source is deliberately original fictional lesson
material, not attributed to another publisher. For a real publication, use your
own authorized source text and a real source URL instead.

```sh
python exercises.py check 3 work/practice/exercise-3.json
python newsletter_workflow.py build work/practice/exercise-3.json --out work/four-section-edition.zip
```

Expect four sections, a matching fourth entry in `source-map.json`, and one
unsent draft for Sam. Confirm that the new section appears in both HTML and
plain text. Import the generated `workspace.json` in a fresh browser tab to
continue editing the same edition.

**Worked solution:** `work/practice/solution-3.json`.

## Handoff to the participant's real work

Use **Save editable JSON** to retain your current source. Make a copy before
replacing the fictional publication with your own material. Update sender and
reply addresses, source titles/text/URLs, editorial copy, topic names, and the
current preference records together. Do not treat the starter's fictional
claims, recipients, or dates as production input.

The compiler writes reviewed-ready content but does not install or operate an
email campaign. Use your existing platform's normal authorized draft/import
workflow for a real delivery. Confirm that platform's current preferences,
recipient list, links, sender identity, and scheduling before sending. There is
no automatic import, subscription page, live preference endpoint, or external
scheduler in this kit. A completed workshop is the functioning editable
workflow, not a claim that a newsletter was sent or a business earned money.

## Office-hour format

Ask the participant to bring their edited workspace and the exact error or
output that surprised them. Use fictional replacements for any real subscriber
records before sharing the file with a group. Start by reproducing one issue,
change the smallest relevant input, and rebuild into a new ZIP. End by having
the participant repeat the change without the facilitator's keyboard.

Useful prompts: Which part is source text and which is your interpretation?
Which source supports this exact quote? Why was this person excluded? What
happens to the old ZIP after an unsubscribe? Which file lets a colleague revise
the issue? What has actually been scheduled or sent?

## Troubleshooting

| Symptom | Action |
| --- | --- |
| The page is blank or the starter cannot load | Start the Python server and use its HTTP address; do not double-click `workshop.html` |
| Port 8765 is in use | Run `python newsletter_workflow.py serve --port 8766` and use the printed address |
| Full JSON edits are pending | Apply them before using the short form; Save retains pending text, even while invalid |
| A quote is not an exact excerpt | Compare it with the selected source text, including punctuation and whitespace |
| A date has no timezone | Supply an ISO datetime with `Z` or an offset such as `-05:00` |
| An output file already exists | Select a new revision filename; the existing ZIP is preserved |
| A subscriber is duplicated | Consolidate the email's current preference into one record, then rebuild |
| The browser loses its cache | Import your saved JSON; browser storage is not a backup |
| A source link does not open | The starter's links are fictional; no network fetch was used to compile the issue |
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
