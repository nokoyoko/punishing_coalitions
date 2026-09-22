// Experimental H/S0/petty condition kernel. Never used by production dispatch.
// CPython C API is used only for condition I/O, constant-sized float formatting,
// and bulk SHA-256. There are no Python calls in the production discovery loop.
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using S=std::string;
using V=std::vector<int>;
using O=std::map<S,S>;
static void require(bool ok,const S& s) { if(!ok) throw std::runtime_error(s); }
struct Ref { PyObject* p; explicit Ref(PyObject* p):p(p){if(!p) throw std::runtime_error("CPython operation failed");} ~Ref(){Py_DECREF(p);} Ref(const Ref&)=delete; };
static S text(PyObject* v){require(PyUnicode_Check(v),"string required");Py_ssize_t size=0;const char* p=PyUnicode_AsUTF8AndSize(v,&size);require(p,"invalid UTF8");return S(p,size);}
static PyObject* field(PyObject* d,const char* key){PyObject* v=PyDict_GetItemString(d,key);require(v,S("missing input: ")+key);return v;}
static int integer(PyObject* v){require(PyLong_Check(v)&&!PyBool_Check(v),"integer required");long x=PyLong_AsLong(v);require(!PyErr_Occurred()&&x>=-1&&x<=3000000,"integer outside prototype range");return int(x);}
static V ints(PyObject* p){Ref seq(PySequence_Fast(p,"sequence required"));V r;for(Py_ssize_t i=0;i<PySequence_Fast_GET_SIZE(seq.p);++i)r.push_back(integer(PySequence_Fast_GET_ITEM(seq.p,i)));return r;}
static S num(long long x){return std::to_string(x);}
static S id(int x){return x?num(x):"null";}
static S boolean(bool x){return x?"true":"false";}
static S quote(const S& s){S r="\"";for(unsigned char c:s){require(c<128,"prototype accepts ASCII identifiers only");if(c=='"'||c=='\\'){r+='\\';r+=char(c);}else if(c=='\b')r+="\\b";else if(c=='\f')r+="\\f";else if(c=='\n')r+="\\n";else if(c=='\r')r+="\\r";else if(c=='\t')r+="\\t";else if(c<32||c==127){const char* h="0123456789abcdef";r+="\\u00";r+=h[c>>4];r+=h[c&15];}else r+=char(c);}return r+'"';}
static S obj(const O& fields){S r="{";bool first=true;for(auto& [k,v]:fields){if(!first)r+=',';first=false;r+=quote(k);r+=':';r+=v;}return r+'}';}
static S array(const std::vector<S>& xs){size_t size=2+xs.size();for(const S& s:xs)size+=s.size();S r;r.reserve(size);r+='[';for(size_t i=0;i<xs.size();++i){if(i)r+=',';r+=xs[i];}return r+']';}
static S ids(const V& xs,bool nullable=false){S r="[";for(size_t i=0;i<xs.size();++i){if(i)r+=',';r+=nullable?id(xs[i]):num(xs[i]);}return r+']';}
static V sorted(V xs){std::sort(xs.begin(),xs.end());return xs;}
static bool has(const V& xs,int b){return std::find(xs.begin(),xs.end(),b)!=xs.end();}
static S fp(double x){require(std::isfinite(x),"nonfinite native output");Ref value(PyFloat_FromDouble(x));Ref repr(PyObject_Repr(value.p));return text(repr.p);}
static S sha(const S& bytes){
    Ref module(PyImport_ImportModule("hashlib"));Ref fn(PyObject_GetAttrString(module.p,"sha256"));
    Ref view(PyMemoryView_FromMemory(const_cast<char*>(bytes.data()),Py_ssize_t(bytes.size()),PyBUF_READ));
    Ref hash(PyObject_CallOneArg(fn.p,view.p));Ref hex(PyObject_CallMethod(hash.p,"hexdigest",nullptr));return text(hex.p);
}
static S summary(const S& serialized,size_t count){return obj({{"count",num(count)},{"sha256",quote(sha(serialized))}});}
static S range(const V& xs){long long total=0;for(int v:xs)total+=v;return obj({{"count",num(xs.size())},{"min",xs.empty()?"null":num(*std::min_element(xs.begin(),xs.end()))},{"max",xs.empty()?"null":num(*std::max_element(xs.begin(),xs.end()))},{"sum",num(total)}});}

