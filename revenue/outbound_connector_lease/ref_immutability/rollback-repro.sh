#!/usr/bin/env bash
set -euo pipefail
root="${1:-$(mktemp -d)}"
mkdir -p "$root"
cd "$root"
git init -q
git config user.name Z-Aster
git config user.email z-aster@example.invalid
printf 'root\n' > root.txt
git add root.txt
git commit -q -m root
sha=$(git rev-parse HEAD)
ref='refs/heads/outbound-connector-lease/v1/rollback-probe'
git update-ref "$ref" "$sha" ''
first=$(git rev-parse "$ref")
git update-ref -d "$ref" "$sha"
! git show-ref --verify --quiet "$ref"
git update-ref "$ref" "$sha" ''
second=$(git rev-parse "$ref")
printf 'first_create_sha=%s\nsecond_create_sha=%s\nboth_creates_succeeded=%s\n' "$first" "$second" "$([[ "$first" == "$second" ]] && echo true || echo false)"
