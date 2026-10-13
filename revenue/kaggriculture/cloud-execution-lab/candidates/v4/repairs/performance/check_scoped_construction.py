# SPDX-License-Identifier: Apache-2.0
"""Executable constructor, cache, optimizer and funding lifetime contracts.

The four source surfaces execute in the native dependency root. Nested donor
copies are relocated-source controls, not claims that cold routes are active.
Only scratch modules are instrumented; cyclic GC is disabled inside isolated
liveness probes and restored. No production GC changes or network calls.
"""
from __future__ import annotations
import argparse
import contextlib
import copy
import functools
import gc
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import signal
import subprocess
import tempfile
import sys
import threading
import time
import types
import unittest
import weakref
from collections import Counter
from compose_scoped_constructor import compose, git_blob, BASE, CANDIDATE, IMPORT, authenticate_helper

SURFACES = {
    'selected_sell_core.py': 'f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3',
    'scheduler.py': 'a483b24dd72b580d7d8811636b54d2d44f391575',
    'reference/titan-current/latest/selected_sell_core.py': 'f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3',
    'reference/titan-current/vendor/sell/scheduler.py': '97085acebd7268e87a09e4b5c1bf7d049038cb25',
}
MANIFEST_SHA256 = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
STATS = Counter()
RUNTIME = None
HELPER_BYTES = None
EXTRA = None
MUTANT = None
SOURCES = {}


def authenticate_runtime(root):
    manifest = (root/'SOURCE.json').read_bytes()
    if hashlib.sha256(manifest).hexdigest() != MANIFEST_SHA256:
        raise ValueError('checked native SOURCE identity mismatch')
    entries = json.loads(manifest)['runtime']
    for name, record in entries.items():
        data = (root/name).read_bytes()
        if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('native member mismatch: ' + name)
    if len(entries) != 109:
        raise ValueError('unexpected native member count')
    for name, expected in SURFACES.items():
        if git_blob((root/name).read_bytes()) != expected:
            raise ValueError('native source mismatch: ' + name)
    return len(entries)


def helper_module():
    module = types.ModuleType('scoped_method_cache')
    module.__file__ = '<authenticated-quickstep>'
    text = HELPER_BYTES.decode()
    if MUTANT == 'strong_owner':
        text = text.replace('owner_ref = ref(method.__self__)', 'owner_ref = lambda: method.__self__')
    elif MUTANT == 'wrong_limit':
        text = text.replace('@lru_cache(maxsize=maxsize)', '@lru_cache(maxsize=1)')
    elif MUTANT == 'wrong_result':
        text = text.replace('return function(owner, *args, **kwargs)', 'return (0, 0)')
    elif MUTANT == 'swallow':
        text = text.replace('return function(owner, *args, **kwargs)',
                            'try:\n            return function(owner, *args, **kwargs)\n        except BaseException:\n            return None')
    exec(compile(text, module.__file__, 'exec'), module.__dict__)
    sys.modules['scoped_method_cache'] = module
    return module


def load_surface(surface='selected_sell_core.py', changed=True):
    helper = helper_module()
    data = SOURCES[surface]
    if changed:
        data, _ = compose(data, HELPER_BYTES)
        if MUTANT in ('retain_single', 'retain_joint'):
            name = MUTANT.removeprefix('retain_')
            data = data.replace(('scoped_method_cache(self._'+name+',maxsize=8192)').encode(),
                                ('lru_cache(maxsize=8192)(self._'+name+')').encode())
    module = types.ModuleType('_spindle_' + str(time.time_ns()))
    # Native nested files have loader-relative references. Relocate only their
    # dependency root for cold-source controls; execute their complete bytes.
    filename = 'scheduler.py' if surface.endswith('scheduler.py') else 'selected_sell_core.py'
    module.__file__ = str(RUNTIME/filename)
    exec(compile(data, module.__file__, 'exec'), module.__dict__)
    return module, helper


@contextlib.contextmanager
def isolated_gc():
    enabled, thresholds, callbacks = gc.isenabled(), gc.get_threshold(), list(gc.callbacks)
    gc.collect()
    gc.disable()
    try:
        yield
    finally:
        gc.collect()
        if enabled:
            gc.enable()
        else:
            gc.disable()
        if gc.get_threshold() != thresholds or gc.callbacks != callbacks:
            raise AssertionError('GC configuration was changed')


