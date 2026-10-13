import copy, importlib.util, os, pathlib, sys, tempfile, unittest
HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('repair',HERE/'repair_redundant_hire_two_seat.py'); repair=importlib.util.module_from_spec(spec); spec.loader.exec_module(repair)
def _runtime_root():
    explicit=os.environ.get('TITAN_RUNTIME_ROOT')
    if explicit: return pathlib.Path(explicit)
    for parent in HERE.parents:
        if parent.name=='cloud-execution-lab': return parent
    raise RuntimeError('cannot locate cloud-execution-lab; set TITAN_RUNTIME_ROOT')
RUNTIME=_runtime_root(); sys.path.insert(0,str(RUNTIME)); import mechanics as m
source=RUNTIME/'reference/titan-current/redundant_hire.py'
with tempfile.TemporaryDirectory() as td:
    fixed=pathlib.Path(td)/'redundant_hire.py'; fixed.write_bytes(repair.transform(source.read_bytes()))
    rs=importlib.util.spec_from_file_location('rh_fixed',fixed); rh=importlib.util.module_from_spec(rs); rs.loader.exec_module(rh)

def farm(board=10):
    return {'money':1000,'tiles':[[{} for _ in range(board)] for _ in range(board)],'hands':[],'farmer':[0,0],'hires_today':0}
def fixture(player=0, farms_count=2):
    obs={'step':22,'day':0,'hour':22,'player':player,'farms':[farm() for _ in range(farms_count)],'private':{'inventories':[{}],'shed':{},'seeds':{}},'market':{'inventory':{p:100 for p in m.PRODUCTS},'prices':{p:1 for p in m.PRODUCTS},'params':{}}}
    sel={'farmer':['PASS'],'hands':[],'market':[['HIRE']]}
    route=[{'farmer':['PASS'],'hands':[],'market':[]} for _ in range(24)]; route[23]={'farmer':['PASS'],'hands':[['PASS']],'market':[]}
    return obs,sel,route
def run(obs,sel,route): return rh.propose_redundant_hires(m,obs,{},sel,route=route,route_id='r',route_switch_steps=[])
class TestRepair(unittest.TestCase):
    def assert_closed(self,player,n):
        obs,sel,route=fixture(player,n); before=copy.deepcopy((obs,sel,route)); out,rep=run(obs,sel,route)
        self.assertEqual((obs,sel,route),before); self.assertEqual(out,sel); self.assertFalse(rep['changed']); self.assertFalse(rep['route_changed']); self.assertEqual(rep['reason'],'unsupported_public_seat_schema')
    def test_three_farms_player_two(self): self.assert_closed(2,3)
    def test_three_farms_valid_index(self): self.assert_closed(0,3)
    def test_one_farm(self): self.assert_closed(0,1)
    def test_negative_player(self): self.assert_closed(-1,2)
    def test_player_two(self): self.assert_closed(2,2)
    def test_bool_player(self): self.assert_closed(True,2)
    def test_seat_zero_behavior_preserved(self):
        o,s,r=fixture(0,2); out,rep=run(o,s,r); self.assertEqual(out['market'],[['SELL','WHEAT',0]]); self.assertTrue(rep['changed']); self.assertEqual(rep['removed_workers'],1)
    def test_seat_one_behavior_preserved(self):
        o,s,r=fixture(1,2); out,rep=run(o,s,r); self.assertEqual(out['market'],[['SELL','WHEAT',0]]); self.assertTrue(rep['changed']); self.assertEqual(rep['removed_workers'],1)
if __name__=='__main__': unittest.main()
