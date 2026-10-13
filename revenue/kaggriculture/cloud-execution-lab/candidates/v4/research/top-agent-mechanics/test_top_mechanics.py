#!/usr/bin/env python3
from __future__ import annotations
import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('miner', HERE/'mine_top_mechanics.py')
miner=importlib.util.module_from_spec(spec); assert spec.loader; sys.modules[spec.name]=miner; spec.loader.exec_module(miner)


def write_csv(path, rows):
    fields=list(rows[0])
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

class MechanicsMiner(unittest.TestCase):
    def test_enriched_sequence_ranks_above_common_event(self):
        events=[]
        ord=0
        for team in ['T1','T2','F1','F2','F3']:
            for match in ['m1','m2']:
                events.append(miner.Event(match,team,'0',10,'unit','WATER','WHEAT',None,ord)); ord+=1
                if team.startswith('T'):
                    events.append(miner.Event(match,team,'0',11,'unit','PICKUP','FERTILIZER',1,ord)); ord+=1
                    events.append(miner.Event(match,team,'0',12,'unit','FERTILIZE','WHEAT',1,ord)); ord+=1
        r=miner.rank_features(events,{'T1','T2'},min_top_teams=2,min_top_support=1.0,limit=100)
        feats={x['feature']:x for x in r['ranking']}
        key='seq2|unit:PICKUP:FERTILIZER>unit:FERTILIZE:WHEAT'
        self.assertEqual(feats[key]['top_support'],1.0)
        self.assertEqual(feats[key]['field_support'],0.0)
        self.assertGreater(feats[key]['support_delta'],0.9)

    def test_prolific_team_does_not_count_multiple_times(self):
        events=[]
        ord=0
        for i in range(100):
            events.append(miner.Event(str(i),'T1','0',1,'market','HIRE','',None,ord)); ord+=1
        events.append(miner.Event('a','T2','0',1,'unit','PASS','',None,ord)); ord+=1
        for team in ['F1','F2']:
            events.append(miner.Event(team,team,'0',1,'unit','PASS','',None,ord)); ord+=1
        r=miner.rank_features(events,{'T1','T2'},min_top_teams=1,min_top_support=0,limit=100)
        hire=next(x for x in r['ranking'] if x['feature']=='event|market:HIRE')
        self.assertEqual(hire['top_teams_with'],1)
        self.assertEqual(hire['top_support'],0.5)

    def test_sequence_sort_uses_step_not_csv_order(self):
        events=[
            miner.Event('m','T1','0',20,'unit','HARVEST','WHEAT',None,0),
            miner.Event('m','T1','0',10,'unit','WATER','WHEAT',None,1),
            miner.Event('m','T2','0',10,'unit','WATER','WHEAT',None,2),
            miner.Event('m','T2','0',20,'unit','HARVEST','WHEAT',None,3),
            miner.Event('m','F1','0',10,'unit','PASS','',None,4),
        ]
        r=miner.rank_features(events,{'T1','T2'},min_top_teams=2,min_top_support=1,limit=100)
        feats={x['feature'] for x in r['ranking']}
        self.assertIn('seq2|unit:WATER:WHEAT>unit:HARVEST:WHEAT',feats)

    def test_alias_csv_reader_and_optional_columns(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'a.csv'
            write_csv(p,[{'episode_id':'e1','team_name':'T1','seat':'0','turn':'7','action_verb':'water','target':'wheat'},
                         {'episode_id':'e1','team_name':'T1','seat':'0','turn':'8','action_verb':'harvest','target':'wheat'}])
            rows=miner.read_events(p,'unit')
            self.assertEqual([x.verb for x in rows],['WATER','HARVEST'])
            self.assertEqual(rows[0].step,7)

    def test_missing_top_team_fails_closed(self):
        events=[miner.Event('m','T1','0',1,'unit','PASS','',None,0),
                miner.Event('m','F1','0',1,'unit','PASS','',None,1)]
        with self.assertRaises(miner.DataError):
            miner.rank_features(events,{'T1','NOPE'},min_top_teams=1)

    def test_same_step_cooccurrence_cross_source(self):
        events=[
            miner.Event('m','T1','0',5,'market','HIRE','',None,0),
            miner.Event('m','T1','0',5,'unit','PICKUP','FERTILIZER',1,1),
            miner.Event('m','T2','0',5,'market','HIRE','',None,2),
            miner.Event('m','T2','0',5,'unit','PICKUP','FERTILIZER',1,3),
            miner.Event('m','F1','0',5,'unit','PASS','',None,4),
        ]
        r=miner.rank_features(events,{'T1','T2'},min_top_teams=2,min_top_support=1,limit=100)
        self.assertTrue(any(x['feature']=='same_step|market:HIRE+unit:PICKUP:FERTILIZER' for x in r['ranking']))

    def test_cross_source_same_step_is_not_forced_into_sequence(self):
        events=[
            miner.Event('m','T1','0',10,'unit','PICKUP','FERTILIZER',1,0),
            miner.Event('m','T1','0',10,'market','HIRE','',1,1),
            miner.Event('m','T1','0',11,'unit','FERTILIZE','WHEAT',1,2),
            miner.Event('m','T2','0',10,'unit','PASS','',None,3),
            miner.Event('m','F1','0',10,'unit','PASS','',None,4),
        ]
        feats,_=miner.features_by_team(events)
        self.assertIn('same_step|market:HIRE+unit:PICKUP:FERTILIZER', feats['T1'])
        self.assertIn('seq2|unit:PICKUP:FERTILIZER>unit:FERTILIZE:WHEAT', feats['T1'])
        self.assertNotIn('seq2|market:HIRE>unit:PICKUP:FERTILIZER', feats['T1'])

    def test_quantity_bucket_is_preserved_as_mechanic(self):
        events=[miner.Event('m','T1','0',1,'market','SELL','MILK',12,0)]
        feats,_=miner.features_by_team(events)
        self.assertIn('qty_bucket|7-15|market:SELL:MILK', feats['T1'])

    def test_json_report_is_strict(self):
        events=[miner.Event('m','T1','0',1,'unit','WATER','WHEAT',None,0),
                miner.Event('m','T2','0',1,'unit','WATER','WHEAT',None,1),
                miner.Event('m','F1','0',1,'unit','PASS','',None,2)]
        r=miner.rank_features(events,{'T1','T2'},min_top_teams=2,min_top_support=1)
        json.dumps(r,allow_nan=False)

if __name__=='__main__': unittest.main()
