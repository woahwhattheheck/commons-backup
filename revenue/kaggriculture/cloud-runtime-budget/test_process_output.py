# SPDX-License-Identifier: Apache-2.0
"""Child diagnostic bytes must not abort saved-profile result collection."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import profile_saved as p

CHILD = '''from pathlib import Path
import base64,os,sys,time
Path(sys.argv[1]).write_bytes(base64.b64decode(sys.argv[2]))
os.write(1,base64.b64decode(sys.argv[3]))
os.write(2,base64.b64decode(sys.argv[4]))
if sys.argv[5] == "timeout":
    time.sleep(30)
raise SystemExit(int(sys.argv[5]))
'''
ERROR_REPORT = {'status':'error','calls':[],
                'error':{'type':'RuntimeError','message':'original child body'}}


def complete_report():
    # This tests report transport, not a claimed profiling measurement.
    return {'status':'complete','calls':[{'step':0,'wall_s':.01}],
            'action_sequence_sha256':'fixture','runtime_sources':{'main.py':'fixture'},
            'input':{'fixture':True},'loaded_sources':{'target':'fixture'},
            'loaded_sources_unchanged':True,'sources_unchanged':True}


class ProcessOutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_case(self, stdout, stderr, report=None, exit_code=7):
        raw = json.dumps(ERROR_REPORT if report is None else report).encode() if not isinstance(report,bytes) else report
        output = self.root/'result.json'
        args = SimpleNamespace(entrypoint=self.root/'unused.py',factory='make_agent',method='act',
            timing_source=self.root/'timing.py',replay=self.root/'work.json',seat=0,
            max_decisions=1,classification='constructed-diagnostic-transport',
            process_timeout=1.0 if exit_code == 'timeout' else 10,output=output)
        real_run = subprocess.run
        calls=[]
        def run(command,**kwargs):
            calls.append(command)
            encoded=[base64.b64encode(x).decode('ascii') for x in (raw,stdout,stderr)]
            return real_run([sys.executable,'-c',CHILD,command[command.index('--output')+1],
                             *encoded,str(exit_code)],**kwargs)
        with patch.object(p.subprocess,'run',run):
            code=p.supervise(args)
        self.assertEqual(len(calls),2,'one child per mode, no decoding retries')
        result=json.loads(output.read_text())
        logs=[output.with_name(output.stem+'.'+mode+'.log').read_text() for mode in ('ordinary','profile')]
        return code,result,logs

    def assert_original_failure(self,code,result):
        self.assertEqual(code,2)
        self.assertFalse(result['instrumentation_action_parity'])
        for mode in ('ordinary','instrumented'):
            self.assertEqual(result[mode]['process_exit_code'],7)
            self.assertEqual(result[mode]['status'],'error')
            self.assertEqual(result[mode]['error'],ERROR_REPORT['error'])

    def test_non_utf8_stdout_preserves_original_error_and_exit_code(self):
        code,result,logs=self.run_case(b'stdout \xff\xfe\n',b'stderr intact\n')
        self.assert_original_failure(code,result)
        self.assertEqual(logs,['stdout \\xff\\xfe\nstderr intact\n']*2)

    def test_non_utf8_stderr_preserves_original_error_and_exit_code(self):
        code,result,logs=self.run_case(b'stdout intact\n',b'stderr \x80\n')
        self.assert_original_failure(code,result)
        self.assertEqual(logs,['stdout intact\nstderr \\x80\n']*2)

    def test_valid_unicode_and_text_newlines_remain_readable(self):
        code,result,logs=self.run_case('caf\u00e9\r\n\u96ea\r'.encode(),b'literal \\xff\n')
        self.assert_original_failure(code,result)
        self.assertEqual(logs,['caf\u00e9\n\u96ea\nliteral \\xff\n']*2)

    def test_binary_diagnostic_does_not_turn_complete_output_into_failure(self):
        code,result,logs=self.run_case(b'notice \xff\n',b'warning \xfe\n',complete_report(),0)
        self.assertEqual(code,0)
        self.assertTrue(result['instrumentation_action_parity'])
        self.assertEqual(logs,['notice \\xff\nwarning \\xfe\n']*2)

    def test_complete_report_cannot_hide_nonzero_exit(self):
        code,result,logs=self.run_case(b'notice \xff\n',b'',complete_report(),7)
        self.assertEqual(code,2)
        self.assertFalse(result['instrumentation_action_parity'])
        self.assertEqual(result['ordinary']['process_exit_code'],7)
        self.assertEqual(result['instrumented']['process_exit_code'],7)

    def test_malformed_report_recovery_composes_with_binary_diagnostic(self):
        raw=b'{"status":'
        code,result,logs=self.run_case(b'notice \xff\n',b'',raw)
        self.assertEqual(code,2)
        for mode in ('ordinary','instrumented'):
            report=result[mode]
            self.assertEqual(report['error']['type'],'InvalidChildReport')
            self.assertEqual(report['process_exit_code'],7)
            self.assertEqual(Path(report['invalid_report']['path']).read_bytes(),raw)
            self.assertEqual(report['invalid_report']['sha256'],p.digest(raw))
        self.assertEqual(logs,['notice \\xff\n']*2)

    def test_timeout_retention_remains_authoritative_with_binary_diagnostic(self):
        raw=json.dumps(ERROR_REPORT).encode()
        code,result,logs=self.run_case(b'notice \xff\n',b'stderr\n',raw,'timeout')
        self.assertEqual(code,2)
        self.assertFalse(result['instrumentation_action_parity'])
        for mode in ('ordinary','instrumented'):
            report=result[mode]
            self.assertEqual(report['status'],'process_timeout')
            self.assertIsNone(report['process_exit_code'])
            self.assertEqual(Path(report['timed_out_child_report']['path']).read_bytes(),raw)
        # TimeoutExpired carries bytes; its existing replacement display is unchanged.
        self.assertEqual(logs,['notice \ufffd\nstderr\n']*2)

    def test_actual_profiler_collects_both_passes_after_binary_actor_output(self):
        actor=self.root/'actor.py'
        actor.write_text('import os\nclass Agent:\n'
            '    def act(self,obs,cfg):\n'
            '        os.write(1,b"actor \\xff\\n")\n'
            '        os.write(2,b"diagnostic \\xfe\\n")\n'
            '        return {"market":[],"hand":[]}\n'
            'def make_agent():\n    return Agent()\n')
        workload=self.root/'workload.json'
        workload.write_text(json.dumps({'schema':'titan.profile.observations.v1','records':[
            {'observation':{'farms':[],'private':{},'market':{},'step':0,'player':0},
             'expected_action':{'market':[],'hand':[]}}]}))
        timing=Path(__file__).resolve().parent.parent/'cloud-combination-analysis/execution_timing.py'
        output=self.root/'actual.json'
        completed=subprocess.run([sys.executable,'-B',str(Path(p.__file__).resolve()),
            '--entrypoint',str(actor),'--timing-source',str(timing),'--replay',str(workload),
            '--max-decisions','1','--output',str(output)],capture_output=True,text=True,timeout=10)
        self.assertEqual(completed.returncode,0,completed.stderr)
        result=json.loads(output.read_text())
        self.assertTrue(result['instrumentation_action_parity'])
        for mode in ('ordinary','instrumented'):
            self.assertEqual(result[mode]['status'],'complete')
            self.assertEqual(result[mode]['process_exit_code'],0)
            self.assertEqual(result[mode]['expected_actions']['mismatches'],0)
            self.assertEqual(len(result[mode]['calls']),1)
        for mode in ('ordinary','profile'):
            log=output.with_name(output.stem+'.'+mode+'.log').read_text()
            self.assertIn('actor \\xff\n',log)
            self.assertIn('diagnostic \\xfe\n',log)


if __name__=='__main__':
    unittest.main(verbosity=2)
