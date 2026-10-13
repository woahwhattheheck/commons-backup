# Docs Rebuild Repair: intake and delivery checklist

Companion to [the complete offer](offer.md). This is a reusable work record, not a claim that any client has supplied inputs, funded work, or accepted a delivery. Fill the named fields from client-provided evidence; never manufacture a buyer or acceptance.

## Intake record

Record: client/project identifier; existing CRM record and submitting owner; repository URL and base commit; permitted delivery branch; contribution/AI-use rules; acceptance contact; confirmed start date; agreed price and any itemized fees; funding receipt reference (never a credential).

Record the Python version, dependency lock or exact install command, generator entrypoint, real generation command, selected test/CI command, environment variables by name only, and sanitized fixture paths. List up to two renderer files and two output files. Capture the failure log and the expected missing/stale/duplicated content. State unrelated baseline failures explicitly.

Create the acceptance map before changing code:

| Check | Client-provided definition | Delivery evidence to record |
| --- | --- | --- |
| Reported defect | Exact failing command and expected outcome | Base SHA, failing assertion, repaired SHA, passing assertion |
| Required output | Each section, href, label, order, and expected count | Assertions against actual generated output |
| Identical rebuild | Inputs and explicitly variable fields, if any | First/second output hashes; separate variable-field checks |
| Changed metadata | One input edit and old/new expected values | New value present; obsolete value absent |
| Compatibility | Legacy, empty, or special-character case relevant to this renderer | Expected behavior and test result |
| Preservation | Named forms, navigation, catalog entries, and unaffected content | Assertions and reviewed source/output diff |
| CI | One existing job and its baseline failures | Run URL, tested SHA, outcome, any unrelated failures |
| Handoff | Delivery route and acceptance contact | Patch/commit, instructions, explicit acceptance response |

The definition column is intentionally completed with the client; blank entries are missing inputs, not permission to invent acceptance. Preserve existing account ownership and SENT/DNR exclusions before contact. Do not create a second client ledger.

## Implementation sequence

First capture the actual baseline and identify the renderer responsible for the lost content. Add a failing assertion that identifies that content defect, not a broken test environment. Repair the generator's source of truth, regenerate only the selected outputs, then run the real pipeline twice with the same inputs. Check the changed-metadata and compatibility cases in isolated temporary fixtures. Review unaffected content and run the selected existing tests/CI job. Do not patch only the checked-in generated page.

## Delivery record

Provide the exact base and delivered SHAs, complete changed-file list, patch or PR, runtime/dependency versions, setup/generation/test commands in execution order, result counts, and any unrelated failures. Record output hashes and CI run links for the tested revision. Include the client-specific acceptance map above with actual evidence. Never label pending, skipped, cancelled, or failed checks as passing.

Explain reversal using the delivered source commit or patch through the client's normal workflow, followed by regeneration with the original inputs and the same tests. Do not delete client data or force-push shared branches. State whether merge/deployment has actually happened and which external event remains; a submitted PR is not an upstream acceptance receipt.

Request the named client's explicit acceptance against the map. A consolidated in-scope review received within five business days is included. New scope is separately quoted before additional work. Keep private repository contents and client inputs in their existing private facilities; this public checklist stores no client data.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
