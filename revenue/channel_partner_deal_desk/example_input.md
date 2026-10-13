# Synthetic operator walkthrough

This file is documentation only; the runnable synthetic flow is `python channel_partner_deal_desk.py demo DB OUT_DIR`.

The demo uses no real partner/customer names or provider data. It creates:

- partner `partner.demo`;
- immutable terms `terms.demo.v1`, 1,250 bps and 90-day deal protection;
- opaque buyer `buyer.demo` / opportunity `opportunity.demo`;
- exact proposed value 1,500,000 USD minor units;
- buyer-acceptance evidence;
- 1,500,000 USD-minor settlement evidence.

The resulting commission is 187,500 USD minor units and the state is `COMMISSION_DUE_FOR_OWNER_REVIEW`. No payment event is created by the demo.
