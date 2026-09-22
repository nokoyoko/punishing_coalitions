// Independent structural/accounting checks matching lightweight-ledger-v1.
// This reads the emitted witness, not Engine counters or policy decisions.
// No RNG draw, fork-choice function, release plan or replay call is used.
#include "json_value.hpp"

static bool numeric_equal(const Json& v,double n){return (v.type==Json::Integer||v.type==Json::Float||v.type==Json::Bool)&&v.number()==n;}
static bool node_equal(const Json& v,int node){return node?v.type!=Json::Null&&numeric_equal(v,node):v.null();}
static int ledger_node(const Json& value,int maximum,bool nullable=false){if(value.null()){require(nullable,"null block ID");return 0;}long long n=value.whole();require(n>0&&n<=maximum,"unknown block ID");return int(n);}
static bool python_equal(const Json& left,const Json& right){
    auto numeric=[](const Json& v){return v.type==Json::Integer||v.type==Json::Float||v.type==Json::Bool;};
    if(numeric(left)&&numeric(right))return left.numeric_key()==right.numeric_key();
    if(left.type!=right.type)return false;
    if(left.type==Json::Array){if(left.size()!=right.size())return false;for(size_t i=0;i<left.size();++i)if(!python_equal(left.at(i),right.at(i)))return false;return true;}
    if(left.type==Json::Object){if(left.size()!=right.size())return false;for(const auto& [key,value]:left.object())if(!right.has(key)||!python_equal(value,right.at(key)))return false;return true;}
    return left.value()==right.value();
}
static void same_json(const Json& left,const Json& right,const S& message){require(left.dump()==right.dump(),message);}
static V ledger_ids(const Json& value){require(value.type==Json::Array,"ledger ID array required");V out;for(const auto& item:value.array()){long long n=item.whole();require(n>0&&n<=INT32_MAX,"ledger positive block ID");out.push_back(int(n));}return out;}
static std::set<int> id_set(const V& ids){return {ids.begin(),ids.end()};}
static std::set<S> object_keys(const Json& value){require(value.type==Json::Object,"ledger object required");std::set<S> out;for(const auto& [key,item]:value.object())out.insert(key);return out;}
static bool empty_array(const Json& value){return value.type==Json::Array&&value.array().empty();}

struct LightReference {O metadata;std::vector<S> names,roles;std::vector<double> powers;int horizon;};

