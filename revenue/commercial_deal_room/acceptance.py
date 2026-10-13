from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from .engine import compile_board, sha256_hex

NOW = datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc)
D = "1" * 64
E = "2" * 64
P = "3" * 64
R = "4" * 64
A = "5" * 64


def base_packet(name: str):
    return {
        "version": "commercial-deal-room/v1",
        "buyer_id": f"buyer-{name}",
        "opportunity_id": f"opp-{name}",
        "offer": {
            "offer_id": f"offer-{name}",
            "currency": "USD",
            "price_minor": 250000,
            "required_before_start_minor": 250000,
            "scope_sha256": D,
            "terms_sha256": E,
            "created_at": "2026-09-13T12:00:00Z",
            "expires_at": "2026-09-20T12:00:00Z",
        },
        "events": [],
    }


def add(packet, event_id, typ, at, payload, source_sha=A):
    packet["events"].append(
        {
            "event_id": event_id,
            "type": typ,
            "buyer_id": packet["buyer_id"],
            "opportunity_id": packet["opportunity_id"],
            "offer_id": packet["offer"]["offer_id"],
            "observed_at": at,
            "source_ref": f"synthetic:{event_id}",
            "source_sha256": source_sha,
            "payload": payload,
        }
    )


def offer_sent(packet, t="2026-09-13T12:10:00Z"):
    add(packet, "send-1", "OFFER_SENT", t, {"provider":"gmail","provider_message_id":"m-send-1","scope_sha256":D,"terms_sha256":E})


def accepted_path(name: str):
    p = base_packet(name)
    offer_sent(p)
    add(p,"interest-1","BUYER_INTEREST","2026-09-13T12:20:00Z",{"provider":"gmail","provider_message_id":"m-int-1","reply_to_event_id":"send-1"})
    add(p,"proposal-1","PROPOSAL_SENT","2026-09-13T12:30:00Z",{"provider":"gmail","provider_message_id":"m-prop-1","reply_to_event_id":"interest-1","proposal_sha256":P,"revision":1})
    add(p,"accept-1","BUYER_ACCEPTED","2026-09-13T12:40:00Z",{"provider":"gmail","provider_message_id":"m-acc-1","reply_to_event_id":"proposal-1","accepted_proposal_sha256":P})
    return p


def acceptance_summary():
    packets = []
    p = base_packet("offer-ready"); packets.append(p)
    p = base_packet("awaiting"); offer_sent(p); packets.append(p)
    p = base_packet("interest"); offer_sent(p); add(p,"interest-1","BUYER_INTEREST","2026-09-13T12:20:00Z",{"provider":"gmail","provider_message_id":"m-int-1","reply_to_event_id":"send-1"}); packets.append(p)
    p = accepted_path("accepted"); packets.append(p)
    p = accepted_path("road"); add(p,"road-1","PAYMENT_ROAD_CONFIGURED","2026-09-13T12:45:00Z",{"route_id":"stripe-link-1","route_sha256":R}); packets.append(p)
    p = deepcopy(p); p["buyer_id"]="buyer-request"; p["opportunity_id"]="opp-request"; p["offer"]["offer_id"]="offer-request"; 
    for e in p["events"]: e["buyer_id"]=p["buyer_id"]; e["opportunity_id"]=p["opportunity_id"]; e["offer_id"]=p["offer"]["offer_id"]
    add(p,"payreq-1","PAYMENT_REQUEST_SENT","2026-09-13T12:50:00Z",{"provider":"gmail","provider_message_id":"m-pay-1","route_id":"stripe-link-1","currency":"USD","amount_minor":250000}); packets.append(p)
    p2 = deepcopy(p); p2["buyer_id"]="buyer-funded"; p2["opportunity_id"]="opp-funded"; p2["offer"]["offer_id"]="offer-funded";
    for e in p2["events"]: e["buyer_id"]=p2["buyer_id"]; e["opportunity_id"]=p2["opportunity_id"]; e["offer_id"]=p2["offer"]["offer_id"]
    add(p2,"settle-1","SETTLEMENT_OBSERVED","2026-09-13T13:00:00Z",{"settlement_id":"s1","route_id":"stripe-link-1","currency":"USD","amount_minor":250000}); packets.append(p2)
    p3 = deepcopy(p2); p3["buyer_id"]="buyer-ready"; p3["opportunity_id"]="opp-ready"; p3["offer"]["offer_id"]="offer-ready2";
    for e in p3["events"]: e["buyer_id"]=p3["buyer_id"]; e["opportunity_id"]=p3["opportunity_id"]; e["offer_id"]=p3["offer"]["offer_id"]
    add(p3,"artifact-1","FULFILLMENT_ARTIFACT","2026-09-13T13:10:00Z",{"artifact_id":"a1","artifact_sha256":A}); packets.append(p3)
    p4 = deepcopy(p3); p4["buyer_id"]="buyer-delivered"; p4["opportunity_id"]="opp-delivered"; p4["offer"]["offer_id"]="offer-delivered";
    for e in p4["events"]: e["buyer_id"]=p4["buyer_id"]; e["opportunity_id"]=p4["opportunity_id"]; e["offer_id"]=p4["offer"]["offer_id"]
    add(p4,"delivery-1","FULFILLMENT_SENT","2026-09-13T13:20:00Z",{"provider":"gmail","provider_message_id":"m-del-1","artifact_event_id":"artifact-1"}); packets.append(p4)
    p5 = deepcopy(p4); p5["buyer_id"]="buyer-closed"; p5["opportunity_id"]="opp-closed"; p5["offer"]["offer_id"]="offer-closed";
    for e in p5["events"]: e["buyer_id"]=p5["buyer_id"]; e["opportunity_id"]=p5["opportunity_id"]; e["offer_id"]=p5["offer"]["offer_id"]
    add(p5,"fulfill-accept-1","BUYER_FULFILLMENT_ACCEPTED","2026-09-13T13:30:00Z",{"provider":"gmail","provider_message_id":"m-fa-1","reply_to_event_id":"delivery-1","artifact_event_id":"artifact-1"}); packets.append(p5)
    p6 = base_packet("dnr"); offer_sent(p6); add(p6,"dnr-1","DNR","2026-09-13T12:30:00Z",{"reason_code":"buyer-no"}); packets.append(p6)
    p7 = base_packet("collision"); offer_sent(p7); add(p7,"send-2","OFFER_SENT","2026-09-13T12:11:00Z",{"provider":"gmail","provider_message_id":"m-send-2","scope_sha256":D,"terms_sha256":E}); packets.append(p7)

    boards = [compile_board(p, now=NOW) for p in packets]
    counts = {}
    for b in boards:
        counts[b["stage"]] = counts.get(b["stage"], 0) + 1
    digest = sha256_hex(b"".join((b["receipt_sha256"]+"\n").encode() for b in boards))
    return {"count": len(boards), "stages": counts, "receipt_set_sha256": digest}


if __name__ == "__main__":
    import json
    print(json.dumps(acceptance_summary(), sort_keys=True))
