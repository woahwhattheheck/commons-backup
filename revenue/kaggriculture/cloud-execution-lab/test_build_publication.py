# SPDX-License-Identifier: Apache-2.0
"""Real renderer/filesystem publication tests with a controlled source tree.

No policy or engine is executed. Faults are injected only at the file writer,
fsync, rename, or process-exit boundary; source mapping and rendering are real.
"""
import argparse
import errno
from contextlib import contextmanager
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

BUILDER = Path(__file__).with_name('build_integrated.py')
OBSERVED = {}


def load_builder(path, root):
    spec = importlib.util.spec_from_file_location('publication_subject', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = Path(root)
    return module


def populate(module):
    """Source bytes for exercising the real build graph, not a runnable agent."""
    root = module.ROOT
    (root/'exports').mkdir(parents=True)
    (root/module.RECORD).mkdir(parents=True)
    (root/(module.RECORD+'RELEASE.json')).write_text('{"fixture":"filesystem-only"}\n')
    for name in module.source_files().values():
        p = root/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(('# source fixture: '+name+'\n').encode())
    (root/'TITAN-CONFIG.json').write_text('{"seed": true}\n')
    (root/'TITAN-HISTORY-CONFIG.json').write_text('{}\n')
    p = root/'reference/titan-history/context.py'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b'# referenced history source fixture\n')