def path_args():
    return ('WOOL', 10000, None, ['YARN_STORE'], {}, 241, 249)


def optimizer_args(rule='strict', item='WOOL', horizon=8, inventory=10000):
    now = 241
    return dict(item=item, quantity=4, inventory=inventory, params=None,
                shops=['YARN_STORE']*4+['FARMERS_MARKET','SMOOTHIE_SHOP'],
                config={'sellAcceptanceRule':rule,'sellDownsideBound':200.0},
                now=now, dates=sorted({now,now+min(1,horizon),now+horizon}),
                reference=((now,4),), rival_quantity=3, minimum_now=0, last=718)


class Cancel(BaseException):
    pass


def constructor_probe(module, helper, *, trip=0, phase='before', opcode=False, timer=False):
    original = module.MarketPath
    refs, counts = [], Counter()
    class Observed(original):
        def __new__(cls, *a, **kw):
            instance = super().__new__(cls)
            refs.append(weakref.ref(instance))
            return instance
    original_lru, original_helper_lru = module.lru_cache, helper.lru_cache
    previous_trace = sys.gettrace()
    def cache(*a, **kw):
        decorator = functools.lru_cache(*a, **kw)
        def install(function):
            counts['installs'] += 1
            hit = counts['installs'] == trip
            if hit and timer:
                signal.setitimer(signal.ITIMER_REAL, 0.001)
                time.sleep(0.02)
            if hit and phase == 'before':
                raise Cancel('constructor boundary')
            result = decorator(function)
            if hit and phase == 'after':
                raise Cancel('constructor boundary')
            return result
        return install
    def trace(frame, event, arg):
        selected = ((frame.f_code.co_name == '__init__' and frame.f_globals is module.__dict__)
                    or frame.f_globals is helper.__dict__)
        if selected:
            frame.f_trace_opcodes = True
        if event == 'call':
            return trace
        if selected and event == 'opcode':
            counts['opcodes'] += 1
            if counts['opcodes'] == trip:
                raise Cancel('opcode boundary')
        return trace
    raised = False
    module.MarketPath = Observed
    try:
        if opcode:
            sys.settrace(trace)
        else:
            module.lru_cache = helper.lru_cache = cache
        try:
            owner = module.MarketPath(*path_args())
            del owner
        except Cancel:
            raised = True
    finally:
        sys.settrace(previous_trace)
        module.lru_cache, helper.lru_cache = original_lru, original_helper_lru
        module.MarketPath = original
    alive = sum(ref() is not None for ref in refs)
    gc.collect()
    if any(ref() is not None for ref in refs):
        raise AssertionError('probe or traceback retains owner after collection')
    return raised, alive, dict(counts)


