# SPDX-License-Identifier: Apache-2.0
"""Relocatable T13 callable. The exported directory includes pinned vendor/sell.

In a Commons checkout, the unchanged T08 vendor is reused directly. In raw-file
loaders, __raw_path__ is supplied in configuration and imports happen lazily.
"""
_policy = None
_controller = None


def make_agent(root, sell=True, enabled=True):
    import importlib.util
    from pathlib import Path
    import sys
    root = Path(root).resolve()
    vendor = root / "vendor/sell"
    if not vendor.is_dir():
        vendor = root.parent / "cloud-titan-composition/vendor/sell"
    sys.path.insert(0, str(vendor))
    spec = importlib.util.spec_from_file_location("alder_scheduler", vendor / "scheduler.py")
    scheduler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scheduler)
    spec = importlib.util.spec_from_file_location("alder_recovery", root / "recovery.py")
    recovery = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recovery)
    policy = scheduler.SellScheduler() if sell else scheduler.parent.Agent()
    parent = policy.controller if sell else policy
    controller = recovery.RecoveryController(parent, scheduler.parent, scheduler.m, enabled)
    if sell:
        policy.controller = controller
    else:
        policy = controller
    def run(observation, configuration=None):
        controller.configuration = dict(configuration or {})
        return policy.act(observation, configuration) if sell else policy.act(observation)
    run.controller = controller
    run.policy = policy
    return run


def agent(observation, configuration=None):
    global _policy, _controller
    if _policy is None or int(observation.get("step", 0)) == 0:
        from pathlib import Path
        path = globals().get("__file__") or (configuration or {}).get("__raw_path__")
        if not path:
            raise ValueError("Supply a module path or configuration.__raw_path__ for T13 dependencies")
        _policy = make_agent(Path(path).resolve().parent)
        _controller = _policy.controller
    return _policy(observation, configuration)