@contextmanager
def writer_fault(root, basename, kind, exception=None, observations=None):
    original = Path.open
    class Writer:
        def __init__(self, stream): self.stream = stream
        def __getattr__(self, name): return getattr(self.stream, name)
        def __enter__(self): self.stream.__enter__(); return self
        def __exit__(self, *args): return self.stream.__exit__(*args)
        def write(self, data):
            if observations is not None:
                observations.append((root/'exports/titan-current.tar.gz').read_bytes())
            if kind == 'observe': return self.stream.write(data)
            if kind == 'short': return self.stream.write(data[:7])
            if kind == 'zero': return 0
            if kind == 'none': return None
            self.stream.write(data[:max(1, len(data)//3)])
            self.stream.flush()
            if kind == 'exit': os._exit(73)
            raise exception
    def opened(path, mode='r', *args, **kwargs):
        stream = original(path, mode, *args, **kwargs)
        if ('w' in mode or 'x' in mode) and basename in path.name and path.is_relative_to(root):
            return Writer(stream)
        return stream
    with patch.object(Path, 'open', opened):
        yield


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='titan-publication-')
        self.addCleanup(self.directory.cleanup)
        # Use the same sibling layout as the repository so attributed package
        # sources outside cloud-execution-lab remain inside this fixture.
        self.root = Path(self.directory.name)/'cloud-execution-lab'
        self.root.mkdir()
        self.m = load_builder(BUILDER, self.root)
        populate(self.m)
        self.m.build_release()
        self.paths = [self.root/self.m.ARCHIVE,
                      self.root/(self.m.RECORD+'CURRENT-SOURCE.json'),
                      self.root/(self.m.RECORD+'CURRENT-ARCHIVE.json')]
        self.before = [p.read_bytes() for p in self.paths]
        self.changed = self.root/'main.py'
        self.changed.write_bytes(self.changed.read_bytes()+b'# changed source fixture\n')
        self.expected = self.m.render()
        self.history = self.root/'exports/historical'/('titan-'+hashlib.sha256(self.before[0]).hexdigest()+'.tar.gz')

    def unchanged(self):
        for path, before in zip(self.paths, self.before):
            self.assertTrue(path.read_bytes() == before, path.name+' was changed')

    def no_temps(self):
        self.assertEqual(list(self.root.rglob('.*.tmp')), [])

    def assert_archive(self, data):
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
            manifest = json.load(archive.extractfile('SOURCE.json'))
            for name, record in manifest['runtime'].items():
                body = archive.extractfile(name).read()
                self.assertEqual(hashlib.sha256(body).hexdigest(), record['sha256'])
                self.assertEqual(len(body), record['bytes'])

    def fail_write(self, name, kind='raise'):
        error = OSError('injected partial write')
        with writer_fault(self.root, name, kind, error):
            with self.assertRaises((OSError, ValueError)):
                self.m.build_release()
        self.unchanged(); self.no_temps()

    def test_success_preserves_exact_rendered_bytes_and_receipt(self):
        receipt = self.m.build_release()
        self.assertEqual(receipt, self.expected[2])
        self.assertEqual(self.paths[0].read_bytes(), self.expected[0])
        self.assertEqual(self.paths[1].read_bytes(), self.expected[1])
        expected_text = (json.dumps(receipt, indent=2)+'\n').replace('\n',os.linesep)
        self.assertEqual(self.paths[2].read_bytes(), expected_text.encode())
        self.assertEqual(self.history.read_bytes(), self.before[0])
        self.assertEqual(self.m.verify_current(), receipt)
        self.assert_archive(self.paths[0].read_bytes()); self.no_temps()
        OBSERVED['rendered'] = {'archive_sha256':hashlib.sha256(self.expected[0]).hexdigest(),
                               'source_files':receipt['runtime_files'], 'bytes':len(self.expected[0])}

    def test_archive_partial_write_keeps_previous_bundle(self):
        self.fail_write('titan-current.tar.gz')

    def test_manifest_partial_write_keeps_previous_bundle(self):
        self.fail_write('CURRENT-SOURCE.json')

    def test_receipt_partial_write_keeps_previous_bundle(self):
        self.fail_write('CURRENT-ARCHIVE.json')

    def test_historical_partial_write_never_publishes_truncation(self):
        self.fail_write(self.history.name)
        self.assertFalse(self.history.exists())

    def test_short_writes_complete_all_bytes(self):
        for name in ('titan-current.tar.gz', 'CURRENT-SOURCE.json', 'CURRENT-ARCHIVE.json'):
            with self.subTest(name=name):
                with writer_fault(self.root, name, 'short'):
                    try: self.m.build_release()
                    except Exception as error: self.fail('short write not completed: '+repr(error))
                self.assertEqual(self.paths[0].read_bytes(), self.expected[0])
                self.assertEqual(self.paths[1].read_bytes(), self.expected[1])
                self.assertEqual(json.loads(self.paths[2].read_bytes()), self.expected[2])
        self.no_temps()

    def test_zero_progress_keeps_previous_bundle(self):
        self.fail_write('titan-current.tar.gz', 'zero')

    def test_none_progress_keeps_previous_bundle(self):
        self.fail_write('CURRENT-SOURCE.json', 'none')

    def test_keyboard_interrupt_keeps_previous_bundle_and_identity(self):
        error = KeyboardInterrupt('injected interruption')
        with writer_fault(self.root, 'CURRENT-SOURCE.json', 'raise', error):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.m.build_release()
        self.assertIs(caught.exception, error); self.unchanged(); self.no_temps()

    def test_original_io_exception_identity_is_preserved(self):
        error = OSError('original io exception')
        with writer_fault(self.root, 'CURRENT-SOURCE.json', 'raise', error):
            with self.assertRaises(OSError) as caught: self.m.build_release()
        self.assertIs(caught.exception, error); self.unchanged(); self.no_temps()

    def test_fsync_failure_keeps_previous_bundle(self):
        error = OSError('injected fsync failure')
        with patch.object(os, 'fsync', side_effect=error):
            with self.assertRaises(OSError) as caught: self.m.build_release()
        self.assertIs(caught.exception, error); self.unchanged(); self.no_temps()

    def test_all_files_are_fsynced_before_first_promotion(self):
        events=[]; sync=os.fsync; replace=os.replace
        def synced(fd): events.append('sync'); return sync(fd)
        def promoted(a,b): events.append(Path(b).name); return replace(a,b)
        with patch.object(os,'fsync',synced), patch.object(os,'replace',promoted):
            self.m.build_release()
        self.assertEqual(events[:4],['sync']*4)
        self.assertEqual(events[4:],[self.history.name,'titan-current.tar.gz','CURRENT-SOURCE.json','CURRENT-ARCHIVE.json'])
        self.no_temps()

    def test_open_failure_before_last_staging_preserves_bundle(self):
        original=Path.open
        error=OSError(errno.EMFILE, 'injected file-descriptor exhaustion')
        def opened(path, mode='r', *args, **kwargs):
            if ('w' in mode or 'x' in mode) and 'CURRENT-ARCHIVE.json' in path.name:
                raise error
            return original(path,mode,*args,**kwargs)
        with patch.object(Path,'open',opened):
            with self.assertRaises(OSError) as caught: self.m.build_release()
        self.assertIs(caught.exception, error)
        self.assertEqual(caught.exception.errno, errno.EMFILE)
        self.unchanged(); self.no_temps()

    def test_archive_never_exposes_partial_bytes_during_write(self):
        observations=[]
        with writer_fault(self.root,'titan-current.tar.gz','observe',observations=observations):
            self.m.build_release()
        self.assertTrue(observations)
        self.assertTrue(all(x==self.before[0] for x in observations))
        self.assert_archive(self.paths[0].read_bytes()); self.no_temps()

    def test_rename_failure_keeps_old_receipt_and_complete_archives(self):
        replace=os.replace
        def promoted(source,target):
            if Path(target).name=='CURRENT-SOURCE.json': raise OSError('injected rename failure')
            return replace(source,target)
        with patch.object(os,'replace',promoted):
            with self.assertRaises(OSError): self.m.build_release()
        self.assertEqual(self.paths[2].read_bytes(),self.before[2])
        self.assertEqual(self.history.read_bytes(),self.before[0])
        self.assert_archive(self.paths[0].read_bytes())
        with self.assertRaises(ValueError): self.m.verify_current()
        self.no_temps()
        self.m.build_release(); self.assertEqual(self.m.verify_current(),self.expected[2])
        # Rerunning after partial promotion must retain the original historical copy.
        self.assertEqual(self.history.read_bytes(),self.before[0])

    def test_historical_collision_never_touches_current(self):
        self.history.parent.mkdir(parents=True,exist_ok=True)
        self.history.write_bytes(b'preexisting differing bytes')
        with self.assertRaisesRegex(ValueError,'Historical archive identity collision'):
            self.m.build_release()
        self.unchanged(); self.no_temps()
        self.assertEqual(self.history.read_bytes(),b'preexisting differing bytes')

    def test_completed_historical_file_is_not_rewritten(self):
        self.history.parent.mkdir(parents=True,exist_ok=True)
        self.history.write_bytes(self.before[0]); os.utime(self.history,ns=(1000000000,1000000000))
        before=self.history.stat().st_mtime_ns
        self.m.build_release()
        self.assertEqual(self.history.stat().st_mtime_ns,before)
        self.assertEqual(self.history.read_bytes(),self.before[0])

    def test_existing_output_modes_survive_replacement(self):
        if os.name!='posix': self.skipTest('POSIX mode-bit check')
        modes=[0o640,0o600,0o644]
        for p,mode in zip(self.paths,modes):p.chmod(mode)
        self.m.build_release()
        self.assertEqual([stat.S_IMODE(p.stat().st_mode) for p in self.paths],modes)

    def test_identical_rebuild_adds_no_historical_generation(self):
        self.changed.write_bytes(self.changed.read_bytes().replace(b'# changed source fixture\n',b''))
        self.m.build_release(); self.unchanged(); self.no_temps()
        self.assertEqual(list((self.root/'exports').rglob('titan-*.tar.gz')),[self.paths[0]])

    def test_hard_exit_during_staging_preserves_previous_bundle(self):
        code='''import importlib.util, pathlib, sys
s=importlib.util.spec_from_file_location('suite',sys.argv[1]);t=importlib.util.module_from_spec(s);s.loader.exec_module(t)
r=pathlib.Path(sys.argv[3]);m=t.load_builder(pathlib.Path(sys.argv[2]),r)
with t.writer_fault(r,'CURRENT-SOURCE.json','exit'):m.build_release()
'''
        process=subprocess.run([sys.executable,'-B','-c',code,str(Path(__file__).resolve()),str(BUILDER.resolve()),str(self.root)],capture_output=True,timeout=20)
        self.assertEqual(process.returncode,73,process.stderr.decode())
        self.unchanged(); self.assert_archive(self.paths[0].read_bytes())
        OBSERVED['hard_exit']={'exit_code':73,'previous_bundle_preserved':True,
                               'orphan_staging_files':len(list(self.root.rglob('.*.tmp')))}
        # Hard exits cannot run cleanup. A normal retry ignores unreferenced stages.
        self.m.build_release(); self.assertEqual(self.m.verify_current(),self.expected[2])

    def test_source_change_is_still_detected_by_existing_check(self):
        with self.assertRaises(ValueError):self.m.verify_current()
        self.m.build_release();self.changed.write_bytes(b'# another source change\n')
        with self.assertRaises(ValueError):self.m.verify_current()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--builder',type=Path,default=BUILDER)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args();BUILDER=args.builder
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PublicationTests))
    report={'scope':'real build renderer/filesystem on controlled source tree; no policy/game execution',
            'builder_sha256':hashlib.sha256(BUILDER.read_bytes()).hexdigest(),
            'test_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'tests_run':result.testsRun,'failures':[str(t) for t,_ in result.failures],
            'errors':[str(t) for t,_ in result.errors], 'skipped':[str(t) for t,_ in result.skipped],
            'successful':result.wasSuccessful(),'witnesses':OBSERVED,'full_games':0}
    if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
    sys.exit(not result.wasSuccessful())
