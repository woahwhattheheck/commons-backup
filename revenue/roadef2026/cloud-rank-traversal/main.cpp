// Fleet candidate: SEDGE/FLORA ECMP kernel with directed and joint neighborhoods.
// Derived from the MIT-licensed SEDGE and FLORA implementations.
// SPDX-License-Identifier: MIT
#include <algorithm>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <numeric>
#include <queue>
#include <random>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>
#include "rapidjson/document.h"
#include "rapidjson/istreamwrapper.h"

using Sparse = std::vector<std::pair<int, double>>;
using Route = std::vector<int>;
using Clock = std::chrono::steady_clock;
static volatile std::sig_atomic_t interrupted = 0;
static void stop(int) { interrupted = 1; }

static rapidjson::Document readJson(const std::string& path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("Cannot read " + path);
    rapidjson::IStreamWrapper stream(in);
    rapidjson::Document doc;
    doc.ParseStream(stream);
    if (doc.HasParseError() || !doc.IsObject())
        throw std::runtime_error("Invalid JSON in " + path);
    return doc;
}
static double setting(const char* name, double fallback) {
    const char* text = std::getenv(name);
    if (!text) return fallback;
    char* end = nullptr;
    double value = std::strtod(text, &end);
    if (end == text || *end || !std::isfinite(value) || value < 0)
        throw std::runtime_error(std::string("Invalid setting ") + name);
    return value;
}
struct Edge { int from, to, id; double metric, capacity; };
struct Demand { int from, to; std::vector<double> volume; };
struct Dag {
    std::vector<double> distance;
    std::vector<int> offset, next;
};

class Solver {
    int n = 0, m = 0, h = 0, maxSegments = 0;
    std::vector<int> nodeIds, budget, used;
    std::vector<Edge> edges;
    std::vector<Demand> demands;
    std::vector<std::vector<int>> incoming, outgoing;
    std::vector<std::vector<bool>> offline;
    // Immutable maintenance-equivalent slots share only topology-derived data.
    // Traffic, routes, loads and transition budgets remain indexed by real time.
    std::vector<int> topologySlot;
    std::vector<std::unique_ptr<Dag>> dags;
    std::unordered_map<std::uint64_t, Sparse> cache;
    std::vector<Route> routes;
    std::vector<Sparse> routed;
    std::vector<double> loads, delta;
    std::vector<unsigned> marked;
    unsigned generation = 0;
    std::mt19937 rng{20260907};
    Clock::time_point start = Clock::now();
    double seconds = setting("SEDGE_SECONDS", 565);
    int maxRounds = static_cast<int>(std::min(setting("SEDGE_MAX_ROUNDS", 1000000), 1000000.0));
    std::string output;
    long long accepted = 0, attempted = 0;
    long long jointAccepted = 0, jointAttempted = 0, rankedCandidates = 0;
    double initialMlu = 0;
    bool resumed = false;
    bool jointEnabled = setting("FLEET_JOINT", 1) != 0;
    bool directedEnabled = setting("FLEET_DIRECTED", 1) != 0;
    int scanLimit = static_cast<int>(setting("FLEET_WAYPOINT_LIMIT", 0));

    struct Change { int d, left, right; Route next; };

    double elapsed() const {
        return std::chrono::duration<double>(Clock::now() - start).count();
    }
    bool finished() const { return interrupted || elapsed() >= seconds; }

    Dag& dag(int t, int target) {
        auto& ptr = dags[topologySlot[t] * n + target];
        if (ptr) return *ptr;
        auto result = std::make_unique<Dag>();
        auto& dist = result->distance;
        dist.assign(n, std::numeric_limits<double>::infinity());
        using Item = std::pair<double, int>;
        std::priority_queue<Item, std::vector<Item>, std::greater<Item>> pending;
        dist[target] = 0;
        pending.emplace(0, target);
        while (!pending.empty()) {
            auto [value, v] = pending.top(); pending.pop();
            if (value != dist[v]) continue;
            for (int e : incoming[v]) {
                if (offline[t][e]) continue;
                const auto& edge = edges[e];
                double next = value + edge.metric;
                if (next < dist[edge.from]) {
                    dist[edge.from] = next;
                    pending.emplace(next, edge.from);
                }
            }
        }
        result->offset.reserve(n + 1);
        for (int u = 0; u < n; ++u) {
            result->offset.push_back(static_cast<int>(result->next.size()));
            if (!std::isfinite(dist[u])) continue;
            for (int e : outgoing[u]) {
                const auto& edge = edges[e];
                if (!offline[t][e] && dist[edge.to] < dist[u] &&
                    std::abs(dist[u] - edge.metric - dist[edge.to]) <= 1e-9)
                    result->next.push_back(e);
            }
        }
        result->offset.push_back(static_cast<int>(result->next.size()));
        ptr = std::move(result);
        return *ptr;
    }

    // A unit flow splits equally at EACH forwarding node, not across whole paths.
    // Values are fractions divided by link capacity, ready for load accumulation.
    const Sparse& segment(int t, int source, int target) {
        std::uint64_t key = (static_cast<std::uint64_t>(topologySlot[t]) * n + source) * n + target;
        auto found = cache.find(key);
        if (found != cache.end()) return found->second;
        if (cache.size() >= 300000) cache.clear();
        Dag& graph = dag(t, target);
        Sparse flow;
        if (!std::isfinite(graph.distance[source])) {
            flow.emplace_back(-1, 0); // explicit unreachable sentinel
        } else if (source != target) {
            std::vector<double> received(n, 0);
            std::vector<bool> queued(n, false);
            std::priority_queue<std::pair<double, int>> pending;
            received[source] = 1;
            queued[source] = true;
            pending.emplace(graph.distance[source], source);
            while (!pending.empty()) {
                int u = pending.top().second; pending.pop();
                int begin = graph.offset[u], end = graph.offset[u + 1];
                if (u == target) continue;
                if (begin == end) throw std::runtime_error("Broken forwarding DAG");
                double fraction = received[u] / (end - begin);
                for (int j = begin; j < end; ++j) {
                    int e = graph.next[j], v = edges[e].to;
                    flow.emplace_back(e, fraction / edges[e].capacity);
                    received[v] += fraction;
                    if (!queued[v]) {
                        queued[v] = true;
                        pending.emplace(graph.distance[v], v);
                    }
                }
            }
            std::sort(flow.begin(), flow.end());
        }
        return cache.emplace(key, std::move(flow)).first->second;
    }

