template<class A, class B> void verify(A& a, B& b, long long& queries, long long& entries) {
    for (int d=0;d<(int)a.demands.size();++d) for(int t=0;t<a.h;++t) {
        std::vector<std::vector<int>> paths{{}};
        for(int w=0;w<a.n;++w) paths.push_back({w});
        for(int w=0;w<a.n;++w) {
            paths.push_back({w,(w+1)%a.n});
            paths.push_back({w,(w+1)%a.n,(w+3)%a.n});
        }
        for (const auto& path:paths) {
            baseline::Sparse x{{999,0.123}}, y{{999,0.123}};
            bool ax=a.routeFlow(d,t,path,x), by=b.routeFlow(d,t,path,y);
            if(ax!=by || x!=y) throw std::runtime_error("flow mismatch");
            for(std::size_t i=0;i<x.size();++i)
                if(std::memcmp(&x[i].second,&y[i].second,sizeof(double))) throw std::runtime_error("non-bit-exact flow");
            ++queries; entries+=(long long)x.size();
        }
    }
}

template<class S> double measure(S& solver, int repeats, int mode, double& checksum) {
    auto begin=std::chrono::steady_clock::now(); baseline::Sparse flow;
    for(int r=0;r<repeats;++r)
        for(int d=0;d<(int)solver.demands.size();++d)
            for(int t=0;t<solver.h;++t)
                for(int w=0;w<(mode==0?1:solver.n);++w) {
                    std::vector<int> path;
                    if(mode==1) path={w};
                    if(mode==2) path={w,(w+1)%solver.n};
                    if(solver.routeFlow(d,t,path,flow)) {
                        checksum+=flow.size();
                        if(!flow.empty())checksum+=flow.back().second;
                    }
                }
    return std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();
}

static void require_same(bool ax, bool bx, const baseline::Sparse& a,
                         const baseline::Sparse& b, const char* label) {
    if (ax != bx || a.size() != b.size()) throw std::runtime_error(label);
    for (std::size_t i = 0; i < a.size(); ++i)
        if (a[i].first != b[i].first ||
            std::memcmp(&a[i].second, &b[i].second, sizeof(double)))
            throw std::runtime_error(label);
}

static void reset_cache(baseline::Solver& a, inplace::Solver& b) {
    a.cache.clear(); b.cache.clear();
}

