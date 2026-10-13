# Executed continuation and observed handover repairs

**SYNTHETIC, single-seat role-transition simulation.** ZZ-BOREAL-138Q / GPT-6 Astra Pro executed this in an ephemeral cloud container on 2026-09-19. This deliberately constructed scenario is not a user study, independent peer review or live University engagement.

## Actual sequence

1. Read merged UIOWA-091 at the pinned revision, preserving original IDs, states and testimony distinctions.
2. Run its unchanged native validator on the materialized bytes.
3. Attempt continuation with version 1, an intentionally incomplete handover. The diagnostic command returned exit 1 with five gaps. A separate execution test rejected it without creating an output directory.
4. Repair five packet omissions without changing any source evidence or original classification.
5. Execute version 2, producing three draft findings, three retained UNKNOWNs, four reviewer dispositions and a readable HTML view with exact source excerpts and retained source copies.
6. Start a second Python process with only the exported sources, packet, lock and runner. No Slack history or complete repository is supplied. Its output checksum manifest is identical to the first.

## Observed gaps and repairs

| Diagnostic | Missing continuation context | Repair in v2 |
|---|---|---|
| SOURCE_REVISION | Which exact source version the packet selected | Bind the source-register revision |
| MISSING_CONTEXT / decisions[2].rationale | Why synthesis can proceed with open inputs | State the draft/limitation rationale |
| MISSING_CONTEXT / reviewer_comments[3].response | Whether the restoration request was answered | Keep OPEN_INPUT; no new evidence arrived |
| NEXT_DELIVERABLE | What to complete next and what done means | Name SYN138-SYNTHESIS-v1, recipient role and completion criteria |
| MISSING_DEPENDENCY | What precedes synthesis | Replace the undefined predecessor with HANDOVER |

## Observed execution

- **32 tests passed** normally; **the same 32 tests passed** with `python -O`. These are not 64 different tests.
- Existing native validator: exit 0; 24 canonical facts across 12 cells, source-reference resolution and synthetic labels validated.
- Completed task: **3 findings, 3 retained unknowns, 4 comment dispositions, 14 retained files / 10 source documents**.
- Export: 19 hashed files plus the checksum manifest. The clean second-process replay produced identical hashes.
- Covered cases include absent/changed source, wrong citation text/line, dropped unknown, dangling comment, missing rationale, dependency cycle/inversion, authority overstatement, duplicate JSON/IDs, symlinks/path escape, output preservation and clean replay.

Native program blob: `ac9c634bbcf2e0a92eab3c2c0127aaf8f35f383f`.

```text
PASS: UIOWA-091 synthetic collection is internally consistent
PASS: 24 canonical facts across all 12 service x assessment cells
PASS: manifest references resolve and every artifact is synthetic-labeled
```

The successful continuation printed:

```text
SYNTHETIC_CONTINUATION_COMPLETE findings=3 unknowns=3 sources=14
```

## Completed-run identity

```json
{
  "schema": "uiowa138-completion-v1",
  "synthetic": true,
  "packet_id": "SYN138-HANDOVER",
  "packet_version": 2,
  "packet_sha256": "c32f79c4722798efc41862b4b291e94771c2d8188b661a076eda060aafd23e14",
  "source_revision": "bcf765be4d537a513bf1d7ac54a210b25b053d07",
  "source_files": 14,
  "source_documents": 10,
  "facts": 24,
  "finding_count": 3,
  "unknown_fact_ids": ["ESS-AI-002", "ESS-SEC-002", "IAM-AI-001"],
  "review_dispositions": {
    "RC-01": "ADDRESSED_IN_DRAFT",
    "RC-02": "ADDRESSED_IN_DRAFT",
    "RC-03": "ADDRESSED_IN_DRAFT",
    "RC-04": "OPEN_INPUT"
  },
  "authority": {
    "university_findings": false,
    "client_acceptance": false,
    "payment_trigger": false,
    "staff_availability_confirmed": false,
    "appointment_created": false
  }
}
```

## Reproduction with the executable companion

The companion carrier contains `continuation.py`, `test_continuation.py`, `handover.json`, `handover-incomplete.json` and `source-lock.json`. Its publication/merge state is tracked separately on issue #16186 and in the demo thread. A document merge is not evidence that executable changes passed provider CI.

```sh
cd revenue/uiowa_rfq_18649_analyst_continuation
python -B -m unittest -v test_continuation.py
python -O -B -m unittest -v test_continuation.py
python continuation.py --packet handover-incomplete.json --lock source-lock.json --diagnose
# Expected exit 1 and five diagnostics.
python continuation.py --packet handover.json --lock source-lock.json --repo-root ../.. --out /tmp/uiowa138-first
python continuation.py --packet /tmp/uiowa138-first/handover.json --lock /tmp/uiowa138-first/source-lock.json --repo-root /tmp/uiowa138-first/sources --out /tmp/uiowa138-second
cmp /tmp/uiowa138-first/bundle-sha256.json /tmp/uiowa138-second/bundle-sha256.json
```

Use fresh output directories; existing output is preserved. The pinned native validator is invoked directly, never an arbitrary command from packet data. This is normal execution of reviewed repository code, not a security sandbox for an untrusted repository.

## Validation limits

Hashes and structural checks do not prove authored prose true, prove every implication supported or establish reviewer agreement. The interpretations were authored after reading the synthetic sources. The program checks retained bytes, references, exact citation lines and continuity metadata, not natural-language truth. No source was rewritten, no fact rescored, no appointment/outreach performed and no client acceptance or payment condition created.
