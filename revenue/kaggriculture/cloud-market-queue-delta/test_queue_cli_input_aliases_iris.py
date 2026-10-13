"""Exercise the actual queue CLI on temporary copies of retained market inputs."""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

TARGET=Path(__file__).with_name('queue_delta.py')
ENGINE=CASE=None


def load(path):
    spec=importlib.util.spec_from_file_location('iris_queue_cli_case',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def normalized(value):
    result=copy.deepcopy(value)
    result.pop('elapsed_seconds',None)
    return result


class QueueCLIInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_bytes=TARGET.read_bytes()
        cls.engine_bytes=ENGINE.read_bytes()
        cls.case_bytes=CASE.read_bytes()
        cls.queue=load(TARGET)
        cls.engine=cls.queue.load_market_engine(ENGINE)
        cls.expected=cls.queue.compare_queues(cls.engine,**json.loads(cls.case_bytes))
        cls.expected['engine_source_sha256']=hashlib.sha256(cls.engine_bytes).hexdigest()
        assert cls.expected['status']=='complete_conditional'

    def prepare(self,root):
        paths={k:root/n for k,n in [('cli','queue_delta.py'),('engine','kaggriculture.py'),('input','case.json')]}
        for key,data in [('cli',self.source_bytes),('engine',self.engine_bytes),('input',self.case_bytes)]:
            paths[key].write_bytes(data)
        return paths

    def invoke(self,paths,output=None,cwd=None):
        command=[sys.executable,str(paths['cli']),'--engine-source',str(paths['engine']),
                 '--input',str(paths['input'])]
        if output is not None:command+=['--output',str(output)]
        return subprocess.run(command,cwd=cwd,capture_output=True,text=True,timeout=15)

    def assert_sources_unchanged(self,paths):
        for key,data in [('cli',self.source_bytes),('engine',self.engine_bytes),('input',self.case_bytes)]:
            self.assertEqual(paths[key].read_bytes(),data,key+' bytes changed')

    def aliases(self,target):
        for mode in ('direct','symlink','hardlink'):
            with self.subTest(target=target,alias=mode),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);paths=self.prepare(root)
                output=paths[target] if mode=='direct' else root/'report.json'
                if mode=='symlink':output.symlink_to(paths[target])
                elif mode=='hardlink':output.hardlink_to(paths[target])
                done=self.invoke(paths,output)
                self.assert_sources_unchanged(paths)
                self.assertEqual(done.returncode,2)
                self.assertIn('must not alias',done.stderr)

    def test_engine_source_aliases_preserve_inputs(self):self.aliases('engine')
    def test_input_document_aliases_preserve_inputs(self):self.aliases('input')
    def test_executing_cli_aliases_preserve_inputs(self):self.aliases('cli')

    def test_symlinked_directory_alias_preserves_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);directory=root/'inputs';directory.mkdir();paths=self.prepare(directory)
            link=root/'directory-alias';link.symlink_to(directory,target_is_directory=True)
            done=self.invoke(paths,link/'case.json')
            self.assert_sources_unchanged(paths);self.assertEqual(done.returncode,2)

    def test_relative_parent_alias_preserves_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);paths=self.prepare(root);(root/'child').mkdir()
            done=self.invoke(paths,Path('child/../case.json'),cwd=root)
            self.assert_sources_unchanged(paths);self.assertEqual(done.returncode,2)

    def test_stdout_mode_preserves_original_complete_report(self):
        with tempfile.TemporaryDirectory() as temp:
            paths=self.prepare(Path(temp));done=self.invoke(paths)
            self.assertEqual(done.returncode,0,done.stderr)
            self.assertEqual(normalized(json.loads(done.stdout)),normalized(self.expected))
            self.assert_sources_unchanged(paths)

    def test_distinct_report_path_preserves_original_complete_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);paths=self.prepare(root);report=root/'report.json'
            done=self.invoke(paths,report)
            self.assertEqual(done.returncode,0,done.stderr)
            self.assertEqual(normalized(json.loads(report.read_text())),normalized(self.expected))
            self.assertEqual(done.stdout,'');self.assert_sources_unchanged(paths)

    def test_existing_unrelated_report_remains_writable(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);paths=self.prepare(root);report=root/'report.json'
            report.write_text('old report\n');done=self.invoke(paths,report)
            self.assertEqual(done.returncode,0,done.stderr)
            self.assertEqual(normalized(json.loads(report.read_text())),normalized(self.expected))
            self.assert_sources_unchanged(paths)

    def test_unknown_scenario_exit_and_report_remain_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);paths=self.prepare(root);payload=json.loads(paths['input'].read_text())
            payload['scenarios']=[];paths['input'].write_text(json.dumps(payload))
            saved={k:p.read_bytes() for k,p in paths.items()};report=root/'report.json'
            done=self.invoke(paths,report);out=json.loads(report.read_text())
            self.assertEqual(done.returncode,2)
            self.assertEqual(out['status'],'unknown');self.assertIsNone(out['bounds'])
            self.assertFalse(out['action_selected'])
            self.assertEqual(saved,{k:p.read_bytes() for k,p in paths.items()})

    def test_alias_validation_precedes_loading_and_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);paths=self.prepare(root)
            args=['queue','--engine-source',str(paths['engine']),'--input',str(paths['input']),
                  '--output',str(paths['input'])]
            with patch.object(sys,'argv',args),patch.object(self.queue,'load_market_engine') as loading, \
                    patch.object(self.queue,'compare_queues') as comparing:
                with self.assertRaises(SystemExit) as raised:self.queue.main()
                self.assertEqual(raised.exception.code,2)
                loading.assert_not_called();comparing.assert_not_called()
            self.assert_sources_unchanged(paths)

    def test_broken_output_symlink_cycle_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);paths=self.prepare(root);a=root/'a';b=root/'b'
            a.symlink_to(b);b.symlink_to(a)
            done=self.invoke(paths,a)
            self.assertEqual(done.returncode,2)
            self.assertIn('Cannot resolve report/input identity',done.stderr)
            self.assert_sources_unchanged(paths)


