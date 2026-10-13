// SPDX-License-Identifier: MIT
// Compile after build_candidate.py writes candidate.cpp in this directory.
#define main fleet_program_main
#include "candidate.cpp"
#undef main
#include <cassert>
#include <iostream>

static void expect(int stalled, int available, int limit, int prefix, int rank, int band) {
    auto actual = selectCriticalRank(stalled, available, limit);
    assert(actual.sortedPrefix == prefix);
    assert(actual.rank == rank);
    assert(actual.band == band);
}

int main() {
    expect(0, 1000, 32, 32, 0, 0);
    expect(31, 1000, 32, 32, 31, 0);
    expect(32, 1000, 32, 32, 0, 0);
    expect(63, 1000, 32, 32, 31, 0);
    expect(0, 1000, 128, 32, 0, 0);
    expect(31, 1000, 128, 32, 31, 0);
    expect(32, 1000, 128, 64, 32, 1);
    expect(63, 1000, 128, 64, 63, 1);
    expect(64, 1000, 128, 128, 64, 2);
    expect(127, 1000, 128, 128, 127, 2);
    expect(128, 1000, 128, 128, 64, 2);
    expect(191, 1000, 128, 128, 127, 2);
    expect(0, 10, 128, 10, 0, 0);
    expect(9, 10, 128, 10, 9, 0);
    expect(10, 10, 128, 10, 0, 0);
    expect(31, 50, 128, 32, 31, 0);
    expect(32, 50, 128, 50, 32, 1);
    expect(49, 50, 128, 50, 49, 1);
    expect(50, 50, 128, 50, 32, 1);
    bool rejected = false;
    try { (void)selectCriticalRank(-1, 5, 5); } catch (const std::runtime_error&) { rejected = true; }
    assert(rejected);
    rejected = false;
    try { (void)selectCriticalRank(0, 0, 5); } catch (const std::runtime_error&) { rejected = true; }
    assert(rejected);
    std::cout << "21 critical-rank schedule cases passed\n";
}
