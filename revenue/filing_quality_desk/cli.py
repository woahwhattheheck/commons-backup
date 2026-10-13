import argparse,json
from pathlib import Path
from .core import FilingQualityError
from .files import compile_dir,verify_dir
def main(argv=None):
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True)
    for name in ('compile','verify'):
        p=sub.add_parser(name);p.add_argument('--source',type=Path,required=True);p.add_argument('--policy',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=ap.parse_args(argv)
    try:
        (compile_dir if a.cmd=='compile' else verify_dir)(a.source,a.policy,a.out);print(json.dumps({'ok':True},sort_keys=True));return 0
    except (FilingQualityError,OSError) as e:
        print(json.dumps({'ok':False,'error':str(e)},sort_keys=True));return 2
if __name__=='__main__':raise SystemExit(main())