static int boundary_checks(baseline::Solver& a, inplace::Solver& b) {
    const int d = 0, t = 0, from = a.demands[d].from, to = a.demands[d].to;
    int mid = 0;
    while (mid == from || mid == to) ++mid;
    if (mid >= a.n) throw std::runtime_error("boundary fixture needs three nodes");
    const auto key = [&](int s, int z) {
        return (static_cast<std::uint64_t>(t) * a.n + s) * a.n + z;
    };
    baseline::Sparse x, y;
    int count = 0;
    // Use the real first leg, then make the SECOND cache miss clear all entries.
    // Neither implementation may retain references into the evicted first leg.
    auto first = a.segment(t, from, mid);
    for (auto* cache : {&a.cache, &b.cache}) {
        cache->clear(); cache->emplace(key(from, mid), first);
        for (std::uint64_t i = 0; cache->size() < 300000; ++i)
            cache->emplace((1ULL << 60) + i, baseline::Sparse{});
    }
    bool ax = a.routeFlow(d, t, {mid}, x), bx = b.routeFlow(d, t, {mid}, y);
    require_same(ax, bx, x, y, "cache eviction changed flow");
    if (a.cache.size() >= 300000 || b.cache.size() >= 300000)
        throw std::runtime_error("cache eviction did not activate");
    ++count;
    // Exercise the cutover exactly and overlapping entries with different ratios.
    // Each injected segment obeys the real cache's sorted/unique-edge invariant.
    for (int len : {0, 1, 15, 16, 17, 33, 70}) {
        baseline::Sparse left, right;
        for (int e = 0; e < len; ++e) {
            left.emplace_back(e, 1.0 / (e + 3));
            right.emplace_back(e, 1.0 / (e + 7));
        }
        reset_cache(a, b);
        for (auto* cache : {&a.cache, &b.cache}) {
            cache->emplace(key(from, mid), left);
            cache->emplace(key(mid, to), right);
        }
        x = {{999, 2.0}}; y = x;
        ax = a.routeFlow(d, t, {mid}, x); bx = b.routeFlow(d, t, {mid}, y);
        require_same(ax, bx, x, y, "cutover/overlap changed arithmetic");
        ++count;
    }
    // Unreachable first legs clear previous output; unreachable second legs
    // leave the successful first leg exactly as the original method does.
    for (int which = 0; which < 2; ++which) {
        reset_cache(a, b);
        for (auto* cache : {&a.cache, &b.cache}) {
            cache->emplace(key(from, mid), which == 0 ? baseline::Sparse{{-1, 0}}
                                                        : baseline::Sparse{{2, .125}, {4, .25}});
            cache->emplace(key(mid, to), which == 1 ? baseline::Sparse{{-1, 0}}
                                                      : baseline::Sparse{{3, .5}});
        }
        x = {{999, 2.0}}; y = x;
        ax = a.routeFlow(d, t, {mid}, x); bx = b.routeFlow(d, t, {mid}, y);
        require_same(ax, bx, x, y, "failed-leg partial output changed");
        if (ax || x.size() != (which == 0 ? 0U : 2U))
            throw std::runtime_error("failure discriminator did not activate");
        ++count;
    }
    // Direct unreachable and direct valid paths (including empty zero-hop segment).
    for (int kind = 0; kind < 3; ++kind) {
        reset_cache(a, b);
        baseline::Sparse direct = kind == 0 ? baseline::Sparse{{-1, 0}}
                                : kind == 1 ? baseline::Sparse{}
                                            : baseline::Sparse{{2, .125}, {4, .25}};
        a.cache.emplace(key(from, to), direct); b.cache.emplace(key(from, to), direct);
        x = {{999, 2.0}}; y = x;
        ax = a.routeFlow(d, t, {}, x); bx = b.routeFlow(d, t, {}, y);
        require_same(ax, bx, x, y, "direct-segment behavior changed");
        ++count;
    }
    reset_cache(a, b);
    return count;
}

int main(int argc,char** argv) {
    if(argc<5)return 2;
    try {
        setenv("SEDGE_SECONDS","100000",1); setenv("SEDGE_MAX_ROUNDS","0",1);
        baseline::Solver a(argv[1],argv[2],argv[3],std::string(argv[4])+"-baseline.json");
        inplace::Solver b(argv[1],argv[2],argv[3],std::string(argv[4])+"-inplace.json");
        int boundaries=boundary_checks(a,b); long long q=0,e=0; verify(a,b,q,e);
        std::cout<<std::setprecision(17)<<"{\"boundaries\":"<<boundaries<<",\"queries\":"<<q<<",\"entries\":"<<e;
        if(argc>5) {
            int repeats=std::stoi(argv[5]);
            std::cout<<",\"samples\":[";
            bool comma=false;
            for(int round=0;round<7;++round) for(int mode=0;mode<3;++mode) {
                double sa=0,sb=0,ta,tb;
                if(round%2){tb=measure(b,repeats,mode,sb);ta=measure(a,repeats,mode,sa);}
                else{ta=measure(a,repeats,mode,sa);tb=measure(b,repeats,mode,sb);}
                if(sa!=sb)throw std::runtime_error("benchmark checksum mismatch");
                if(comma)std::cout<<","; comma=true;
                std::cout<<"{\"round\":"<<round<<",\"mode\":"<<mode<<",\"baseline\":"<<ta<<",\"inplace\":"<<tb<<",\"checksum\":"<<sa<<"}";
            }
            std::cout<<"]";
        }
        std::cout<<"}\n";
    }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}
}
