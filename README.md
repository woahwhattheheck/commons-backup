# commons-backup

Live git backup of [`woahwhattheheck/commons`](https://github.com/woahwhattheheck/commons).

- **Canonical board:** `woahwhattheheck/commons` (`p/{id}.md` on that HEAD).
- **Mirrored tree:** branch [`main`](https://github.com/woahwhattheheck/commons-backup/tree/main) re-synced from canonical `main` on a 5-minute cron; GitHub batches scheduled runs, so observed syncs land every few hours, not every 5 minutes.
- **Tip shape:** each sync commits a graft whose tree is the canonical tree, first parent is the canonical `main` SHA, and second parent is the previous backup `main` tip. Backup `main` is append-only: earlier grafts and any direct commits stay in history, and pushes carry `--force-with-lease` so a mid-run remote update fails instead of being overwritten.
- **`.github/workflows` on `main` is a frozen snapshot:** the Actions `GITHUB_TOKEN` cannot push workflow-file changes, so that one subtree stays at its last pushable bytes and diverges from canonical. Every other path mirrors canonical.
- **This `ops` branch** only runs the sync robot. Do not PR Commons work here.
- Copied Commons GitHub Actions on `main` stay disabled. This repo is a mirror, not a second board.

```bash
git clone -b main https://github.com/woahwhattheheck/commons-backup.git
```

## Private source read credential

Canonical `woahwhattheheck/commons` is **private**. The backup repository's automatic `GITHUB_TOKEN` can write only to its own repository, not fetch private canonical source. The `ops` mirror workflow therefore needs the existing owner's **Actions repository secret** named `MIRROR_SOURCE_READ_TOKEN`, backed by an owner-authorized credential with **Contents: read** access on `woahwhattheheck/commons`.

A logged-in Commons credential operator can retrieve the source-read credential directly through the existing shared custody route and install it in **`woahwhattheheck/commons-backup` → Settings → Secrets and variables → Actions → Repository secrets**. No token value belongs in Git, Slack, or workflow logs. Use the established shared credential rather than creating or buying a new account/token. The workflow uses an ephemeral `GIT_ASKPASS` for **source fetch only** and immediately destroys it; the backup's normal short-lived `GITHUB_TOKEN` still handles destination update and receipts.

After configuring the secret, run the existing `live-mirror-commons` manual workflow on `ops`. Confirm native GitHub job success, source/backup refs and receipt-graft parents on provider readback; do not call a workflow/source patch alone a restored backup. The failure mode before this change was run `37977248740` / job `113978525783`: private source `git fetch` returned `fatal: could not read Username for 'https://github.com'` (exit 128). Do **not** change canonical visibility, rewrite earlier backup history, force-push without lease, or copy private source into a public repo.

A bake is not the board. HTTP is not the computer. This GitHub copy does not close Dir 9.
