// Exact finite search/verifier for OEIS A304081.
// Research utility: finite null searches are evidence only, never a proof.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

using u64 = std::uint64_t;
using u128 = __uint128_t;

namespace {
constexpr u64 kSplitMixGamma = 0x9e3779b97f4a7c15ULL;
constexpr u64 kMaxSieveRoot = 20'000'000ULL;

u64 parse_u64(const char* s) {
    std::string v(s);
    std::size_t pos = 0;
    unsigned long long x = std::stoull(v, &pos, 10);
    if (pos != v.size()) throw std::invalid_argument("invalid integer: " + v);
    return static_cast<u64>(x);
}

u64 mul_mod(u64 a, u64 b, u64 mod) { return static_cast<u64>((u128)a * b % mod); }

u64 pow_mod(u64 a, u64 d, u64 mod) {
    u64 out = 1;
    while (d) {
        if (d & 1) out = mul_mod(out, a, mod);
        a = mul_mod(a, a, mod);
        d >>= 1;
    }
    return out;
}

// Deterministic Miller-Rabin for all uint64_t inputs.
bool is_prime(u64 n) {
    if (n < 2) return false;
    for (u64 p : {2ULL, 3ULL, 5ULL, 7ULL, 11ULL, 13ULL, 17ULL, 19ULL,
                  23ULL, 29ULL, 31ULL, 37ULL}) {
        if (n % p == 0) return n == p;
    }
    u64 d = n - 1, s = 0;
    while ((d & 1) == 0) { d >>= 1; ++s; }
    for (u64 a : {2ULL, 325ULL, 9375ULL, 28178ULL, 450775ULL,
                  9780504ULL, 1795265022ULL}) {
        if (a % n == 0) continue;
        u64 x = pow_mod(a % n, d, n);
        if (x == 1 || x == n - 1) continue;
        bool witness = true;
        for (u64 r = 1; r < s; ++r) {
            x = mul_mod(x, x, n);
            if (x == n - 1) { witness = false; break; }
        }
        if (witness) return false;
    }
    return true;
}

std::vector<std::uint32_t> primes_up_to(u64 limit) {
    if (limit > kMaxSieveRoot) {
        throw std::runtime_error("sqrt(max_n) exceeds safety cap; reduce max_n or replace squarefree sieve");
    }
    std::vector<bool> composite(static_cast<std::size_t>(limit + 1), false);
    std::vector<std::uint32_t> primes;
    for (u64 i = 2; i <= limit; ++i) {
        if (composite[static_cast<std::size_t>(i)]) continue;
        primes.push_back(static_cast<std::uint32_t>(i));
        if (i * i <= limit) {
            for (u64 j = i * i; j <= limit; j += i) composite[static_cast<std::size_t>(j)] = true;
        }
    }
    return primes;
}

bool is_squarefree(u64 x, const std::vector<std::uint32_t>& primes) {
    for (u64 p : primes) {
        const u64 square = p * p;
        if (square > x) break;
        if (x % square == 0) return false;
    }
    return true;
}

struct Offset {
    u64 value;
    std::uint32_t k;
    std::uint32_t m;
};

struct Representation {
    u64 p;
    u64 offset;
    std::uint32_t k;
    std::uint32_t m;
};

class SearchSpace {
  public:
    explicit SearchSpace(u64 max_n) : max_n_(max_n) {
        if (max_n < 8) max_n_ = 8;
        const u64 root = static_cast<u64>(std::sqrt(static_cast<long double>(max_n_))) + 2;
        primes_ = primes_up_to(root);
        even_offsets_ = build_offsets(0);
        odd_offsets_ = build_offsets(1);
    }

    const std::vector<Offset>& offsets(u64 n) const {
        return (n & 1ULL) ? odd_offsets_ : even_offsets_;
    }

    std::vector<Representation> representations(u64 n) const {
        std::vector<Representation> out;
        for (const Offset& off : offsets(n)) {
            if (off.value + 3 > n) continue;
            const u64 p = n - off.value;
            if ((p & 1ULL) && is_prime(p)) out.push_back({p, off.value, off.k, off.m});
        }
        return out;
    }

    u64 count(u64 n) const {
        u64 total = 0;
        for (const Offset& off : offsets(n)) {
            if (off.value + 3 > n) continue;
            const u64 p = n - off.value;
            if ((p & 1ULL) && is_prime(p)) ++total;
        }
        return total;
    }

    std::pair<bool, u64> has_representation(u64 n) const {
        u64 tested = 0;
        for (const Offset& off : offsets(n)) {
            if (off.value + 3 > n) continue;
            ++tested;
            const u64 p = n - off.value;
            if ((p & 1ULL) && is_prime(p)) return {true, tested};
        }
        return {false, tested};
    }

