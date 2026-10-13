# Attribution and scope

The new `route_frontier.py`, `engine_cases.py`, and regression suite are an
independent Commons implementation, licensed Apache-2.0. They do not copy or
import code from Opus Magnum, LiveSplit, or any chess implementation.

The integration cases execute Kaggle's original Apache-2.0 Kaggriculture engine
at `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`, through the existing engine artifact
`10005621438`. Its source and original license remain in that artifact and are
not duplicated here. Only the loader's original helper function is extracted
from the supplied, hash-checked `utils.py`; the game rules are not reimplemented.

The optional macro adapter consumes FIR's existing Apache-2.0 T06
`cloud-search-kernel/search_kernel.py` (Git blob
`d05b35057509ed706679c0c841a81ffba05a9936`) without editing or redistributing that
file. Its authorship, source references, notices, and separate experimental
results remain in the original directory. The adapter supplies ordered state
keys; it does not change the kernel's default behavior for existing consumers.

Engine traces are synthetic evaluator fixtures and contain no user account
credentials, private hosted games, or new public competition submissions.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
