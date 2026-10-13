"""T03 file-publication regressions, including real resource limits and SIGKILL.

The production runner and OS files/processes are real; play() is the explicitly
labelled evaluator fixture from test_panel_resume. No official games are run.
T03_PANEL_PATH selects the exact predecessor for the four run-path controls.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest
from unittest import mock

import test_panel_resume as resume


CHILD = r'''
import importlib.util, json, os, signal, sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('t03_publication_child',sys.argv[1])
panel=importlib.util.module_from_spec(spec);spec.loader.exec_module(panel)
runtime,engine,output=map(Path,sys.argv[2:5]);mode=sys.argv[5]
if mode == 'limit':
    import resource
    signal.signal(signal.SIGXFSZ,signal.SIG_IGN)
    resource.setrlimit(resource.RLIMIT_FSIZE,(8192,8192))
elif mode in ('kill_cell','kill_summary'):
    target='panel.json' if mode=='kill_summary' else '41-apex-seat0-candidate.json'
    def selected(path):
        path=Path(path)
        return path.parent==output and (path.name==target or
            (path.name.startswith('.'+target+'.') and path.name.endswith('.pending')))
    def kill():
        os.kill(os.getpid(),signal.SIGKILL)
    original_open=Path.open
    class InterruptedStream:
        def __init__(self,stream): self.stream=stream
        def __enter__(self): self.stream.__enter__();return self
        def __exit__(self,*args): return self.stream.__exit__(*args)
        def write(self,data):
            self.stream.write(data[:128]);self.stream.flush();os.fsync(self.stream.fileno());kill()
        def __getattr__(self,name):return getattr(self.stream,name)
    def intercept_open(path,*args,**kwargs):
        stream=original_open(path,*args,**kwargs)
        mode=args[0] if args else kwargs.get('mode','r')
        return InterruptedStream(stream) if selected(path) and any(c in mode for c in 'wxa') else stream
    Path.open=intercept_open
    original_write=os.write
    def intercept_write(fd,data):
        if selected(os.readlink('/proc/self/fd/'+str(fd))):
            original_write(fd,data[:128]);os.fsync(fd);kill()
        return original_write(fd,data)
    os.write=intercept_write
elif mode=='kill_after_cell_link':
    original_link=os.link
    def link(*args,**kwargs):
        original_link(*args,**kwargs);os.kill(os.getpid(),signal.SIGKILL)
    os.link=link
elif mode=='kill_before_summary_replace':
    def replace(*args,**kwargs):os.kill(os.getpid(),signal.SIGKILL)
    os.replace=replace
panel.run(runtime,engine,output,[41],['apex'],[0],['candidate'])
'''


class PublicationCases(unittest.TestCase):
    # Reuse the existing file fixture without re-enumerating its 27 test methods.
    setUp = resume.ResumeCases.setUp
    save_manifest = resume.ResumeCases.save_manifest
    calls = resume.ResumeCases.calls
    run_panel = resume.ResumeCases.run_panel
    cell = resume.ResumeCases.cell

    def large_rows(self):
        with self.evaluator.open('a') as stream:
            stream.write('\n_original_play=play\ndef play(*a, **kw):\n'
                         '    row=_original_play(*a, **kw)\n'
                         '    row["retention_fixture"]="x"*16384\n'
                         '    return row\n')

    def child(self, mode):
        return subprocess.run([sys.executable,'-B','-c',CHILD,str(self.panel_path),
                               str(self.runtime),str(self.engine),str(self.output),mode],
                              capture_output=True,text=True,timeout=15)

    def pending(self, name):
        return sorted(self.output.glob('.'+name+'.*.pending'))

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux resource-limit boundary')
    def test_file_limit_never_exposes_partial_cell(self):
        self.large_rows()
        result=self.child('limit')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('File too large',result.stderr)
        self.assertEqual(len(self.calls()),1)
        self.assertFalse(self.cell().exists())
        stages=self.pending(self.cell().name)
        self.assertEqual(len(stages),1)
        self.assertEqual(stages[0].stat().st_size,8192)
        self.assertFalse((self.output/'panel.json').exists())

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux resource-limit boundary')
    def test_file_limit_preserves_previous_summary(self):
        self.large_rows();self.run_panel(arms=['candidate'])
        summary=self.output/'panel.json';before=summary.read_bytes()
        result=self.child('limit')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('File too large',result.stderr)
        self.assertEqual(summary.read_bytes(),before)
        self.assertEqual(len(self.calls()),1)
        self.assertEqual(len(self.pending('panel.json')),1)
        # The partial stage is not a cache row. Recovery uses the complete cell.
        report=self.run_panel(arms=['candidate'])
        self.assertEqual(report['resume']['executed'],0)
        self.assertEqual(report['resume']['reused_complete'],1)
        self.assertEqual(len(self.calls()),1)

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux SIGKILL/write boundary')
    def test_kill_during_cell_write_keeps_final_absent(self):
        self.large_rows();result=self.child('kill_cell')
        self.assertEqual(result.returncode,-signal.SIGKILL)
        self.assertEqual(len(self.calls()),1)
        self.assertFalse(self.cell().exists())
        stages=self.pending(self.cell().name)
        self.assertEqual(len(stages),1)
        self.assertEqual(stages[0].stat().st_size,128)

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux SIGKILL/write boundary')
    def test_kill_during_summary_write_preserves_old_complete_bytes(self):
        self.large_rows();self.run_panel(arms=['candidate'])
        before=(self.output/'panel.json').read_bytes()
        result=self.child('kill_summary')
        self.assertEqual(result.returncode,-signal.SIGKILL)
        self.assertEqual((self.output/'panel.json').read_bytes(),before)
        self.assertEqual(len(self.calls()),1)
        self.assertEqual(self.pending('panel.json')[0].stat().st_size,128)

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux SIGKILL/link boundary')
    def test_kill_after_cell_install_resumes_without_replaying(self):
        result=self.child('kill_after_cell_link')
        self.assertEqual(result.returncode,-signal.SIGKILL)
        before=self.cell().read_bytes();json.loads(before)
        stages=self.pending(self.cell().name)
        self.assertEqual(len(stages),1)
        self.assertEqual(stages[0].read_bytes(),before)
        report=self.run_panel(arms=['candidate'])
        self.assertEqual(report['resume']['reused_complete'],1)
        self.assertEqual(report['resume']['executed'],0)
        self.assertEqual(len(self.calls()),1)
        self.assertEqual(self.cell().read_bytes(),before)

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux SIGKILL/rename boundary')
    def test_kill_before_summary_install_retains_both_complete_versions(self):
        self.run_panel(arms=['candidate']);before=(self.output/'panel.json').read_bytes()
        result=self.child('kill_before_summary_replace')
        self.assertEqual(result.returncode,-signal.SIGKILL)
        self.assertEqual((self.output/'panel.json').read_bytes(),before)
        pending=json.loads(self.pending('panel.json')[0].read_bytes())
        self.assertEqual(pending['resume']['reused_complete'],1)
        self.assertEqual(pending['resume']['executed'],0)
        self.assertEqual(len(self.calls()),1)

    def publish(self, value, *, replace=False, name='result.json'):
        self.output.mkdir(exist_ok=True)
        path=self.output/name
        self.panel.publish_json(path,value,replace=replace)
        return path

    def test_complete_bytes_equal_existing_json_representation(self):
        value={'text':'café\n界','cash':1.0,'order':['MILK','WHEAT']}
        path=self.publish(value)
        self.assertEqual(path.read_bytes(),(json.dumps(value,indent=2)+'\n').encode())
        self.assertEqual(self.pending(path.name),[])

    def test_serialization_error_does_not_touch_old_summary_or_make_stage(self):
        path=self.publish({'old':1});before=path.read_bytes()
        with self.assertRaises(TypeError):self.publish({'bad':object()},replace=True)
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(self.pending(path.name),[])

    def test_short_writes_are_completed(self):
        original=os.write;counts=[]
        def short(fd,data):
            count=original(fd,data[:7]);counts.append(count);return count
        with mock.patch.object(self.panel.os,'write',side_effect=short):path=self.publish({'v':'x'*100})
        self.assertGreater(len(counts),1)
        self.assertEqual(json.loads(path.read_bytes()),{'v':'x'*100})

    def test_zero_write_preserves_unpublished_stage(self):
        with mock.patch.object(self.panel.os,'write',return_value=0):
            with self.assertRaisesRegex(OSError,'no progress'):self.publish({'v':1})
        self.assertFalse((self.output/'result.json').exists())
        self.assertEqual(len(self.pending('result.json')),1)
        self.assertEqual(self.pending('result.json')[0].stat().st_size,0)

    def test_fsync_error_keeps_final_absent_and_complete_stage(self):
        error=OSError('injected file sync')
        with mock.patch.object(self.panel.os,'fsync',side_effect=error):
            with self.assertRaises(OSError) as caught:self.publish({'v':1})
        self.assertIs(caught.exception,error)
        self.assertFalse((self.output/'result.json').exists())
        self.assertEqual(json.loads(self.pending('result.json')[0].read_bytes()),{'v':1})

    def test_existing_cell_is_never_replaced(self):
        path=self.publish({'winner':1});before=path.read_bytes()
        with self.assertRaises(FileExistsError):self.publish({'loser':2})
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(json.loads(self.pending(path.name)[0].read_bytes()),{'loser':2})

    def test_replace_failure_preserves_summary_and_new_complete_stage(self):
        path=self.publish({'old':1});before=path.read_bytes();error=OSError('injected replace')
        with mock.patch.object(self.panel.os,'replace',side_effect=error):
            with self.assertRaises(OSError) as caught:self.publish({'new':2},replace=True)
        self.assertIs(caught.exception,error);self.assertEqual(path.read_bytes(),before)
        self.assertEqual(json.loads(self.pending(path.name)[0].read_bytes()),{'new':2})

    def test_cancellation_preserves_original_exception_and_stage(self):
        error=KeyboardInterrupt('injected stop')
        with mock.patch.object(self.panel.os,'link',side_effect=error):
            with self.assertRaises(KeyboardInterrupt) as caught:self.publish({'v':1})
        self.assertIs(caught.exception,error)
        self.assertFalse((self.output/'result.json').exists())
        self.assertEqual(json.loads(self.pending('result.json')[0].read_bytes()),{'v':1})

    def test_cleanup_failure_leaves_complete_final_and_resumable_cell(self):
        original=Path.unlink
        def unlink(path,*a,**kw):
            if path.suffix=='.pending':raise OSError('injected cleanup')
            return original(path,*a,**kw)
        with mock.patch.object(Path,'unlink',new=unlink):
            with self.assertRaisesRegex(OSError,'injected cleanup'):self.run_panel(arms=['candidate'])
        before=self.cell().read_bytes();json.loads(before)
        report=self.run_panel(arms=['candidate'])
        self.assertEqual(report['resume']['reused_complete'],1)
        self.assertEqual(len(self.calls()),1);self.assertEqual(self.cell().read_bytes(),before)

    def test_game_publication_failure_restores_actor_close(self):
        with mock.patch.object(self.panel.os,'link',side_effect=OSError('injected link')):
            with self.assertRaises(OSError):self.run_panel(arms=['candidate'])
        ev=sys.modules['t03_panel_evaluator']
        self.assertIs(ev.Actor.close,ev.ORIGINAL_CLOSE)
        self.assertFalse(self.cell().exists())
        self.assertFalse((self.output/'panel.json').exists())
        self.assertEqual(len(self.calls()),1)

    def test_summary_failure_does_not_reexecute_published_games(self):
        with mock.patch.object(self.panel.os,'replace',side_effect=OSError('injected replace')):
            with self.assertRaises(OSError):self.run_panel()
        self.assertEqual(len(self.calls()),2)
        report=self.run_panel()
        self.assertEqual(len(self.calls()),2)
        self.assertEqual(report['resume']['reused_complete'],2)
        self.assertEqual(len(report['pairs']),1)

    def test_competing_processes_publish_exactly_one_complete_cell(self):
        self.output.mkdir();go=self.output/'go';target=self.output/'shared.json'
        code=r'''
import importlib.util,json,sys,time
from pathlib import Path
s=importlib.util.spec_from_file_location('p',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
root=Path(sys.argv[2]);tag=sys.argv[3];(root/(tag+'.ready')).touch()
end=time.monotonic()+10
while not (root/'go').exists():
    if time.monotonic()>end:raise RuntimeError('test barrier expired')
    time.sleep(.005)
try:m.publish_json(root/'shared.json',{'writer':tag,'body':tag*10000})
except FileExistsError:sys.exit(3)
'''
        children=[subprocess.Popen([sys.executable,'-B','-c',code,str(self.panel_path),str(self.output),tag],
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE) for tag in ['a','b']]
        try:
            deadline=time.monotonic()+10
            while len(list(self.output.glob('*.ready')))<2:
                if time.monotonic()>deadline:self.fail('writer readiness timed out')
                if any(p.poll() is not None for p in children):self.fail('writer exited before barrier')
                time.sleep(.005)
            go.touch()
            for child in children:child.communicate(timeout=10)
            self.assertEqual(sorted(p.returncode for p in children),[0,3])
            winner=json.loads(target.read_bytes())
            self.assertEqual(winner['body'],winner['writer']*10000)
            stages=self.pending('shared.json');self.assertEqual(len(stages),1)
            loser=json.loads(stages[0].read_bytes())
            self.assertNotEqual(winner['writer'],loser['writer'])
            self.assertEqual(loser['body'],loser['writer']*10000)
        finally:
            for child in children:
                if child.poll() is None:child.kill()
                child.communicate()


if __name__=='__main__':unittest.main()
