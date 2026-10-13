"""Run a retained, hash-pinned read-only product test subset and retain evidence."""
from __future__ import annotations
import argparse,hashlib,json,os,platform,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parent/'lacsd-15865')
parser.add_argument('--output',type=Path,required=True,help='New output directory; must not exist')
parser.add_argument('--worker',default='UNSPECIFIED_REPLAY_OPERATOR',help='Declared operator; not authenticated by this script')
parser.add_argument('--execution-context',default='unspecified local replay',help='Declared compute context; not provider-authenticated')
args=parser.parse_args()
root=args.source.resolve(); evidence=args.output.resolve(); evidence.parent.mkdir(parents=True,exist_ok=True); evidence.mkdir(exist_ok=False)
expected={
 'lacsd_04252.py':'a5f2f9730724f81fc0202519601e02fe63340dd6',
 'test_lacsd_04252.py':'bff86c95ea65e242c5c2bf8a3673651bb00f0250',
 'fixtures/manifest.json':'a11113306aa62274e17e57f48f5d7056bfe9c558',
 'fixtures/ap_cases.json':'4b5d070864bb6db3ebae439894283d216c965bd7',
 'README.md':'5249a545558c5a78ae5e725193f3e1aee4d1cb68',
}
def capture():
 out={}
 for name,expect in expected.items():
  raw=(root/name).read_bytes(); blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
  if blob!=expect: raise RuntimeError(f'byte mismatch: {name}')
  out[name]={'git_blob_sha1':blob,'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw)}
 return out
before=capture()
receipt={'schema':'z-tern/exact-source-execution/v1','worker':args.worker,'operator_identity_is_declared':True,'execution_context':args.execution_context,
 'repo':'woahwhattheheck/commons','pr':15865,'head_sha':'d6ba9099718fab8b308daeab7c7b57d1e97aa786',
 'source_root':'revenue/opportunities/lacsd_04252_ap_automation',
 'subset_only':True,'subset_complete_for_requested_commands':True,
 'execution_class':'hash-pinned source-closure replay; not full Git checkout, provider authentication, or hosted CI',
 'started_at_utc':datetime.now(timezone.utc).isoformat(),
 'machine':{'python':sys.version,'executable':sys.executable,'platform':platform.platform(),'machine':platform.machine(),'cpu_count':os.cpu_count()},
 'sources_before':before,'commands':[],
 'remote_mutations':{'slack_post':False,'github_comment':False,'github_source':False,'github_merge':False,'external_outreach':False}}
commands=[('py_compile',[sys.executable,'-m','py_compile','lacsd_04252.py','test_lacsd_04252.py']),('normal',[sys.executable,'-m','unittest','-v','test_lacsd_04252.py']),('optimized',[sys.executable,'-O','-m','unittest','-v','test_lacsd_04252.py'])]
for name,cmd in commands:
 start=time.monotonic(); proc=subprocess.run(cmd,cwd=root,capture_output=True,timeout=30)
 (evidence/(name+'.stdout.log')).write_bytes(proc.stdout);(evidence/(name+'.stderr.log')).write_bytes(proc.stderr)
 row={'name':name,'argv':cmd,'cwd':str(root),'returncode':proc.returncode,'elapsed_seconds':round(time.monotonic()-start,6),'stdout_sha256':hashlib.sha256(proc.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(proc.stderr).hexdigest()}
 receipt['commands'].append(row); print(name,'exit',proc.returncode);print(proc.stderr.decode()[-350:])
receipt['sources_after']=capture();receipt['source_unchanged']=before==receipt['sources_after'];receipt['completed_at_utc']=datetime.now(timezone.utc).isoformat();receipt['all_commands_passed']=all(row['returncode']==0 for row in receipt['commands'])
(evidence/'execution_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
if not receipt['all_commands_passed']: raise SystemExit(1)
