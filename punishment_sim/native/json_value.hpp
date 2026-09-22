// Small internal JSON reader for independently validating the emitted witness.
// Internal path tokens remain endpoint descriptors; ordinary external JSON is
// parsed without them. Numbers retain their exact lexical identity for hashes.
#include <cstdlib>
#include <limits>
#include <cstdio>
#include <variant>

struct Json {
    enum Type {Null,Bool,Integer,Float,String,Array,Object,Path} type=Null;
    using Items=std::vector<Json>;
    using Fields=std::vector<std::pair<S,Json>>;
    std::variant<S,Items,Fields,PathDescriptor> data;
    const S& value()const{return std::get<S>(data);}
    S& value(){return std::get<S>(data);}
    const Items& array()const{return std::get<Items>(data);}
    Items& array(){return std::get<Items>(data);}
    const Fields& object()const{return std::get<Fields>(data);}
    Fields& object(){return std::get<Fields>(data);}
    const PathDescriptor& path()const{return std::get<PathDescriptor>(data);}
    auto find(const S& key)const{return std::lower_bound(object().begin(),object().end(),key,[](const auto& field,const S& name){return field.first<name;});}
    const Json& at(const S& key)const {
        require(type==Object,"ledger object required");auto position=find(key);if(position==object().end()||position->first!=key)require(false,"missing ledger field: "+key);return position->second;
    }
    const Json& at(size_t index)const {require(type==Array&&index<array().size(),"ledger array index");return array()[index];}
    bool has(const S& key)const{if(type!=Object)return false;auto position=find(key);return position!=object().end()&&position->first==key;}
    bool null()const{return type==Null;}
    bool integer()const{return type==Integer;}
    bool boolean()const{return type==Bool;}
    double number()const {
        require(type==Integer||type==Float||type==Bool,"ledger number required");
        return type==Bool?(value()=="true"?1:0):std::strtod(value().c_str(),nullptr);
    }
    long long whole()const {double x=number();require(std::isfinite(x)&&x>=-9007199254740991.0&&x<=9007199254740991.0&&std::floor(x)==x,"ledger integer-valued field");return static_cast<long long>(x);}
    bool truth()const {return type==Null?false:type==Bool?value()=="true":type==Integer||type==Float?number()!=0:type==Array?!array().empty():type==Object?!object().empty():!value().empty();}
    size_t size()const {require(type==Array||type==Object,"ledger collection required");return type==Array?array().size():object().size();}
    size_t python_length()const {if(type!=String)return size();size_t n=0;for(unsigned char c:value())if((c&0xc0)!=0x80)++n;return n;}
    S numeric_key()const {
        if(type==Bool)return value()=="true"?"1":"0";
        if(type==Integer)return value()=="-0"?"0":value();
        require(type==Float,"numeric equality type");double x=number();
        if(std::floor(x)==x){char buffer[400];std::snprintf(buffer,sizeof(buffer),"%.0f",x==0?0:x);return buffer;}
        return value();
    }
    S hashable_key()const {require(type!=Array&&type!=Object&&type!=Path,"unhashable reaction event");return type==Integer||type==Float||type==Bool?"number:"+numeric_key():dump();}
    S str()const {require(type==String,"ledger string required");return value();}
    S dump()const {
        if(type==Null)return "null";if(type==String)return quote(value());
        if(type==Array){std::vector<S> values;for(const auto& v:array())values.push_back(v.dump());return ::array(values);}
        if(type==Object){O fields;for(const auto& [k,v]:object())fields[k]=v.dump();return obj(fields);}
        require(type!=Path,"cannot serialize internal path as ordinary JSON");return value();
    }
};

