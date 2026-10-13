# SPDX-License-Identifier: Apache-2.0
"""Execute the complete RouteFoundry acceptance flow against a real local server."""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
from pathlib import Path
import threading
from typing import Any
from urllib.parse import urlsplit

from app import make_server


def request(base: str, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, str], bytes]:
    parts = urlsplit(base)
    connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=5)
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    raw = response.read()
    result = response.status, {key.lower(): value for key, value in response.getheaders()}, raw
    connection.close()
    return result


def decode(raw: bytes) -> dict[str, Any]:
    return json.loads(raw.decode("utf-8"))


def run(db: Path) -> dict[str, Any]:
    server = make_server(
        db_path=db, port=0, brand_name="RouteFoundry Demo",
        public_base_url="https://go.northstar.example",
        access_log=False,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    public_base = server.settings.public_base_url
    local_base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, _, raw = request(local_base, "POST", "/api/products", {"name": "Creator Launch Kit", "brand": "Northstar Studio"})
        assert status == 201, raw
        product = decode(raw)
        status, _, raw = request(local_base, "POST", "/api/offers", {
            "product_id": product["id"], "name": "Launch offer",
            "headline": "Turn one launch into three measurable campaigns",
            "body": "Keep the link stable. Edit the destination. Know which campaign converted.",
            "cta_label": "Open the launch kit",
        })
        assert status == 201, raw
        offer = decode(raw)

        presets = []
        for name, source, medium, content in (
            ("YouTube", "youtube", "video", "description"),
            ("Newsletter", "newsletter", "email", "issue-01"),
            ("Partner", "partner", "referral", "launch-partner"),
        ):
            status, _, raw = request(local_base, "POST", "/api/presets", {
                "name": name, "utm_source": source, "utm_medium": medium,
                "utm_campaign": "creator-kit-launch", "utm_content": content, "utm_term": "",
            })
            assert status == 201, raw
            presets.append(decode(raw))

        links = []
        for slug, preset, mode in (
            ("creator-youtube", presets[0], "offer"),
            ("creator-newsletter", presets[1], "offer"),
            ("creator-partner", presets[2], "redirect"),
        ):
            status, _, raw = request(local_base, "POST", "/api/links", {
                "slug": slug, "product_id": product["id"], "offer_id": offer["id"],
                "preset_id": preset["id"], "destination": "https://example.com/creator-kit-v1",
                "route_mode": mode,
            })
            assert status == 201, raw
            links.append(decode(raw))

        status, _, qr_before = request(local_base, "GET", "/q/creator-youtube.svg")
        assert status == 200
        status, _, raw = request(local_base, "PATCH", "/api/links/creator-youtube", {
            "destination": "https://example.com/creator-kit-v2?plan=agency"
        })
        assert status == 200, raw
        status, _, qr_after = request(local_base, "GET", "/q/creator-youtube.svg")
        assert status == 200

        status, _, offer_page = request(local_base, "GET", "/r/creator-youtube")
        assert status == 200
        status, _, state_raw = request(local_base, "GET", "/api/state")
        workspace = decode(state_raw)
        click = next(event for event in workspace["recent_events"] if event["event_type"] == "click")
        status, conversion_headers, _ = request(local_base, "GET", f"/convert/creator-youtube?click={click['event_id']}")
        assert status == 302

        status, redirect_headers, _ = request(local_base, "GET", "/r/creator-partner")
        assert status == 302
        duplicate_id = "demo_conversion_0001"
        first = request(local_base, "POST", "/api/events", {
            "slug": "creator-newsletter", "event_type": "conversion", "event_id": duplicate_id,
        })
        second = request(local_base, "POST", "/api/events", {
            "slug": "creator-newsletter", "event_type": "conversion", "event_id": duplicate_id,
        })

        status, _, report_raw = request(local_base, "GET", "/api/report")
        assert status == 200
        report = decode(report_raw)
        status, _, final_state_raw = request(local_base, "GET", "/api/state")
        final_state = decode(final_state_raw)
        final_link = next(item for item in final_state["links"] if item["slug"] == "creator-youtube")
        campaign_rows = [row for row in report["campaigns"] if row["utm_campaign"] == "creator-kit-launch"]
        campaign = {
            "utm_campaign": "creator-kit-launch",
            "sources": len(campaign_rows),
            "links": sum(int(row["links"]) for row in campaign_rows),
            "clicks": sum(int(row["clicks"]) for row in campaign_rows),
            "conversions": sum(int(row["conversions"]) for row in campaign_rows),
        }

        result = {
            "schema": "routefoundry.acceptance.v1",
            "database": str(db),
            "public_base_url": public_base,
            "product_id": product["id"],
            "created_slugs": [item["slug"] for item in links],
            "stable_short_url": final_link["short_url"],
            "destination_after_edit": final_link["destination"],
            "qr_sha256_before": hashlib.sha256(qr_before).hexdigest(),
            "qr_sha256_after": hashlib.sha256(qr_after).hexdigest(),
            "offer_page_selected": b"Turn one launch into three measurable campaigns" in offer_page,
            "conversion_redirect": conversion_headers.get("location"),
            "direct_redirect": redirect_headers.get("location"),
            "duplicate_event_first_created": decode(first[2])["created"],
            "duplicate_event_second_created": decode(second[2])["created"],
            "campaign_report": campaign,
            "checks": {
                "three_links_created": len(final_state["links"]) == 3,
                "destination_edit_persisted": final_link["destination"].endswith("creator-kit-v2?plan=agency"),
                "short_url_stable": final_link["short_url"].endswith("/r/creator-youtube"),
                "qr_payload_stable": qr_before == qr_after,
                "offer_route_works": b"Turn one launch into three measurable campaigns" in offer_page,
                "click_attributed": campaign["clicks"] >= 2,
                "conversion_attributed": campaign["conversions"] == 2,
                "event_id_deduplicated": decode(first[2])["created"] is True and decode(second[2])["created"] is False,
                "utm_applied": "utm_source=partner" in redirect_headers.get("location", ""),
            },
        }
        result["ok"] = all(result["checks"].values())
        return result
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("routefoundry-demo.db"))
    parser.add_argument("--reset", action="store_true", help="Remove an existing demo database before running.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.db.exists():
        if not args.reset:
            parser.error(f"{args.db} already exists; pass --reset or choose another path")
        args.db.unlink()
    result = run(args.db)
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
