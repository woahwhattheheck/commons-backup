"""Optional connected-route execution in the existing equipment gateway.

All calls use the existing catalog adapters and one private operation journal.
The public route catalog carries capability facts; it never carries private
requests, results, provider quota observations or secret values.
"""
from __future__ import annotations

import os
from pathlib import Path

from .outcomes import effect_uncertain, tool_failed
from .provider_io import EquipmentError, redacted


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROUTES = ROOT / "inventory/resources/connected_capability_observations.json"
ROUTER_TOOLS = frozenset({"connected_tool_run", "connected_tool_dispatch",
                          "connected_tool_resume", "connected_tool_status", "connected_tool_rail_health"})
SUCCESS_DECISIONS = frozenset({"DISPATCH", "COMPLETED", "AWAITING_PROVIDER_RESPONSE", "ROUTING", "RAIL_HEALTH"})


def _tool(name, description, properties, required):
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": properties,
                            "required": required, "additionalProperties": False}}


TOOLS = [
    _tool("connected_tool_run",
          "Execute a Free capability request through this gateway's existing tools. "
          "Reuses the stable operation ID, shared private journal and actual provider "
          "Retry-After feedback. Switches immediately to an untried compatible quota "
          "domain without sleeping or replaying accepted/uncertain writes. Direct tools remain available.",
          {"request": {"type": "object"}}, ["request"]),
    _tool("connected_tool_dispatch",
          "Persist the next connected capability dispatch in the shared private journal. "
          "For an external native binding, invoke exactly that dispatch and return its actual "
          "response with connected_tool_resume. Pending and completed IDs never remint calls.",
          {"request": {"type": "object"}}, ["request"]),
    _tool("connected_tool_resume",
          "Record the actual response for an outstanding connected capability dispatch. "
          "Shares provider cooldowns across gateway consumers and emits another dispatch "
          "only when the existing operation can continue safely.",
          {"operation_id": {"type": "string", "minLength": 1},
           "dispatch_id": {"type": "string", "minLength": 1},
           "response": {"type": "object"}}, ["operation_id", "dispatch_id", "response"]),
    _tool("connected_tool_rail_health",
          "Read typed per-quota-domain observations from this gateway\'s existing private journal. "
          "No operation ID, provider call or routing change. Past outcomes and expired "
          "cooldowns do not establish current health; unknown budgets stay unknown.",
          {}, []),
    _tool("connected_tool_status",
          "Read one connected capability operation and the shared quota-domain observations "
          "without calling a provider or rewriting the journal. Unknown allowance stays unknown.",
          {"operation_id": {"type": "string", "minLength": 1}}, ["operation_id"]),
]


class ConnectedToolEquipment:
    def __init__(self, catalog, *, routes_file=None, state_file=None):
        self.catalog = catalog
        self.routes_file = Path(routes_file) if routes_file is not None else DEFAULT_ROUTES
        configured = state_file or os.environ.get("COMMONS_CONNECTED_TOOL_STATE_FILE")
        self.state_file = Path(configured) if configured else (
            Path.home() / ".commons" / "connected-tool-runtime.json")

    def tools(self):
        return TOOLS.copy()

    def _router(self):
        # Import after services and its CombinedCatalog are initialized: the
        # router reuses services.plan_capability_fallback rather than forking it.
        from host.connected_tool_router import ConnectedToolRouter, load_routes
        return ConnectedToolRouter(load_routes(self.routes_file), self.state_file)

    def _invoke(self, dispatch):
        name = dispatch["tool"]
        if name in ROUTER_TOOLS:
            # Recursive router invocations are invalid bindings, not a peer
            # admission rule. Keep the original pending ID for reconciliation.
            raise EquipmentError("a connected route cannot invoke the router itself")
        return self.catalog.call(name, dispatch["arguments"])

    def call(self, name, arguments):
        try:
            if name not in ROUTER_TOOLS:
                raise EquipmentError("unknown connected execution tool: " + str(name))
            if not isinstance(arguments, dict):
                raise EquipmentError("connected execution arguments must be an object")
            router = self._router()
            if name == "connected_tool_run":
                result = router.run(arguments["request"], self._invoke)
            elif name == "connected_tool_dispatch":
                result = router.dispatch(arguments["request"])
            elif name == "connected_tool_resume":
                result = router.resume(arguments["operation_id"], arguments["dispatch_id"], arguments["response"])
            elif name == "connected_tool_rail_health":
                if arguments:
                    raise EquipmentError("connected_tool_rail_health takes no arguments")
                result = router.rail_health()
            else:
                operation_id = arguments["operation_id"]
                if not isinstance(operation_id, str) or not operation_id.strip():
                    raise EquipmentError("operation_id must be a nonempty string")
                result = router.status(operation_id)
            return {"isError": result["decision"] not in SUCCESS_DECISIONS or tool_failed(result),
                    "result": redacted(result), "uncertain": effect_uncertain(result)}
        except Exception as exc:
            return {"isError": True, "code": getattr(exc, "code", "connected_execution_failed"),
                    "error": type(exc).__name__, "message": redacted(str(exc)),
                    "uncertain": bool(getattr(exc, "uncertain", False))}
