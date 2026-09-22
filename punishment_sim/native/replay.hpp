// Independent ledger reconstruction corresponding to PublicReplay in Python.
// Never calls Engine::step, discover, publish, selfish_publication, or run.
// RNG primitives, policy helpers, ancestry and reward arithmetic remain shared
// model operations, as they are between Python PublicReplay and its simulator.

static bool replay_equal(const Json& actual,const Json& expected,const Engine& view) {
    if(expected.type==Json::Path) {
        const auto& path=expected.path();
        if(actual.type==Json::Path) {
            const auto& other=actual.path();
            return other.tip==path.tip&&other.ancestor==path.ancestor&&other.ascending==path.ascending;
        }
        if(actual.type!=Json::Array)return false;
        V nodes;
        for(int b=path.tip;b!=path.ancestor;b=view.blocks.at(b).parent) {
            if(b<=0)return false;
            nodes.push_back(b);
        }
        if(path.ascending)std::reverse(nodes.begin(),nodes.end());
        if(actual.size()!=nodes.size())return false;
        for(size_t i=0;i<nodes.size();++i)
            if(!actual.at(i).integer()||!numeric_equal(actual.at(i),nodes[i]))return false;
        return true;
    }
    if(actual.type!=expected.type)return false;
    if(expected.type==Json::Array) {
        if(actual.size()!=expected.size())return false;
        for(size_t i=0;i<actual.size();++i)if(!replay_equal(actual.at(i),expected.at(i),view))return false;
        return true;
    }
    if(expected.type==Json::Object) {
        if(actual.size()!=expected.size())return false;
        for(const auto& [key,value]:expected.object())
            if(!actual.has(key)||!replay_equal(actual.at(key),value,view))return false;
        return true;
    }
    return actual.value()==expected.value();
}

class LedgerReplay {
    Engine view;
    const Json& raw;
    std::vector<const Json*> records;
    std::vector<std::vector<Batch>> by_event;

    int draw_actor() {
        double draw=view.discovery_rng.random(), cumulative=0;
        for(size_t actor=0;actor<view.powers.size();++actor) {
            cumulative+=view.powers[actor];
            if(draw<cumulative)return int(actor);
        }
        return int(view.powers.size())-1;
    }

    void apply_batch(const Batch& batch) {
        const V& ids=batch.blocks;
        int maximum=view.height;
        for(int b:ids)maximum=std::max(maximum,view.h(b));
        V longest;
        for(int b:ids)if(view.h(b)==maximum)longest.push_back(b);
        if(maximum==view.height)longest.insert(longest.end(),view.longest.begin(),view.longest.end());
        longest=sorted(longest);
        longest.erase(std::unique(longest.begin(),longest.end()),longest.end());
        view.target_tip(longest);
        view.height=maximum;view.longest=std::move(longest);
        for(int b:ids)view.public_tips.insert(b);
        ++view.batch_number;
        for(int b:ids) {
            auto& block=view.blocks.at(b);
            view.public_tips.erase(block.parent);
            block.publication=++view.publication;block.batch=view.batch_number;block.kind=batch.kind;
        }
        int chosen=has(view.longest,view.reference)?view.reference:
            *std::min_element(view.longest.begin(),view.longest.end(),[&](int a,int b) {
                return std::make_pair(view.blocks[a].publication,a)<std::make_pair(view.blocks[b].publication,b);
            });
        view.adopt(chosen);
        view.batches.push_back(batch);
        view.petty_publication();
        if(view.rule=="counter_fork")view.counter_publication(ids);
        if(view.rule=="ignore")view.ignore_publication(ids);
        for(int b:ids) {
            Engine::index_add(view.levels,b,view.h(b));
            if(!view.rejected_by[b])Engine::index_add(view.acceptable_levels,b,view.h(b));
        }
        for(size_t actor=0;actor<view.names.size();++actor) {
            auto& state=view.private_states[actor];
            if(!state.enabled)continue;
            state.chain.erase(std::remove_if(state.chain.begin(),state.chain.end(),
                [&](int b){return has(ids,b);}),state.chain.end());
            for(int b:ids)if(view.blocks[b].owner==int(actor)) {
                state.exposed=b;
                if(view.blocks[b].withheld)state.released.push_back(b);
            }
        }
    }

    void apply_episode(const std::vector<Batch>& batches) {
        if(batches.empty())return;
        apply_batch(batches[0]);
        V observed=batches[0].blocks;
        size_t cursor=1;
        while(!observed.empty()) {
            std::vector<Decision> decisions;
            for(size_t actor=0;actor<view.names.size();++actor) {
                const auto& state=view.private_states[actor];
                if(!state.enabled||state.chain.empty())continue;
                int tip=state.chain.back(),rival_height=-1;
                V rivals;
                for(int b:view.longest)if(!view.descends(tip,b)) {
                    rivals.push_back(b);rival_height=std::max(rival_height,view.h(b));
                }
                if(rivals.empty()||std::none_of(observed.begin(),observed.end(),
                    [&](int b){return has(rivals,b);}))continue;
                int gap=view.h(tip)-rival_height;
                V blocks;
                if(gap<=1)blocks=state.chain;
                else for(int b:state.chain)if(view.h(b)<=rival_height)blocks.push_back(b);
                if(!blocks.empty())decisions.push_back({int(actor),tip,gap<0,std::move(blocks)});
            }
            if(decisions.empty())break;
            view.reactions.push_back({view.events,view.height,view.publication,observed,decisions});
            observed.clear();
            for(const auto& decision:decisions) {
                auto& state=view.private_states[decision.actor];
                if(decision.abandon) {
                    state.abandoned.insert(state.abandoned.end(),state.chain.begin(),state.chain.end());
                    state.chain.clear();
                } else {
                    require(cursor<batches.size(),"replay missing mandatory selfish release");
                    const auto& batch=batches[cursor++];
                    require(batch.blocks==decision.blocks,"replay unexpected release batch");
                    require(batch.kind==(decision.actor==0?"target_selfish_release":"member_selfish_release"),
                        "replay release mislabeled");
                    apply_batch(batch);
                    observed.insert(observed.end(),decision.blocks.begin(),decision.blocks.end());
                }
            }
        }
        require(cursor==batches.size(),"replay publication without a strategy reaction");
    }

