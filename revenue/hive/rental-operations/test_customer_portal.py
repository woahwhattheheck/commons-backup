from __future__ import annotations
import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from fleet import FleetError
from customer_portal import CustomerPortal, make_server

START='2026-10-01T10:00:00Z'
END='2026-10-02T10:00:00Z'
TOKEN='a'*64
TOKEN2='b'*64

class CustomerPortalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Path(self.temp.name)/'fleet.sqlite'
        self.portal=CustomerPortal(self.db)
        self.asset=self.portal.core.command({
            'action':'save_asset','id':'lift-1','expected_revision':0,'name':'<img src=x onerror=alert(1)> Lift',
            'unit':'day','rate':'75.25','minimum_units':1,'booking_fee':'10.00','security_deposit':'200.00','notes':'operator secret'
        },'asset-fixture')['record']
    def tearDown(self): self.temp.cleanup()
    def payload(self, key='req-1', token=TOKEN, customer='Ada'):
        return {'request_key':key,'status_token':token,'asset_id':'lift-1','start':START,'end':END,'customer':customer,'contact':'ada@example.test','notes':'Need loading ramp'}
    def count(self,table):
        with sqlite3.connect(self.db) as db: return db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]

    def test_catalog_redacts_operator_and_conflict_metadata(self):
        self.portal.core.command({'action':'save_reservation','id':'existing','expected_revision':0,'asset_id':'lift-1','kind':'booking','start':START,'end':END,'customer':'Private Customer','contact':'private@example.test','notes':'private note'},'existing')
        cat=self.portal.catalog(START,END)
        self.assertEqual(len(cat['assets']),1)
        row=cat['assets'][0]
        self.assertFalse(row['available'])
        self.assertEqual(row['name'],'<img src=x onerror=alert(1)> Lift')
        for forbidden in ('conflicts','customer','contact','notes','reservations'):
            self.assertNotIn(forbidden,row)
        self.assertFalse(cat['reservation_created'])

    def test_pending_request_does_not_reserve_and_token_plaintext_is_not_stored(self):
        out=self.portal.submit(self.payload())
        self.assertEqual(out['status'],'pending')
        self.assertFalse(out['reservation_created'])
        self.assertEqual(self.count('reservations'),0)
        with sqlite3.connect(self.db) as db:
            token_hash,result=db.execute('SELECT token_hash,(SELECT result_json FROM customer_request_operations WHERE request_key=?) FROM customer_requests',( 'req-1',)).fetchone()
        self.assertNotEqual(token_hash,TOKEN)
        self.assertNotIn(TOKEN,result)

    def test_exact_retry_returns_same_request_changed_retry_fails(self):
        first=self.portal.submit(self.payload())
        second=self.portal.submit(self.payload())
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(self.count('customer_requests'),1)
        changed=self.payload(customer='Grace')
        with self.assertRaises(FleetError) as cm: self.portal.submit(changed)
        self.assertEqual(cm.exception.status,409)
        self.assertEqual(self.count('customer_requests'),1)

    def test_status_capability_is_generic_on_wrong_id_or_token(self):
        out=self.portal.submit(self.payload())
        self.assertEqual(self.portal.status(out['id'],TOKEN)['id'],out['id'])
        for identifier,token in ((out['id'],TOKEN2),('not-real',TOKEN)):
            with self.subTest(identifier=identifier):
                with self.assertRaises(FleetError) as cm: self.portal.status(identifier,token)
                self.assertEqual(cm.exception.status,404)
                self.assertEqual(str(cm.exception),'Request not found.')

    def test_approval_creates_one_canonical_reservation_and_replay_is_stable(self):
        req=self.portal.submit(self.payload())
        operations_before=self.count('operations')
        first=self.portal.approve(req['id'])
        second=self.portal.approve(req['id'])
        self.assertEqual(first['status'],'accepted')
        self.assertTrue(first['reservation_created'])
        self.assertEqual(first['reservation_id'],second['reservation_id'])
        self.assertEqual(self.count('reservations'),1)
        self.assertEqual(self.count('operations'),operations_before+1)

    def test_asset_term_change_blocks_approval_without_reservation(self):
        req=self.portal.submit(self.payload())
        self.portal.core.command({'action':'save_asset','id':'lift-1','expected_revision':1,'name':'Lift','unit':'day','rate':'99.00','minimum_units':1,'booking_fee':'10.00','security_deposit':'200.00','notes':'changed'},'asset-edit')
        with self.assertRaises(FleetError) as cm: self.portal.approve(req['id'])
        self.assertEqual(cm.exception.status,409)
        self.assertIn('quoted commercial terms changed',str(cm.exception))
        self.assertEqual(self.count('reservations'),0)
        self.assertEqual(self.portal.status(req['id'],TOKEN)['status'],'pending')

    def test_two_pending_requests_same_slot_only_first_can_reserve(self):
        one=self.portal.submit(self.payload('req-1',TOKEN,'Ada'))
        two=self.portal.submit(self.payload('req-2',TOKEN2,'Grace'))
        self.portal.approve(one['id'])
        with self.assertRaises(FleetError) as cm: self.portal.approve(two['id'])
        self.assertEqual(cm.exception.status,409)
        self.assertIn('no longer available',str(cm.exception))
        self.assertEqual(self.count('reservations'),1)
        self.assertEqual(self.portal.status(two['id'],TOKEN2)['status'],'pending')

    def test_reject_never_creates_reservation_and_cannot_be_approved(self):
        req=self.portal.submit(self.payload())
        out=self.portal.reject(req['id'],'Not available for delivery.')
        self.assertEqual(out['status'],'rejected')
        self.assertEqual(self.count('reservations'),0)
        with self.assertRaises(FleetError) as cm: self.portal.approve(req['id'])
        self.assertEqual(cm.exception.status,409)

    def test_submission_rejects_currently_unavailable_slot(self):
        self.portal.core.command({'action':'save_reservation','id':'existing','expected_revision':0,'asset_id':'lift-1','kind':'booking','start':START,'end':END,'customer':'Existing','contact':'x@example.test','notes':''},'existing')
        with self.assertRaises(FleetError) as cm: self.portal.submit(self.payload())
        self.assertEqual(cm.exception.status,409)
        self.assertEqual(self.count('customer_requests'),0)

    def test_http_status_token_is_post_body_and_cross_origin_write_is_denied(self):
        server=make_server(self.portal,0)
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            host,port=server.server_address
            conn=http.client.HTTPConnection(host,port,timeout=5)
            body=json.dumps(self.payload()).encode()
            conn.request('POST','/api/request',body=body,headers={'Content-Type':'application/json','Content-Length':str(len(body)),'Origin':f'http://{host}:{port}'})
            response=conn.getresponse(); data=json.loads(response.read())
            self.assertEqual(response.status,202); self.assertEqual(response.getheader('Cache-Control'),'no-store')
            req_id=data['id']
            status_body=json.dumps({'id':req_id,'status_token':TOKEN}).encode()
            conn.request('POST','/api/status',body=status_body,headers={'Content-Type':'application/json','Content-Length':str(len(status_body)),'Origin':f'http://{host}:{port}'})
            response=conn.getresponse(); self.assertEqual(response.status,200); response.read()
            self.assertNotIn(TOKEN,'/api/status')
            bad=json.dumps(self.payload('req-cross',TOKEN2)).encode()
            conn.request('POST','/api/request',body=bad,headers={'Content-Type':'application/json','Content-Length':str(len(bad)),'Origin':'https://evil.example'})
            response=conn.getresponse(); self.assertEqual(response.status,403); response.read()
            self.assertEqual(self.count('customer_requests'),1)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

if __name__=='__main__': unittest.main()
