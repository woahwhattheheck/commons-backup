import hashlib,tempfile,unittest
from pathlib import Path
import transport

class API:
    def __init__(self, fail=False):self.calls=0;self.rows=[];self.fail=fail
    def competition_submissions(self,*args,**kwargs):return self.rows
    def competition_get_submission_limits(self,*args):return {'numAllowedNow':4,'numToday':1,'numTotal':3}
    def competition_submit(self,path,message,*args,**kwargs):
        self.calls+=1;self.rows=[{'ref':42,'description':message,'status':'pending'}]
        if self.fail:raise ConnectionError('synthetic uncertain response')
        return {'ref':42,'message':'submitted'}

class TransportTests(unittest.TestCase):
    def test_success_and_duplicate_readback(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'main.py';p.write_text('def agent(obs): return {}\n');h=hashlib.sha256(p.read_bytes()).hexdigest();api=API()
            self.assertEqual(transport.execute(api,p,h,Path(d)/'state')['status'],'SUBMISSION_FOUND')
            self.assertEqual(transport.execute(api,p,h,Path(d)/'state')['status'],'ALREADY_PRESENT')
            self.assertEqual(api.calls,1)
    def test_uncertain_create_does_not_resubmit(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'main.py';p.write_text('x=1');h=hashlib.sha256(p.read_bytes()).hexdigest();api=API(True)
            self.assertEqual(transport.execute(api,p,h,Path(d)/'state')['status'],'SUBMISSION_FOUND')
            api.rows=[]
            self.assertEqual(transport.execute(api,p,h,Path(d)/'state')['status'],'RECONCILE_REQUIRED')
            self.assertEqual(api.calls,1)
    def test_hash_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'main.py';p.write_text('x=1');api=API()
            with self.assertRaises(ValueError):transport.execute(api,p,'wrong',Path(d)/'state')
            self.assertEqual(api.calls,0)

    def test_old_operation_row_for_other_hash_is_not_current_payload(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'main.py';p.write_text('new payload')
            h=hashlib.sha256(p.read_bytes()).hexdigest();api=API()
            api.rows=[{'ref':41,'description':f'{transport.OPERATION_ID} sha256:{"0"*64}'}]
            result=transport.execute(api,p,h,Path(d)/'state')
            self.assertEqual(result['status'],'SUBMISSION_FOUND')
            self.assertEqual(api.calls,1)
            self.assertEqual(len(result['after']['matching_submissions']),1)
if __name__=='__main__':unittest.main()