    void discovery(int event) {
        require(view.height<view.horizon,"replay discoveries beyond observation horizon");
        view.events=event;
        const auto& recorded=*records[event];
        int actor=draw_actor();
        require(recorded.at("owner_id").str()==view.names[actor],"replay discovery RNG/owner mismatch");
        Window incoming=view.window;
        view.window=Window{};
        int start_height=view.height;
        V start_tips=view.longest;
        if(view.policy_active()||view.rule=="selfish")for(int member:view.active) {
            ++view.opportunities[member];view.opportunity_seen[member]=true;
        }
        auto& state=view.private_states[actor];
        int parent=0,source=0;bool withheld=false;S kind;
        if(state.enabled&&!state.chain.empty()) {
            parent=state.chain.back();withheld=true;
        } else {
            V hidden=state.enabled?V{}:view.visible_hidden(actor,incoming);
            parent=view.choose(actor,view.eligible(actor,hidden));
            if(state.enabled) {
                withheld=start_tips.size()<=1;
                kind=actor==0?"target_tie_resolution":"member_tie_resolution";
            } else {
                V full=view.eligible(actor,{});
                if(incoming.active()&&view.h(parent)<view.h(full[0]))for(int b:full)
                    if(b&&has(hidden,b)&&(!source||view.blocks[b].publication<view.blocks[source].publication))source=b;
                bool punished=has(view.active,actor)&&(view.rule=="petty"?
                    view.target_tip(view.best(hidden))!=0:view.policy_active());
                kind=punished?view.rule:source?"natural_fork":"ordinary";
            }
        }
        require(node_equal(recorded.at("parent_id"),parent)&&recorded.at("initially_withheld").truth()==withheld,
            "replay fork choice/private discovery mismatch");
        Block block;block.parent=parent;block.height=view.h(parent)+1;block.owner=actor;block.withheld=withheld;
        view.blocks.push_back(block);view.children.emplace_back();view.children[parent].push_back(event);
        view.defending_depth.push_back(-1);view.rejected_by.push_back(0);
        std::array<int,23> jumps{};jumps[0]=parent;
        for(int level=1;level<23;++level)jumps[level]=view.jumps[jumps[level-1]][level-1];
        view.jumps.push_back(jumps);++view.discoveries[actor];
        const auto& batches=by_event[event];
        if(withheld) {
            state.chain.push_back(event);
            require(batches.empty(),"replay private discovery unexpectedly published");
        } else {
            require(!batches.empty()&&batches[0].blocks==V{event}&&batches[0].kind==kind,
                "replay ordinary publication mismatch");
            if(kind=="natural_fork") {
                S left=view.names[actor],right=view.names[view.blocks[source].owner];
                if(right<left)std::swap(left,right);
                ++view.natural_pairs[left+"--"+right];
            }
        }
        apply_episode(batches);
        V publications;
        for(const auto& batch:batches)publications.insert(publications.end(),batch.blocks.begin(),batch.blocks.end());
        bool eligible=!incoming.active()&&start_tips.size()<=1&&view.pub(event)&&view.h(event)>start_height;
        if(eligible&&view.natural_rng.random()<view.lambda) {
            view.window.event=event;view.window.origin=event;view.window.blocks=publications;
            for(int b:publications)if(view.public_tips.count(b))view.window.delayed.push_back(b);
        }
    }

public:
    LedgerReplay(const Json& raw,PyObject* input):view(input),raw(raw) {
        require(raw.at("recording_mode").str()=="production-v2","native replay requires production witness");
        int events=int(raw.at("events").whole());
        records.resize(events+1);by_event.resize(events+1);
        for(const S& field:{"canonical_blocks","frontier_blocks"})
            for(const auto& block:raw.at("terminal").at(field).array())records.at(block.at("id").whole())=&block;
        for(const auto& batch:raw.at("publication_batches").array()) {
            int event=int(batch.at("discovery_event").whole());
            require(event>0&&event<=events,"replay publication event");
            by_event[event].push_back({int(batch.at("batch").whole()),event,ledger_ids(batch.at("blocks")),batch.at("kind").str()});
        }
    }

    void validate() {
        for(size_t event=1;event<records.size();++event)discovery(int(event));
        require(numeric_equal(raw.at("accepted_blocks"),view.height)&&view.height>=view.horizon,"replay horizon mismatch");
        PathEmission emission;emission.parent=[&](int b){return view.blocks.at(b).parent;};PathScope scope(emission);
        auto output=view.report("COMPLETE","",false);
        Json expected=JsonReader(output.first,true).parse();
        for(const S& field:{"terminal","rng","episodes","selfish_reactions","reorganizations",
            "member_activations","member_opportunities","natural_pairs","actors"})
            require(replay_equal(raw.at(field),expected.at(field),view),"native replay endpoint mismatch: "+field);
    }
};
