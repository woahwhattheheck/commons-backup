"""Command center tools shared through every existing equipment carrier."""
import os
from pathlib import Path

class CommandCenterEquipment:
    def __init__(self, center=None):
        self._center = center
    @property
    def center(self):
        if self._center is None:
            from .core import CommandCenter
            state = Path(os.environ.get("COMMONS_COMMAND_CENTER_STATE", str(Path.home() / ".commons" / "command-center")))
            self._center = CommandCenter(state, gateway_url=os.environ.get("COMMONS_COMMAND_CENTER_GATEWAY", "http://127.0.0.1:8878"))
        return self._center
    def tools(self):
        from .context_view import INPUT_SCHEMA
        session_schema = {
            "type": "object", "required": ["id"], "additionalProperties": False,
            "properties": {
                "id": {"type": "string", "description": "Stable ID for the existing session."},
                **{key: {"type": ["string", "null"]} for key in (
                    "label", "url", "provider", "model", "workspace", "observed_at",
                    "status", "objective", "resource_id", "expires_at", "notes")},
                "cpu": {"type": ["number", "string", "object", "null"], "description": "Observed CPU capacity, including structured vCPU metadata."},
                **{key: {"type": ["number", "null"]} for key in (
                    "ram_gib", "disk_gib", "disk_free_gib")},
                "gpu": {"type": ["string", "number", "object", "array", "null"]},
                "origin": {"type": ["string", "object", "null"]},
                **{key: {"type": ["string", "array", "object", "null"]} for key in (
                    "capabilities", "tools", "egress", "artifact_transport", "cost_source")},
                "lifetime": {"type": ["string", "number", "object", "null"]},
            },
        }
        budget_schema = {
            "type": "object", "required": ["id"], "additionalProperties": False,
            "properties": {
                "id": {"type": "string", "description": "Stable ID for this budget, balance, or quota observation."},
                **{key: {"type": ["number", "null"], "minimum": 0} for key in (
                    "limit", "used", "balance", "remaining", "committed")},
                **{key: {"type": ["string", "null"]} for key in (
                    "label", "unit", "period", "observed_at", "source_url",
                    "provider", "kind", "currency", "notes")},
            },
        }
        runtime_schema = {
            "type": "object", "required": ["id", "gateway_url"], "additionalProperties": False,
            "properties": {
                "id": {"type": "string", "description": "Stable ID for the existing shared gateway."},
                "label": {"type": "string"},
                "gateway_url": {"type": "string", "description": "Existing HTTP(S) gateway base URL exposing /v1/tools and /v1/tools/call."},
            },
        }
        source_schema = {
            "type": "object", "required": ["id", "provider", "observed_at", "coverage"],
            "description": "Selected source metadata, explicit stable scope and coverage; never raw bodies or credential values.",
            "properties": {
                **{key: {"type": "string"} for key in ("id", "provider", "observed_at")},
                "coverage": {"type": "object", "required": ["complete"], "properties": {
                    "complete": {"type": "boolean"}, "pagination_remaining": {}, "notes": {}}, "additionalProperties": False},
                **{key: {} for key in ("label", "sync_mode", "activity_as_of", "scope", "status", "error", "stale_after_seconds", "metadata", "refs", "url")},
            }, "additionalProperties": False,
        }
        specs = [
            ("context", "Read selective cached context, not the full feed. Filter first, page 20 by default and reuse unchanged revisions. Optional order=seat with a public seat label varies discovery; order=oldest surfaces older activity. Neither reserves work. Exact items remain reachable to every peer; owner is a provider-reported label. source_health=true adds an all-cached-source envelope from the shared summary without changing the default page or its revision.", {**INPUT_SCHEMA["properties"], "source_health": {"type": "boolean", "description": "When true, attach all-cached-source coverage from the shared summary. Omitted or false preserves the default context response."}}, []),
            ("context_item", "Read one exact stored normalized observation by source_id and item_id. No provider requests or mutations; independent of context filters.", {"source_id": {"type": "string", "minLength": 1, "maxLength": 2000}, "item_id": {"type": "string", "minLength": 1, "maxLength": 2000}}, ["source_id", "item_id"]),
            ("mail", "Read cached mail threads, last-observed waiting state, priority and next action, explicit deadlines, and sync coverage. No inference, provider reads, or sending.", {"limit": {"type": "integer", "minimum": 1, "maximum": 200}, "offset": {"type": "integer", "minimum": 0}, "query": {"type": "string", "maxLength": 240}, "mode": {"type": "string", "enum": ["all", "waiting_on_us", "waiting_on_them", "unknown", "unread", "overdue"]}}, []),
            ("summary", "Compact Deathstar observation: cache-only work, freshness, coverage debt, lower-bound merge throughput, payment states and provider cooldowns. Never triggers provider calls.", {}, []),
            ("swarm_state", "Read the existing PR queue and recorded review metadata before building or integrating. Includes stale-state warnings and records usage. This is an observation, not merge authority or a new review requirement; follow current owner rules in ground/SWARM_ORDER.md.", {"refresh": {"type": "boolean"}}, []),
            ("state", "Read the entire operation: canonical resources, service tools, accounts, observed fleet, budgets, focus, and operation outcomes.", {"refresh": {"type": "boolean"}}, []),
            ("work_state", "Read connected work, source freshness and coverage, owner next actions, and direct refresh progress.", {"refresh": {"type": "boolean"}}, []),
            ("refresh_work", "Start one bounded read of configured GitHub and Slack sources, retaining previous observations during refresh. No model or new service is started.", {}, []),
            ("ingest", "Share selected work observations from an actual connector or native task road. Preserve provider timestamps, source scope, pagination and failures. Stable operation IDs make exact retries safe.", {"source": source_schema, "items": {"type": "array", "maxItems": 10000, "items": {"type": "object"}}}, ["source", "items"]),
            ("work_item", "Record owner priority, next action, or a prepared job against an exact observed work item. A prepared packet is not provider dispatch. Send expected_revision from a context row's owner_work_revision or exact item's owner_work.revision (zero if absent) to avoid overwriting a concurrent edit.", {"source_id": {"type": "string"}, "item_id": {"type": "string"}, "priority": {"type": ["string", "number", "null"]}, "next_action": {"type": ["string", "null"]}, "job": {"type": ["object", "null"]}, "expected_revision": {"type": "integer", "minimum": 0}}, ["source_id", "item_id"]),
            ("focus", "Set the shared objective and next action.", {"objective": {"type": "string"}, "next_action": {"type": "string"}}, ["objective"]),
            ("session", "Record an existing GPT, Claude, or other peer session and observed VM facts. Does not create a provider session.", {"session": session_schema}, ["session"]),
            ("budget", "Record an observed balance, quota, limit, or budget with its source and timestamp.", {"budget": budget_schema}, ["budget"]),
            ("runtime", "Register an existing shared tool gateway.", {"runtime": runtime_schema}, ["runtime"]),
            ("janny", "Assign limited housekeeping responsibility to an existing peer, without changing tool or credential access.", {"peer": {"type": "string"}}, ["peer"]),
            ("note", "Add an operational feed item with its original source link for shared visibility and reversible housekeeping.", {"title": {"type": "string"}, "body": {"type": "string"}, "source_url": {"type": "string"}, "source_ref": {"type": "string"}}, ["title", "body"]),
            ("moderate", "Hide or restore one item in the derived default feed with a reason, retaining its original.", {"event_id": {"type": "string"}, "hidden": {"type": "boolean", "description": "Desired derived-feed visibility: true hides the entry; false restores it."}, "action": {"type": "string", "description": "Legacy hide/restore alias; prefer hidden."}, "reason": {"type": "string"}}, ["event_id", "reason"]),
        ]
        result = []
        for name, description, properties, required in specs:
            if name not in {"state", "work_state", "refresh_work", "swarm_state", "summary", "mail", "context", "context_item"}:
                properties = {"operation_id": {"type": "string", "description": "Stable ID; repeat exact payload on retry."}, **properties}
                required = ["operation_id"] + required
            result.append({"name": "command_center_" + name, "description": description, "inputSchema": {"type": "object", "properties": properties, "required": required, "additionalProperties": False}})
        for tool in result:
            if tool["name"] == "command_center_moderate":
                tool["inputSchema"]["anyOf"] = [
                    {"required": ["hidden"]}, {"required": ["action"]}]
        from .swarm_tasks import tool as swarm_task_tool
        result.append(swarm_task_tool())
        from .provider_admission import tool as provider_admission_tool
        result.append(provider_admission_tool())
        return result
    def call(self, name, arguments):
        if name == "command_center_provider_admission":
            from .provider_admission import call
            return call(self.center, arguments)
        if name == "command_center_swarm_tasks":
            from .swarm_tasks import call
            return call(self.center, arguments)
        if name == "command_center_context":
            arguments = dict(arguments or {})
            opted = arguments.pop("source_health", False)
            if opted not in (False, True, None):
                raise ValueError("source_health must be a boolean when supplied")
            page = self.center.work_context(**arguments)
            if opted:
                from .context_health import with_source_health
                return with_source_health(self.center, page)
            return page
        if name == "command_center_context_item":
            return self.center.work_context_item(arguments.get("source_id"), arguments.get("item_id"))
        if name == "command_center_mail":
            return self.center.work_mail(arguments.get("limit", 100), arguments.get("offset", 0), arguments.get("query", ""), arguments.get("mode", "all"))
        if name == "command_center_summary":
            return self.center.work_summary()
        if name == "command_center_swarm_state":
            return self.center.swarm_state(refresh=bool(arguments.get("refresh", False)))
        if name == "command_center_work_state":
            return self.center.work_state(refresh=bool(arguments.get("refresh", False)))
        if name == "command_center_refresh_work":
            return self.center.refresh_work()
        if name == "command_center_ingest":
            return self.center.ingest_work(arguments)
        if name == "command_center_work_item":
            return {**self.center.update_work(arguments), "status": "completed"}
        if name == "command_center_state":
            from .telemetry import with_host
            return with_host(self.center, self.center.state(refresh=bool(arguments.get("refresh", False))))
        names = {"focus": "focus", "session": "sessions", "budget": "budgets", "runtime": "runtimes", "janny": "janny", "note": "feed", "moderate": "feed/moderate"}
        suffix = name.removeprefix("command_center_")
        if suffix not in names:
            raise ValueError("unknown command center tool")
        return self.center.mutate(names[suffix], arguments)