struct RNG {
    std::array<uint32_t,624> mt{};int position=624;long long count=0;double last=0;
    explicit RNG(PyObject* state){Ref seq(PySequence_Fast(state,"MT state required"));require(PySequence_Fast_GET_SIZE(seq.p)==625,"625 MT words/index required");for(int i=0;i<624;++i){PyObject* v=PySequence_Fast_GET_ITEM(seq.p,i);unsigned long x=PyLong_AsUnsignedLong(v);require(!PyErr_Occurred()&&x<=UINT32_MAX,"invalid MT word");mt[i]=uint32_t(x);}position=int(PyLong_AsLong(PySequence_Fast_GET_ITEM(seq.p,624)));require(position>=0&&position<=624,"invalid MT index");}
    uint32_t word(){if(position==624){for(int i=0;i<624;++i){uint32_t y=(mt[i]&0x80000000u)|(mt[(i+1)%624]&0x7fffffffu);mt[i]=mt[(i+397)%624]^(y>>1)^((y&1)?0x9908b0dfu:0u);}position=0;}uint32_t y=mt[position++];y^=y>>11;y^=(y<<7)&0x9d2c5680u;y^=(y<<15)&0xefc60000u;y^=y>>18;return y;}
    double random(){uint32_t a=word()>>5,b=word()>>6;last=(a*67108864.0+b)*(1.0/9007199254740992.0);++count;return last;}
    S snapshot()const{S state="(3, (";for(int i=0;i<624;++i)state+=num(mt[i])+", ";state+=num(position)+"), None)";return obj({{"draw_count",num(count)},{"last_draw",count?fp(last):"null"},{"state_sha256",quote(sha(state))}});}
    PyObject* state()const{PyObject* out=PyTuple_New(625);if(!out)return nullptr;for(int i=0;i<624;++i)PyTuple_SET_ITEM(out,i,PyLong_FromUnsignedLong(mt[i]));PyTuple_SET_ITEM(out,624,PyLong_FromLong(position));return out;}
};
struct Unsupported:std::runtime_error{using std::runtime_error::runtime_error;};
struct Block {int parent=0,height=0,owner=-1,publication=0,batch=0;bool withheld=false,canonical=false;S kind;};
struct Batch {
    int batch,event;V blocks;S kind;
    // Fixed schema, in canonical key order: no per-record map allocation.
    S json()const {
        return "{\"batch\":"+num(batch)+",\"blocks\":"+ids(blocks)+
            ",\"discovery_event\":"+num(event)+",\"kind\":"+quote(kind)+'}';
    }
};
struct Reorg {int event,ancestor;V removed,added;S json()const{return obj({{"event",num(event)},{"common_ancestor",id(ancestor)},{"removed",ids(removed)},{"added",ids(added)}});}};
struct Episode {bool opened;int target,event,publication;V tips;S json()const{return obj({{"outcome",quote(opened?"PETTY_RACE_OPENED":"PETTY_RACE_CLOSED")},{"target_tip",id(target)},{"tips",ids(tips)},{"discovery_event",num(event)},{"publication_sequence",num(publication)}});}};
struct Reaction {int event,height,publication,tip;bool abandon;V observed,blocks;S json(int round)const{return obj({{"outcome",quote("SELFISH_REACTION_ROUND")},{"round",num(round)},{"discovery_event",num(event)},{"observed_publications",ids(observed)},{"public_height",num(height)},{"publication_sequence",num(publication)},{"decisions",array({obj({{"actor_id",quote("target")},{"action",quote(abandon?"ABANDON":"RELEASE")},{"blocks",ids(blocks)},{"private_tip_before",id(tip)}})})}});}};
struct Window {int event=0,origin=0;V blocks,delayed;bool active()const{return origin!=0;}S json()const{return active()?obj({{"discovery_event",num(event)},{"origin_block",id(origin)},{"blocks",ids(blocks)},{"delayed_tips",ids(delayed)}}):"null";}};
struct Branch {int tip,ancestor;bool hidden;V path,exposed;};
struct Action {int type,actor=-1,parent=0;bool withheld=false;V blocks;S kind="ordinary";};
struct Output {S raw,compact;double simulation_seconds,emission_seconds;};

