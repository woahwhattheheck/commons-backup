// SPDX-License-Identifier: MIT
// Included after an unmodified Solver body with test-only public visibility.
#include <cstring>
#include <iomanip>
int main(int argc, char** argv) {
    if (argc != 6) return 2;
    try {
        Solver solver(argv[1], argv[2], argv[3], argv[4]);
        bool dump = std::string(argv[5]) == "dump";
        std::uint64_t hash = 1469598103934665603ULL;
        auto mix = [&](std::uint64_t value) {
            for (int j = 0; j < 8; ++j) {
                hash ^= (value >> (j * 8)) & 255U;
                hash *= 1099511628211ULL;
            }
        };
        long long entries = 0;
        for (int t = 0; t < solver.h; ++t) for (int a = 0; a < solver.n; ++a)
            for (int b = 0; b < solver.n; ++b) {
                const auto& flow = solver.segment(t, a, b);
                mix(t); mix(a); mix(b); mix(flow.size());
                if (dump) std::cout << "flow " << t << ' ' << a << ' ' << b;
                for (auto [e, fraction] : flow) {
                    std::uint64_t bits;
                    static_assert(sizeof(bits) == sizeof(fraction));
                    std::memcpy(&bits, &fraction, sizeof(bits));
                    mix(static_cast<std::uint64_t>(e)); mix(bits); ++entries;
                    if (dump) std::cout << ' ' << e << ':' << std::hexfloat << fraction;
                }
                if (dump) std::cout << '\n';
            }
        int dags = 0, aliases = 0, collisions = 0;
        for (const auto& p : solver.dags) dags += bool(p);
        for (int t = 0; t < solver.h; ++t) for (int u = 0; u < t; ++u) {
            bool same = &solver.dag(t, 0) == &solver.dag(u, 0);
            if (same && solver.offline[t] == solver.offline[u]) ++aliases;
            if (same && solver.offline[t] != solver.offline[u]) ++collisions;
        }
        std::cout << "summary " << hash << ' ' << entries << ' ' << dags << ' '
                  << solver.cache.size() << ' ' << aliases << ' ' << collisions << '\n';
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