    bool routeFlow(int d, int t, const Route& route, Sparse& flow) {
        flow.clear();
        int from = demands[d].from;
        for (std::size_t k = 0; k <= route.size(); ++k) {
            int to = k == route.size() ? demands[d].to : route[k];
            const auto& part = segment(t, from, to);
            if (!part.empty() && part.front().first == -1) return false;
            flow.insert(flow.end(), part.begin(), part.end());
            from = to;
        }
        std::sort(flow.begin(), flow.end());
        std::size_t out = 0;
        for (auto item : flow) {
            if (out && flow[out - 1].first == item.first) flow[out - 1].second += item.second;
            else flow[out++] = item;
        }
        flow.resize(out);
        return true;
    }

    int distance(int d, const Route& a, const Route& b) const {
        if (a == b) return 0;
        // At most eight segments fit in fixed local storage. Retain unique
        // directed-segment semantics, including repeated/degenerate waypoints.
        // Longer caller routes use the original general-length implementation.
        if (a.size() <= 7 && b.size() <= 7) {
            using Segment = std::pair<int, int>;
            Segment x[8], y[8];
            auto collect = [&](const Route& path, Segment* out) {
                int count = 0;
                int from = demands[d].from;
                auto append = [&](int to) {
                    Segment value{from, to};
                    int j = 0;
                    while (j < count && out[j] != value) ++j;
                    if (j == count) out[count++] = value;
                    from = to;
                };
                for (int to : path) append(to);
                append(demands[d].to);
                return count;
            };
            int nx = collect(a, x), ny = collect(b, y), common = 0;
            for (int i = 0; i < nx; ++i) {
                int j = 0;
                while (j < ny && x[i] != y[j]) ++j;
                common += static_cast<int>(j < ny);
            }
            return nx + ny - 2 * common;
        }
        auto segments = [&](const Route& path) {
            std::set<std::pair<int, int>> result;
            int from = demands[d].from;
            for (int to : path) { result.emplace(from, to); from = to; }
            result.emplace(from, demands[d].to);
            return result;
        };
        auto x = segments(a), y = segments(b);
        int common = 0;
        for (auto item : x) common += static_cast<int>(y.count(item));
        return static_cast<int>(x.size() + y.size()) - 2 * common;
    }

    // Exact first-stratum shortcut; all unresolved comparisons retain the
    // original full descending sort. Quantization remains at the call site.
    static bool quantizedImproves(std::vector<long long>& before,
                                  std::vector<long long>& after) {
        if (before.size() == after.size() && !before.empty()) {
            long long bmax = before.front(), amax = after.front();
            std::size_t bcount = 0, acount = 0;
            for (std::size_t i = 0; i < before.size(); ++i) {
                const auto b = before[i], a = after[i];
                if (b > bmax) { bmax = b; bcount = 1; }
                else if (b == bmax) { ++bcount; }
                if (a > amax) { amax = a; acount = 1; }
                else if (a == amax) { ++acount; }
            }
            if (amax != bmax) {
                return amax < bmax;
            }
            if (acount != bcount) {
                return acount < bcount;
            }
        }
        std::sort(before.begin(), before.end(), std::greater<long long>());
        std::sort(after.begin(), after.end(), std::greater<long long>());
        return after < before;
    }

    // Simultaneous moves are evaluated against the same incumbent. No tentative
    // route is published, and transition capacity released by either demand is
    // available to the other before the combined budget is checked.
    bool moveTogether(const std::vector<Change>& changes) {
        ++attempted;
        if (changes.size() > 1) ++jointAttempted;
        std::set<int> changedDemands;
        std::vector<int> costs = used;
        for (const auto& change : changes) {
            const auto& [d, left, right, next] = change;
            if (!changedDemands.insert(d).second || left < 0 || right >= h || left > right)
                return false;
            if (next.size() + 1 > static_cast<std::size_t>(maxSegments)) return false;
            std::set<int> nodes(next.begin(), next.end());
            if (nodes.size() != next.size() || nodes.count(demands[d].from) || nodes.count(demands[d].to))
                return false;
            bool different = false;
            for (int t = left; t <= right; ++t) different |= routes[d * h + t] != next;
            if (!different) return false;
            auto pathAt = [&](int t) -> const Route& {
                return t >= left && t <= right ? next : routes[d * h + t];
            };
            for (int t = std::max(1, left); t <= std::min(h - 1, right + 1); ++t)
                costs[t] += -distance(d, routes[d * h + t - 1], routes[d * h + t])
                            + distance(d, pathAt(t - 1), pathAt(t));
        }
        for (int t = 1; t < h; ++t) if (costs[t] > budget[t]) return false;
        if (++generation == 0) { std::fill(marked.begin(), marked.end(), 0); ++generation; }
        std::vector<int> touched;
        std::vector<std::vector<Sparse>> replacement(changes.size());
        auto add = [&](int i, double value) {
            if (marked[i] != generation) {
                marked[i] = generation; delta[i] = 0; touched.push_back(i);
            }
            delta[i] += value;
        };
        for (std::size_t k = 0; k < changes.size(); ++k) {
            const auto& [d, left, right, next] = changes[k];
            replacement[k].resize(right - left + 1);
            for (int t = left; t <= right; ++t) {
                if (!routeFlow(d, t, next, replacement[k][t - left])) return false;
                double volume = demands[d].volume[t];
                for (auto [e, ratio] : routed[d * h + t]) add(t * m + e, -volume * ratio);
                for (auto [e, ratio] : replacement[k][t - left]) add(t * m + e, volume * ratio);
            }
        }
        // Unchanged multiset elements cancel under sorted lexicographic comparison.
        // The checker truncates decimal output. Use conservative bounds around
        // each changed load so sub-nanoscopic accumulation noise is not a gain.
        std::vector<long long> before, after;
        before.reserve(touched.size()); after.reserve(touched.size());
        for (int i : touched) {
            if (std::abs(delta[i]) <= 1e-12) continue;
            before.push_back(static_cast<long long>(std::floor(std::max(0.0, loads[i] - 1e-10) * 1e6)));
            after.push_back(static_cast<long long>(std::floor(std::max(0.0, loads[i] + delta[i] + 1e-10) * 1e6)));
        }
        if (!quantizedImproves(before, after)) return false;
        for (int i : touched) loads[i] += delta[i];
        used = std::move(costs);
        for (std::size_t k = 0; k < changes.size(); ++k) {
            const auto& [d, left, right, next] = changes[k];
            for (int t = left; t <= right; ++t) {
                routes[d * h + t] = next;
                routed[d * h + t] = std::move(replacement[k][t - left]);
            }
        }
        ++accepted;
        if (changes.size() > 1) ++jointAccepted;
        return true;
    }

