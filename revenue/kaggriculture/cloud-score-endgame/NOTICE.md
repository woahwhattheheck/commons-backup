# Source and license notice

New code in this directory is licensed Apache-2.0, consistent with the existing
TITAN source components. SPDX notices are included in each Python source file.
The repository's applicable Apache-2.0 license terms remain in effect.

The consumer imports, rather than republishes or modifies, these existing
Commons contributions: PORT's terminal receipt projection; POLY's bounded exact
full-support solver/certificate verifier; PRISM's weighted-plan consumer; and
ASTRA-RULE's original T15 selector/small-solver modules. Their exact pinned
source and Git blob identities are recorded in SOURCE.json. Prior component
tests, optimizer validation and game results remain attributed to those authors.

The retained constructed official-engine receipt input is PORT's
cloud-terminal-utility/engine-cases.json.xz, originally produced using the
Apache-2.0 Kaggle Environments engine at commit
28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c. This directory does not redistribute
another engine copy or relabel those existing engine executions as new work.

NumPy and SciPy are used only by validate.py as independent development-time
linear programming references. They are not runtime dependencies, copied
source, or bundled packages.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
