#!/usr/bin/env python3
"""Provider-neutral payment-capability registry and storefront failover.

Reuses checkout_capability, catalog SKUs, payment_ready money states,
reply-to-revenue cash truth, and scope-to-delivery money separation.
Never calls a provider, never stores bank/routing/tax/credentials, and
never claims current cash. Recorded offline amounts remain separate from the
unverified receiving-rail state; missing live evidence never becomes zero.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any


ROOT_DEFAULT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join("revenue", "payment_capability", "registry.json")
SNAPSHOT = os.path.join("revenue", "checkout_capability", "snapshot.json")
CATALOG = os.path.join("revenue", "outcome_commerce", "catalog.json")
FUNNEL = os.path.join("revenue", "reply_to_revenue", "funnel.json")
BINDINGS = os.path.join("revenue", "scope_to_delivery", "catalog_bindings.json")
PACK = os.path.join("revenue", "payment_ready", "pack.json")
STRIPE_URL_RE = re.compile(r"^https://(?:buy|donate)\.stripe\.com/[A-Za-z0-9_-]+$")
STRIPE_HTML_URL_RE = re.compile(r"https://(?:buy|donate)\.stripe\.com/")
BUY_HOST_PATH_RE = re.compile(r"https?://buy\.stripe\.com/([A-Za-z0-9_-]+)", re.I)
DONATE_HOST_PATH_RE = re.compile(r"https?://donate\.stripe\.com/([A-Za-z0-9_-]+)", re.I)
BUY_HTTPS_URL_RE = re.compile(r"https://buy\.stripe\.com/[A-Za-z0-9_-]+")
HTTP_BUY_URL_RE = re.compile(r"http://buy\.stripe\.com/", re.I)
PAY_CONVERT_SHELF_LIVE_BUYS = frozenset(
    {
        "https://buy.stripe.com/14AfZgckZ0IN0Y99h043S0e",
        "https://buy.stripe.com/28E9AS70F6378qB2SC43S0w",
        "https://buy.stripe.com/14AfZg1Gl3UZ7mxfFo43S0x",
        "https://buy.stripe.com/7sYdR8ckZgHLbCN50K43S0y",
    }
)
COMMERCE_CONVERT_SHELF_LIVE_BUYS = frozenset(
    {
        "https://buy.stripe.com/3cIdR8gBf6379uF1Oy43S0b",
        "https://buy.stripe.com/9B600i98N77b9uFeBk43S0c",
        "https://buy.stripe.com/9B66oGacR2QVdKVeBk43S0d",
        "https://buy.stripe.com/14AfZgckZ0IN0Y99h043S0e",
        "https://buy.stripe.com/7sYdR8ckZgHLbCN50K43S0y",
        "https://buy.stripe.com/14AfZg1Gl3UZ7mxfFo43S0x",
        "https://buy.stripe.com/28E9AS70F6378qB2SC43S0w",
        "https://buy.stripe.com/8x27sK2Kp3UZ9uF2SC43S07",
    }
)
PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS = frozenset(
    {
        "https://buy.stripe.com/8x27sK2Kp3UZ9uF2SC43S07",
    }
)
CONVERT_SHELF_LIVE_BUYS = {
    "pay.html": PAY_CONVERT_SHELF_LIVE_BUYS,
    "commerce.html": COMMERCE_CONVERT_SHELF_LIVE_BUYS,
    "payment-capability.html": COMMERCE_CONVERT_SHELF_LIVE_BUYS,
    "reply-to-revenue.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "claude-paste.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "mcp-tool-drift.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "failed.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "task-forge.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "subzero-receipt.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "subzero-quote.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "data-license.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "gemini-mcp.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "manual.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "pixel-portfolio.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "todo.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "redundancy.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "distro.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "paperwork-included.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "unbuilt-items.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "webmcp.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "skills.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "swarm.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "embassy.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "glyphs.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "program.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "foldbook.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "flipbook.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "compress.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "command.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "coordination.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "observatory.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "tabletop.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "insights.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "grounding.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "open-door.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "interconnect.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "merge-on-pr.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "landed-work.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "owner-now-revenue.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "ace-qat-thermal-rheology-capacity-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "agriseed-rush-work-allocator-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "ait-mn-metrc-capacity-gate.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "aquatrace-ops-acceptance.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "aquatrace-work-order-b-production-foundation.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "aquatrace-work-order-c-reporting-offline.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "aquatrace-work-order-f-release-readiness.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "at-grok-adapter-evidence.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "at-grok-cmdp-evidence.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "ats-asphalt-spec-result-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "paid-opportunities.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "right-now.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "baddl-eia-accession-release-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "billings-bid-1421-acceptance-runner.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "billings-bid-1421-operations-runner.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "billings-bid-1421-partner-recon.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "bsk-multilab-accession-parity-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "canyon-multisite-regulated-intake.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "ccc-snapshot-toolchain.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "chemtechford-short-hold-intake-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "clark-d4172-proficiency-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "cornell-craft-beverage-intake-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "corrigan-specialty-fuel-blend-dossier-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "csanalytical-expansion-crossline-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "csplabs-express-capacity-assurance-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "ddl-crosssite-method-proficiency-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "discount-concession-leakage.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "eagletrax-split-sample-preflight-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "elevatebio-pittsburgh-replication-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "highpower-ssf-receiving-gate-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "kincell-rtp-qc-release-bridge-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "lexington-mrf-diversion-gate.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "luvak-ssa-lab-analytics-cutover-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "made-scientific-princeton-rapid-qc-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "oregon-brewlab-sample-report-reconciliation-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "pace-lebanon-microbial-volume-evidence-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "paragon-biodiesel-sample-coa-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "pcl-scope-sla-routing-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "preinnewhof-pfas-fieldblank-gate-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "ptl-controlled-sample-order-preflight.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "qlabs-qconnect-cutover-verification-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "rmb-crosssite-courier-accession-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "rosecity-olcc-metrc-sampling-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "roslinct-hopkinton-paperless-qc-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "sanair-asbestos-coc-router-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "savant-fe8-order-report-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "sc-labs-multistate-coa-rule-version-gate.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "sgspsi-thermal-rheology-lineage-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "sharp-rtu-vial-isolator-lineage-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "slo-cls-cutover-evidence-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "torrent-workorder-commissioning-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "trace-sila-ml-iatf-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "wadsworth-five-site-consolidation-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "ward-feed-nirs-intake-validator-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "weck-coc-preaccession-validator-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "westpak-scope-capacity-routing-lims.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "organabio-multisite-donor-coa.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "subzero-proof.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "pixel-unify.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "proof-spiral-succinct-argument.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "muhlnickel-free-sample.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "titan-hands-free-sample.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "proof-to-proposal.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "the-world.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "image-drop.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "muhl-train.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
    "post-http.html": PEERS_REPLY_CONVERT_SHELF_LIVE_BUYS,
}
TIPS_CONVERT_SHELF_LIVE_CHECKOUTS = frozenset(
    {
        "https://donate.stripe.com/fZucN40Ch9fj7mxgJs43S08",
        "https://buy.stripe.com/3cIeVc5WB1MRgX7al443S03",
        "https://buy.stripe.com/3cIbJ0ckZgHL36h8cW43S04",
        "https://buy.stripe.com/bJe28qacR4Z3gX7bp843S05",
        "https://buy.stripe.com/3cIfZgacRezDfT39h043S06",
    }
)
WHITEBOX_HOUR_CHECKOUT = "https://buy.stripe.com/8x27sK2Kp3UZ9uF2SC43S07"
PAY_CONVERT_SHELF_LIVE_CHECKOUTS = (
    PAY_CONVERT_SHELF_LIVE_BUYS | TIPS_CONVERT_SHELF_LIVE_CHECKOUTS | {WHITEBOX_HOUR_CHECKOUT}
)
COMMERCE_CONVERT_SHELF_LIVE_CHECKOUTS = (
    COMMERCE_CONVERT_SHELF_LIVE_BUYS | TIPS_CONVERT_SHELF_LIVE_CHECKOUTS
)
OWNER_ACTION_HOSTS = {
    "dashboard.stripe.com",
    "www.paypal.com",
    "paypal.com",
    "github.com",
    "squareup.com",
    "www.squareup.com",
}
FORBIDDEN = (
    r"\brouting[_\s-]?number\b.+\d{9}\b",
    r"\baccount[_\s-]?number\b.+\d{8,17}\b",
    r"\bIBAN\b\s*[A-Z]{2}\d{2}[A-Z0-9]{10,}",
    r"\b(?:4\d{15}|5[1-5]\d{14})\b",
    r"\bcvv\b\s*\d{3,4}\b",
    r"\bssn\b\s*\d{3}-\d{2}-\d{4}\b",
)
PUBLIC_HTML = (
    "pay.html",
    "tips.html",
    "commerce.html",
    "payment-capability.html",
    "reply-to-revenue.html",
    "owner-now-revenue.html",
    "claude-paste.html",
    "mcp-tool-drift.html",
    "failed.html",
    "task-forge.html",
    "subzero-receipt.html",
    "subzero-quote.html",
    "data-license.html",
    "gemini-mcp.html",
    "manual.html",
    "pixel-portfolio.html",
    "todo.html",
    "redundancy.html",
    "distro.html",
    "paperwork-included.html",
    "unbuilt-items.html",
    "webmcp.html",
    "skills.html",
    "swarm.html",
    "embassy.html",
    "glyphs.html",
    "program.html",
    "foldbook.html",
    "flipbook.html",
    "compress.html",
    "command.html",
    "coordination.html",
    "observatory.html",
    "tabletop.html",
    "insights.html",
    "grounding.html",
    "open-door.html",
    "interconnect.html",
    "merge-on-pr.html",
    "landed-work.html",
    "ace-qat-thermal-rheology-capacity-lims.html",
    "agriseed-rush-work-allocator-lims.html",
    "ait-mn-metrc-capacity-gate.html",
    "aquatrace-ops-acceptance.html",
    "aquatrace-work-order-b-production-foundation.html",
    "aquatrace-work-order-c-reporting-offline.html",
    "aquatrace-work-order-f-release-readiness.html",
    "at-grok-adapter-evidence.html",
    "at-grok-cmdp-evidence.html",
    "ats-asphalt-spec-result-lims.html",
    "paid-opportunities.html",
    "right-now.html",
    "baddl-eia-accession-release-lims.html",
    "billings-bid-1421-acceptance-runner.html",
    "billings-bid-1421-operations-runner.html",
    "billings-bid-1421-partner-recon.html",
    "bsk-multilab-accession-parity-lims.html",
    "canyon-multisite-regulated-intake.html",
    "ccc-snapshot-toolchain.html",
    "chemtechford-short-hold-intake-lims.html",
    "clark-d4172-proficiency-lims.html",
    "cornell-craft-beverage-intake-lims.html",
    "corrigan-specialty-fuel-blend-dossier-lims.html",
    "csanalytical-expansion-crossline-lims.html",
    "csplabs-express-capacity-assurance-lims.html",
    "ddl-crosssite-method-proficiency-lims.html",
    "discount-concession-leakage.html",
    "eagletrax-split-sample-preflight-lims.html",
    "elevatebio-pittsburgh-replication-lims.html",
    "highpower-ssf-receiving-gate-lims.html",
    "kincell-rtp-qc-release-bridge-lims.html",
    "lexington-mrf-diversion-gate.html",
    "luvak-ssa-lab-analytics-cutover-lims.html",
    "made-scientific-princeton-rapid-qc-lims.html",
    "oregon-brewlab-sample-report-reconciliation-lims.html",
    "pace-lebanon-microbial-volume-evidence-lims.html",
    "paragon-biodiesel-sample-coa-lims.html",
    "pcl-scope-sla-routing-lims.html",
    "preinnewhof-pfas-fieldblank-gate-lims.html",
    "ptl-controlled-sample-order-preflight.html",
    "qlabs-qconnect-cutover-verification-lims.html",
    "rmb-crosssite-courier-accession-lims.html",
    "rosecity-olcc-metrc-sampling-lims.html",
    "roslinct-hopkinton-paperless-qc-lims.html",
    "sanair-asbestos-coc-router-lims.html",
    "savant-fe8-order-report-lims.html",
    "sc-labs-multistate-coa-rule-version-gate.html",
    "sgspsi-thermal-rheology-lineage-lims.html",
    "sharp-rtu-vial-isolator-lineage-lims.html",
    "slo-cls-cutover-evidence-lims.html",
    "torrent-workorder-commissioning-lims.html",
    "trace-sila-ml-iatf-lims.html",
    "wadsworth-five-site-consolidation-lims.html",
    "ward-feed-nirs-intake-validator-lims.html",
    "weck-coc-preaccession-validator-lims.html",
    "westpak-scope-capacity-routing-lims.html",
    "organabio-multisite-donor-coa.html",
    "subzero-proof.html",
    "pixel-unify.html",
    "proof-spiral-succinct-argument.html",
    "muhlnickel-free-sample.html",
    "titan-hands-free-sample.html",
    "proof-to-proposal.html",
    "the-world.html",
    "fleet-work-order.html",
    "image-drop.html",
    "muhl-train.html",
    "post-http.html",
)
REQUIRED_RAIL_FIELDS = (
    "id",
    "provider",
    "account_provenance",
    "capability_state",
    "required_owner_actions",
    "evidence",
    "supported_skus",
    "currencies",
    "settlement_destination",
    "public_presentation",
)


class RegistryError(ValueError):
    pass


def _read(root: str, rel: str) -> str:
    path = os.path.join(root, rel)
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _load(root: str, rel: str) -> Any:
    return json.loads(_read(root, rel))


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not (
        value.endswith("Z") or re.search(r"[+-]\d\d:\d\d$", value)
    ):
        raise RegistryError("%s must be an offset-aware ISO-8601 timestamp" % field)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    # ISO-8601 allows extra fractional digits; datetime.fromisoformat is
    # microsecond-capped, so keep the first six digits instead of dropping
    # a real observed timestamp.
    normalized = re.sub(r"(\.\d{6})\d+(?=[+-])", r"\1", normalized)
    try:
        parsed = datetime.fromisoformat(normalized)

    except ValueError as exc:
        raise RegistryError("%s must be a real timestamp" % field) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RegistryError("%s must include an offset" % field)
    return parsed.astimezone(timezone.utc)


def forbidden_hits(text: str) -> list[str]:
    hits = []
    for pattern in FORBIDDEN:
        if re.search(pattern, text or "", flags=re.I):
            hits.append(pattern)
    return hits


def owner_action_url_ok(url: str) -> bool:
    if not isinstance(url, str) or not url.startswith("https://"):
        return False
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return False
    return parsed.hostname in OWNER_ACTION_HOSTS


def public_storefront_eligible(rail: dict[str, Any]) -> bool:
    if rail.get("capability_state") != "CHARGEABLE":
        return False
    if rail.get("public_presentation") != "EXPOSE":
        return False
    if rail.get("charges_enabled") is not True:
        return False
    if rail.get("payouts_enabled") is not True:
        return False
    evidence = rail.get("evidence") if isinstance(rail.get("evidence"), dict) else {}
    if not evidence.get("reference") or not evidence.get("observed_at"):
        return False
    _timestamp(evidence.get("observed_at"), "evidence.observed_at")
    return True


def owner_usable(rail: dict[str, Any]) -> bool:
    return rail.get("capability_state") in {
        "CHARGEABLE",
        "CHARGEABLE_ACCOUNT_OWNER_DASHBOARD",
    } and rail.get("charges_enabled") is True


def catalog_checkouts(catalog: dict[str, Any]) -> dict[str, str]:
    """Return active Stripe checkouts, failing closed on duplicate SKU ids."""
    counts: dict[str, int] = {}
    for listing in catalog.get("listings") or []:
        if isinstance(listing, dict) and isinstance(listing.get("id"), str):
            sku = listing["id"]
            counts[sku] = counts.get(sku, 0) + 1
    out: dict[str, str] = {}
    for listing in catalog.get("listings") or []:
        if not isinstance(listing, dict) or not isinstance(listing.get("id"), str):
            continue
        sku = listing["id"]
        if counts.get(sku) != 1:
            continue
        checkout = listing.get("checkout") if isinstance(listing.get("checkout"), dict) else {}
        url = checkout.get("url")
        if (
            checkout.get("status") == "ACTIVE_CHARGEABLE"
            and checkout.get("provider") == "stripe"
            and checkout.get("link_active") is True
            and checkout.get("account_charges_enabled") is True
            and checkout.get("account_payouts_enabled") is True
            and isinstance(url, str)
            and STRIPE_URL_RE.fullmatch(url)
        ):
            out[sku] = url
    return out


def catalog_checkout_evidence(catalog: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Return evidence from the same unique listing admitted as active."""
    active = catalog_checkouts(catalog)
    out: dict[str, dict[str, str]] = {}
    for listing in catalog.get("listings") or []:
        if not isinstance(listing, dict) or not isinstance(listing.get("id"), str):
            continue
        sku = listing["id"]
        checkout = listing.get("checkout") if isinstance(listing.get("checkout"), dict) else {}
        url = checkout.get("url")
        if active.get(sku) != url:
            continue
        evidence = checkout.get("capability_evidence") if isinstance(checkout.get("capability_evidence"), dict) else {}
        reference = evidence.get("reference")
        observed_at = evidence.get("observed_at")
        if not isinstance(reference, str) or not reference.strip():
            continue
        if not isinstance(observed_at, str) or not observed_at:
            continue
        try:
            _timestamp(observed_at, "%s.checkout.capability_evidence.observed_at" % sku)
        except RegistryError:
            continue
        out[sku] = {
            "url": str(url),
            "reference": reference,
            "observed_at": observed_at,
        }
    return out