class JsonReader {
    const S& input;size_t cursor=0;bool paths;
    void whitespace(){while(cursor<input.size()&&(input[cursor]==' '||input[cursor]=='\n'||input[cursor]=='\r'||input[cursor]=='\t'))++cursor;}
    char take(){require(cursor<input.size(),"truncated ledger JSON");return input[cursor++];}
    unsigned hex(){unsigned result=0;for(int i=0;i<4;++i){char c=take();require((c>='0'&&c<='9')||(c>='a'&&c<='f')||(c>='A'&&c<='F'),"invalid JSON unicode");result=result*16+(c<='9'?c-'0':c<='F'?c-'A'+10:c-'a'+10);}return result;}
    static void unicode(S& s,unsigned code){
        if(code<128)s+=char(code);
        else if(code<2048){s+=char(0xc0|(code>>6));s+=char(0x80|(code&63));}
        else if(code<65536){s+=char(0xe0|(code>>12));s+=char(0x80|((code>>6)&63));s+=char(0x80|(code&63));}
        else{s+=char(0xf0|(code>>18));s+=char(0x80|((code>>12)&63));s+=char(0x80|((code>>6)&63));s+=char(0x80|(code&63));}
    }
    S string(){require(take()=='"',"JSON string expected");S result;
        for(;;){unsigned char c=take();if(c=='"')break;require(c>=32,"unescaped JSON control character");
            if(c!='\\'){result+=char(c);continue;}c=take();
            if(c=='"'||c=='\\'||c=='/')result+=char(c);else if(c=='b')result+='\b';else if(c=='f')result+='\f';else if(c=='n')result+='\n';else if(c=='r')result+='\r';else if(c=='t')result+='\t';
            else if(c=='u'){unsigned code=hex();if(code>=0xd800&&code<=0xdbff){if(input.compare(cursor,2,"\\u")==0){size_t saved=cursor;cursor+=2;unsigned low=hex();if(low>=0xdc00&&low<=0xdfff)code=0x10000+((code-0xd800)<<10)+(low-0xdc00);else cursor=saved;}}unicode(result,code);}else require(false,"invalid JSON escape");
        }return result;
    }
    Json read(int depth){require(depth<1024,"ledger JSON nesting limit");whitespace();require(cursor<input.size(),"empty ledger JSON");char c=input[cursor];Json out;
        if(c=='\x1e'){require(paths&&path_emission,"external path token forbidden");++cursor;size_t end=input.find('\x1f',cursor);require(end!=S::npos,"path token end");size_t i=std::stoull(input.substr(cursor,end-cursor));require(i<path_emission->paths.size(),"path token index");out.type=Json::Path;out.data=path_emission->paths[i];cursor=end+1;return out;}
        if(c=='"'){out.type=Json::String;out.value()=string();return out;}
        if(c=='['||c=='{'){++cursor;out.type=c=='['?Json::Array:Json::Object;if(c=='[')out.data=Json::Items{};else out.data=Json::Fields{};char closing=c=='['?']':'}';whitespace();if(cursor<input.size()&&input[cursor]==closing){++cursor;return out;}
            for(;;){whitespace();if(c=='[')out.array().push_back(read(depth+1));else{S key=string();whitespace();require(take()==':',"JSON object colon");if(out.object().empty()||out.object().back().first<key)out.object().emplace_back(std::move(key),read(depth+1));else{auto position=out.find(key);require(position==out.object().end()||position->first!=key,"duplicate JSON key");out.object().emplace(position,std::move(key),read(depth+1));}}whitespace();char separator=take();if(separator==closing)break;require(separator==',',"JSON collection delimiter");}return out;
        }
        for(const S& literal:{"null","true","false"})if(input.compare(cursor,literal.size(),literal)==0){cursor+=literal.size();out.type=literal=="null"?Json::Null:Json::Bool;out.value()=literal;return out;}
        size_t start=cursor;if(c=='-')++cursor;require(cursor<input.size()&&input[cursor]>='0'&&input[cursor]<='9',"JSON number expected");if(input[cursor]=='0')++cursor;else while(cursor<input.size()&&input[cursor]>='0'&&input[cursor]<='9')++cursor;
        out.type=Json::Integer;
        if(cursor<input.size()&&input[cursor]=='.'){out.type=Json::Float;++cursor;size_t begin=cursor;while(cursor<input.size()&&input[cursor]>='0'&&input[cursor]<='9')++cursor;require(cursor>begin,"JSON fraction digits");}
        if(cursor<input.size()&&(input[cursor]=='e'||input[cursor]=='E')){out.type=Json::Float;++cursor;if(cursor<input.size()&&(input[cursor]=='+'||input[cursor]=='-'))++cursor;size_t begin=cursor;while(cursor<input.size()&&input[cursor]>='0'&&input[cursor]<='9')++cursor;require(cursor>begin,"JSON exponent digits");}
        out.value()=input.substr(start,cursor-start);if(out.type==Json::Float)require(std::isfinite(out.number()),"nonfinite ledger JSON");return out;
    }
public:
    explicit JsonReader(const S& input,bool paths=false):input(input),paths(paths){}
    Json parse(){Json value=read(0);whitespace();require(cursor==input.size(),"trailing ledger JSON");return value;}
};
