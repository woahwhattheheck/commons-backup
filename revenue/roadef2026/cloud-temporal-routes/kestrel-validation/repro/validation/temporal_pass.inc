// SPDX-License-Identifier: MIT
// Included inside the existing SEDGE/FLORA Solver class. No forwarding-code copy.
// This optional pass optimizes a whole time sequence for ONE demand at a time.
    bool temporalDemand(int d) {
        if (finished()) return false;
        const int cap = static_cast<int>(std::min(256.0, setting("KESTREL_DP_ROUTES", 32)));
        if (cap < 1) return false;
        std::vector<Route> pool;
        auto add = [&](const Route& path) {
            if (std::find(pool.begin(), pool.end(), path) == pool.end()) pool.push_back(path);
        };
        for (int t = 0; t < h; ++t) add(routes[d * h + t]);
        if (static_cast<int>(pool.size()) > cap) return false;
        if (static_cast<int>(pool.size()) < cap) add({});
        // Preserve incumbent alternatives first; remaining one-waypoint offers
        // are deterministic. This bound limits the pool, not solution validity.
        for (int w = 0; w < n && static_cast<int>(pool.size()) < cap; ++w)
            if (w != demands[d].from && w != demands[d].to && maxSegments >= 2) add({w});
        const std::size_t k = pool.size();
        constexpr std::size_t cells = 2000000;
        if (static_cast<std::size_t>(h) > cells / k ||
            static_cast<std::size_t>(h) * k > cells / static_cast<std::size_t>(m)) return false;
        std::vector<std::vector<int>> costs(k, std::vector<int>(k));
        for (std::size_t a = 0; a < k; ++a) for (std::size_t b = 0; b < k; ++b) {
            if (finished()) return false;
            costs[a][b] = distance(d, pool[a], pool[b]);
        }
        std::vector<int> allowance(h);
        for (int t = 1; t < h; ++t) {
            allowance[t] = budget[t] - used[t] + distance(d, routes[d*h+t-1], routes[d*h+t]);
            if (allowance[t] < 0) return false;
        }
        std::vector<std::vector<kestrel::Option>> rows(h, std::vector<kestrel::Option>(k));
        for (int t = 0; t < h; ++t) {
            std::vector<double> base(loads.begin() + t*m, loads.begin() + (t+1)*m);
            for (auto [e, ratio] : routed[d*h+t]) base[e] -= demands[d].volume[t] * ratio;
            for (std::size_t p = 0; p < k; ++p) {
                if (finished()) return false;
                Sparse flow;
                if (!routeFlow(d, t, pool[p], flow)) continue;
                auto next = base;
                for (auto [e, ratio] : flow) next[e] += demands[d].volume[t] * ratio;
                kestrel::Score score;
                score.reserve(m);
                for (double value : next) {
                    const double scaled = std::floor(std::max(0.0, value) * 1e6);
                    if (!std::isfinite(scaled) || scaled >= static_cast<double>(INT64_MAX)) return false;
                    score.push_back(static_cast<std::int64_t>(scaled));
                }
                std::sort(score.begin(), score.end(), std::greater<std::int64_t>());
                rows[t][p] = {true, std::move(score)};
            }
        }
        auto chosen = kestrel::optimize(rows, costs, allowance, [&] { return finished(); }, cells);
        if (chosen.status != kestrel::Status::complete || finished()) return false;
        ++attempted;
        auto updated = loads;
        auto updatedUsed = used;
        std::vector<Sparse> replacement(h);
        for (int t = 0; t < h; ++t) {
            if (finished()) return false;
            const auto& route = pool[chosen.route_indices[t]];
            if (!routeFlow(d, t, route, replacement[t])) return false;
            for (auto [e, ratio] : routed[d*h+t]) updated[t*m+e] -= demands[d].volume[t] * ratio;
            for (auto [e, ratio] : replacement[t]) updated[t*m+e] += demands[d].volume[t] * ratio;
            if (t) {
                updatedUsed[t] += -distance(d, routes[d*h+t-1], routes[d*h+t])
                    + distance(d, pool[chosen.route_indices[t-1]], route);
                if (updatedUsed[t] < 0 || updatedUsed[t] > budget[t]) return false;
            }
        }
        // The same conservative six-decimal acceptance as the parent. A DP
        // proposal cannot commit from approximate labels or incomplete work.
        std::vector<long long> before, after;
        for (std::size_t i = 0; i < loads.size(); ++i) {
            if (std::abs(updated[i] - loads[i]) <= 1e-12) continue;
            if (!std::isfinite(updated[i])) return false;
            before.push_back(static_cast<long long>(std::floor(std::max(0.0, loads[i]-1e-10)*1e6)));
            after.push_back(static_cast<long long>(std::floor(std::max(0.0, updated[i]+1e-10)*1e6)));
        }
        std::sort(before.begin(), before.end(), std::greater<long long>());
        std::sort(after.begin(), after.end(), std::greater<long long>());
        if (!(after < before) || finished()) return false;
        loads.swap(updated);
        used.swap(updatedUsed);
        for (int t = 0; t < h; ++t) {
            routes[d*h+t] = pool[chosen.route_indices[t]];
            routed[d*h+t] = std::move(replacement[t]);
        }
        ++accepted;
        return true;
    }

    void temporalSweep() {
        if (setting("KESTREL_TEMPORAL", 0) == 0 || finished()) return;
        std::vector<std::pair<double,int>> order;
        for (int d = 0; d < static_cast<int>(demands.size()); ++d) {
            double pressure = 0;
            for (int t = 0; t < h; ++t) for (auto [e, ratio] : routed[d*h+t])
                pressure = std::max(pressure, loads[t*m+e] * ratio * demands[d].volume[t]);
            order.emplace_back(-pressure, d);
        }
        std::sort(order.begin(), order.end());
        const std::size_t count = std::min(order.size(), static_cast<std::size_t>(
            std::min(1000000.0, setting("KESTREL_DP_DEMANDS", 8))));
        for (std::size_t i = 0; i < count && !finished(); ++i)
            if (temporalDemand(order[i].second)) writeSolution();
    }
