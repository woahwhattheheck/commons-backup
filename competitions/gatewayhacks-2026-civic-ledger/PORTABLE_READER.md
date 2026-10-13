# Civic Action Ledger: take a meeting's evidence with you

The portable reader carries an existing meeting workspace, its compiled decisions and its retained source text into one offline handoff. Open `reader.html` directly from disk to read it without starting a server. The source website is a reference, not a required network connection.

The original Civic Action Ledger compiler, CLI, loopback reader and synthetic Riverton demonstration were completed by **Z-DirichletRook-120812-P6X4 (ZDR-P6X4)** in [#14075](https://github.com/woahwhattheheck/commons/pull/14075) and [#14082](https://github.com/woahwhattheheck/commons/pull/14082). This companion is the Trellis extension tracked in [#16445](https://github.com/woahwhattheheck/commons/issues/16445). It retains the original decision model rather than reinterpreting public records.

## Export and verify

Run from `competitions/gatewayhacks-2026-civic-ledger` in a checkout containing the companion. Use an existing workspace made with the original `civic_ledger.cli init` and `add` commands. Choose a new output directory; an existing directory, even an empty one, is refused.

```bash
python -m civic_ledger.handoff export \
  --workspace /path/to/meeting-workspace.json \
  --output-dir /path/to/new-meeting-handoff \
  --as-of 2026-09-13T16:30:00Z \
  --max-source-age-days 90 \
  --classification synthetic
python -m civic_ledger.handoff verify \
  --output-dir /path/to/new-meeting-handoff
```

Use `synthetic` only for fictional records. Omit the classification or use `unspecified` when that is the honest description. Neither option authenticates a record. The explicit assessment time is required; choose it deliberately and keep it with the result.

The handoff contains the original `ledger.json`, `ledger.csv`, `ledger.md` and `manifest.json`, plus the exact input `workspace.json`, retained snapshot text under `sources/`, the offline `reader.html`, a handoff README and source package. `handoff-manifest.json` describes the companion's files separately from the original bundle manifest.

Open the reader, search for an item, filter its state and follow a citation into the retained document. Compare the cited line with the displayed claim. Inspect change history and all competing decision citations before drawing a conclusion. The canonical exports and workspace remain available for reuse; browser presentation does not replace them.

The included Python package also verifies a copied handoff without the original checkout:

```bash
cd /path/to/new-meeting-handoff
python -B -m civic_ledger.handoff verify --output-dir .
```

Use `-B` for this copied-package command so Python does not add cache files to the handoff's recorded file inventory.

## What the labels mean

| Label or field | What the existing compiler establishes | What remains unknown |
|---|---|---|
| `PROPOSED` | No minutes snapshot exists in this workspace for an undecided item | Whether a meeting took place or a decision was made elsewhere |
| `UNKNOWN_DECISION` | Minutes exist somewhere in the workspace, but no explicit supported minutes decision was extracted for this item | Whether this item was discussed; an item can be absent from those minutes |
| `DECIDED_APPROVED`, `DECIDED_DENIED`, `DECIDED_CONTINUED`, `DECIDED_WITHDRAWN` | Retained minutes contain one distinct supported decision value | Record authenticity, legal effect and completeness of the supplied collection |
| `HOLD_CONFLICT` | Retained minutes contain competing decision values | Which record should control; the newer record does not automatically settle the conflict |
| Owner, deadline, action | The latest retained field by the core's source ordering, with its citation and prior changed values | Whether the named work was performed or the assignment remains effective outside these records |
| `CURRENT` / `STALE_SOURCE` | Age of the latest source observation relative to the explicit assessment time and age limit | Whether every source is recent, whether newer records exist, or whether the website was checked today |
| Missing value / `null` | No supported field value was extracted | A negative fact; missing owner does not prove nobody is responsible |

The text contract is explicit: `[ITEM …]`, `Decision:`, `Owner:` or `Assigned:`, `Deadline:` or `Due:`, and `Action:`. Free-form discussion is not silently promoted into those fields. This companion introduces no OCR, language-model extraction or legal interpretation.

## Read a citation honestly

The core normalizes CRLF and CR line endings to LF when it creates a snapshot. A snapshot digest identifies that normalized retained text; each citation also identifies a line and its digest. The exact workspace JSON bytes are preserved separately. Do not call the normalized snapshot an exact copy of unknown original website or PDF bytes.

The handoff's verification concerns retained artifact integrity and its recorded generation. It does not certify the source URL, the observer, a public body's approval, an exhaustive source collection or present-day legal effect. A `CURRENT` label is tied to the displayed assessment time. The original hard-false external-action and legal-judgment fields remain part of the canonical output.

## Six fictional operator cases

Run the rehearsal from the same component root, with an existing parent directory and a new destination:

```bash
python -m civic_ledger.rehearse_portable --output-dir new-civic-rehearsal
```

The command constructs six fictional workspaces, invokes the actual companion export and verify CLI for each, and retains every command's output. `INDEX.md` links to each reader; `INDEX.json` contains the actual observed item records and before/after source-file identities. Each case retains its editable `input-workspace.json` and an `OBSERVED.json` readout. A failed run keeps its case diagnostics and does not write a completed index.

| Case | Question to explore |
|---|---|
| Agenda only | Why is a written assignment still a proposal? |
| Minutes without decisions | Does an unknown decision prove an omitted item was discussed? |
| Changed owner and deadline | Where are the old assignment and the later Unicode assignment retained? |
| Competing decisions | Can both APPROVED and DENIED citations be inspected without erasing either? |
| Stale assessment | Why can an old recorded approval remain while freshness changes? |
| Continued, unassigned item | Which follow-through fields remain unknown despite an explicit decision? |

The fixture texts use reserved `civic.example` URLs and fictional public-body content. The generator checks the intended item states and freshness against real output. It does not automate a browser: successful generation is not a browser acceptance result. Before/after disk hashes document the files present during the CLI run; they are not attestation of an arbitrary Python interpreter.

Start with `04-competing-decisions/handoff/reader.html`: filter to `HOLD_CONFLICT`, open item 4.2 and follow both minutes citations. Then compare `03-owner-deadline-change` with `05-stale-assessment`: their workspaces contain the same source facts, while the assessment times differ. Finally open the continued case and search for `Café`; its known decision must not turn missing follow-through fields into invented facts. These are operator instructions, not a claim that browser checks have already run.

To explore a variation, copy a case's input workspace outside its existing handoff, update the fictional snapshot through the original workspace workflow so its digest stays consistent, and export to another new directory. Keep the earlier packet when comparing generations. Do not edit a handoff in place and present the old manifest as describing it.

## Recorded rehearsal

The six cases were executed with Python 3.12.14 normally and with real `-O`, including optimized child CLI calls. All 12 export/verify calls in each mode exited zero. All 80 handoff file instances across the six cases, and all six input workspaces, were byte-identical between modes. The included verifier also succeeded from the copied conflict handoff using the `-B` command above.

This execution used original core blob `964cf5231cf4c72390fe9fb30bddc45813ebeac9`, companion blob `bed0659a3b622368f4c7f48b203c1bdd4fc65894`, and rehearsal blob `154760462f30c6a4aa3b13ba5ae8638ce857cd55`. See [PORTABLE_WALKTHROUGH.md](PORTABLE_WALKTHROUGH.md) for the observed decisions and [PORTABLE_EXECUTION.md](PORTABLE_EXECUTION.md) for literal commands, outputs and source identities. This receipt does not assert browser acceptance, hosted-check success or runtime integration; executable publication remains tracked separately in [#16452](https://github.com/woahwhattheheck/commons/pull/16452).
