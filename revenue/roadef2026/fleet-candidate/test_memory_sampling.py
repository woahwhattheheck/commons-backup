"""Exercise the exact Supervisor.sample_rss method with offline procfs fixtures."""
import ast
from contextlib import contextmanager
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
SOURCE=os.environ.get('SAMPLING_SOURCE', str(HERE/'supervisor.py'))
text=Path(SOURCE).read_text()
if text.startswith('    def sample_rss'):
    tree=ast.parse('class Supervisor:\n'+text)
else:
    tree=ast.parse(text)
cls_node=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='Supervisor')
method=next(node for node in cls_node.body if isinstance(node,ast.FunctionDef) and node.name=='sample_rss')
ns={'Path':Path,'os':os,'sys':sys,'time':time}
exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])), SOURCE, 'exec'),ns)
METHOD=ns['sample_rss']

class Proc:
    def __init__(self,pid,code=None): self.pid=pid; self.code=code
    def poll(self): return self.code

def actor(lanes=(),check=None,peak=None):
    return SimpleNamespace(lanes=[{'process':p} for p in lanes],check={'process':check} if check else None,
                           next_rss_sample=0,peak_sampled_rss_kib=peak)

def fields(pid,parent,rss=100,nspid=None):
    s=f'Name:\tfixture\nPid:\t{pid}\nPPid:\t{parent}\n'
    if nspid is not False: s+='NSpid:\t'+'\t'.join(map(str,nspid or [pid]))+'\n'
    if rss is not None: s+=f'VmRSS:\t{rss} kB\n'
    return s

class SamplingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.real_scandir=os.scandir
        self.self_path=self.root/'self'/'status'
        self.self_path.parent.mkdir(); self.self_path.write_text(fields(100,1,100))
        self.put(100,1,100)
    def tearDown(self): self.tmp.cleanup()
    def put(self,pid,parent,rss=100,ns=None):
        p=self.root/str(pid)/'status';p.parent.mkdir(exist_ok=True);p.write_text(fields(pid,parent,rss,ns));return p
    @contextmanager
    def virtual(self,pid=100,clock=None,no_scan=False):
        def map_path(value):
            p=Path(value)
            if str(p).startswith('/proc'):
                return self.root/p.relative_to('/proc')
            return p
        def scan(value):
            if no_scan: raise AssertionError('same-namespace sampling scanned unrelated processes')
            return self.real_scandir(self.root if str(value)=='/proc' else value)
        with patch.dict(ns,Path=map_path),patch.object(os,'getpid',return_value=pid),patch.object(os,'scandir',side_effect=scan),patch.object(sys,'platform','linux'):
            if clock is None:
                yield
            else:
                with patch.object(time,'monotonic',side_effect=clock): yield
    def run_method(self,obj,**kw):
        with self.virtual(**kw): METHOD(obj)
        return obj
    def test_same_namespace_fast_path(self):
        self.put(200,100,300);self.put(300,100,500)
        obj=self.run_method(actor([Proc(200)],Proc(300)),no_scan=True)
        self.assertEqual(obj.peak_sampled_rss_kib,900)
        self.assertEqual(obj.memory_sampling['status'],'complete')
    def test_outer_procfs_mapping(self):
        self.self_path.write_text(fields(8000,1,100,[8000,100]));self.put(8000,1,100,[8000,100])
        self.put(9000,8000,300,[9000,200]);self.put(10000,8000,500,[10000,300])
        obj=self.run_method(actor([Proc(200)],Proc(300)))
        self.assertEqual(obj.peak_sampled_rss_kib,900)
        self.assertEqual(obj.memory_sampling['sampled_processes'],3)
    def test_namespace_collision_is_not_a_child(self):
        self.self_path.write_text(fields(8000,1,100,[8000,100]));self.put(8000,1,100,[8000,100])
        self.put(100,1,900000);self.put(200,77,800000,[200,200]);self.put(9000,8000,300,[9000,200])
        obj=self.run_method(actor([Proc(200)]));self.assertEqual(obj.peak_sampled_rss_kib,400)
    def test_nested_child_uses_supervisor_depth(self):
        self.self_path.write_text(fields(8000,1,100,[8000,100]));self.put(8000,1,100,[8000,100])
        self.put(9000,8000,300,[9000,200,1]);obj=self.run_method(actor([Proc(200)]))
        self.assertEqual(obj.peak_sampled_rss_kib,400)
    def test_same_inner_pid_from_other_parent_is_ignored(self):
        self.self_path.write_text(fields(8000,1,100,[8000,100]));self.put(8000,1,100,[8000,100])
        self.put(9000,7000,900000,[9000,200]);obj=self.run_method(actor([Proc(200)]))
        self.assertIsNone(obj.peak_sampled_rss_kib)
        self.assertEqual(obj.memory_sampling['status'],'partial')
        self.assertEqual(obj.memory_sampling['sampled_sum_kib'],100)
    def test_missing_root_is_unavailable_not_zero(self):
        self.self_path.unlink(); obj=self.run_method(actor())
        self.assertIsNone(obj.peak_sampled_rss_kib)
        self.assertEqual(obj.memory_sampling['status'],'unavailable')
        self.assertIsNone(obj.memory_sampling['sampled_sum_kib'])
    def test_missing_live_process_preserves_previous_complete_peak(self):
        obj=self.run_method(actor([Proc(200)],peak=800))
        self.assertEqual(obj.peak_sampled_rss_kib,800)
        self.assertEqual(obj.memory_sampling['incomplete_samples'],1)
    def test_missing_rss_is_not_zero(self):
        self.put(200,100,None);obj=self.run_method(actor([Proc(200)]))
        self.assertIsNone(obj.peak_sampled_rss_kib)
        self.assertEqual(obj.memory_sampling['reason'],'active_process_unreadable')
    def test_malformed_rss_and_namespace_are_incomplete(self):
        for bad in ('VmRSS:\t-2 kB\n','VmRSS:\tNaN kB\n','VmRSS:\t200 MB\n','NSpid:\twrong\n'):
            with self.subTest(bad=bad):
                self.put(200,100,300).write_text(fields(200,100,None)+bad)
                obj=self.run_method(actor([Proc(200)]));self.assertIsNone(obj.peak_sampled_rss_kib)
    def test_old_kernel_same_namespace_without_nspid(self):
        self.self_path.write_text(fields(100,1,100,False));self.put(200,100,300,False)
        obj=self.run_method(actor([Proc(200)]),no_scan=True)
        self.assertEqual(obj.peak_sampled_rss_kib,400)
    def test_ambiguous_namespace_matches_are_not_credited(self):
        self.self_path.write_text(fields(8000,1,100,[8000,100]));self.put(8000,1,100,[8000,100])
        self.put(9000,8000,300,[9000,200]);self.put(9001,8000,700,[9001,200])
        obj=self.run_method(actor([Proc(200)]));self.assertIsNone(obj.peak_sampled_rss_kib)
        self.assertEqual(obj.memory_sampling['sampled_processes'],1)
    def test_duplicate_process_reference_counts_once(self):
        p=Proc(200);self.put(200,100,300)
        obj=self.run_method(actor([p,p],p));self.assertEqual(obj.peak_sampled_rss_kib,400)
        self.assertEqual(obj.memory_sampling['expected_processes'],2)
    def test_ended_process_is_not_sampled(self):
        self.put(200,100,300);obj=self.run_method(actor([Proc(200,0)]),no_scan=True)
        self.assertEqual(obj.peak_sampled_rss_kib,100)
    def test_no_leader_descendant_sum_is_invented(self):
        self.put(200,100,300);self.put(300,200,700)
        obj=self.run_method(actor([Proc(200)]),no_scan=True);self.assertEqual(obj.peak_sampled_rss_kib,400)
    def test_peak_never_decreases_on_complete_sample(self):
        obj=self.run_method(actor(peak=800),no_scan=True)
        self.assertEqual(obj.peak_sampled_rss_kib,800)
        self.assertEqual(obj.memory_sampling['complete_samples'],1)
    def test_sampling_cadence_is_unchanged(self):
        obj=actor();obj.next_rss_sample=1000
        self.run_method(obj,clock=lambda:999)
        self.assertIsNone(obj.peak_sampled_rss_kib);self.assertFalse(hasattr(obj,'memory_sampling'))
    def test_nonlinux_does_not_touch_procfs(self):
        obj=actor()
        with patch.object(sys,'platform','win32'),patch.dict(ns,Path=lambda _:self.fail('procfs read on nonlinux')): METHOD(obj)
        self.assertIsNone(obj.peak_sampled_rss_kib)
    def test_scan_budget_remains_diagnostic(self):
        self.self_path.write_text(fields(8000,1,100,[8000,100]));self.put(8000,1,100,[8000,100])
        ticks=iter([10,10,10.021,10.023]);obj=self.run_method(actor([Proc(200)],peak=700),clock=lambda:next(ticks))
        self.assertEqual(obj.peak_sampled_rss_kib,700)
        self.assertEqual(obj.memory_sampling['reason'],'procfs_scan_budget')
    def test_counts_accumulate_without_resetting_prior_incomplete(self):
        obj=self.run_method(actor([Proc(200)]))
        self.put(200,100,300);obj.next_rss_sample=0;self.run_method(obj,no_scan=True)
        self.assertEqual(obj.memory_sampling['complete_samples'],1)
        self.assertEqual(obj.memory_sampling['incomplete_samples'],1)
        self.assertEqual(obj.peak_sampled_rss_kib,400)
    def test_inaccessible_scan_is_explicit_without_losing_prior_peak(self):
        obj=actor([Proc(200)],peak=800)
        with self.virtual(),patch.object(os,'scandir',side_effect=PermissionError('fixture')):
            METHOD(obj)
        self.assertEqual(obj.peak_sampled_rss_kib,800)
        self.assertEqual(obj.memory_sampling['reason'],'procfs_scan_unavailable')
        self.assertEqual(obj.memory_sampling['status'],'partial')
    def test_structurally_invalid_self_status_is_unavailable(self):
        self.self_path.write_text(fields(8000,1,100,[8000,200]))
        obj=self.run_method(actor())
        self.assertIsNone(obj.peak_sampled_rss_kib)
        self.assertEqual(obj.memory_sampling['reason'],'supervisor_procfs_unavailable')
    def test_empty_process_rss_can_be_a_measured_zero(self):
        self.self_path.write_text(fields(100,1,0));self.put(200,100,0)
        obj=self.run_method(actor([Proc(200)]),no_scan=True)
        self.assertEqual(obj.peak_sampled_rss_kib,0)
        self.assertEqual(obj.memory_sampling['status'],'complete')
    def test_real_child_and_supervisor_native_read(self):
        if not sys.platform.startswith('linux'): self.skipTest('Linux procfs')
        child=subprocess.Popen([sys.executable,'-c','import time; x=bytearray(8*1024*1024); print("ready",flush=True); time.sleep(15)'],stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(),'ready')
            obj=actor([child]);METHOD(obj)
            self.assertEqual(obj.memory_sampling['status'],'complete')
            self.assertEqual(obj.memory_sampling['expected_processes'],2)
            self.assertGreater(obj.peak_sampled_rss_kib,8*1024)
        finally:
            child.terminate();child.wait(timeout=5);child.stdout.close()

if __name__=='__main__': unittest.main(verbosity=2)