def canonical_payment_authority() -> dict[str, dict[str, str]]:
    """Caller-independent Stripe authority from canonical registry + catalog."""
    try:
        registry = _load(ROOT_DEFAULT, REGISTRY)
        catalog = _load(ROOT_DEFAULT, CATALOG)
        if registry.get("kind") != "PAYMENT_CAPABILITY_REGISTRY":
            return {}
        if registry.get("schema_version") != "commons-payment-capability/v1":
            return {}
        _timestamp(registry.get("observed_at"), "canonical.observed_at")
    except (OSError, ValueError, json.JSONDecodeError, RegistryError):
        return {}
    checkouts = catalog_checkouts(catalog)
    checkout_evidence = catalog_checkout_evidence(catalog)
    out: dict[str, dict[str, str]] = {}
    duplicate: set[str] = set()
    for rail in registry.get("rails") or []:
        if not isinstance(rail, dict):
            continue
        if rail.get("provider") != "stripe" or not public_storefront_eligible(rail):
            continue
        rail_id = str(rail.get("id") or "")
        supported = {
            sku for sku in rail.get("supported_skus") or [] if isinstance(sku, str)
        }
        rail_evidence = rail.get("evidence") if isinstance(rail.get("evidence"), dict) else {}
        for link in rail.get("canonical_links") or []:
            if not isinstance(link, dict) or not isinstance(link.get("sku"), str):
                continue
            sku = link["sku"]
            if sku in out:
                duplicate.add(sku)
                continue
            url = str(link.get("url") or "")
            exposure = str(link.get("exposure") or "")
            evidence = link.get("evidence") if isinstance(link.get("evidence"), dict) else rail_evidence
            reference = evidence.get("reference")
            observed_at = evidence.get("observed_at")
            catalog_evidence = checkout_evidence.get(sku) or {}
            if not (
                link.get("link_active") is True
                and link.get("livemode") is True
                and sku in supported
                and checkouts.get(sku) == url
                and bool(STRIPE_URL_RE.fullmatch(url))
                and isinstance(reference, str)
                and bool(reference.strip())
                and isinstance(observed_at, str)
                and catalog_evidence.get("url") == url
                and catalog_evidence.get("reference") == reference
                and catalog_evidence.get("observed_at") == observed_at
            ):
                continue
            try:
                _timestamp(observed_at, "%s.canonical.evidence.observed_at" % sku)
            except RegistryError:
                continue
            out[sku] = {
                "rail_id": rail_id,
                "url": url,
                "reference": reference,
                "observed_at": observed_at,
                "exposure": exposure,
            }
    for sku in duplicate:
        out.pop(sku, None)
    return out


