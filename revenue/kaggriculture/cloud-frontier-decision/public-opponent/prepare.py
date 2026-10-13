"""Prepare reviewed exact fixture using existing pack/loader and panel compiler."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',type=Path,required=True)
    args=p.parse_args();runtime=args.runtime.resolve()
    source=HERE/'submission.py'
    assert hashlib.sha256(source.read_bytes()).hexdigest()=='df4e899ad535754cf2ddbd3c16e48085916b0cd2baa5182a1a2cfc6a856abae5'
    panel=ROOT/'cloud-frontier-policy/next-panel'
    subprocess.run([sys.executable,'-B',str(panel/'prepare.py'),'--runtime',str(runtime)],check=True)
    spec=importlib.util.spec_from_file_location('existing_pack',ROOT/'cloud-pack/pack.py')
    pack=importlib.util.module_from_spec(spec);sys.modules[spec.name]=pack;spec.loader.exec_module(pack)
    adapter=runtime/'breaking-tie-adapter.py';pack.write_adapter(adapter,source)
    prefix='import sys\n'+f'sys.path.insert(0, {str(panel)!r})\n'+'from offline import restrict\nrestrict()\n'
    adapter.write_text(prefix+adapter.read_text())


if __name__=='__main__': main()
