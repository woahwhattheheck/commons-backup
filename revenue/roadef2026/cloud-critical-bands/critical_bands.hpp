// Optional deterministic critical-coordinate bands for the existing fleet loop.
// SPDX-License-Identifier: MIT
#pragma once
#include <algorithm>
#include <cstddef>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace trace_rank {
struct BandReceipt {
    int first, last;
    long long rounds = 0, proposals = 0, accepts = 0;
};
class CriticalBands {
    bool enabled_;
    int limit_, begin_ = 0, end_, offset_ = 0;
    std::size_t active_ = 0;
    std::vector<BandReceipt> receipts_;
public:
    int largest_rank_visited = 0;
    long long expansions = 0, resets = 0;
    CriticalBands(int coordinates, bool enabled, int rank_limit = 0)
        : enabled_(enabled), limit_(rank_limit > 0 ? std::min(coordinates, rank_limit) : coordinates),
          end_(std::min(32, limit_)) {
        if (coordinates < 1 || rank_limit < 0) throw std::invalid_argument("Invalid critical-rank dimensions");
        for (int first = 0, last = end_; first < limit_;) {
            receipts_.push_back({first + 1, last});
            first = last;
            last = static_cast<int>(std::min<long long>(limit_, static_cast<long long>(last) * 2));
        }
    }
    int sort_count() const { return enabled_ ? end_ : std::min(32, limit_); }
    int rank(int stalled) {
        const int selected = enabled_ ? begin_ + offset_ % (end_ - begin_) : stalled % sort_count();
        largest_rank_visited = std::max(largest_rank_visited, selected + 1);
        return selected;
    }
    // Returns true only when the selected rank range has been exhausted.
    bool record(long long proposals, long long accepts, bool adaptive, int stalled) {
        auto &receipt = receipts_[active_];
        ++receipt.rounds; receipt.proposals += proposals; receipt.accepts += accepts;
        if (!enabled_) return adaptive && stalled >= 64;
        if (accepts > 0) {
            begin_ = 0; end_ = std::min(32, limit_); offset_ = 0; active_ = 0; ++resets;
            return false;
        }
        ++offset_;
        if (!adaptive || static_cast<long long>(offset_) < 2LL * (end_ - begin_)) return false;
        if (end_ == limit_) return true;
        begin_ = end_;
        end_ = static_cast<int>(std::min<long long>(limit_, static_cast<long long>(end_) * 2));
        offset_ = 0; ++active_; ++expansions;
        return false;
    }
    void write(const char *path, const char *reason, long long rounds) const {
        if (!path) return;
        std::ofstream out(path);
        if (!out) throw std::runtime_error("Cannot write critical-band diagnostics");
        out << "{\"schema\":\"roadef.critical-bands.v1\",\"enabled\":" << (enabled_ ? "true" : "false")
            << ",\"rank_limit\":" << limit_ << ",\"exit_reason\":\"" << reason
            << "\",\"rounds\":" << rounds << ",\"largest_critical_rank_visited\":" << largest_rank_visited
            << ",\"expansions\":" << expansions << ",\"improvement_resets\":" << resets << ",\"bands\":[";
        for (std::size_t i = 0; i < receipts_.size(); ++i) {
            if (i) out << ',';
            const auto &b = receipts_[i];
            out << "{\"first_rank\":" << b.first << ",\"last_rank\":" << b.last << ",\"rounds\":" << b.rounds
                << ",\"proposals\":" << b.proposals << ",\"accepts\":" << b.accepts << '}';
        }
        out << "]}\n";
        if (!out) throw std::runtime_error("Failed writing critical-band diagnostics");
    }
};
} // namespace trace_rank
