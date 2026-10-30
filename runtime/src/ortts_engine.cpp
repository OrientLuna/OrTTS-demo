#include "ortts_engine.h"
#include "audiocpp.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;
thread_local std::string error;
std::mutex execution_gate;
double elapsed(Clock::time_point start) {
 return std::chrono::duration<double,std::milli>(Clock::now()-start).count();
}
void check(audiocpp_status s) {
 if(s!=AUDIOCPP_OK) throw std::runtime_error(audiocpp_last_error());
}
// The old runtime reads process environment. Serialize our instances and restore
// caller state after every operation; unrelated direct audio.cpp users must not
// run concurrently in this process until upstream uses per-session selectors.
struct Environment {
 struct Entry { std::string key, value; bool existed; };
 std::vector<Entry> saved;
 void set(const std::string& key, const char* value) {
  const char* old=std::getenv(key.c_str());
  saved.push_back({key,old?old:"",old!=nullptr});
  if((value ? setenv(key.c_str(),value,1) : unsetenv(key.c_str()))!=0)
   throw std::runtime_error("Cannot set engine environment");
 }
 ~Environment() {
  for(auto i=saved.rbegin();i!=saved.rend();++i) {
   if(i->existed) setenv(i->key.c_str(),i->value.c_str(),1);
   else unsetenv(i->key.c_str());
  }
 }
};
std::string child(const std::string& root,const char* path) {
 return (std::filesystem::path(root)/path).string();
}
void regular(const std::string& path) {
 if(!std::filesystem::is_regular_file(path)) throw std::invalid_argument("Missing asset: "+path);
}
struct RequestOwner {
 audiocpp_request* p=audiocpp_request_create();
 ~RequestOwner(){audiocpp_request_free(p);}
};
struct ResultOwner {
 audiocpp_result* p=nullptr;
 ~ResultOwner(){audiocpp_result_free(p);}
};
struct OptionsOwner {
 audiocpp_options* p=audiocpp_options_create();
 ~OptionsOwner(){audiocpp_options_free(p);}
};
}

struct ortts_engine {
 std::string root, variant, speaker, manifest;
 int threads=4;
 bool streaming=true;
 audiocpp_registry* registry=nullptr;
 audiocpp_model* model=nullptr;
 audiocpp_session* session=nullptr;
 std::atomic<bool> running{false}, cancelled{false};
 void environment(Environment& e) const {
  for(auto key:{"ORTTS_GROUPED_PREDICTOR_GGUF","ORTTS_GROUPED_PREDICTOR_PACKED",
      "ORTTS_P3_PREDICTOR_SOURCE","ORTTS_PRIVATE_NATIVE_BODY_Q4","ORTTS_PREDICTOR_CPU_REPACK",
      "ORTTS_B0_STREAM_PREFIX_REFERENCE","ORTTS_B0_DISABLE_REPACK","ORTTS_EXPORT_GENERATED_CODES_DIR"}) e.set(key,nullptr);
  if(variant=="P3") {auto path=child(root,"P3/predictor");e.set("ORTTS_P3_PREDICTOR_SOURCE",path.c_str());}
  for(auto kv:{std::pair{"ORTTS_FFN_PUREC_M1","0"},{"ORTTS_NATIVE_PREDICTOR_PACKED","0"},
      {"ORTTS_CPU_PERSISTENT_POOL","0"},{"ORTTS_CPU_TCONV_GEMM","1"},{"ORTTS_PRIVATE_FAST_BACKEND","cpu"}}) e.set(kv.first,kv.second);
  auto base=child(root,"native/tokenizer-LFM2.5-Audio-1.5B-Q4_0.gguf");
  e.set("ORTTS_PRIVATE_BASE_DETOK_GGUF",base.c_str());
  e.set("ORTTS_PRIVATE_BRIDGE_MANIFEST_SHA256",manifest.c_str());
 }
 ~ortts_engine() {
  audiocpp_session_free(session);
  audiocpp_model_free(model);
  audiocpp_registry_free(registry);
 }
};
struct ortts_audio {
 std::vector<float> samples;
 ortts_metrics metrics{};
};

namespace {
struct Running {
 ortts_engine& e;
 explicit Running(ortts_engine& engine):e(engine){e.cancelled=false;e.running=true;}
 ~Running(){e.running=false;}
};
struct Capture {
 ortts_engine* engine;
 ortts_pcm_callback sink;
 void* user;
 Clock::time_point start;
 ortts_metrics metrics{0,0,0,-1,0};
 bool failed=false;
 size_t samples=0;
};
int capture(const audiocpp_event* event,void* user) noexcept {
 auto& c=*static_cast<Capture*>(user);
 if(c.engine->cancelled.load()) return 1;
 try {
  const float* pcm=nullptr;size_t n=0;int rate=0,channels=0;
  check(audiocpp_result_audio(audiocpp_event_as_result(event),&pcm,&n,&rate,&channels));
  if(!n)return 0;
  if(!pcm||rate!=24000||channels!=1)throw std::runtime_error("Invalid PCM chunk");
  for(size_t i=0;i<n;++i)if(!std::isfinite(pcm[i]))throw std::runtime_error("Nonfinite PCM chunk");
  if(c.metrics.first_pcm_ms<0)c.metrics.first_pcm_ms=elapsed(c.start);
  ++c.metrics.chunks;c.samples+=n;
  if(c.sink) {
   auto begin=Clock::now();int stop=c.sink(c.user,pcm,n,rate);
   c.metrics.callback_ms+=elapsed(begin);
   if(stop)c.engine->cancelled=true;
  }
  return c.engine->cancelled?1:0;
 } catch(...) {c.failed=true;return 1;}
}
}