def project_rail(
    rail: dict[str, Any],
    checkouts: dict[str, str],
    checkout_evidence: dict[str, dict[str, str]],
    authority: dict[str, dict[str, str]],
) -> dict[str, Any]:
    eligible = public_storefront_eligible(rail)
    links = rail.get("canonical_links") if isinstance(rail.get("canonical_links"), list) else []
    supported_skus = {
        sku for sku in rail.get("supported_skus") or [] if isinstance(sku, str)
    }
    public_links = []
    rail_id = str(rail.get("id") or "")
    if eligible and rail.get("provider") == "stripe":
        for link in links:
            if not isinstance(link, dict):
                continue
            url = str(link.get("url") or "")
            sku = str(link.get("sku") or "")
            exposure = str(link.get("exposure") or "")
            evidence = link.get("evidence") if isinstance(link.get("evidence"), dict) else rail.get("evidence") or {}
            evidence_ready = bool(evidence.get("reference") and evidence.get("observed_at"))
            if evidence_ready:
                try:
                    _timestamp(evidence["observed_at"], "%s.evidence.observed_at" % sku)
                except RegistryError:
                    evidence_ready = False
            catalog_evidence = checkout_evidence.get(sku) or {}
            evidence_matches = (
                catalog_evidence.get("url") == url
                and catalog_evidence.get("reference") == evidence.get("reference")
                and catalog_evidence.get("observed_at") == evidence.get("observed_at")
            )
            canonical = authority.get(sku) or {}
            authority_matches = (
                canonical.get("rail_id") == rail_id
                and canonical.get("url") == url
                and canonical.get("reference") == evidence.get("reference")
                and canonical.get("observed_at") == evidence.get("observed_at")
                and canonical.get("exposure") == exposure
            )
            if (
                link.get("link_active") is True
                and link.get("livemode") is True
                and sku in supported_skus
                and checkouts.get(sku) == url
                and STRIPE_URL_RE.fullmatch(url)
                and evidence_ready
                and evidence_matches
                and authority_matches
            ):
                public_links.append(
                    {
                        "sku": sku,
                        "url": url,
                        "exposure": link.get("exposure"),
                        "evidence_reference": evidence.get("reference"),
                        "evidence_observed_at": evidence.get("observed_at"),
                    }
                )
    actions = []
    for action in rail.get("required_owner_actions") or []:
        if isinstance(action, dict) and action.get("kind") == "EXTERNAL_OWNER_ACTION":
            actions.append(
                {
                    "id": action.get("id"),
                    "label": action.get("label"),
                    "url": action.get("url") if owner_action_url_ok(str(action.get("url") or "")) else "",
                    "blocking": bool(action.get("blocking")),
                }
            )
    dest = rail.get("settlement_destination") if isinstance(rail.get("settlement_destination"), dict) else {}
    return {
        "id": rail_id,
        "provider": str(rail.get("provider") or ""),
        "capability_state": str(rail.get("capability_state") or ""),
        "public_presentation": "EXPOSE" if eligible and public_links else "INERT",
        "chargeable": eligible,
        "owner_usable": owner_usable(rail),
        "public_links": public_links if eligible else [],
        "supported_skus": list(rail.get("supported_skus") or []),
        "currencies": list(rail.get("currencies") or []),
        "settlement_status": str(dest.get("status") or "NONE"),
        "settlement_kind": str(dest.get("kind") or "unmeasured"),
        "owner_actions": actions,
        "evidence_reference": str((rail.get("evidence") or {}).get("reference") or ""),
        "evidence_observed_at": str((rail.get("evidence") or {}).get("observed_at") or ""),
    }


