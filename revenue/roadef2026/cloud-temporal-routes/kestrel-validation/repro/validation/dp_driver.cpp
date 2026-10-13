// SPDX-License-Identifier: MIT
// Test-only stdin adapter for the production header (no duplicate optimizer).
#include "temporal_dp.hpp"
#include <iostream>
int main() {
    int cases;
    if (!(std::cin >> cases)) return 2;
    for (int case_id = 0; case_id < cases; ++case_id) {
        int t, k, width, cancel_at;
        std::size_t max_cells;
        std::cin >> t >> k >> width >> cancel_at >> max_cells;
        std::vector<int> budget(t);
        for (auto& value : budget) std::cin >> value;
        std::vector<std::vector<int>> transition(k, std::vector<int>(k));
        for (auto& row : transition) for (auto& value : row) std::cin >> value;
        std::vector<std::vector<kestrel::Option>> rows(t, std::vector<kestrel::Option>(k));
        for (auto& row : rows) for (auto& option : row) {
            int available; std::cin >> available; option.available = available;
            option.descending_loads.resize(width);
            for (auto& value : option.descending_loads) std::cin >> value;
        }
        try {
            int checks = 0;
            auto result = kestrel::optimize(rows, transition, budget,
                [&] { return cancel_at >= 0 && ++checks >= cancel_at; }, max_cells);
            std::cout << static_cast<int>(result.status) << ' ' << result.route_indices.size();
            for (int r : result.route_indices) std::cout << ' ' << r;
            std::cout << ' ' << result.descending_loads.size();
            for (auto value : result.descending_loads) std::cout << ' ' << value;
            std::cout << '\n';
        } catch (const std::invalid_argument&) { std::cout << "error\n"; }
    }
}
