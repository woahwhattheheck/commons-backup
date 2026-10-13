    // CEDAR: cross a single-demand two-waypoint barrier. Existing move() alone
    // decides feasibility and strict full-vector improvement; no tentative path
    // is installed, no budget is borrowed, and no peer neighborhood is replaced.
    bool cedarPairMoves(int t, int edge,
                        const std::vector<std::pair<double, int>>& contributing,
                        bool adaptive) {
        if (!cedarEnabled || maxSegments < 3) return false;
        const double until = std::getenv("SEDGE_MAX_ROUNDS") ? seconds
            : std::min(seconds, elapsed() + std::min(1.0, std::max(0.02, seconds * 0.02)));
        std::size_t checks = 0;
        auto expired = [&] { return finished() || elapsed() >= until || checks >= cedarTrialLimit; };
        const int count = std::min<int>(4, contributing.size());
        for (int index = 0; index < count && !expired(); ++index) {
            const int d = contributing[index].second;
            Route pool;
            if (n <= 32) {
                pool.resize(n); std::iota(pool.begin(), pool.end(), 0);
            } else {
                pool = waypointCandidates(d, t, edge, -1, nullptr, until);
            }
            std::vector<std::pair<int, int>> intervals{{0, h - 1}};
            if (adaptive && h > 1) {
                intervals.emplace_back(t, t);
                for (int radius : {1, 2, 3})
                    intervals.emplace_back(std::max(0, t-radius), std::min(h-1, t+radius));
                intervals.emplace_back(0, t);
                intervals.emplace_back(t, h-1);
            }
            // Keep the inherited window order, but never pay twice for a duplicate.
            std::vector<std::pair<int, int>> unique;
            for (auto interval : intervals)
                if (std::find(unique.begin(), unique.end(), interval) == unique.end())
                    unique.push_back(interval);
            const auto width = n <= 32 ? pool.size() : cedarWidth;
            const auto result = cedar_pairs::visit(pool, demands[d].from, demands[d].to,
                width, cedarTrialLimit, expired, [&](int first, int second) {
                    const Route next{first, second};
                    for (auto [left, right] : unique) {
                        if (expired()) return false;
                        ++checks; ++cedarChecks;
                        if (move(d, left, right, next)) {
                            ++cedarAccepted;
                            return true;
                        }
                    }
                    return false;
                });
            if (result.accepted) return true;
        }
        return false;
    }

