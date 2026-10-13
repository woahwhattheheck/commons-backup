    // CEDAR edge-seeded proposal frontier. An input link provides two candidate
    // waypoints; it does NOT force forwarding along that link. All three real
    // shortest-path ECMP segments must avoid the current critical link before
    // a proposal is tested by the inherited move() acceptance.
    bool cedarEdgeSeedMoves(int d, int t, int critical, bool adaptive,
                            double until, std::size_t& checks) {
        if (!cedarEdgeSeeds || cedarSeedArcLimit == 0) return false;
        auto expired = [&] { return finished() || elapsed() >= until || checks >= cedarTrialLimit; };
        std::vector<std::pair<int, int>> intervals{{0, h - 1}};
        if (adaptive && h > 1) {
            intervals.emplace_back(t, t);
            for (int radius : {1, 2, 3})
                intervals.emplace_back(std::max(0, t-radius), std::min(h-1, t+radius));
            intervals.emplace_back(0, t);
            intervals.emplace_back(t, h-1);
        }
        std::vector<std::pair<int, int>> unique;
        for (auto interval : intervals)
            if (std::find(unique.begin(), unique.end(), interval) == unique.end())
                unique.push_back(interval);
        std::vector<signed char> prefixes(n, -1), suffixes(n, -1);
        auto avoids = [&](int from, int to) {
            ++cedarSeedSegmentChecks;
            const auto& flow = segment(t, from, to);
            // Inspect this reference before another segment() can clear cache.
            if (!flow.empty() && flow.front().first == -1) return false;
            auto entry = std::lower_bound(flow.begin(), flow.end(), critical,
                [](const auto& item, int key) { return item.first < key; });
            return entry == flow.end() || entry->first != critical || entry->second == 0;
        };
        std::set<std::pair<int, int>> seen;
        const int source = demands[d].from, destination = demands[d].to;
        const auto count = std::min(edges.size(), cedarSeedArcLimit);
        for (std::size_t k = 0; k < count; ++k) {
            if (expired()) return false;
            ++cedarSeedScans;
            const auto& link = edges[k];
            const int first = link.from, second = link.to;
            if (offline[t][k] || first == second || first == source || second == source ||
                first == destination || second == destination || !seen.emplace(first, second).second)
                continue;
            if (prefixes[first] < 0) prefixes[first] = avoids(source, first);
            if (!prefixes[first] || expired()) continue;
            if (suffixes[second] < 0) suffixes[second] = avoids(second, destination);
            if (!suffixes[second] || expired()) continue;
            if (!avoids(first, second) || expired()) continue;
            ++cedarSeedCandidates;
            const Route next{first, second};
            for (auto [left, right] : unique) {
                if (expired()) return false;
                ++checks; ++cedarChecks; ++cedarSeedTrials;
                if (move(d, left, right, next)) {
                    ++cedarAccepted; ++cedarSeedAccepted;
                    return true;
                }
            }
        }
        return false;
    }