  private:
    std::vector<Offset> build_offsets(int parity) const {
        const u64 coefficient = 1 + static_cast<u64>(parity);
        std::vector<u64> powers2, powers5;
        // k=0 can never yield an odd prime p because its offset has n's parity.
        for (u64 v = 2; v < max_n_;) {
            powers2.push_back(v);
            if (v > max_n_ / 2) break;
            v *= 2;
        }
        for (u64 v = 1; v < max_n_;) {
            powers5.push_back(v);
            if (v > max_n_ / 5) break;
            v *= 5;
        }
        std::vector<Offset> out;
        for (std::size_t ki = 0; ki < powers2.size(); ++ki) {
            for (std::size_t m = 0; m < powers5.size(); ++m) {
                const u128 wide = static_cast<u128>(powers2[ki]) +
                    static_cast<u128>(coefficient) * powers5[m];
                if (wide >= max_n_) break;
                const u64 off = static_cast<u64>(wide);
                if (is_squarefree(off, primes_)) {
                    out.push_back({off, static_cast<std::uint32_t>(ki + 1),
                                   static_cast<std::uint32_t>(m)});
                }
            }
        }
        std::sort(out.begin(), out.end(), [](const Offset& a, const Offset& b) {
            if (a.value != b.value) return a.value < b.value;
            return std::tie(a.k, a.m) < std::tie(b.k, b.m);
        });
        return out;
    }

