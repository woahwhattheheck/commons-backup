# Browser validation scope

The compiler and real loopback HTTP tests are described in the original
workshop receipt. The browser has two separate optional test paths; neither is
a production dependency.

## Offline DOM plus actual compiler: eight checks passed

On September 8, 2026, `test_offline_browser.py` ran successfully using the
installed system Chromium in the ChatGPT cloud container. It loads the exact
`workshop.html` into an offline page, operates the actual controls and event
handlers, and routes `fetch` through a declared adapter to the production
Python parser, validator and compiler. The fixture is the actual `example.json`.
It inspects real emitted Blob bytes before browser navigation. No production
source changes or substituted compiler outputs are used.

```sh
CHROMIUM_EXECUTABLE=/usr/bin/chromium python test_offline_browser.py
```

With a Playwright-managed Chromium installation, use
`python test_offline_browser.py` without the environment variable. The optional
script imports Playwright only when explicitly run, so normal unittest discovery
does not require that browser dependency merely to import the module.

The executed checks cover starter fields/sections/preferences; form edits into a
valid ZIP with two unsent MIME drafts; an unsubscribe reducing the rebuilt draft
count to one; duplicate-key JSON diagnostics with exact invalid-text export;
unsupported source excerpts producing an error instead of a new export; native
file-input import through the validator; a 390px layout without horizontal
overflow; and absence of application `pageerror` events.

**Boundary:** this test replaces the fetch transport and captures export Blobs.
It does not establish browser HTTP navigation, native browser download/file
creation, native localStorage persistence, reload behavior, or provider delivery.
The existing separate HTTP regression tests exercise the actual server endpoints;
passing those tests and this DOM test is not labeled one end-to-end browser pass.

## Original direct browser HTTP attempt

`test_browser.py` is the direct end-to-end script. Its system-Chromium attempt
was blocked at navigation to the local server with
`net::ERR_BLOCKED_BY_ADMINISTRATOR`, before the first application assertion.
An attempt to install Playwright's browser failed with EAI_AGAIN DNS resolution
at its official download hosts. Neither result is a product success or a GitHub
publishing failure. This direct script has not been reported passing.

## Direct operator handoff completed on October 3, 2026

An ordinary Chromium 153.0.8010.0 session used the existing Python server over
loopback, with native file import, downloads and localStorage. It imported the
unchanged fictional starter, edited the subject and reloaded the browser: the
applied edit was restored. An explicit fictional subscriber change through the
full JSON editor survived Apply and a second reload with the complete workspace
unchanged. The portable JSON download retained that workspace.

The starter edition downloaded by the browser was 10,090 bytes and matched the
native CLI build byte-for-byte: two unsent drafts and three exclusions. After the
fictional unsubscribe, the rebuilt 7,959-byte ZIP also matched the native CLI
byte-for-byte, with one unsent draft and four exclusions. The extracted
`preview.html` opened directly through `file://`, displaying the edited subject
and all three original source links without fetching them. Both native builds
exited 0. The planned date remained metadata; no schedule or message was created.

Desktop (1280 × 900) and mobile (390 × 844) pages were inspected. The authoring
page and exported preview each fit a 390-pixel document width. This handoff fixed
white text on the header reference panel's pale code labels and dark links on its
dark background through scoped panel colors. The compiler, fictional starter and
inline browser JavaScript remained unchanged. Browser execution recorded no
page/console errors or external requests; the temporary server and browser were
closed. The earlier compiler/DOM observations remain accepted. No new tests,
dependencies, provider connection, real participant, customer delivery or send
was involved.

## Source identity used for the offline run

The test consumed the unchanged production files merged in PR10622, main commit
`93adaf800d100ed1309666a01f87e2a9d84eede0`:

| File | Git blob |
| --- | --- |
| newsletter_workflow.py | `5eb84bb316a44d59de94a95a6911c9c0c45ada59` |
| workshop.html | `9241740dd840de283c00a1fe11d8ae48bc4d0b60` |
| example.json | `38b8735b846d616ee6b644e76dc9f1ba3d683b1a` |
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
