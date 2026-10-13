# SPDX-License-Identifier: Apache-2.0
"""Exercise after-call diagnostics through the actual existing JSON IPC worker."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from run_panel import detach_receipt, HERE, load


def fixture_agent(obs, cfg=None):
    return {'farmer':['PASS'],'hands':[],'market':[],
            '_t14_evaluation':{'selected':'retain','reason':'transport_fixture'}}


class TransportTests(unittest.TestCase):
    def test_actual_worker_receipt_is_removed_before_engine_action(self):
        ev = load(HERE/'vendor/cloud-eval/evaluate.py','t14_r2_receipt_test_eval')
        actor = ev.Actor(str(Path(__file__).resolve())+'::fixture_agent',
                         HERE/'vendor/engine',ev.LOADER,20260907,startup_timeout=1)
        try:
            self.assertEqual(actor.ready['kind'],'ready')
            result = actor.act({'step':360},{'episodeSteps':720},1)
            self.assertEqual(result['kind'],'action')
            states = [SimpleNamespace(action=result['action']),SimpleNamespace(action={'market':[]})]
            receipt = detach_receipt(states,0)
            self.assertEqual(receipt,{'selected':'retain','reason':'transport_fixture'})
            self.assertEqual(states[0].action,{'farmer':['PASS'],'hands':[],'market':[]})
            self.assertEqual(states[1].action,{'market':[]})
            self.assertIsNone(detach_receipt(states,0))
        finally:
            actor.close()


if __name__ == '__main__':unittest.main()
