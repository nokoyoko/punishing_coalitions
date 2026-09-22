// Persistent-v2 condition kernel. Python remains the scientific reference.
// CPython C API is used only for condition I/O, constant-sized float formatting,
// and bulk SHA-256. There are no Python calls in the production discovery loop.
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <ctime>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using S=std::string;
using V=std::vector<int>;
using O=std::map<S,S>;
static void require(bool ok,const char* s) { if(!ok) throw std::runtime_error(s); }
static void require(bool ok,const S& s) { if(!ok) throw std::runtime_error(s); }
struct Ref { PyObject* p; explicit Ref(PyObject* p):p(p){if(!p) throw std::runtime_error("CPython operation failed");} ~Ref(){Py_DECREF(p);} Ref(const Ref&)=delete; };
static S text(PyObject* v){require(PyUnicode_Check(v),"string required");Py_ssize_t size=0;const char* p=PyUnicode_AsUTF8AndSize(v,&size);require(p,"invalid UTF8");return S(p,size);}
static PyObject* field(PyObject* d,const char* key){PyObject* v=PyDict_GetItemString(d,key);require(v,S("missing input: ")+key);return v;}
static int integer(PyObject* v){require(PyLong_Check(v)&&!PyBool_Check(v),"integer required");long x=PyLong_AsLong(v);require(!PyErr_Occurred()&&x>=-1&&x<=3000000,"integer outside native range");return int(x);}
static V ints(PyObject* p){Ref seq(PySequence_Fast(p,"sequence required"));V r;for(Py_ssize_t i=0;i<PySequence_Fast_GET_SIZE(seq.p);++i)r.push_back(integer(PySequence_Fast_GET_ITEM(seq.p,i)));return r;}
static S num(long long x){return std::to_string(x);}
static S id(int x){return x?num(x):"null";}
static S boolean(bool x){return x?"true":"false";}
static S quote(const S& s){
    S r="\"";const char* hex="0123456789abcdef";
    auto escaped=[&](unsigned cp){r+="\\u";for(int shift=12;shift>=0;shift-=4)r+=hex[(cp>>shift)&15];};
    for(size_t i=0;i<s.size();++i){unsigned char c=s[i];
        if(c=='"'||c=='\\'){r+='\\';r+=char(c);}else if(c=='\b')r+="\\b";else if(c=='\f')r+="\\f";else if(c=='\n')r+="\\n";else if(c=='\r')r+="\\r";else if(c=='\t')r+="\\t";
        else if(c<32||c==127)escaped(c);else if(c<128)r+=char(c);
        else{int count=c<224?2:c<240?3:4;unsigned cp=c&((1u<<(7-count))-1);for(int j=1;j<count;++j){require(++i<s.size()&&(static_cast<unsigned char>(s[i])&192)==128,"invalid UTF8 identifier");cp=(cp<<6)|(static_cast<unsigned char>(s[i])&63);}if(cp<65536)escaped(cp);else{cp-=65536;escaped(0xd800+(cp>>10));escaped(0xdc00+(cp&1023));}}
    }return r+'"';
}
static S obj(const O& fields){S r="{";bool first=true;for(auto& [k,v]:fields){if(!first)r+=',';first=false;r+=quote(k);r+=':';r+=v;}return r+'}';}
static S array(const std::vector<S>& xs){size_t size=2+xs.size();for(const S& s:xs)size+=s.size();S r;r.reserve(size);r+='[';for(size_t i=0;i<xs.size();++i){if(i)r+=',';r+=xs[i];}return r+']';}
static S ids(const V& xs,bool nullable=false){S r="[";for(size_t i=0;i<xs.size();++i){if(i)r+=',';r+=nullable?id(xs[i]):num(xs[i]);}return r+']';}
static V sorted(V xs){std::sort(xs.begin(),xs.end());return xs;}
static bool has(const V& xs,int b){return std::find(xs.begin(),xs.end(),b)!=xs.end();}
static S fp(double x){require(std::isfinite(x),"nonfinite native output");Ref value(PyFloat_FromDouble(x));Ref repr(PyObject_Repr(value.p));return text(repr.p);}
#include "path_emission.hpp"

