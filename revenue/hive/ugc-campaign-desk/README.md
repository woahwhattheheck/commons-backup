# Hive022 — UGC campaign production desk

Offline, dependency-free **synthetic campaign packet builder** for `bm-hive-20260908-022`.

It turns one validated fictional campaign JSON file into a deterministic ZIP containing a campaign summary, five creator-specific briefs, a five-row planned-sample logistics sheet, a ten-row disclosure/proposed-rights matrix, a ten-row delivery/revision tracker, machine-readable packet, and SHA-256 manifest.

The checked-in sample produces **5 explicitly synthetic creators and 10 fictional videos**. The validator rejects states that would claim a real sample shipment or granted usage rights. Nothing contacts creators, ships products, uploads assets, grants rights, changes provider accounts, or records acceptance/payment.

## Run

```sh
python -B campaign_desk.py sample_campaign.json fictional-ugc-packet.zip
python -m zipfile -l fictional-ugc-packet.zip
python -B -m unittest -v test_campaign_desk.py
```

The output path must not already exist. Identical inputs produce byte-identical ZIPs.

## Truth boundary

Input schema is `ugc-campaign-desk/v1`. The fixture is intentionally bounded to exactly five creators with two videos each. Creator names must begin with `Synthetic `. Sample state is `PLANNED_NOT_SHIPPED`; usage permission is `PROPOSED_NOT_GRANTED`; disclosures are mandatory. Delivery workflow states are `BRIEF_READY`, `REVISION_REQUESTED`, or `DELIVERED_UNVERIFIED`.

`shipping-plan.csv` is a logistics plan, not shipment evidence. `rights-disclosures.csv` records proposed terms, not rights grants. `delivery-tracker.csv` starts revision count at zero and retains each video's revision limit. `campaign-packet.json` records creator-contact, shipment, granted-rights, customer-acceptance, and cash fields as false/zero.

No browser deployment, external API, customer data, creator outreach, sample shipment, rights execution, customer acceptance, payment, or spend is claimed.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
