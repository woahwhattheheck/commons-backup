// QUAY native correspondence fixture; actual solver methods are in generated headers.
#include <algorithm>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <random>
#include <string>
#include <utility>
#include <vector>
using Sparse = std::vector<std::pair<int, double>>;
struct Demand { int from, to; std::vector<double> volume; };
#include "original.hpp"
#include "candidate.hpp"

static void populate(Original& s, int count, int seed) {
    s.h = 3;
    std::mt19937 rng(seed);
    s.demands.resize(count); s.routed.resize(count * s.h);
    for (int d = 0; d < count; ++d) {
        s.demands[d] = {d, d + 1, {}};
        for (int t = 0; t < s.h; ++t) {
            // Repeated values deliberately create many exact ties.
            double volume = static_cast<int>(rng() % 13) / 4.0;
            if (d % 29 == 0) volume = 0;
            s.demands[d].volume.push_back(volume);
            Sparse flow;
            for (int e = 0; e < 16; ++e) {
                if (rng() % 7 == 0) continue;
                flow.emplace_back(e, static_cast<int>(rng() % 9) / 8.0);
            }
            s.routed[d * s.h + t] = std::move(flow);
        }
    }
}

static Candidate copy(const Original& s) {
    Candidate c; c.h = s.h; c.demands = s.demands; c.routed = s.routed;
    return c;
}

static int check() {
    std::uint64_t checked = 0;
    for (int count : {0, 1, 3, 4, 5, 31, 32, 33, 64, 257, 1024, 4096}) {
        for (int seed : {1, 19, 205}) {
            Original original; populate(original, count, seed);
            Candidate candidate = copy(original);
            for (int t = 0; t < original.h; ++t) {
                for (int edge : {-1, 0, 5, 15, 16}) {
                    for (int excluded : {-1, 0, count / 2, count + 7}) {
                        auto expected = original.contributors(t, edge, excluded);
                        auto all = candidate.contributors(t, edge, excluded);
                        if (all != expected) {
                            std::cerr << "default full-list mismatch\n"; return 1;
                        }
                        ++checked;
                        for (std::size_t limit : {0UL, 1UL, 3UL, 4UL, 31UL, 32UL, 33UL, 64UL, 10000UL}) {
                            auto want = expected;
                            if (want.size() > limit) want.resize(limit);
                            auto actual = candidate.contributors(t, edge, excluded, limit);
                            if (actual != want) {
                                std::cerr << "prefix mismatch count=" << count << " seed=" << seed
                                          << " t=" << t << " e=" << edge << " excluded=" << excluded
                                          << " limit=" << limit << '\n'; return 1;
                            }
                            ++checked;
                        }
                    }
                }
            }
        }
    }
    std::cout << "{\"status\":\"PASS\",\"comparisons\":" << checked << "}\n";
    return 0;
}

static double run_original(const Original& s, int limit, int repeat, double& checksum) {
    auto start = std::chrono::steady_clock::now();
    double sum = 0;
    for (int i = 0; i < repeat; ++i) {
        auto got = s.contributors(i % 3, 5, i % 17 == 0 ? 0 : -1);
        int count = std::min<int>(limit, got.size());
        for (int k = 0; k < count; ++k) sum += got[k].first + got[k].second;
    }
    checksum = sum;
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
}

static double run_candidate(const Candidate& s, int limit, int repeat, double& checksum) {
    auto start = std::chrono::steady_clock::now();
    double sum = 0;
    for (int i = 0; i < repeat; ++i) {
        auto got = s.contributors(i % 3, 5, i % 17 == 0 ? 0 : -1, limit);
        for (auto item : got) sum += item.first + item.second;
    }
    checksum = sum;
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
}

static int benchmark() {
    std::cout << "count,limit,pair,original_s,candidate_s,checksum\n" << std::setprecision(17);
    for (int count : {4, 32, 128, 1024, 8192, 32768}) {
        Original original; populate(original, count, 7391);
        Candidate candidate = copy(original);
        int repeat = std::max(20, 600000 / count);
        for (int limit : {4, 32}) {
            for (int pair = 0; pair < 9; ++pair) {
                double before, after, a, b;
                if (pair % 2 == 0) {
                    before = run_original(original, limit, repeat, a);
                    after = run_candidate(candidate, limit, repeat, b);
                } else {
                    after = run_candidate(candidate, limit, repeat, b);
                    before = run_original(original, limit, repeat, a);
                }
                if (a != b) { std::cerr << "benchmark result mismatch\n"; return 1; }
                std::cout << count << ',' << limit << ',' << pair << ',' << before << ',' << after << ',' << a << '\n';
            }
        }
    }
    return 0;
}

int main(int argc, char** argv) {
    if (argc == 2 && std::string(argv[1]) == "--bench") return benchmark();
    if (argc != 1) return 64;
    return check();
}
