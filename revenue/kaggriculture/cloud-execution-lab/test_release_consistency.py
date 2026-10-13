# SPDX-License-Identifier: Apache-2.0
"""Discriminating release tests; no game panel."""
import hashlib,json,shutil,subprocess,sys,tarfile,tempfile,unittest
from pathlib import Path
import build_integrated as b

class ReleaseTests(unittest.TestCase):
 def test_default_build_and_history_preservation(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'cloud-execution-lab';root.mkdir()
   for p in set(b.source_files().values())|{'build_integrated.py',b.RECORD+'RELEASE.json'}:
    dest=root/p;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(b.ROOT/p,dest)
   (root/'exports').mkdir();old=b'historical evidence sentinel';(root/b.ARCHIVE).write_bytes(old)
   named=root/'exports/integrated-selected-v1.tar.gz';named.write_bytes(b'unchanged control')
   def call(*args):return subprocess.run([sys.executable,str(root/'build_integrated.py'),*args],capture_output=True,text=True)
   out=call();self.assertEqual(out.returncode,0,out.stderr)
   receipt=json.loads(out.stdout);self.assertEqual(receipt['path'],b.ARCHIVE)
   self.assertEqual(named.read_bytes(),b'unchanged control')
   self.assertEqual((root/'exports/historical'/('titan-'+hashlib.sha256(old).hexdigest()+'.tar.gz')).read_bytes(),old)
   with tarfile.open(root/b.ARCHIVE) as t:
    self.assertEqual(t.extractfile('main.py').read(),(b.ROOT/'main.py').read_bytes())
    manifest=json.load(t.extractfile('SOURCE.json'))
    for name,row in manifest['runtime'].items():
     self.assertEqual(t.extractfile(name).read(),(root/row['source_path']).read_bytes())
    self.assertIn('terminal_history_join.py',t.getnames())
    self.assertIn('funded_payback.py',t.getnames())
    self.assertIn('seed_retry.py',t.getnames())
    self.assertIn('early_capital.py',t.getnames())
    self.assertIn('integrated_main.py',t.getnames())
    self.assertIn('integrated_parent.py',t.getnames())
    self.assertIn('checks/test_early_capital.py',t.getnames())
    self.assertIn('checks/test_config_metadata_boundary.py',t.getnames())
    self.assertEqual(manifest['runtime']['seed_retry.py']['source_path'],
                     '../cloud-committed-seed-retry/seed_retry.py')
    self.assertTrue(any(p.startswith('reference/titan-history/') for p in t.getnames()))
    unpacked=Path(tmp)/'packaged';t.extractall(unpacked)
    packaged=subprocess.run(
        [sys.executable,str(unpacked/'checks/test_config_metadata_boundary.py')],
        cwd=unpacked,capture_output=True,text=True)
    self.assertEqual(packaged.returncode,0,packaged.stdout+packaged.stderr)
   first=(root/b.ARCHIVE).read_bytes();self.assertEqual(call().returncode,0);self.assertEqual(first,(root/b.ARCHIVE).read_bytes())
   for target in ['main.py','TITAN-CONFIG.json',b.RECORD+'CURRENT-SOURCE.json',b.RECORD+'CURRENT-ARCHIVE.json',b.ARCHIVE,'reference/titan-history/selected_action_history.py']:
    p=root/target;original=p.read_bytes()
    if target.endswith('CURRENT-ARCHIVE.json'):
     changed=json.loads(original);changed['path']='exports/integrated-selected-v1.tar.gz';p.write_text(json.dumps(changed))
    else:p.write_bytes(original+b' ')
    self.assertNotEqual(call('--check').returncode,0,target)
    p.write_bytes(original)
   self.assertEqual(call('--check').returncode,0)
   for flag in ['--history-v2','--entry-clock-v3','--version']:
    self.assertNotEqual(call(flag).returncode,0)

 def test_live_current_includes_early_capital(self):
  receipt=b.verify_current()
  self.assertEqual(receipt['path'],b.ARCHIVE)
  with tarfile.open(b.ROOT/b.ARCHIVE) as t:
   regular=[m.name for m in t.getmembers() if m.isfile()]
   names=t.getnames()
   runtime=[name for name in regular if name != 'SOURCE.json']
   self.assertEqual(receipt['runtime_files'], len(runtime))
   self.assertIn('SOURCE.json', regular)
   self.assertEqual(len(regular), receipt['runtime_files'] + 1)
   self.assertIn('early_capital.py',names)
   self.assertIn('integrated_main.py',names)
   self.assertIn('integrated_parent.py',names)
   self.assertIn('checks/test_early_capital.py',names)
   self.assertIn('checks/test_final_market_pressure_entrypoint.py',names)
   self.assertIn('checks/test_entrypoint_deadline.py',names)
   self.assertIn('checks/test_config_metadata_boundary.py',names)
   packaged_early=t.extractfile('early_capital.py').read()
   self.assertEqual(packaged_early,(b.ROOT/'early_capital.py').read_bytes())
   self.assertIn(b'def _market_limit',packaged_early)
   self.assertIn(b"'revision': 'v4-executable-funding'",packaged_early)
   self.assertIn(b'def _certified_funding',packaged_early)
   self.assertIn(b'def _project_post_unit_private',packaged_early)
   self.assertNotIn(b"'revision': 'v2-order-only'",packaged_early)
   predecessor=b.ROOT/'exports/historical'/'titan-5f6a4153e502713b9467776eafe7464af650584149173ce7507a31a1b2af60f1.tar.gz'
   self.assertEqual(hashlib.sha256(predecessor.read_bytes()).hexdigest(),
                    '5f6a4153e502713b9467776eafe7464af650584149173ce7507a31a1b2af60f1')
   with tarfile.open(predecessor) as old:
    old_early=old.extractfile('early_capital.py').read()
   self.assertNotEqual(old_early,packaged_early)
   self.assertIn(b"'revision': 'v2-order-only'",old_early)
   config=json.load(t.extractfile('TITAN-CONFIG.json'))
   self.assertTrue(config.get('early_capital'))
   self.assertIn(b'def _early_capital_selected',t.extractfile('titan_runtime.py').read())
   main=t.extractfile('main.py').read()
   self.assertEqual(main,(b.ROOT/'main.py').read_bytes())
   self.assertIn(b'class FinalPressureAgent',main)
   self.assertIn(b'_final_pressure_boundary',main)
   self.assertIn(b'def _entrypoint_fallback',main)
   self.assertIn(b'def _runtime_feature_data',main)
   self.assertIn(b'entrypoint_guard',main)

 def test_live_package_matches_documentation_and_keeps_predecessor(self):
  receipt=b.verify_current()
  self.assertEqual(receipt['path'],b.ARCHIVE)
  historical=b.ROOT/'exports/historical'/'titan-17f536087b3a6baf4ae1222a051285766a3ea8c2ca5af6edc190d4f527e12b86.tar.gz'
  self.assertEqual(hashlib.sha256(historical.read_bytes()).hexdigest(),
                   '17f536087b3a6baf4ae1222a051285766a3ea8c2ca5af6edc190d4f527e12b86')
  with tarfile.open(historical) as old, tarfile.open(b.ROOT/b.ARCHIVE) as cur:
   for name in ('TITAN-RELEASE.md','reference/decision/README.md'):
    current_bytes=(b.ROOT/name).read_bytes()
    packaged=cur.extractfile(name).read()
    self.assertEqual(packaged, current_bytes)
    predecessor=old.extractfile(name).read()
    self.assertNotEqual(predecessor, current_bytes)
    self.assertFalse(name.endswith('.py'))


 def test_live_current_packages_landed_evaluator_and_keeps_predecessor(self):
  receipt=b.verify_current()
  self.assertEqual(receipt['path'],b.ARCHIVE)
  live=(b.ROOT/'reference/evaluator/evaluate.py').read_bytes()
  live_blob=hashlib.sha1(b'blob '+str(len(live)).encode()+b'\0'+live).hexdigest()
  self.assertEqual(live_blob,'6d9edcc4ec5eeee22c8a6faec6ddd208a9a2e9e7')
  with tarfile.open(b.ROOT/b.ARCHIVE) as cur:
   packaged=cur.extractfile('checks/reference/evaluator/evaluate.py').read()
  self.assertEqual(packaged,live)
  predecessor=b.ROOT/'exports/historical'/'titan-4ba742a88d73d483cc844e1007ade5e02c4be198f7383abbbbb32dff1860eac5.tar.gz'
  self.assertEqual(hashlib.sha256(predecessor.read_bytes()).hexdigest(),
                   '4ba742a88d73d483cc844e1007ade5e02c4be198f7383abbbbb32dff1860eac5')
  with tarfile.open(predecessor) as old:
   old_eval=old.extractfile('checks/reference/evaluator/evaluate.py').read()
  self.assertNotEqual(old_eval,packaged)
  old_blob=hashlib.sha1(b'blob '+str(len(old_eval)).encode()+b'\0'+old_eval).hexdigest()
  self.assertEqual(old_blob,'1fb6b655bb4ca1e1684be165a8ef513e2e6c2325')

if __name__=='__main__':unittest.main()
