# Restore a Conversation Desk export

`restore_export.py` turns the existing `conversation-desk-export-v1` JSON download into a **new** Conversation Desk SQLite workspace. It is an operator recovery tool for the already-shipped local application; it does not change `app.py`, the browser UI, drafting behavior, OCR, or messaging behavior.

## Restore

From `revenue/hive/conversation-desk/`:

```sh
python3 restore_export.py /private/path/conversation-desk-export.json /private/path/restored-conversations.sqlite3
```

The destination path must not exist. Its parent directory must already exist. Success prints one JSON receipt containing the old-to-new conversation and image ID maps. Failure prints `{"restored": false, ...}` and exits 2.

After success, run the unchanged desk against the new database:

```sh
python3 app.py --db /private/path/restored-conversations.sqlite3 --port 8769
```

Keep exports and restored databases private: they can contain conversation text, context notes, drafts, and the original screenshot bytes.

## What is preserved

Before it creates any destination file, the restore tool validates the complete export shape and every saved field with the current Conversation Desk validators. It also checks:

- unique conversation and screenshot IDs;
- every screenshot's conversation association;
- nested screenshot metadata against the top-level screenshot record;
- PNG/JPEG/WebP bytes using the current screenshot validator;
- MIME type, byte length, and SHA-256 against the encoded original bytes; and
- finite, strict JSON with the exact `conversation-desk-export-v1` structure.

The actual restore is replayed through the unchanged `app.Store.create` and `app.Store.add_image` APIs. A final re-export verifies every saved Conversation Desk field, screenshot name/MIME/SHA, original screenshot bytes, image order, and conversation association before the new database is published.

## What is regenerated

The v1 export is a saved-state export, not a revision-history backup. It does not contain prior versions of conversations. Restore therefore regenerates:

- conversation IDs;
- screenshot IDs;
- current database revisions; and
- created/updated timestamps.

The success receipt returns explicit old-to-new ID maps. It does **not** claim to restore earlier revisions or their timestamps.

## No overwrite / failure behavior

The tool refuses any pre-existing destination, including a dangling link. It builds and verifies a temporary SQLite database in the destination directory and publishes it with an exclusive hard-link operation. A concurrent creator therefore wins or loses without overwrite. If validation, replay, or verification fails, the temporary database is removed and no destination is created.

This publication method requires normal same-filesystem hard-link support in the destination directory. The tool fails rather than falling back to an overwrite-capable rename.

## Test

```sh
PYTHONWARNINGS=error::ResourceWarning python3 -B -m unittest -v test_restore_export.py
```

The focused suite uses only synthetic conversation text and a synthetic 1×1 PNG. It exercises real temporary SQLite databases, the canonical Store/image/field APIs, export→restore→re-export equivalence, tamper rejection, no-overwrite behavior, malformed JSON, empty workspaces, CLI diagnostics, and concurrent restore attempts to one destination.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
