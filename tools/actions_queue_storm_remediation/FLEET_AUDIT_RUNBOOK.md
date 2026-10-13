# Fleet workflow audit runbook

The GitHub connector available to `Z-ZephyrFoundry-0047-L6N2` was read-only.
This script is the authenticated, GET-only bridge for a peer with a repository
token. It does not contain any GitHub mutation operation.

```bash
export GH_TOKEN='token with read access to the three private repositories'

python github_workflow_fleet_audit.py \
  woahwhattheheck/smb-showcase-inventory \
  woahwhattheheck/pack-market \
  woahwhattheheck/motel-ops-suite \
  --output-dir fleet-audit
```

Interpret the exit status:

- `0`: no duplicate unrestricted push/PR triggers found.
- `1`: one or more mechanically safe changes were emitted.
- `2`: `--strict` was used and one or more trigger forms require manual review.
- other nonzero: deterministic retrieval or integrity failure.

Every fetched file is checked against its directory-listing blob SHA, decoded
size, UTF-8 validity, and SHA-256 byte receipt. The generated patch is also
SHA-256 pinned. Only exact structured YAML forms are changed.

Review then apply one repository patch at a time:

```bash
git -C smb-showcase-inventory apply --check \
  ../fleet-audit/woahwhattheheck__smb-showcase-inventory__main.patch
git -C smb-showcase-inventory apply \
  ../fleet-audit/woahwhattheheck__smb-showcase-inventory__main.patch
python actions_queue_storm_fix.py smb-showcase-inventory --check
```

Do not run the audit in `--include-push-only` mode without a separate semantic
review. A push-only workflow may intentionally run on feature branches.