extern "C" {
uint32_t ortts_abi_version(void){return ORTTS_ABI_VERSION;}
const char* ortts_last_error(void){return error.c_str();}
ortts_status ortts_engine_create(const ortts_config* cfg,ortts_engine** out) {
 if(out)*out=nullptr;
 error.clear();
 if(!cfg||!out||cfg->struct_size!=sizeof(*cfg)||!cfg->asset_root||!cfg->variant||
    !cfg->bridge_manifest_sha256||cfg->threads<1||cfg->threads>8||
    (cfg->streaming!=0&&cfg->streaming!=1)) {error="Invalid engine configuration";return ORTTS_INVALID;}
 std::unique_lock<std::mutex> lock(execution_gate,std::try_to_lock);
 if(!lock.owns_lock()){error="Another engine operation is active";return ORTTS_BUSY;}
 try {
  Environment env;
  auto e=std::make_unique<ortts_engine>();
  e->root=std::filesystem::absolute(cfg->asset_root).string();e->variant=cfg->variant;
  e->speaker=cfg->speaker_f32?cfg->speaker_f32:child(e->root,"voices/female.f32");
  e->manifest=cfg->bridge_manifest_sha256;e->threads=cfg->threads;e->streaming=cfg->streaming!=0;
  if((e->variant!="P3"&&e->variant!="P5")||e->manifest.size()!=64||
     e->manifest.find_first_not_of("0123456789abcdefABCDEF")!=std::string::npos)
   throw std::invalid_argument("Invalid variant/manifest identity");
  for(auto name:{"native/model.gguf","native/bridge/MANIFEST.json","native/tokenizer-b260k-MIXED_Q4_0.gguf",
      "native/tokenizer-LFM2.5-Audio-1.5B-Q4_0.gguf","native/vocoder-LFM2.5-Audio-1.5B-Q4_0.gguf"})regular(child(e->root,name));
  regular(e->speaker);
  if(std::filesystem::file_size(e->speaker)!=4096)throw std::invalid_argument("Speaker must be 1024 F32 values");
  std::ifstream speaker(e->speaker,std::ios::binary);float values[1024];
  if(!speaker.read(reinterpret_cast<char*>(values),sizeof values))throw std::invalid_argument("Cannot read speaker");
  for(auto v:values)if(!std::isfinite(v))throw std::invalid_argument("Nonfinite speaker vector");
  if(e->variant=="P3")for(auto name:{"config.json","predictor.safetensors"})regular(child(e->root,(std::string("P3/predictor/")+name).c_str()));
  e->environment(env);
  check(audiocpp_registry_create(nullptr,&e->registry));
  audiocpp_model_config model{"qwen3_tts",nullptr,nullptr,nullptr};
  check(audiocpp_model_load(e->registry,child(e->root,"native/model.gguf").c_str(),&model,nullptr,&e->model));
  OptionsOwner options;if(!options.p)throw std::runtime_error("Options allocation failed");
  auto opt=[&](const char* k,const std::string& v){check(audiocpp_options_set(options.p,k,v.c_str()));};
  opt("qwen3_tts.fixed_speaker_f32",e->speaker);opt("qwen3_tts.lfm_b0_bundle",child(e->root,"native/bridge"));
  opt("qwen3_tts.lfm_b0_detokenizer_gguf",child(e->root,"native/tokenizer-b260k-MIXED_Q4_0.gguf"));
  opt("qwen3_tts.lfm_b0_vocoder_gguf",child(e->root,"native/vocoder-LFM2.5-Audio-1.5B-Q4_0.gguf"));
  for(auto kv:{std::pair{"qwen3_tts.perf_mode","off"},{"qwen3_tts.packed_projections","false"},
      {"qwen3_tts.conv_weight_type","f32"},{"qwen3_tts.speech_decoder_conv_weight_type","f16"},
      {"qwen3_tts.codec_pipeline","false"},{"qwen3_tts.cpu_chunk_frames","0"},{"qwen3_tts.stitch_decode","false"}})opt(kv.first,kv.second);
  audiocpp_backend_config backend{"cpu",0,e->threads};
  check(audiocpp_session_create(e->model,"tts",e->streaming?"streaming":"offline",&backend,options.p,&e->session));
  *out=e.release();return ORTTS_OK;
 }catch(const std::invalid_argument& x){error=x.what();return ORTTS_INVALID;}
 catch(const std::exception& x){error=x.what();return ORTTS_RUNTIME_ERROR;}
 catch(...){error="Unknown engine load failure";return ORTTS_RUNTIME_ERROR;}
}
ortts_status ortts_engine_synthesize(ortts_engine* e,const ortts_request* req,ortts_pcm_callback sink,void* user,ortts_audio** out) {
 const auto api_start=Clock::now();
 if(out)*out=nullptr;
 error.clear();
 if(!e||!req||!out||req->struct_size!=sizeof(*req)||!req->text||!*req->text||req->max_tokens<1||req->max_tokens>513) {
  error="Invalid synthesis request";return ORTTS_INVALID;
 }
 if(!e->streaming&&sink){error="PCM callbacks require a streaming engine";return ORTTS_INVALID;}
 std::unique_lock<std::mutex> lock(execution_gate,std::try_to_lock);
 if(!lock.owns_lock()){error="Another engine operation is active";return ORTTS_BUSY;}
 try {
  Environment env;e->environment(env);Running running(*e);
  RequestOwner q;if(!q.p)throw std::runtime_error("Request allocation failed");
  check(audiocpp_request_set_text(q.p,req->text,nullptr));
  for(auto kv:{std::pair{"x_vector_only_mode","true"},{"language","Chinese"},{"do_sample","true"},
      {"temperature","0.9"},{"top_k","50"},{"top_p","0.9"},{"repetition_penalty","1.05"},
      {"subtalker_do_sample","false"}})check(audiocpp_request_set_option(q.p,kv.first,kv.second));
  check(audiocpp_request_set_option(q.p,"seed",std::to_string(req->seed).c_str()));
  check(audiocpp_request_set_option(q.p,"max_tokens",std::to_string(req->max_tokens).c_str()));
  Capture c{e,sink,user,api_start};ResultOwner result;
  if(e->streaming) {
   check(audiocpp_request_set_option(q.p,"stream_frames_per_event","3"));
   check(audiocpp_request_set_option(q.p,"stream_chunk_policy","fixed"));
   check(audiocpp_stream_set_callback(e->session,capture,&c));
   auto status=audiocpp_stream_start(e->session,q.p);
   (void)audiocpp_stream_set_callback(e->session,nullptr,nullptr);
   if(e->cancelled||c.failed) {
    (void)audiocpp_stream_reset(e->session);
    error=c.failed?"PCM callback failed":"Generation cancelled";
    return c.failed?ORTTS_RUNTIME_ERROR:ORTTS_CANCELLED;
   }
   check(status);check(audiocpp_stream_finish(e->session,&result.p));
  }else check(audiocpp_session_run(e->session,q.p,&result.p));
  if(e->cancelled){error="Generation cancelled";return ORTTS_CANCELLED;}
  const float* pcm=nullptr;size_t n=0;int rate=0,channels=0;
  check(audiocpp_result_audio(result.p,&pcm,&n,&rate,&channels));
  if(!n||!pcm||rate!=24000||channels!=1||(e->streaming&&c.samples!=n))throw std::runtime_error("Invalid/incomplete result PCM");
  for(size_t i=0;i<n;++i)if(!std::isfinite(pcm[i]))throw std::runtime_error("Nonfinite result PCM");
  auto audio=std::make_unique<ortts_audio>();audio->samples.assign(pcm,pcm+n);
  const double wall=elapsed(api_start);
  audio->metrics=c.metrics;audio->metrics.api_ms=wall;
  audio->metrics.generation_ms=std::max(0.0,wall-c.metrics.callback_ms);
  *out=audio.release();return ORTTS_OK;
 }catch(const std::exception& x) {error=x.what();}
 catch(...) {error="Unknown synthesis failure";}
 (void)audiocpp_stream_set_callback(e->session,nullptr,nullptr);
 (void)audiocpp_stream_reset(e->session);
 return ORTTS_RUNTIME_ERROR;
}
void ortts_engine_cancel(ortts_engine* e){if(e&&e->running.load())e->cancelled=true;}
void ortts_engine_free(ortts_engine* e){if(!e)return;std::lock_guard<std::mutex> lock(execution_gate);delete e;}
const float* ortts_audio_samples(const ortts_audio* a){return a?a->samples.data():nullptr;}
size_t ortts_audio_sample_count(const ortts_audio* a){return a?a->samples.size():0;}
int32_t ortts_audio_sample_rate(const ortts_audio* a){return a?24000:0;}
ortts_status ortts_audio_metrics(const ortts_audio* a,ortts_metrics* out){if(!a||!out){error="Invalid audio/metrics output";return ORTTS_INVALID;}*out=a->metrics;return ORTTS_OK;}
void ortts_audio_free(ortts_audio* a){delete a;}
}