    bool move(int d, int left, int right, const Route& next) {
        return moveTogether({{d, left, right, next}});
    }

    static double coefficient(const Sparse& flow, int edge) {
        auto found = std::lower_bound(flow.begin(), flow.end(), std::pair<int, double>{edge, -1});
        return found != flow.end() && found->first == edge ? found->second : 0;
    }

    std::vector<std::pair<double, int>> contributors(int t, int edge, int excluded = -1) const {
        std::vector<std::pair<double, int>> result;
        for (int d = 0; d < static_cast<int>(demands.size()); ++d) {
            if (d == excluded || demands[d].volume[t] <= 0) continue;
            double value = coefficient(routed[d * h + t], edge) * demands[d].volume[t];
            if (value > 0) result.emplace_back(value, d);
        }
        std::sort(result.begin(), result.end(), [](auto a, auto b) {
            return a.first != b.first ? a.first > b.first : a.second < b.second;
        });
        return result;
    }

    // This score orders the neighborhood only. Acceptance always uses the full
    // exact six-decimal vector in moveTogether, across every changed time slot.
    // Pending is the first leg of a proposed ejection, applied only in this local
    // scoring model so the second demand sees the capacity it must free.
    Route waypointCandidates(int d, int t, int edge, int pendingDemand = -1,
                             const Sparse* pending = nullptr,
                             double deadline = std::numeric_limits<double>::infinity()) {
        Route candidates;
        if (!directedEnabled && !pending) {
            if (n <= 50) {
                candidates.resize(n); std::iota(candidates.begin(), candidates.end(), 0);
            } else {
                candidates = {edges[edge].from, edges[edge].to};
                for (int v : {demands[d].from, demands[d].to, edges[edge].from, edges[edge].to}) {
                    for (int arc : outgoing[v]) candidates.push_back(edges[arc].to);
                    for (int arc : incoming[v]) candidates.push_back(edges[arc].from);
                }
                for (int k = 0; k < 32; ++k) candidates.push_back(static_cast<int>(rng() % n));
                std::sort(candidates.begin(), candidates.end());
                candidates.erase(std::unique(candidates.begin(), candidates.end()), candidates.end());
            }
            std::shuffle(candidates.begin(), candidates.end(), rng);
            return candidates;
        }
        std::vector<double> base(loads.begin() + t * m, loads.begin() + (t + 1) * m);
        for (auto [e, ratio] : routed[d * h + t]) base[e] -= ratio * demands[d].volume[t];
        if (pending) {
            for (auto [e, ratio] : routed[pendingDemand * h + t]) base[e] -= ratio * demands[pendingDemand].volume[t];
            for (auto [e, ratio] : *pending) base[e] += ratio * demands[pendingDemand].volume[t];
        }
        double basePeak = *std::max_element(base.begin(), base.end());
        double scale = std::max(basePeak, 1e-6);
        auto power = [scale](double x) { x = std::max(0.0, x) / scale; x *= x; x *= x; return x * x; };
        struct Ranked { double peak, potential, critical; int waypoint; };
        std::vector<Ranked> ranked;
        int count = scanLimit > 0 ? std::min(n, scanLimit) : n;
        int offset = count < n ? static_cast<int>(rng() % n) : 0;
        for (int k = 0; k < count && !finished() && elapsed() < deadline; ++k) {
            int w = (k + offset) % n;
            if (w == demands[d].from || w == demands[d].to) continue;
            Sparse flow;
            if (!routeFlow(d, t, {w}, flow)) continue;
            double peak = basePeak, potential = 0;
            for (auto [e, ratio] : flow) {
                double next = base[e] + ratio * demands[d].volume[t];
                peak = std::max(peak, next);
                potential += power(next) - power(base[e]);
            }
            ranked.push_back({peak, potential, coefficient(flow, edge), w});
            ++rankedCandidates;
        }
        std::sort(ranked.begin(), ranked.end(), [](const Ranked& a, const Ranked& b) {
            if (a.peak != b.peak) return a.peak < b.peak;
            if (a.potential != b.potential) return a.potential < b.potential;
            if (a.critical != b.critical) return a.critical < b.critical;
            return a.waypoint < b.waypoint;
        });
        for (const auto& item : ranked) candidates.push_back(item.waypoint);
        return candidates;
    }