class Engine {
public:
    std::vector<S> names,roles,hp_json;std::vector<double> powers;
    double gamma,lambda;int horizon,max_events,stop_after;bool selfish,enabled,production,trace;
    V active,rewards,discoveries,activations,opportunities;std::vector<bool> activation_seen,opportunity_seen;
    std::vector<Block> blocks{Block{}};std::set<int> public_tips;V longest,canonical;
    std::vector<V> levels{{0}};int height=0,events=0,publication=0,batch_number=0,reference=0;
    V chain,released,abandoned,pending;int exposed=0;bool processing=false;
    int race_target=0;V race_tips;std::vector<Episode> episodes;
    std::vector<Batch> batches;std::vector<Reorg> reorgs;std::vector<Reaction> reactions;
    std::map<S,int> natural_pairs;Window window;std::vector<S> public_events,traces;V scripted;
    RNG discovery_rng,tie_rng,natural_rng;O metadata;std::vector<Action> actions;bool has_actions=false;
    explicit Engine(PyObject* input):
        gamma(PyFloat_AsDouble(field(input,"gamma"))),lambda(PyFloat_AsDouble(field(input,"lambda"))),
        horizon(integer(field(input,"horizon"))),max_events(integer(field(input,"max_events"))),
        stop_after(integer(field(input,"stop_after"))),selfish(PyObject_IsTrue(field(input,"selfish"))),
        enabled(PyObject_IsTrue(field(input,"enabled"))),production(PyObject_IsTrue(field(input,"production"))),
        trace(PyObject_IsTrue(field(input,"trace"))),
        discovery_rng(PyTuple_GetItem(field(input,"rng_states"),0)),tie_rng(PyTuple_GetItem(field(input,"rng_states"),1)),natural_rng(PyTuple_GetItem(field(input,"rng_states"),2)) {
        require(horizon>0&&horizon<=30000&&max_events>0,"prototype horizon/resource bound");
        require(gamma>=0&&gamma<=1&&lambda>=0&&lambda<=1,"probability out of range");
        require(!(production&&trace),"trace and production conflict");
        PyObject* miners=field(input,"miners");Ref seq(PySequence_Fast(miners,"miners required"));
        for(Py_ssize_t i=0;i<PySequence_Fast_GET_SIZE(seq.p);++i){PyObject* m=PySequence_Fast_GET_ITEM(seq.p,i);names.push_back(text(PyTuple_GetItem(m,0)));roles.push_back(text(PyTuple_GetItem(m,1)));powers.push_back(PyFloat_AsDouble(PyTuple_GetItem(m,2)));hp_json.push_back(text(PyTuple_GetItem(m,3)));quote(names.back());}
        require(names.size()>=3&&names.size()<=8&&names.front()=="target"&&names.back()=="honest_residual","prototype miner coverage");
        active=ints(field(input,"active"));for(int a:active)require(a>0&&a<int(names.size())-1,"invalid active member");
        int n=names.size();rewards.resize(n);discoveries.resize(n);activations.resize(n);opportunities.resize(n);activation_seen.resize(n);opportunity_seen.resize(n);reward_seen_storage.resize(n);
        PyObject* header=field(input,"metadata");PyObject *k,*v;Py_ssize_t pos=0;while(PyDict_Next(header,&pos,&k,&v))metadata[text(k)]=text(v);
        require(metadata["punishment_rule"]==(enabled?"\"petty\"":"null"),"unsupported prototype rule metadata");
        PyObject* script=field(input,"actions");has_actions=script!=Py_None;
        if(has_actions){Ref acts(PySequence_Fast(script,"actions required"));require(PySequence_Fast_GET_SIZE(acts.p)<=512,"debug action bound");for(Py_ssize_t i=0;i<PySequence_Fast_GET_SIZE(acts.p);++i){PyObject* a=PySequence_Fast_GET_ITEM(acts.p,i);Action cmd;cmd.type=integer(PyTuple_GetItem(a,0));if(cmd.type==2){cmd.blocks=ints(PyTuple_GetItem(a,1));cmd.kind=text(PyTuple_GetItem(a,2));}else {cmd.actor=integer(PyTuple_GetItem(a,1));if(cmd.type==1){cmd.parent=integer(PyTuple_GetItem(a,2));cmd.withheld=PyObject_IsTrue(PyTuple_GetItem(a,3));cmd.kind=text(PyTuple_GetItem(a,4));}}actions.push_back(cmd);}}
    }
    int h(int b)const{return blocks[b].height;}
    bool pub(int b)const{return b&&blocks[b].publication!=0;}
    bool descends(int tip,int ancestor)const{while(h(tip)>h(ancestor))tip=blocks[tip].parent;return tip==ancestor;}
    int target_tip(const V& tips)const{int target=0,count=0;for(int b:tips)if(b&&blocks[b].owner==0){target=b;++count;}if(count>1)throw Unsupported("multiple simultaneous target-owned competing tips");return tips.size()>1?target:0;}
    V visible_hidden(int actor,const Window& incoming)const{V hidden=incoming.delayed;if(actor!=int(names.size())-1){for(int b:incoming.delayed)if(blocks[b].owner==actor){while(has(hidden,b)){hidden.erase(std::find(hidden.begin(),hidden.end(),b));b=blocks[b].parent;}}}return hidden;}
    V best(const V& hidden)const{for(int depth=int(levels.size())-1;depth>=0;--depth){V result;for(int b:levels[depth])if(!b||!has(hidden,b))result.push_back(b);if(!result.empty())return sorted(result);}throw Unsupported("policy has no visible eligible parent");}
    V eligible(int actor,const V& hidden)const{V tips=best(hidden);if(enabled&&has(active,actor)){int t=target_tip(tips);if(t)tips.erase(std::find(tips.begin(),tips.end(),t));}return tips;}
    int choose(int actor,const V& tips){target_tip(tips);int own=0;for(int b:tips)if(b&&blocks[b].owner==actor&&(!own||blocks[b].publication>blocks[own].publication))own=b;if(actor!=int(names.size())-1&&own)return own;if(tips.size()==1)return tips[0];int target=target_tip(tips);double draw=tie_rng.random(),total=0;for(int b:tips){double probability=target?(b==target?gamma:(1-gamma)/(tips.size()-1)):1.0/tips.size();total+=probability;if(draw<total)return b;}return tips.back();}
    void adopt(int tip){int old=reference,next=tip;V removed,added;while(old!=next){if(h(old)>=h(next)){removed.push_back(old);old=blocks[old].parent;}else{added.push_back(next);next=blocks[next].parent;}}
        for(int b:removed){blocks[b].canonical=false;--rewards[blocks[b].owner];reward_seen_storage[blocks[b].owner]=true;}if(!removed.empty())canonical.resize(canonical.size()-removed.size());std::reverse(added.begin(),added.end());for(int b:added){blocks[b].canonical=true;++rewards[blocks[b].owner];reward_seen_storage[blocks[b].owner]=true;canonical.push_back(b);}if(!removed.empty())reorgs.push_back({events,old,removed,added});reference=tip;}
    void petty_publication(){if(!enabled)return;int target=target_tip(longest);V tips=target?longest:V{};if(target==race_target&&tips==race_tips)return;if(race_target)episodes.push_back({false,race_target,events,publication,race_tips});race_target=target;race_tips=tips;if(target){episodes.push_back({true,target,events,publication,tips});for(int a:active){++activations[a];activation_seen[a]=true;}}}
    void selfish_publication(const V& published){if(!selfish)return;chain.erase(std::remove_if(chain.begin(),chain.end(),[&](int b){return has(published,b);}),chain.end());for(int b:published)if(blocks[b].owner==0){exposed=b;if(blocks[b].withheld)released.push_back(b);}pending.insert(pending.end(),published.begin(),published.end());if(processing)return;processing=true;
        try{while(!pending.empty()){V observed;observed.swap(pending);if(chain.empty())continue;int tip=chain.back();V rivals;for(int b:longest)if(!descends(tip,b))rivals.push_back(b);if(rivals.empty()||std::none_of(observed.begin(),observed.end(),[&](int b){return has(rivals,b);}))continue;int rival_height=h(rivals[0]);int gap=h(tip)-rival_height;bool abandon=gap<0;V plan;if(abandon||gap<=1)plan=chain;else for(int b:chain)if(h(b)<=rival_height)plan.push_back(b);if(plan.empty())continue;
            reactions.push_back({events,height,publication,tip,abandon,observed,plan});size_t before=chain.size();if(abandon){abandoned.insert(abandoned.end(),chain.begin(),chain.end());chain.clear();}else publish(plan,"target_selfish_release");require(chain.size()<before,"reaction round made no private-state progress");}
        }catch(...){processing=false;throw;}processing=false;}
    void publish(const V& ids_to_publish,const S& kind){std::set<int> seen;V added;for(int b:ids_to_publish){require(b>0&&b<int(blocks.size()),"unknown publication");require(seen.insert(b).second,"duplicate ID inside publication batch");if(pub(b))continue;int parent=blocks[b].parent;require(!parent||pub(parent)||has(added,parent),"publication must expose parents before children");added.push_back(b);}if(added.empty())return;
        int maximum=height;for(int b:added)maximum=std::max(maximum,h(b));V high;for(int b:added)if(h(b)==maximum)high.push_back(b);if(maximum==height)high.insert(high.end(),longest.begin(),longest.end());high=sorted(high);high.erase(std::unique(high.begin(),high.end()),high.end());target_tip(high);
        height=maximum;longest=high;++batch_number;for(int b:added){public_tips.insert(b);}for(int b:added){public_tips.erase(blocks[b].parent);Block& block=blocks[b];block.publication=++publication;block.batch=batch_number;block.kind=kind;}
        int chosen=has(longest,reference)?reference:*std::min_element(longest.begin(),longest.end(),[&](int a,int b){return std::make_pair(blocks[a].publication,a)<std::make_pair(blocks[b].publication,b);});adopt(chosen);batches.push_back({batch_number,events,added,kind});petty_publication();for(int b:added){if(int(levels.size())<=h(b))levels.resize(h(b)+1);levels[h(b)].push_back(b);}selfish_publication(added);}
    int discover(int actor,int parent,bool withheld,const S& kind){require(actor>=0&&actor<int(names.size()),"unknown owner or parent");require(parent>=0&&parent<int(blocks.size()),"unknown owner or parent");require(!parent||pub(parent)||blocks[parent].owner==actor,"cannot mine on another actor's hidden block");if(withheld){require(selfish&&actor==0,"honest actor has no private state");require(chain.empty()||parent==chain.back(),"private actor must extend its own private tip");require(!chain.empty()||!parent||pub(parent),"private chain must start on public history");}
        ++events;int b=blocks.size();Block block;block.parent=parent;block.height=h(parent)+1;block.owner=actor;block.withheld=withheld;blocks.push_back(block);++discoveries[actor];if(!withheld)publish({b},kind);if(withheld)chain.push_back(b);return b;}
    O state()const{int tip=chain.empty()?0:chain.back();V rivals;for(int b:longest)if(tip&&!descends(tip,b))rivals.push_back(b);bool leading=has(longest,exposed);S phase=!chain.empty()?(longest.size()>1?"PRIVATE_WITH_PUBLIC_TIE":"PRIVATE"):(leading&&longest.size()>1?"EXPOSED_RACE":"PUBLIC");return {{"actor_id",quote("target")},{"private_chain",ids(chain)},{"private_fork_base",chain.empty()?"null":id(blocks[chain.front()].parent)},{"private_tip",id(tip)},{"private_tip_height",num(h(tip))},{"private_block_count",num(chain.size())},{"lead_relative_to_public_height",num(tip?h(tip)-height:0)},{"competing_public_tips",ids(rivals)},{"exposed_tip",id(exposed)},{"exposure_is_leading",boolean(leading)},{"released_blocks",ids(released)},{"abandoned_private_blocks",ids(abandoned)},{"phase",quote(phase)}};}
    S active_names()const{std::vector<S> values;for(int a:active)values.push_back(names[a]);std::sort(values.begin(),values.end());for(S& a:values)a=quote(a);return array(values);}
    S race()const{return race_target?obj({{"target_tip",id(race_target)},{"tips",ids(race_tips)}}):"null";}
    S punishment()const{return enabled?obj({{"punishment_rule",quote("petty")},{"active_members",active_names()},{"race",race()}}):"null";}
    S states()const{return selfish?obj({{"target",obj(state())}}):"{}";}
    S rngs()const{return obj({{"discoveries",discovery_rng.snapshot()},{"ties",tie_rng.snapshot()},{"natural",natural_rng.snapshot()}});}
    S counts(const V& values,const std::vector<bool>* seen=nullptr)const{O out;for(size_t a=0;a<names.size();++a)if(seen?(*seen)[a]:values[a]!=0)out[names[a]]=num(values[a]);return obj(out);}
    void step(int actor=-1){if(actor<0){double d=discovery_rng.random(),total=0;actor=names.size()-1;for(size_t a=0;a<powers.size();++a){total+=powers[a];if(d<total){actor=a;break;}}}else {require(actor<int(names.size()),"unknown discoverer");scripted.push_back(events+1);}
        Window incoming=window;window=Window{};int start_height=height;V start_tips=longest;size_t start_batch=batches.size();if(race_target)for(int a:active){++opportunities[a];opportunity_seen[a]=true;}int source=0,b=0,parent=0;V tips;long long tie_before=tie_rng.count;S choice="null";
        if(selfish&&actor==0&&!chain.empty()){b=discover(actor,chain.back(),true,"ordinary");}
        else {V hidden=(selfish&&actor==0)?V{}:visible_hidden(actor,incoming);tips=eligible(actor,hidden);parent=choose(actor,tips);if(!production||trace)choice=obj({{"tips",ids(tips,true)},{"parent",id(parent)},{"draw",tie_rng.count>tie_before?fp(tie_rng.last):"null"}});
            if(selfish&&actor==0)b=discover(actor,parent,start_tips.size()<=1,"target_tie_resolution");
            else {V full=eligible(actor,{});if(incoming.active()&&h(parent)<h(full[0]))for(int candidate:full)if(candidate&&has(hidden,candidate)&&(!source||blocks[candidate].publication<blocks[source].publication))source=candidate;
                bool punishing=enabled&&has(active,actor)&&target_tip(best(hidden));S kind=punishing?"petty":source?"natural_fork":"ordinary";b=discover(actor,parent,false,kind);if(kind=="natural_fork"){S a=names[actor],other=names[blocks[source].owner];if(other<a)std::swap(a,other);++natural_pairs[a+"--"+other];}}
        }
        V published;for(size_t i=start_batch;i<batches.size();++i)published.insert(published.end(),batches[i].blocks.begin(),batches[i].blocks.end());bool eligible_lambda=!incoming.active()&&start_tips.size()<=1&&pub(b)&&h(b)>start_height;double draw=eligible_lambda?natural_rng.random():0;
        if(eligible_lambda&&draw<lambda){window.event=events;window.origin=b;window.blocks=published;for(int bid:published)if(public_tips.count(bid))window.delayed.push_back(bid);}
        if(!production||trace){O ev={{"event",num(events)},{"discoverer",quote(names[actor])},{"block",id(b)},{"public_height_before",num(start_height)},{"leading_tips_before",ids(start_tips)},{"incoming_window",incoming.json()},{"choice",choice},{"delayed_source",id(source)},{"publications",ids(published)},{"lambda_eligible",boolean(eligible_lambda)},{"lambda_draw",eligible_lambda?fp(draw):"null"},{"pending_window",window.json()}};if(!production)public_events.push_back(obj(ev));if(trace){ev["private_states"]=states();ev["public_frontier"]=ids(V(public_tips.begin(),public_tips.end()));ev["canonical_chain"]=ids(canonical);ev["publication_sequence"]=num(publication);ev["rewards"]=counts(rewards,&reward_seen());ev["rng"]=rngs();ev["punishment"]=punishment();traces.push_back(obj(ev));}}
    }
    // Counter keeps an actor key even when later reorganizations return it to 0.
    std::vector<bool> reward_seen_storage;
    const std::vector<bool>& reward_seen(){return reward_seen_storage;}
    S block_json(int b)const {
        const auto& v=blocks[b];
        // This is the exact durable JSON ordering, emitted from native fields.
        // Avoid ten map nodes and dynamic key sorting for every ledger block.
        return "{\"canonical\":"+boolean(v.canonical)+
            ",\"discovery_sequence\":"+num(b)+",\"height\":"+num(v.height)+
            ",\"id\":"+num(b)+",\"initially_withheld\":"+boolean(v.withheld)+
            ",\"owner_id\":"+quote(names[v.owner])+",\"parent_id\":"+id(v.parent)+
            ",\"publication_kind\":"+(v.publication?quote(v.kind):"null")+
            ",\"publication_sequence\":"+id(v.publication)+
            ",\"release_batch\":"+id(v.batch)+'}';
    }
    std::pair<O,O> terminal()const {
        const int n=names.size();V public_frontier(public_tips.begin(),public_tips.end()),private_frontier;
        std::vector<bool> hidden_parent(blocks.size()),frontier_block(blocks.size());
        for(int b=1;b<int(blocks.size());++b)if(!pub(b))hidden_parent[blocks[b].parent]=true;
        for(int b=1;b<int(blocks.size());++b)if(!pub(b)&&!hidden_parent[b])private_frontier.push_back(b);
        // Compact owner-prefix counts replace repeated Python Counter copies.
        std::vector<int> prefix((canonical.size()+1)*n);
        for(size_t i=0;i<canonical.size();++i){std::copy_n(prefix.begin()+i*n,n,prefix.begin()+(i+1)*n);++prefix[(i+1)*n+blocks[canonical[i]].owner];}
        std::vector<S> branch_json;V ancestors,exposures,lengths;std::vector<V> exposed_by_actor(n);
        for(int visibility=0;visibility<2;++visibility){const V& tips=visibility?private_frontier:public_frontier;for(int tip:tips){if(!visibility&&tip==reference)continue;int ancestor=tip;V path;while(ancestor&&!blocks[ancestor].canonical){path.push_back(ancestor);frontier_block[ancestor]=true;ancestor=blocks[ancestor].parent;}std::reverse(path.begin(),path.end());int ah=h(ancestor);O exposed_counts;for(int a=0;a<n;++a){int value=rewards[a]-prefix[ah*n+a];exposed_counts[names[a]]=num(value);exposed_by_actor[a].push_back(value);}O branch={{"tip",id(tip)},{"visibility",quote(visibility?"private":"public")},{"common_ancestor",id(ancestor)},{"common_ancestor_height",num(ah)},{"path",ids(path)},{"height",num(h(tip))},{"canonical_blocks_exposed",num(height-ah)},{"active_target_private",boolean(has(chain,tip))},{"canonical_rewards_exposed",obj(exposed_counts)}};if(visibility){branch["private_actor"]=quote(names[blocks[tip].owner]);branch["active_selfish_private"]=boolean(has(chain,tip));}branch_json.push_back(obj(branch));ancestors.push_back(ah);exposures.push_back(height-ah);lengths.push_back(path.size());}}
        std::vector<S> canon_blocks,other_blocks;for(int b:canonical)canon_blocks.push_back(block_json(b));for(int b=1;b<int(blocks.size());++b)if(frontier_block[b])other_blocks.push_back(block_json(b));
        bool unresolved=!branch_json.empty()||race_target||window.active()||!pending.empty();O bounds;if(unresolved)for(const S& name:names)bounds[name]="[0.0,1.0]";
        O boundary={{"method",quote("common-persistent-complete-frontier-v2")},{"potentially_material",boolean(unresolved)},{"max_exposed_canonical_blocks",num(exposures.empty()?0:*std::max_element(exposures.begin(),exposures.end()))},{"future_reorganization_excluded",unresolved?"false":"null"},{"actor_payoff_bounds",unresolved?obj(bounds):"null"},{"interpretation",quote("Unresolved branches have no proven small future-payoff bound; intervals are worst-case bounds, not confidence intervals.")},{"private_leads",selfish?obj({{"target",num(chain.empty()?0:h(chain.back())-height)}}):"{}"}};
        S all_branches=array(branch_json),abandoned_json=ids(sorted(abandoned)),state_json=states();
        O term={{"reference_tip",id(reference)},{"reference_height",num(height)},{"canonical_chain",ids(canonical)},{"canonical_blocks",array(canon_blocks)},{"public_frontier",ids(public_frontier)},{"private_frontier",ids(private_frontier)},{"frontier_blocks",array(other_blocks)},{"alternative_branches",all_branches},{"target_private_chain",ids(chain)},{"abandoned_private",abandoned_json},{"pending_visibility_block",id(window.origin)},{"retaliation",punishment()},{"boundary",obj(boundary)},{"private_states",state_json},{"pending_publication_window",window.json()},{"reaction_queue",ids(pending)}};
        O fronts;for(int visibility=0;visibility<2;++visibility){const V& tips=visibility?private_frontier:public_frontier;V heights,deficits;std::map<S,int> owners;for(int b:tips){heights.push_back(h(b));deficits.push_back(height-h(b));++owners[names[blocks[b].owner]];}O owner_json;for(auto& [owner,count]:owners)owner_json[owner]=num(count);O f={{"count",num(tips.size())},{"sha256",quote(sha(ids(tips)))},{"height",range(heights)},{"reference_height_deficit",range(deficits)},{"owners",obj(owner_json)}};fronts[visibility?"private":"public"]=obj(f);}
        O private_summary;if(selfish){O s=state();V rivals;int tip=chain.empty()?0:chain.back();for(int b:longest)if(tip&&!descends(tip,b))rivals.push_back(b);s["private_chain"]=summary(ids(chain),chain.size());s["released_blocks"]=summary(ids(released),released.size());s["abandoned_private_blocks"]=summary(ids(abandoned),abandoned.size());s["competing_public_tips"]=summary(ids(rivals),rivals.size());private_summary["target"]=obj(s);}
        S retaliation="null";if(enabled)retaliation=obj({{"punishment_rule",quote("petty")},{"active_members",summary(active_names(),active.size())},{"race",race()}});
        O reward_ranges;if(unresolved)for(int a=0;a<n;++a)reward_ranges[names[a]]=range(exposed_by_actor[a]);
        O compact={{"schema",quote("persistent-terminal-science-summary-v2-1")},{"reference_tip",id(reference)},{"reference_height",num(height)},{"boundary",obj(boundary)},{"pending_publication_window",window.json()},{"reaction_queue",ids(pending)},{"retaliation",retaliation},{"frontier",obj(fronts)},{"private_states",obj(private_summary)},{"terminal_sha256",quote(sha(obj(term)))},{"canonical_chain",summary(ids(canonical),canonical.size())},{"alternative_branches",obj({{"count",num(branch_json.size())},{"sha256",quote(sha(all_branches))},{"common_ancestor_height",range(ancestors)},{"canonical_blocks_exposed",range(exposures)},{"path_length",range(lengths)},{"canonical_rewards_exposed",obj(reward_ranges)}})},{"target_private_chain",summary(ids(chain),chain.size())},{"abandoned_private",summary(abandoned_json,abandoned.size())}};
        return {std::move(term),std::move(compact)};
    }
    std::pair<S,S> report(const S& status,const S& error){
        V orphan(names.size()),hidden(names.size());for(int b=1;b<int(blocks.size());++b){auto& block=blocks[b];if(!pub(b))++hidden[block.owner];else if(!block.canonical)++orphan[block.owner];}
        O actors;long long orphan_total=0,hidden_total=0;for(size_t a=0;a<names.size();++a){double payoff=height?double(rewards[a])/height:0;actors[names[a]]=obj({{"role",quote(roles[a])},{"hash_power",hp_json[a]},{"discovered",num(discoveries[a])},{"accepted",num(rewards[a])},{"orphaned",num(orphan[a])},{"public_noncanonical",num(orphan[a])},{"unresolved",num(hidden[a])},{"payoff",height?fp(payoff):"null"},{"normalized_revenue",height?fp(payoff/powers[a]):"null"}});orphan_total+=orphan[a];hidden_total+=hidden[a];}
        O pairs;for(auto& [key,count]:natural_pairs)pairs[key]=num(count);
        std::vector<S> episode_json,batch_json,reaction_json,reorg_json;O outcomes;int opened=0,closed=0;for(auto& e:episodes){episode_json.push_back(e.json());if(e.opened)++opened;else ++closed;}if(opened)outcomes["PETTY_RACE_OPENED"]=num(opened);if(closed)outcomes["PETTY_RACE_CLOSED"]=num(closed);
        for(auto& b:batches)batch_json.push_back(b.json());std::map<int,int> round_counts;int max_rounds=0;for(size_t i=0;i<reactions.size();++i){reaction_json.push_back(reactions[i].json(i+1));max_rounds=std::max(max_rounds,++round_counts[reactions[i].event]);}V removed;for(auto& r:reorgs){reorg_json.push_back(r.json());removed.push_back(r.removed.size());}
        auto [term,terminal_compact]=terminal();O raw=metadata;
        raw["status"]=quote(status);raw["error"]=error.empty()?"null":quote(error);raw["events"]=num(events);raw["accepted_blocks"]=num(height);raw["actors"]=obj(actors);raw["member_opportunities"]=counts(opportunities,&opportunity_seen);raw["member_activations"]=counts(activations,&activation_seen);raw["natural_pairs"]=obj(pairs);raw["episodes"]=array(episode_json);raw["selfish_reactions"]=array(reaction_json);raw["selfish_actor_order"]=selfish?"[\"target\"]":"[]";raw["publication_batches"]=array(batch_json);raw["reorganizations"]=array(reorg_json);raw["terminal"]=obj(term);raw["rng"]=rngs();raw["scripted_discoveries"]=ids(scripted);raw["recording_mode"]=quote("production-v2");
        const S native_json=obj(raw);
        O compact;for(const S& field:{"identity","condition_id","status","events","accepted_blocks","actors","member_opportunities","member_activations","natural_pairs","rng"})compact[field]=raw[field];
        compact["schema"]=quote("persistent-scientific-condition-v2-compact-2");compact["terminal"]=obj(terminal_compact);compact["native_result_sha256"]=quote(sha(native_json));compact["accounting"]=obj({{"discovered",num(events)},{"accepted",num(height)},{"orphaned",num(orphan_total)},{"unresolved",num(hidden_total)}});
        compact["punishment"]=obj({{"reaction_diagnostics",obj({{"max_simultaneous_decisions",num(reactions.empty()?0:1)},{"max_rounds_in_discovery",num(max_rounds)}})},{"episodes",summary(raw["episodes"],episodes.size())},{"outcomes",obj(outcomes)},{"selfish_reactions",summary(raw["selfish_reactions"],reactions.size())},{"publication_batches",summary(raw["publication_batches"],batches.size())},{"reorganizations",obj({{"count",num(reorgs.size())},{"sha256",quote(sha(raw["reorganizations"]))},{"removed_depth",range(removed)}})}});
        if(!production){raw.erase("recording_mode");raw["public_events"]=array(public_events);}if(trace)raw["trace"]=array(traces);
        return {production?native_json:obj(raw),obj(compact)};
    }
    Output run(){S status="COMPLETE",error;auto start=std::chrono::steady_clock::now();
        try{if(has_actions){for(auto& action:actions){if(action.type==0)step(action.actor);else if(action.type==1)discover(action.actor,action.parent,action.withheld,action.kind);else if(action.type==2)publish(action.blocks,action.kind);else throw std::runtime_error("unknown action");}}
            else while(height<horizon&&(stop_after<0||events<stop_after)){if(events>=max_events){status="INCOMPLETE_RESOURCE_LIMIT";break;}step();}}
        catch(const Unsupported& e){status="UNSUPPORTED_STATE";error=e.what();}
        auto emitted=std::chrono::steady_clock::now();auto [raw,compact]=report(status,error);auto end=std::chrono::steady_clock::now();
        return {std::move(raw),std::move(compact),std::chrono::duration<double>(emitted-start).count(),std::chrono::duration<double>(end-emitted).count()};
    }
};

