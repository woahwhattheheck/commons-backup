# Wyoming OSPD 0046-N — Prime Teaming Carrier

Operation: `WY-OSPD-0046N-PRIME-TEAMING-ZRHN7Q4-20260913`

This directory is an internal/public **commercial control and scope carrier**, not the private Case-Event→Calendar Integrity Engine and not a bid submission. It exists so an inbound prime reply can be converted into a paid, bounded work package without violating the buyer's procurement channel or accidentally drifting into free bespoke implementation.

## Verified procurement boundary (2026-09-13)

- Buyer: State of Wyoming, Office of the State Public Defender.
- Solicitation: RFP `0046-N`, Case Management System.
- Proposal deadline: 2026-10-02 14:00 MT.
- Written-question deadline: 2026-09-08 14:00 MT (already closed when this carrier was created).
- Solicitation communication and proposals use Public Purchase. Do **not** email/phone the procurement representative about the RFP from this lane.
- Official bid hub: <https://ai.wyo.gov/divisions/general-services/purchasing/bid-opportunities>
- Public Purchase buyer page: <https://www.publicpurchase.com/gems/wyominggsd%2Cwy/buyer/public/publicInfo>

## Commercial strategy

Two platform vendors with current public-defender CMS products were approached through their own published business routes, not through Wyoming procurement:

- Journal Technologies — eDefender — `sales@journaltech.com`
- Karpel Solutions — DEFENDERbyKarpel — `info@karpel.com`

The offered seam is deliberately narrow enough to be testable but commercially meaningful: a **$2,500 fixed synthetic sandbox proof** or a negotiated paid integration/acceptance subcontract around migration replay, calendaring, and third-party handoff integrity.

This lane does not claim either vendor is bidding, that TokenJunkieLabs is qualified as prime, that the buyer approved subcontracting, or that any award/payment is likely.

## Use

```bash
python revenue/wyoming_ospd_0046n_prime_teaming/teaming_kit.py --partner "Journal Technologies"
python revenue/wyoming_ospd_0046n_prime_teaming/teaming_kit.py --partner "Karpel Solutions"
python -m unittest discover -s revenue/wyoming_ospd_0046n_prime_teaming/tests -v
```

The renderer validates the commercial/procurement safety manifest and exact 12-case synthetic acceptance matrix before it emits a partner work package. Any drift toward direct buyer email, free custom work, a different proof price, live client data, production writes, or an incomplete fixture set fails closed.

## Private-product boundary

The private delivery artifact referenced by the Aug-30 lead thread is intentionally **not** published here. Do not send this GitHub/Commons path as product delivery. A partner yes + paid scope/PO gates buyer-specific configuration and direct delivery.
