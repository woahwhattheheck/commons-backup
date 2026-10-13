# SPDX-License-Identifier: Apache-2.0
"""Lifetime and behavior checks for short-lived, owner-scoped method caches."""
from __future__ import annotations
import gc
import platform
import unittest
import weakref
from functools import lru_cache
from scoped_method_cache import scoped_method_cache


class Workspace:
    def __init__(self, multiplier=1, size=2, scoped=True):
        self.multiplier = multiplier
        self.calls = 0
        self.compute = (scoped_method_cache(self._compute, maxsize=size) if scoped
                        else lru_cache(maxsize=size)(self._compute))

    def _compute(self, value, *, bias=0):
        self.calls += 1
        if value == 'error':
            raise ValueError('deliberate test exception')
        return self.multiplier*value+bias


class ScopedCacheTests(unittest.TestCase):
    def test_hits_values_and_keywords_match_bound_lru(self):
        direct = Workspace(multiplier=3, scoped=False)
        scoped = Workspace(multiplier=3)
        for value, bias in ((2, 4), (2, 4), (3, 1), (2, 4), (4, 0), (3, 1)):
            self.assertEqual(direct.compute(value, bias=bias), scoped.compute(value, bias=bias))
            self.assertEqual(direct.compute.cache_info(), scoped.compute.cache_info())
            self.assertEqual(direct.calls, scoped.calls)

    def test_cache_limits_and_explicit_clear(self):
        workspace = Workspace(size=2)
        for value in (1, 2, 3, 1):
            workspace.compute(value)
        self.assertEqual(workspace.compute.cache_info().currsize, 2)
        self.assertEqual(workspace.calls, 4)
        workspace.compute.cache_clear()
        self.assertEqual(workspace.compute.cache_info().currsize, 0)
        self.assertEqual(workspace.compute.cache_info().misses, 0)
        self.assertEqual(workspace.compute.cache_parameters(), {'maxsize': 2, 'typed': False})
        self.assertEqual(workspace.compute(3), 3)
        self.assertEqual(workspace.calls, 5)

    def test_distinct_owners_never_share_entries(self):
        first, second = Workspace(2), Workspace(7)
        self.assertEqual(first.compute(3), 6)
        self.assertEqual(second.compute(3), 21)
        self.assertEqual(first.compute(3), 6)
        self.assertEqual((first.calls, second.calls), (1, 1))

    def test_underlying_exceptions_are_not_cached_or_hidden(self):
        workspace = Workspace()
        for _ in range(2):
            with self.assertRaisesRegex(ValueError, 'deliberate test exception'):
                workspace.compute('error')
        self.assertEqual(workspace.calls, 2)
        self.assertEqual(workspace.compute.cache_info().currsize, 0)

    def test_recursive_bound_method_can_call_its_cache(self):
        class Fibonacci:
            def __init__(self):
                self.fib = scoped_method_cache(self._fib, maxsize=16)
            def _fib(self, value):
                return value if value < 2 else self.fib(value-1)+self.fib(value-2)
        workspace = Fibonacci()
        self.assertEqual(workspace.fib(12), 144)
        self.assertEqual(workspace.fib.cache_info().misses, 13)

    def test_override_is_the_original_bound_implementation(self):
        class Different(Workspace):
            def _compute(self, value, *, bias=0):
                self.calls += 1
                return -value-bias
        workspace = Different()
        self.assertEqual(workspace.compute(4, bias=2), -6)
        self.assertEqual(workspace.compute(4, bias=2), -6)
        self.assertEqual(workspace.calls, 1)

    @unittest.skipUnless(platform.python_implementation() == 'CPython', 'Immediate release is a CPython property')
    def test_discarded_workspaces_do_not_wait_for_cyclic_collection(self):
        enabled = gc.isenabled()
        gc.collect()
        gc.disable()
        try:
            references = []
            for _ in range(20):
                workspace = Workspace()
                workspace.compute(5)
                references.append(weakref.ref(workspace))
                del workspace
            self.assertTrue(all(reference() is None for reference in references))
        finally:
            if enabled:
                gc.enable()
            gc.collect()

    @unittest.skipUnless(platform.python_implementation() == 'CPython', 'Immediate release is a CPython property')
    def test_cache_miss_pins_owner_through_the_call(self):
        holder = []
        observed = []
        class Releasable:
            def __init__(self):
                self.compute = scoped_method_cache(self._compute, maxsize=2)
            def _compute(self, value):
                holder.clear()
                observed.append(reference() is self)
                return value+1
        holder.append(Releasable())
        reference = weakref.ref(holder[0])
        cached = holder[0].compute
        self.assertEqual(cached(5), 6)
        self.assertEqual(observed, [True])
        self.assertIsNone(reference())
        # A retained cache has deliberately different ownership from a normal
        # bound method. New keys after owner release must not invoke with None.
        with self.assertRaisesRegex(ReferenceError, 'workspace was released'):
            cached(6)

    def test_gc_configuration_is_unchanged(self):
        original = (gc.isenabled(), gc.get_threshold(), list(gc.callbacks))
        workspace = Workspace()
        workspace.compute(7)
        workspace.compute.cache_clear()
        self.assertEqual((gc.isenabled(), gc.get_threshold(), list(gc.callbacks)), original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
