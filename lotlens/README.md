# LotLens — "this supplier lot has a problem; what else could it affect?"

Build Order 2 (`commons-lotlens-20260904-01`). A standalone, read-only
traceability workbench over the exports a lab or plant already has. It does
not replace an ERP or LIMS, does not certify safety, does not initiate a
recall, does not release product. It imports rows, keeps them, and lets an
investigator ask questions of them with every answer tied to its source row.

Stdlib Python, no server, no network, no third-party script anywhere.

```powershell
python lotlens/lotlens.py -w .lotlens import lotlens/fixtures/synthetic_pilot --label pilot
python lotlens/lotlens.py -w .lotlens summary
python lotlens/lotlens.py -w .lotlens find LOT-WATER-01               # two lots, two namespaces, not merged
python lotlens/lotlens.py -w .lotlens inspect sup-acme/lot/LOT-CITRIC-01
python lotlens/lotlens.py -w .lotlens impact sup-acme/lot/LOT-CITRIC-01 --brief
# After CLEAT paths land: --brief prints hop lines + a what/detail column;
# --paths summary does the same on the printed report while --out keeps full edges.
python lotlens/lotlens.py -w .lotlens impact sup-acme/lot/LOT-CITRIC-01 --paths summary
python lotlens/lotlens.py -w .lotlens impact sup-acme/lot/LOT-CITRIC-01 --assume unlinked_package_same_product_day --out report.json --md report.md
python lotlens/lotlens.py -w .lotlens impact pilot-plant/shipment/SHIP-3 --backward --brief
python lotlens/lotlens.py -w .lotlens facts --kind contradiction
python lotlens/lotlens.py -w .lotlens annotate pilot-plant/batch/BATCH-P3 "40 kg against a 30 kg lot: QA says the consumption row is a typo, confirming" --by CLEAT
python lotlens/lotlens.py -w .lotlens compare <v1> <v2>
python lotlens/lotlens.py assumptions
```

Open `lotlens/app.html` in a browser and load `report.json` to read the same
report as a page: filter by status or kind, activate an item for its evidence
path, add notes and download them as an annotations file to apply with the
CLI. The page reads a file you give it and nothing else.

Item identifiers are native buttons: Tab to an item and press Enter or Space
to inspect it. Keyboard activation moves focus to the evidence detail; the
next Tab reaches the note field. Clicking elsewhere in an item row still
opens the same detail. On narrow screens the evidence table scrolls within
its labeled region; focus that region and use the arrow keys to reach later
columns. The detail and note field remain within the page width.

Native browser execution on 2026-10-03 used the three unchanged published
sample reports with Chromium 153.0.8010.0 directly from a file, plus the
backward report over loopback HTTP. Enter opened a documented BATCH-P1 path, Space opened the
filtered potential PKG-ORPHAN-1 path with its named assumption intact, and
keyboard note entry/download produced the two intended target/text records.
The reports retained 16, 18 and 8 affected rows and their original content
hashes. The measured 390 px page overflow (819 px) is repaired to 390 px;
keyboard scrolling moved the table 40 px and focus reached detail then notes.
No page errors or external requests occurred. This viewer continuation does
not repeat or replace the completed graph and second-investigator acceptance;
no engine command or project test was run, and no fixture or dependency was added.

Viewer operator columns (FORGE follow-up): the table includes a **what**
column (lot material+supplier, batch/package product, shipment customer) and
shows hop lines `from -relation-> to (file:line@version)` in the via column
and detail pane. Full edge objects remain in the JSON you load from `--out`.

## What an answer looks like

Every affected item has one of three statuses and a path of edges, each edge
citing `file:line@version`:

- `KNOWN_AFFECTED` — a documented row path exists from the start to the item.
- `POTENTIALLY_AFFECTED` — reachable only through an edge the investigator
  asked the engine to assume; the assumption is named on that edge.
- The report also lists, for everything on the path: `unresolved`
  references (rows pointing at things no row defines), `coverage_gaps` (the
  records stop here; that is not "unaffected"), `contradictions` (rows that
  disagree, all of them cited) and `cycles`.

Forward answers "what did this lot reach"; backward answers "what went into
this shipment". Both are the same mechanics run the other way; the engine
never decides which question comes next.

CLI display helpers (CLEAT follow-up to TENON's acceptance):

- `impact --brief` — compact affected list; with paths landed, each item
  carries hop strings and a `detail` / what string.
- `impact --paths summary` — printed report replaces bulky `path` arrays with
  the same hop lines; files written with `--out` keep full edge objects.

## The synthetic pilot fixture (what it deliberately contains)

`lotlens/fixtures/synthetic_pilot/` is a small high-acid RTD pilot in the
BevSource shape (ingredient lots → pilot batches → packages → shipments) with
every anomaly the order names, so the tests can freeze the expected facts:

| anomaly | where |
| --- | --- |
| split lot | `LOT-CITRIC-01` → `01A` (into `BATCH-P1`) and `01B` (into `BATCH-P3`) |
| blending | `BATCH-P2` consumes `BATCH-P1` plus fresh lots |
| rework into a later batch | `REW-01`: `BATCH-P2` → `BATCH-P4` |
| identical ids in separate namespaces | `LOT-WATER-01` from `sup-h2o` and from `sup-aqua`; `L-7` is a lot in `sup-acme` and a batch in `pilot-plant` |
| contradictory links | `BATCH-P3` consumes 40 kg of a 30 kg lot; `SHIP-9` names two packages |
| missing relations | `PKG-P4-1` has no shipment row; `PKG-ORPHAN-1` has no batch; `PKG-P9-1` names a batch no row defines; `BATCH-P4` consumes a lot no row defines |
| duplicate import | importing the directory twice changes nothing |

`python test_lotlens.py` (repo root, picked up by the battery) freezes the
expected affected sets forward from `LOT-CITRIC-01` and backward from
`SHIP-3`, the contradictions, the gaps, the assumption toggle, namespace
separation, cycle safety on a rework loop, reimport idempotence, version
comparison, annotation revisions, deterministic export, the Markdown render,
and a mutation check: remove the rework row and `BATCH-P4` leaves the answer.

## Relation to what already exists

aquatrace-lims carries a BevSource pilot-QA genealogy *acceptance runner*
(`fixtures/bevsource/`): sixty synthetic runs replayed to release/hold
verdicts inside the LIMS. LotLens is the other side of that table: it reads
exports out of any system and answers impact questions without owning the
records. The column names here (`formula_id`, `formula_version`, lot, batch,
package, shipment) follow that runner's vocabulary so its exports fit this
import contract without translation.

Real customer validation is separate from this synthetic correctness; no
customer data is in this directory.

Sample answers on the fixture, regenerated and pinned by `test_lotlens_samples.py`: `lotlens/samples/README.md`.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP.
