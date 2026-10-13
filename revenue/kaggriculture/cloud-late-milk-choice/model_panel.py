# SPDX-License-Identifier: Apache-2.0
"""Source-bound entry binding for the existing late-milk panel/evaluator.

The original panel owns the experiment loop, recording and result checkpoints.
This file supplies the model/control entry points; it introduces no simulator.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
from pathlib import Path
import sys
import panel


def load(path, name):
    """Execute one source snapshot, ignoring bytecode and restoring failed loads.

    Keep normal module metadata and registration for dataclasses and relative
    imports. This binds this file only; transitive imports retain their existing
    import behavior. Callers continue to own source pins and isolated names.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    code = compile(Path(path).read_bytes(), spec.origin, 'exec', dont_inherit=True)
    module = importlib.util.module_from_spec(spec)
    missing = object()
    previous = sys.modules.get(name, missing)
    sys.modules[name] = module
    try:
        exec(code, module.__dict__)
    except BaseException:
        # Include cancellation; a partial module must not replace an old one.
        if previous is missing:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
        raise
    return module


def source(path):
    body = Path(path).read_bytes()
    return {'sha256': hashlib.sha256(body).hexdigest(),
            'git_blob': hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()}


def entry_factory(*, source_root, engine_dir, oracle_path, replay_path, seconds):
    """Prepare exact source paths once; every worker constructs one live actor."""
    def write_entry(path, *, sell_dir, implementation, enabled, telemetry):
        path.write_text(
            '# Generated source-bound model/control entry.\n'
            'import json\nimport sys\nfrom pathlib import Path\n'
            f'sys.path.insert(0, {str(sell_dir)!r})\n'
            f'sys.path.insert(0, {str(implementation)!r})\n'
            'from scheduler import SellScheduler\n'
            'from model_choice import wrap_model_sell\n'
            'from model_panel import load\n'
            f'_ev=load({str(source_root/"cloud-eval/evaluate.py")!r}, "model_entry_evaluator")\n'
            f'_engine,_=_ev.get_engine(Path({str(engine_dir)!r}),'
            f'loader=Path({str(source_root/"20260907-offline-agent/evaluate.py")!r}),prepare=False)\n'
            f'_oracle=load({str(oracle_path)!r},"model_entry_oracle")\n'
            f'_physical=load({str(replay_path)!r},"model_entry_replay")\n'
            '_scheduler=SellScheduler()\n'
            '_actor=wrap_model_sell(_scheduler,_engine,_oracle.simulate_bundle,_oracle.Scenario,\n'
            f'    _physical.replay_routes,_physical.ReplayLimits,enabled={enabled!r},seconds={seconds!r})\n'
            f'_telemetry=Path({str(telemetry)!r})\n'
            'def agent(obs,configuration=None):\n'
            '    action=_actor.act(obs,configuration)\n'
            "    if obs['step'] in (0,433,576,577,718):\n"
            "        row={'step':obs['step'],'route':_actor.controller.cur,'choice':_actor.last_choice,\n"
            "             'live_calls':_actor.calls,'milk_inventory':obs['market']['inventory']['MILK']}\n"
            "        with _telemetry.open('a',encoding='utf-8') as f:f.write(json.dumps(row,sort_keys=True)+'\\n')\n"
            '    return action\n', encoding='utf-8')
    return write_entry


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--engine-dir',type=Path,required=True)
    parser.add_argument('--oracle',type=Path,required=True)
    parser.add_argument('--physical-replay',type=Path,required=True)
    parser.add_argument('--seeds',required=True)
    parser.add_argument('--seconds',type=float,default=0.6)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    root=args.source_root.resolve()
    for key in ('engine_dir','oracle','physical_replay','output'):
        setattr(args,key,getattr(args,key).resolve())
    here=Path(__file__).resolve().parent
    closure={'model_choice.py':source(here/'model_choice.py'),
             'model_panel.py':source(Path(__file__)),
             'physical_replay.py':source(args.physical_replay),
             'oracle.py':source(args.oracle)}
    forwarded=['panel.py','--evaluator',str(root/'cloud-eval/evaluate.py'),
               '--loader',str(root/'20260907-offline-agent/evaluate.py'),
               '--engine-dir',str(args.engine_dir),
               '--sell-dir',str(root/'cloud-titan-composition/vendor/sell'),
               '--arlene',str(root/'cloud-frontier-policy/next-panel/vendor/arlene.py'),
               '--apex',str(root/'cloud-frontier-policy/next-panel/vendor/apex/main.py'),
               '--seeds',args.seeds,'--output',str(args.output)]
    previous=sys.argv
    try:
        sys.argv=forwarded
        return panel.main(entry_factory=entry_factory(source_root=root,engine_dir=args.engine_dir,
            oracle_path=args.oracle,replay_path=args.physical_replay,seconds=args.seconds),
            arms=(('frozen_sell_control',False),('modeled_late_choice',True)),
            extra_metadata={'model_source_closure':closure,'model_seconds':args.seconds,
                'classification_detail':'new development on explicit repaired replay dependency; original model panel not recovered'})
    finally:
        sys.argv=previous

if __name__=='__main__':raise SystemExit(main())