    // At a one-demand local minimum, route one contributor away from the
    // critical edge, then reroute a contributor on a newly burdened edge.
    // Both moves share an interval and are committed atomically only if their
    // combined result strictly improves the incumbent and fits every budget.
    bool eject(int t, int criticalEdge, const std::vector<std::pair<double, int>>& firstDemands,
               bool adaptive) {
        if (!jointEnabled || maxSegments < 2) return false;
        // Keep a difficult exchange from monopolizing the remaining search.
        // Explicit fixed-round verification disables this secondary wall-clock
        // slice; the overall process deadline remains active in either mode.
        double deadline = std::getenv("SEDGE_MAX_ROUNDS") ? seconds
            : std::min(seconds, elapsed() + std::min(3.0, std::max(0.1, seconds * 0.1)));
        auto exhausted = [&] { return finished() || elapsed() >= deadline; };
        int demandLimit = std::min<int>(4, firstDemands.size());
        for (int first = 0; first < demandLimit && !exhausted(); ++first) {
            int d = firstDemands[first].second;
            auto candidates = waypointCandidates(d, t, criticalEdge, -1, nullptr, deadline);
            int tried = 0;
            for (int w : candidates) {
                if (exhausted() || tried >= 6) break;
                if (routes[d * h + t] == Route{w}) continue;
                Sparse next;
                if (!routeFlow(d, t, {w}, next)) continue;
                if (coefficient(next, criticalEdge) >= coefficient(routed[d * h + t], criticalEdge) - 1e-12)
                    continue;
                ++tried;
                std::vector<std::pair<double, int>> burdened;
                for (auto [e, ratio] : next) {
                    double increase = demands[d].volume[t] * (ratio - coefficient(routed[d * h + t], e));
                    if (increase > 1e-12) burdened.emplace_back(loads[t * m + e] + increase, e);
                }
                std::sort(burdened.begin(), burdened.end(), std::greater<std::pair<double, int>>());
                if (burdened.size() > 2) burdened.resize(2);
                for (auto [ignored, edge] : burdened) {
                    (void)ignored;
                    auto secondDemands = contributors(t, edge, d);
                    if (secondDemands.size() > 4) secondDemands.resize(4);
                    for (auto [amount, second] : secondDemands) {
                        (void)amount;
                        if (exhausted()) return false;
                        auto secondCandidates = waypointCandidates(second, t, edge, d, &next, deadline);
                        if (secondCandidates.size() > 12) secondCandidates.resize(12);
                        std::vector<Route> secondRoutes{{}};
                        for (int v : secondCandidates) secondRoutes.push_back({v});
                        std::vector<std::pair<int, int>> intervals{{0, h - 1}};
                        if (adaptive && h > 1) {
                            intervals.emplace_back(t, t);
                            intervals.emplace_back(std::max(0, t - 1), std::min(h - 1, t + 1));
                            intervals.emplace_back(0, t);
                            intervals.emplace_back(t, h - 1);
                        }
                        for (auto [left, right] : intervals) for (const auto& secondRoute : secondRoutes) {
                            if (exhausted()) return false;
                            if (moveTogether({{d, left, right, {w}}, {second, left, right, secondRoute}})) return true;
                        }
                    }
                }
            }
        }
        return false;
    }

    void writeSolution() const {
        std::string temporary = output + ".tmp";
        std::ofstream out(temporary);
        if (!out) throw std::runtime_error("Cannot write " + temporary);
        out << "{\"srpaths\":[";
        bool comma = false;
        for (std::size_t d = 0; d < demands.size(); ++d) {
            for (int t = 0; t < h; ++t) {
                const auto& path = routes[d * h + t];
                if (path.empty()) continue;
                if (comma) out << ',';
                comma = true;
                out << "{\"d\":" << d << ",\"t\":" << t << ",\"w\":[";
                for (std::size_t j = 0; j < path.size(); ++j) {
                    if (j) out << ',';
                    out << nodeIds[path[j]];
                }
                out << "]}";
            }
        }
        out << "]}\n";
        out.close();
        if (!out) throw std::runtime_error("Failed writing " + temporary);
        std::filesystem::rename(temporary, output);
    }

