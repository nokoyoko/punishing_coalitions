// Representation-only path compression. Expanded canonical bytes are unchanged.
// A path is an endpoint pair into the immutable discovery tree, not a stored
// vector per terminal leaf or per reorganization. Memory is O(tree + endpoints).
#include <functional>
#include <string_view>

struct PathDescriptor {int tip,ancestor;bool ascending;};
struct PathEmission {
    std::function<int(int)> parent;
    std::vector<PathDescriptor> paths;
    S defer(int tip,int ancestor,bool ascending=true) {
        paths.push_back({tip,ancestor,ascending});
        return S(1,'\x1e')+num(paths.size()-1)+S(1,'\x1f');
    }
    template<class Consumer> void emit(const S& input,Consumer consume)const {
        size_t position=0;
        while(position<input.size()) {
            size_t token=input.find('\x1e',position);
            if(token==S::npos){consume(input.data()+position,input.size()-position);break;}
            consume(input.data()+position,token-position);
            size_t end=input.find('\x1f',token+1);require(end!=S::npos,"unfinished path token");
            size_t index=std::stoull(input.substr(token+1,end-token-1));
            require(index<paths.size(),"unknown path token");const auto& path=paths[index];
            S buffer="[";buffer.reserve(65568);bool first=true;
            auto element=[&](int b){if(!first)buffer+=',';first=false;buffer+=num(b);
                if(buffer.size()>=65536){consume(buffer.data(),buffer.size());buffer.clear();}};
            if(path.ascending) {
                V scratch;
                for(int b=path.tip;b!=path.ancestor;b=parent(b)){require(b>0,"path ancestor missing");scratch.push_back(b);}
                for(auto it=scratch.rbegin();it!=scratch.rend();++it)element(*it);
            } else {
                for(int b=path.tip;b!=path.ancestor;b=parent(b)){require(b>0,"path ancestor missing");element(b);}
            }
            buffer+=']';consume(buffer.data(),buffer.size());position=end+1;
        }
    }
    S expand(const S& input)const {
        S result;emit(input,[&](const char* p,size_t n){result.append(p,n);});return result;
    }
    S dag(const S& input)const {
        S result;size_t position=0;
        while(position<input.size()){
            size_t token=input.find('\x1e',position);
            if(token==S::npos){result.append(input,position,S::npos);break;}
            result.append(input,position,token-position);size_t end=input.find('\x1f',token+1);
            require(end!=S::npos,"unfinished DAG path token");size_t index=std::stoull(input.substr(token+1,end-token-1));require(index<paths.size(),"unknown DAG path token");
            const auto& p=paths[index];result+="{\"__path__\":["+num(p.tip)+','+num(p.ancestor)+','+boolean(p.ascending)+"]}";position=end+1;
        }return result;
    }
};
static thread_local PathEmission* path_emission=nullptr;
struct PathScope {
    PathEmission* previous;
    explicit PathScope(PathEmission& current):previous(path_emission){path_emission=&current;}
    ~PathScope(){path_emission=previous;}
};