class Construction(unittest.TestCase):
    def test_01_composition_preserves_every_other_byte(self):
        for surface, data in SOURCES.items():
            output, receipt = compose(data, HELPER_BYTES)
            self.assertEqual(output.decode().replace(IMPORT,'',1).replace(CANDIDATE,BASE,1),data.decode())
            again, metadata = compose(output, HELPER_BYTES)
            self.assertEqual(again, output)
            self.assertEqual(metadata['state'],'already_applied')
            peer = data + b'\n# unrelated peer bytes\n'
            self.assertEqual(compose(peer,HELPER_BYTES)[0],output+b'\n# unrelated peer bytes\n')
            STATS['composition_surfaces'] += 1

    def test_02_constructor_source_and_helper_drift_refused(self):
        data = SOURCES['selected_sell_core.py']
        for changed in (data.replace(b'maxsize=8192',b'maxsize=8193',1),
                        data.replace(b'class MarketPath:',b'class OtherPath:'),
                        data.replace(b'def _joint(',b'def other('),
                        data.replace(b'    def _single(',b'    @staticmethod\n    def _single('),
                        data.replace(b'from functools import lru_cache',b'# absent import'),
                        data+b'\n# scoped_method_cache mixed\n'):
            with self.assertRaises((ValueError,SyntaxError)):
                compose(changed,HELPER_BYTES)
            STATS['source_rejections'] += 1
        with self.assertRaises(ValueError):
            compose(data,HELPER_BYTES+b'\n')
        STATS['helper_rejections'] += 1

    def test_03_all_cache_install_boundaries(self):
        with isolated_gc():
            for surface in SOURCES:
                for changed in (False,True):
                    module, helper = load_surface(surface,changed)
                    observed=[]
                    for phase in ('before','after'):
                        for trip in (1,2,3):
                            raised, alive, counts=constructor_probe(module,helper,trip=trip,phase=phase)
                            self.assertTrue(raised)
                            self.assertEqual(counts['installs'],trip)
                            observed.append(alive)
                            if changed:
                                self.assertEqual(alive,0, surface+' retains partial model')
                            STATS['install_cancellation_sites'] += 1
                    if not changed:
                        self.assertEqual(observed,[0,0,1,0,0,1])
                        STATS['baseline_install_retention_witnesses'] += sum(observed)

    def test_04_every_constructor_and_helper_opcode_cut(self):
        with isolated_gc():
            for surface in SOURCES:
                for changed in (False,True):
                    module, helper = load_surface(surface,changed)
                    constructor_probe(module,helper,opcode=True)
                    _,normal_alive,counts=constructor_probe(module,helper,opcode=True)
                    count=counts['opcodes']
                    self.assertGreater(count,40)
                    self.assertEqual(normal_alive,0 if changed else 1)
                    retained=0
                    for trip in range(1,count+1):
                        raised,alive,counts=constructor_probe(module,helper,trip=trip,opcode=True)
                        self.assertTrue(raised, 'opcode site not reached')
                        self.assertEqual(counts['opcodes'],trip)
                        if changed:
                            self.assertEqual(alive,0, 'partial candidate retained at opcode '+str(trip))
                        retained+=alive
                        STATS['opcode_cancellation_sites'] += 1
                    if not changed:
                        self.assertGreater(retained,0)
                    STATS['baseline_opcode_retention_witnesses'] += retained

    def test_05_actual_signal_during_construction(self):
        old=signal.getsignal(signal.SIGALRM)
        timer=signal.getitimer(signal.ITIMER_REAL)
        self.assertEqual(timer,(0.0,0.0),'do not disturb an existing timer')
        def cancel(*_):
            raise Cancel('real signal')
        try:
            signal.signal(signal.SIGALRM,cancel)
            with isolated_gc():
                for changed in (False,True):
                    for surface in ('scheduler.py','selected_sell_core.py'):
                        module,helper=load_surface(surface,changed)
                        raised,alive,_=constructor_probe(module,helper,trip=3,timer=True)
                        self.assertTrue(raised)
                        self.assertEqual(alive,0 if changed else 1)
                        STATS['actual_signal_cases'] += 1
        finally:
            signal.setitimer(signal.ITIMER_REAL,0)
            signal.signal(signal.SIGALRM,old)

    def test_06_worker_thread_opcode_cancellation(self):
        outcomes=[]
        def worker():
            try:
                module,helper=load_surface()
                with isolated_gc():
                    constructor_probe(module,helper,opcode=True)
                    outcomes.append(constructor_probe(module,helper,opcode=True,trip=80))
            except BaseException as error:
                outcomes.append(type(error).__name__)
        thread=threading.Thread(target=worker)
        thread.start();thread.join()
        self.assertEqual(len(outcomes),1)
        self.assertIsInstance(outcomes[0],tuple)
        self.assertTrue(outcomes[0][0]);self.assertEqual(outcomes[0][1],0)
        STATS['worker_trace_cases'] += 1

    def test_07_cache_results_statistics_and_owner_isolation(self):
        for surface in SOURCES:
            base,_=load_surface(surface,False);cand,_=load_surface(surface)
            a=base.MarketPath(*path_args());b=cand.MarketPath(*path_args())
            for inv in (9900,10000,11000,10000):
                for quantity in (0,1,4,1):
                    for alignment in ('before','paired','after'):
                        self.assertEqual(a.joint(inv,quantity,2,alignment),b.joint(inv,quantity,2,alignment))
                        STATS['joint_pairs'] += 1
            for name in ('quote','single','joint'):
                x,y=getattr(a,name),getattr(b,name)
                self.assertEqual(x.cache_info(),y.cache_info())
                self.assertEqual(x.cache_parameters(),y.cache_parameters())
                x.cache_clear();y.cache_clear()
                self.assertEqual(x.cache_info(),y.cache_info())
            c=cand.MarketPath('MILK',10000,None,[],{},241,249)
            self.assertEqual(c.single.cache_info().currsize,0)
            a.single(inv=10000,quantity=1);b.single(inv=10000,quantity=1)
            self.assertEqual(a.single.cache_info(),b.single.cache_info())
            self.assertEqual(c.single.cache_info().currsize,0)
            c.single(10000,1)
            self.assertNotEqual(c.single(10000,1),b.single(10000,1))
            del a,b,c
        gc.collect()

    def test_08_subclass_overrides_and_exception_identity(self):
        for changed in (False,True):
            module,_=load_surface(changed=changed)
            log=[]
            class Special(module.MarketPath):
                def _single(self,inv,quantity):
                    log.append((inv,quantity))
                    if quantity < 0: raise Cancel('unchanged')
                    return inv+quantity,inv-quantity
            owner=Special(*path_args())
            self.assertEqual(owner.single(20,3),(23,17))
            self.assertEqual(owner.single(20,3),(23,17))
            self.assertEqual(log,[(20,3)])
            for _ in range(2):
                with self.assertRaisesRegex(Cancel,'unchanged'):
                    owner.single(20,-1)
            self.assertEqual(log,[(20,3),(20,-1),(20,-1)])
            STATS['override_exception_cases'] += 1
        gc.collect()

    def test_09_success_release_and_explicit_disposal(self):
        with isolated_gc():
            for surface in SOURCES:
                for changed in (False,True):
                    module,_=load_surface(surface,changed)
                    refs=[]
                    for _ in range(12):
                        owner=module.MarketPath(*path_args())
                        owner.joint(10000,3,2,'before')
                        refs.append(weakref.ref(owner));del owner
                    self.assertEqual(sum(r() is not None for r in refs),0 if changed else 12)
                    gc.collect()
                    self.assertTrue(all(r() is None for r in refs))
                    STATS['discarded_model_cases'] += 12
                owner=module.MarketPath(*path_args())
                owner.single(10000,1)
                owner.quote.cache_clear();owner.single.cache_clear();owner.joint.cache_clear()
                del owner.single,owner.joint
                ref=weakref.ref(owner);del owner
                self.assertIsNone(ref())
                STATS['caller_disposal_cases'] += 1

    def test_10_whole_optimizer_and_capacity_order(self):
        surfaces=['selected_sell_core.py']+(['weave'] if EXTRA else [])
        for surface in surfaces:
            base,_=load_surface(surface,False);cand,_=load_surface(surface)
            for item in ('WHEAT','CARROT','TOMATO','STRAWBERRY','MELON','MILK','EGG','WOOL','FERTILIZER'):
                for rule in ('strict','expected_downside','minimax_regret'):
                    for horizon in (0,3,8):
                        for inventory in (9900,20000):
                            args=optimizer_args(rule,item,horizon,inventory)
                            outputs=[]
                            for module in (base,cand):
                                trace=[]
                                def capacity(plan):
                                    trace.append(tuple(plan))
                                    return dict(plan).get(241,0)%2==0
                                outputs.append((module.optimize_lot(**copy.deepcopy(args),capacity_ok=capacity),trace))
                            self.assertEqual(outputs[0],outputs[1])
                            STATS['optimizer_pairs'] += 1
                            STATS['capacity_entries'] += len(outputs[0][1])
        gc.collect()

    def test_11_funding_receipts_and_retained_pool(self):
        import frozen_selected as frozen
        original=frozen.MarketPath
        a,_=load_surface('scheduler.py',False);b,_=load_surface('scheduler.py')
        try:
            for item in ('WHEAT','CARROT','MILK','WOOL','FERTILIZER'):
                for inv in (9900,10000,20000):
                    for quantity in (0,1,7,20):
                        for rival in (0,5):
                            values=[]
                            for module in (a,b):
                                frozen.MarketPath=module.MarketPath
                                values.append(frozen._stressed_sale_receipt(item,quantity,inv,{},[],{},240,rival))
                            self.assertEqual(*values)
                            STATS['funding_receipt_pairs'] += 1
            # Borrowed models remain strongly owned by a caller pool; a receipt
            # does not invalidate a sibling/trial's cache. This is the ownership
            # contract, NOT an execution of FUNDING-PERF's separate composer.
            with isolated_gc():
                pool=[b.MarketPath(*path_args()) for _ in range(3)]
                refs=[weakref.ref(owner) for owner in pool]
                for q in (1,2,1,3,2):
                    for owner in pool: owner.single(10000,q)
                del owner
                self.assertTrue(all(r() is not None for r in refs))
                self.assertTrue(all(owner.single.cache_info().hits==2 for owner in pool))
                pool.clear()
                self.assertTrue(all(r() is None for r in refs))
        finally:
            frozen.MarketPath=original
        gc.collect()

    def test_12_documented_escaped_callable_boundary(self):
        module,helper=load_surface()
        with isolated_gc():
            owner=module.MarketPath(*path_args())
            escaped=owner.single
            expected=escaped(10000,2)
            ref=weakref.ref(owner);del owner
            self.assertIsNone(ref())
            self.assertEqual(escaped(10000,2),expected)
            with self.assertRaises(ReferenceError): escaped(10000,3)
        STATS['documented_ownership_boundaries'] += 1


    def test_13_real_cli_refuses_bad_inputs_and_overwrites(self):
        with tempfile.TemporaryDirectory(prefix='spindle-cli-') as temp:
            temp=Path(temp)
            source=temp/'core.py';source.write_bytes(SOURCES['selected_sell_core.py'])
            helper=temp/'helper.py';helper.write_bytes(HELPER_BYTES)
            out=temp/'result.py'
            command=[sys.executable]+(['-O'] if not __debug__ else [])+[
                str(Path(__file__).with_name('compose_scoped_constructor.py')),
                '--source',str(source),'--helper',str(helper),'--out',str(out)]
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            expected=compose(source.read_bytes(),HELPER_BYTES)[0]
            self.assertEqual(out.read_bytes(),expected)
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,2)
            self.assertEqual(out.read_bytes(),expected)
            out.unlink();helper.write_bytes(HELPER_BYTES+b'\n')
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,2)
            self.assertFalse(out.exists())
            helper.unlink()
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,2)
            self.assertFalse(out.exists())
            helper.write_bytes(HELPER_BYTES)
            source.write_bytes(source.read_bytes().replace(b'maxsize=8192',b'maxsize=99',1))
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,2)
            self.assertFalse(out.exists())
            self.assertEqual(subprocess.run(command[:-1]+[str(source)],capture_output=True).returncode,2)
            STATS['real_cli_controls'] += 6


