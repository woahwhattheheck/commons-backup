# GOSIM 2026: runnable ARC preparation

This package builds a bootcamp baseline from the real MIT-licensed ARC compiler,
not a copy of the starter that returns success without implementing anything.
It translates ARC-Bench's fixed entry command to the upstream compiler and keeps
text/visual model configuration on the runner-injected gateway. No qualifier
application is implemented here and no score, paid result, or live model run is claimed.

## Run and obtain the upload candidate

Use the **GOSIM ARC preparation** GitHub Actions run for this commit. Its artifact
`gosim-arc-preparation-<commit>` contains `commons-arc.zip`, the dependency lock,
and actual startup/readback results. All builds run on ephemeral cloud Linux.
Do not create new clones, archives or build trees on the owner's PC.

To reproduce in an existing ephemeral cloud checkout:

```sh
python3 -m unittest discover -s revenue/gosim2026 -p 'test_*.py' -v
python3 revenue/gosim2026/build.py --output /tmp/commons-arc.zip
python3 revenue/gosim2026/cloud_validate.py /tmp/commons-arc.zip --workspace /tmp/gosim-candidate
```

Python 3.11+ and network access to public GitHub/PyPI are required for preparation.
The compiler also needs Node.js 20+ and pnpm when it actually generates a web app.
No model credentials are used by the build or startup checks.

The ZIP root contains `main.py`, the tested 69-package dependency lock as
`requirements.txt` (original retained as `requirements.upstream.txt`), ARC's full Python source,
its exact template gitlink, retained license and a file-hash manifest. In ARC-Bench,
select Python and upload the ZIP only when that platform's run window permits.
The published entry shape is:

```sh
python3 main.py /path/to/requirements --output-dir /path/to/output --type web
```

For a permitted practice run, the runner supplies `OPENAI_API_KEY`,
`OPENAI_BASE_URL`, and `MODEL`; do not add personal paid-provider fallback
credentials. The adapter supports native ARC `compile`, `--resume` and
`--retry-failed` arguments too. It does not use `--clean`, reset or overwrite
existing work by default. ARC's own runtime emits real production events and
traceability; this adapter invents no node-success events.

## Source and work window

Checked 2026-09-09 UTC. Team TokenJunkieLabs is already registered under the
single existing team account; do not create another registration or teammate account.

- [Official event](https://create.gosim.org/factory26/): registration closed September 7
  23:59 Beijing (15:59 UTC). An organizer follow-up on September 9 says the
  bootcamp now starts September 10; scored qualifier remains September 21–30 with
  a simultaneous start; top 20 finals October 1–7.
- Organizer account follow-through from the September 9 email: the captain/main
  contact should use the existing login's “编辑报名信息” flow to complete newly added
  fields, verify every teammate is under the correct team, and add any missing members
  under “编辑报名信息 → 其他队伍成员”. Already-added teammates should not register again.
  Join participant group 2 using the emailed QR code, with group 3 as fallback. These
  are account/participant-group maintenance steps, not a scored run or new registration.
- [Official resources](https://create.gosim.org/factory26/resources) explicitly
  recommend running the supplied example and packaging a custom agent. That
  supports generic preparation; it does not authorize starting scored tasks early.
- [Full rules](https://create.gosim.org/factory26/rules) require the shared model
  gateway and prohibit changing tests, metering or scoring. Section 4 lists
  runnable source/startup, full production traces, and a 3–5 minute demo.
  The homepage's agent-only FAQ conflicts with this. Keep both requirements
  visible; do not automatically record/publish a video. Root owns entry/account
  actions and any organizer communication.
- [ARC source, exact pin](https://github.com/code-philia/agentic-requirement-compiler/tree/bf7b703d7e349834a1a16513f140aad55b790fe3)
  and its [template gitlink](https://github.com/Weiyu-Kong/arc-template/tree/e4ac841073726bf3e35552c6bc789c0f2f075098).
  ARC is the actual coding framework. Commons' account-specific headless/connector
  assets are not bundled: they are not the organizer's metered gateway.
- [Public ARC-Bench](http://arc-bench.com) links its starter from the task UI.
  The publicly linked site currently uses HTTP; no credentials were sent during
  documentation inspection and no TLS interstitial was bypassed. The starter
  documents the fixed entry contract above. Do not confuse this with ARC-AGI or
  the unrelated autonomous-research ARC-Bench.

## Execution queue

1. Root: before the September 10 bootcamp, use the existing single TokenJunkieLabs
   login to complete newly added registration fields, verify teammate membership,
   and join participant group 2 (group 3 fallback) via the organizer email's QR.
   Retain private confirmation; do not duplicate the registration.
2. Technical lane: preserve this pinned baseline and use newly published official
   bootcamp instructions to run a permitted sample with sponsored tokens.
3. Compare against built-in ARC on the same permitted sample: actual GUI pass rate,
   metered tokens and elapsed time; fix demonstrated functionality gaps.
4. September 21: reread the released competition requirements, model options and
   upload contract before starting the scored task. Save real prompts/tool calls,
   node iterations, human edits and generated source; keep organizer tests unchanged.
5. Submit the tested current candidate under the official run window. Check actual
   platform acceptance and score. Prepare any requested demo only at Bryce's direction.

Unresolved external details: gateway access/configuration, published scoring
weights, interpretation of conflicting submission descriptions, payout/IP terms.
The first cloud run (34081766220) passed 10 contract tests, built the real pinned
source, installed 69 resolved dependencies, and started ARC 1.2.0 plus its SDK.
The complete dependency versions from that actual run are now pinned in this
repository and the upload bundle; subsequent builds recheck them. Startup/package
validation is not a replacement for the sponsor-gateway sample run.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

