// OrTTS CPU offline entry point. Model assets and speaker vectors are external.
#include "audiocpp.h"
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>
namespace fs=std::filesystem;
void check(audiocpp_status s){if(s!=AUDIOCPP_OK)throw std::runtime_error(audiocpp_last_error());}
void u32(std::ostream&f,uint32_t x){for(int i=0;i<4;++i)f.put(char((x>>(8*i))&255));}
void u16(std::ostream&f,uint16_t x){f.put(char(x&255));f.put(char(x>>8));}
void save(const fs::path&p,const float*x,size_t n,int rate){
 if(n>(UINT32_MAX-36)/4)throw std::runtime_error("WAV exceeds RIFF limit");
 std::ofstream f(p,std::ios::binary);f.write("RIFF",4);u32(f,uint32_t(36+n*4));f.write("WAVEfmt ",8);u32(f,16);u16(f,3);u16(f,1);u32(f,rate);u32(f,rate*4);u16(f,4);u16(f,32);f.write("data",4);u32(f,uint32_t(n*4));f.write(reinterpret_cast<const char*>(x),n*4);if(!f)throw std::runtime_error("WAV write failed");
}
struct Handles{
 audiocpp_registry*r=nullptr;audiocpp_model*m=nullptr;audiocpp_options*o=nullptr;audiocpp_session*s=nullptr;
 ~Handles(){if(s)audiocpp_session_free(s);if(o)audiocpp_options_free(o);if(m)audiocpp_model_free(m);if(r)audiocpp_registry_free(r);}
};
int main(int argc,char**argv){try{
 if(argc==2&&std::string(argv[1])=="--help"){
  std::cout<<"Use tools/run.py --assets-manifest MANIFEST --binary ortts-tts --text TEXT --out NEW_DIRECTORY\nCPU offline whole-sentence; no automatic downloads or device access.\n";return 0;
 }
 std::map<std::string,std::string>a;for(int i=1;i<argc;i+=2){if(i+1>=argc||!a.emplace(argv[i],argv[i+1]).second)throw std::runtime_error("invalid/duplicate option");}
 for(auto k:{"--model","--bridge","--decoder","--base-decoder","--vocoder","--speaker","--manifest-sha","--text","--out","--threads","--seed","--repeats","--max-tokens"})if(!a.count(k))throw std::runtime_error(std::string("missing ")+k);
 int threads=std::stoi(a.at("--threads")),repeats=std::stoi(a.at("--repeats")),max_tokens=std::stoi(a.at("--max-tokens"));if(threads<1||threads>8||repeats<1||repeats>3||max_tokens<1||max_tokens>513)throw std::runtime_error("threads/repeats/max-tokens out of supported range");
 if(a.at("--text").empty()||a.at("--manifest-sha").size()!=64)throw std::runtime_error("empty text/manifest identity");
 fs::path out=a.at("--out");if(fs::exists(out)||!fs::create_directories(out))throw std::runtime_error("output must be a fresh directory");
 // Keep the validated CPU lineage; do not inherit experiment overrides.
 for(auto k:{"ORTTS_GROUPED_PREDICTOR_GGUF","ORTTS_GROUPED_PREDICTOR_PACKED","ORTTS_P3_PREDICTOR_SOURCE","ORTTS_PRIVATE_NATIVE_BODY_Q4","ORTTS_PREDICTOR_CPU_REPACK","ORTTS_B0_DISABLE_REPACK"})unsetenv(k);
 if(a.count("--p3-source"))setenv("ORTTS_P3_PREDICTOR_SOURCE",a.at("--p3-source").c_str(),1);
 setenv("ORTTS_NATIVE_PREDICTOR_PACKED","0",1);setenv("ORTTS_CPU_PERSISTENT_POOL","0",1);setenv("ORTTS_CPU_TCONV_GEMM","1",1);setenv("ORTTS_FFN_PUREC_M1","0",1);setenv("ORTTS_PRIVATE_FAST_BACKEND","cpu",1);setenv("ORTTS_PRIVATE_BASE_DETOK_GGUF",a.at("--base-decoder").c_str(),1);setenv("ORTTS_PRIVATE_BRIDGE_MANIFEST_SHA256",a.at("--manifest-sha").c_str(),1);setenv("ORTTS_EXPORT_GENERATED_CODES_DIR",out.c_str(),1);
 fs::create_directory(out/"tmp");setenv("TMPDIR",(out/"tmp").c_str(),1);check(audiocpp_ortts_trace_file((out/"trace.log").c_str()));
 const auto load_start=std::chrono::steady_clock::now();Handles h;check(audiocpp_registry_create(nullptr,&h.r));audiocpp_model_config mc{"qwen3_tts",nullptr,nullptr,nullptr};check(audiocpp_model_load(h.r,a.at("--model").c_str(),&mc,nullptr,&h.m));h.o=audiocpp_options_create();if(!h.o)throw std::runtime_error("options allocation failed");
 auto option=[&](const char*k,const std::string&v){check(audiocpp_options_set(h.o,k,v.c_str()));};
 option("qwen3_tts.fixed_speaker_f32",a.at("--speaker"));option("qwen3_tts.lfm_b0_bundle",a.at("--bridge"));option("qwen3_tts.lfm_b0_detokenizer_gguf",a.at("--decoder"));option("qwen3_tts.lfm_b0_vocoder_gguf",a.at("--vocoder"));
 for(auto p:{std::pair{"qwen3_tts.perf_mode","off"},{"qwen3_tts.packed_projections","false"},{"qwen3_tts.conv_weight_type","f32"},{"qwen3_tts.speech_decoder_conv_weight_type","f16"},{"qwen3_tts.codec_pipeline","false"},{"qwen3_tts.cpu_chunk_frames","0"},{"qwen3_tts.stitch_decode","false"}})option(p.first,p.second);
 audiocpp_backend_config bc{"cpu",0,threads};check(audiocpp_session_create(h.m,"tts","offline",&bc,h.o,&h.s));double setup_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-load_start).count();std::ofstream metrics(out/"metrics.jsonl");
 for(int i=0;i<repeats;++i){
  struct Request{audiocpp_request*p=audiocpp_request_create();~Request(){if(p)audiocpp_request_free(p);}}q;
  check(audiocpp_request_set_text(q.p,a.at("--text").c_str(),nullptr));
  for(auto p:{std::pair{"x_vector_only_mode","true"},{"language","Chinese"},{"do_sample","true"},{"temperature","0.9"},{"top_k","50"},{"top_p","0.9"},{"repetition_penalty","1.05"},{"subtalker_do_sample","false"}})check(audiocpp_request_set_option(q.p,p.first,p.second));check(audiocpp_request_set_option(q.p,"seed",a.at("--seed").c_str()));check(audiocpp_request_set_option(q.p,"max_tokens",a.at("--max-tokens").c_str()));
  const auto start=std::chrono::steady_clock::now();struct Result{audiocpp_result*p=nullptr;~Result(){if(p)audiocpp_result_free(p);}}y;check(audiocpp_session_run(h.s,q.p,&y.p));double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();const float*pcm=nullptr;size_t n=0;int rate=0,ch=0;check(audiocpp_result_audio(y.p,&pcm,&n,&rate,&ch));if(!n||rate!=24000||ch!=1)throw std::runtime_error("unexpected audio schema");for(size_t j=0;j<n;++j)if(!std::isfinite(pcm[j]))throw std::runtime_error("nonfinite PCM");
  save(out/("request-"+std::to_string(i)+".wav"),pcm,n,rate);std::ofstream raw(out/("request-"+std::to_string(i)+".f32"),std::ios::binary);raw.write(reinterpret_cast<const char*>(pcm),n*4);if(!raw)throw std::runtime_error("PCM write failed");
  std::ifstream trace(out/"trace.log");std::string log((std::istreambuf_iterator<char>(trace)),{}),eos="UNKNOWN";const auto pos=log.rfind("observed_stop_reason ");if(pos!=std::string::npos){auto v=log.substr(pos+21);if(v.rfind("eos",0)==0)eos="eos";else eos="NON_EOS";}
  std::string row="{\"repeat\":"+std::to_string(i)+",\"setup_ms\":"+std::to_string(setup_ms)+",\"api_ms\":"+std::to_string(ms)+",\"samples\":"+std::to_string(n)+",\"audio_s\":"+std::to_string(double(n)/rate)+",\"RTF\":"+std::to_string(ms/1000/(double(n)/rate))+",\"threads\":"+std::to_string(threads)+",\"backend\":\"CPU\",\"mode\":\"offline_whole_sentence\",\"first_pcm_ms\":null,\"EOS\":\""+eos+"\"}";metrics<<row<<std::endl;std::cout<<row<<std::endl;if(eos!="eos")return 2;
 }
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}return 0;}
