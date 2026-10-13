# Repository portability / verified cold archive

This package is a provider-neutral, **offline** escape hatch for repositories that should not remain coupled to one paid private-hosting surface.

It does three things:

1. `snapshot` creates `git bundle --all`, records exact refs and `HEAD`, hashes the exact bundle bytes, runs Git's own bundle verification, restores the bundle into a fresh bare repository, runs `git fsck --full`, and requires exact ref + HEAD equality before publishing a canonical manifest.
2. `verify` repeats byte/hash/ref/restore/fsck checks from a retained bundle + manifest. A manifest is integrity evidence, not deletion/publication authority.
3. `plan` compiles an owner-authored inventory into deterministic provider-neutral next actions. `MIGRATE_PRIVATE` can emit a mirror handoff as argv arrays, but this tool never executes a destination push. `PUBLIC_REVIEW` is always a hold for separate human publication review.

## Authority ceiling

Every snapshot and plan keeps these actions hard-false:

- delete a source repository;
- publish private source;
- change repository visibility;
- mutate billing;
- push a destination;
- execute emitted migration commands.

A repository should be removed from GitHub only after a separate executor proves destination/archive custody and the owner authorizes that exact repository.

## CLI

```bash
python -m tools.repo_portability.cli snapshot --repo /path/to/repo --out /safe/new/snapshot --label repo-name
python -m tools.repo_portability.cli verify --bundle /safe/snapshot/repository.bundle --manifest /safe/snapshot/manifest.json
python -m tools.repo_portability.cli plan --inventory inventory.json --out migration-plan.json
```

The output directory/file must not already exist. Symlinked inputs/ancestors, parent traversal, malformed refs/OIDs, duplicate JSON keys, floats/non-finite values, unknown inventory fields, credential-bearing destination URLs, URL query/fragment material, control characters, and action/schema mismatches fail closed.

## Inventory schema

```json
{
  "schema": "repo-portability-inventory/v1",
  "repositories": [
    {
      "name": "private-app",
      "action": "MIGRATE_PRIVATE",
      "bundle_path": "/retained/private-app/repository.bundle",
      "destination_url": "https://git.example.invalid/team/private-app.git"
    },
    {
      "name": "inactive-app",
      "action": "COLD_ARCHIVE",
      "bundle_path": "/retained/inactive-app/repository.bundle"
    },
    {"name": "sensitive-app", "action": "KEEP_PRIVATE"},
    {"name": "possible-open-source", "action": "PUBLIC_REVIEW"}
  ]
}
```

Allowed actions are `MIGRATE_PRIVATE`, `COLD_ARCHIVE`, `KEEP_PRIVATE`, and `PUBLIC_REVIEW`. The planner never infers an action.

## Proof

Focused tests create synthetic Git histories with branches/tags, snapshot and independently restore them, verify exact object/ref custody, exercise tamper and symlink failures, reject credential-bearing handoff URLs and hostile JSON, and run under normal Python and real `python -O`.

No network request, provider account creation, repository visibility mutation, billing mutation, destination push, or deletion is performed by this package.
