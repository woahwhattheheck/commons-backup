"""Focused integration/regression tests; all identifiers and records are synthetic."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from panel_time_windows import (UTC, BusyBooking, Window, WindowError, from_request,
    normalize_windows, resolve_time, slot_conflicts, suggest_slots, utc_text)

HERE = Path(__file__).resolve().parent

def win(a='2030-01-15T15:00Z', b='2030-01-15T18:00Z'):
    return Window(resolve_time(a), resolve_time(b))

def three():
    return {pid: (win(),) for pid in ('candidate-a', 'panel-one', 'panel-two')}

class TimeResolution(unittest.TestCase):
    def test_explicit_offsets_same_instant(self):
        self.assertEqual(resolve_time('2030-01-15T09:00-06:00'), resolve_time('2030-01-15T15:00Z'))
    def test_naive_requires_timezone(self):
        with self.assertRaisesRegex(WindowError, 'timezone'):
            resolve_time('2030-01-15T09:00')
    def test_naive_chicago(self):
        self.assertEqual(utc_text(resolve_time('2030-01-15T09:00','America/Chicago')), '2030-01-15T15:00Z')
    def test_spring_gap_rejected(self):
        with self.assertRaisesRegex(WindowError, 'does not exist'):
            resolve_time('2026-03-08T02:30','America/New_York')
    def test_fall_fold_not_guessed(self):
        with self.assertRaisesRegex(WindowError, 'Ambiguous'):
            resolve_time('2026-11-01T01:30','America/New_York')
    def test_explicit_fall_folds_differ_one_hour(self):
        first = resolve_time('2026-11-01T01:30','America/New_York',fold=0)
        second = resolve_time('2026-11-01T01:30','America/New_York',fold=1)
        self.assertEqual(second-first, timedelta(hours=1))
        self.assertEqual(first,resolve_time('2026-11-01T01:30-04:00'))
        self.assertEqual(second,resolve_time('2026-11-01T01:30-05:00'))
    def test_lord_howe_half_hour_fold(self):
        first = resolve_time('2026-04-05T01:45','Australia/Lord_Howe',fold=0)
        second = resolve_time('2026-04-05T01:45','Australia/Lord_Howe',fold=1)
        self.assertEqual(second-first,timedelta(minutes=30))
    def test_lord_howe_half_hour_gap(self):
        with self.assertRaisesRegex(WindowError,'does not exist'):
            resolve_time('2026-10-04T02:15','Australia/Lord_Howe')
    def test_independent_endpoint_folds(self):
        windows=normalize_windows([{'start':'2026-11-01T01:30','end':'2026-11-01T01:45','start_fold':0,'end_fold':1}], 'America/New_York')
        self.assertEqual(windows[0].end-windows[0].start,timedelta(minutes=75))
    def test_unknown_timezone(self):
        with self.assertRaises(WindowError): resolve_time('2030-01-15T09:00','No/Such_Zone')
    def test_invalid_fold_and_precision(self):
        for value in (True,False,-1,2,'0',0.5):
            with self.subTest(value=value), self.assertRaises(WindowError):
                resolve_time('2030-01-15T09:00','UTC',fold=value)
        for value in ('2030-01-15','not-a-date','2030-01-15T09:00:01Z','2030-01-15T09:00:00.1Z','2030-01-15T09:00+01:00:01'):
            with self.subTest(value=value), self.assertRaises(WindowError): resolve_time(value)
    def test_offset_datetime_converts_to_utc(self):
        d=datetime(2030,1,15,9,tzinfo=timezone(timedelta(hours=-6)))
        self.assertEqual(resolve_time(d),resolve_time('2030-01-15T15:00Z'))
    def test_timezone_range_error(self):
        with self.assertRaises(WindowError): resolve_time('0001-01-01T00:00+01:00')
    def test_historical_second_offset_rejected(self):
        with self.assertRaises(WindowError): resolve_time('1850-01-01T12:00','Asia/Kolkata')

class Normalize(unittest.TestCase):
    def test_overlaps_adjacencies_duplicates_merged(self):
        source=[{'start':'2030-01-15T16:00Z','end':'2030-01-15T17:00Z'},
                {'start':'2030-01-15T15:00Z','end':'2030-01-15T16:00Z'},
                {'start':'2030-01-15T15:30Z','end':'2030-01-15T16:30Z'}]
        original=deepcopy(source)
        self.assertEqual(normalize_windows(source), (win(b='2030-01-15T17:00Z'),))
        self.assertEqual(source,original)
    def test_empty_and_unsorted(self):
        self.assertEqual(normalize_windows([]),())
        a,b=win(),win('2030-01-16T15:00Z','2030-01-16T18:00Z')
        self.assertEqual(normalize_windows([b,a]),(a,b))
    def test_positive_window(self):
        for end in ('2030-01-15T15:00Z','2030-01-15T14:59Z'):
            with self.assertRaises(WindowError):win(b=end)
    def test_invalid_shape_and_large_source_interval(self):
        for rows in (None,{},'abc',[None],[{}],[{'start':'2030-01-15T15:00Z'}]):
            with self.subTest(rows=rows),self.assertRaises(WindowError):normalize_windows(rows)
        with self.assertRaises(WindowError):normalize_windows([win('2030-01-01T00:00Z','2030-02-02T00:00Z')])
    def test_input_bound_stops_infinite_generator(self):
        count=0
        def infinite():
            nonlocal count
            while True:
                count+=1
                yield win()
        with self.assertRaisesRegex(WindowError,'10000'):normalize_windows(infinite())
        self.assertEqual(count,10001)
    def test_window_is_immutable(self):
        from dataclasses import FrozenInstanceError
        with self.assertRaises(FrozenInstanceError):win().start=resolve_time('2030-01-01T00:00Z')
    def test_merged_longer_than_source_cap_remains_usable(self):
        a=normalize_windows([win('2030-01-01T00:00Z','2030-02-01T00:00Z'),win('2030-02-01T00:00Z','2030-03-01T00:00Z')])
        result=suggest_slots({'p':a},['p'],win('2030-02-15T15:00Z','2030-02-15T16:00Z'),30)
        self.assertEqual(len(result),3)

class SlotSearch(unittest.TestCase):
    def test_candidate_and_two_interviewers_three_timezones(self):
        a={
            'candidate':normalize_windows([{'start':'2030-01-15T09:00','end':'2030-01-15T11:00'}],'America/Chicago'),
            'panel-one':normalize_windows([{'start':'2030-01-15T10:30','end':'2030-01-15T12:00'}],'America/New_York'),
            'panel-two':normalize_windows([{'start':'2030-01-15T15:00','end':'2030-01-15T17:00'}],'Europe/London')}
        result=suggest_slots(a,list(a),win(),30)
        self.assertEqual(result[0],win('2030-01-15T15:30Z','2030-01-15T16:00Z'))
        self.assertEqual(len(result),5)
    def test_missing_participant_availability_has_no_slots(self):
        a=three();del a['panel-two']
        self.assertEqual(suggest_slots(a,['candidate-a','panel-one','panel-two'],win(),30),())
    def test_short_availability_no_slot(self):
        self.assertEqual(suggest_slots({'p':(win(b='2030-01-15T15:15Z'),)},['p'],win(),30),())
    def test_shared_panel_busy_removes_overlaps(self):
        a=three();b=BusyBooking('other-case',('candidate-b','panel-one'),win('2030-01-15T15:30Z','2030-01-15T16:00Z'))
        found=suggest_slots(a,list(a),win(),30,[b])
        self.assertEqual(found[0],win('2030-01-15T15:00Z','2030-01-15T15:30Z'))
        self.assertEqual(found[1],win('2030-01-15T16:00Z','2030-01-15T16:30Z'))
        for w in found:self.assertFalse(w.start<b.window.end and b.window.start<w.end)
    def test_unrelated_busy_has_no_effect(self):
        a=three();b=BusyBooking('other',('nobody-here',),win())
        self.assertEqual(suggest_slots(a,list(a),win(),30,[b]),suggest_slots(a,list(a),win(),30))
    def test_reschedule_excludes_only_current_booking(self):
        a=three();ids=list(a)
        current=BusyBooking('current',tuple(ids),win('2030-01-15T15:00Z','2030-01-15T15:30Z'))
        other=BusyBooking('other',('panel-one',),win('2030-01-15T16:00Z','2030-01-15T16:30Z'))
        found=suggest_slots(a,ids,win(),30,[current,other],exclude_booking_id='current')
        self.assertEqual(found[0],current.window)
        self.assertNotIn(other.window,found)
    def test_conflicts_do_not_disclose_other_candidate(self):
        a=three();b=BusyBooking('SECRET_OTHER_INTERVIEW',('PRIVATE_OTHER_CANDIDATE','panel-two'),win())
        found=slot_conflicts(a,list(a),win(),[b])
        self.assertEqual(found,[{'kind':'busy','participant_id':'panel-two'}])
        self.assertNotIn('PRIVATE',json.dumps(found));self.assertNotIn('SECRET',json.dumps(found))
    def test_availability_change_is_visible(self):
        a=three();proposed=suggest_slots(a,list(a),win(),30)[0];a['panel-two']=()
        self.assertEqual(slot_conflicts(a,list(a),proposed),[{'kind':'unavailable','participant_id':'panel-two'}])
    def test_exact_boundaries_half_open(self):
        a=three();w=win('2030-01-15T15:30Z','2030-01-15T16:00Z')
        busy=[BusyBooking('before',('panel-one',),win('2030-01-15T15:00Z','2030-01-15T15:30Z')),
              BusyBooking('after',('panel-one',),win('2030-01-15T16:00Z','2030-01-15T16:30Z'))]
        self.assertEqual(slot_conflicts(a,list(a),w,busy),[])
    def test_grid_rounds_up_not_down(self):
        a=three();found=suggest_slots(a,list(a),win('2030-01-15T15:01Z','2030-01-15T16:00Z'),30)
        self.assertEqual(utc_text(found[0].start),'2030-01-15T15:15Z')
    def test_pre_epoch_grid(self):
        w=win('1969-12-31T23:01Z','1969-12-31T23:59Z')
        found=suggest_slots({'p':(w,)},['p'],w,15)
        self.assertEqual(utc_text(found[0].start),'1969-12-31T23:15Z')
    def test_limit_and_duration(self):
        a=three();found=suggest_slots(a,list(a),win(),45,limit=2)
        self.assertEqual(len(found),2)
        self.assertTrue(all(w.end-w.start==timedelta(minutes=45) for w in found))
    def test_invalid_integer_parameters(self):
        for val in (True,0,-1,1.5,'30',float('inf'),float('nan')):
            with self.subTest(val=val),self.assertRaises(WindowError):suggest_slots(three(),list(three()),win(),val)
        with self.assertRaises(WindowError):suggest_slots(three(),list(three()),win(),30,limit=0)
        with self.assertRaises(WindowError):suggest_slots(three(),list(three()),win(),30,grid_minutes=0)
    def test_bad_participant_shapes(self):
        for ids in ([],['p','p'],[None],{},'candidate',None):
            with self.subTest(ids=ids),self.assertRaises(WindowError):suggest_slots({},ids,win(),30)
    def test_duplicate_busy_ids_not_silently_ignored(self):
        a=three();b=BusyBooking('same',('panel-one',),win())
        with self.assertRaisesRegex(WindowError,'Duplicate'):suggest_slots(a,list(a),win(),30,[b,b],exclude_booking_id='same')
    def test_invalid_busy_record(self):
        for ids in ([],['p','p'],None,'p'):
            with self.subTest(ids=ids),self.assertRaises(WindowError):BusyBooking('id',ids,win())
        with self.assertRaises(WindowError):suggest_slots(three(),list(three()),win(),30,[{}])
    def test_too_long_search(self):
        with self.assertRaises(WindowError):suggest_slots(three(),list(three()),win('2030-01-01T00:00Z','2030-02-02T00:00Z'),30)
    def test_no_mutation(self):
        a=three();original=deepcopy(a);busy=[BusyBooking('other',('panel-two',),win())];old=deepcopy(busy)
        suggest_slots(a,list(a),win(),30,busy);self.assertEqual(a,original);self.assertEqual(busy,old)
    def test_datetime_upper_boundary(self):
        w=win('9999-12-31T23:45Z','9999-12-31T23:59Z')
        self.assertEqual(len(suggest_slots({'p':(w,)},['p'],w,1)),1)
        self.assertEqual(suggest_slots({'p':(w,)},['p'],w,1,grid_minutes=1440),())
    def test_randomized_bruteforce_oracle_300_panels(self):
        rng=random.Random(450908)
        origin=resolve_time('2030-01-15T00:00Z')
        def minute(n):return origin+timedelta(minutes=n)
        for example in range(300):
            with self.subTest(example=example):
                ids=['c','i1','i2'];a={}
                for pid in ids:
                    rows=[]
                    for _ in range(rng.randrange(1,7)):
                        left=rng.randrange(0,90);right=rng.randrange(left+1,121)
                        rows.append(Window(minute(left),minute(right)))
                    a[pid]=normalize_windows(rows)
                busy=[]
                for j in range(rng.randrange(0,6)):
                    left=rng.randrange(0,90);right=rng.randrange(left+1,121)
                    busy.append(BusyBooking(str(j),(rng.choice(ids+['outsider']),),Window(minute(left),minute(right))))
                duration=rng.choice([5,10,15,30]);grid=rng.choice([1,5,15])
                search=Window(minute(0),minute(120))
                actual=suggest_slots(a,ids,search,duration,busy,grid_minutes=grid,limit=1000)
                expected=[]
                for start in range(0,121-duration):
                    if int(minute(start).timestamp())%(grid*60):continue
                    w=Window(minute(start),minute(start+duration))
                    # Independent predicate oracle, not slot_conflicts/_intersect.
                    available=all(any(x.start<=w.start and w.end<=x.end for x in a[pid]) for pid in ids)
                    occupied=any(set(ids)&set(b.participant_ids) and w.start<b.window.end and b.window.start<w.end for b in busy)
                    if available and not occupied:expected.append(w)
                self.assertEqual(actual,tuple(expected))

class Consumers(unittest.TestCase):
    def request(self):
        return {'participants':['c','i1','i2'],'timezones':{'c':'America/Chicago','i1':'America/New_York','i2':'Europe/London'},
                'availability':{'c':[{'start':'2030-01-15T09:00','end':'2030-01-15T11:00'}],
                                'i1':[{'start':'2030-01-15T10:30','end':'2030-01-15T12:00'}],
                                'i2':[{'start':'2030-01-15T15:00','end':'2030-01-15T17:00'}]},
                'search':{'start':'2030-01-15T15:00Z','end':'2030-01-15T18:00Z'},'duration_minutes':30}
    def test_json_adapter_runs_complete_three_person_workflow(self):
        req=self.request();orig=deepcopy(req);out=from_request(req)
        self.assertEqual(out['slot_count'],5)
        self.assertEqual(out['slots'][0],{'start':'2030-01-15T15:30Z','end':'2030-01-15T16:00Z'})
        self.assertFalse(out['booking_created']);self.assertFalse(out['messages_sent']);self.assertEqual(req,orig)
        req['busy']=[{'id':'meeting-a','participants':['i1','other-candidate'],'start':'2030-01-15T15:30Z','end':'2030-01-15T16:00Z'}]
        after=from_request(req)
        self.assertEqual(after['slots'][0]['start'],'2030-01-15T16:00Z')
        self.assertNotIn('other-candidate',json.dumps(after))
        req['exclude_booking_id']='meeting-a'
        self.assertEqual(from_request(req)['slots'],out['slots'])
    def test_cli_actual_subprocess_and_new_file_only(self):
        with tempfile.TemporaryDirectory() as temp:
            inp=Path(temp)/'request.json';out=Path(temp)/'slots.json';inp.write_text(json.dumps(self.request()))
            command=[sys.executable,str(HERE/'panel_time_windows.py'),str(inp),'--output',str(out)]
            first=subprocess.run(command,capture_output=True,text=True,timeout=10)
            self.assertEqual(first.returncode,0,first.stderr)
            content=out.read_bytes();self.assertEqual(json.loads(content)['slot_count'],5)
            second=subprocess.run(command,capture_output=True,text=True,timeout=10)
            self.assertEqual(second.returncode,2);self.assertEqual(out.read_bytes(),content)
    def test_cli_invalid_json_no_output(self):
        with tempfile.TemporaryDirectory() as temp:
            inp=Path(temp)/'request.json';out=Path(temp)/'slots.json';inp.write_text('{"duration_minutes":NaN}')
            r=subprocess.run([sys.executable,str(HERE/'panel_time_windows.py'),str(inp),'--output',str(out)],capture_output=True,text=True,timeout=10)
            self.assertEqual(r.returncode,2);self.assertFalse(out.exists());self.assertIn('Non-finite',r.stderr)
    def test_real_sqlite_transaction_rechecks_shared_panel(self):
        # This consumer illustrates the required transaction boundary; it is not
        # a replacement for WILLOW's native application's storage implementation.
        with tempfile.TemporaryDirectory() as temp:
            path=str(Path(temp)/'bookings.sqlite3')
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('CREATE TABLE bookings(id TEXT PRIMARY KEY, person TEXT, start TEXT, end TEXT)')
            barrier=threading.Barrier(2)
            def reserve(name):
                with closing(sqlite3.connect(path,timeout=10)) as db, db:
                    barrier.wait();db.execute('BEGIN IMMEDIATE')
                    rows=db.execute('SELECT id,person,start,end FROM bookings').fetchall()
                    busy=[BusyBooking(r[0],(r[1],),win(r[2],r[3])) for r in rows]
                    a=three();proposed=win('2030-01-15T15:30Z','2030-01-15T16:00Z')
                    conflicts=slot_conflicts(a,list(a),proposed,busy)
                    if conflicts:return 'conflict'
                    db.execute('INSERT INTO bookings VALUES(?,?,?,?)',(name,'panel-one',utc_text(proposed.start),utc_text(proposed.end)))
                    return 'booked'
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(reserve,['case-a','case-b']))
            self.assertCountEqual(results,['booked','conflict'])
            with closing(sqlite3.connect(path)) as db, db:self.assertEqual(db.execute('SELECT count(*) FROM bookings').fetchone()[0],1)

if __name__=='__main__': unittest.main(verbosity=2)