static S sha(const S& bytes){
    Ref module(PyImport_ImportModule("hashlib"));Ref fn(PyObject_GetAttrString(module.p,"sha256"));
    Ref hash(PyObject_CallNoArgs(fn.p));
    auto update=[&](const char* p,size_t n){if(!n)return;Ref view(PyMemoryView_FromMemory(const_cast<char*>(p),Py_ssize_t(n),PyBUF_READ));Ref result(PyObject_CallMethod(hash.p,"update","O",view.p));};
    if(path_emission)path_emission->emit(bytes,update);else update(bytes.data(),bytes.size());
    Ref hex(PyObject_CallMethod(hash.p,"hexdigest",nullptr));return text(hex.p);
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
struct Reorg {
    int event,ancestor,old_tip,new_tip,removed_count;
    S json()const{return obj({{"event",num(event)},{"common_ancestor",id(ancestor)},
        {"removed",path_emission->defer(old_tip,ancestor,false)},
        {"added",path_emission->defer(new_tip,ancestor,true)}});}
};
struct Episode {bool opened;int target,event,publication;V tips;S json()const{return obj({{"outcome",quote(opened?"PETTY_RACE_OPENED":"PETTY_RACE_CLOSED")},{"target_tip",id(target)},{"tips",ids(tips)},{"discovery_event",num(event)},{"publication_sequence",num(publication)}});}};
struct Decision {int actor,tip;bool abandon;V blocks;};
struct Reaction {
    int event,height,publication;V observed;std::vector<Decision> decisions;
    S json(int round,const std::vector<S>& names)const {
        std::vector<S> ds;
        for(const auto& d:decisions)ds.push_back(obj({{"actor_id",quote(names[d.actor])},{"action",quote(d.abandon?"ABANDON":"RELEASE")},{"blocks",ids(d.blocks)},{"private_tip_before",id(d.tip)}}));
        return obj({{"outcome",quote("SELFISH_REACTION_ROUND")},{"round",num(round)},{"discovery_event",num(event)},{"observed_publications",ids(observed)},{"public_height",num(height)},{"publication_sequence",num(publication)},{"decisions",array(ds)}});
    }
};
struct Private {V chain,released,abandoned;int exposed=0;bool enabled=false;};
struct CounterEpisode {
    int number=0,trigger=0,anchor=0,publication=0,defended=0,depth=0,refresh=0;
    O fields()const{return {{"episode_id",num(number)},{"trigger",id(trigger)},{"anchor",id(anchor)},{"publication_index",num(publication)},{"defended_height",num(defended)},{"depth",num(depth)},{"refresh_count",num(refresh)}};}
};
struct Window {int event=0,origin=0;V blocks,delayed;bool active()const{return origin!=0;}S json()const{return active()?obj({{"discovery_event",num(event)},{"origin_block",id(origin)},{"blocks",ids(blocks)},{"delayed_tips",ids(delayed)}}):"null";}};
struct Branch {int tip,ancestor;bool hidden;V path,exposed;};
struct Action {int type,actor=-1,parent=0;bool withheld=false;V blocks;S kind="ordinary";};
struct Output {S raw,compact;double simulation_seconds,emission_seconds,simulation_cpu,emission_cpu;};

class Engine {
public:
    std::vector<S> names,roles,hp_json;std::vector<double> powers;
    double gamma,lambda;int horizon,max_events,stop_after;bool selfish,enabled,production,trace;
    V active,rewards,discoveries,activations,opportunities;std::vector<bool> activation_seen,opportunity_seen;
    std::vector<Block> blocks{Block{}};std::set<int> public_tips;V longest,canonical;
    std::vector<V> levels{{0}};int height=0,events=0,publication=0,batch_number=0,reference=0;
    std::array<Private,8> private_states;
    V &chain=private_states[0].chain,&released=private_states[0].released,&abandoned=private_states[0].abandoned;
    int &exposed=private_states[0].exposed;V pending;bool processing=false;
    S rule;int counter_k=0;CounterEpisode counter;int next_episode=1,defending_maximum=0;
    V defending_depth{0},rejected_by{0};std::vector<V> counter_levels,acceptable_levels{{0}},children{{}};
    std::vector<std::array<int,23>> jumps{std::array<int,23>{}};
    std::set<int> rejected_roots,minimal_roots,competing_roots,eligible_frontier{0};int best_eligible_height=0;
    std::vector<O> policy_events;
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
        require(horizon>0&&horizon<=30000&&max_events>0,"native horizon/resource bound");
        require(gamma>=0&&gamma<=1&&lambda>=0&&lambda<=1,"probability out of range");
        require(!(production&&trace),"trace and production conflict");
        PyObject* miners=field(input,"miners");Ref seq(PySequence_Fast(miners,"miners required"));
        for(Py_ssize_t i=0;i<PySequence_Fast_GET_SIZE(seq.p);++i){PyObject* m=PySequence_Fast_GET_ITEM(seq.p,i);names.push_back(text(PyTuple_GetItem(m,0)));roles.push_back(text(PyTuple_GetItem(m,1)));powers.push_back(PyFloat_AsDouble(PyTuple_GetItem(m,2)));hp_json.push_back(text(PyTuple_GetItem(m,3)));quote(names.back());}
        require(names.size()>=3&&names.size()<=8&&names.front()=="target"&&names.back()=="honest_residual","native miner coverage");
        active=ints(field(input,"active"));for(int a:active)require(a>0&&a<int(names.size())-1,"invalid active member");
        int n=names.size();rewards.resize(n);discoveries.resize(n);activations.resize(n);opportunities.resize(n);activation_seen.resize(n);opportunity_seen.resize(n);reward_seen_storage.resize(n);
        PyObject* header=field(input,"metadata");PyObject *k,*v;Py_ssize_t pos=0;while(PyDict_Next(header,&pos,&k,&v))metadata[text(k)]=text(v);
        rule=text(field(input,"rule"));counter_k=integer(field(input,"counter_fork_k"));
        require(rule=="none"||rule=="petty"||rule=="counter_fork"||rule=="ignore"||rule=="selfish","unsupported native rule");
        require(rule!="counter_fork"||(counter_k>=1&&counter_k<=3),"native production depth is 1..3");
        private_states[0].enabled=selfish;
        if(rule=="selfish")for(int a:active){private_states[a].enabled=true;activations[a]=1;activation_seen[a]=true;}
        PyObject* script=field(input,"actions");has_actions=script!=Py_None;
        if(has_actions){Ref acts(PySequence_Fast(script,"actions required"));require(PySequence_Fast_GET_SIZE(acts.p)<=512,"debug action bound");for(Py_ssize_t i=0;i<PySequence_Fast_GET_SIZE(acts.p);++i){PyObject* a=PySequence_Fast_GET_ITEM(acts.p,i);Action cmd;cmd.type=integer(PyTuple_GetItem(a,0));if(cmd.type==2){cmd.blocks=ints(PyTuple_GetItem(a,1));cmd.kind=text(PyTuple_GetItem(a,2));}else {cmd.actor=integer(PyTuple_GetItem(a,1));if(cmd.type==1){cmd.parent=integer(PyTuple_GetItem(a,2));cmd.withheld=PyObject_IsTrue(PyTuple_GetItem(a,3));cmd.kind=text(PyTuple_GetItem(a,4));}}actions.push_back(cmd);}}
    }
    int h(int b)const{return blocks[b].height;}
    bool pub(int b)const{return b&&blocks[b].publication!=0;}
    bool descends(int tip,int ancestor)const {
        if(h(tip)<h(ancestor))return false;
        unsigned distance=h(tip)-h(ancestor);int level=0;
        while(distance){if(distance&1)tip=jumps[tip][level];distance>>=1;++level;}
        return tip==ancestor;
    }
    int target_tip(const V& tips)const{int target=0,count=0;for(int b:tips)if(b&&blocks[b].owner==0){target=b;++count;}if(count>1)throw Unsupported("multiple simultaneous target-owned competing tips");return tips.size()>1?target:0;}
    V visible_hidden(int actor,const Window& incoming)const{V hidden=incoming.delayed;if(actor!=int(names.size())-1){for(int b:incoming.delayed)if(blocks[b].owner==actor){while(has(hidden,b)){hidden.erase(std::find(hidden.begin(),hidden.end(),b));b=blocks[b].parent;}}}return hidden;}
    V best_levels(const std::vector<V>& index,const V& hidden)const {
        for(int depth=int(index.size())-1;depth>=0;--depth){V result;for(int b:index[depth])if(!b||!has(hidden,b))result.push_back(b);if(!result.empty()){result=sorted(result);result.erase(std::unique(result.begin(),result.end()),result.end());return result;}}
        throw Unsupported("policy has no visible eligible parent");
    }
    V best(const V& hidden)const{return best_levels(levels,hidden);}
    static void index_add(std::vector<V>& index,int b,int height){if(int(index.size())<=height)index.resize(height+1);index[height].push_back(b);}
    V eligible(int actor,const V& hidden)const {
        V tips;
        if(has(active,actor)&&rule=="counter_fork"&&counter.number)tips=best_levels(counter_levels,hidden);
        else if(has(active,actor)&&rule=="ignore")tips=best_levels(acceptable_levels,hidden);
        else tips=best(hidden);
        if(rule=="petty"&&has(active,actor)){int t=target_tip(tips);if(t)tips.erase(std::find(tips.begin(),tips.end(),t));}
        return tips;
    }
    bool policy_active()const{return rule=="petty"?race_target!=0:rule=="counter_fork"?counter.number!=0:rule=="ignore"?!competing_roots.empty():false;}
    void finish_counter(const S& outcome){O e=counter.fields();e["outcome"]=quote(outcome);policy_events.push_back(e);counter=CounterEpisode{};}
    void counter_publication(const V& published){
        for(int bid:published)if(blocks[bid].owner==0&&std::any_of(longest.begin(),longest.end(),[&](int t){return descends(t,bid);})){
            int refresh=counter.number?counter.refresh+1:0;if(counter.number)finish_counter("REFRESHED");
            counter={next_episode++,bid,blocks[bid].parent,blocks[bid].publication,h(bid),0,refresh};
            for(int a:active){++activations[a];activation_seen[a]=true;}
            std::fill(defending_depth.begin(),defending_depth.end(),-1);defending_depth[bid]=0;defending_maximum=h(bid);counter_levels.clear();V todo{counter.anchor};
            while(!todo.empty()){int b=todo.back();todo.pop_back();if(b==bid)continue;if(!b||pub(b)){index_add(counter_levels,b,h(b));todo.insert(todo.end(),children[b].begin(),children[b].end());}}
        }
        if(!counter.number)return;
        for(int b:published){if(descends(b,counter.trigger)){defending_maximum=std::max(defending_maximum,h(b));if(b!=counter.trigger){require(defending_depth[blocks[b].parent]>=0,"missing defending parent");defending_depth[b]=defending_depth[blocks[b].parent]+(blocks[b].owner!=0&&!has(active,blocks[b].owner));counter.depth=std::max(counter.depth,defending_depth[b]);counter.defended=std::max(counter.defended,h(b));}}
            else if(descends(b,counter.anchor))index_add(counter_levels,b,h(b));}
        if(!descends(reference,counter.trigger)&&height>defending_maximum)finish_counter("SUCCEEDED");
        else if(counter.depth>=counter_k)finish_counter("CAPITULATED");
    }
    void ignore_publication(const V& published){
        for(int bid:published){const auto& b=blocks[bid];int root=rejected_by[b.parent];
            if(b.owner==0){rejected_roots.insert(bid);if(!root){minimal_roots.insert(bid);root=bid;}policy_events.push_back({{"outcome",quote("REJECTED_TARGET_ROOT")},{"root",id(bid)},{"first_rejected_ancestor",id(root)},{"publication_sequence",num(b.publication)},{"release_batch",num(b.batch)}});for(int a:active){++activations[a];activation_seen[a]=true;}}
            if(root)rejected_by[bid]=root;else {eligible_frontier.erase(b.parent);eligible_frontier.insert(bid);best_eligible_height=std::max(best_eligible_height,h(bid));}
        }
        std::set<int> next;for(int b:longest)if(rejected_by[b])next.insert(rejected_by[b]);
        for(int root:next)if(!competing_roots.count(root))policy_events.push_back({{"outcome",quote("CONFLICT_OPENED")},{"root",id(root)},{"publication_sequence",num(publication)}});
        for(int root:competing_roots)if(!next.count(root))policy_events.push_back({{"outcome",quote("CONFLICT_NO_LONGER_LEADING")},{"root",id(root)},{"publication_sequence",num(publication)}});
        competing_roots=std::move(next);
    }
    int choose(int actor,const V& tips){target_tip(tips);int own=0;for(int b:tips)if(b&&blocks[b].owner==actor&&(!own||blocks[b].publication>blocks[own].publication))own=b;if(actor!=int(names.size())-1&&own)return own;if(tips.size()==1)return tips[0];int target=target_tip(tips);double draw=tie_rng.random(),total=0;for(int b:tips){double probability=target?(b==target?gamma:(1-gamma)/(tips.size()-1)):1.0/tips.size();total+=probability;if(draw<total)return b;}return tips.back();}
    void adopt(int tip){int old_tip=reference;int old=reference,next=tip;V removed,added;while(old!=next){if(h(old)>=h(next)){removed.push_back(old);old=blocks[old].parent;}else{added.push_back(next);next=blocks[next].parent;}}
        for(int b:removed){blocks[b].canonical=false;--rewards[blocks[b].owner];reward_seen_storage[blocks[b].owner]=true;}if(!removed.empty())canonical.resize(canonical.size()-removed.size());std::reverse(added.begin(),added.end());for(int b:added){blocks[b].canonical=true;++rewards[blocks[b].owner];reward_seen_storage[blocks[b].owner]=true;canonical.push_back(b);}if(!removed.empty())reorgs.push_back({events,old,old_tip,tip,int(removed.size())});reference=tip;}
    void petty_publication(){if(rule!="petty")return;int target=target_tip(longest);V tips=target?longest:V{};if(target==race_target&&tips==race_tips)return;if(race_target)episodes.push_back({false,race_target,events,publication,race_tips});race_target=target;race_tips=tips;if(target){episodes.push_back({true,target,events,publication,tips});for(int a:active){++activations[a];activation_seen[a]=true;}}}
    void selfish_publication(const V& published){
        for(size_t actor=0;actor<names.size();++actor){auto& s=private_states[actor];if(!s.enabled)continue;
            s.chain.erase(std::remove_if(s.chain.begin(),s.chain.end(),[&](int b){return has(published,b);}),s.chain.end());
            for(int b:published)if(blocks[b].owner==int(actor)){s.exposed=b;if(blocks[b].withheld)s.released.push_back(b);}}
        pending.insert(pending.end(),published.begin(),published.end());if(processing)return;processing=true;
        try{while(!pending.empty()){
            V observed;observed.swap(pending);std::vector<Decision> decisions;
            for(size_t actor=0;actor<names.size();++actor){const auto& s=private_states[actor];if(!s.enabled||s.chain.empty())continue;int tip=s.chain.back();V rivals;for(int b:longest)if(!descends(tip,b))rivals.push_back(b);
                if(rivals.empty()||std::none_of(observed.begin(),observed.end(),[&](int b){return has(rivals,b);}))continue;
                int gap=h(tip)-h(rivals[0]);bool abandon=gap<0;V plan;
                if(abandon||gap<=1)plan=s.chain;else for(int b:s.chain)if(h(b)<=h(rivals[0]))plan.push_back(b);
                if(!plan.empty())decisions.push_back({int(actor),tip,abandon,plan});
            }
            if(decisions.empty())continue;reactions.push_back({events,height,publication,observed,decisions});
            size_t before=0;for(const auto& s:private_states)before+=s.chain.size();
            for(const auto& d:decisions){auto& s=private_states[d.actor];if(d.abandon){s.abandoned.insert(s.abandoned.end(),s.chain.begin(),s.chain.end());s.chain.clear();}else publish(d.blocks,d.actor==0?"target_selfish_release":"member_selfish_release");}
            size_t after=0;for(const auto& s:private_states)after+=s.chain.size();require(after<before,"reaction round made no private-state progress");
        }}catch(...){processing=false;throw;}processing=false;
    }
    void publish(const V& ids_to_publish,const S& kind){std::set<int> seen;V added;for(int b:ids_to_publish){require(b>0&&b<int(blocks.size()),"unknown publication");require(seen.insert(b).second,"duplicate ID inside publication batch");if(pub(b))continue;int parent=blocks[b].parent;require(!parent||pub(parent)||has(added,parent),"publication must expose parents before children");added.push_back(b);}if(added.empty())return;
        int maximum=height;for(int b:added)maximum=std::max(maximum,h(b));V high;for(int b:added)if(h(b)==maximum)high.push_back(b);if(maximum==height)high.insert(high.end(),longest.begin(),longest.end());high=sorted(high);high.erase(std::unique(high.begin(),high.end()),high.end());target_tip(high);
        height=maximum;longest=high;++batch_number;for(int b:added){public_tips.insert(b);}for(int b:added){public_tips.erase(blocks[b].parent);Block& block=blocks[b];block.publication=++publication;block.batch=batch_number;block.kind=kind;}
        int chosen=has(longest,reference)?reference:*std::min_element(longest.begin(),longest.end(),[&](int a,int b){return std::make_pair(blocks[a].publication,a)<std::make_pair(blocks[b].publication,b);});adopt(chosen);batches.push_back({batch_number,events,added,kind});petty_publication();if(rule=="counter_fork")counter_publication(added);if(rule=="ignore")ignore_publication(added);for(int b:added){index_add(levels,b,h(b));if(!rejected_by[b])index_add(acceptable_levels,b,h(b));}selfish_publication(added);}
    int discover(int actor,int parent,bool withheld,const S& kind){require(actor>=0&&actor<int(names.size()),"unknown owner or parent");require(parent>=0&&parent<int(blocks.size()),"unknown owner or parent");require(!parent||pub(parent)||blocks[parent].owner==actor,"cannot mine on another actor's hidden block");if(withheld){require(private_states[actor].enabled,"honest actor has no private state");const auto& own=private_states[actor].chain;require(own.empty()||parent==own.back(),"private actor must extend its own private tip");require(!own.empty()||!parent||pub(parent),"private chain must start on public history");}
        ++events;int b=blocks.size();Block block;block.parent=parent;block.height=h(parent)+1;block.owner=actor;block.withheld=withheld;blocks.push_back(block);children.emplace_back();children[parent].push_back(b);defending_depth.push_back(-1);rejected_by.push_back(0);std::array<int,23> j{};j[0]=parent;for(int l=1;l<23;++l)j[l]=jumps[j[l-1]][l-1];jumps.push_back(j);++discoveries[actor];if(!withheld)publish({b},kind);if(withheld)private_states[actor].chain.push_back(b);return b;}
    O state(int actor=0)const{const auto& s=private_states[actor];const V& chain=s.chain;const V& released=s.released;const V& abandoned=s.abandoned;int exposed=s.exposed;int tip=chain.empty()?0:chain.back();V rivals;for(int b:longest)if(tip&&!descends(tip,b))rivals.push_back(b);bool leading=has(longest,exposed);S phase=!chain.empty()?(longest.size()>1?"PRIVATE_WITH_PUBLIC_TIE":"PRIVATE"):(leading&&longest.size()>1?"EXPOSED_RACE":"PUBLIC");return {{"actor_id",quote(names[actor])},{"private_chain",ids(chain)},{"private_fork_base",chain.empty()?"null":id(blocks[chain.front()].parent)},{"private_tip",id(tip)},{"private_tip_height",num(h(tip))},{"private_block_count",num(chain.size())},{"lead_relative_to_public_height",num(tip?h(tip)-height:0)},{"competing_public_tips",ids(rivals)},{"exposed_tip",id(exposed)},{"exposure_is_leading",boolean(leading)},{"released_blocks",ids(released)},{"abandoned_private_blocks",ids(abandoned)},{"phase",quote(phase)}};}
    S active_names()const{std::vector<S> values;for(int a:active)values.push_back(names[a]);std::sort(values.begin(),values.end());for(S& a:values)a=quote(a);return array(values);}
    S race()const{return race_target?obj({{"target_tip",id(race_target)},{"tips",ids(race_tips)}}):"null";}
    O punishment_fields()const {
        if(rule=="petty")return {{"punishment_rule",quote("petty")},{"active_members",active_names()},{"race",race()}};
        if(rule=="counter_fork")return counter.number?counter.fields():O{};
        if(rule=="selfish")return {{"punishment_rule",quote("selfish")},{"activation_event","0"},{"active_members",active_names()}};
        if(rule=="ignore"){V rejected;for(int b:public_tips)if(rejected_by[b])rejected.push_back(b);return {{"punishment_rule",quote("ignore")},{"armed","true"},{"activation_publication_sequence","0"},{"rejected_roots",ids(V(rejected_roots.begin(),rejected_roots.end()))},{"minimal_rejected_roots",ids(V(minimal_roots.begin(),minimal_roots.end()))},{"competing_rejected_roots",ids(V(competing_roots.begin(),competing_roots.end()))},{"conflict_active",boolean(policy_active())},{"eligible_public_frontier",ids(V(eligible_frontier.begin(),eligible_frontier.end()),true)},{"rejected_public_frontier",ids(rejected)},{"best_eligible_height",num(best_eligible_height)},{"reference_rejected",boolean(rejected_by[reference])},{"reference_height_minus_best_eligible_height",num(height-best_eligible_height)}};}
        return {};
    }
    S punishment()const{O p=punishment_fields();return p.empty()?"null":obj(p);}
    S states()const{O out;for(size_t a=0;a<names.size();++a)if(private_states[a].enabled)out[names[a]]=obj(state(a));return obj(out);}
    S rngs()const{return obj({{"discoveries",discovery_rng.snapshot()},{"ties",tie_rng.snapshot()},{"natural",natural_rng.snapshot()}});}
    S counts(const V& values,const std::vector<bool>* seen=nullptr)const{O out;for(size_t a=0;a<names.size();++a)if(seen?(*seen)[a]:values[a]!=0)out[names[a]]=num(values[a]);return obj(out);}
    void step(int actor=-1){if(actor<0){double d=discovery_rng.random(),total=0;actor=names.size()-1;for(size_t a=0;a<powers.size();++a){total+=powers[a];if(d<total){actor=a;break;}}}else {require(actor<int(names.size()),"unknown discoverer");scripted.push_back(events+1);}
        Window incoming=window;window=Window{};int start_height=height;V start_tips=longest;size_t start_batch=batches.size();if(policy_active()||rule=="selfish")for(int a:active){++opportunities[a];opportunity_seen[a]=true;}int source=0,b=0,parent=0;V tips;long long tie_before=tie_rng.count;S choice="null";
        if(private_states[actor].enabled&&!private_states[actor].chain.empty()){b=discover(actor,private_states[actor].chain.back(),true,"ordinary");}
        else {V hidden=private_states[actor].enabled?V{}:visible_hidden(actor,incoming);tips=eligible(actor,hidden);parent=choose(actor,tips);if(!production||trace)choice=obj({{"tips",ids(tips,true)},{"parent",id(parent)},{"draw",tie_rng.count>tie_before?fp(tie_rng.last):"null"}});
            if(private_states[actor].enabled)b=discover(actor,parent,start_tips.size()<=1,actor==0?"target_tie_resolution":"member_tie_resolution");
            else {V full=eligible(actor,{});if(incoming.active()&&h(parent)<h(full[0]))for(int candidate:full)if(candidate&&has(hidden,candidate)&&(!source||blocks[candidate].publication<blocks[source].publication))source=candidate;
                bool punishing=has(active,actor)&&(rule=="petty"?target_tip(best(hidden))!=0:policy_active());S kind=punishing?rule:source?"natural_fork":"ordinary";b=discover(actor,parent,false,kind);if(kind=="natural_fork"){S a=names[actor],other=names[blocks[source].owner];if(other<a)std::swap(a,other);++natural_pairs[a+"--"+other];}}
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
    std::pair<O,O> terminal(bool summaries=true)const {
        const int n=names.size();V public_frontier(public_tips.begin(),public_tips.end()),private_frontier;
        std::vector<bool> hidden_parent(blocks.size()),frontier_block(blocks.size());
        V canonical_ancestor(blocks.size());for(int b=1;b<int(blocks.size());++b){canonical_ancestor[b]=blocks[b].canonical?b:canonical_ancestor[blocks[b].parent];frontier_block[b]=!blocks[b].canonical;}
        for(int b=1;b<int(blocks.size());++b)if(!pub(b))hidden_parent[blocks[b].parent]=true;
        for(int b=1;b<int(blocks.size());++b)if(!pub(b)&&!hidden_parent[b])private_frontier.push_back(b);
        // Compact owner-prefix counts replace repeated Python Counter copies.
        std::vector<int> prefix((canonical.size()+1)*n);
        for(size_t i=0;i<canonical.size();++i){std::copy_n(prefix.begin()+i*n,n,prefix.begin()+(i+1)*n);++prefix[(i+1)*n+blocks[canonical[i]].owner];}
        std::vector<S> branch_json;V ancestors,exposures,lengths;std::vector<V> exposed_by_actor(n);
        for(int visibility=0;visibility<2;++visibility){const V& tips=visibility?private_frontier:public_frontier;for(int tip:tips){if(!visibility&&tip==reference)continue;int ancestor=canonical_ancestor[tip];S path=path_emission->defer(tip,ancestor);int ah=h(ancestor);O exposed_counts;for(int a=0;a<n;++a){int value=rewards[a]-prefix[ah*n+a];exposed_counts[names[a]]=num(value);exposed_by_actor[a].push_back(value);}O branch={{"tip",id(tip)},{"visibility",quote(visibility?"private":"public")},{"common_ancestor",id(ancestor)},{"common_ancestor_height",num(ah)},{"path",path},{"height",num(h(tip))},{"canonical_blocks_exposed",num(height-ah)},{"active_target_private",boolean(has(chain,tip))},{"canonical_rewards_exposed",obj(exposed_counts)}};if(visibility){branch["private_actor"]=quote(names[blocks[tip].owner]);branch["active_selfish_private"]=boolean(has(private_states[blocks[tip].owner].chain,tip));}if(rule=="ignore"){int public_ancestor=tip;while(public_ancestor&&!pub(public_ancestor))public_ancestor=blocks[public_ancestor].parent;branch["first_rejected_public_ancestor"]=id(rejected_by[public_ancestor]);branch["eligible_by_published_ancestry"]=boolean(!rejected_by[public_ancestor]);}branch_json.push_back(obj(branch));ancestors.push_back(ah);exposures.push_back(height-ah);lengths.push_back(h(tip)-ah);}}
        std::vector<S> canon_blocks,other_blocks;for(int b:canonical)canon_blocks.push_back(block_json(b));for(int b=1;b<int(blocks.size());++b)if(frontier_block[b])other_blocks.push_back(block_json(b));
        bool unresolved=!branch_json.empty()||policy_active()||window.active()||!pending.empty();O bounds;if(unresolved)for(const S& name:names)bounds[name]="[0.0,1.0]";
        O boundary={{"method",quote("common-persistent-complete-frontier-v2")},{"potentially_material",boolean(unresolved)},{"max_exposed_canonical_blocks",num(exposures.empty()?0:*std::max_element(exposures.begin(),exposures.end()))},{"future_reorganization_excluded",unresolved?"false":"null"},{"actor_payoff_bounds",unresolved?obj(bounds):"null"},{"interpretation",quote("Unresolved branches have no proven small future-payoff bound; intervals are worst-case bounds, not confidence intervals.")},{"private_leads",selfish?obj({{"target",num(chain.empty()?0:h(chain.back())-height)}}):"{}"}};
        O leads;V all_abandoned;for(size_t a=0;a<names.size();++a)if(private_states[a].enabled){const auto& own=private_states[a];leads[names[a]]=num(own.chain.empty()?0:h(own.chain.back())-height);all_abandoned.insert(all_abandoned.end(),own.abandoned.begin(),own.abandoned.end());}boundary["private_leads"]=obj(leads);
        std::vector<S> eligible_branches;V eligible_heights,eligible_exposures;
        if(rule=="ignore"){
            for(int tip:eligible_frontier){int ancestor=canonical_ancestor[tip];S path=path_emission->defer(tip,ancestor);int exposure=height-h(ancestor);eligible_exposures.push_back(exposure);eligible_heights.push_back(h(tip));eligible_branches.push_back(obj({{"tip",id(tip)},{"height",num(h(tip))},{"common_ancestor",id(ancestor)},{"common_ancestor_height",num(h(ancestor))},{"path",path},{"canonical_blocks_exposed",num(exposure)}}));}
            int maximum=exposures.empty()?0:*std::max_element(exposures.begin(),exposures.end());for(int e:eligible_exposures)maximum=std::max(maximum,e);
            boundary["max_exposed_canonical_blocks"]=num(maximum);boundary["reference_rejected_by_active_coalition"]=boolean(rejected_by[reference]);boundary["best_eligible_height"]=num(best_eligible_height);boundary["reference_height_minus_best_eligible_height"]=num(height-best_eligible_height);
        }
        S all_branches=array(branch_json),abandoned_json=ids(sorted(all_abandoned)),state_json=states();
        O term={{"reference_tip",id(reference)},{"reference_height",num(height)},{"canonical_chain",ids(canonical)},{"canonical_blocks",array(canon_blocks)},{"public_frontier",ids(public_frontier)},{"private_frontier",ids(private_frontier)},{"frontier_blocks",array(other_blocks)},{"alternative_branches",all_branches},{"target_private_chain",ids(chain)},{"abandoned_private",abandoned_json},{"pending_visibility_block",id(window.origin)},{"retaliation",punishment()},{"boundary",obj(boundary)},{"private_states",state_json},{"pending_publication_window",window.json()},{"reaction_queue",ids(pending)}};
        if(rule=="ignore")term["ostracism_eligible_frontier"]=array(eligible_branches);
        if(!summaries)return {std::move(term),{}};
        O fronts;for(int visibility=0;visibility<2;++visibility){const V& tips=visibility?private_frontier:public_frontier;V heights,deficits;std::map<S,int> owners;for(int b:tips){heights.push_back(h(b));deficits.push_back(height-h(b));++owners[names[blocks[b].owner]];}O owner_json;for(auto& [owner,count]:owners)owner_json[owner]=num(count);O f={{"count",num(tips.size())},{"sha256",quote(sha(ids(tips)))},{"height",range(heights)},{"reference_height_deficit",range(deficits)},{"owners",obj(owner_json)}};fronts[visibility?"private":"public"]=obj(f);}
        O private_summary;
        for(size_t a=0;a<names.size();++a)if(private_states[a].enabled){const auto& own=private_states[a];O fields=state(a);V rivals;int tip=own.chain.empty()?0:own.chain.back();for(int b:longest)if(tip&&!descends(tip,b))rivals.push_back(b);fields["private_chain"]=summary(ids(own.chain),own.chain.size());fields["released_blocks"]=summary(ids(own.released),own.released.size());fields["abandoned_private_blocks"]=summary(ids(own.abandoned),own.abandoned.size());fields["competing_public_tips"]=summary(ids(rivals),rivals.size());private_summary[names[a]]=obj(fields);}
        O ret=punishment_fields();
        if(ret.count("active_members"))ret["active_members"]=summary(active_names(),active.size());
        if(rule=="ignore"){
            ret["rejected_roots"]=summary(ret["rejected_roots"],rejected_roots.size());ret["minimal_rejected_roots"]=summary(ret["minimal_rejected_roots"],minimal_roots.size());ret["competing_rejected_roots"]=summary(ret["competing_rejected_roots"],competing_roots.size());ret["eligible_public_frontier"]=summary(ret["eligible_public_frontier"],eligible_frontier.size());size_t rejected=0;for(int b:public_tips)if(rejected_by[b])++rejected;ret["rejected_public_frontier"]=summary(ret["rejected_public_frontier"],rejected);
        }
        S retaliation=ret.empty()?"null":obj(ret);
        O reward_ranges;if(unresolved)for(int a=0;a<n;++a)reward_ranges[names[a]]=range(exposed_by_actor[a]);
        O compact={{"schema",quote("persistent-terminal-science-summary-v2-1")},{"reference_tip",id(reference)},{"reference_height",num(height)},{"boundary",obj(boundary)},{"pending_publication_window",window.json()},{"reaction_queue",ids(pending)},{"retaliation",retaliation},{"frontier",obj(fronts)},{"private_states",obj(private_summary)},{"terminal_sha256",quote(sha(obj(term)))},{"canonical_chain",summary(ids(canonical),canonical.size())},{"alternative_branches",obj({{"count",num(branch_json.size())},{"sha256",quote(sha(all_branches))},{"common_ancestor_height",range(ancestors)},{"canonical_blocks_exposed",range(exposures)},{"path_length",range(lengths)},{"canonical_rewards_exposed",obj(reward_ranges)}})},{"target_private_chain",summary(ids(chain),chain.size())},{"abandoned_private",summary(abandoned_json,abandoned.size())}};
        if(rule=="ignore")compact["ostracism_eligible_frontier"]=obj({{"count",num(eligible_branches.size())},{"sha256",quote(sha(array(eligible_branches)))},{"height",range(eligible_heights)},{"canonical_blocks_exposed",range(eligible_exposures)}});
        return {std::move(term),std::move(compact)};
    }
    std::pair<S,S> report(const S& status,const S& error,bool summaries=true){
        V orphan(names.size()),hidden(names.size());for(int b=1;b<int(blocks.size());++b){auto& block=blocks[b];if(!pub(b))++hidden[block.owner];else if(!block.canonical)++orphan[block.owner];}
        O actors;long long orphan_total=0,hidden_total=0;for(size_t a=0;a<names.size();++a){double payoff=height?double(rewards[a])/height:0;actors[names[a]]=obj({{"role",quote(roles[a])},{"hash_power",hp_json[a]},{"discovered",num(discoveries[a])},{"accepted",num(rewards[a])},{"orphaned",num(orphan[a])},{"public_noncanonical",num(orphan[a])},{"unresolved",num(hidden[a])},{"payoff",height?fp(payoff):"null"},{"normalized_revenue",height?fp(payoff/powers[a]):"null"}});orphan_total+=orphan[a];hidden_total+=hidden[a];}
        O pairs;for(auto& [key,count]:natural_pairs)pairs[key]=num(count);
        std::vector<S> episode_json,batch_json,reaction_json,reorg_json;O outcomes;int opened=0,closed=0;for(auto& e:episodes){episode_json.push_back(e.json());if(e.opened)++opened;else ++closed;}if(opened)outcomes["PETTY_RACE_OPENED"]=num(opened);if(closed)outcomes["PETTY_RACE_CLOSED"]=num(closed);
        std::map<S,int> outcome_counts;for(const auto& e:policy_events){episode_json.push_back(obj(e));++outcome_counts[e.at("outcome")];}for(const auto& [outcome,count]:outcome_counts){S key=outcome.substr(1,outcome.size()-2);outcomes[key]=num(count);}
        for(auto& b:batches)batch_json.push_back(b.json());std::map<int,int> round_counts;int max_rounds=0;for(size_t i=0;i<reactions.size();++i){reaction_json.push_back(reactions[i].json(i+1,names));max_rounds=std::max(max_rounds,++round_counts[reactions[i].event]);}V removed;for(auto& r:reorgs){reorg_json.push_back(r.json());removed.push_back(r.removed_count);}
        auto [term,terminal_compact]=terminal(summaries);O raw=metadata;
        raw["status"]=quote(status);raw["error"]=error.empty()?"null":quote(error);raw["events"]=num(events);raw["accepted_blocks"]=num(height);raw["actors"]=obj(actors);raw["member_opportunities"]=counts(opportunities,&opportunity_seen);raw["member_activations"]=counts(activations,&activation_seen);raw["natural_pairs"]=obj(pairs);raw["episodes"]=array(episode_json);raw["selfish_reactions"]=array(reaction_json);std::vector<S> order;for(size_t a=0;a<names.size();++a)if(private_states[a].enabled)order.push_back(quote(names[a]));raw["selfish_actor_order"]=array(order);raw["publication_batches"]=array(batch_json);raw["reorganizations"]=array(reorg_json);raw["terminal"]=obj(term);raw["rng"]=rngs();raw["scripted_discoveries"]=ids(scripted);raw["recording_mode"]=quote("production-v2");
        const S native_json=obj(raw);
        if(!summaries)return {native_json,{}};
        O compact;for(const S& field:{"identity","condition_id","status","events","accepted_blocks","actors","member_opportunities","member_activations","natural_pairs","rng"})compact[field]=raw[field];
        compact["schema"]=quote("persistent-scientific-condition-v2-compact-2");compact["terminal"]=obj(terminal_compact);compact["native_result_sha256"]=quote(sha(native_json));compact["accounting"]=obj({{"discovered",num(events)},{"accepted",num(height)},{"orphaned",num(orphan_total)},{"unresolved",num(hidden_total)}});
        size_t max_decisions=0;for(const auto& r:reactions)max_decisions=std::max(max_decisions,r.decisions.size());
        compact["punishment"]=obj({{"reaction_diagnostics",obj({{"max_simultaneous_decisions",num(max_decisions)},{"max_rounds_in_discovery",num(max_rounds)}})},{"episodes",summary(raw["episodes"],episode_json.size())},{"outcomes",obj(outcomes)},{"selfish_reactions",summary(raw["selfish_reactions"],reactions.size())},{"publication_batches",summary(raw["publication_batches"],batches.size())},{"reorganizations",obj({{"count",num(reorgs.size())},{"sha256",quote(sha(raw["reorganizations"]))},{"removed_depth",range(removed)}})}});
        if(!production){raw.erase("recording_mode");raw["public_events"]=array(public_events);}if(trace)raw["trace"]=array(traces);
        return {production?native_json:obj(raw),obj(compact)};
    }
    Output run(){S status="COMPLETE",error;auto start=std::chrono::steady_clock::now();auto cpu_start=std::clock();
        try{if(has_actions){for(auto& action:actions){if(action.type==0)step(action.actor);else if(action.type==1)discover(action.actor,action.parent,action.withheld,action.kind);else if(action.type==2)publish(action.blocks,action.kind);else throw std::runtime_error("unknown action");}}
            else while(height<horizon&&(stop_after<0||events<stop_after)){if(events>=max_events){status="INCOMPLETE_RESOURCE_LIMIT";break;}step();}}
        catch(const Unsupported& e){status="UNSUPPORTED_STATE";error=e.what();}
        auto emitted=std::chrono::steady_clock::now();auto cpu_emitted=std::clock();auto [raw,compact]=report(status,error);auto end=std::chrono::steady_clock::now();auto cpu_end=std::clock();
        return {std::move(raw),std::move(compact),std::chrono::duration<double>(emitted-start).count(),std::chrono::duration<double>(end-emitted).count(),double(cpu_emitted-cpu_start)/CLOCKS_PER_SEC,double(cpu_end-cpu_emitted)/CLOCKS_PER_SEC};
    }
};

#include "lightweight.hpp"
#include "replay.hpp"

static void validate_input(PyObject* input){
    require(PyDict_Check(input),"dict input required");PyObject* states=field(input,"rng_states");require(PyTuple_Check(states)&&PyTuple_Size(states)==3,"three RNG streams required");
    PyObject* miners=field(input,"miners");require(PyList_Check(miners),"miner list required");for(Py_ssize_t i=0;i<PyList_Size(miners);++i){PyObject* m=PyList_GetItem(miners,i);require(PyTuple_Check(m)&&PyTuple_Size(m)==4,"miner tuple required");}
    require(PyDict_Check(field(input,"metadata")),"metadata required");PyObject* acts=field(input,"actions");if(acts!=Py_None){require(PyList_Check(acts),"action list required");for(Py_ssize_t i=0;i<PyList_Size(acts);++i){PyObject* a=PyList_GetItem(acts,i);require(PyTuple_Check(a)&&PyTuple_Size(a)>=2,"action tuple required");int type=integer(PyTuple_GetItem(a,0));require((type==0&&PyTuple_Size(a)==2)||(type==1&&PyTuple_Size(a)==5)||(type==2&&PyTuple_Size(a)==3),"action shape");}}
}
static LightReference light_reference(PyObject* input){
    LightReference ref;ref.horizon=integer(field(input,"horizon"));
    PyObject* header=field(input,"metadata");require(PyDict_Check(header),"reference metadata required");PyObject *k,*v;Py_ssize_t pos=0;while(PyDict_Next(header,&pos,&k,&v))ref.metadata[text(k)]=text(v);
    Ref miners(PySequence_Fast(field(input,"miners"),"reference miners required"));
    for(Py_ssize_t i=0;i<PySequence_Fast_GET_SIZE(miners.p);++i){PyObject* m=PySequence_Fast_GET_ITEM(miners.p,i);require(PyTuple_Check(m)&&PyTuple_Size(m)==4,"reference miner tuple");ref.names.push_back(text(PyTuple_GetItem(m,0)));ref.roles.push_back(text(PyTuple_GetItem(m,1)));ref.powers.push_back(PyFloat_AsDouble(PyTuple_GetItem(m,2)));}
    return ref;
}
static PyObject* run_kernel(PyObject*,PyObject* input){
    try{
        validate_input(input);Engine engine(input);PathEmission emission;emission.parent=[&](int b){return engine.blocks.at(b).parent;};PathScope scope(emission);
        Output out=engine.run();S raw=emission.expand(out.raw);
        return Py_BuildValue("(y#y#dd)",raw.data(),Py_ssize_t(raw.size()),out.compact.data(),Py_ssize_t(out.compact.size()),out.simulation_seconds,out.emission_seconds);
    }catch(const std::exception& e){if(!PyErr_Occurred())PyErr_SetString(PyExc_ValueError,e.what());return nullptr;}
}
static PyObject* run_checked_kernel(PyObject*,PyObject* input){
    try{
        validate_input(input);Engine engine(input);PathEmission emission;emission.parent=[&](int b){return engine.blocks.at(b).parent;};PathScope scope(emission);
        Output out=engine.run();auto begin=std::chrono::steady_clock::now();auto cpu_begin=std::clock();
        Json parsed=JsonReader(out.raw,true).parse();
        auto risks=check_lightweight(parsed,light_reference(input));
        auto checked=std::chrono::steady_clock::now();auto cpu_checked=std::clock();
        Ref risk_list(PyList_New(risks.size()));for(size_t i=0;i<risks.size();++i)PyList_SET_ITEM(risk_list.p,i,PyUnicode_FromString(risks[i].c_str()));
        PyObject* selector=field(input,"replay_selector");require(PyCallable_Check(selector),"Python replay selector required");
        Ref selected(PyObject_CallOneArg(selector,risk_list.p));require(PyBool_Check(selected.p),"replay selector must return bool");
        bool replay=selected.p==Py_True;double replay_cpu=-1,replay_wall=-1;
        if(replay){auto start=std::chrono::steady_clock::now();auto cpu=std::clock();
            {LedgerReplay reconstruction(parsed,input);reconstruction.validate();}
            replay_cpu=double(std::clock()-cpu)/CLOCKS_PER_SEC;replay_wall=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();}
        PyObject* capture=field(input,"capture_witness");require(PyBool_Check(capture),"witness capture flag");
        S witness=replay&&capture==Py_True?emission.dag(out.raw):S{};
        double validation=std::chrono::duration<double>(checked-begin).count();
        return Py_BuildValue("(y#y#OdddKddddd)",witness.data(),Py_ssize_t(witness.size()),out.compact.data(),Py_ssize_t(out.compact.size()),risk_list.p,out.simulation_seconds,out.emission_seconds,validation,static_cast<unsigned long long>(emission.paths.size()),out.simulation_cpu,out.emission_cpu,double(cpu_checked-cpu_begin)/CLOCKS_PER_SEC,replay_cpu,replay_wall);
    }catch(const std::exception& e){if(!PyErr_Occurred())PyErr_SetString(PyExc_ValueError,e.what());return nullptr;}
}
static PyObject* validate_replay_kernel(PyObject*,PyObject* args){
    const char* bytes;Py_ssize_t size;PyObject* input;
    if(!PyArg_ParseTuple(args,"y#O",&bytes,&size,&input))return nullptr;
    try{validate_input(input);S raw(bytes,size);Json parsed=JsonReader(raw).parse();
        check_lightweight(parsed,light_reference(input));LedgerReplay reconstruction(parsed,input);reconstruction.validate();Py_RETURN_NONE;
    }catch(const std::exception& e){if(!PyErr_Occurred())PyErr_SetString(PyExc_ValueError,e.what());return nullptr;}
}
static PyObject* validate_light_kernel(PyObject*,PyObject* args){
    const char* bytes;Py_ssize_t size;PyObject* reference;
    if(!PyArg_ParseTuple(args,"y#O",&bytes,&size,&reference))return nullptr;
    try{S raw(bytes,size);Json parsed=JsonReader(raw).parse();auto risks=check_lightweight(parsed,light_reference(reference));Ref result(PyList_New(risks.size()));for(size_t i=0;i<risks.size();++i)PyList_SET_ITEM(result.p,i,PyUnicode_FromString(risks[i].c_str()));return Py_NewRef(result.p);}
    catch(const std::exception& e){if(!PyErr_Occurred())PyErr_SetString(PyExc_ValueError,e.what());return nullptr;}
}
static PyObject* rng_test(PyObject*,PyObject* args){PyObject* state;int count;if(!PyArg_ParseTuple(args,"Oi",&state,&count))return nullptr;try{require(count>=0&&count<=100000,"RNG test draw bound");RNG rng(state);Ref values(PyList_New(count));for(int i=0;i<count;++i)PyList_SET_ITEM(values.p,i,PyFloat_FromDouble(rng.random()));Ref final_state(rng.state());return PyTuple_Pack(2,values.p,final_state.p);}catch(const std::exception& e){if(!PyErr_Occurred())PyErr_SetString(PyExc_ValueError,e.what());return nullptr;}}
static PyMethodDef methods[]={{"validate_replay",validate_replay_kernel,METH_VARARGS,"Independent production-ledger replay with no mining calls."},{"run_checked",run_checked_kernel,METH_O,"Native simulation, independent lightweight check, policy-selected DAG witness."},{"validate_lightweight",validate_light_kernel,METH_VARARGS,"Independent native lightweight-ledger-v1 check."},{"run",run_kernel,METH_O,"One diagnostic condition for any supported rule; returns expanded and compact JSON."},{"rng_test",rng_test,METH_VARARGS,"Exact MT state/draw diagnostic only."},{nullptr,nullptr,0,nullptr}};
static PyModuleDef module={PyModuleDef_HEAD_INIT,"_persistent_v2_native","Exact persistent-v2 condition kernel with explicit backend provenance.",-1,methods};
PyMODINIT_FUNC PyInit__persistent_v2_native(){return PyModule_Create(&module);}
