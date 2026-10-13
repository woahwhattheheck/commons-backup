"""Paired accounting/custody/observer tests; no game-strength claims."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('panel_driver', HERE/'run_capital_pair_panel.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def pair(old=(10, 8), new=(12, 8), seat=0):
    plan = [{'variant':v,'opponent':'x','seed':17,'seat':seat} for v in driver.CAPITAL]
    rows = [{'variant':v,'opponent':'x','seed':17,'candidate_seat':seat,
             'status':'complete','scores':list(scores),'failure':None}
            for v,scores in [('control',old),('candidate',new)]]
    return plan,rows


class PanelTests(unittest.TestCase):
    def test_sole_source_delta(self):
        driver.verify_single_delta({'early_capital.py':'a','main.py':'m'},
                                   {'early_capital.py':'b','main.py':'m'})
    def test_no_delta_rejected(self):
        with self.assertRaises(ValueError):
            driver.verify_single_delta({'early_capital.py':'a'},{'early_capital.py':'a'})
    def test_extra_source_rejected(self):
        with self.assertRaises(ValueError):
            driver.verify_single_delta({'early_capital.py':'a'}, {'early_capital.py':'b','new.py':'x'})
    def test_dependency_mutation_rejected(self):
        with self.assertRaises(ValueError):
            driver.verify_single_delta({'early_capital.py':'a','main.py':'x'},
                                       {'early_capital.py':'b','main.py':'y'})
    def test_relative_inventory_and_bytecode_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'x.py').write_text('a\n');(root/'__pycache__').mkdir()
            (root/'__pycache__/z.pyc').write_bytes(b'not source')
            self.assertEqual(set(driver.inventory(root)), {'x.py'})
            self.assertEqual(driver.blob(root/'x.py'),'78981922613b2afb6025042ff6bd878ac1994e85')
    def test_check_rejects_wrong_blob(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.py';p.write_text('a\n')
            with self.assertRaises(ValueError):driver.check(p,'0'*40)
    def test_digest_canonical(self):
        self.assertEqual(driver.digest({'a':1,'b':2}),driver.digest({'b':2,'a':1}))
        with self.assertRaises(ValueError):driver.digest({'a':float('nan')})
    def test_delta_accounts_for_rival_gain(self):
        p,r=pair((100,90),(110,115))
        s=driver.summarize_pairs(p,r)
        self.assertEqual((s['mean_delta_own'],s['mean_delta_rival'],s['mean_delta_margin']),(10,25,-15))
        self.assertEqual(s['new_losses'],1)
    def test_seat_one_orientation(self):
        p,r=pair((90,100),(115,110),seat=1)
        s=driver.summarize_pairs(p,r)
        self.assertEqual(s['mean_delta_margin'],-15)
        self.assertEqual(s['new_losses'],1)
    def test_lost_win_to_tie_not_new_loss(self):
        p,r=pair((10,8),(8,8));s=driver.summarize_pairs(p,r)
        self.assertEqual((s['lost_wins'],s['new_losses']),(1,0))
    def test_incomplete_retained_without_imputed_score(self):
        p,r=pair();r[1].update(status='failed',scores=None,failure={'kind':'timeout'})
        s=driver.summarize_pairs(p,r)
        self.assertEqual((s['planned_pairs'],s['complete_pairs'],s['incomplete_pairs']),(1,0,1))
        self.assertIsNone(s['mean_delta_margin'])
        self.assertEqual(s['pairs'][0]['candidate_failure'],{'kind':'timeout'})
    def test_missing_cell_rejected(self):
        p,r=pair()
        with self.assertRaises(ValueError):driver.summarize_pairs(p,r[:1])
    def test_duplicate_cell_rejected(self):
        p,r=pair()
        with self.assertRaises(ValueError):driver.summarize_pairs(p,r+[r[0]])
    def test_unplanned_cell_rejected(self):
        p,r=pair();extra=deepcopy(r[0]);extra['seed']=18
        with self.assertRaises(ValueError):driver.summarize_pairs(p,r+[extra])
    def test_observer_returns_original_action_and_freezes_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);modpath=root/'observer.py';dest=root/'rows.json'
            driver.write_observer(modpath,root,dest)
            action={'farmer':['PASS'],'hands':[],'market':[['SELL','WHEAT',1]]}
            report={'changed':False,'reason':'already_ordered'}
            fake=types.ModuleType('main');fake.agent=lambda obs,cfg:action
            fake._INSTANCE=types.SimpleNamespace(diagnostics={'status':'completed','early_capital':report})
            saved=list(sys.path)
            try:
                with patch.dict(sys.modules,{'main':fake}):
                    spec=importlib.util.spec_from_file_location('test_observer',modpath)
                    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
                    observation={'step':0};before=deepcopy(observation)
                    self.assertIs(m.agent(observation,{'episodeSteps':720}),action)
                    self.assertEqual(observation,before)
                    action['market'][0][2]=9;report['changed']=True
                    self.assertEqual(m.ROWS[0]['action']['market'][0][2],1)
                    self.assertFalse(m.ROWS[0]['capital']['changed'])
                    m.agent({'step':718},{'episodeSteps':720})
                    rows=json.loads(dest.read_text())
                    self.assertEqual(len(rows),2)
                    self.assertEqual(rows[1]['action']['market'][0][2],9)
            finally:sys.path[:]=saved

if __name__=='__main__':unittest.main(verbosity=2)
