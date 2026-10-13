from __future__ import annotations
import csv,io,json,tempfile,threading,unittest,urllib.error,urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer
import app

CFG={'schema':app.SCHEMA,'routes':[{'service':'plumbing','area':'north','calendar':'north-plumb'}],'slots':[{'id':'s1','calendar':'north-plumb','start':'2026-09-09T09:00:00-04:00'},{'id':'s2','calendar':'north-plumb','start':'2026-09-09T10:00:00-04:00'}]}
def lead(ref='form-1',slot='s1',consent=True,area='north'):
    return {'source_ref':ref,'name':'Synthetic Taylor','email':'taylor@example.invalid','phone':'','service':'plumbing','area':area,'consent':consent,'requested_slot':slot}
class T(unittest.TestCase):
    def setUp(self): self.t=tempfile.TemporaryDirectory(); self.d=app.Desk(Path(self.t.name)/'x.db',CFG)
    def tearDown(self): self.t.cleanup()
    def test_book_and_replay_once(self):
        a=self.d.intake(lead()); self.assertEqual(a['status'],'BOOKED'); self.assertEqual(a['booking_slot'],'s1'); self.assertTrue(self.d.intake(lead())['replayed']); self.assertEqual(len(self.d.state()['leads']),1); self.assertEqual(self.d.state()['draft_count'],1)
    def test_source_ref_conflict(self):
        self.d.intake(lead()); bad=lead(); bad['name']='Changed'
        with self.assertRaisesRegex(app.DeskError,'different payload'): self.d.intake(bad)
    def test_unavailable_returns_alternative(self):
        self.d.intake(lead('a','s1')); b=self.d.intake(lead('b','s1')); self.assertEqual(b['status'],'AWAITING_SLOT'); self.assertEqual([x['id'] for x in b['alternatives']],['s2'])
    def test_no_consent_or_area_never_drafts_or_books(self):
        a=self.d.intake(lead('a','s1',False)); b=self.d.intake(lead('b','s1',True,'south')); self.assertIsNone(a['reply_draft']); self.assertIsNone(b['reply_draft']); self.assertIsNone(a['booking_slot']); self.assertIsNone(b['booking_slot']); self.assertEqual(self.d.state()['followup_count'],2)
    def test_manual_booking_and_restart(self):
        a=self.d.intake(lead('a','')); self.assertEqual(a['status'],'AWAITING_SLOT'); self.d.book('a','s2'); d2=app.Desk(self.d.db_path,CFG); self.assertEqual(d2.book('a','s2')['booking_slot'],'s2'); self.assertTrue(d2.book('a','s2')['replayed'])
    def test_concurrent_slot_exactly_one(self):
        out=[]
        def f(ref):
            try: out.append(('ok',self.d.intake(lead(ref,'s1'))['booking_slot']))
            except Exception as e: out.append(('err',type(e).__name__))
        ts=[threading.Thread(target=f,args=(x,)) for x in ('a','b')]
        [x.start() for x in ts]; [x.join() for x in ts]
        self.assertEqual(sum(v=='s1' for k,v in out if k=='ok'),1); self.assertEqual(len(self.d.state()['leads']),2)
    def test_crm_unique(self):
        self.d.intake(lead()); rows=list(csv.DictReader(io.StringIO(self.d.crm_csv()))); self.assertEqual(len(rows),1); self.assertEqual(rows[0]['source_ref'],'form-1')
    def test_strict_input(self):
        x=lead(); x['consent']='true'
        with self.assertRaisesRegex(app.DeskError,'boolean'): self.d.intake(x)
        with self.assertRaises(app.DeskError): self.d.intake([])
    def test_checked_in_demo_fixture(self):
        root=Path(__file__).resolve().parent; cfg=app.load_config(root/'demo_config.json'); d=app.Desk(Path(self.t.name)/'demo.db',cfg); payload=json.loads((root/'demo_intake.json').read_text()); got=d.intake(payload); self.assertEqual(got['booking_slot'],'north-0900'); self.assertIn('DRAFT',got['reply_draft'])
    def test_real_http(self):
        srv=ThreadingHTTPServer(('127.0.0.1',0),app.handler_for(self.d)); th=threading.Thread(target=srv.serve_forever); th.start()
        try:
            base=f'http://127.0.0.1:{srv.server_address[1]}'; raw=json.dumps(lead()).encode(); req=urllib.request.Request(base+'/intake',data=raw,headers={'Content-Type':'application/json'},method='POST')
            got=json.load(urllib.request.urlopen(req)); self.assertEqual(got['booking_slot'],'s1'); state=json.load(urllib.request.urlopen(base+'/state')); self.assertEqual(len(state['leads']),1); self.assertIn('form-1',urllib.request.urlopen(base+'/crm.csv').read().decode())
        finally: srv.shutdown(); srv.server_close(); th.join()
if __name__=='__main__': unittest.main()
