# SPDX-License-Identifier: Apache-2.0
import unittest
from dependencies import HERE, load
from history_streams import bounded_history_streams


class HistoryStreamTests(unittest.TestCase):
    def test_real_t12_deduplicated_unshifted_stream_remains(self):
        flow=load(HERE.parent/'cloud-market-response/flow.py','t15_history_test')
        history=flow.FlowHistory()
        now,end=505,513
        for lag in (1,2,3):
            for t in range(now-lag*24,end-lag*24+1):
                q=2 if t==now-lag*24 else 0
                history.add(flow.FlowInterval(t,'EGG',q,q,q,q,'identified'))
        # FlowHistory accepts chronological observations, as in real gameplay.
        history=flow.FlowHistory()
        for t in sorted({x for lag in (1,2,3) for x in range(now-lag*24,end-lag*24+1)}):
            q=2 if t in {now-lag*24 for lag in (1,2,3)} else 0
            history.add(flow.FlowInterval(t,'EGG',q,q,q,q,'identified'))
        streams,prediction=history.scenarios('EGG',now,end)
        self.assertTrue(prediction['ready'])
        old=[r for r in streams if r[0].endswith('_shift_0_paired')]
        self.assertEqual(old,[])
        chosen=bounded_history_streams(streams,4)
        self.assertTrue(chosen)
        self.assertTrue(any(tuple(row[1])==((now,2),) for row in chosen))
        self.assertTrue(all(row in streams for row in chosen))
        self.assertTrue(all(w['training_end']<now for w in prediction['windows']))

    def test_budget_and_whole_correlations(self):
        rows=[('day_1_shift_0_paired',((101,3),(103,7)),'paired'),
              ('day_2_shift_-1_paired',((101,2),(104,8)),'paired')]
        self.assertEqual(bounded_history_streams(rows,1),rows[:1])
        self.assertEqual(bounded_history_streams(rows,0),[])


if __name__=='__main__':unittest.main()
