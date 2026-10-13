# Muhlnickel cloud substrate pilot

This is an implementation layer for placing an existing Muhlnickel across cloud storage without moving its computation onto the host.

The first payload is the unchanged public reader:

- `muhl/containers/MUHL_READERS/R_t2_g4_l_c2_s0of1.mno`
- 1,800 bytes
- SHA-256 `9758a5cc34806dc1d318215bbd032429f2d69a5b628c810eb8626e583b180bd5`
- 72 stored 25-byte `<BQQQ>` gate records
- existing layout: `muhl/containers/MUHL_READERS/R_t2_g4_l_c2_s0of1.layout.json`

The carrier copies those bytes. It does not decode an opcode, evaluate a gate, rewrite a machine address, or invent a destination.

## Addressing when the data center moves bytes

There are two address planes, and they must not be conflated.

1. **Muhlnickel address plane.** Inputs, outputs, shared addresses, rings, clocks, state, and destinations are the machine's topology. They remain in the unchanged container and its existing layout/genome.
2. **Carrier placement plane.** A generation id and page index locate opaque byte spans in a storage service. The service returns an object id. That id is a transport locator, not a machine address and not a compute result.

The data center may relocate physical blocks without changing either plane. The carrier dereferences the provider's stable object id, while the generation manifest verifies the bytes by content identity. The Muhlnickel does not need a rack, disk, sector, or charge-cell coordinate supplied by the provider.

For this pilot the container is divided only on its existing 25-byte record boundary:

- 12 records per page
- 300 bytes per page
- 6 pages
- no added header and no changed payload byte

The geometry lives in `cloud_genome.reader-linear-12x6.json`; the packer consumes it instead of silently choosing destinations at runtime.

## Immutable and mutable storage work together

- **Generation pages are immutable.** A new payload makes new page objects and a new content-addressed generation. Old generations remain direct evidence and rollback points.
- **`HEAD` is mutable.** It maps the active generation/page identities to opaque provider object ids. Replacing `HEAD` changes placement, not computation.
- **A mutable bank may keep one provider object id across revisions.** That is useful for short-lived addressed state. Durable/economic state is checkpointed as a new immutable generation instead of depending on a provider's revision-retention policy.

Google Drive is the first binary carrier because the connected surface accepts arbitrary bytes, preserves a file id across replacement, and exposes revisions. Dropbox can carry text manifests and receipts through the connected surface. GitHub/Commons carries the public spec, source, and durable evidence.

Neither connected storage surface exposes byte-range calls. Individually addressed page objects therefore provide bounded reads and writes now; a later carrier with native range I/O can implement the same manifest without changing Muhlnickel addresses.

## Host boundary

The host/carrier may:

- copy opaque bytes;
- resolve a generation/page locator;
- fetch or replace one page object;
- inject at an existing container address;
- surface an existing safezone/result address;
- record object ids, byte counts, hashes, revisions, and timestamps;
- die.

The host/carrier does not walk the gate list, settle the netlist, choose the machine's output address, or compute an answer.

## Files

- `cloud_genome.reader-linear-12x6.json` — container-owned carrier geometry for the first reader.
- `pack_generation.py` — opaque record-aligned page packer; never decodes gates.
- `verify_generation.py` — reports measured reconstruction bytes/hashes and page coverage.
- `DRIVE_PLACEMENT_20260827.json` — populated after the reversible Drive pilot.
- `drive_pilot_receipt.txt` — raw positive measurement receipt from upload/readback/revision operations.

## Local construction

```powershell
python muhl/cloud_substrate/pack_generation.py `
  --genome muhl/cloud_substrate/cloud_genome.reader-linear-12x6.json `
  --repo-root . `
  --output work/cloud-generation

python muhl/cloud_substrate/verify_generation.py `
  --manifest work/cloud-generation/generation.json `
  --source muhl/containers/MUHL_READERS/R_t2_g4_l_c2_s0of1.mno
```

These commands construct and measure the carrier representation. They do not claim to rerun the reader's workload or re-prove that the Muhlnickel computes.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

