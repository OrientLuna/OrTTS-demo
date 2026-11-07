// Standalone multi-family C ABI probe. Never links OrTavern or mutates model assets.
#include "audiocpp.h"
#include <mach/mach.h>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
static void check(audiocpp_status s) { if(s!=AUDIOCPP_OK) throw std::runtime_error(audiocpp_last_error()); }
static size_t rss() { mach_task_basic_info_data_t info{}; mach_msg_type_number_t n=MACH_TASK_BASIC_INFO_COUNT; return task_info(mach_task_self(),MACH_TASK_BASIC_INFO,(task_info_t)&info,&n)==KERN_SUCCESS?info.resident_size:0; }
static void wav(const std::string& path,const float* p,size_t frames,int rate,int channels) {
 std::ofstream f(path,std::ios::binary); uint32_t bytes=uint32_t(frames*channels*4), total=bytes+36,fmtSize=16,byteRate=rate*channels*4; uint16_t fmt=3,ch=channels,align=channels*4,bits=32;
 auto put=[&](auto& x){f.write((char*)&x,sizeof(x));}; f.write("RIFF",4);put(total);f.write("WAVEfmt ",8);put(fmtSize);put(fmt);put(ch);put(rate);put(byteRate);put(align);put(bits);f.write("data",4);put(bytes);f.write((char*)p,bytes); if(!f)throw std::runtime_error("WAV write failed");
}
struct Handles {
 audiocpp_model* model=nullptr; audiocpp_session* session=nullptr; audiocpp_request* request=nullptr; audiocpp_result* result=nullptr;
 ~Handles(){audiocpp_result_free(result);audiocpp_request_free(request);audiocpp_session_free(session);audiocpp_model_free(model);}
};
int main(int argc,char**argv) {
 if(argc!=3 && argc!=4){std::cerr<<"probe ASSET_ROOT OUTPUT_DIR [CYCLES]\n";return 2;}
 int cycles=argc==4?std::stoi(argv[3]):2;if(cycles<1||cycles>10)return 2;
 std::string root=argv[1],out=argv[2];std::filesystem::create_directories(out); audiocpp_registry* registry=nullptr;
 try {
 check(audiocpp_registry_create(nullptr,&registry));
 std::cout<<"{\"registry_families\":"<<audiocpp_registry_family_count(registry)<<",\"observations\":[\n";bool comma=false;
 for(int cycle=0;cycle<cycles;cycle++) for(const std::string family:{"piper_tts","kokoro_tts","sense_asr"}) {
 size_t before=rss();
 { Handles h; std::string file=family=="piper_tts"?"Piper-TTS-GGUF/piper-en-us-lessac-medium-orig.gguf":family=="kokoro_tts"?"Kokoro-82M-GGUF/kokoro-82m-q8_0.gguf":"sensevoice-small-q8-audiocpp-v1.gguf";
 audiocpp_model_config config{family.c_str(),nullptr,nullptr,nullptr};check(audiocpp_model_load(registry,(root+"/"+file).c_str(),&config,nullptr,&h.model));
 audiocpp_backend_config backend{"cpu",0,4};check(audiocpp_session_create(h.model,family=="sense_asr"?"asr":"tts","offline",&backend,nullptr,&h.session));
 for(int repeat=0;repeat<2;repeat++) {
 h.request=audiocpp_request_create();if(!h.request)throw std::runtime_error("request allocation");
 if(family=="sense_asr") {
  std::ifstream f(out+"/reference-zh.f32",std::ios::binary|std::ios::ate);if(!f)throw std::runtime_error("missing reference-zh.f32");size_t bytes=f.tellg();f.seekg(0);std::vector<float>a(bytes/4);f.read((char*)a.data(),bytes);check(audiocpp_request_set_audio(h.request,a.data(),a.size(),16000,1));check(audiocpp_request_set_option(h.request,"audio_chunk_mode","none"));
 } else {
  check(audiocpp_request_set_text(h.request,"At nine thirty, please check the train ticket and call the station.","en-us"));
  if(family=="kokoro_tts")check(audiocpp_request_set_option(h.request,"voice_id","af_heart"));
 }
 auto begin=std::chrono::steady_clock::now();check(audiocpp_session_run(h.session,h.request,&h.result)); double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
 if(comma)std::cout<<",\n";comma=true;std::cout<<"{\"family\":\""<<family<<"\",\"cycle\":"<<cycle<<",\"repeat\":"<<repeat<<",\"run_ms\":"<<ms<<",\"rss_before\":"<<before<<",\"rss_after_run\":"<<rss();
 if(family=="sense_asr") {const char*text=nullptr;const char*language=nullptr;check(audiocpp_result_text(h.result,&text,&language));std::ofstream(out+"/cabi-asr.txt")<<(text?text:"");}
 else {const float*p=nullptr;size_t frames=0;int rate=0,ch=0;check(audiocpp_result_audio(h.result,&p,&frames,&rate,&ch));if(!p||!frames||ch!=1||(rate!=22050&&rate!=24000))throw std::runtime_error("invalid PCM metadata");for(size_t i=0;i<frames*ch;i++)if(!std::isfinite(p[i]))throw std::runtime_error("nonfinite PCM");wav(out+"/cabi-"+family+".wav",p,frames,rate,ch);std::cout<<",\"frames\":"<<frames<<",\"sample_rate\":"<<rate<<",\"channels\":"<<ch;}
 std::cout<<"}"<<std::flush;audiocpp_result_free(h.result);h.result=nullptr;audiocpp_request_free(h.request);h.request=nullptr;
 }
 }
 std::cerr<<family<<" cycle="<<cycle<<" rss_after_free="<<rss()<<"\n";
 }
 std::cout<<"\n]}\n";audiocpp_registry_free(registry);return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";audiocpp_registry_free(registry);return 1;}
}