    void statistics() const {
        const char* path = std::getenv("SEDGE_STATS");
        if (!path) return;
        std::ofstream out(path);
        out.precision(17);
        out << "{\"seconds\":" << elapsed() << ",\"resumed\":" << (resumed ? "true" : "false")
            << ",\"attempted\":" << attempted
            << ",\"joint_attempted\":" << jointAttempted << ",\"joint_accepted\":" << jointAccepted
            << ",\"ranked_candidates\":" << rankedCandidates
            << ",\"accepted\":" << accepted << ",\"initial_mlu\":" << initialMlu
            << ",\"final_mlu\":" << *std::max_element(loads.begin(), loads.end())
            << ",\"budget_used\":[";
        for (int t = 0; t < h; ++t) { if (t) out << ','; out << used[t]; }
        out << "],\"loads\":[";
        for (int t = 0; t < h; ++t) for (int e = 0; e < m; ++e) {
            if (t || e) out << ',';
            out << "{\"t\":" << t << ",\"from\":" << nodeIds[edges[e].from]
                << ",\"to\":" << nodeIds[edges[e].to] << ",\"sat\":" << std::max(0.0, loads[t*m+e]) << '}';
        }
        out << "]}\n";
    }

public:
    Solver(const std::string& netPath, const std::string& tmPath,
           const std::string& scenarioPath, std::string outputPath) : output(std::move(outputPath)) {
        auto net = readJson(netPath), tm = readJson(tmPath), scenario = readJson(scenarioPath);
        std::unordered_map<int, int> nodeIndex, edgeIndex;
        for (const auto& node : net["nodes"].GetArray()) {
            int id = node["id"].GetInt();
            if (!nodeIndex.emplace(id, n++).second) throw std::runtime_error("Duplicate node ID");
            nodeIds.push_back(id);
        }
        incoming.resize(n); outgoing.resize(n);
        for (const auto& link : net["links"].GetArray()) {
            Edge edge{nodeIndex.at(link["from"].GetInt()), nodeIndex.at(link["to"].GetInt()),
                      link["id"].GetInt(), link["metric"].GetDouble(), link["capacity"].GetDouble()};
            if (edge.metric <= 0 || edge.capacity <= 0) throw std::runtime_error("Nonpositive metric/capacity");
            if (!edgeIndex.emplace(edge.id, m).second) throw std::runtime_error("Duplicate link ID");
            outgoing[edge.from].push_back(m); incoming[edge.to].push_back(m++);
            edges.push_back(edge);
        }
        h = tm["num_time_slots"].GetInt();
        maxSegments = scenario["max_segments"].GetInt();
        if (h < 1 || n < 1 || m < 1 || maxSegments < 1) throw std::runtime_error("Empty instance");
        for (const auto& item : tm["demands"].GetArray()) {
            Demand demand{nodeIndex.at(item["s"].GetInt()), nodeIndex.at(item["t"].GetInt()), {}};
            for (const auto& value : item["v"].GetArray()) demand.volume.push_back(value.GetDouble());
            if (demand.volume.size() != static_cast<std::size_t>(h)) throw std::runtime_error("Traffic horizon mismatch");
            demands.push_back(std::move(demand));
        }
        offline.assign(h, std::vector<bool>(m, false));
        for (const auto& item : scenario["interventions"].GetArray()) {
            int t = item["t"].GetInt();
            for (const auto& link : item["links"].GetArray()) offline.at(t).at(edgeIndex.at(link.GetInt())) = true;
        }
        // Equality uses the complete link mask, including nonconsecutive slots
        // and bits past a machine word; equal counts alone are insufficient.
        topologySlot.resize(h);
        for (int t = 0; t < h; ++t) {
            topologySlot[t] = t;
            for (int prior = 0; prior < t; ++prior) {
                if (offline[t] == offline[prior]) {
                    topologySlot[t] = topologySlot[prior];
                    break;
                }
            }
        }
        budget.assign(h, 0); used.assign(h, 0);
        for (const auto& item : scenario["budget"].GetArray()) budget.at(item["t"].GetInt()) = item["value"].GetInt();
        dags.resize(h * n);
        routes.resize(demands.size() * h); routed.resize(routes.size());
        loads.assign(h * m, 0); delta.resize(loads.size()); marked.assign(loads.size(), 0);
        // Do not overwrite a resume file before reading it when the caller uses
        // the same path for the incumbent and output. A cold run checkpoints its
        // zero-change routing immediately; a resume checkpoints after validation.
        if (!std::getenv("CLOUD_INITIAL_SOLUTION")) writeSolution();
        for (std::size_t d = 0; d < demands.size(); ++d) for (int t = 0; t < h; ++t) {
            auto& flow = routed[d * h + t];
            if (!routeFlow(static_cast<int>(d), t, {}, flow))
                throw std::runtime_error("A demand is unreachable in the supplied topology");
            for (auto [e, ratio] : flow) loads[t * m + e] += demands[d].volume[t] * ratio;
        }
        if (const char* incumbentPath = std::getenv("CLOUD_INITIAL_SOLUTION")) {
            auto incumbent = readJson(incumbentPath);
            if (!incumbent.HasMember("srpaths") || !incumbent["srpaths"].IsArray())
                throw std::runtime_error("Initial solution has no srpaths array");
            std::vector<Route> nextRoutes(routes.size());
            std::set<std::pair<int, int>> seen;
            for (const auto& item : incumbent["srpaths"].GetArray()) {
                if (!item.HasMember("d") || !item.HasMember("t") || !item.HasMember("w") ||
                    !item["d"].IsInt() || !item["t"].IsInt() || !item["w"].IsArray())
                    throw std::runtime_error("Malformed initial route");
                int d = item["d"].GetInt(), t = item["t"].GetInt();
                if (d < 0 || d >= static_cast<int>(demands.size()) || t < 0 || t >= h ||
                    !seen.emplace(d, t).second)
                    throw std::runtime_error("Invalid or duplicate initial route index");
                Route route;
                for (const auto& waypoint : item["w"].GetArray()) {
                    if (!waypoint.IsInt() || !nodeIndex.count(waypoint.GetInt()))
                        throw std::runtime_error("Unknown initial waypoint");
                    route.push_back(nodeIndex.at(waypoint.GetInt()));
                }
                if (route.size() + 1 > static_cast<std::size_t>(maxSegments))
                    throw std::runtime_error("Initial route exceeds segment limit");
                std::set<int> unique(route.begin(), route.end());
                if (unique.size() != route.size() || unique.count(demands[d].from) || unique.count(demands[d].to))
                    throw std::runtime_error("Initial route repeats an endpoint or waypoint");
                nextRoutes[d * h + t] = std::move(route);
            }
            std::vector<Sparse> nextRouted(routes.size());
            std::vector<double> nextLoads(loads.size(), 0);
            for (std::size_t d = 0; d < demands.size(); ++d) for (int t = 0; t < h; ++t) {
                auto& flow = nextRouted[d * h + t];
                if (!routeFlow(static_cast<int>(d), t, nextRoutes[d * h + t], flow))
                    throw std::runtime_error("Initial route is unreachable");
                for (auto [e, ratio] : flow)
                    nextLoads[t * m + e] += demands[d].volume[t] * ratio;
            }
            std::vector<int> nextUsed(h, 0);
            for (int t = 1; t < h; ++t) {
                for (std::size_t d = 0; d < demands.size(); ++d)
                    nextUsed[t] += distance(static_cast<int>(d), nextRoutes[d * h + t - 1], nextRoutes[d * h + t]);
                if (nextUsed[t] > budget[t])
                    throw std::runtime_error("Initial route exceeds transition budget");
            }
            routes = std::move(nextRoutes);
            routed = std::move(nextRouted);
            loads = std::move(nextLoads);
            used = std::move(nextUsed);
            resumed = true;
            writeSolution();
        }
        initialMlu = *std::max_element(loads.begin(), loads.end());
        std::cerr << "Loaded " << n << " nodes, " << demands.size() << " demands, " << h
                  << " slots; initial MLU " << initialMlu << "; preparation " << elapsed() << "s\n";
    }

