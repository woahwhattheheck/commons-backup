"""Shared, read-only adapter for the existing equipment catalog and fresh CLIs."""
from __future__ import annotations
import json
import os
import urllib.request
from .peer_server import TOOLS

class TelemetryEquipment:
    def __init__(self, base_url=None):
        self.base_url=(base_url or os.environ.get("COMMONS_SWARM_TELEMETRY_URL") or "http://127.0.0.1:8893").rstrip("/")
    def tools(self):
        return [{**t,"name":"swarm_telemetry_"+t["name"]} for t in TOOLS if t["name"]!="get_dashboard_summary"]
    def call(self,name,arguments):
        prefix="swarm_telemetry_"
        if name not in {t["name"] for t in self.tools()}:raise ValueError("Unknown telemetry read")
        req=urllib.request.Request(self.base_url+"/api/telemetry/tools/call",
            data=json.dumps({"name":name[len(prefix):],"arguments":arguments}).encode(),
            headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)

if __name__=="__main__":
    import sys
    request=json.load(sys.stdin)
    print(json.dumps(TelemetryEquipment().call(request["name"],request.get("arguments",{})),ensure_ascii=False))
