    // DOCK additive neighborhood. Existing ECMP, distance and objective kernel
    // stay authoritative; no tentative schedule is published.
    long long dockAttempted = 0, dockAccepted = 0;
    bool dockMenuLoaded = false;
    std::vector<std::vector<Route>> dockExtraMenu;

    void dockLoadMenu() {
        if (dockMenuLoaded) return;
        dockExtraMenu.resize(demands.size());
        if (const char* path = std::getenv("DOCK_ROUTE_MENU")) {
            auto doc = readJson(path);
            if (!doc.HasMember("routes") || !doc["routes"].IsArray())
                throw std::runtime_error("DOCK_ROUTE_MENU needs routes array");
            for (const auto& item : doc["routes"].GetArray()) {
                if (!item.IsObject() || !item.HasMember("d") || !item["d"].IsInt() ||
                    !item.HasMember("w") || !item["w"].IsArray())
                    throw std::runtime_error("Malformed temporal route menu entry");
                int d = item["d"].GetInt();
                if (d < 0 || static_cast<std::size_t>(d) >= demands.size())
                    throw std::runtime_error("Temporal menu demand out of range");
                Route route;
                for (const auto& value : item["w"].GetArray()) {
                    if (!value.IsInt()) throw std::runtime_error("Noninteger menu waypoint");
                    auto it = std::find(nodeIds.begin(), nodeIds.end(), value.GetInt());
                    if (it == nodeIds.end()) throw std::runtime_error("Unknown menu waypoint");
                    route.push_back(static_cast<int>(it - nodeIds.begin()));
                }
                dockExtraMenu[d].push_back(std::move(route));
            }
        }
        dockMenuLoaded = true;
    }

    bool dockTemporal(int d, const Route& rankedWaypoints = {}) {
        ++dockAttempted;
        dockLoadMenu();
        const std::size_t cap = static_cast<std::size_t>(std::min(64.0, setting("DOCK_TEMPORAL_K", 12)));
        if (cap == 0) return false;
        double deadline = std::min(seconds, elapsed() + setting("DOCK_TEMPORAL_SECONDS", 1.0));
        auto cancelled = [&] { return finished() || elapsed() >= deadline; };
        std::vector<Route> menu;
        auto insert = [&](const Route& route) {
            if (route.size()+1 > static_cast<std::size_t>(maxSegments)) return;
            std::set<int> unique(route.begin(), route.end());
            if (unique.size()!=route.size() || unique.count(demands[d].from) || unique.count(demands[d].to)) return;
            for (int node : route) if (node<0 || node>=n) return;
            if (std::find(menu.begin(),menu.end(),route)==menu.end()) menu.push_back(route);
        };
        // Preserve every incumbent option before capping proposed additions.
        for (int t=0;t<h;++t) insert(routes[d*h+t]);
        if (menu.size()>cap) return false;
        for (const Route& route : dockExtraMenu[d]) {
            if (menu.size()>=cap) break;
            insert(route);
        }
        if (menu.size()<cap) insert({});
        for (int waypoint : rankedWaypoints) {
            if (menu.size()>=cap) break;
            insert({waypoint});
        }
        if (menu.size()<2) return false;
        // This bounds the materialized costs and DP vectors, not a claimed
        // official memory limit. Oversized neighborhoods retain the incumbent.
        if (static_cast<std::size_t>(h)*static_cast<std::size_t>(m)>2000000/menu.size()) return false;
        std::vector<int> residual(h,0);
        for (int t=1;t<h;++t) {
            residual[t]=budget[t]-used[t]+distance(d,routes[d*h+t-1],routes[d*h+t]);
            if (residual[t]<0) throw std::runtime_error("Invalid incumbent temporal budget");
        }
        std::vector<std::vector<dock_temporal::Option>> layers(h,
            std::vector<dock_temporal::Option>(menu.size()));
        for(int t=0;t<h;++t) {
            std::vector<double> base(loads.begin()+t*m,loads.begin()+(t+1)*m);
            for(auto [edge,ratio]:routed[d*h+t]) base[edge]-=ratio*demands[d].volume[t];
            for(std::size_t k=0;k<menu.size();++k) {
                if(cancelled()) return false;
                Sparse flow;
                if(!routeFlow(d,t,menu[k],flow)) { layers[t][k].reachable=false; continue; }
                auto trial=base;
                for(auto [edge,ratio]:flow) trial[edge]+=ratio*demands[d].volume[t];
                auto& objective=layers[t][k].cost;
                objective.reserve(m);
                for(double value:trial) {
                    double scaled=std::floor(std::max(0.0,value)*1e6);
                    if(!std::isfinite(scaled) || scaled>=static_cast<double>(std::numeric_limits<long long>::max()))
                        throw std::runtime_error("Temporal objective outside integer range");
                    objective.push_back(static_cast<long long>(scaled));
                }
                std::sort(objective.begin(),objective.end(),std::greater<long long>());
            }
        }
        std::vector<std::vector<int>> transition(menu.size(),std::vector<int>(menu.size()));
        for(std::size_t a=0;a<menu.size();++a) for(std::size_t b=0;b<menu.size();++b)
            transition[a][b]=distance(d,menu[a],menu[b]);
        auto best=dock_temporal::solve(layers,residual,
            [&](std::size_t,std::size_t a,std::size_t b){return transition[a][b];},cancelled);
        if(!best.complete || !best.feasible || cancelled()) return false;
        std::vector<Route> nextRoutes(h);
        std::vector<Sparse> nextFlows(h);
        std::vector<int> nextUsed=used;
        std::vector<double> nextLoads=loads;
        bool changed=false;
        for(int t=0;t<h;++t) {
            if(cancelled()) return false;
            nextRoutes[t]=menu[static_cast<std::size_t>(best.choices[t])];
            changed |= nextRoutes[t]!=routes[d*h+t];
            if(!routeFlow(d,t,nextRoutes[t],nextFlows[t])) return false;
            for(auto [edge,ratio]:routed[d*h+t]) nextLoads[t*m+edge]-=ratio*demands[d].volume[t];
            for(auto [edge,ratio]:nextFlows[t]) nextLoads[t*m+edge]+=ratio*demands[d].volume[t];
            if(t) {
                nextUsed[t]=used[t]-distance(d,routes[d*h+t-1],routes[d*h+t])+distance(d,nextRoutes[t-1],nextRoutes[t]);
                if(nextUsed[t]>budget[t]) return false;
            }
        }
        if(!changed) return false;
        // Match the incumbent kernel's conservative six-decimal acceptance,
        // independently of the DP's rounded candidate-ranking calculation.
        std::vector<long long> before,after;
        for(std::size_t i=0;i<loads.size();++i) {
            if(std::abs(nextLoads[i]-loads[i])<=1e-12) continue;
            before.push_back(static_cast<long long>(std::floor(std::max(0.0,loads[i]-1e-10)*1e6)));
            after.push_back(static_cast<long long>(std::floor(std::max(0.0,nextLoads[i]+1e-10)*1e6)));
        }
        std::sort(before.begin(),before.end(),std::greater<long long>());
        std::sort(after.begin(),after.end(),std::greater<long long>());
        if(!(after<before) || cancelled()) return false;
        loads=std::move(nextLoads); used=std::move(nextUsed);
        for(int t=0;t<h;++t) {
            routes[d*h+t]=std::move(nextRoutes[t]);
            routed[d*h+t]=std::move(nextFlows[t]);
        }
        ++accepted; ++dockAccepted;
        return true;
    }

