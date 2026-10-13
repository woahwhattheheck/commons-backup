// SEDGE: deterministic local search for ROADEF/EURO 2026 T-adaptive routing.
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
    double initialMlu = 0;

    double elapsed() const {
        return std::chrono::duration<double>(Clock::now() - start).count();
    }
    bool finished() const { return interrupted || elapsed() >= seconds; }

    Dag& dag(int t, int target) {
        auto& ptr = dags[t * n + target];
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
        std::uint64_t key = (static_cast<std::uint64_t>(t) * n + source) * n + target;
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

    bool move(int d, int left, int right, const Route& next) {
        ++attempted;
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
        std::vector<std::pair<int, int>> costs;
        for (int t = std::max(1, left); t <= std::min(h - 1, right + 1); ++t) {
            int value = used[t] - distance(d, routes[d * h + t - 1], routes[d * h + t])
                                  + distance(d, pathAt(t - 1), pathAt(t));
            if (value > budget[t]) return false;
            costs.emplace_back(t, value);
        }
        if (++generation == 0) { std::fill(marked.begin(), marked.end(), 0); ++generation; }
        std::vector<int> touched;
        std::vector<Sparse> replacement(right - left + 1);
        auto add = [&](int i, double value) {
            if (marked[i] != generation) {
                marked[i] = generation; delta[i] = 0; touched.push_back(i);
            }
            delta[i] += value;
        };
        for (int t = left; t <= right; ++t) {
            if (!routeFlow(d, t, next, replacement[t - left])) return false;
            double volume = demands[d].volume[t];
            for (auto [e, ratio] : routed[d * h + t]) add(t * m + e, -volume * ratio);
            for (auto [e, ratio] : replacement[t - left]) add(t * m + e, volume * ratio);
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
        std::sort(before.begin(), before.end(), std::greater<long long>());
        std::sort(after.begin(), after.end(), std::greater<long long>());
        if (!(after < before)) return false;
        for (int i : touched) loads[i] += delta[i];
        for (auto [t, value] : costs) used[t] = value;
        for (int t = left; t <= right; ++t) {
            routes[d * h + t] = next;
            routed[d * h + t] = std::move(replacement[t - left]);
        }
        ++accepted;
        return true;
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
        out << "{\"seconds\":" << elapsed() << ",\"attempted\":" << attempted
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
        budget.assign(h, 0); used.assign(h, 0);
        for (const auto& item : scenario["budget"].GetArray()) budget.at(item["t"].GetInt()) = item["value"].GetInt();
        dags.resize(h * n);
        routes.resize(demands.size() * h); routed.resize(routes.size());
        loads.assign(h * m, 0); delta.resize(loads.size()); marked.assign(loads.size(), 0);
        // An atomic, immediately available empty-waypoint incumbent uses zero changes.
        writeSolution();
        for (std::size_t d = 0; d < demands.size(); ++d) for (int t = 0; t < h; ++t) {
            auto& flow = routed[d * h + t];
            if (!routeFlow(static_cast<int>(d), t, {}, flow))
                throw std::runtime_error("A demand is unreachable in the supplied topology");
            for (auto [e, ratio] : flow) loads[t * m + e] += demands[d].volume[t] * ratio;
        }
        initialMlu = *std::max_element(loads.begin(), loads.end());
        std::cerr << "Loaded " << n << " nodes, " << demands.size() << " demands, " << h
                  << " slots; initial MLU " << initialMlu << "; preparation " << elapsed() << "s\n";
    }

    void run() {
        int stalled = 0;
        bool adaptive = false;
        double lastSave = elapsed();
        for (int round = 0; round < maxRounds && !finished(); ++round) {
            if (elapsed() > seconds * 0.65 || stalled >= 12) adaptive = true;
            std::vector<int> critical(loads.size());
            std::iota(critical.begin(), critical.end(), 0);
            int count = std::min<int>(32, static_cast<int>(critical.size()));
            std::partial_sort(critical.begin(), critical.begin() + count, critical.end(),
                [&](int a, int b) { return loads[a] != loads[b] ? loads[a] > loads[b] : a < b; });
            int position = critical[stalled % count], t = position / m, e = position % m;
            std::vector<std::pair<double, int>> contributors;
            for (std::size_t d = 0; d < demands.size(); ++d) {
                const auto& flow = routed[d * h + t];
                auto it = std::lower_bound(flow.begin(), flow.end(), std::pair<int, double>{e, -1});
                if (it != flow.end() && it->first == e && demands[d].volume[t] > 0)
                    contributors.emplace_back(it->second * demands[d].volume[t], static_cast<int>(d));
            }
            std::sort(contributors.begin(), contributors.end(), [](auto a, auto b) {
                return a.first != b.first ? a.first > b.first : a.second < b.second;
            });
            long long oldAccepted = accepted;
            int limit = std::min<int>(32, static_cast<int>(contributors.size()));
            for (int j = 0; j < limit && !finished(); ++j) {
                int d = contributors[j].second;
                Route candidates;
                if (n <= 50) {
                    candidates.resize(n); std::iota(candidates.begin(), candidates.end(), 0);
                } else {
                    candidates = {edges[e].from, edges[e].to};
                    for (int v : {demands[d].from, demands[d].to, edges[e].from, edges[e].to}) {
                        for (int arc : outgoing[v]) candidates.push_back(edges[arc].to);
                        for (int arc : incoming[v]) candidates.push_back(edges[arc].from);
                    }
                    for (int k = 0; k < 32; ++k) candidates.push_back(static_cast<int>(rng() % n));
                    std::sort(candidates.begin(), candidates.end());
                    candidates.erase(std::unique(candidates.begin(), candidates.end()), candidates.end());
                }
                std::shuffle(candidates.begin(), candidates.end(), rng);
                std::vector<std::pair<int, int>> intervals{{0, h - 1}};
                if (adaptive && h > 1) {
                    intervals.emplace_back(t, t);
                    intervals.emplace_back(0, t);
                    intervals.emplace_back(t, h - 1);
                }
                bool improved = false;
                Route original = routes[d * h + t];
                for (auto [left, right] : intervals) {
                    if (move(d, left, right, {})) { improved = true; break; }
                    for (int w : candidates) {
                        if (finished()) break;
                        if (move(d, left, right, {w})) { improved = true; break; }
                        if (!original.empty()) {
                            Route path = original;
                            for (std::size_t k = 0; k < original.size(); ++k) {
                                path = original; path[k] = w;
                                if (move(d, left, right, path)) { improved = true; break; }
                            }
                            if (!improved && original.size() < 3) {
                                path = original; path.insert(path.begin(), w);
                                improved = move(d, left, right, path);
                                if (!improved) { path = original; path.push_back(w); improved = move(d, left, right, path); }
                            }
                            if (improved) break;
                        }
                    }
                    if (improved) break;
                }
                if (elapsed() - lastSave >= 2) { writeSolution(); lastSave = elapsed(); }
                if (accepted - oldAccepted >= 8) break;
            }
            if (accepted > oldAccepted) stalled = 0; else ++stalled;
            if (adaptive && stalled >= 64) break;
        }
        writeSolution();
        statistics();
        std::cerr << "Completed " << accepted << " improving moves / " << attempted << " attempts; MLU "
                  << *std::max_element(loads.begin(), loads.end()) << "; elapsed " << elapsed() << "s\n";
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