def project(registry: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    if registry.get("kind") != "PAYMENT_CAPABILITY_REGISTRY":
        raise RegistryError("registry kind is invalid")
    if registry.get("schema_version") != "commons-payment-capability/v1":
        raise RegistryError("registry schema_version is invalid")
    _timestamp(registry.get("observed_at"), "observed_at")
    rails = registry.get("rails") if isinstance(registry.get("rails"), list) else []
    checkouts = catalog_checkouts(catalog)
    checkout_evidence = catalog_checkout_evidence(catalog)
    authority = canonical_payment_authority()
    projected = [
        project_rail(rail, checkouts, checkout_evidence, authority)
        for rail in rails
        if isinstance(rail, dict)
    ]
    public = [row for row in projected if row["public_presentation"] == "EXPOSE"]
    usable = [row for row in projected if row["owner_usable"]]
    active = public[0]["id"] if public else ""
    cash = registry.get("cash") if isinstance(registry.get("cash"), dict) else {}
    intake = registry.get("intake_fallback") if isinstance(registry.get("intake_fallback"), dict) else {}
    blocking = []
    for row in projected:
        for action in row["owner_actions"]:
            if action.get("blocking") and action.get("url"):
                blocking.append(action)
    return {
        "active_storefront_rail_id": active,
        "public_rails": public,
        "owner_usable_rails": [row["id"] for row in usable],
        "inert_rails": [row["id"] for row in projected if row["public_presentation"] == "INERT"],
        "has_lawfully_chargeable_path": bool(usable),
        "has_public_storefront": bool(public),
        "failover_owner_actions": blocking,
        "collected_cash_usd": None,
        "settlement_status": "NOT_VERIFIED_IN_THIS_RUN",
        "settlement_scope": "offline_registry_only",
        "recorded_cash_usd": cash.get("collected_usd"),
        "recorded_cash_observed_at": registry.get("observed_at"),
        "authorization": str(cash.get("authorization") or ""),
        "bank_available": str(cash.get("bank_available") or ""),
        "intake_url": str(intake.get("url") or ""),
        "rails": projected,
    }


def compose_errors(root: str, registry: dict[str, Any], projected: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    snapshot = _load(root, SNAPSHOT)
    catalog = _load(root, CATALOG)
    funnel = _load(root, FUNNEL)
    bindings = _load(root, BINDINGS)
    pack = _load(root, PACK)
    provider = snapshot.get("provider") if isinstance(snapshot.get("provider"), dict) else {}
    money = snapshot.get("money") if isinstance(snapshot.get("money"), dict) else {}
    stripe = next((r for r in registry.get("rails") or [] if r.get("id") == "stripe-livemode-acct_1U6HI9ATH4EDE7XD"), {})
    if stripe.get("charges_enabled") is True and provider.get("charges_enabled") is not True:
        errors.append("registry must not claim Stripe charges_enabled without the checkout snapshot")
    if stripe.get("payouts_enabled") is True and provider.get("payouts_enabled") is not True:
        errors.append("registry must not claim Stripe payouts_enabled without the checkout snapshot")
    pack_text = json.dumps(pack)
    if "BANK_AVAILABLE" not in pack_text and "NOT_LANDED" not in pack_text:
        errors.append("payment_ready pack must keep cash states")
    cash_fields = json.dumps(funnel)
    if '"cash_usd"' not in cash_fields and '"collected_cash_usd"' not in json.dumps(catalog.get("funnel_truth") or {}):
        errors.append("reply-to-revenue/catalog cash truth missing")
    if not isinstance(bindings.get("skus"), dict) or "sku-tip-20260826" not in (bindings.get("skus") or {}):
        errors.append("scope-to-delivery bindings must still name canonical SKUs")
    stripe_links = {
        link["sku"]: link["url"]
        for link in stripe.get("canonical_links") or []
        if isinstance(link, dict) and isinstance(link.get("sku"), str)
    }
    stripe_supported = {
        sku for sku in stripe.get("supported_skus") or [] if isinstance(sku, str)
    }
    by_id = {row.get("id"): row for row in catalog.get("listings") or [] if isinstance(row, dict)}
    for sku in catalog_checkouts(catalog):
        listing = by_id[sku]
        checkout = listing.get("checkout") if isinstance(listing.get("checkout"), dict) else {}
        if checkout.get("url") != stripe_links.get(sku):
            errors.append("%s catalog checkout URL must match registry canonical link" % sku)
        if sku not in stripe_supported:
            errors.append("%s must be named in the Stripe rail supported_skus" % sku)
    return errors


def _https_stripe_identity(host: str, path: str) -> str:
    return "https://" + host + "/" + path


def live_stripe_checkout_urls(html: str) -> set[str]:
    """Canonical Stripe Payment Link identities found in HTML (buy or donate hosts)."""
    return {
        _https_stripe_identity("buy.stripe.com", path)
        for path in BUY_HOST_PATH_RE.findall(html)
    } | {
        _https_stripe_identity("donate.stripe.com", path)
        for path in DONATE_HOST_PATH_RE.findall(html)
    }


def https_buy_checkout_urls(html: str) -> set[str]:
    """Exact https buy.stripe.com path hrefs. Does not reconstruct http hrefs."""
    return set(BUY_HTTPS_URL_RE.findall(html))


def http_buy_duplicate(html: str) -> bool:
    """True when an http buy.stripe.com href is present beside live buys."""
    return HTTP_BUY_URL_RE.search(html or "") is not None


def html_stripe_url_errors(name: str, text: str) -> list[str]:
    """tips/pay/commerce convert shelves reuse existing Stripe URLs; payment-capability stays Type live buys."""
    if name == "tips.html":
        found = live_stripe_checkout_urls(text)
        if found != TIPS_CONVERT_SHELF_LIVE_CHECKOUTS | {WHITEBOX_HOUR_CHECKOUT}:
            return [
                "%s convert shelf must reuse exactly the existing tip-shelf Stripe URLs"
                % name
            ]
        return []
    if name == "pay.html":
        found = live_stripe_checkout_urls(text)
        if found != PAY_CONVERT_SHELF_LIVE_CHECKOUTS:
            return [
                "%s convert shelf must reuse exactly the existing pay Stripe URLs"
                % name
            ]
        return []
    if name == "commerce.html":
        found = live_stripe_checkout_urls(text)
        if found != COMMERCE_CONVERT_SHELF_LIVE_CHECKOUTS:
            return [
                "%s convert shelf must reuse exactly the existing commerce Stripe URLs"
                % name
            ]
        return []
    allowed = CONVERT_SHELF_LIVE_BUYS.get(name)
    if allowed is not None:
        found = https_buy_checkout_urls(text)
        if found != allowed:
            return [
                "%s convert shelf must reuse exactly the existing live buy.stripe.com URLs"
                % name
            ]
        if http_buy_duplicate(text):
            return [
                "%s convert shelf must not duplicate live buys over http://" % name
            ]
        if "donate.stripe.com" in text.lower():
            return ["%s must not invent donate.stripe.com URLs" % name]
        return []
    if STRIPE_HTML_URL_RE.search(text):
        return ["%s must keep Stripe URLs out of static HTML" % name]
    return []


def html_surface_errors(root: str) -> list[str]:
    errors: list[str] = []
    paypal_me = re.compile(r"paypal\.me/", re.I)
    for name in PUBLIC_HTML:
        text = _read(root, name)
        errors.extend(html_stripe_url_errors(name, text))
        if paypal_me.search(text):
            errors.append("%s must not invent a PayPal.me" % name)
        if "mailto:tokenjunkielabs@gmail.com" not in text and name in (
            "pay.html",
            "tips.html",
            "commerce.html",
            "payment-capability.html",
            "owner-now-revenue.html",
        ):
            errors.append("%s must keep the provider-neutral contact fallback" % name)
    text = _read(root, "payment-capability.html")
    if "js-rail-list" not in text:
        errors.append("payment-capability.html must include js-rail-list")
    if "js-owner-actions" not in text:
        errors.append("payment-capability.html must include js-owner-actions")
    if "payment-capability.js" not in text:
        errors.append("payment-capability.html must load payment-capability.js")
    js = _read(root, "payment-capability.js")
    if "capability_state" not in js:
        errors.append("payment-capability.js must branch on capability_state")
    if "EXTERNAL_OWNER_ACTION" not in js:
        errors.append("payment-capability.js must render owner one-click actions")
    pay_js = _read(root, "pay.js")
    if "payment_capability/registry.json" not in pay_js:
        errors.append("pay.js must load the provider-neutral registry for failover")
    door = _read(root, "door.js")
    if '["payment-capability.html", "payment rails"]' not in door:
        errors.append("door.js must surface payment-capability.html")
    index = _read(root, "index.html")
    if 'href="./payment-capability.html">payment rails</a>' not in index:
        errors.append("index hub must surface payment-capability.html")
    boards = _read(root, "boards.html")
    hub = _read(root, "hub_pages.py")
    needle = 'href="./payment-capability.html">payment rails</a>'
    if needle not in boards:
        errors.append("boards.html must catalog payment-capability.html")
    if needle not in hub:
        errors.append("hub_pages.py must keep payment-capability.html")
    listing = _read(root, os.path.join("host", "listing_registry.py"))
    if "revenue/payment_capability/registry.json" not in listing:
        errors.append("listing_registry must compose with payment_capability")
    return errors


def storefront_policy_errors(projected: dict[str, Any]) -> list[str]:
    """Public storefront follows the registry. Dead Stripe stays honest."""
    errors: list[str] = []
    stripe_row = next(
        (row for row in projected["rails"] if row["id"] == "stripe-livemode-acct_1U6HI9ATH4EDE7XD"),
        {},
    )
    if stripe_row.get("chargeable"):
        if not projected["has_lawfully_chargeable_path"]:
            errors.append("chargeable Stripe rail must remain owner-usable")
        if projected["active_storefront_rail_id"] != "stripe-livemode-acct_1U6HI9ATH4EDE7XD":
            errors.append("active public storefront must be the proven Stripe rail")
    else:
        if projected["has_public_storefront"] or projected["active_storefront_rail_id"]:
            errors.append("inert Stripe must hide the public storefront")
        invented = [
            row["id"]
            for row in projected["rails"]
            if row["id"] != "stripe-livemode-acct_1U6HI9ATH4EDE7XD"
            and row.get("public_presentation") == "EXPOSE"
        ]
        if invented:
            errors.append("unproven rails must stay inert: %s" % ",".join(invented))
    if "paypal-wallet-unmeasured" not in projected["inert_rails"]:
        errors.append("PayPal must stay inert without owner KYC evidence")
    if not projected["failover_owner_actions"]:
        errors.append("inert rails must keep one-click owner actions")
    return errors


def measure_root(root: str) -> dict[str, Any]:
    registry = _load(root, REGISTRY)
    catalog = _load(root, CATALOG)
    blob = "\n".join(
        [
            _read(root, REGISTRY),
            _read(root, os.path.join("ground", "PAYMENT_CAPABILITY.md")),
            _read(root, os.path.join("host", "payment_capability.py")),
            _read(root, "payment-capability.html"),
            _read(root, "payment-capability.js"),
        ]
    )
    errors: list[str] = []
    hits = forbidden_hits(blob)
    if hits:
        errors.append("forbidden financial field pattern")
    rails = registry.get("rails") if isinstance(registry.get("rails"), list) else []
    if len(rails) < 3:
        errors.append("registry must name Stripe plus at least two failover rails")
    seen = set()
    for rail in rails:
        if not isinstance(rail, dict):
            errors.append("rail must be an object")
            continue
        for field in REQUIRED_RAIL_FIELDS:
            if field not in rail:
                errors.append("rail %s missing %s" % (rail.get("id"), field))
        rid = rail.get("id")
        if rid in seen:
            errors.append("duplicate rail id %s" % rid)
        seen.add(rid)
        evidence = rail.get("evidence") if isinstance(rail.get("evidence"), dict) else {}
        if not evidence.get("reference") or not evidence.get("observed_at"):
            errors.append("rail %s missing evidence timestamp/reference" % rid)
        dest = rail.get("settlement_destination") if isinstance(rail.get("settlement_destination"), dict) else {}
        if "status" not in dest or "kind" not in dest:
            errors.append("rail %s missing settlement destination evidence" % rid)
        for action in rail.get("required_owner_actions") or []:
            if not isinstance(action, dict):
                continue
            url = str(action.get("url") or "")
            if action.get("kind") == "EXTERNAL_OWNER_ACTION" and not owner_action_url_ok(url):
                errors.append("rail %s owner action URL is not an official provider UI" % rid)
        if rail.get("public_presentation") == "EXPOSE" and rail.get("capability_state") != "CHARGEABLE":
            errors.append("rail %s cannot EXPOSE unless CHARGEABLE" % rid)
        if rail.get("capability_state") != "CHARGEABLE" and rail.get("canonical_links"):
            # inert rails may omit links; if present they still must not be public
            pass
        if rail.get("id") != "stripe-livemode-acct_1U6HI9ATH4EDE7XD" and rail.get("public_presentation") == "EXPOSE":
            errors.append("non-Stripe rail must stay inert until a later evidence pass")
    projected = project(registry, catalog)
    if projected["intake_url"] != "mailto:tokenjunkielabs@gmail.com":
        errors.append("intake fallback must stay the public email")
    errors.extend(storefront_policy_errors(projected))
    errors.extend(compose_errors(root, registry, projected))
    errors.extend(html_surface_errors(root))
    for rel in (
        os.path.join("ground", "PAYMENT_CAPABILITY.md"),
        os.path.join("ground", "CHECKOUT_CAPABILITY.md"),
        os.path.join("ground", "PAY.md"),
        os.path.join("ground", "STRIPE.md"),
    ):
        text = _read(root, rel)
        if "PAYMENT_CAPABILITY" not in text and rel.endswith("PAYMENT_CAPABILITY.md"):
            errors.append("%s missing title" % rel)
        if rel != os.path.join("ground", "PAYMENT_CAPABILITY.md") and "payment_capability" not in text and "PAYMENT_CAPABILITY" not in text:
            errors.append("%s must cite the payment-capability registry" % rel)
    state = "INTEGRATED" if not errors else "NOT_LANDED"
    return {
        "state": state,
        "errors": errors,
        "projected": projected,
        "registry": REGISTRY,
        "z": "" if not errors else "FINDER-FAILED",
    }


def _self_test() -> bool:
    dead = {
        "schema_version": "commons-payment-capability/v1",
        "kind": "PAYMENT_CAPABILITY_REGISTRY",
        "observed_at": "2026-08-28T16:43:00Z",
        "cash": {
            "collected_usd": 0,
            "authorization": "NOT_LANDED",
            "bank_available": "NOT_LANDED",
        },
        "intake_fallback": {
            "kind": "PROVIDER_NEUTRAL_INTAKE",
            "url": "mailto:tokenjunkielabs@gmail.com",
        },
        "rails": [
            {
                "id": "stripe-dead",
                "provider": "stripe",
                "capability_state": "INERT_CHARGES_DISABLED",
                "charges_enabled": False,
                "payouts_enabled": False,
                "public_presentation": "INERT",
                "canonical_links": [
                    {
                        "sku": "sku-tip-20260826",
                        "url": "https://donate.stripe.com/fZucN40Ch9fj7mxgJs43S08",
                        "link_active": True,
                        "livemode": True,
                    }
                ],
                "evidence": {
                    "reference": "fixture",
                    "observed_at": "2026-08-28T16:43:00Z",
                },
                "required_owner_actions": [],
                "supported_skus": [],
                "currencies": ["usd"],
                "settlement_destination": {"kind": "unmeasured", "status": "NONE"},
            },
            {
                "id": "paypal-dead",
                "provider": "paypal",
                "capability_state": "INERT_NEEDS_OWNER_KYC",
                "charges_enabled": False,
                "public_presentation": "INERT",
                "evidence": {
                    "reference": "fixture",
                    "observed_at": "2026-08-28T16:43:00Z",
                },
                "required_owner_actions": [
                    {
                        "id": "paypal-business-signup",
                        "blocking": True,
                        "kind": "EXTERNAL_OWNER_ACTION",
                        "label": "Open PayPal",
                        "url": "https://www.paypal.com/bizsignup",
                    }
                ],
                "supported_skus": [],
                "currencies": ["usd"],
                "settlement_destination": {"kind": "unmeasured", "status": "NONE"},
            },
        ],
    }
    fixture_catalog = {
        "listings": [
            {
                "id": "sku-tip-20260826",
                "checkout": {
                    "status": "ACTIVE_CHARGEABLE",
                    "provider": "stripe",
                    "url": "https://donate.stripe.com/fZucN40Ch9fj7mxgJs43S08",
                    "link_active": True,
                    "account_charges_enabled": True,
                    "account_payouts_enabled": True,
                },
            }
        ]
    }
    projected = project(dead, fixture_catalog)
    if projected["has_public_storefront"] or projected["public_rails"]:
        return False
    if projected["has_lawfully_chargeable_path"]:
        return False
    if not projected["failover_owner_actions"]:
        return False
    live = {
        "schema_version": "commons-payment-capability/v1",
        "kind": "PAYMENT_CAPABILITY_REGISTRY",
        "observed_at": "2026-08-28T16:43:00Z",
        "cash": {"collected_usd": 0, "authorization": "NOT_LANDED", "bank_available": "NOT_LANDED"},
        "intake_fallback": {"url": "mailto:tokenjunkielabs@gmail.com"},
        "rails": [
            dead["rails"][0],
            {
                "id": "paypal-live-fixture",
                "provider": "paypal",
                "capability_state": "CHARGEABLE",
                "charges_enabled": True,
                "payouts_enabled": True,
                "public_presentation": "EXPOSE",
                "canonical_links": [],
                "evidence": {
                    "reference": "fixture-paypal",
                    "observed_at": "2026-08-28T16:43:00Z",
                },
                "required_owner_actions": [],
                "supported_skus": ["sku-tip-20260826"],
                "currencies": ["usd"],
                "settlement_destination": {"kind": "paypal_balance", "status": "verified"},
            },
        ],
    }
    # PayPal fixture is CHARGEABLE but has no public checkout URL of a known kind,
    # so public_presentation stays INERT. That is honest: chargeable is not a URL.
    alt = project(live, fixture_catalog)
    if alt["has_public_storefront"]:
        return False
    if "paypal-live-fixture" not in alt["owner_usable_rails"]:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project payment-capability registry")
    parser.add_argument("--root", default=ROOT_DEFAULT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_root(args.root)
    json.dump(row, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("state") == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