    u64 max_n_;
    std::vector<std::uint32_t> primes_;
    std::vector<Offset> even_offsets_;
    std::vector<Offset> odd_offsets_;
};

u64 splitmix64(u64& state) {
    u64 z = (state += kSplitMixGamma);
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
    return z ^ (z >> 31);
}

void self_test() {
    struct Case { u64 n, expected; };
    const Case cases[] = {
        {1,0}, {2,0}, {3,0}, {4,0}, {5,0}, {6,1}, {7,0}, {8,2},
        {15,1}, {35,1}, {91,1}, {9'574'899ULL,1}, {6'447'154'629ULL,2}
    };
    SearchSpace space(6'447'154'630ULL);
    for (const auto& c : cases) {
        const u64 got = space.count(c.n);
        if (got != c.expected) {
            std::cerr << "SELF_TEST_FAIL n=" << c.n << " expected=" << c.expected
                      << " got=" << got << "\n";
            std::exit(2);
        }
    }
    if (!is_prime(2) || !is_prime(3) || !is_prime(2'147'483'647ULL) ||
        is_prime(1) || is_prime(4) || is_prime(341) || is_prime(3'215'031'751ULL)) {
        std::cerr << "SELF_TEST_FAIL primality\n";
        std::exit(2);
    }
    std::cout << "SELF_TEST_PASS cases=" << (sizeof(cases)/sizeof(cases[0])) << "\n";
}

void usage() {
    std::cerr << "usage:\n"
              << "  a304081_search self-test\n"
              << "  a304081_search count N\n"
              << "  a304081_search scan LO HI\n"
              << "  a304081_search verify-range LO HI\n"
              << "  a304081_search random TRIALS LO HI SEED [SKIP]\n"
              << "  a304081_search sample TRIALS LO HI SEED [SKIP]\n";
}
}

int main(int argc, char** argv) {
    try {
        if (argc < 2) { usage(); return 2; }
        const std::string mode = argv[1];
        if (mode == "self-test") { self_test(); return 0; }

        if (mode == "count") {
            if (argc != 3) { usage(); return 2; }
            const u64 n = parse_u64(argv[2]);
            if (n == std::numeric_limits<u64>::max())
                throw std::invalid_argument("N too large for inclusive bound");
            SearchSpace space(n + 1);
            const auto reps = space.representations(n);
            std::cout << "COUNT n=" << n << " a=" << reps.size() << "\n";
            for (const auto& r : reps) {
                std::cout << "REP p=" << r.p << " k=" << r.k << " m=" << r.m
                          << " offset=" << r.offset << "\n";
            }
            return 0;
        }

        if (mode == "scan") {
            if (argc != 4) { usage(); return 2; }
            const u64 lo = parse_u64(argv[2]), hi = parse_u64(argv[3]);
            if (lo > hi) throw std::invalid_argument("LO > HI");
            if (hi == std::numeric_limits<u64>::max())
                throw std::invalid_argument("HI too large for inclusive bound");
            SearchSpace space(hi + 1);
            u64 best_count = std::numeric_limits<u64>::max(), best_n = 0;
            for (u64 n = lo;; ++n) {
                const u64 c = space.count(n);
                if (c < best_count) {
                    best_count = c; best_n = n;
                    std::cerr << "BEST n=" << n << " a=" << c << "\n";
                }
                if (c == 0 && n > 7) {
                    std::cout << "COUNTEREXAMPLE n=" << n << "\n";
                    return 1;
                }
                if (n == hi) break;
            }
            std::cout << "SCAN_DONE lo=" << lo << " hi=" << hi
                      << " best_n=" << best_n << " best_a=" << best_count << "\n";
            return 0;
        }

        if (mode == "verify-range") {
            if (argc != 4) { usage(); return 2; }
            const u64 lo = parse_u64(argv[2]), hi = parse_u64(argv[3]);
            if (lo > hi) throw std::invalid_argument("LO > HI");
            if (hi == std::numeric_limits<u64>::max())
                throw std::invalid_argument("HI too large for inclusive bound");
            SearchSpace space(hi + 1);
            u64 hardest_n = 0, hardest_prefix = 0;
            for (u64 n = lo;; ++n) {
                const auto [found, tested] = space.has_representation(n);
                if (!found && n > 7) {
                    std::cout << "COUNTEREXAMPLE n=" << n
                              << " tested_offsets=" << tested << "\n";
                    return 1;
                }
                if (tested > hardest_prefix) {
                    hardest_prefix = tested; hardest_n = n;
                }
                if (n == hi) break;
            }
            std::cout << "RANGE_DONE lo=" << lo << " hi=" << hi
                      << " count=" << (hi-lo+1) << " hardest_n=" << hardest_n
                      << " hardest_prefix=" << hardest_prefix << "\n";
            return 0;
        }

        if (mode == "random" || mode == "sample") {
            if (argc != 6 && argc != 7) { usage(); return 2; }
            const u64 trials = parse_u64(argv[2]), lo = parse_u64(argv[3]),
                      hi = parse_u64(argv[4]), seed = parse_u64(argv[5]),
                      skip = argc == 7 ? parse_u64(argv[6]) : 0;
            if (lo > hi) throw std::invalid_argument("LO > HI");
            if (hi == std::numeric_limits<u64>::max())
                throw std::invalid_argument("HI too large for inclusive span");
            SearchSpace space(hi + 1);
            const u64 span = hi - lo + 1;
            u64 state = seed + kSplitMixGamma * skip;
            u64 hardest_n = 0, hardest_prefix = 0;
            u64 min_count = std::numeric_limits<u64>::max(), min_n = 0;
            std::map<u64,u64> histogram;
            const auto start = std::chrono::steady_clock::now();

            for (u64 i = 0; i < trials; ++i) {
                const u64 n = lo + splitmix64(state) % span;
                if (mode == "random") {
                    const auto [found, tested] = space.has_representation(n);
                    if (!found && n > 7) {
                        std::cout << "COUNTEREXAMPLE n=" << n << " trial=" << (skip+i)
                                  << " tested_offsets=" << tested << "\n";
                        return 1;
                    }
                    if (tested > hardest_prefix) {
                        hardest_prefix = tested; hardest_n = n;
                    }
                } else {
                    const u64 c = space.count(n);
                    ++histogram[std::min<u64>(c,20)];
                    if (c < min_count) { min_count = c; min_n = n; }
                    if (c == 0 && n > 7) {
                        std::cout << "COUNTEREXAMPLE n=" << n
                                  << " trial=" << (skip+i) << "\n";
                        return 1;
                    }
                }
            }

            const double seconds =
                std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
            if (mode == "random") {
                std::cout << "RANDOM_DONE trials=" << trials << " skip=" << skip
                          << " lo=" << lo << " hi=" << hi << " hardest_n=" << hardest_n
                          << " hardest_prefix=" << hardest_prefix
                          << " rate=" << (seconds ? trials/seconds : 0.0) << "\n";
            } else {
                std::cout << "SAMPLE_DONE trials=" << trials << " skip=" << skip
                          << " lo=" << lo << " hi=" << hi << " min_n=" << min_n
                          << " min_a=" << min_count
                          << " rate=" << (seconds ? trials/seconds : 0.0) << "\n";
                for (const auto& [bucket,c] : histogram) {
                    std::cout << "HIST bucket="
                              << (bucket==20 ? std::string("20+") : std::to_string(bucket))
                              << " count=" << c << "\n";
                }
            }
            return 0;
        }

        usage(); return 2;
    } catch (const std::exception& e) {
        std::cerr << "ERROR " << e.what() << "\n";
        return 2;
    }
}
