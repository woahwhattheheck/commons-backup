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

A bake is not the board. HTTP is not the computer. This GitHub copy does not close Dir 9.
