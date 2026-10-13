#!/usr/bin/env python3
"""Compile a large, public-safe Commons marketing and sales research universe.

The tool uses GitHub's public repository search without credentials, clusters
repositories by their public owner, and emits named research entities. It
does not call an account qualified merely because a repository exists, does not
verify a business route, and never drafts or sends a message. The canonical CRM
remains the existing Airtable Revenue Pipeline; this output is research input.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUERIES = ROOT / "revenue" / "marketing_sales" / "discovery_queries.json"
DEFAULT_CONTRACT = ROOT / "revenue" / "marketing_sales" / "operating_contract.json"
DEFAULT_UNIVERSE = ROOT / "revenue" / "marketing_sales" / "account_universe.json"
DEFAULT_PIPELINE = ROOT / "revenue" / "marketing_sales" / "pipeline.json"
QUALIFIED_SEED = ROOT / "revenue" / "production_survival" / "qualified_prospects_20260830.json"
OUTREACH_LOG = ROOT / "revenue" / "production_survival" / "outreach_log_20260830.json"
REPLY_FUNNEL = ROOT / "revenue" / "reply_to_revenue" / "funnel.json"

DISCOVERY_VERSION = "commons-marketing-sales-discovery/v1"
UNIVERSE_VERSION = "commons-marketing-sales-account-universe/v1"
PIPELINE_VERSION = "commons-marketing-sales-pipeline/v1"
CONTRACT_VERSION = "commons-marketing-sales-operating-contract/v1"
IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,120}$")
EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
GITHUB_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
SECRET_VALUE_RE = re.compile(
    r"(?:sk_live_[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"(?:xox[baprs]|xapp)-[A-Za-z0-9-]{16,}|AKIA[A-Z0-9]{16}|"
    r"Bearer\s+[A-Za-z0-9._~-]{20,})",
    re.IGNORECASE,
)


class MarketingSalesError(ValueError):
    """A source or public projection is incomplete or contradictory."""


def canonical_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MarketingSalesError(f"cannot read JSON {path}: {error}") from error


def read_object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise MarketingSalesError(f"{path} must contain one JSON object")
    return value


def parse_time(value: str) -> dt.datetime:
    if not isinstance(value, str):
        raise MarketingSalesError("date-time must be text")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError as error:
        raise MarketingSalesError(f"invalid date-time: {value}") from error
    if parsed.tzinfo is None:
        raise MarketingSalesError("date-time must include timezone")
    return parsed.astimezone(dt.timezone.utc)


def exact_keys(value: dict[str, Any], expected: set[str], where: str) -> None:
    if not isinstance(value, dict):
        raise MarketingSalesError(f"{where} must be an object")
    actual = set(value)
    if actual != expected:
        raise MarketingSalesError(
            f"{where} fields differ: missing={sorted(expected - actual)} "
            f"extra={sorted(actual - expected)}"
        )


def validate_queries(value: dict[str, Any]) -> dict[str, Any]:
    exact_keys(value, {"schema_version", "kind", "configured_at", "source", "queries"}, "queries")
    if value["schema_version"] != DISCOVERY_VERSION:
        raise MarketingSalesError("unsupported discovery version")
    if value["kind"] != "MARKETING_SALES_DISCOVERY_QUERIES":
        raise MarketingSalesError("unsupported discovery kind")
    parse_time(value["configured_at"])
    if value["source"] != "GitHub public repository search":
        raise MarketingSalesError("discovery source must be GitHub public repository search")
    queries = value["queries"]
    if not isinstance(queries, list) or not queries:
        raise MarketingSalesError("queries must be a non-empty array")
    seen: set[str] = set()
    for index, query in enumerate(queries):
        where = f"queries[{index}]"
        if not isinstance(query, dict):
            raise MarketingSalesError(f"{where} must be an object")
        exact_keys(query, {"id", "query", "pages"}, where)
        query_id = query["id"]
        if not isinstance(query_id, str) or not IDENTIFIER_RE.fullmatch(query_id):
            raise MarketingSalesError(f"{where}.id is invalid")
        if query_id in seen:
            raise MarketingSalesError(f"duplicate query id: {query_id}")
        seen.add(query_id)
        if not isinstance(query["query"], str) or not query["query"].strip():
            raise MarketingSalesError(f"{where}.query must be non-empty")
        if type(query["pages"]) is not int or not 1 <= query["pages"] <= 10:
            raise MarketingSalesError(f"{where}.pages must be 1..10")
    return value


def validate_contract(value: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version", "kind", "offer_id", "price_usd", "goal", "universe",
        "qualification", "segments", "truth_boundaries", "stop_rules",
    }
    exact_keys(value, required, "operating contract")
    if value["schema_version"] != CONTRACT_VERSION:
        raise MarketingSalesError("unsupported operating contract version")
    if value["kind"] != "MARKETING_SALES_OPERATING_CONTRACT":
        raise MarketingSalesError("unsupported operating contract kind")
    if type(value["price_usd"]) is not int or value["price_usd"] <= 0:
        raise MarketingSalesError("price_usd must be a positive integer")
    goal = value["goal"]
    if not isinstance(goal, dict):
        raise MarketingSalesError("goal must be an object")
    exact_keys(goal, {"weekly_captures", "weekly_gross_captured_usd", "minimum_delivery_capacity"}, "goal")
    for key in goal:
        if type(goal[key]) is not int or goal[key] <= 0:
            raise MarketingSalesError(f"goal.{key} must be a positive integer")
    if goal["weekly_gross_captured_usd"] != goal["weekly_captures"] * value["price_usd"]:
        raise MarketingSalesError("goal gross must equal captures times price")
    universe = value["universe"]
    if not isinstance(universe, dict):
        raise MarketingSalesError("universe contract must be an object")
    universe_keys = {
        "minimum_research_entities", "minimum_github_organization_entities",
        "weekly_new_qualified_accounts", "weekly_verified_business_routes",
        "weekly_actual_sends", "weekly_positive_human_replies",
        "weekly_confirmed_bookings", "weekly_purchase_authorizations",
        "weekly_captured_payments", "weekly_completed_deliveries",
        "rolling_research_queue",
    }
    exact_keys(universe, universe_keys, "universe contract")
    for key in (
        "minimum_research_entities", "minimum_github_organization_entities",
        "weekly_new_qualified_accounts",
        "weekly_verified_business_routes", "weekly_actual_sends",
        "weekly_positive_human_replies", "weekly_confirmed_bookings",
        "weekly_purchase_authorizations", "weekly_captured_payments",
        "weekly_completed_deliveries", "rolling_research_queue",
    ):
        if type(universe.get(key)) is not int or universe[key] <= 0:
            raise MarketingSalesError(f"universe.{key} must be a positive integer")
    funnel = [
        universe["weekly_new_qualified_accounts"],
        universe["weekly_verified_business_routes"],
        universe["weekly_actual_sends"],
        universe["weekly_positive_human_replies"],
        universe["weekly_confirmed_bookings"],
        universe["weekly_purchase_authorizations"],
        universe["weekly_captured_payments"],
    ]
    if any(left < right for left, right in zip(funnel, funnel[1:])):
        raise MarketingSalesError("weekly funnel counts must be nonincreasing")
    if universe["weekly_captured_payments"] != goal["weekly_captures"]:
        raise MarketingSalesError("weekly capture target must match goal")
    if universe["weekly_completed_deliveries"] > universe["weekly_captured_payments"]:
        raise MarketingSalesError("weekly deliveries cannot exceed captures")
    if goal["minimum_delivery_capacity"] < universe["weekly_completed_deliveries"]:
        raise MarketingSalesError("delivery capacity must cover weekly deliveries")
    qualification = value["qualification"]
    if not isinstance(qualification, dict):
        raise MarketingSalesError("qualification must be an object")
    exact_keys(qualification, {"account_unit", "minimum_score", "required", "score"}, "qualification")
    if qualification["account_unit"] != "verified organization, never an issue-author row":
        raise MarketingSalesError("qualification account unit must remain verified organization")
    if qualification["minimum_score"] != 7:
        raise MarketingSalesError("qualification minimum score must remain 7")
    required = qualification["required"]
    if not isinstance(required, list) or len(required) != 7 or any(not isinstance(item, str) or not item for item in required):
        raise MarketingSalesError("qualification.required must contain seven statements")
    if len(set(required)) != len(required):
        raise MarketingSalesError("qualification.required must be unique")
    score = qualification["score"]
    if not isinstance(score, dict):
        raise MarketingSalesError("qualification.score must be an object")
    exact_keys(
        score,
        {
            "current_production_incident", "business_impact_or_manual_mitigation",
            "relevant_owner_and_public_route", "public_or_synthetic_binary_proof",
            "current_budget_signal", "under_90_days_or_confirmed_active",
        },
        "qualification.score",
    )
    if any(type(points) is not int or points <= 0 for points in score.values()) or sum(score.values()) != 10:
        raise MarketingSalesError("qualification score weights must be positive integers totaling 10")
    segments = value["segments"]
    if not isinstance(segments, list) or len(segments) != 8:
        raise MarketingSalesError("segments must contain eight entries")
    if any(not isinstance(item, str) or not IDENTIFIER_RE.fullmatch(item) for item in segments):
        raise MarketingSalesError("segments contain an invalid identifier")
    if len(set(segments)) != len(segments):
        raise MarketingSalesError("segments must be unique")
    boundaries = value["truth_boundaries"]
    if not isinstance(boundaries, dict):
        raise MarketingSalesError("truth_boundaries must be an object")
    boundary_booleans = {
        "draft_is_send", "click_is_booking", "auto_reply_is_positive_reply",
        "authorization_is_capture", "captured_gross_is_profit",
        "public_thread_is_business_route",
    }
    exact_keys(boundaries, boundary_booleans | {"transport_actions", "cash_usd"}, "truth_boundaries")
    if any(boundaries[key] is not False for key in boundary_booleans):
        raise MarketingSalesError("truth boundary relations must remain false")
    if boundaries["transport_actions"] != 0 or boundaries["cash_usd"] != 0:
        raise MarketingSalesError("operating contract cannot claim transport or cash")
    stop_rules = value["stop_rules"]
    if not isinstance(stop_rules, dict):
        raise MarketingSalesError("stop_rules must be an object")
    exact_keys(
        stop_rules,
        {
            "hard_bounce_rate_gte", "complaint_rate_gte",
            "positive_reply_rate_lt_after_500_sends",
            "booking_to_authorization_lt_after_20_bookings",
            "authorization_to_capture_lt_after_10_authorizations",
            "on_time_delivery_lt", "refund_rate_gt", "dispute_rate_gt",
            "backlog_days_gt",
        },
        "stop_rules",
    )
    for key, threshold in stop_rules.items():
        if key == "backlog_days_gt":
            if type(threshold) is not int or threshold <= 0:
                raise MarketingSalesError("backlog_days_gt must be a positive integer")
        elif type(threshold) not in {int, float} or not 0 < threshold < 1:
            raise MarketingSalesError(f"stop_rules.{key} must be between zero and one")
    return value


def github_search_url(query: str, page: int, per_page: int) -> str:
    params = urllib.parse.urlencode(
        {"q": query, "page": page, "per_page": per_page, "sort": "updated", "order": "desc"}
    )
    return "https://api.github.com/search/repositories?" + params


def fetch_json(url: str, *, timeout: int = 30, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "commons-marketing-sales-public-discovery",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                value = json.load(response)
            if not isinstance(value, dict):
                raise MarketingSalesError("GitHub search returned a non-object")
            return value
        except urllib.error.HTTPError as error:
            if error.code not in {403, 429} or attempt == 2:
                raise MarketingSalesError(f"GitHub search failed HTTP {error.code}: {url}") from error
            reset = error.headers.get("X-RateLimit-Reset")
            wait = 65.0
            if reset and reset.isdigit():
                wait = max(1.0, min(70.0, int(reset) - time.time() + 1.0))
            sleep(wait)
        except (OSError, json.JSONDecodeError) as error:
            if attempt == 2:
                raise MarketingSalesError(f"GitHub search failed: {url}: {error}") from error
            sleep(2.0 ** attempt)
    raise AssertionError("unreachable")


def research_score(
    owner_type: str,
    repositories: list[dict[str, Any]],
    query_ids: list[str],
    *,
    observed_at: dt.datetime,
) -> int:
    score = 3 if owner_type == "Organization" else 0
    score += min(3, len(query_ids))
    highest_stars = max((item["stars"] for item in repositories), default=0)
    if highest_stars >= 100:
        score += 2
    elif highest_stars >= 10:
        score += 1
    latest = max((parse_time(item["pushed_at"]) for item in repositories), default=None)
    if latest and latest >= observed_at - dt.timedelta(days=90):
        score += 2
    return min(score, 10)


def discover(
    config: dict[str, Any],
    *,
    per_page: int = 100,
    max_entities: int | None = None,
    fetcher: Callable[[str], dict[str, Any]] = fetch_json,
    observed_at: dt.datetime | None = None,
) -> dict[str, Any]:
    config = validate_queries(config)
    if not 1 <= per_page <= 100:
        raise MarketingSalesError("per_page must be 1..100")
    if max_entities is not None and max_entities <= 0:
        raise MarketingSalesError("max_entities must be positive")
    accounts: dict[str, dict[str, Any]] = {}
    source_results = 0
    executed_queries = 0
    for query in config["queries"]:
        executed_queries += 1
        for page in range(1, query["pages"] + 1):
            payload = fetcher(github_search_url(query["query"], page, per_page))
            if payload.get("incomplete_results") is True:
                raise MarketingSalesError(f"query {query['id']} returned incomplete results")
            items = payload.get("items")
            if not isinstance(items, list):
                raise MarketingSalesError(f"query {query['id']} returned no items array")
            source_results += len(items)
            for item in items:
                if not isinstance(item, dict):
                    continue
                owner = item.get("owner")
                if not isinstance(owner, dict):
                    continue
                login = owner.get("login")
                owner_type = owner.get("type")
                full_name = item.get("full_name")
                url = item.get("html_url")
                pushed_at = item.get("pushed_at")
                stars = item.get("stargazers_count")
                if (
                    not isinstance(login, str) or not login or
                    not isinstance(owner_type, str) or owner_type not in {"Organization", "User"} or
                    not isinstance(full_name, str) or not isinstance(url, str) or
                    not url.startswith("https://github.com/") or
                    not isinstance(pushed_at, str) or type(stars) is not int or stars < 0
                ):
                    continue
                parse_time(pushed_at)
                key = login.casefold()
                account = accounts.setdefault(
                    key,
                    {
                        "account_id": f"github:{login}",
                        "account_name": login,
                        "owner_type": owner_type,
                        "qualification_state": "RESEARCH_REQUIRED",
                        "source_query_ids": set(),
                        "repositories": {},
                    },
                )
                if account["owner_type"] == "User" and owner_type == "Organization":
                    account["owner_type"] = "Organization"
                account["source_query_ids"].add(query["id"])
                repo_key = (full_name.casefold(), query["id"])
                account["repositories"][repo_key] = {
                    "full_name": full_name,
                    "url": url,
                    "pushed_at": pushed_at,
                    "stars": stars,
                    "query_id": query["id"],
                }
            if len(items) < per_page:
                break
    collected_at = (observed_at or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    observed_text = collected_at.isoformat(timespec="seconds").replace("+00:00", "Z")
    all_rows: list[dict[str, Any]] = []
    for key in sorted(accounts):
        account = accounts[key]
        repositories = sorted(
            account["repositories"].values(),
            key=lambda item: (item["full_name"].casefold(), item["query_id"]),
        )
        query_ids = sorted(account["source_query_ids"])
        all_rows.append(
            {
                "entity_id": account["account_id"],
                "entity_name": account["account_name"],
                "owner_type": account["owner_type"],
                "qualification_state": "RESEARCH_REQUIRED",
                "research_score": research_score(
                    account["owner_type"], repositories, query_ids, observed_at=collected_at
                ),
                "source_query_ids": query_ids,
                "repositories": repositories,
            }
        )
    ranked = sorted(
        all_rows,
        key=lambda item: (
            -item["research_score"],
            item["owner_type"] != "Organization",
            item["entity_name"].casefold(),
        ),
    )
    selected = ranked[:max_entities] if max_entities is not None else ranked
    rows = sorted(selected, key=lambda item: item["entity_name"].casefold())
    result = {
        "schema_version": UNIVERSE_VERSION,
        "kind": "MARKETING_SALES_RESEARCH_UNIVERSE",
        "observed_at": observed_text,
        "source": config["source"],
        "truth": {
            "source_queries": executed_queries,
            "source_results": source_results,
            "research_entities": len(rows),
            "github_organization_entities": sum(
                item["owner_type"] == "Organization" for item in rows
            ),
            "evidence_qualified_accounts": 0,
            "verified_business_routes": 0,
            "transport_actions": 0,
            "cash_usd": 0,
        },
        "entities": rows,
    }
    return validate_universe(result)


def validate_universe(value: dict[str, Any]) -> dict[str, Any]:
    exact_keys(value, {"schema_version", "kind", "observed_at", "source", "truth", "entities"}, "universe")
    if value["schema_version"] != UNIVERSE_VERSION or value["kind"] != "MARKETING_SALES_RESEARCH_UNIVERSE":
        raise MarketingSalesError("unsupported universe version or kind")
    observed_at = parse_time(value["observed_at"])
    if value["source"] != "GitHub public repository search":
        raise MarketingSalesError("universe source must be GitHub public repository search")
    truth = value["truth"]
    if not isinstance(truth, dict):
        raise MarketingSalesError("universe.truth must be an object")
    exact_keys(
        truth,
        {
            "source_queries", "source_results", "research_entities",
            "github_organization_entities", "evidence_qualified_accounts",
            "verified_business_routes", "transport_actions", "cash_usd",
        },
        "universe.truth",
    )
    for count in ("source_queries", "source_results", "research_entities", "github_organization_entities"):
        if type(truth[count]) is not int or truth[count] < 0:
            raise MarketingSalesError(f"universe.{count} must be a nonnegative integer")
    if truth["source_queries"] == 0:
        raise MarketingSalesError("universe.source_queries must be positive")
    for zero in ("evidence_qualified_accounts", "verified_business_routes", "transport_actions", "cash_usd"):
        if type(truth[zero]) is not int or truth[zero] != 0:
            raise MarketingSalesError(f"universe.{zero} must remain zero")
    entities = value["entities"]
    if not isinstance(entities, list):
        raise MarketingSalesError("universe.entities must be an array")
    canonical_names: list[str] = []
    seen: set[str] = set()
    organizations = 0
    for index, entity in enumerate(entities):
        where = f"entities[{index}]"
        if not isinstance(entity, dict):
            raise MarketingSalesError(f"{where} must be an object")
        exact_keys(
            entity,
            {
                "entity_id", "entity_name", "owner_type", "qualification_state",
                "research_score", "source_query_ids", "repositories",
            },
            where,
        )
        name = entity["entity_name"]
        if (
            not isinstance(name, str)
            or not GITHUB_NAME_RE.fullmatch(name)
            or name.endswith("-")
            or "--" in name
        ):
            raise MarketingSalesError(f"{where}.entity_name is not a GitHub owner name")
        if entity["entity_id"] != f"github:{name}":
            raise MarketingSalesError(f"{where}.entity_id must derive exactly from entity_name")
        canonical_names.append(name)
        identity = name.casefold()
        if identity in seen:
            raise MarketingSalesError(f"duplicate entity identity: {name}")
        seen.add(identity)
        if not isinstance(entity["owner_type"], str) or entity["owner_type"] not in {"Organization", "User"}:
            raise MarketingSalesError(f"{where}.owner_type is invalid")
        organizations += entity["owner_type"] == "Organization"
        if entity["qualification_state"] != "RESEARCH_REQUIRED":
            raise MarketingSalesError(f"{where} cannot self-qualify")
        if type(entity["research_score"]) is not int or not 0 <= entity["research_score"] <= 10:
            raise MarketingSalesError(f"{where}.research_score is invalid")
        if not isinstance(entity["source_query_ids"], list) or not entity["source_query_ids"]:
            raise MarketingSalesError(f"{where}.source_query_ids must be non-empty")
        if any(
            not isinstance(query_id, str) or not IDENTIFIER_RE.fullmatch(query_id)
            for query_id in entity["source_query_ids"]
        ):
            raise MarketingSalesError(f"{where}.source_query_ids contains an invalid id")
        if entity["source_query_ids"] != sorted(set(entity["source_query_ids"])):
            raise MarketingSalesError(f"{where}.source_query_ids must be sorted and unique")
        repositories = entity["repositories"]
        if not isinstance(repositories, list) or not repositories:
            raise MarketingSalesError(f"{where}.repositories must be non-empty")
        seen_repositories: set[tuple[str, str]] = set()
        for repository in repositories:
            if not isinstance(repository, dict):
                raise MarketingSalesError(f"{where}.repositories entries must be objects")
            exact_keys(repository, {"full_name", "url", "pushed_at", "stars", "query_id"}, f"{where}.repository")
            full_name = repository["full_name"]
            if not isinstance(full_name, str) or "/" not in full_name:
                raise MarketingSalesError(f"{where}.repository.full_name is invalid")
            owner, repo_name = full_name.split("/", 1)
            if (
                owner.casefold() != name.casefold()
                or not GITHUB_REPO_RE.fullmatch(repo_name)
            ):
                raise MarketingSalesError(f"{where}.repository owner must match entity")
            if repository["url"] != f"https://github.com/{full_name}":
                raise MarketingSalesError(f"{where}.repository.url must derive exactly from full_name")
            pushed_at = parse_time(repository["pushed_at"])
            if pushed_at > observed_at:
                raise MarketingSalesError(f"{where}.repository.pushed_at exceeds observed_at")
            if type(repository["stars"]) is not int or repository["stars"] < 0:
                raise MarketingSalesError(f"{where}.repository.stars must be nonnegative")
            if repository["query_id"] not in entity["source_query_ids"]:
                raise MarketingSalesError(f"{where}.repository query is absent from source_query_ids")
            repository_key = (full_name.casefold(), repository["query_id"])
            if repository_key in seen_repositories:
                raise MarketingSalesError(f"{where}.repositories contains a duplicate provenance row")
            seen_repositories.add(repository_key)
        expected_repo_order = sorted(
            repositories,
            key=lambda item: (str(item.get("full_name", "")).casefold(), str(item.get("query_id", ""))),
        )
        if repositories != expected_repo_order:
            raise MarketingSalesError(f"{where}.repositories must be canonically sorted")
        repo_query_ids = sorted({repository["query_id"] for repository in repositories})
        if repo_query_ids != entity["source_query_ids"]:
            raise MarketingSalesError(f"{where}.source_query_ids do not match repository provenance")
        expected_score = research_score(
            entity["owner_type"], repositories, entity["source_query_ids"], observed_at=observed_at
        )
        if entity["research_score"] != expected_score:
            raise MarketingSalesError(f"{where}.research_score does not match evidence")
    if canonical_names != sorted(canonical_names, key=str.casefold):
        raise MarketingSalesError("universe.entities must be canonically sorted")
    if truth["research_entities"] != len(entities):
        raise MarketingSalesError("truth.research_entities does not match entities")
    if truth["github_organization_entities"] != organizations:
        raise MarketingSalesError("truth.github_organization_entities does not match entities")
    if truth["source_results"] < len(entities):
        raise MarketingSalesError("truth.source_results cannot be below retained entities")
    public_text = canonical_text(value)
    if EMAIL_RE.search(public_text):
        raise MarketingSalesError("public universe must not contain email addresses")
    if SECRET_VALUE_RE.search(public_text):
        raise MarketingSalesError("public universe must not contain secret values")
    return value


def _seed_truth() -> dict[str, Any]:
    seed = read_json(QUALIFIED_SEED)
    if not isinstance(seed, list):
        raise MarketingSalesError("qualified seed must be an array")
    named = 0
    public_email_routes = 0
    for row in seed:
        if not isinstance(row, dict):
            raise MarketingSalesError("qualified seed entries must be objects")
        organization = row.get("organization")
        if isinstance(organization, str) and not organization.startswith("UNVERIFIED"):
            named += 1
        route = row.get("contact_route")
        if isinstance(route, dict) and str(route.get("kind", "")).casefold() == "email":
            public_email_routes += 1
    outreach = read_object(OUTREACH_LOG)
    sends = outreach.get("sends")
    if not isinstance(sends, list):
        raise MarketingSalesError("outreach log sends must be an array")
    if outreach.get("cash_received_usd") != 0:
        raise MarketingSalesError("unexpected nonzero cash in outreach log")
    funnel = read_object(REPLY_FUNNEL)
    funnel_truth = funnel.get("truth")
    if not isinstance(funnel_truth, dict):
        raise MarketingSalesError("reply funnel truth must be an object")
    return {
        "source_rows_labeled_qualified": len(seed),
        "verified_organizations_in_seed": named,
        "public_email_routes_in_seed": public_email_routes,
        "production_survival_sends": len(sends),
        "production_survival_cash_usd": outreach["cash_received_usd"],
        "canonical_historical_contacts": funnel_truth.get("distinct_contacts", 0),
        "canonical_hard_dnr_contacts": funnel_truth.get("hard_dnr_contacts", 0),
        "positive_human_replies": funnel_truth.get("human_positive", 0),
        "scope_acceptances": funnel_truth.get("scope_acceptances", 0),
        "payment_evidence": funnel_truth.get("payment_evidence", 0),
    }


def compile_pipeline(universe: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    universe = validate_universe(universe)
    contract = validate_contract(contract)
    queue_size = contract["universe"]["rolling_research_queue"]
    queue = sorted(
        universe["entities"],
        key=lambda item: (
            -item["research_score"],
            item["owner_type"] != "Organization",
            item["entity_name"].casefold(),
        ),
    )[:queue_size]
    queue_projection = [
        {
            "rank": rank,
            "entity_id": item["entity_id"],
            "entity_name": item["entity_name"],
            "owner_type": item["owner_type"],
            "research_score": item["research_score"],
            "qualification_state": "RESEARCH_REQUIRED",
            "source_query_ids": item["source_query_ids"],
        }
        for rank, item in enumerate(queue, 1)
    ]
    targets = contract["universe"]
    current_entities = universe["truth"]["research_entities"]
    current_organizations = universe["truth"]["github_organization_entities"]
    result = {
        "schema_version": PIPELINE_VERSION,
        "kind": "MARKETING_SALES_PUBLIC_PIPELINE",
        "observed_at": universe["observed_at"],
        "offer": {"offer_id": contract["offer_id"], "price_usd": contract["price_usd"]},
        "targets": dict(targets),
        "current": {
            "research_entities": current_entities,
            "github_organization_entities": current_organizations,
            "evidence_qualified_accounts": 0,
            "verified_business_routes": 0,
            "contact_ready_accounts": 0,
            "drafts": 0,
            "transport_actions": 0,
            "positive_human_replies": 0,
            "confirmed_bookings": 0,
            "purchase_authorizations": 0,
            "captured_payments": 0,
            "completed_deliveries": 0,
            "cash_usd": 0,
        },
        "gap": {
            "research_entities": max(
                0, targets["minimum_research_entities"] - current_entities
            ),
            "github_organization_entities": max(
                0,
                targets["minimum_github_organization_entities"] - current_organizations,
            ),
            "weekly_new_qualified_accounts": targets["weekly_new_qualified_accounts"],
            "weekly_verified_business_routes": targets["weekly_verified_business_routes"],
            "weekly_actual_sends": targets["weekly_actual_sends"],
            "weekly_positive_human_replies": targets["weekly_positive_human_replies"],
            "weekly_confirmed_bookings": targets["weekly_confirmed_bookings"],
            "weekly_purchase_authorizations": targets["weekly_purchase_authorizations"],
            "weekly_captured_payments": targets["weekly_captured_payments"],
            "weekly_completed_deliveries": targets["weekly_completed_deliveries"],
        },
        "seed_audit": _seed_truth(),
        "research_queue": queue_projection,
        "boundaries": {
            "canonical_crm": "JOJO Revenue Recovery CRM / Revenue Pipeline",
            "public_projection_is_not_crm": True,
            "public_threads_are_evidence_not_contact_permission": True,
            "private_routes_or_provider_ids_published": False,
            "messages_sent_by_this_tool": 0,
        },
    }
    return validate_pipeline(result, universe=universe, contract=contract)


def validate_pipeline(
    value: dict[str, Any],
    *,
    universe: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    universe = validate_universe(universe)
    contract = validate_contract(contract)
    exact_keys(value, {"schema_version", "kind", "observed_at", "offer", "targets", "current", "gap", "seed_audit", "research_queue", "boundaries"}, "pipeline")
    if value["schema_version"] != PIPELINE_VERSION or value["kind"] != "MARKETING_SALES_PUBLIC_PIPELINE":
        raise MarketingSalesError("unsupported pipeline version or kind")
    parse_time(value["observed_at"])
    if value["observed_at"] != universe["observed_at"]:
        raise MarketingSalesError("pipeline observed_at must match universe")
    expected_offer = {"offer_id": contract["offer_id"], "price_usd": contract["price_usd"]}
    if value["offer"] != expected_offer:
        raise MarketingSalesError("pipeline offer differs from contract")
    targets = contract["universe"]
    if value["targets"] != targets:
        raise MarketingSalesError("pipeline targets differ from contract")
    expected_current = {
        "research_entities": universe["truth"]["research_entities"],
        "github_organization_entities": universe["truth"]["github_organization_entities"],
        "evidence_qualified_accounts": 0,
        "verified_business_routes": 0,
        "contact_ready_accounts": 0,
        "drafts": 0,
        "transport_actions": 0,
        "positive_human_replies": 0,
        "confirmed_bookings": 0,
        "purchase_authorizations": 0,
        "captured_payments": 0,
        "completed_deliveries": 0,
        "cash_usd": 0,
    }
    if value["current"] != expected_current:
        raise MarketingSalesError("pipeline current counts differ from universe truth")
    expected_gap = {
        "research_entities": max(
            0, targets["minimum_research_entities"] - expected_current["research_entities"]
        ),
        "github_organization_entities": max(
            0,
            targets["minimum_github_organization_entities"]
            - expected_current["github_organization_entities"],
        ),
        "weekly_new_qualified_accounts": targets["weekly_new_qualified_accounts"],
        "weekly_verified_business_routes": targets["weekly_verified_business_routes"],
        "weekly_actual_sends": targets["weekly_actual_sends"],
        "weekly_positive_human_replies": targets["weekly_positive_human_replies"],
        "weekly_confirmed_bookings": targets["weekly_confirmed_bookings"],
        "weekly_purchase_authorizations": targets["weekly_purchase_authorizations"],
        "weekly_captured_payments": targets["weekly_captured_payments"],
        "weekly_completed_deliveries": targets["weekly_completed_deliveries"],
    }
    if value["gap"] != expected_gap:
        raise MarketingSalesError("pipeline gap differs from current truth and targets")
    expected_seed = _seed_truth()
    if value["seed_audit"] != expected_seed:
        raise MarketingSalesError("pipeline seed audit differs from canonical sources")
    ranked = sorted(
        universe["entities"],
        key=lambda item: (
            -item["research_score"],
            item["owner_type"] != "Organization",
            item["entity_name"].casefold(),
        ),
    )[:targets["rolling_research_queue"]]
    expected_queue = [
        {
            "rank": rank,
            "entity_id": item["entity_id"],
            "entity_name": item["entity_name"],
            "owner_type": item["owner_type"],
            "research_score": item["research_score"],
            "qualification_state": "RESEARCH_REQUIRED",
            "source_query_ids": item["source_query_ids"],
        }
        for rank, item in enumerate(ranked, 1)
    ]
    if value["research_queue"] != expected_queue:
        raise MarketingSalesError("pipeline research queue differs from ranked universe evidence")
    expected_boundaries = {
        "canonical_crm": "JOJO Revenue Recovery CRM / Revenue Pipeline",
        "public_projection_is_not_crm": True,
        "public_threads_are_evidence_not_contact_permission": True,
        "private_routes_or_provider_ids_published": False,
        "messages_sent_by_this_tool": 0,
    }
    if value["boundaries"] != expected_boundaries:
        raise MarketingSalesError("pipeline boundaries differ from the public-safe contract")
    public_text = canonical_text(value)
    if EMAIL_RE.search(public_text):
        raise MarketingSalesError("public pipeline must not contain email addresses")
    if SECRET_VALUE_RE.search(public_text):
        raise MarketingSalesError("public pipeline must not contain secret values")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_text(value), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser("discover", help="query the public GitHub repository search")
    discover_parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    discover_parser.add_argument("--output", type=Path, default=DEFAULT_UNIVERSE)
    discover_parser.add_argument("--per-page", type=int, default=100)
    discover_parser.add_argument("--max-entities", type=int)

    compile_parser = subparsers.add_parser("compile", help="compile the public research pipeline")
    compile_parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    compile_parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    compile_parser.add_argument("--output", type=Path, default=DEFAULT_PIPELINE)

    subparsers.add_parser("validate", help="validate checked-in universe and pipeline")
    args = parser.parse_args()

    if args.command == "discover":
        value = discover(
            read_object(args.queries),
            per_page=args.per_page,
            max_entities=args.max_entities,
        )
        write_json(args.output, value)
        print(
            f"DISCOVERED {value['truth']['research_entities']} research entities "
            f"{value['truth']['github_organization_entities']} GitHub organizations "
            f"from {value['truth']['source_results']} public repository results; "
            "0 qualified 0 routes 0 sends USD 0 cash"
        )
        return 0
    if args.command == "compile":
        value = compile_pipeline(read_object(args.universe), read_object(args.contract))
        write_json(args.output, value)
        print(
            f"COMPILED {value['current']['research_entities']} research entities "
            f"{value['current']['github_organization_entities']} GitHub organizations "
            f"top {len(value['research_queue'])}; 0 qualified 0 routes 0 sends USD 0 cash"
        )
        return 0
    validate_queries(read_object(DEFAULT_QUERIES))
    validate_contract(read_object(DEFAULT_CONTRACT))
    universe = validate_universe(read_object(DEFAULT_UNIVERSE))
    contract = validate_contract(read_object(DEFAULT_CONTRACT))
    pipeline = validate_pipeline(
        read_object(DEFAULT_PIPELINE), universe=universe, contract=contract
    )
    rebuilt = compile_pipeline(universe, contract)
    if canonical_text(rebuilt) != canonical_text(pipeline):
        raise MarketingSalesError("checked-in pipeline differs from deterministic rebuild")
    print(
        f"VALID {universe['truth']['research_entities']} research entities "
        f"{universe['truth']['github_organization_entities']} GitHub organizations "
        f"{len(pipeline['research_queue'])} queued; 0 qualified 0 routes 0 sends USD 0 cash"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