static void validate_input(PyObject* input){
    require(PyDict_Check(input),"dict input required");PyObject* states=field(input,"rng_states");require(PyTuple_Check(states)&&PyTuple_Size(states)==3,"three RNG streams required");
    PyObject* miners=field(input,"miners");require(PyList_Check(miners),"miner list required");for(Py_ssize_t i=0;i<PyList_Size(miners);++i){PyObject* m=PyList_GetItem(miners,i);require(PyTuple_Check(m)&&PyTuple_Size(m)==4,"miner tuple required");}
    require(PyDict_Check(field(input,"metadata")),"metadata required");PyObject* acts=field(input,"actions");if(acts!=Py_None){require(PyList_Check(acts),"action list required");for(Py_ssize_t i=0;i<PyList_Size(acts);++i){PyObject* a=PyList_GetItem(acts,i);require(PyTuple_Check(a)&&PyTuple_Size(a)>=2,"action tuple required");int type=integer(PyTuple_GetItem(a,0));require((type==0&&PyTuple_Size(a)==2)||(type==1&&PyTuple_Size(a)==5)||(type==2&&PyTuple_Size(a)==3),"action shape");}}
}
static PyObject* run_kernel(PyObject*,PyObject* input){try{validate_input(input);Engine engine(input);Output out=engine.run();return Py_BuildValue("(y#y#dd)",out.raw.data(),Py_ssize_t(out.raw.size()),out.compact.data(),Py_ssize_t(out.compact.size()),out.simulation_seconds,out.emission_seconds);}catch(const std::exception& e){if(!PyErr_Occurred())PyErr_SetString(PyExc_ValueError,e.what());return nullptr;}}
static PyObject* rng_test(PyObject*,PyObject* args){PyObject* state;int count;if(!PyArg_ParseTuple(args,"Oi",&state,&count))return nullptr;try{require(count>=0&&count<=100000,"RNG test draw bound");RNG rng(state);Ref values(PyList_New(count));for(int i=0;i<count;++i)PyList_SET_ITEM(values.p,i,PyFloat_FromDouble(rng.random()));Ref final_state(rng.state());return PyTuple_Pack(2,values.p,final_state.p);}catch(const std::exception& e){if(!PyErr_Occurred())PyErr_SetString(PyExc_ValueError,e.what());return nullptr;}}
static PyMethodDef methods[]={{"run",run_kernel,METH_O,"One native H/S0/petty condition; returns raw and unattested compact JSON."},{"rng_test",rng_test,METH_VARARGS,"Exact MT state/draw diagnostic only."},{nullptr,nullptr,0,nullptr}};
static PyModuleDef module={PyModuleDef_HEAD_INIT,"_persistent_v2_prototype","Experimental condition kernel, never production dispatch.",-1,methods};
PyMODINIT_FUNC PyInit__persistent_v2_prototype(){return PyModule_Create(&module);}
