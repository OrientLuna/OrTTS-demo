#include "ortts_speech.h"
#include <algorithm>
#include <chrono>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
struct Result{std::string text;size_t partial=0,final=0;};
static int event(void*u,const ortts_asr_stream_event*e){auto&r=*static_cast<Result*>(u);if(e->endpoint){if(!r.text.empty())r.text+=' ';r.text+=e->text;++r.final;}else ++r.partial;return 0;}
static void check(ortts_status s){if(s!=ORTTS_OK)throw std::runtime_error(ortts_last_error());}
static std::string quoted(const std::string&s){std::string r="\"";for(unsigned char c:s){if(c=='"'||c=='\\')r+='\\';if(c<32){const char*h="0123456789abcdef";r+="\\u00";r+=h[c>>4];r+=h[c&15];}else r+=char(c);}return r+'"';}
int main(int argc,char**argv){ortts_asr_stream*engine=nullptr;try{
 if(argc!=4)throw std::runtime_error("model-root input-list output-dir");ortts_speech_config c{};c.struct_size=sizeof(c);c.family="zipformer_bilingual";c.model_path=argv[1];c.threads=2;c.streaming=1;ortts_asr_stream_config v{sizeof(v),400,1000,15000,0,.003F};check(ortts_asr_stream_create(&c,&v,&engine));
 std::ifstream list(argv[2]);std::string line;while(std::getline(list,line)){auto tab=line.find('\t');if(tab==std::string::npos)throw std::runtime_error("invalid list");auto id=line.substr(0,tab),path=line.substr(tab+1);if(id.empty()||id.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")!=std::string::npos)throw std::runtime_error("invalid fixture id");std::ifstream in(path,std::ios::binary|std::ios::ate);if(!in)throw std::runtime_error("missing input");auto bytes=in.tellg();if(bytes<=0||bytes%4||bytes>16000*120*4)throw std::runtime_error("invalid PCM size");in.seekg(0);std::vector<float>pcm(size_t(bytes)/4);in.read(reinterpret_cast<char*>(pcm.data()),bytes);check(ortts_asr_stream_reset(engine));Result r;auto start=std::chrono::steady_clock::now();for(size_t off=0;off<pcm.size();off+=3200)check(ortts_asr_stream_accept(engine,pcm.data()+off,std::min(size_t(3200),pcm.size()-off),event,&r));check(ortts_asr_stream_finish(engine,event,&r));double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();std::ofstream out(std::string(argv[3])+"/"+id+".json");out<<"{\"hypothesis\":"<<quoted(r.text)<<",\"native_api_ms\":"<<ms<<",\"audio_s\":"<<pcm.size()/16000.<<",\"partials\":"<<r.partial<<",\"finals\":"<<r.final<<"}\n";std::cout<<id<<" done\n";}
 ortts_asr_stream_free(engine);return 0;
 }catch(const std::exception&e){if(engine)ortts_asr_stream_free(engine);std::cerr<<e.what()<<"\n";return 1;}}
