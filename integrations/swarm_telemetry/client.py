"""Optional reads and nonblocking observation; never required for execution."""
from __future__ import annotations
import json
import urllib.request
from queue import Queue,Full,Empty
from threading import Thread

class Client:
    def __init__(self,base_url="http://127.0.0.1:8893",timeout=10):
        self.base_url=base_url.rstrip("/")
        self.timeout=timeout
    def call(self,name,arguments=None):
        req=urllib.request.Request(self.base_url+"/api/telemetry/tools/call",data=json.dumps({"name":name,"arguments":arguments or {}}).encode(),headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req,timeout=self.timeout) as response: return json.load(response)

class Observer:
    """Best-effort optional observer; emit() never waits for network or disk."""
    def __init__(self,base_url="http://127.0.0.1:8893",queue_size=2048,batch_size=64):
        self.base_url=base_url.rstrip("/")
        self.batch_size=max(1,int(batch_size))
        self.queue=Queue(maxsize=queue_size)
        self.dropped=0
        self.failed=0
        Thread(target=self._deliver,daemon=True,name="optional-telemetry-observer").start()
    def emit(self,event):
        # Capture once before the caller can reuse mutable event fields.
        try: captured=json.dumps(event)
        except Exception: self.failed+=1; return False
        try: self.queue.put_nowait(captured); return True
        except Full: self.dropped+=1; return False
    def _deliver(self):
        while True:
            events=[self.queue.get()]
            # A lone event goes immediately. Drain only the already available
            # burst; never wait for another event to fill a batch.
            while len(events)<self.batch_size:
                try: events.append(self.queue.get_nowait())
                except Empty: break
            try:
                body='{"events":['+','.join(events)+']}'
                req=urllib.request.Request(self.base_url+"/api/telemetry/observe",data=body.encode(),headers={"Content-Type":"application/json"})
                with urllib.request.urlopen(req,timeout=2) as response: receipt=json.loads(response.read(1024))
                if not isinstance(receipt,dict) or receipt.get("ok") is not True:
                    raise ValueError("Observation was not acknowledged")
                # A successful HTTP response can still reject a full queue.
                counts=[receipt["queued"]] if "queued" in receipt else [receipt.get("inserted"),receipt.get("duplicates")]
                if any(type(count) is not int or count<0 for count in counts):
                    raise ValueError("Invalid observation acknowledgment")
                accepted=sum(counts)
                if accepted>len(events): raise ValueError("Invalid observation acknowledgment")
                self.failed+=len(events)-accepted
            except Exception: self.failed+=len(events)
            finally:
                for _ in events: self.queue.task_done()
