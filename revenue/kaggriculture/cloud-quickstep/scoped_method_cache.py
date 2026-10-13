# SPDX-License-Identifier: Apache-2.0
"""Per-owner method memoization for short-lived optimizer workspaces.

Use only where the workspace stays strongly owned throughout every call, cached
arguments/results do not refer back to it, and callers do not retain the cached
callable after dropping the workspace. This deliberately differs from a normal
bound method: the cache does not extend the workspace's lifetime.
"""
from functools import lru_cache
from weakref import ref


def scoped_method_cache(method, *, maxsize: int):
    """Cache a Python bound method without a cache -> bound-owner cycle.

    A cache miss pins the owner for the complete underlying call. Cache limits,
    argument keys, exceptions and cache_info/cache_clear remain those supplied
    by functools.lru_cache. No global cache, collection trigger, or GC setting
    is changed. The caller must keep the owner alive, including on cache hits.
    """
    owner_ref = ref(method.__self__)
    function = method.__func__

    @lru_cache(maxsize=maxsize)
    def invoke(*args, **kwargs):
        owner = owner_ref()
        if owner is None:
            raise ReferenceError('Scoped cache used after its workspace was released')
        return function(owner, *args, **kwargs)

    return invoke