    // PRISM proposal body retained from commons PR10430,
    // merged 73a805e290cee36981917ac09e7ce2133f35afd7 (cloud-a-rank1).
    // Scheduler idea: PR10451 / TRACE; PRISM owns the proposal mechanism.
    // PR10451 merge: 4b1dcaa793f9b54f13c287d766e6094f2faf4ac8.
    // This separate opt-in uses a finite sweep, not rank-band cycling.
    // The e801 natural-exhaustion guard and allowance remain unchanged.

    // Opt-in bounded proposals at the selected load coordinate before
    // returning to the ordinary search. All proposed routes still enter through
    // move()/moveTogether(), so exact ECMP, segment limits, transition budgets,
    // and the full sorted six-decimal acceptance rule remain authoritative.
    void rankOne() {
        int passLimit = static_cast<int>(std::min(128.0, setting("FLEET_RANK1_PASSES", 16)));
        int demandLimitSetting = static_cast<int>(std::min(256.0, setting("FLEET_RANK1_DEMANDS", 32)));
        int pairNodeLimit = static_cast<int>(std::min(96.0, setting("FLEET_RANK1_PAIR_NODES", 24)));
        const char* reportPath = std::getenv("FLEET_RANK1_REPORT");
        bool rankTraversal = setting("FLEET_POLISH_RANK_TRAVERSAL", 0) != 0;
        int rankLimit = std::min<int>(static_cast<int>(loads.size()), passLimit);
        int rankCursor = 0;
        std::vector<int> coordinateOrder;
        const char* schedulerStop = "pass_budget";
        struct PassRecord {
            int pass, t, edge, from, to, contributors;
            double before, after;
            long long attemptsBefore, attemptsAfter, acceptedBefore, acceptedAfter;
            bool ejection;
            std::vector<std::pair<int, double>> top;
            int selectedRank = 1;
            const char* passOutcome = "configured_pass_exhaustion";
        };
        std::vector<PassRecord> records;
        auto appendWindow = [](std::vector<std::pair<int, int>>& windows, int left, int right) {
            std::pair<int, int> item{left, right};
            if (std::find(windows.begin(), windows.end(), item) == windows.end()) windows.push_back(item);
        };
        for (int pass = 0; pass < passLimit && !finished(); ++pass) {
            int position = 0;
            if (rankTraversal) {
                if (rankCursor == 0) {
                    coordinateOrder.resize(loads.size());
                    std::iota(coordinateOrder.begin(), coordinateOrder.end(), 0);
                    std::partial_sort(coordinateOrder.begin(), coordinateOrder.begin() + rankLimit,
                                      coordinateOrder.end(), [&](int a, int b) {
                        return loads[a] != loads[b] ? loads[a] > loads[b] : a < b;
                    });
                }
                position = coordinateOrder[rankCursor];
            } else {
                for (int i = 1; i < static_cast<int>(loads.size()); ++i)
                    if (loads[i] > loads[position]) position = i;
            }
            int t = position / m, edge = position % m;
            double before = loads[position];
            auto contributing = contributors(t, edge);
            PassRecord record{pass, t, edge, nodeIds[edges[edge].from], nodeIds[edges[edge].to],
                              static_cast<int>(contributing.size()), before, before,
                              attempted, attempted, accepted, accepted, false, {}};
            for (int i = 0; i < std::min<int>(32, contributing.size()); ++i)
                record.top.emplace_back(contributing[i].second, contributing[i].first);
            long long acceptedBefore = accepted;
            int demandLimit = std::min<int>(demandLimitSetting, contributing.size());
            for (int j = 0; j < demandLimit && accepted == acceptedBefore && !finished(); ++j) {
                int d = contributing[j].second;
                Route original = routes[d * h + t];
                std::vector<std::pair<int, int>> windows;
                appendWindow(windows, t, t);
                if (h > 1) {
                    for (int radius : {1, 2, 3})
                        appendWindow(windows, std::max(0, t - radius), std::min(h - 1, t + radius));
                    appendWindow(windows, 0, t);
                    appendWindow(windows, t, h - 1);
                }
                appendWindow(windows, 0, h - 1);

                auto tryPath = [&](const Route& path) {
                    for (auto [left, right] : windows) {
                        if (finished()) return false;
                        if (move(d, left, right, path)) return true;
                    }
                    return false;
                };

                if (tryPath({})) break;
                for (std::size_t k = 0; k < original.size() && accepted == acceptedBefore && !finished(); ++k) {
                    Route path = original;
                    path.erase(path.begin() + static_cast<std::ptrdiff_t>(k));
                    if (tryPath(path)) break;
                }
                if (accepted != acceptedBefore || finished()) break;

                // This ranks every node when FLEET_WAYPOINT_LIMIT is unset, but
                // unlike run() it does not truncate the returned candidate list.
                auto candidates = waypointCandidates(d, t, edge);
                for (int w : candidates) {
                    if (finished() || accepted != acceptedBefore) break;
                    if (tryPath({w})) break;
                    for (std::size_t k = 0; k < original.size() && accepted == acceptedBefore; ++k) {
                        Route path = original;
                        path[k] = w;
                        if (tryPath(path)) break;
                    }
                    if (accepted != acceptedBefore) break;
                    if (original.size() + 1 < static_cast<std::size_t>(maxSegments)) {
                        for (std::size_t k = 0; k <= original.size() && accepted == acceptedBefore; ++k) {
                            Route path = original;
                            path.insert(path.begin() + static_cast<std::ptrdiff_t>(k), w);
                            if (tryPath(path)) break;
                        }
                    }
                }
                if (accepted != acceptedBefore || finished() || maxSegments < 3) break;

                int pairLimit = std::min<int>(pairNodeLimit, candidates.size());
                for (int a = 0; a < pairLimit && accepted == acceptedBefore && !finished(); ++a) {
                    for (int b = 0; b < pairLimit && accepted == acceptedBefore && !finished(); ++b) {
                        if (a == b) continue;
                        if (tryPath({candidates[a], candidates[b]})) break;
                    }
                }
            }
            if (accepted == acceptedBefore && !finished()) {
                record.ejection = eject(t, edge, contributing, true);
            }
            record.after = loads[t * m + edge];
            record.attemptsAfter = attempted;
            record.acceptedAfter = accepted;
            if (rankTraversal) {
                record.selectedRank = rankCursor + 1;
                record.passOutcome = accepted != acceptedBefore ? "accepted_move"
                    : interrupted ? "signal" : elapsed() >= seconds ? "deadline"
                    : "configured_pass_exhaustion";
            }
            records.push_back(std::move(record));
            writeSolution();
            // A no-accept result exhausts this configured pass, not all routes.
            if (!rankTraversal) {
                if (accepted == acceptedBefore) break;
                continue;
            }
            const auto& completed = records.back();
            std::cerr << "FLEET_POLISH {\"event\":\"rank_pass\",\"pass\":" << pass
                      << ",\"selected_rank\":" << completed.selectedRank
                      << ",\"coordinate\":" << position << ",\"outcome\":\""
                      << completed.passOutcome << "\",\"attempted\":"
                      << (completed.attemptsAfter - completed.attemptsBefore)
                      << ",\"accepted\":" << (completed.acceptedAfter - completed.acceptedBefore)
                      << "}\n";
            if (finished()) {
                schedulerStop = interrupted ? "signal" : "deadline";
                break;
            }
            if (accepted != acceptedBefore) {
                rankCursor = 0;
            } else if (++rankCursor >= rankLimit) {
                schedulerStop = "configured_sweep_exhaustion";
                break;
            }
        }
        if (rankTraversal) {
            if (interrupted) schedulerStop = "signal";
            else if (elapsed() >= seconds) schedulerStop = "deadline";
            std::cerr << "FLEET_POLISH {\"event\":\"rank_stop\",\"reason\":\""
                      << schedulerStop << "\",\"passes\":" << records.size()
                      << ",\"pass_limit\":" << passLimit << ",\"rank_limit\":" << rankLimit
                      << ",\"last_selected_rank\":"
                      << (records.empty() ? 0 : records.back().selectedRank) << "}\n";
        }
        writeSolution();
        statistics();
        if (reportPath) {
            std::string temporary = std::string(reportPath) + ".tmp";
            std::ofstream out(temporary);
            if (!out) throw std::runtime_error("Cannot write " + temporary);
            out.precision(17);
            out << "{\"schema\":\"roadef.rank-one-diversion.v1\",\"passes\":[";
            for (std::size_t i = 0; i < records.size(); ++i) {
                if (i) out << ',';
                const auto& r = records[i];
                out << "{\"pass\":" << r.pass;
                if (rankTraversal) {
                    out << ",\"selected_rank\":" << r.selectedRank
                        << ",\"outcome\":\"" << r.passOutcome << "\"";
                }
                out << ",\"t\":" << r.t
                    << ",\"edge\":" << r.edge << ",\"from\":" << r.from
                    << ",\"to\":" << r.to << ",\"before\":" << r.before
                    << ",\"after\":" << r.after << ",\"contributors\":" << r.contributors
                    << ",\"attempts\":" << (r.attemptsAfter - r.attemptsBefore)
                    << ",\"accepted\":" << (r.acceptedAfter - r.acceptedBefore)
                    << ",\"ejection\":" << (r.ejection ? "true" : "false")
                    << ",\"top_contributors\":[";
                for (std::size_t j = 0; j < r.top.size(); ++j) {
                    if (j) out << ',';
                    out << "{\"d\":" << r.top[j].first << ",\"load\":" << r.top[j].second << '}';
                }
                out << "]}";
            }
            out << "],\"attempted\":" << attempted << ",\"accepted\":" << accepted
                << ",\"elapsed\":" << elapsed();
            if (rankTraversal) {
                out << ",\"rank_traversal\":true,\"rank_limit\":" << rankLimit
                    << ",\"stop_reason\":\"" << schedulerStop << "\"";
            }
            out << "}\n";
            out.close();
            if (!out) throw std::runtime_error("Failed writing " + temporary);
            std::filesystem::rename(temporary, reportPath);
        }
        std::cerr << "Rank-one pass completed " << accepted << " improving moves / "
                  << attempted << " attempts; MLU " << *std::max_element(loads.begin(), loads.end())
                  << "; elapsed " << elapsed() << "s\n";
    }

