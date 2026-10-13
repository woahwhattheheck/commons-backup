"""Deterministic local microbenchmark for S06 data-structure bounds."""
import statistics
import sys
import time
import tracemalloc

from continuation_index import ContinuationIndex, _deep_size


def state(i):
    # 64 product buckets; enough collisions to exercise retrieve-limit slicing.
    b = i % 64
    return {
        'phase': b % 8,
        'positions': {'farmer': [b % 4, (b // 4) % 4]},
        'resources': {'money': 100 + (b % 4), 'seeds': {'CARROT': 8 + (b % 4)}},
        'structures': {'shed': 1, 'plots': 4},
        'animals': {'COW': b % 3},
        'market': {'inventory': {'MILK': 40 + (b % 4)}, 'prices': {'MILK': 8}},
        'commitments': {'funding_reserved': 20, 'seed_reserved': {'CARROT': 2},
                        'blocked_routes': ['west']},
    }


def main():
    tracemalloc.start()
    idx = ContinuationIndex()
    for i in range(20000):
        idx.add(state(i), {'name': 'history-%05d' % i, 'requires': {}}, 't%05d' % i)
    current, peak = tracemalloc.get_traced_memory()
    structural = _deep_size((idx._records, idx._exact, idx._product,
                             idx._seen, idx.quanta)) + sys.getsizeof(idx)
    admission = idx.stats()['admission_bytes']
    if admission < structural:
        raise AssertionError('admission charge below retained structural footprint')
    if admission < peak:
        raise AssertionError('admission charge below traced benchmark peak')
    timings = []
    canonical = [{'name': 'canonical', 'requires': {}}]
    for i in range(1000):
        s = state(i)
        start = time.perf_counter_ns()
        got = idx.retrieve(s, canonical, mode='rerank',
                           economic_score=lambda a, _s: float(len(a['name'])))
        elapsed = (time.perf_counter_ns() - start) / 1_000_000.0
        if not any(c.source == 'canonical' for c in got):
            raise AssertionError('canonical missing')
        timings.append(elapsed)
    print('records', idx.stats()['records'])
    print('admission_bytes', admission)
    print('structural_bytes', structural)
    print('tracemalloc_current_bytes', current)
    print('tracemalloc_peak_bytes', peak)
    print('lookup_ms_p50', round(statistics.median(timings), 6))
    print('lookup_ms_p95', round(sorted(timings)[int(len(timings)*0.95)-1], 6))
    print('lookup_ms_max', round(max(timings), 6))


if __name__ == '__main__':
    main()
