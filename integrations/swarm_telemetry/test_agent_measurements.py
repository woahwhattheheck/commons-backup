"""Discriminating agent-tool cases; real-source inventory is validated separately."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from threading import Thread
from urllib.request import Request,urlopen
from .peer_store import PeerStore as Store
from .agent_inventory import retain_inventory
from .agent_queries import roster,measurements
from .peer_server import PeerServer as Server
from .equipment import TelemetryEquipment

class AgentMeasurements(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/"telemetry.sqlite3",key_loader=lambda _:bytes(range(64)))
    def tearDown(self):self.tmp.cleanup()
    def inventory(self,rows):
        return retain_inventory(self.store,"chatgpt-native-catalog",rows,
            {"read_at":"2026-10-06T06:00:00Z","source_watermark":"2026-10-05T10:00:00Z",
             "cached_provider_inventory":True,"inventory_complete":True},raw=rows)
    def test_all_accounts_pagination_and_container_exclusion(self):
        rows=[{"session_id":f"gpt-{i:04}","harness":"chatgpt","provider":"openai","account_ref":"account-a" if i%2 else "account-b", "created_at":"2026-10-03T05:00:00Z"} for i in range(1107)]
        self.inventory(rows)
        # A source-container label cannot be counted as an agent; two roads for
        # one Chat mode seat cannot manufacture another identity.
        self.store.ingest([{"event_id":"slack-thread","source":"slack","session_id":"slack-container","harness":"slack"},
                           {"event_id":"same-gpt","source":"native","session_id":"gpt-0000","harness":"chatgpt"}])
        ids=[];page=roster(self.store,harness="chatgpt",limit=89)
        while True:
            ids.extend(r["identity"] for r in page["peers"])
            if not page["has_more"]:break
            page=roster(self.store,harness="chatgpt",limit=89,cursor=page["next_cursor"])
        self.assertEqual(len(ids),1107);self.assertEqual(len(set(ids)),1107)
        self.assertEqual(roster(self.store,session_id="slack-container")["total_known"],0)
        self.assertFalse(page["corpus_complete"])
        page=roster(self.store,harness="chatgpt",limit=89)
        with self.assertRaises(ValueError):roster(self.store,harness="codex",cursor=page["next_cursor"])
    def test_expired_and_future_execution_are_unknown(self):
        peers=[{"session_id":sid,"harness":"chatgpt","status":"executing","basis":"runtime_observation","observed_at":at}
               for sid,at in [("expired","2000-01-01T00:00:00Z"),("future","2999-01-01T00:00:00Z")]]
        self.store.state("census",{"peers":peers})
        result=measurements(self.store)
        self.assertEqual(result["current_runtime"]["executing_observed_lower_bound"],0)
        self.assertIsNone(result["current_runtime"]["swarm_executing_total"])
        self.assertTrue(all(x["status"]=="unknown" for x in roster(self.store)["peers"]))
        self.assertIn("lower bound",result["peer_note"]);self.assertIn("improve",result["peer_note"])
    def test_real_dates_and_cached_watermark_are_not_refreshed(self):
        self.inventory([{"session_id":"boundary","harness":"chatgpt","created_at":"2026-10-03T04:00:00.123Z"}])
        result=roster(self.store,since="2026-10-03T04:00:00Z",until="2026-10-03T04:00:01Z")
        self.assertEqual(result["total_known"],1)
        self.assertEqual(result["inventory_coverage"][0]["source_watermark"],"2026-10-05T10:00:00Z")
        self.assertFalse(result["inventory_coverage"][0]["current_provider_inventory_verified"])
    def test_http_and_shared_adapter(self):
        self.inventory([{"session_id":"shared-read","harness":"chatgpt","provider":"openai"}])
        server=Server(("127.0.0.1",0),self.store);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            adapter=TelemetryEquipment("http://127.0.0.1:"+str(server.server_port))
            result=adapter.call("swarm_telemetry_list_peers",{"harness":"chatgpt"})
            self.assertEqual(result["total_known"],1)
            body=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_swarm_measurements","arguments":{}}}).encode()
            with urlopen(Request(adapter.base_url+"/mcp",data=body,headers={"Content-Type":"application/json"})) as response:reply=json.load(response)
            self.assertNotIn("error",reply);self.assertIn("lower bound",json.dumps(reply))
        finally:server.shutdown();server.server_close();thread.join()
    def test_provider_requests_and_processes_stay_separate(self):
        self.store.state("census",{"peers":[{"session_id":"req-1","peer_id":"TESSERA","harness":"shared-equipment","provider":"google","status":"running","source_refs":["gemini_get_request"],"observed_at":"2000-01-01T00:00:00Z"},
            {"session_id":"process:123","harness":"codex","status":"unknown","metadata":{"pid":123},"observed_at":"2000-01-01T00:00:00Z"}]})
        result=measurements(self.store)
        self.assertEqual(result["historical"]["known_agent_instances"],0)
        self.assertEqual(len(result["runtime_source_partitions"]["provider_observations"]),1)
        self.assertEqual(len(result["runtime_source_partitions"]["process_presence"]),1)

if __name__=="__main__":unittest.main()