    void polishAfterExhaustion(bool naturallyExhausted) {
        if (setting("FLEET_POLISH_AFTER_EXHAUSTION", 0) == 0) return;
        const double phaseStart = elapsed();
        const char* reason = interrupted ? "signal" : phaseStart >= seconds ? "deadline"
            : naturallyExhausted ? nullptr : "round_limit";
        if (reason) {
            std::cerr << "FLEET_POLISH {\"event\":\"skipped\",\"reason\":\"" << reason
                      << "\",\"elapsed\":" << phaseStart << ",\"remaining\":"
                      << std::max(0.0, seconds - phaseStart) << "}\n";
            return;
        }
        const long long attemptsBefore = attempted, acceptedBefore = accepted;
        std::cerr << "FLEET_POLISH {\"event\":\"begin\",\"reason\":\"natural_exhaustion\","
                  << "\"elapsed\":" << phaseStart << ",\"remaining\":" << (seconds - phaseStart)
                  << ",\"attempted_before\":" << attemptsBefore
                  << ",\"accepted_before\":" << acceptedBefore << "}\n";
        rankOne();
        const double phaseEnd = elapsed();
        std::cerr << "FLEET_POLISH {\"event\":\"end\",\"reason\":\""
                  << (interrupted ? "signal" : phaseEnd >= seconds ? "deadline" : "completed")
                  << "\",\"elapsed\":" << phaseEnd << ",\"phase_seconds\":" << (phaseEnd - phaseStart)
                  << ",\"remaining\":" << std::max(0.0, seconds - phaseEnd)
                  << ",\"attempted\":" << (attempted - attemptsBefore)
                  << ",\"accepted\":" << (accepted - acceptedBefore) << "}\n";
    }