def main():
    global TARGET,ENGINE,CASE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=TARGET)
    parser.add_argument('--engine-source',type=Path,required=True)
    parser.add_argument('--case',type=Path,required=True)
    parser.add_argument('--json-output',type=Path)
    args=parser.parse_args();TARGET=args.source.resolve(strict=True)
    ENGINE=args.engine_source.resolve(strict=True);CASE=args.case.resolve(strict=True)
    # The test runner itself must not overwrite any of its source inputs.
    if args.json_output:
        for incoming in (TARGET,ENGINE,CASE,Path(__file__)):
            if args.json_output.resolve()==incoming.resolve() or (args.json_output.exists() and args.json_output.samefile(incoming)):
                parser.error('Use a distinct JSON result destination')
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(QueueCLIInputTests))
    report={'tests':result.testsRun,'passed':result.wasSuccessful(),'failures':len(result.failures),
            'errors':len(result.errors),'skipped':len(result.skipped),
            'source_sha256':hashlib.sha256(TARGET.read_bytes()).hexdigest(),
            'engine_sha256':hashlib.sha256(ENGINE.read_bytes()).hexdigest(),
            'case_sha256':hashlib.sha256(CASE.read_bytes()).hexdigest(),
            'failure_ids':[t.id() for t,_ in result.failures],
            'error_ids':[t.id() for t,_ in result.errors],
            'new_games':0,'policy_calls':0,
            'scope':'CLI file preservation; actual retained single-market comparisons, not new games'}
    if args.json_output:args.json_output.write_text(json.dumps(report,indent=2)+'\n')
    return int(not result.wasSuccessful())


if __name__=='__main__':raise SystemExit(main())
