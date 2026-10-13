# Oracle Always Free Commons carrier

This Resource Manager/Terraform stack turns Oracle Cloud's current Always Free
Ampere allocation into an additional Commons compute and copy-only storage
carrier. It composes with GitHub, Google Drive, and the existing Muhlnickel
cloud-substrate carrier; it replaces none of them.

The source screenshot claimed 2 Ampere A1 OCPUs, 12 GB RAM, 200 GB block
storage, and 10 TB monthly outbound transfer. Oracle's current primary
documentation confirms those bounds for an Always Free tenancy. The 200 GB is
combined boot and attached block capacity, not 200 GB in addition to the boot
disk. This stack therefore uses Oracle's documented 50 GB boot + 150 GB
attached-volume layout in the tenancy's home region.

Primary sources, checked 2026-08-27:

- <https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm>
- <https://www.oracle.com/cloud/free/>

## What lands

- one `VM.Standard.A1.Flex` Ubuntu/aarch64 instance at exactly 2 OCPUs / 12 GB;
- one 50 GB boot volume and one 150 GB paravirtualized data volume;
- `/srv/commons-cloud/{work,evacuation,receipts}` on the attached volume;
- Git, Python, rclone, jq, and XFS tooling installed by cloud-init;
- a machine-readable `COMMONS_CLOUD_ROUTE.json` truth boundary on the volume;
- outbound network reachability for GitHub/cloud carriers while preserving
  Commons' existing open-door access semantics.

The bootstrap has no delete, move, prune, garbage-collection, overwrite, or
local-release operation. Existing owner-PC bytes remain untouched. Use
`host/commons_cloud_evacuation.py` for copy + remote hash readback, and treat
`cloud_complete=true` as mandatory evidence before any later owner decision.

## Provision through OCI Resource Manager

Zip this directory or point an OCI Resource Manager stack at it, set the
tenancy, compartment, and home-region OCIDs, then apply. Resource Manager is
itself included in Oracle's Always Free services. The stack deliberately uses
the Always Free bounds exactly; do not raise the shape or volume sizes without
rechecking the live tenancy limits.

`capacity.json` stays `READY_NOT_PROVISIONED` until an actual apply and remote
readback occur. A Terraform plan, tweet, or repository merge is not proof that
the VM or cloud bytes exist.

Oracle notes two operational limits that Commons must keep visible:

- Always Free shape capacity may be unavailable in one availability domain;
  retry another domain or later rather than claiming a provisioned instance.
- idle Always Free compute may be reclaimed. Real Commons workloads count;
  artificial keep-busy loops are not evidence and are not included here.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