    void run() {
        bool naturallyExhausted = false;
        int stalled = 0;
        // A resumed incumbent has already exhausted the broad early search;
        // enter the complementary window neighborhood immediately.
        bool adaptive = resumed;
        double lastSave = elapsed();
        for (int round = 0; round < maxRounds && !finished(); ++round) {
            if (elapsed() > seconds * 0.65 || stalled >= 12) adaptive = true;
            std::vector<int> critical(loads.size());
            std::iota(critical.begin(), critical.end(), 0);
            int count = std::min<int>(32, static_cast<int>(critical.size()));
            std::partial_sort(critical.begin(), critical.begin() + count, critical.end(),
                [&](int a, int b) { return loads[a] != loads[b] ? loads[a] > loads[b] : a < b; });
            int position = critical[stalled % count], t = position / m, e = position % m;
            auto contributing = contributors(t, e);
            long long oldAccepted = accepted;
            int limit = std::min<int>(32, static_cast<int>(contributing.size()));
            for (int j = 0; j < limit && !finished(); ++j) {
                int d = contributing[j].second;
                Route candidates = waypointCandidates(d, t, e);
                // Ranking considers the full node set by default; reserve the
                // expensive multi-slot evaluation for its strongest candidates.
                // Broaden deterministically when the current search stalls.
                if (directedEnabled) {
                    std::size_t limitCandidates = stalled < 8 ? 48 : stalled < 24 ? 128 : candidates.size();
                    if (candidates.size() > limitCandidates) candidates.resize(limitCandidates);
                }
                std::vector<std::pair<int, int>> intervals{{0, h - 1}};
                if (adaptive && h > 1) {
                    intervals.emplace_back(t, t);
                    // Transition budgets often permit a short stable run even
                    // when a single-slot change or a full prefix/suffix does
                    // not.  Search local windows before the larger intervals.
                    for (int radius : {1, 2, 3}) {
                        int left = std::max(0, t - radius);
                        int right = std::min(h - 1, t + radius);
                        if (left != 0 || right != h - 1)
                            intervals.emplace_back(left, right);
                    }
                    intervals.emplace_back(0, t);
                    intervals.emplace_back(t, h - 1);
                }
                bool improved = false;
                Route original = routes[d * h + t];
                for (auto [left, right] : intervals) {
                    if (move(d, left, right, {})) { improved = true; break; }
                    for (std::size_t k = 0; k < original.size(); ++k) {
                        Route path = original; path.erase(path.begin() + k);
                        if (move(d, left, right, path)) { improved = true; break; }
                    }
                    if (improved) break;
                    for (int w : candidates) {
                        if (finished()) break;
                        if (move(d, left, right, {w})) { improved = true; break; }
                        if (!original.empty()) {
                            Route path = original;
                            for (std::size_t k = 0; k < original.size(); ++k) {
                                path = original; path[k] = w;
                                if (move(d, left, right, path)) { improved = true; break; }
                            }
                            if (!improved && original.size() + 1 < static_cast<std::size_t>(maxSegments)) {
                                for (std::size_t k = 0; k <= original.size(); ++k) {
                                    path = original; path.insert(path.begin() + k, w);
                                    if (move(d, left, right, path)) { improved = true; break; }
                                }
                            }
                            if (improved) break;
                        }
                    }
                    if (improved) break;
                }
                if (elapsed() - lastSave >= 2) { writeSolution(); lastSave = elapsed(); }
                if (accepted - oldAccepted >= 8) break;
            }
            if (accepted == oldAccepted && !finished() && stalled % 4 == 3)
                eject(t, e, contributing, adaptive);
            if (accepted > oldAccepted) stalled = 0; else ++stalled;
            if (adaptive && stalled >= 64) { naturallyExhausted = true; break; }
        }
        writeSolution();
        statistics();
        std::cerr << "Completed " << accepted << " improving moves / " << attempted << " attempts; MLU "
                  << *std::max_element(loads.begin(), loads.end()) << "; elapsed " << elapsed() << "s\n";
        polishAfterExhaustion(naturallyExhausted);
    }
};

int main(int argc, char** argv) {
    if (argc != 5) {
        std::cerr << "Usage: " << argv[0] << " network.json traffic.json scenario.json output.json\n";
        return 2;
    }
    std::signal(SIGTERM, stop);
    std::signal(SIGINT, stop);
    try { Solver solver(argv[1], argv[2], argv[3], argv[4]); solver.run(); }
    catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