static std::vector<S> check_lightweight(const Json& raw,const LightReference& ref){
    auto expected=[&](const S& field){return JsonReader(ref.metadata.at(field)).parse();};
    for(const S& field:{"identity","condition_id","network_version","model_version","population","strategy","label","active_coalition","punishment_rule","counter_fork_k"})
        same_json(raw.at(field),expected(field),"light metadata: "+field);
    require(raw.at("status").str()=="COMPLETE"&&raw.at("error").null()&&empty_array(raw.at("scripted_discoveries")),"light completion/native provenance");
    if(raw.has("recording_mode"))require(raw.at("recording_mode").str()=="production-v2"&&!raw.has("trace")&&!raw.has("public_events"),"light recording mode");
    require(raw.at("accepted_blocks").integer()&&raw.at("events").integer(),"light horizon integers");
    long long n64=raw.at("accepted_blocks").whole(),events64=raw.at("events").whole();
    require(events64>=n64&&n64>=ref.horizon&&events64<=INT32_MAX,"light horizon");int n=n64,events=events64;
    const Json& t=raw.at("terminal");const Json& cb=t.at("canonical_blocks");const Json& fb=t.at("frontier_blocks");
    require(cb.type==Json::Array&&fb.type==Json::Array&&cb.size()+fb.size()==size_t(events),"light ledger coverage");
    std::vector<const Json*> records(events+1,nullptr);V parents(events+1),heights(events+1),owners(events+1),publication(events+1),release(events+1);
    std::vector<bool> canonical(events+1),withheld(events+1),public_block(events+1),published(events+1);
    std::map<S,int> actors;for(size_t a=0;a<ref.names.size();++a)actors[ref.names[a]]=int(a);int actor_count=ref.names.size();
    V discovered(actor_count),accepted(actor_count),orphaned(actor_count),hidden_count(actor_count);
    for(const Json* list:{&cb,&fb})for(const auto& block:list->array()){
        const auto& bid=block.at("id");require(bid.integer(),"light block integer identity");long long b64=bid.whole();require(b64>=1&&b64<=events&&!records[b64],"light ledger coverage");records[b64]=&block;
    }
    std::set<int> public_ids,hidden_ids;
    for(int bid=1;bid<=events;++bid){require(records[bid],"light ledger coverage");const auto& b=*records[bid];
        require(numeric_equal(b.at("discovery_sequence"),bid)&&actors.count(b.at("owner_id").str()),"light block identity");owners[bid]=actors.at(b.at("owner_id").str());
        const auto& parent=b.at("parent_id");if(!parent.null()){require(parent.integer(),"light ancestry type");long long p=parent.whole();require(p>=1&&p<bid,"light ancestry");parents[bid]=p;}
        heights[bid]=heights[parents[bid]]+1;require(numeric_equal(b.at("height"),heights[bid]),"light height");
        require(b.at("canonical").boolean()&&b.at("initially_withheld").boolean(),"light block flags");canonical[bid]=b.at("canonical").truth();withheld[bid]=b.at("initially_withheld").truth();++discovered[owners[bid]];
        if(!b.at("publication_sequence").null()){public_block[bid]=true;public_ids.insert(bid);(canonical[bid]?accepted:orphaned)[owners[bid]]++;}
        else{require(!canonical[bid]&&b.at("release_batch").null()&&b.at("publication_kind").null(),"light hidden fields");hidden_ids.insert(bid);++hidden_count[owners[bid]];}
    }
    const auto& batches=raw.at("publication_batches");require(batches.type==Json::Array,"light publication batches");int index=0,last_event=0,sequence=0;
    for(const auto& batch:batches.array()){++index;const auto& event=batch.at("discovery_event");require(event.integer()&&numeric_equal(batch.at("batch"),index),"light publication batch");long long e=event.whole();require(e>=last_event&&e<=events,"light publication order");last_event=e;
        const auto& bs=batch.at("blocks");require(bs.type==Json::Array&&!bs.array().empty(),"light publication batch blocks");
        for(const auto& v:bs.array()){require(v.integer(),"light publication integer ID");long long b64=v.whole();require(b64>0&&b64<=events&&b64<=e&&!published[b64],"light publication coverage");int bid=b64;const auto& b=*records[bid];
            require(!parents[bid]||published[parents[bid]],"light publication ancestry");
            require(numeric_equal(b.at("publication_sequence"),++sequence)&&numeric_equal(b.at("release_batch"),index)&&python_equal(b.at("publication_kind"),batch.at("kind")),"light publication metadata");published[bid]=true;
        }
    }
    require(published==public_block,"light public coverage");V chain=ledger_ids(t.at("canonical_chain"));std::set<int> canonical_ids;
    for(int bid=1;bid<=events;++bid)if(canonical[bid])canonical_ids.insert(bid);
    require(chain.size()==size_t(n)&&id_set(chain).size()==chain.size()&&node_equal(t.at("reference_tip"),chain.back())&&numeric_equal(t.at("reference_height"),n),"light canonical endpoint");
    require(id_set(chain)==canonical_ids,"light canonical flags");
    for(size_t i=0;i<chain.size();++i){int bid=chain[i];require(bid<=events&&public_block[bid]&&parents[bid]==(i?chain[i-1]:0),"light canonical chain");}
    int maximum=0;for(int bid:public_ids)maximum=std::max(maximum,heights[bid]);require(n==maximum,"light public height");
    std::set<int> public_frontier=public_ids,private_frontier=hidden_ids;
    for(int bid:public_ids)public_frontier.erase(parents[bid]);for(int bid:hidden_ids)private_frontier.erase(parents[bid]);
    V pf=ledger_ids(t.at("public_frontier")),hf=ledger_ids(t.at("private_frontier"));
    require(pf==V(public_frontier.begin(),public_frontier.end())&&hf==V(private_frontier.begin(),private_frontier.end()),"light public/private frontier");
    std::set<S> selfish_actors;bool selfish=raw.at("strategy").str()=="selfish";
    if(selfish)selfish_actors.insert("target");if(raw.at("label").str()=="flagged"&&raw.at("punishment_rule").str()=="selfish")for(const auto& a:raw.at("active_coalition").array())selfish_actors.insert(a.str());
    const Json& states=t.at("private_states");require(object_keys(states)==selfish_actors,"light selfish actors");
    std::vector<S> ordered;for(const auto& a:ref.names)if(selfish_actors.count(a))ordered.push_back(a);
    const Json& order=raw.at("selfish_actor_order");require(order.type==Json::Array&&order.size()==ordered.size(),"light selfish actor order");for(size_t i=0;i<ordered.size();++i)require(order.at(i).str()==ordered[i],"light selfish actor order");
    std::set<int> private_ids,abandoned_ids;
    for(const auto& [actor,state]:states.object()){int owner=actors.at(actor);V owned=ledger_ids(state.at("private_chain")),lost=ledger_ids(state.at("abandoned_private_blocks")),released_ids=ledger_ids(state.at("released_blocks"));
        auto ownset=id_set(owned),lostset=id_set(lost),relset=id_set(released_ids);require(ownset.size()==owned.size()&&lostset.size()==lost.size()&&relset.size()==released_ids.size(),"light private duplicates");
        for(int b:owned){require(!lostset.count(b)&&!private_ids.count(b),"light private overlap");require(b<=events&&hidden_ids.count(b)&&owners[b]==owner&&withheld[b],"light private ownership");}
        for(int b:lost){require(!abandoned_ids.count(b),"light private overlap");require(b<=events&&hidden_ids.count(b)&&owners[b]==owner&&withheld[b],"light private ownership");}
        for(size_t i=0;i<owned.size();++i)require(i?parents[owned[i]]==owned[i-1]:!parents[owned[i]]||public_block[parents[owned[i]]],"light private chain");
        int tip=owned.empty()?0:owned.back(),h=heights[tip];
        require(state.at("actor_id").str()==actor&&numeric_equal(state.at("private_block_count"),owned.size())&&node_equal(state.at("private_tip"),tip)&&numeric_equal(state.at("private_tip_height"),h)&&numeric_equal(state.at("lead_relative_to_public_height"),tip?h-n:0),"light private state");
        require(node_equal(state.at("private_fork_base"),owned.empty()?0:parents[owned.front()]),"light private base");
        std::set<int> actual_released;for(int b:public_ids)if(owners[b]==owner&&withheld[b])actual_released.insert(b);require(actual_released==relset,"light released ownership");
        private_ids.insert(owned.begin(),owned.end());abandoned_ids.insert(lost.begin(),lost.end());
    }
    for(int b:private_ids)require(!abandoned_ids.count(b),"light private/abandoned overlap");std::set<int> all_hidden=private_ids;all_hidden.insert(abandoned_ids.begin(),abandoned_ids.end());require(all_hidden==hidden_ids,"light hidden coverage");
    if(states.has("target"))same_json(t.at("target_private_chain"),states.at("target").at("private_chain"),"light target private chain");else require(empty_array(t.at("target_private_chain")),"light target private chain");
    require(ledger_ids(t.at("abandoned_private"))==V(abandoned_ids.begin(),abandoned_ids.end())&&!t.at("reaction_queue").truth(),"light terminal private/queue");
    const Json& actor_records=raw.at("actors");require(object_keys(actor_records)==std::set<S>(ref.names.begin(),ref.names.end()),"light actor coverage");
    int accepted_total=0,discovered_total=0;
    for(int a=0;a<actor_count;++a){const auto& r=actor_records.at(ref.names[a]);require(r.at("role").str()==ref.roles[a]&&numeric_equal(r.at("hash_power"),ref.powers[a]),"light actor identity");
        for(const auto& [key,value]:std::vector<std::pair<S,int>>{{"discovered",discovered[a]},{"accepted",accepted[a]},{"orphaned",orphaned[a]},{"unresolved",hidden_count[a]}})require(r.at(key).integer()&&numeric_equal(r.at(key),value),"light ledger accounting");
        double payoff=double(accepted[a])/n;require(numeric_equal(r.at("public_noncanonical"),orphaned[a])&&numeric_equal(r.at("payoff"),payoff)&&numeric_equal(r.at("normalized_revenue"),payoff/ref.powers[a]),"light payoff");
        require(discovered[a]==accepted[a]+orphaned[a]+hidden_count[a],"light conservation");accepted_total+=accepted[a];discovered_total+=discovered[a];
    }
    require(accepted_total==n&&discovered_total==events,"light global accounting");
    // Every ancestry edge was checked above. A descriptor can denote only the
    // unique parent path. Its first canonical ancestor is independently derived
    // once per block; checking all leaves is O(events + leaves), without repeats.
    V first_canonical(events+1);for(int b=1;b<=events;++b)first_canonical[b]=canonical[b]?b:first_canonical[parents[b]];
    auto path_check=[&](const Json& path,int tip,int ancestor,bool public_only,bool require_nonempty){
        if(path.type==Json::Path){require(path.path().ascending&&path.path().tip==tip&&path.path().ancestor==ancestor,"light path descriptor");require(first_canonical[tip]==ancestor,"light branch ancestry");require(!require_nonempty||tip!=ancestor,"light branch nonempty");if(public_only)require(!tip||public_block[tip],"light eligible path visibility");return;}
        V ids=ledger_ids(path);require(!require_nonempty||!ids.empty(),"light branch path");require((ids.empty()?ancestor:ids.back())==tip,"light branch endpoint");for(size_t i=0;i<ids.size();++i){int b=ids[i];require(b<=events&&!canonical[b]&&parents[b]==(i?ids[i-1]:ancestor)&&(!public_only||public_block[b]),"light branch ancestry");}
    };
    std::vector<V> prefixes(n+1,V(actor_count));for(int i=0;i<n;++i){prefixes[i+1]=prefixes[i];++prefixes[i+1][owners[chain[i]]];}
    const Json& branches=t.at("alternative_branches");require(branches.type==Json::Array,"light branches");std::set<int> branch_tips;int maximum_exposure=0;
    for(const auto& branch:branches.array()){int tip=ledger_node(branch.at("tip"),events);require(tip>0&&tip<=events&&!branch_tips.count(tip),"light branch tip");branch_tips.insert(tip);
        const auto& av=branch.at("common_ancestor");int ancestor=ledger_node(av,events,true);require(!ancestor||canonical_ids.count(ancestor),"light branch ancestor");int h=heights[ancestor];
        path_check(branch.at("path"),tip,ancestor,false,true);
        require(numeric_equal(branch.at("common_ancestor_height"),h)&&numeric_equal(branch.at("height"),heights[tip]),"light branch height");
        require(branch.at("visibility").str()==(public_block[tip]?"public":"private"),"light branch visibility");require(numeric_equal(branch.at("canonical_blocks_exposed"),n-h),"light exposed depth");
        O rewards;for(int a=0;a<actor_count;++a)rewards[ref.names[a]]=num(accepted[a]-prefixes[h][a]);require(branch.at("canonical_rewards_exposed").dump()==obj(rewards),"light exposed rewards");maximum_exposure=std::max(maximum_exposure,n-h);
    }
    std::set<int> expected_tips=public_frontier;expected_tips.erase(chain.back());expected_tips.insert(private_frontier.begin(),private_frontier.end());require(branch_tips==expected_tips,"light branch coverage");
    bool ignore=raw.at("label").str()=="flagged"&&raw.at("punishment_rule").str()=="ignore";require(t.has("ostracism_eligible_frontier")==ignore,"light eligible frontier presence");
    if(ignore){const auto& frontier=t.at("ostracism_eligible_frontier");require(frontier.type==Json::Array,"light eligible frontier array");for(const auto& branch:frontier.array()){const auto& tv=branch.at("tip");int tip=ledger_node(tv,events,true);require(!tip||public_ids.count(tip),"light eligible frontier visibility");const auto& av=branch.at("common_ancestor");int ancestor=ledger_node(av,events,true);require(!ancestor||canonical_ids.count(ancestor),"light eligible ancestor");int h=heights[ancestor];require(numeric_equal(branch.at("common_ancestor_height"),h)&&numeric_equal(branch.at("height"),heights[tip])&&numeric_equal(branch.at("canonical_blocks_exposed"),n-h),"light eligible frontier exposure");path_check(branch.at("path"),tip,ancestor,true,false);maximum_exposure=std::max(maximum_exposure,n-h);}}
    const auto& boundary=t.at("boundary");require(numeric_equal(boundary.at("max_exposed_canonical_blocks"),maximum_exposure),"light boundary exposure");
    const auto& window=t.at("pending_publication_window");if(window.truth()){require(python_equal(t.at("pending_visibility_block"),window.at("origin_block")),"light pending window");int origin=ledger_node(window.at("origin_block"),events);require(numeric_equal(window.at("discovery_event"),events)&&public_ids.count(origin),"light window endpoint");for(int b:ledger_ids(window.at("delayed_tips")))require(public_ids.count(b),"light delayed tips");}else require(t.at("pending_visibility_block").null(),"light pending window");
    if(!branches.array().empty()||window.truth())require(boundary.at("potentially_material").boolean()&&boundary.at("potentially_material").truth(),"light unresolved boundary");
    const auto& rng=raw.at("rng");require(numeric_equal(rng.at("discoveries").at("draw_count"),events),"light discovery draws");for(const S& name:{"ties","natural"}){const auto& count=rng.at(name).at("draw_count");require(count.integer()&&count.whole()>=0&&count.whole()<=events,"light RNG draw bounds");}
    for(const S& name:{"member_activations","member_opportunities","natural_pairs"}){const auto& values=raw.at(name);require(values.type==Json::Object,"light counters");for(const auto& [key,value]:values.object())require(value.integer()&&(value.value().empty()||value.value()[0]!='-'),"light counter bounds");}
    const auto& reactions=raw.at("selfish_reactions");require(reactions.type==Json::Array,"light reaction diagnostics");std::map<S,int> rounds;size_t max_decisions=0;int max_rounds=0;
    for(const auto& frame:reactions.array()){max_decisions=std::max(max_decisions,frame.at("decisions").python_length());max_rounds=std::max(max_rounds,++rounds[frame.at("discovery_event").hashable_key()]);}
    std::vector<S> risks;if(max_decisions>1)risks.push_back("simultaneous_selfish_reactions");if(max_rounds>1)risks.push_back("cascading_selfish_reactions");return risks;
}
