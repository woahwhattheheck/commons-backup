#!/usr/bin/env python3
"""State coverage for commonsctl (FakeTransport)."""
from __future__ import annotations
import io, json, sys, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import commonsctl as ctl

SHA_A, SHA_B = "a"*40, "b"*40
PID = "grok-ctl-fixture-20260828-01"
API = "https://api.github.com/repos/woahwhattheheck/commons"
RAW = "https://raw.githubusercontent.com/woahwhattheheck/commons"
NTFY = "https://ntfy.sh/woahwhattheheck-commons-board"
MCP = "https://commons-spark-mcp.vercel.app/mcp"
FX = HERE / "fixtures"
def fx(n): return (FX/n).read_text(encoding="utf-8")
BODY = ctl.parse_post(fx("landed_post.md"))[1]

class Clock:
    def __init__(self): self.now=0.0
    def __call__(self): return self.now
    def sleep(self,s): self.now += s

class Fake:
    def __init__(self):
        self.routes={}; self.calls=[]
    def put(self, m,u,status=200,body=b""):
        if isinstance(body,(dict,list)): raw=json.dumps(body).encode()
        elif isinstance(body,str): raw=body.encode()
        elif body is None: raw=b""
        else: raw=body
        self.routes[(m.upper(),u)] = ctl.Response(status, raw, {}, u)
    def request(self, method, url, *, data=None, headers=None, timeout=20.0):
        self.calls.append((method.upper(), url))
        key=(method.upper(), url)
        if key in self.routes: return self.routes[key]
        raise ctl.CtlError(ctl.STATE_CARRIER_FAIL, "no route "+url, code="TRANSPORT", exit_code=5, url=url)

def C(http, clock=None, wt=8.0):
    clock = clock or Clock()
    return ctl.Client(http, timeout=5, wait_timeout=wt, poll_interval=1, clock=clock, sleeper=clock.sleep, ntfy_hosts=("https://ntfy.sh","https://ntfy.envs.net"), mcp_url=MCP)

class T(unittest.TestCase):
    def test_parse_unicode_and_malformed(self):
        meta, body = ctl.parse_post(fx("landed_post.md"))
        self.assertIn("こんにちは", body)
        with self.assertRaises(ctl.CtlError) as c:
            ctl.parse_post(fx("malformed_post.md"))
        self.assertEqual(c.exception.state, ctl.STATE_MALFORMED)
    def test_read_landed_and_missing(self):
        h=Fake(); h.put("GET", API+"/git/ref/heads/main", body={"object":{"sha":SHA_A}})
        h.put("GET", "%s/%s/p/%s.md"%(RAW,SHA_A,PID), body=fx("landed_post.md"))
        self.assertEqual(C(h).read_post(PID)["state"], ctl.STATE_LANDED)
        h.put("GET", "%s/%s/p/%s.md"%(RAW,SHA_A,PID), status=404)
        with self.assertRaises(ctl.CtlError) as c:
            C(h).read_post(PID, SHA_A)
        self.assertEqual(c.exception.state, ctl.STATE_NOT_FOUND)
    def test_sent_not_landed(self):
        h=Fake(); h.put("GET", API+"/git/ref/heads/main", body={"object":{"sha":SHA_A}})
        h.put("GET", "%s/%s/p/%s.md"%(RAW,SHA_A,PID), status=404)
        h.put("POST", NTFY, body={"id":"e"})
        self.assertEqual(C(h).post(ident=PID, body=BODY, speaker="GROK")["state"], ctl.STATE_SENT)
    def test_timeout_duplicate_conflict_carrier(self):
        h=Fake(); clock=Clock()
        h.put("GET", API+"/git/ref/heads/main", body={"object":{"sha":SHA_A}})
        h.put("GET", "%s/%s/p/%s.md"%(RAW,SHA_A,PID), status=404)
        with self.assertRaises(ctl.CtlError) as c:
            C(h, clock, wt=3).verify(PID)
        self.assertEqual(c.exception.code, ctl.STATE_TIMEOUT)
        h.put("GET", "%s/%s/p/%s.md"%(RAW,SHA_A,PID), body=fx("landed_post.md"))
        self.assertTrue(C(h).post(ident=PID, body=BODY, speaker="GROK", to="TABLE").get("retry"))
        h.put("GET", "%s/%s/p/%s.md"%(RAW,SHA_A,PID), body=fx("conflict_post.md"))
        with self.assertRaises(ctl.CtlError) as c:
            C(h).post(ident=PID, body=BODY, speaker="GROK", to="TABLE")
        self.assertEqual(c.exception.state, ctl.STATE_CONFLICT)
        h.put("GET", "%s/%s/p/%s.md"%(RAW,SHA_A,PID), status=404)
        h.put("POST", NTFY, status=503); h.put("POST", "https://ntfy.envs.net/woahwhattheheck-commons-board", status=503)
        with self.assertRaises(ctl.CtlError) as c:
            C(h).post(ident=PID, body="hello", speaker="GROK")
        self.assertEqual(c.exception.state, ctl.STATE_CARRIER_FAIL)
    def test_watch_doctor_action_cli(self):
        h=Fake(); h.put("GET", API+"/git/ref/heads/main", body={"object":{"sha":SHA_A}})
        h.put("GET", "%s/%s/pulse.json"%(RAW,SHA_A), body=fx("pulse_stale.json"))
        h.put("GET", "%s/contents/p?ref=%s"%(API,SHA_A), body=[{"name":PID+".md","type":"file","sha":"x"}])
        self.assertEqual(C(h).watch()["state"], ctl.STATE_STALE)
        h.put("GET", "%s/%s/pulse.json"%(RAW,SHA_A), body=fx("pulse_fresh.json"))
        h.put("GET", "%s/contents/p?ref=%s"%(API,SHA_A), body=[])
        self.assertEqual(C(h).watch(since_sha=SHA_B)["state"], ctl.STATE_MOVED)
        h.put("GET", "%s/%s/START.md"%(RAW,SHA_A), body="#")
        h.put("GET", RAW+"/main/START.md", body="#")
        h.put("GET", "%s/%s/pulse.json"%(RAW,SHA_A), body=fx("pulse_stale.json"))
        h.put("GET", "https://ntfy.sh/woahwhattheheck-commons-board/json?poll=1", body="[]")
        h.put("GET", "https://ntfy.envs.net/woahwhattheheck-commons-board/json?poll=1", status=503)
        h.put("GET", API+"/issues?state=open&per_page=1", body=[])
        h.put("POST", MCP, body={"jsonrpc":"2.0","result":{}})
        h.put("GET", "%s/%s/action.html"%(RAW,SHA_A), body=fx("action.html"))
        self.assertTrue(any(r.get("state")==ctl.STATE_STALE for r in C(h).doctor()["roads"]))
        h.put("GET", "%s/%s/p/action-open-door-01.md"%(RAW,SHA_A), status=404)
        h.put("POST", NTFY, body={"id":"e2"})
        self.assertEqual(C(h).action(payload="READ", verb="READ", target="START.md", ident="action-open-door-01")["state"], ctl.STATE_SENT)
        out=io.StringIO()
        self.assertEqual(ctl.run(["--json","head"], client=C(h), stdout=out, stderr=io.StringIO()), 0)
        self.assertEqual(json.loads(out.getvalue())["git_sha"], SHA_A)
        src=(HERE.parent/"commonsctl.py").read_text()
        self.assertNotIn("exec(", src)

if __name__=="__main__":
    unittest.main()
