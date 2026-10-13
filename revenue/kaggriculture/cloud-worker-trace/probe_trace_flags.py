"""Bounded child-process probe for TITAN worker trace flags. No game execution."""
import importlib.util, json, os, sys, threading, time, traceback
from pathlib import Path

source = Path(sys.argv[1]).resolve()
mode = sys.argv[2]
spec = importlib.util.spec_from_file_location('deadline_probe', source)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
result = {'mode': mode, 'source': str(source), 'budget_seconds': 0.02}

def worker():
    def prior(frame, event, arg):
        if frame.f_code.co_name == 'spin' and (mode == 'callee_muted' or (mode == 'dynamic_mute' and event == 'line')):
            frame.f_trace_lines = False
        return prior
    def spin():
        while True:
            pass
    frame = sys._getframe()
    if mode in ('caller_muted', 'callee_muted', 'dynamic_mute', 'nested_outer', 'nested_inner'):
        sys.settrace(prior)
        frame.f_trace = prior
        if mode in ('caller_muted', 'nested_outer', 'nested_inner'):
            frame.f_trace_lines = False
    if mode == 'muted_no_global':
        frame.f_trace_lines = False
    old_trace = sys.gettrace()
    old_lines = frame.f_trace_lines
    timer = mod._DeadlineTimer(0.02)
    start = time.perf_counter()
    try:
        with timer:
            if mode in ('nested_outer', 'nested_inner'):
                inner = mod._DeadlineTimer(0.2 if mode == 'nested_outer' else 0.005)
                with inner:
                    while True:
                        pass
            elif mode in ('callee_muted', 'dynamic_mute'):
                spin()
            else:
                while True:
                    pass
    except mod.DeadlineExceeded as error:
        result.update(cancelled=True, identity_preserved=error is (inner.expired if mode == 'nested_inner' else timer.expired),
                      elapsed_seconds=time.perf_counter()-start,
                      trace_restored=sys.gettrace() is old_trace,
                      line_flag_restored=frame.f_trace_lines is old_lines,
                      context_restored=mod._ACTIVE_TIMER.get() is None)
    except BaseException:
        result['unexpected'] = traceback.format_exc()
    finally:
        sys.settrace(None)
        frame.f_trace = None
        frame.f_trace_lines = True

thread = threading.Thread(target=worker, daemon=True)
thread.start()
thread.join(timeout=0.4)
result['watchdog_expired'] = thread.is_alive()
print(json.dumps(result), flush=True)
os._exit(0 if result.get('cancelled') and not result['watchdog_expired'] else 2)
