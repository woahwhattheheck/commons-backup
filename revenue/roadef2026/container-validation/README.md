# Frozen ROADEF portfolio: Docker execution and held package

This lane consumes the coordinator's immutable
[FROZEN-CANDIDATE-20260908.json](https://github.com/woahwhattheheck/commons/blob/6feb9c0566b8f203c5d1a2ffdfbf1cb6d11be055/revenue/roadef2026/fleet-candidate/FROZEN-CANDIDATE-20260908.json)
for candidate `S139-fleet-20260908-75897709`. The manifest SHA256 is
`6a5127cbf56305cfa46e5f26b52b4105c6c8b8aaa4ce12ed7643a076f82c9c51`.
It requests an enforced four-GiB build, B01/B11/B12 smoke execution,
accepted-checkpoint SIGTERM exit within ten seconds, and a held source package
with the reviewed two-page method PDF.

## Exact source staging

`bootstrap.py` verifies the frozen manifest before consuming its entries. It
preserves all 22 files and the public manifest from the original publication
`2885d176373c33410148829fef93c310c3752c0b`. A separate runtime source directory
contains all eight frozen runtime files plus the original README required by the
published preparer. Every frozen byte count, SHA256 and provided Git blob identity
is checked. The exact LINK preparer retains the existing QUARTZ dependency-header
repair and verifies four pinned source archives.

The CEDAR-JOIN patch is applied without fuzz to the original candidate source.
The output must be exactly 37,251 bytes with SHA256
`758977095f8f34263bbcd9ed043ac4ab7943f04f65fae530c78ee64787c34f8f`.
This consumes WREN, DELVE and KESTREL's authored kernels with original
directed/joint defaults and no additional neighborhood flags. SEDGE and FLORA
remain unchanged. The frozen supervisor includes cleanup, status, memory and
checker-attempt retention; the frozen comparator combines PORT's scientific-value
handling, BRIDGE's reference interface and HAZEL's malformed-report handling.

The exact frozen portfolio LICENSE is added to `attribution/FLEET-LICENSE`, which
the unchanged Dockerfile also copies into the final image. This addition is
recorded in the actual build manifest. Nine official inputs are mapped explicitly
to `data/B01`, `data/B11` and `data/B12`. `PREPARATION.json` retains the full frozen
manifest, configuration, documentation and original/used source identities.

## Enforced build and runtime checks

`build_with_limit.py` creates a dedicated BuildKit container using the documented
[Docker container driver options](https://docs.docker.com/build/builders/drivers/docker-container/).
It sets four GiB of memory with no additional swap, verifies actual HostConfig and
memory-controller limits, and observes compiler processes inside that capped
cgroup. It retains limits, peak usage, events, source/image identity and full build
logs. Only its own builder, container and cache are removed after execution.

The validator uses the built immutable image ID, required UID/EUID 1006410000,
read-only inputs and disabled networking. It verifies the actual image's runtime
and source-manifest hashes before running six sequential cases: a normal 30-second
smoke and an early accepted-checkpoint SIGTERM case for each of B01/B11/B12.
TERM cases configure a 90-second budget and interrupt early; signal delivery and
observed exit together must take at most ten seconds. Frozen environment controls
are applied explicitly, with only the documented smoke budget and artifact path
overridden. These are not the separate 585-second full-panel arms.

Independent official checks accept the final solutions and saved pre-signal
solutions. Complete exact saturation vectors determine selected-report equality
and non-regression across the signal. Each case stops any remaining owned
containers before advancing, and forced cleanup is recorded as a failure. Actual
host/runtime resource observations remain separate from the four-GiB build limit.
The hosted validator runs with sudo to read private files created by the required
numeric UID; only its result directory changes ownership after execution.

## Method and held artifact

The workflow fetches and verifies `S139-method.md` and `build_method_pdf.py` from
the same frozen commit. It executes that unchanged generator in an isolated
Python environment with `reportlab==4.4.9`; `pypdf==6.10.0` independently confirms
two pages. The dependency inventory and exact generated PDF are retained.

`package_held.py` requires passing build/runtime receipts and matching source,
image, context and documentation identities. It packages the unchanged tested
context plus `method.pdf`, the frozen manifest and a complete SHA256 inventory.
The artifact is explicitly held and its receipt keeps visual review pending until
both final generated pages are rendered and inspected after the job. The existing
S139 draft and attachment are not replaced, and no submission is sent.

The always-run artifact step retains build failures, runtime evidence, exact
sources, workflow and hash inventories, including intentional public hidden files.
A prepared workflow or package is not itself evidence that execution or visual
review passed; completed receipts are published separately after verification.

## Local invocation on an existing Docker host

Choose fresh work, result and package directories:

```sh
python3 -B revenue/roadef2026/container-validation/bootstrap.py --output /tmp/roadef-fleet-work
python3 -B revenue/roadef2026/container-validation/build_with_limit.py --context /tmp/roadef-fleet-work/context --image roadef-fleet --output /tmp/roadef-fleet-work/build-evidence
sudo python3 -B revenue/roadef2026/container-validation/validate.py --image roadef-fleet --data /tmp/roadef-fleet-work/data --preparation /tmp/roadef-fleet-work/PREPARATION.json --output /tmp/roadef-fleet-results
```

The workflow contains the corresponding PDF generation and held-package commands.
Prior PR10181 B01/early-TERM execution remains frozen in its separate receipt;
this candidate and acceptance contract are a distinct execution. Neither proves
competition rank, hidden-instance performance, official-hardware behavior or a
complete final-drain timing matrix.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
