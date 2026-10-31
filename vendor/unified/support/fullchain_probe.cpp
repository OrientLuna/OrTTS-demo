extern "C" unsigned long long ortts_lc_worker_peak_rss_kib();
#include "audiocpp.h"
#include <chrono>
#include <sys/resource.h>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <cmath>
#include <stdexcept>
using Clock=std::chrono::steady_clock;
static double elapsed(Clock::time_point t){return std::chrono::duration<double,std::milli>(Clock::now()-t).count();}
void check(audiocpp_status s){if(s!=AUDIOCPP_OK)throw std::runtime_error(audiocpp_last_error());}
struct Chunk{double arrival_ms;size_t samples;};
struct Capture{Clock::time_point start;std::vector<float>pcm;std::vector<Chunk>chunks;bool bad=false;};
int callback(const audiocpp_event*e,void*ptr){auto&c=*static_cast<Capture*>(ptr);try{
 const float*pcm=nullptr;size_t n=0;int sr=0,ch=0;check(audiocpp_result_audio(audiocpp_event_as_result(e),&pcm,&n,&sr,&ch));if(!n)return 0;
 double t=elapsed(c.start);if(!pcm||sr!=24000||ch!=1)throw std::runtime_error("callback audio schema");for(size_t j=0;j<n;++j)if(!std::isfinite(pcm[j]))throw std::runtime_error("callback nonfinite");c.chunks.push_back({t,n});c.pcm.insert(c.pcm.end(),pcm,pcm+n);return 0;
}catch(...){c.bad=true;return 1;}}
int main(int argc,char**argv){try{
 if(argc!=10)throw std::runtime_error("assets offline|streaming text new-output repeats P3-source-or-dash b260k|qwen");std::string root=argv[1],mode=argv[2],out=argv[4];bool use_b260=true;if(std::string(argv[7])!="b260k"&&std::string(argv[7])!="base100k"&&std::string(argv[7])!="expanded120k")throw std::runtime_error("decoder selector");if(std::string(argv[7])=="b260k")unsetenv("ORTTS_LC_VARIANT");else setenv("ORTTS_LC_VARIANT",argv[7],1);fprintf(stderr,"ORTTS_GGML_RUNTIME=unified-0.28.0 LC_TRANSPORT=inprocess\n");bool streaming=mode=="streaming";if(!streaming&&mode!="offline")throw std::runtime_error("mode");if(streaming&&!use_b260)throw std::runtime_error("original Qwen fixedvoice control is offline only");int repeats=std::stoi(argv[5]);if(repeats<1||repeats>2)throw std::runtime_error("repeats");
 for(auto k:{"ORTTS_GROUPED_PREDICTOR_GGUF","ORTTS_GROUPED_PREDICTOR_PACKED","ORTTS_P3_PREDICTOR_SOURCE","ORTTS_PRIVATE_NATIVE_BODY_Q4","ORTTS_PREDICTOR_CPU_REPACK","ORTTS_B0_STREAM_PREFIX_REFERENCE","ORTTS_B0_DISABLE_REPACK"})unsetenv(k);
 if(std::string(argv[6])!="-")setenv("ORTTS_P3_PREDICTOR_SOURCE",argv[6],1);
 setenv("ORTTS_FFN_PUREC_M1","0",1);setenv("ORTTS_NATIVE_PREDICTOR_PACKED","0",1);setenv("ORTTS_CPU_PERSISTENT_POOL","0",1);setenv("ORTTS_CPU_TCONV_GEMM","1",1);setenv("ORTTS_PRIVATE_FAST_BACKEND","cpu",1);setenv("ORTTS_PRIVATE_BASE_DETOK_GGUF",(root+"/tokenizer-LFM2.5-Audio-1.5B-Q4_0.gguf").c_str(),1);setenv("ORTTS_PRIVATE_BRIDGE_MANIFEST_SHA256",(getenv("ORTTS_CONTROL_MANIFEST_SHA")?getenv("ORTTS_CONTROL_MANIFEST_SHA"):"5d3b9989748de248667ed9ca5e878b612082554abaed46fff37d6217f55c6b00"),1);setenv("ORTTS_EXPORT_GENERATED_CODES_DIR",out.c_str(),1);check(audiocpp_ortts_trace_file((out+"/trace.log").c_str()));
 auto load_start=Clock::now();audiocpp_registry*r=nullptr;audiocpp_model*m=nullptr;audiocpp_session*s=nullptr;check(audiocpp_registry_create(nullptr,&r));audiocpp_model_config mc{"qwen3_tts",nullptr,nullptr,nullptr};check(audiocpp_model_load(r,(root+"/model.gguf").c_str(),&mc,nullptr,&m));auto*o=audiocpp_options_create();auto set=[&](const char*k,std::string v){check(audiocpp_options_set(o,k,v.c_str()));};set("qwen3_tts.fixed_speaker_f32",root+"/voices/"+argv[8]+".f32");if(use_b260){set("qwen3_tts.lfm_b0_bundle",root+"/bridge");set("qwen3_tts.lfm_b0_detokenizer_gguf",root+"/tokenizer-control.gguf");set("qwen3_tts.lfm_b0_vocoder_gguf",root+"/vocoder-LFM2.5-Audio-1.5B-Q4_0.gguf");}
 for(auto p:{std::pair{"qwen3_tts.perf_mode","off"},{"qwen3_tts.packed_projections","false"},{"qwen3_tts.conv_weight_type","f32"},{"qwen3_tts.speech_decoder_conv_weight_type","f16"},{"qwen3_tts.codec_pipeline","false"},{"qwen3_tts.cpu_chunk_frames","0"},{"qwen3_tts.stitch_decode","false"}})set(p.first,p.second);
 audiocpp_backend_config bc{"cpu",0,4};check(audiocpp_session_create(m,"tts",mode.c_str(),&bc,o,&s));double setup_ms=elapsed(load_start);
 std::vector<std::string>texts;
 if(argv[3][0]=='@'){std::ifstream f(argv[3]+1);std::string line;while(std::getline(f,line))if(!line.empty())texts.push_back(line);if(texts.size()!=3)throw std::runtime_error("expected short/mid/long panel");texts.insert(texts.begin(),texts.front());}
 else for(int i=0;i<repeats;i++)texts.emplace_back(argv[3]);
 for(int i=0;i<int(texts.size());++i){
  auto*q=audiocpp_request_create();check(audiocpp_request_set_text(q,texts[i].c_str(),nullptr));
  for(auto p:{std::pair{"x_vector_only_mode","true"},{"language","Chinese"},{"seed","20261029"},{"max_tokens","513"},{"do_sample","true"},{"temperature","0.9"},{"top_k","50"},{"top_p","0.9"},{"repetition_penalty","1.05"},{"subtalker_do_sample","false"}})check(audiocpp_request_set_option(q,p.first,p.second));
  if(streaming){check(audiocpp_request_set_option(q,"stream_frames_per_event","3"));check(audiocpp_request_set_option(q,"stream_chunk_policy","fixed"));}
  Capture c;c.start=Clock::now();audiocpp_result*y=nullptr;double start_return_ms=0;
  if(streaming){check(audiocpp_stream_set_callback(s,callback,&c));check(audiocpp_stream_start(s,q));start_return_ms=elapsed(c.start);check(audiocpp_stream_set_callback(s,nullptr,nullptr));check(audiocpp_stream_finish(s,&y));}else check(audiocpp_session_run(s,q,&y));double wall_ms=elapsed(c.start);
  const float*pcm=nullptr;size_t n=0;int sr=0,ch=0;check(audiocpp_result_audio(y,&pcm,&n,&sr,&ch));if(!n||sr!=24000||ch!=1)throw std::runtime_error("output audio schema");for(size_t j=0;j<n;++j)if(!std::isfinite(pcm[j]))throw std::runtime_error("output nonfinite");
  if(streaming){if(c.bad||c.chunks.size()<2||c.pcm.size()!=n||c.chunks.front().arrival_ms>=start_return_ms)throw std::runtime_error("not actual incremental PCM or callback schema");for(size_t j=0;j<n;++j)if(c.pcm[j]!=pcm[j])throw std::runtime_error("callback vs finalPCM mismatch");}
  std::ofstream f(out+"/pcm-"+std::to_string(i)+".f32",std::ios::binary);f.write((const char*)pcm,n*4);if(!f)throw std::runtime_error("write PCM");
  std::ofstream chunks(out+"/chunks-"+std::to_string(i)+".jsonl");size_t accumulated=0;for(const auto&v:c.chunks){accumulated+=v.samples;chunks<<"{\"arrival_ms\":"<<v.arrival_ms<<",\"samples\":"<<v.samples<<",\"cumulative_samples\":"<<accumulated<<"}"<<std::endl;}
  struct rusage usage{};getrusage(RUSAGE_SELF,&usage);
  std::cout<<"{\"worker_peak_RSS_KiB\":"<<ortts_lc_worker_peak_rss_kib()<<",\"peak_RSS_KiB\":"<<usage.ru_maxrss<<",\"mode\":\""<<mode<<"\",\"repeat\":"<<i<<",\"setup_ms\":"<<setup_ms<<",\"api_ms\":"<<wall_ms<<",\"samples\":"<<n<<",\"sample_rate\":"<<sr<<",\"RTF\":"<<wall_ms/1000/(double(n)/sr)<<",\"callbacks\":"<<c.chunks.size()<<",\"first_pcm_ms\":"<<(streaming?std::to_string(c.chunks.front().arrival_ms):"null")<<",\"stream_start_return_ms\":"<<(streaming?std::to_string(start_return_ms):"null")<<",\"callback_concat_equals_result\":"<<(streaming?"true":"null")<<"}"<<std::endl;
  audiocpp_result_free(y);audiocpp_request_free(q);std::ifstream trace(out+"/trace.log");std::stringstream z;z<<trace.rdbuf();auto log=z.str();auto pos=log.rfind("observed_stop_reason ");if(pos==std::string::npos||log.substr(pos,40).find("eos")==std::string::npos)throw std::runtime_error("EOS gate failed; no retry");
 }
 audiocpp_session_free(s);audiocpp_options_free(o);audiocpp_model_free(m);audiocpp_registry_free(r);
}catch(const std::exception&e){std::cerr<<e.what()<<std::endl;return 1;}return 0;}