def main():
    global RUNTIME, HELPER_BYTES, EXTRA, MUTANT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',required=True,type=Path)
    parser.add_argument('--helper',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--weave',type=Path)
    parser.add_argument('--mutant',choices=['strong_owner','wrong_limit','wrong_result','swallow','retain_single','retain_joint'])
    parser.add_argument('--test')
    args=parser.parse_args()
    RUNTIME=args.runtime.resolve();HELPER_BYTES=args.helper.read_bytes();EXTRA=args.weave;MUTANT=args.mutant
    try:
        authenticate_helper(HELPER_BYTES)
        members=authenticate_runtime(RUNTIME)
        SOURCES.update({name:(RUNTIME/name).read_bytes() for name in SURFACES})
        if EXTRA:
            data=EXTRA.read_bytes()
            if git_blob(data)!='16dde00627effa5d0ae4d73a8e05a295e9534e1f':
                raise ValueError('WEAVE output identity mismatch')
            SOURCES['weave']=data
    except (OSError,ValueError) as error:
        parser.exit(2,'REFUSED: '+str(error)+'\n')
    sys.path.insert(0,str(RUNTIME))
    helper_module()
    loader=unittest.TestLoader()
    suite=loader.loadTestsFromName(args.test,sys.modules[__name__]) if args.test else loader.loadTestsFromTestCase(Construction)
    stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    report=dict(python=sys.version,optimized=not __debug__,runtime_members=members,mutant=MUTANT,
                tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skips=len(result.skipped),
                counters=dict(STATS),weave=bool(EXTRA),log=stream.getvalue(),
                sources={p:git_blob(b) for p,b in SOURCES.items()})
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(stream.getvalue())
    print(json.dumps({k:v for k,v in report.items() if k not in ('log','sources')},sort_keys=True))
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__=='__main__':
    raise SystemExit(main())
