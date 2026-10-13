"""Passive, resumable collection over the installed authenticated service roads.

The callback is ``read_page(native_tool_name, args, account_ref)``. An absent
callback exposes the exact same jobs in ``pending_native_reads`` for a native
harness to dispatch. Feed receipts back as ``config['native_results'][job_id]``.
Persist returned state only after Store has encrypted the returned full_source.
Request/page limits schedule work; they never bound the retained corpus.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Mapping


PREFIX = "mcp__codex_apps__"
ALIASES = {"google": "google_drive", "gdrive": "google_drive", "drive": "google_drive",
           "apollo": "apollo_io", "gmail.com": "gmail", "google.com": "google_drive"}
SCOPES = {
    "gmail": ["profile", "all mailbox messages including spam/trash", "threads", "attachments", "labels", "drafts", "history"],
    "google_drive": ["profile", "all drives", "all files including unviewed files", "file contents", "revisions", "comments and replies including deleted", "Docs tabs", "Sheets full grid cells", "Slides"],
    "dropbox": ["profile", "all recursive files", "file contents", "revisions", "restore events", "file requests"],
    "airtable": ["all workspaces", "all bases", "all tables", "all records and fields", "record comments", "interfaces", "automations and runs"],
    "vercel": ["all teams", "all projects", "all deployments", "build logs", "runtime logs", "agent runs and full traces"],
    "railway": ["all workspaces", "all projects", "all services and environments", "all deployments", "build/deploy/http logs", "service configurations and domains"],
    "netlify": ["all teams", "all sites", "deployments", "functions", "build/runtime/function logs", "forms"],
    "stripe": ["all accounts and organizations", "account data", "balances", "balance transactions", "payment intents", "customers", "events", "charges", "invoices", "subscriptions", "payouts"],
    "apollo_io": ["saved contacts", "conversations and transcripts", "email messages and content", "campaign activity", "deals", "tasks", "users", "custom objects", "account activity"],
}


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _id(*values):
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _unwrap(raw):
    """Decode for traversal only; the unmodified envelope is retained separately."""
    value = raw
    for _ in range(12):
        # Some native tools JSON-encode a complete JSON response inside a text
        # block. Decode every wrapper before declaring its source traversed.
        # Plain document text remains a valid leaf response.
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                return value
            continue
        if not isinstance(value, Mapping):
            return value
        if value.get("isError") or value.get("ok") is False or value.get("error"):
            raise RuntimeError("native_service_read_error")
        if isinstance(value.get("structuredContent"), (dict, list, str)):
            value = value["structuredContent"]
        elif isinstance(value.get("result"), (dict, list, str)):
            value = value["result"]
        elif isinstance(value.get("content"), list):
            decoded = []
            text = []
            for block in value["content"]:
                if isinstance(block, Mapping) and block.get("type") == "text":
                    if not isinstance(block.get("text"), str):
                        raise ValueError("native_service_invalid_text_block")
                    text.append(block["text"])
                    try:
                        decoded.append(json.loads(block["text"]))
                    except (TypeError, ValueError):
                        pass
            if not decoded:
                return "\n".join(text)
            value = decoded[0] if len(decoded) == 1 else {"decoded_blocks": decoded}
        else:
            return value
    raise ValueError("native_service_response_nesting_exceeded")


def _response_values(value):
    if isinstance(value, Mapping) and set(value) == {"decoded_blocks"}:
        for block in value["decoded_blocks"]:
            yield from _response_values(_unwrap(block))
    else:
        yield value


def _has_collection(value, keys):
    """Distinguish an empty provider collection from an unrecognized shape."""
    if isinstance(value, list):
        return True
    if not isinstance(value, Mapping):
        return False
    for key in keys:
        rows = value.get(key)
        if isinstance(rows, list) or isinstance(rows, Mapping) and isinstance(rows.get("nodes"), list):
            return True
    return any(_has_collection(value[key], keys) for key in ("data", "results", "response") if key in value)


def _collection_keys(job):
    # These are the collections used by successors/continuation below. Content
    # reads have no collection requirement, including plain-text documents.
    action = (job.get("tool_name") or "").removeprefix(PREFIX)
    collections = {
        "gmail_search_email_ids": ("messages", "emails", "message_ids", "ids"),
        "gmail_list_drafts": ("drafts",),
        "gmail_read_email_thread": ("messages", "emails"),
        "google_drive_search": ("files", "results", "items"),
        "google_drive_list_file_revisions": ("revisions",),
        "google_drive_get_file_comments": ("comments",),
        "dropbox_list_folder": ("entries",),
        "dropbox_list_restore_events": ("events",),
        "dropbox_list_file_requests": ("file_requests",),
        "dropbox_list_file_revisions": ("entries",),
        "airtable_list_bases": ("bases",),
        "airtable_list_tables_for_base": ("tables",),
        "airtable_list_records_for_table": ("records",),
        "airtable_list_automations": ("automations",),
        "vercel_list_teams": ("teams",),
        "vercel_list_projects": ("projects",),
        "vercel_list_deployments": ("deployments",),
        "vercel_list_agent_runs": ("runs", "agentRuns", "items"),
        "railway_list_projects": ("projects",),
        "railway_list_services": ("services",),
        "railway_list_deployments": ("deployments",),
        "stripe_list_available_accounts_or_orgs": ("accounts",),
        "stripe_stripe_api_search": ("data",),
        "apollo_io_apollo_find_tools": ("tools",),
        "chatgpt_space_list_spaces": ("spaces", "items"),
        "chatgpt_space_list_pages": ("items", "pages"),
        "chatgpt_space_list_page_comments": ("items", "comments"),
        "pets_list_pets": ("pets", "items"),
        "sites_list_sites": ("items", "sites"),
        "sites_list_site_versions": ("items", "versions"),
    }
    operation = job.get("args", {}).get("selectSchema", {}).get("operation")
    if action == "netlify_netlify_team_services_reader" and operation == "get-teams":
        return ("teams", "accounts")
    if action == "netlify_netlify_project_services_reader" and operation == "get-projects":
        return ("sites", "projects")
    return collections.get(action)


def _rows(value, *keys):
    if isinstance(value, list):
        return [row for row in value if isinstance(row, Mapping)]
    if not isinstance(value, Mapping):
        return []
    for key in keys:
        rows = value.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, Mapping)]
        if isinstance(rows, Mapping) and isinstance(rows.get("nodes"), list):
            return _rows(rows["nodes"])
    for key in ("data", "results", "response", "decoded_blocks"):
        if key in value:
            rows = _rows(value[key], *keys)
            if rows:
                return rows
    return []


def _walk(value):
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _column(number):
    result = ""
    while number:
        number, digit = divmod(number - 1, 26)
        result = chr(65 + digit) + result
    return result


def _catalog(config, sources):
    rows = list(sources or [])
    value = config.get("source_catalog")
    if value is None:
        path = Path(config.get("source_catalog_path", "work/telemetry-runtime/service-catalog.json"))
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(value, Mapping):
        rows.extend(value.get("sources", []))
        rows.extend(value.get("accounts", []))
    elif isinstance(value, list):
        rows.extend(value)
    rows.extend(config.get("service_sources", []))
    return [dict(row) for row in rows if isinstance(row, Mapping)]


class _Collector:
    def __init__(self, config, state, sources):
        self.config = config
        self.state = copy.deepcopy(state or {})
        self.state.setdefault("jobs", {})
        self.state.setdefault("roots", {})
        self.state.setdefault("cycle", 0)
        self.events = []
        self.sources = _catalog(config, sources)
        self.available = set(config.get("available_tools", []))
        for row in self.sources:
            self.available.update(row.get("tools", []))
        self.at = _now()
        self.active_cycle = self.state["cycle"]

    def add(self, service, account, action, args=None, *, scope=None, context=None, gap=None, poll=False):
        args = copy.deepcopy(args or {})
        tool = PREFIX + action if action else None
        key = _id(service, account, tool, args, scope, context if gap else None,
                  0 if gap else self.active_cycle)
        job = self.state["jobs"].setdefault(key, {
            "job_id": key, "operation_id": "passive-service-read:" + key,
            "service": service, "account_ref": account, "tool_name": tool,
            "args": args, "scope": scope or action, "context": copy.deepcopy(context or {}),
            "status": "pending_recovery" if gap else "queued", "attempts": 0,
            "complete": False, "created_at": self.at, "cycle": self.active_cycle,
            "unread_regions": [gap] if gap else [], "poll_root": bool(poll),
            "alternate_reader": "existing authenticated provider SDK/API or native harness; shared secure reference retrieval" if gap else None,
        })
        if not gap and self.available and tool not in self.available:
            job.update(status="pending_recovery", unread_regions=["native tool unavailable in this installed catalog"],
                       alternate_reader="recover installed service connector, then existing authenticated provider SDK/API")
        return job

    def gap(self, job, scope, reason):
        return self.add(job["service"], job["account_ref"], None, scope=scope,
                        context={**job.get("context", {}), "parent_tool_name": job.get("tool_name"),
                                 "parent_args": copy.deepcopy(job.get("args", {}))}, gap=reason)

    def seed(self):
        seen = set()
        for row in self.sources:
            service = str(row.get("service") or row.get("source") or row.get("provider") or "unknown").lower()
            service = ALIASES.get(service, service)
            if service in {"slack", "github"}:
                continue  # Dedicated full-source collectors own these roads.
            account = str(row.get("account_ref") or service + ":installed-connector-account-unresolved")
            if (service, account) in seen:
                continue
            seen.add((service, account))
            rootkey = _id(service, account)
            if rootkey in self.state["roots"]:
                continue
            self.state["roots"][rootkey] = {"service": service, "account_ref": account, "discovered_at": self.at}
            self.bootstrap(service, account)
        # Existing checkpoints may already have completed table discovery before
        # detailed field schemas were collected. Recover the table identities
        # from record jobs once, retaining every historical job and cursor.
        if not self.state.get("airtable_field_schemas_seeded"):
            recovered = set()
            for job in list(self.state["jobs"].values()):
                if job.get("tool_name") != PREFIX + "airtable_list_records_for_table":
                    continue
                args = job.get("args", {})
                base, table = args.get("baseId"), args.get("tableId")
                identity = (job["account_ref"], base, table)
                if base and table and identity not in recovered:
                    recovered.add(identity)
                    self.add("airtable", job["account_ref"], "airtable_get_table_schema",
                             {"baseId": base, "tables": [{"tableId": table}]})
            self.state["airtable_field_schemas_seeded"] = True
        if not seen and not self.sources:
            self.add("all_services", "unresolved", None, scope="all accounts/services", gap="service catalog discovery and authenticated reader binding pending")

    def bootstrap(self, service, account):
        def add(action, args=None, **kw):
            return self.add(service, account, action, args, poll=True, **kw)
        if service == "gmail":
            add("gmail_get_profile")
            add("gmail_list_labels")
            add("gmail_list_drafts", {"max_results": 500})
            add("gmail_search_email_ids", {"query": "in:anywhere", "max_results": 500})
            self.add(service, account, None, scope="history", gap="users.history.list is not exposed by installed Gmail connector; recover direct authenticated Gmail SDK history road")
        elif service == "google_drive":
            add("google_drive_get_profile")
            add("google_drive_list_drives")
            # Explicit item_type requests return provider pages with real tokens.
            for kind in ("image", "document", "folder"):
                add("google_drive_search", {"item_type": kind, "topn": 100, "require_viewed_by_user": False})
            self.add(service, account, None, scope="other binary MIME types and Drive change journal", gap="Drive connector paginated search supports image/document/folder categories only; bind authenticated files.list(all MIME types, allDrives) and changes.list road")
        elif service == "dropbox":
            add("dropbox_who_am_i")
            add("dropbox_list_folder", {"path": "", "recursive": True, "max_results": 600})
            add("dropbox_list_restore_events", {"path": "", "direction": "PAST", "only_rewindable": False})
            add("dropbox_list_file_requests", {"limit": 1000})
        elif service == "airtable":
            add("airtable_list_workspaces")
            add("airtable_list_bases")
            add("airtable_list_external_accounts")
        elif service == "vercel":
            add("vercel_list_teams")
        elif service == "railway":
            add("railway_whoami")
            add("railway_list_workspaces")
            add("railway_list_projects")
        elif service == "netlify":
            add("netlify_netlify_team_services_reader", {"selectSchema": {"operation": "get-teams"}})
            add("netlify_netlify_project_services_reader", {"selectSchema": {"operation": "get-projects"}})
            self.add(service, account, None, scope="all deployments, functions and build/runtime/function logs", gap="installed Netlify reader has get-deploy but no enumeration/log API; bind authenticated Netlify SDK listSiteDeploys/listSiteFunctions and native log road")
        elif service == "stripe":
            add("stripe_list_available_accounts_or_orgs")
        elif service == "chatgpt":
            add("chatgpt_space_list_spaces", {"limit": 100})
            add("chatgpt_space_list_pages", {"limit": 100, "top_level_only": False, "include_has_children": True})
            self.add(service, account, None, scope="all ChatGPT account conversations and account history", gap="Pages connector enumerates spaces/pages only; recover existing account export/history connector road for complete conversations")
        elif service == "sites":
            add("sites_list_sites", {"limit": 50, "include_editable": True})
            self.add(service, account, None, scope="all Sites source versions and deployment activity", gap="recover native site version/source/activity enumeration and complete provider Git object roads from each returned source_repository reference")
        elif service == "pets":
            add("pets_list_pets", {"limit": 100})
            self.add(service, account, None, scope="all pet original assets and lifecycle history", gap="native catalog/download-link references retained; recover complete asset bytes and provider lifecycle history road")
        elif service == "apollo_io":
            add("apollo_io_apollo_find_tools", {"intent": "read", "query": "Enumerate all saved account contacts, conversations, message content, campaigns, deals, tasks, custom object records and historical activity with pagination schemas"})
            for action in ("apollo_users_api_profile", "apollo_email_accounts_index", "apollo_contacts_search", "apollo_conversations_search", "apollo_emailer_messages_search", "apollo_emailer_campaigns_search", "apollo_deals_search", "apollo_tasks_search", "apollo_users_search", "apollo_custom_objects_show", "apollo_labels_index", "apollo_fields_index"):
                add("apollo_io_apollo_find_tools", {"intent": "read", "query": action + " exact input schema, complete account enumeration and pagination"}, context={"target_action": action})
                if action == "apollo_custom_objects_show":
                    self.add(service, account, None, scope="Apollo collection identities and contents", context={"target_action": action}, gap="native collection detail requires an existing collection ID; recover exact IDs from retained account source or authenticated provider inventory before binding reads")
                    continue
                parameters = {"action": action}
                if action in {"apollo_contacts_search", "apollo_conversations_search"}:
                    parameters.update(page=1, per_page=50)
                add("apollo_io_apollo_read", parameters)
        else:
            self.add(service, account, None, scope="all account activity and full retained service contents", gap="native reader schema/account binding pending; discover existing authenticated installed/custom service road without excluding this account")

    def continuation(self, job, value):
        """Continue only through parameters present in the actual native schema."""
        if not isinstance(value, Mapping):
            return
        action = (job.get("tool_name") or "").removeprefix(PREFIX)
        args = copy.deepcopy(job["args"])
        token_fields = {
            "gmail_search_email_ids": ("next_page_token", ("next_page_token", "nextPageToken")),
            "gmail_list_drafts": ("next_page_token", ("next_page_token", "nextPageToken")),
            "google_drive_search": ("page_token", ("next_page_token", "nextPageToken")),
            "google_drive_list_file_revisions": ("pageToken", ("nextPageToken", "next_page_token")),
            "google_drive_get_file_comments": ("page_token", ("nextPageToken", "next_page_token")),
            "airtable_list_bases": ("offset", ("offset",)),
            "airtable_list_records_for_table": ("cursor", ("nextCursor",)),
            "airtable_list_record_comments": ("offset", ("offset",)),
            "airtable_list_automation_runs": ("cursor", ("nextCursor",)),
            "chatgpt_space_list_spaces": ("cursor", ("next_cursor", "nextCursor")),
            "chatgpt_space_list_pages": ("cursor", ("next_cursor", "nextCursor")),
            "pets_list_pets": ("cursor", ("next_cursor", "nextCursor", "cursor")),
            "sites_list_sites": ("cursor", ("cursor", "next_cursor", "nextCursor")),
            "sites_list_site_versions": ("cursor", ("cursor", "next_cursor", "nextCursor")),
        }
        token = None
        parameter = None
        if action in token_fields:
            parameter, fields = token_fields[action]
            token = next((value.get(field) for field in fields if value.get(field)), None)
        if action in {"dropbox_list_folder", "dropbox_list_restore_events", "dropbox_list_file_requests"}:
            if value.get("has_more"):
                token, parameter = value.get("cursor"), "cursor"
                args = {}  # Native Dropbox continuation accepts cursor only.
                if not token:
                    self.gap(job, job["scope"] + ":continuation", "provider reports has_more without a native continuation cursor")
        if token:
            if str(token) == str(job["args"].get(parameter, "")):
                self.gap(job, job["scope"] + ":continuation", "provider cursor stalled; recover reader without discarding remaining source")
            else:
                args[parameter] = token
                self.add(job["service"], job["account_ref"], action, args, scope=job["scope"], context=job["context"])
        elif action == "vercel_list_deployments":
            next_time = (value.get("pagination") or {}).get("next")
            if next_time is not None:
                if str(next_time) == str(args.get("until")):
                    self.gap(job, job["scope"] + ":continuation", "deployment time cursor stalled")
                else:
                    args["until"] = next_time
                    self.add(job["service"], job["account_ref"], action, args, context=job["context"])
        elif action == "vercel_list_agent_runs":
            rows = _rows(value, "runs", "agentRuns", "items")
            pagination = value.get("pagination") or {}
            if value.get("hasMore") or pagination.get("hasMore") or len(rows) >= args.get("pageSize", 100):
                args["page"] = args.get("page", 1) + 1
                self.add(job["service"], job["account_ref"], action, args, context=job["context"])
        elif action == "stripe_stripe_api_read" and value.get("has_more"):
            rows = _rows(value, "data")
            if rows and rows[-1].get("id"):
                args.setdefault("parameters", {})["starting_after"] = rows[-1]["id"]
                self.add(job["service"], job["account_ref"], action, args, context=job["context"])
            else:
                self.gap(job, "Stripe continuation", "has_more without last object ID; recover native Stripe list continuation")
        elif action == "apollo_io_apollo_read":
            subaction = args.get("action")
            schema = self.state.get("apollo_action_schemas", {}).get(subaction, {})
            properties = schema.get("properties", {})
            pagination = value.get("pagination") or {}
            current = int(str(args.get("page", pagination.get("page", 1))))
            page_size = int(str(args.get("per_page", pagination.get("per_page", 50))))
            raw_total = pagination.get("total_pages", value.get("total_pages"))
            total = None if raw_total is None else int(str(raw_total))
            if current < 1 or page_size < 1 or total is not None and total < 0:
                raise ValueError("native_apollo_invalid_pagination")
            more = bool(value.get("next_page") or value.get("has_more") or total is not None and current < total)
            rows = _rows(value, "contacts", "conversations", "emailer_messages", "messages", "emailer_campaigns", "campaigns", "deals", "tasks", "users", "records")
            if total is None and len(rows) >= page_size:
                more = True
            if more:
                if "page" in properties and "per_page" in properties:
                    for field, number in (("page", current + 1), ("per_page", page_size)):
                        args[field] = str(number) if properties[field].get("type") == "string" else number
                    self.add(job["service"], job["account_ref"], action, args, context=job["context"])
                else:
                    self.gap(job, "Apollo continuation:" + str(subaction), "provider has more source; recover exact action pagination schema via native Apollo tool discovery")
        elif any(value.get(key) for key in ("nextPageToken", "next_page_token", "nextCursor", "has_more", "hasMore")) or (value.get("pagination") or {}).get("next"):
            self.gap(job, job["scope"] + ":continuation", "provider continuation exists but installed native tool lacks a supported pagination argument")

    def time_partition(self, job, value):
        action = (job.get("tool_name") or "").removeprefix(PREFIX)
        if action not in {"railway_get_logs", "vercel_get_runtime_logs", "vercel_get_deployment_build_logs"}:
            return
        streams = [value.get(k, []) for k in ("build", "deploy", "http")] if action == "railway_get_logs" else [_rows(value, "logs", "events", "entries", "data")]
        limit = job["args"].get("limit", 100)
        if not any(len(stream) >= limit for stream in streams):
            return
        args = job["args"]
        start_key, end_key = ("startDate", "endDate") if action == "railway_get_logs" else ("since", "until")
        try:
            start = datetime.fromisoformat(args[start_key].replace("Z", "+00:00"))
            end = datetime.fromisoformat(args[end_key].replace("Z", "+00:00"))
            midpoint = start + (end - start) / 2
            if (end - start).total_seconds() <= 0.000001:
                raise ValueError("timestamp_density")
            for low, high in ((start, midpoint), (midpoint, end)):
                successor = dict(args)
                successor[start_key] = low.isoformat().replace("+00:00", "Z")
                successor[end_key] = high.isoformat().replace("+00:00", "Z")
                self.add(job["service"], job["account_ref"], action, successor, context=job["context"])
        except (KeyError, ValueError, TypeError):
            self.gap(job, job["scope"] + ":dense time partition", "native log cap saturated; recover provider cursor/export road for dense timestamps")

    def successors(self, job, value):
        service, account = job["service"], job["account_ref"]
        action = (job.get("tool_name") or "").removeprefix(PREFIX)
        args, context = job["args"], job["context"]
        def add(name, params=None, **kw):
            return self.add(service, account, name, params, context=kw.pop("context", context), **kw)
        if action == "gmail_search_email_ids":
            rows = _rows(value, "messages", "emails", "message_ids", "ids")
            if isinstance(value, Mapping):
                for key in ("message_ids", "ids"):
                    if isinstance(value.get(key), list):
                        rows += [{"id": x} for x in value[key] if isinstance(x, str)]
            for row in rows:
                mid = row.get("id") or row.get("message_id")
                if mid:
                    add("gmail_read_email", {"message_id": mid, "format": "full"})
                    add("gmail_read_email", {"message_id": mid, "format": "raw"})
                tid = row.get("threadId") or row.get("thread_id")
                if tid:
                    add("gmail_read_email_thread", {"thread_id": tid, "max_messages": 500})
        elif action == "chatgpt_space_list_spaces":
            for row in _rows(value, "spaces", "items"):
                sid = row.get("space_id") or row.get("id")
                if sid:
                    add("chatgpt_space_get_space", {"space_id": sid})
                    add("chatgpt_space_list_pages", {"space_id": sid, "limit": 100, "top_level_only": False, "include_has_children": True})
        elif action == "chatgpt_space_get_space":
            if isinstance(value, Mapping) and value.get("root_page_id"):
                add("chatgpt_space_read_page", {"page_id": value["root_page_id"], "view": "full", "include_content": True})
        elif action == "chatgpt_space_list_pages":
            for row in _rows(value, "items", "pages"):
                if row.get("page_id"):
                    add("chatgpt_space_read_page", {"page_id": row["page_id"], "view": "full", "include_content": True})
                    add("chatgpt_space_list_page_automations", {"page_id": row["page_id"]})
                    add("chatgpt_space_list_page_comments", {"page_id": row["page_id"], "limit": 100})
                    if row.get("has_children"):
                        add("chatgpt_space_list_pages", {"parent_page_id": row["page_id"], "limit": 100, "top_level_only": False})
            if isinstance(value, Mapping) and (value.get("partial_results") or value.get("incomplete_reasons")):
                self.gap(job, "all Page contents", "native Pages listing reports partial results; recover complete account provider enumeration")
        elif action == "pets_list_pets":
            for row in _rows(value, "pets", "items"):
                pid = row.get("pet_id") or row.get("id")
                if pid:
                    add("pets_get_pet_download_link", {"pet_id": pid})
        elif action == "sites_list_sites":
            for row in _rows(value, "items", "sites"):
                sid = row.get("id") or row.get("project_id")
                if sid:
                    add("sites_get_site", {"project_id": sid, "include_mcp_connection": True})
                    add("sites_list_site_versions", {"project_id": sid, "limit": 50})
                    # The native reader supports seven days; retain older history as a recovery gap.
                    add("sites_get_site_worker_logs", {"project_id": sid, "errors_only": False, "limit": 100, "since_minutes": 10080})
                    self.gap(job, "all historical Sites worker logs:" + sid, "native recent worker log tool has no cursor or end-time bound; recover complete source/provider activity road")
        elif action == "sites_list_site_versions":
            for row in _rows(value, "items", "versions"):
                if row.get("id"):
                    add("sites_get_site_version", {"project_id": args["project_id"], "version_id": row["id"]})
        elif action == "chatgpt_space_list_page_comments":
            if len(_rows(value, "items", "comments")) >= args.get("limit", 100):
                self.gap(job, "all Page comments:" + args["page_id"], "native comments read cap reached and schema has no cursor; recover complete comment-history provider road")
        elif action == "gmail_list_drafts":
            for row in _rows(value, "drafts"):
                message = row.get("message") or {}
                mid = row.get("message_id") or message.get("id")
                if mid:
                    add("gmail_read_email", {"message_id": mid, "format": "full"})
                    add("gmail_read_email", {"message_id": mid, "format": "raw"})
        elif action == "gmail_read_email":
            if args.get("format") == "full":
                for part in _walk(value):
                    if part.get("read_attachment_supported") is True:
                        identifier = part.get("attachment_id")
                        attach = {"message_id": args["message_id"]}
                        if identifier and not part.get("attachment_id_truncated"):
                            attach["attachment_id"] = identifier
                        elif part.get("filename"):
                            attach["filename"] = part["filename"]
                        else:
                            self.gap(job, "Gmail attachment identity", "attachment lacks complete ID and filename")
                            continue
                        add("gmail_read_attachment", attach)
                    elif part.get("read_attachment_supported") is False:
                        self.gap(job, "Gmail unsupported attachment", "preserve exact attachment references; bind authenticated Gmail MIME body download for unsupported native extraction")
                    elif part.get("attachment_id") or part.get("attachmentId"):
                        self.gap(job, "Gmail MIME attachment support", "attachment reference retained but native support flag absent; recover exact attachment descriptor or authenticated Gmail attachment download")
                tid = value.get("threadId") or value.get("thread_id") if isinstance(value, Mapping) else None
                if tid:
                    add("gmail_read_email_thread", {"thread_id": tid, "max_messages": 500})
        elif action == "gmail_read_email_thread":
            rows = _rows(value, "messages", "emails")
            for row in rows:
                if row.get("id") or row.get("message_id"):
                    add("gmail_read_email", {"message_id": row.get("id") or row["message_id"], "format": "full"})
            if len(rows) >= args.get("max_messages", 500) or isinstance(value, Mapping) and value.get("truncated"):
                self.gap(job, "complete thread", "thread native cap reached; mailbox-wide per-message reads preserve all messages; bind users.threads.get for complete thread structure")
        elif action in {"gmail_read_attachment", "google_drive_fetch", "google_drive_fetch_file_revision", "dropbox_fetch"}:
            for part in _walk(value):
                if part.get("content_truncated") or part.get("truncated"):
                    self.gap(job, "full binary/extraction contents", "inline content truncated; original file_uri/extraction_file_uri retained; native reference reader must ingest complete referenced bytes")
        elif action == "google_drive_list_drives":
            if isinstance(value, Mapping) and value.get("nextPageToken"):
                self.gap(job, "all shared drives", "list_drives native schema has no page token; bind Drive drives.list pagination")
        elif action == "google_drive_search":
            for row in _rows(value, "files", "results", "items"):
                fid = row.get("id") or row.get("file_id")
                url = row.get("url") or row.get("webViewLink")
                if not fid and not url:
                    self.gap(job, "Drive result identity", "search item lacks native file ID or canonical URL")
                    continue
                if fid and str(fid).startswith("gdrive://"):
                    fid = str(fid).split("/")[-1]
                if not url and fid:
                    url = "https://drive.google.com/file/d/" + str(fid) + "/view"
                mime = row.get("mimeType") or row.get("mime_type") or ""
                if mime != "application/vnd.google-apps.folder":
                    add("google_drive_fetch", {"url": url, "download_raw_file": True, "include_base64": False})
                    add("google_drive_fetch", {"url": url})
                if fid:
                    add("google_drive_get_file_comments", {"id": fid, "include_deleted": True, "page_size": 100})
                    add("google_drive_list_file_revisions", {"fileId": fid, "pageSize": 100})
                    if mime == "application/vnd.google-apps.document":
                        add("google_drive_get_document", {"document_id": fid})
                    elif mime == "application/vnd.google-apps.presentation":
                        add("google_drive_get_presentation", {"presentation_id": fid})
                    elif mime == "application/vnd.google-apps.spreadsheet":
                        add("google_drive_get_spreadsheet_metadata", {"spreadsheet_id": fid, "include_conditional_format_rules": True})
        elif action == "google_drive_list_file_revisions":
            for row in _rows(value, "revisions"):
                if row.get("id"):
                    add("google_drive_fetch_file_revision", {"fileId": args["fileId"], "revisionId": row["id"]})
        elif action == "google_drive_get_spreadsheet_metadata":
            for row in _rows(value, "sheets"):
                props = row.get("properties", row)
                grid = props.get("gridProperties") or props.get("grid_properties") or {}
                title = props.get("title")
                count, columns = grid.get("rowCount"), grid.get("columnCount")
                if not title or not isinstance(count, int) or not isinstance(columns, int):
                    self.gap(job, "complete Sheets grid", "sheet bounds absent; recover native metadata before all-cell traversal")
                    continue
                width = _column(columns)
                quoted = "'" + title.replace("'", "''") + "'"
                for start in range(1, count + 1, 500):
                    add("google_drive_get_spreadsheet_cells", {"spreadsheet_id": args["spreadsheet_id"], "ranges": [f"{quoted}!A{start}:{width}{min(start + 499, count)}"], "cell_fields": "*"})
        elif action == "dropbox_list_folder":
            for row in _rows(value, "entries"):
                if row.get("object_type") == "file" or row.get("file") is not None:
                    fid = row.get("file_id") or row.get("path") or row.get("path_display")
                    if fid:
                        add("dropbox_fetch", {"id": fid})
                        add("dropbox_list_file_revisions", {"path_or_file_id": fid, "limit": 100})
                        self.gap(job, "Dropbox original binary:" + str(fid), "fetch provides extracted text with 5 MiB cap; preserve metadata and bind existing authenticated files.download for complete original bytes")
        elif action == "dropbox_list_file_revisions":
            if isinstance(value, Mapping) and value.get("has_more"):
                self.gap(job, "all Dropbox revisions:" + args["path_or_file_id"], "native revisions limit100 has no continuation argument; bind authenticated revision-history road")
            for row in _rows(value, "entries"):
                if row.get("rev"):
                    self.gap(job, "Dropbox revision content:" + row["rev"], "revision metadata retained; native fetch cannot select revision; bind files.download(rev) using existing shared credential")
        elif action == "dropbox_list_file_requests":
            for row in _rows(value, "file_requests"):
                if row.get("id"):
                    add("dropbox_get_file_request", {"id": row["id"]})
        elif action == "airtable_list_bases":
            for row in _rows(value, "bases"):
                if row.get("id"):
                    add("airtable_list_pages_for_base", {"baseId": row["id"], "shouldIncludeRecordDetailPages": True, "shouldIncludeTableSchema": True,
                                                           "shouldIncludeDraftPages": row.get("permissionLevel") not in {"none", "interfaceOnly"}})
                    add("airtable_list_automations", {"baseId": row["id"], "includeDeployedVersion": True})
                    if row.get("permissionLevel") not in {"none", "interfaceOnly"}:
                        add("airtable_list_tables_for_base", {"baseId": row["id"]})
        elif action == "airtable_list_tables_for_base":
            for row in _rows(value, "tables"):
                if row.get("id"):
                    fields = [field["id"] for field in row.get("fields", []) if field.get("id")]
                    # Table summaries omit type-specific options such as select
                    # choices and formula configuration. Retain the full schema
                    # alongside record values through the same native queue.
                    add("airtable_get_table_schema", {"baseId": args["baseId"], "tables": [{"tableId": row["id"]}]})
                    add("airtable_list_records_for_table", {"baseId": args["baseId"], "tableId": row["id"], "fieldIds": fields, "pageSize": 100})
        elif action == "airtable_list_records_for_table":
            for row in _rows(value, "records"):
                if row.get("id"):
                    add("airtable_list_record_comments", {"baseId": args["baseId"], "tableId": args["tableId"], "recordId": row["id"], "pageSize": 100})
        elif action == "airtable_list_pages_for_base":
            count = 0
            for page in _walk(value):
                pid = page.get("pageId") or (page.get("id") if page.get("pageType") else None)
                iid = page.get("interfaceId")
                if pid and iid and page.get("pageType") in {"list", "dashboard"}:
                    parameters = {"baseId": args["baseId"], "interfaceId": iid, "pageId": pid, "pageSize": 100}
                    elements = page.get("elements") or page.get("dashboardElements") or []
                    element_ids = [entry.get("id") or entry.get("elementId") for entry in elements if isinstance(entry, Mapping)]
                    if element_ids:
                        for eid in element_ids:
                            if eid:
                                add("airtable_list_records_for_page", {**parameters, "elementId": eid})
                                count += 1
                    else:
                        add("airtable_list_records_for_page", parameters)
                        count += 1
            if not count and _rows(value, "interfaces", "pages", "draftPages"):
                self.gap(job, "all Airtable interface records", "native interface records need published page/element IDs; recover complete page schema and provider record road")
        elif action == "airtable_list_records_for_page":
            grouped = value.get("recordsByTableId", {}) if isinstance(value, Mapping) else {}
            if any(len(records) >= args.get("pageSize", 100) for records in grouped.values() if isinstance(records, list)):
                self.gap(job, "all interface page records:" + args["pageId"], "native interface page read has pageSize but no pagination argument; recover authenticated table-record cursor road")
        elif action == "airtable_list_automations":
            for row in _rows(value, "automations"):
                aid = row.get("id") or row.get("automationId")
                if aid:
                    add("airtable_list_automation_runs", {"baseId": args["baseId"], "automationId": aid, "pageSize": 100})
        elif action == "vercel_list_teams":
            for row in _rows(value, "teams"):
                if row.get("id"):
                    add("vercel_list_projects", {"teamId": row["id"]})
        elif action == "vercel_list_projects":
            for row in _rows(value, "projects"):
                if row.get("id"):
                    ctx = {"projectId": row["id"], "teamId": args["teamId"]}
                    add("vercel_list_deployments", ctx, context=ctx)
                    for environment in ("production", "preview"):
                        add("vercel_list_agent_runs", {**ctx, "pageSize": 100, "page": 1, "from": "1970-01-01T00:00:00Z", "to": self.at, "environment": environment}, context=ctx)
                    add("vercel_get_runtime_logs", {**ctx, "since": "1970-01-01T00:00:00Z", "until": self.at, "limit": 100}, context=ctx)
        elif action == "vercel_list_deployments":
            for row in _rows(value, "deployments"):
                did = row.get("uid") or row.get("id")
                if did:
                    add("vercel_get_deployment_build_logs", {"teamId": args["teamId"], "idOrUrl": did, "limit": 100, "direction": "head", "errorsOnly": False, "since": "1970-01-01T00:00:00Z", "until": self.at})
        elif action == "vercel_list_agent_runs":
            for row in _rows(value, "runs", "agentRuns", "items"):
                rid = row.get("id") or row.get("runId")
                if rid:
                    params = {key: args[key] for key in ("teamId", "projectId", "environment", "from", "to") if key in args}
                    params["runId"] = rid
                    add("vercel_get_agent_run", params)
                    add("vercel_get_agent_run_trace", {**params, "maxFieldLength": 0})
        elif action == "railway_list_projects":
            for row in _rows(value, "projects"):
                if row.get("id"):
                    add("railway_list_services", {"projectId": row["id"]})
                    add("railway_list_deployments", {"projectId": row["id"], "limit": 50})
        elif action == "railway_list_services":
            environments = _rows(value, "environments")
            for row in _rows(value, "services"):
                for environment in environments:
                    if row.get("id") and environment.get("id"):
                        params = {"projectId": args["projectId"], "serviceId": row["id"], "environmentId": environment["id"]}
                        add("railway_get_service_config", params)
                        add("railway_list_domains", params)
                        add("railway_list_deployments", {**params, "limit": 50})
        elif action == "railway_list_deployments":
            rows = _rows(value, "deployments")
            for row in rows:
                if row.get("id"):
                    add("railway_get_logs", {"projectId": args["projectId"], "deploymentId": row["id"], "types": ["build", "deploy", "http"], "startDate": row.get("createdAt") or "1970-01-01T00:00:00Z", "endDate": self.at, "limit": 500})
            # Native API exposes max50 and no cursor; even a short response gives
            # no authoritative total/terminal marker for all historical runs.
            self.gap(job, "all Railway historical deployments:" + args["projectId"], "native list_deployments lacks cursor/time bounds; bind authenticated Railway GraphQL deployment connection(after) for historical enumeration")
        elif action == "netlify_netlify_team_services_reader":
            for row in _rows(value, "teams", "accounts"):
                slug = row.get("slug")
                if slug:
                    add("netlify_netlify_project_services_reader", {"selectSchema": {"operation": "get-projects", "params": {"teamSlug": slug}}})
        elif action == "netlify_netlify_project_services_reader":
            for row in _rows(value, "sites", "projects"):
                sid = row.get("id")
                if sid:
                    add("netlify_netlify_project_services_reader", {"selectSchema": {"operation": "get-project", "params": {"siteId": sid}}})
                    add("netlify_netlify_project_services_reader", {"selectSchema": {"operation": "get-forms-for-project", "params": {"siteId": sid}}})
                    for deployment in (row.get("published_deploy"), row.get("deploy")):
                        if isinstance(deployment, Mapping) and deployment.get("id"):
                            add("netlify_netlify_deploy_services_reader", {"selectSchema": {"operation": "get-deploy-for-site", "params": {"siteId": sid, "deployId": deployment["id"]}}})
        elif action == "stripe_list_available_accounts_or_orgs":
            for row in _rows(value, "accounts"):
                if row.get("stripe_context") and isinstance(row.get("livemode"), bool):
                    ctx = {"stripe_context": row["stripe_context"], "livemode": row["livemode"]}
                    for resource in SCOPES["stripe"][1:]:
                        add("stripe_stripe_api_search", {**ctx, "intent": "read/list all retained " + resource, "resource": resource, "limit": 20}, context={**ctx, "resource": resource})
        elif action == "stripe_stripe_api_search":
            operations = [row for row in _rows(value, "data") if row.get("method", "").upper() == "GET"]
            matches = [row for row in operations if "{" not in row.get("path", "")]
            for row in matches:
                params = {"stripe_context": args["stripe_context"], "livemode": args["livemode"], "stripe_api_operation_id": row["id"]}
                add("stripe_stripe_api_details", params, context={**context, "read_args": params, "path": row.get("path")})
            if not matches:
                self.gap(job, "Stripe resource:" + context.get("resource", "unknown"), "native GET operation/account path parameters need discovery; preserve search response and recover authenticated Stripe SDK road")
        elif action == "stripe_stripe_api_details":
            params = dict(context["read_args"])
            path = context.get("path", "")
            # Top-level account and balance retrieve do not accept limit.
            if path not in {"/v1/account", "/v1/balance"}:
                params["parameters"] = {"limit": 100}
            add("stripe_stripe_api_read", params)
        elif action == "apollo_io_apollo_find_tools":
            for descriptor in _rows(value, "tools"):
                name = descriptor.get("name")
                if name and descriptor.get("dispatcher") in {"apollo_read", "mcp__codex_apps__apollo_io_apollo_read", None}:
                    self.state.setdefault("apollo_action_schemas", {})[name] = {"properties": descriptor.get("properties", {}), "required": descriptor.get("required", [])}
        elif action == "apollo_io_apollo_read":
            subaction = args.get("action", "")
            next_page = value.get("next_page") if isinstance(value, Mapping) else None
            if next_page and not self.state.get("apollo_action_schemas", {}).get(subaction):
                self.gap(job, "Apollo pagination:" + subaction, "native Apollo read action schema must be resolved from apollo_find_tools before provider-specific page arguments are dispatched")
            for row in _rows(value, "conversations"):
                if row.get("id"):
                    self.gap(job, "Apollo transcript:" + row["id"], "conversation identity discovered; bind exact native transcript/insights/recording-link action parameters from Apollo schema")
        if isinstance(value, Mapping) and any(value.get(key) for key in ("truncated", "content_truncated", "partial", "incompleteSearch")):
            self.gap(job, job["scope"] + ":unreturned contents", "native response declares partial/truncated source; recover complete original/reference or provider continuation")

    def retain(self, job, raw):
        digest = _id(raw)
        size = len(json.dumps(raw, ensure_ascii=False, default=str).encode("utf-8"))
        self.events.append({
            "event_id": _id(job["job_id"], digest), "source": "service_activity",
            "source_id": job["job_id"], "event_type": "native_service_response",
            "provider": job["service"], "harness": "native_authenticated_connector",
            "occurred_at": None, "observed_at": self.at, "status": "observed",
            "operation_id": job["operation_id"], "summary": "Passive service source response captured",
            "metrics": {"source_envelope_bytes": size},
            "metadata": {"service": job["service"], "account_ref": job["account_ref"], "job_id": job["job_id"], "tool_name": job["tool_name"]},
            "source_ref": {"job_id": job["job_id"], "tool_name": job["tool_name"], "account_ref": job["account_ref"], "args": copy.deepcopy(job["args"]), "envelope_sha256": digest},
            "full_source": raw,
        })
        return digest


def collect_service_activity(config=None, state=None, sources=None, read_page=None):
    """Return events, coverage, checkpoint proposals and all pending native reads.

    ``max_pages_per_cycle`` is a scheduling quantum (default 50). Successor jobs
    are durable and unbounded. ``native_results`` may contain either the original
    tool result or ``{'payload': result, 'source_ref': trace_reference}``.
    Callback failures are retained as recovery jobs without copying secret error
    strings into operational status. All successful/error native envelopes enter
    full_source; no field, body, character or binary-reference selection occurs.
    """
    config = dict(config or {})
    collector = _Collector(config, state, sources)
    collector.seed()
    jobs = collector.state["jobs"]
    receipts = config.get("native_results", {})
    used = 0
    quantum = max(1, int(config.get("max_pages_per_cycle", 50)))
    attempted = set()
    has_reader = callable(read_page)
    while used < quantum:
        # Native-only passes can consume receipts, but must not repeatedly
        # select and skip every queued job while enumerating pending reads.
        candidates = [job for key, job in jobs.items() if key not in attempted and job.get("tool_name") and not job.get("complete") and
                      (key in receipts or has_reader and
                       (job["status"] == "queued" or job.get("retry_at_epoch", 0) <= time.time()))]
        if not candidates:
            break
        job = candidates[0]
        attempted.add(job["job_id"])
        used += 1
        job["attempts"] += 1
        job["last_attempt_at"] = collector.at
        try:
            if job["job_id"] in receipts:
                receipt = receipts[job["job_id"]]
                raw = receipt.get("payload") if isinstance(receipt, Mapping) and "payload" in receipt else receipt
            else:
                raw = read_page(job["tool_name"], copy.deepcopy(job["args"]), job["account_ref"])
            digest = collector.retain(job, raw)
            if job["job_id"] in receipts and isinstance(receipt, Mapping) and receipt.get("source_ref"):
                collector.events[-1]["source_ref"]["native_receipt"] = copy.deepcopy(receipt["source_ref"])
            values = list(_response_values(_unwrap(raw)))
            keys = _collection_keys(job)
            if keys and not any(_has_collection(value, keys) for value in values):
                raise ValueError("native_service_unrecognized_collection")
            for value in values:
                collector.continuation(job, value)
                collector.time_partition(job, value)
                collector.successors(job, value)
            job.update(status="observed", complete=True, observed_at=collector.at,
                       response_envelope_sha256=digest, unread_regions=[], retry_at_epoch=None)
        except Exception as error:
            # Never print a connector exception's text: it can contain secret
            # values. The exact native response, when returned, is encrypted by
            # Store through the event retained before traversal.
            job.update(status="pending_recovery", complete=False, error_code=type(error).__name__,
                       unread_regions=["authenticated native read or response traversal recovery pending"],
                       retry_at_epoch=time.time() + min(3600, 30 * 2 ** min(job["attempts"], 7)),
                       alternate_reader="recover intended installed connector/authentication; existing shared secure reference facility and provider SDK/native harness")
    coverage_rows = []
    for root in collector.state["roots"].values():
        related = [job for job in jobs.values() if job["service"] == root["service"] and job["account_ref"] == root["account_ref"]]
        pending = [job for job in related if not job["complete"]]
        coverage_rows.append({"source": "service_activity", "service": root["service"], "account_ref": root["account_ref"],
                              "status": "pending_recovery" if any(job["status"] == "pending_recovery" for job in pending) else "backfilling" if pending else "observed",
                              "complete": not pending, "scope": SCOPES.get(root["service"], ["all available activity and full contents"]),
                              "jobs": len(related), "pages_read": sum(job["complete"] for job in related),
                              "pending_reads": sum(bool(job["tool_name"]) for job in pending),
                              "pending_recovery_scopes": sum(job["status"] == "pending_recovery" for job in pending),
                              "observed_at": collector.at,
                              "unread_regions": [{"job_id": job["job_id"], "scope": job["scope"], "status": job["status"], "alternate_reader": job.get("alternate_reader")} for job in pending]})
    # Each account refreshes after its own executable historical queue drains.
    # Another account's backfill or failed reader must not freeze this account.
    # Recovery scopes stay visible and are never erased by polling. Older
    # checkpoints share one deadline; migrate it once into the account roots.
    executable_scopes = {(job["service"], job["account_ref"]) for job in jobs.values()
                         if job.get("tool_name") and not job["complete"]}
    now_epoch = time.time()
    ready_roots = []
    for root in collector.state["roots"].values():
        root.setdefault("next_poll_epoch", collector.state.get("next_poll_epoch", 0))
        if ((root["service"], root["account_ref"]) not in executable_scopes and
                now_epoch >= root["next_poll_epoch"]):
            ready_roots.append(root)
    if ready_roots:
        collector.state["cycle"] += 1
        collector.active_cycle = collector.state["cycle"]
        for root in ready_roots:
            collector.bootstrap(root["service"], root["account_ref"])
            root["next_poll_epoch"] = now_epoch + float(config.get("poll_interval_seconds", 300))
    if collector.state["roots"]:
        collector.state["next_poll_epoch"] = min(root["next_poll_epoch"]
                                                for root in collector.state["roots"].values())
    pending = [copy.deepcopy(job) for job in jobs.values() if not job["complete"]]
    return {"events": collector.events, "coverage": {"source": "service_activity", "observed_at": collector.at,
            "complete": not pending, "services": len({root["service"] for root in collector.state["roots"].values()}),
            "accounts": len(collector.state["roots"]), "pages_read_this_cycle": used, "rows": coverage_rows,
            "pending_reads": len(pending), "sampling": False, "full_source_retained": True},
            "state": collector.state, "checkpoints": collector.state, "sources": collector.sources,
            "pending_native_reads": pending}


__all__ = ["collect_service_activity", "SCOPES"]
