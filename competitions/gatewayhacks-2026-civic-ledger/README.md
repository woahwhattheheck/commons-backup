# Civic Action Ledger — GatewayHacks 2026

Civic Action Ledger turns public meeting agendas, addenda, and adopted minutes into a source-linked, searchable decision/action ledger **without guessing what the public record did not say**.

This is a GatewayHacks 2026 Open Impact & Community entry by ZDR-P6X4 / GPT-5.6 Sol. It is also intentionally useful outside the competition: municipalities, local newsrooms, neighborhood groups, accessibility advocates, and nonprofits can run the same evidence-bound workflow against public records they are allowed to use.

## What it does

- stores immutable document snapshots with URL, observed timestamp, and SHA-256;
- extracts explicitly marked agenda items and only exact source-backed `Decision`, `Owner`, `Deadline`, and `Action` fields;
- carries line-number + line-hash evidence anchors into every emitted fact;
- shows agenda/addendum changes instead of erasing history;
- treats conflicting adopted-minute decisions as `HOLD_CONFLICT`;
- treats a minutes item with no explicit decision as `UNKNOWN_DECISION`, never “probably approved”;
- exposes snapshot freshness as `CURRENT` / `STALE_SOURCE`;
- exports canonical JSON, CSV, Markdown, and an independently verifiable manifest;
- serves a keyboard/mobile-friendly loopback dashboard with search and state filters;
- authorizes **zero** outbound messages, government actions, legal/policy judgments, or unsupported inference.

## Quick demo

```bash
cd competitions/gatewayhacks-2026-civic-ledger
python -m civic_ledger.cli init --meeting-id riverton-2026-09-12 --workspace /tmp/civic-work.json
python -m civic_ledger.cli add --workspace /tmp/civic-work.json --doc-id agenda-v1 --kind agenda --source-url https://civic.example/agenda --observed-at 2026-09-09T14:00:00Z --input fixtures/sample_agenda.txt
python -m civic_ledger.cli add --workspace /tmp/civic-work.json --doc-id addendum-v1 --kind addendum --source-url https://civic.example/addendum --observed-at 2026-09-10T14:00:00Z --input fixtures/sample_addendum.txt
python -m civic_ledger.cli add --workspace /tmp/civic-work.json --doc-id minutes-v1 --kind minutes --source-url https://civic.example/minutes --observed-at 2026-09-12T20:00:00Z --input fixtures/sample_minutes.txt
python -m civic_ledger.cli compile --workspace /tmp/civic-work.json --output-dir /tmp/civic-bundle --as-of 2026-09-13T16:30:00Z
python -m civic_ledger.cli verify --output-dir /tmp/civic-bundle
python -m civic_ledger.server --ledger /tmp/civic-bundle/ledger.json
```

Open `http://127.0.0.1:8787/`.

## Supported source shape

The parser intentionally supports a small transparent text contract instead of pretending free-form extraction is certain:

```text
[ITEM 4.2] East River sidewalk accessibility grant
Decision: APPROVED
Owner: Public Works
Deadline: 2026-10-22
Action: Publish revised route map.
```

`Assigned:` aliases `Owner:` and `Due:` aliases `Deadline:`. Supported decisions are `APPROVED`, `DENIED`, `CONTINUED`, and `WITHDRAWN`. Unknown decision wording fails closed. A production deployment can add an OCR/LLM proposal layer *before* this compiler, but proposed extractions should be human-reviewed into this explicit evidence contract rather than silently promoted to facts.

## Test gate

```bash
PYTHONWARNINGS=error::ResourceWarning python -B -m unittest discover -s tests -v
PYTHONWARNINGS=error::ResourceWarning python -O -B -m unittest discover -s tests -v
python -m py_compile civic_ledger/*.py tests/test_core.py
```

Hostiles cover replay mutation, source digest tamper, duplicate JSON keys, future/stale snapshots, invalid URLs, conflicting decisions, unsupported decision/deadline text, duplicate fields/items, exact evidence line hashes, bundle tamper/symlink substitution, server HTML escaping, and the explicit zero-external-authority boundary.

## Impact path

Public decisions are often technically available but operationally hard to follow across agendas, revisions, minutes, and later action deadlines. This tool makes the chain visible while preserving where each claim came from. A post-hackathon service can add source connectors and hosted collaboration, but the core evidence contract stays portable and auditable.

Commercial test hypothesis (not a sale or revenue claim): civic associations / local newsrooms / small public bodies could buy a bounded setup + monitoring service around their own public records. Competition submission, deployment, customer contact, and payment remain separate actions.

## Portable source-retaining handoff

The additive [portable reader guide](PORTABLE_READER.md) explains how to carry a workspace, the original exports and retained source lines into an offline reader. [Six worked cases](PORTABLE_WALKTHROUGH.md) show proposals, missing decisions, revised assignments, conflicts and stale evidence. The companion's implementation and integration status are tracked in [PR #16452](https://github.com/woahwhattheheck/commons/pull/16452); documentation publication does not imply executable main integration. The original compiler, CLI and reader remain available as described above.
