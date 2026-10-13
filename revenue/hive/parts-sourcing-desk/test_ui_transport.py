"""Execute the exact index.html api/write functions in Node against real HTTP/SQLite.

This checks UI transport composition, not native Chromium navigation.
"""
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from parts_desk import Desk, make_server
from test_parts_desk import item, job


class UITransportCase(unittest.TestCase):
    def test_speaker_named_form_fields_are_not_html_required(self):
        import re

        html = Path(__file__).with_name("index.html").read_text()
        speaker = re.compile(
            r"(?:name|id)\s*=\s*['\"]?(?:from|actor(?:_id)?|identity|claim|seat|memory|"
            r"is_language_model|model|harness|tools|resources)\b",
            re.I,
        )
        tags = re.findall(r"<(?:input|select|textarea)\b[^>]*>", html, re.I)
        self.assertGreater(len(tags), 0)
        speaker_tags = [tag for tag in tags if speaker.search(tag)]
        self.assertGreater(len(speaker_tags), 0)
        for tag in speaker_tags:
            self.assertIsNone(re.search(r"\brequired\b", tag, re.I), tag)

    @unittest.skipUnless(shutil.which("node"), "Node is needed for the UI transport composition test")
    def test_exact_javascript_write_functions_with_live_http(self):
        html = Path(__file__).with_name("index.html").read_text()
        code = html[html.index("let pending = new Map();"):html.index("async function run(action)")]
        with tempfile.TemporaryDirectory() as work:
            desk = Desk(Path(work) / "store.sqlite3")
            server = make_server(desk, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                setup = "const base=" + json.dumps(f"http://127.0.0.1:{server.server_port}") + ";\n"
                setup += "const example=" + json.dumps(item()) + ";\nconst job=" + json.dumps(job()) + ";\n"
                setup += """
const nativeFetch=globalThis.fetch;
let loseReply=false;
globalThis.fetch=async (url,options)=>{
  const response=await nativeFetch(new URL(url,base),options);
  if(loseReply){loseReply=false;await response.text();throw new Error('SIMULATED_LOST_RESPONSE_AFTER_REAL_COMMIT');}
  return response;
};
"""
                scenario = """
let assertions=0;
function check(value,name){if(!value)throw new Error(name);assertions++;}
await write('/api/catalog/import',{items:[example]});
let requestBody={data:job};
loseReply=true;
try{await write('/api/requests',requestBody);throw new Error('expected lost response');}
catch(e){check(e.message==='SIMULATED_LOST_RESPONSE_AFTER_REAL_COMMIT','lost response retained');}
let req=await write('/api/requests',requestBody);
check((await api('/api/state')).requests.length===1,'retry created no duplicate');
check(pending.size===0,'completed retry clears pending key');
req=await write(`/api/requests/${req.id}/options`,{revision:req.revision,catalog_id:example.id});
const option=req.options[0].id;
check(req.options[0].effective_fit==='unreviewed','alias not treated as fit');
req=await write(`/api/options/${option}/review`,{revision:req.revision,fit:'compatible',technician:'Synthetic reviewer',note:'Synthetic source page and serial reviewed'});
const draftBody={revision:req.revision,option_id:option};
const pair=await Promise.all([write(`/api/requests/${req.id}/orders`,draftBody),write(`/api/requests/${req.id}/orders`,draftBody)]);
check(pair[0].orders[0].id===pair[1].orders[0].id,'concurrent clicks share one handoff');
req=pair[0];let order=req.orders[0];
check(order.document.total_before_tax==='29.00','initial cents');
req=await write(`/api/orders/${order.id}`,{revision:order.revision,quantity:'3',unit_price:'13.25',shipping:'',notes:'Manual collection'});
check(req.orders[0].document.total_before_tax===null,'unknown shipping');
order=req.orders[0];
req=await write(`/api/orders/${order.id}`,{revision:order.revision,shipping:'2.10'});
check(req.orders[0].document.total_before_tax==='41.85','exact edited cents');
order=req.orders[0];
req=await write(`/api/orders/${order.id}/placed`,{revision:order.revision,supplier_reference:'SYNTHETIC-NODE-1'});
check(req.orders[0].status==='placed','manual external reference');
req=await write(`/api/requests/${req.id}`,{revision:req.revision,data:{...job,serial:'changed'}});
check(req.options[0].effective_fit==='stale','changed equipment stales fit');
check(req.orders[0].document.total_before_tax==='41.85','historical total retained');
const handoff=await (await fetch(`/api/orders/${order.id}/handoff.txt`)).text();
check(handoff.includes('SYNTHETIC-NODE-1')&&handoff.includes('41.85'),'actual handoff bytes');
check((await api('/api/export')).tables.orders.length===1,'actual export');
console.log(JSON.stringify({assertions,request_id:req.id,order_id:order.id,total:req.orders[0].document.total_before_tax}));
"""
                script = Path(work) / "transport.mjs"
                script.write_text(setup + code + scenario)
                run = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=15)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                result = json.loads(run.stdout.strip())
                self.assertEqual(result["assertions"], 13)
                self.assertEqual(result["total"], "41.85")
                saved = Desk(desk.database).request(result["request_id"])
                self.assertEqual(len(saved["orders"]), 1)
                self.assertEqual(saved["orders"][0]["document"]["supplier_reference"], "SYNTHETIC-NODE-1")
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
