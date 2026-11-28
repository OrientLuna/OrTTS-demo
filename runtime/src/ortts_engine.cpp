#include "ortts_engine.h"
#include "runtime_internal.h"
#include "audiocpp.h"
#include "inference_defaults.h"
#include "language_routing.h"
#include "model_pack.h"
#include "ptq_lazy_policy.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
#ifndef ORTTS_WITH_COOPERATIVE_CANCEL
#define ORTTS_WITH_COOPERATIVE_CANCEL 0
#endif
#ifndef ORTTS_WITH_P3_FOUR_ROUND
#define ORTTS_WITH_P3_FOUR_ROUND 0
#endif
#if defined(__has_include)
#if __has_include("ortts_speaker_switch_support.h")
#include "ortts_speaker_switch_support.h"
#endif
#endif
#ifndef ORTTS_AUDIOCPP_PER_REQUEST_SPEAKER
#define ORTTS_AUDIOCPP_PER_REQUEST_SPEAKER 0
#endif
#ifndef ORTTS_AUDIOCPP_C0_GUARD
#define ORTTS_AUDIOCPP_C0_GUARD 0
#endif
#if ORTTS_AUDIOCPP_C0_GUARD
extern "C" const char* ortts_lc_stop_reason(void);
#endif
#if ORTTS_WITH_COOPERATIVE_CANCEL
#include "engine/framework/core/ortts_cancellation.h"
#endif

namespace ortts::detail {
thread_local std::string error;
std::mutex execution_gate;
}

namespace {
#if ORTTS_WITH_COOPERATIVE_CANCEL
using CancelScope = engine::core::ortts_cancel::Scope;
#else
struct CancelScope { explicit CancelScope(const std::atomic<bool>*, const std::atomic<bool>* = nullptr) {} };
#endif
void cancellation_checkpoint(const ortts_cancel_token* token) {
 if(token && token->cancelled.load())throw std::runtime_error("Engine loading cancelled");
}
using Clock = std::chrono::steady_clock;
using ortts::detail::error;
using ortts::detail::execution_gate;
double elapsed(Clock::time_point start) {
 return std::chrono::duration<double,std::milli>(Clock::now()-start).count();
}
void check(audiocpp_status s) {
 if(s!=AUDIOCPP_OK) throw std::runtime_error(audiocpp_last_error());
}
std::string child(const std::string& root,const char* path) {
 return (std::filesystem::path(root)/path).string();
}
std::string encode_speaker_vector_hex(const float* vec, size_t dim, size_t expected_dim) {
 if (!vec || dim != expected_dim || (expected_dim != 1024 && expected_dim != 2048)) {
  throw std::invalid_argument("Speaker vector must match own model dimensions");
 }
 double energy = 0.0;
 for (size_t i = 0; i < dim; ++i) {
  if (!std::isfinite(vec[i])) throw std::invalid_argument("Nonfinite speaker vector");
  energy += double(vec[i]) * double(vec[i]);
 }
 if (!(energy > 0.0)) throw std::invalid_argument("Speaker vector cannot be zero");
 static constexpr char kHex[] = "0123456789abcdef";
 const uint8_t* bytes = reinterpret_cast<const uint8_t*>(vec);
 std::string out(dim * sizeof(float) * 2, '\0');
 for (size_t i = 0; i < dim * sizeof(float); ++i) {
  out[2 * i] = kHex[(bytes[i] >> 4) & 0xf];
  out[2 * i + 1] = kHex[bytes[i] & 0xf];
 }
 return out;
}
void validate_request_speed(float speed) {
 if (speed == 0.0f) return;
 if (!std::isfinite(speed) || speed < 0.5f || speed > 2.0f) {
  throw std::invalid_argument("Speech speed must be finite within 0.5..=2.0 (or 0 for default)");
 }
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
 std::string root, variant, speaker, manifest, predictor_sha, active_speaker_hex, p3_schedule="serial";
 size_t speaker_dim=1024;
 bool speaker_overridden=false;
 ortts::pack::Decoder decoder;
 ortts::ptq::PTQPolicy ptq;
 int threads=4;
 bool streaming=true;
 audiocpp_registry* registry=nullptr;
 audiocpp_model* model=nullptr;
 audiocpp_session* session=nullptr;
 std::timed_mutex execution;
 std::atomic<bool> running{false}, cancelled{false};
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
 const ortts_cancel_token* token=nullptr;
};
int capture(const audiocpp_event* event,void* user) noexcept {
 auto& c=*static_cast<Capture*>(user);
  if(c.engine->cancelled.load() || (c.token && c.token->cancelled.load())) return 1;
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
uint32_t ortts_engine_feature_version(void){return ORTTS_AUDIOCPP_PER_REQUEST_SPEAKER ? 2u : 0u;}
const char* ortts_last_error(void){return error.c_str();}
uint32_t ortts_cooperative_cancel_version(void) { return ORTTS_WITH_COOPERATIVE_CANCEL ? 1u : 0u; }
ortts_cancel_token* ortts_cancel_token_create(void) {
 try { return new ortts_cancel_token(); } catch(...) { return nullptr; }
}
void ortts_cancel_token_request(ortts_cancel_token* token) { if(token)token->cancelled=true; }
void ortts_cancel_token_free(ortts_cancel_token* token) { delete token; }
ortts_status ortts_engine_create(const ortts_config* cfg,ortts_engine** out) {
 return ortts_engine_create_cancellable(cfg,nullptr,out);
}
ortts_status ortts_engine_create_cancellable(const ortts_config* cfg,ortts_cancel_token* token,ortts_engine** out) {
 if(out)*out=nullptr;
 error.clear();
 if(!cfg||!out||cfg->struct_size!=sizeof(*cfg)||!cfg->asset_root||!cfg->variant||
    !cfg->bridge_manifest_sha256||cfg->threads<1||cfg->threads>8||
    (cfg->streaming!=0&&cfg->streaming!=1)) {error="Invalid engine configuration";return ORTTS_INVALID;}
 try {
  CancelScope cancellation(token?&token->cancelled:nullptr);
  cancellation_checkpoint(token);
  auto e=std::make_unique<ortts_engine>();
  e->root=std::filesystem::absolute(cfg->asset_root).string();e->variant=cfg->variant;
  e->speaker=cfg->speaker_f32?cfg->speaker_f32:child(e->root,"voices/female.f32");
  e->decoder=ortts::pack::resolve(e->root);
  e->manifest=cfg->bridge_manifest_sha256;e->threads=cfg->threads;e->streaming=cfg->streaming!=0;
  if((e->variant!="P3"&&e->variant!="P5")||e->manifest.size()!=64||
     e->manifest.find_first_not_of("0123456789abcdefABCDEF")!=std::string::npos)
   throw std::invalid_argument("Invalid variant/manifest identity");
  if(!e->decoder.dequant_bundle.empty() && e->manifest!=e->decoder.dequant_sha)throw std::invalid_argument("Caller dequant manifest identity mismatch");
  ortts::pack::require_dependencies(e->root,e->decoder);
  e->speaker_dim=ortts::pack::speaker_dimension(e->root);
  ortts::pack::validate_speaker(e->speaker,e->speaker_dim);
  e->predictor_sha=ortts::pack::native_predictor_hash(e->root,e->variant);
  e->ptq=ortts::ptq::policy(e->root,e->variant);
  if(const char*env_lazy=std::getenv("ORTTS_LAZY_IMPORT_SCRATCH");env_lazy&&*env_lazy) {
   if(std::strcmp(env_lazy,"1")==0)e->ptq.lazy=true;
   else if(std::strcmp(env_lazy,"0")==0)e->ptq.lazy=false;
   else throw std::invalid_argument("ORTTS_LAZY_IMPORT_SCRATCH must be 0 or 1");
  }
  e->p3_schedule=ortts::pack::resolve_p3_schedule(e->root,e->variant);
  if(e->p3_schedule=="four_round"){
#if ORTTS_WITH_P3_FOUR_ROUND
   if(e->variant!="P3" || e->speaker_dim!=1024)
    throw std::invalid_argument("Four-round P3 requires 0.6B P3");
#else
   throw std::invalid_argument("此版本未启用四轮 P3");
#endif
  }
  cancellation_checkpoint(token);
  check(audiocpp_registry_create(nullptr,&e->registry));
  audiocpp_model_config model{"qwen3_tts",nullptr,nullptr,nullptr};
  check(audiocpp_model_load(e->registry,child(e->root,"native/model.gguf").c_str(),&model,nullptr,&e->model));
  cancellation_checkpoint(token);
  OptionsOwner options;if(!options.p)throw std::runtime_error("Options allocation failed");
  auto opt=[&](const char* k,const std::string& v){check(audiocpp_options_set(options.p,k,v.c_str()));};
  opt("qwen3_tts.fixed_speaker_f32",e->speaker);opt("qwen3_tts.lfm_b0_bundle",e->decoder.dequant_bundle.empty()?child(e->root,"native/bridge"):e->decoder.dequant_bundle);
  if(e->decoder.dequant_bundle.empty()){
   opt("qwen3_tts.lfm_b0_detokenizer_gguf",child(e->root,"native/tokenizer-b260k-MIXED_Q4_0.gguf"));
   opt("qwen3_tts.lfm_b0_vocoder_gguf",child(e->root,"native/vocoder-LFM2.5-Audio-1.5B-Q4_0.gguf"));
   opt("qwen3_tts.lfm_b0_base_detok_gguf",child(e->root,"native/tokenizer-LFM2.5-Audio-1.5B-Q4_0.gguf"));
   opt("qwen3_tts.lfm_b0_bridge_manifest_sha256",e->manifest);
  }else{
   opt("qwen3_tts.lfm_b0_base_detok_gguf","");
   opt("qwen3_tts.lfm_b0_bridge_manifest_sha256",e->decoder.dequant_sha);
  }
  if(e->decoder.liquid()){
   opt("qwen3_tts.lc_variant",e->decoder.variant=="base"?"base100k":"expanded120k");
   opt("qwen3_tts.lc_assets",e->decoder.assets);
  }
  if(e->variant=="P3"){
   opt("qwen3_tts.p3_predictor_source",child(e->root,"P3/predictor"));
   opt("qwen3_tts.p3_schedule",e->p3_schedule);
  }
  if(!e->predictor_sha.empty())opt("qwen3_tts.p3_native_sha256",e->predictor_sha);
  const char* pred_packed=std::getenv("ORTTS_NATIVE_PREDICTOR_PACKED");
  if(pred_packed&&*pred_packed&&std::strcmp(pred_packed,"0")!=0&&std::strcmp(pred_packed,"1")!=0)
   throw std::invalid_argument("ORTTS_NATIVE_PREDICTOR_PACKED must be 0 or 1");
  opt("qwen3_tts.native_predictor_packed",(pred_packed&&*pred_packed)?pred_packed:"1");
  opt("qwen3_tts.private_fast_backend","cpu");
  opt("qwen3_tts.b0_disable_repack","0");
  opt("qwen3_tts.lazy_import_scratch",e->ptq.lazy?"1":"0");
  if(e->ptq.present)opt("qwen3_tts.qa_expect_talker_type",std::to_string(e->ptq.type));
  for(auto kv:ortts::inference::session_defaults)opt(kv.first,kv.second);
  if(const char* v=std::getenv("ORTTS_PACKED_PROJECTIONS");v&&*v)opt("qwen3_tts.packed_projections",v);
  if(const char* v=std::getenv("ORTTS_KV_CACHE_TYPE");v&&*v)opt("qwen3_tts.kv_cache_type",v);
  audiocpp_backend_config backend{"cpu",0,e->threads};
  check(audiocpp_session_create(e->model,"tts",e->streaming?"streaming":"offline",&backend,options.p,&e->session));
  cancellation_checkpoint(token);
  *out=e.release();return ORTTS_OK;
 }catch(const std::invalid_argument& x){error=x.what();return token&&token->cancelled?ORTTS_CANCELLED:ORTTS_INVALID;}
 catch(const std::exception& x){error=x.what();return token&&token->cancelled?ORTTS_CANCELLED:ORTTS_RUNTIME_ERROR;}
 catch(...){error="Unknown engine load failure";return token&&token->cancelled?ORTTS_CANCELLED:ORTTS_RUNTIME_ERROR;}
}
ortts_status ortts_engine_set_speaker(ortts_engine* e, const char* speaker_f32) {
 return ortts_engine_set_speaker_ex(e, speaker_f32, nullptr);
}
ortts_status ortts_engine_set_speaker_ex(ortts_engine* e, const char* speaker_f32, const ortts_exec_policy* policy) {
 error.clear();
 if(!e) { error="Invalid engine handle"; return ORTTS_INVALID; }
 if(speaker_f32 && !*speaker_f32) { error="Speaker path cannot be empty"; return ORTTS_INVALID; }
 ortts_status lock_status=ORTTS_BUSY;
 auto lock=ortts::detail::try_acquire_execution(e->execution,e->running,e->cancelled,policy,lock_status);
 if(!lock.owns_lock()) return lock_status;
 try {
#if !ORTTS_AUDIOCPP_PER_REQUEST_SPEAKER
  throw std::invalid_argument("Per-request speaker switching requires speaker-switch runtime patch");
#endif
  std::string target = speaker_f32 ? std::string(speaker_f32) : child(e->root, "voices/female.f32");
  ortts::pack::validate_speaker(target, e->speaker_dim);
  e->speaker = std::move(target);
  e->active_speaker_hex.clear();
  e->speaker_overridden = true;
  return ORTTS_OK;
 } catch(const std::invalid_argument& x) { error=x.what(); return ORTTS_INVALID; }
 catch(const std::exception& x) { error=x.what(); return ORTTS_RUNTIME_ERROR; }
 catch(...) { error="Unknown speaker update failure"; return ORTTS_RUNTIME_ERROR; }
}
ortts_status ortts_engine_set_speaker_vector(ortts_engine* e, const float* vector, size_t dim) {
 return ortts_engine_set_speaker_vector_ex(e, vector, dim, nullptr);
}
ortts_status ortts_engine_set_speaker_vector_ex(ortts_engine* e, const float* vector, size_t dim, const ortts_exec_policy* policy) {
 error.clear();
 if(!e) { error="Invalid engine handle"; return ORTTS_INVALID; }
 ortts_status lock_status=ORTTS_BUSY;
 auto lock=ortts::detail::try_acquire_execution(e->execution,e->running,e->cancelled,policy,lock_status);
 if(!lock.owns_lock()) return lock_status;
 try {
#if !ORTTS_AUDIOCPP_PER_REQUEST_SPEAKER
  throw std::invalid_argument("Per-request speaker switching requires speaker-switch runtime patch");
#endif
  std::string hex = encode_speaker_vector_hex(vector, dim, e->speaker_dim);
  e->active_speaker_hex = std::move(hex);
  e->speaker_overridden = true;
  return ORTTS_OK;
 } catch(const std::invalid_argument& x) { error=x.what(); return ORTTS_INVALID; }
 catch(const std::exception& x) { error=x.what(); return ORTTS_RUNTIME_ERROR; }
 catch(...) { error="Unknown speaker vector update failure"; return ORTTS_RUNTIME_ERROR; }
}
ortts_status ortts_engine_synthesize(ortts_engine* e,const ortts_request* req,ortts_pcm_callback sink,void* user,ortts_audio** out) {
 return ortts_engine_synthesize_ex(e,req,nullptr,nullptr,sink,user,out);
}
ortts_status ortts_engine_synthesize_cancellable(ortts_engine* e,const ortts_request* req,ortts_cancel_token* token,ortts_pcm_callback sink,void* user,ortts_audio** out) {
 return ortts_engine_synthesize_ex(e,req,nullptr,token,sink,user,out);
}
ortts_status ortts_engine_synthesize_ex(ortts_engine* e,const ortts_request* req,const ortts_exec_policy* policy,ortts_cancel_token* token,ortts_pcm_callback sink,void* user,ortts_audio** out) {
 const auto api_start=Clock::now();
 if(out)*out=nullptr;
 error.clear();
 if(!e||!req||!out||(req->struct_size!=ORTTS_REQUEST_V1_SIZE&&req->struct_size!=ORTTS_REQUEST_V1_1_SIZE&&req->struct_size!=sizeof(*req))||!req->text||!*req->text||req->max_tokens<1||req->max_tokens>513) {
  error="Invalid synthesis request";return ORTTS_INVALID;
 }
 if(!e->streaming&&sink){error="PCM callbacks require a streaming engine";return ORTTS_INVALID;}
 const bool has_v11 = req->struct_size >= ORTTS_REQUEST_V1_1_SIZE;
 const bool has_v12 = req->struct_size == sizeof(*req);
 std::string req_speaker_hex;
 std::string req_speaker_path;
 std::string resolved_language;
 bool use_req_hex = false;
 bool use_req_path = false;
 try {
  resolved_language = ortts::language::resolve_language(has_v12 ? req->language : nullptr, req->text);
  if (has_v11) {
   validate_request_speed(req->speed);
   const bool has_path = req->speaker_f32 != nullptr;
   const bool has_vec = req->speaker_vector != nullptr;
   if (has_path && !*req->speaker_f32) {
    throw std::invalid_argument("Per-request speaker path cannot be empty");
   }
   if (!has_vec && req->speaker_dim != 0) {
    throw std::invalid_argument("speaker_dim must be 0 when speaker_vector is NULL");
   }
   if (has_path && has_vec) {
    throw std::invalid_argument("Specify either speaker_f32 or speaker_vector, not both");
   }
   if (has_vec) {
#if !ORTTS_AUDIOCPP_PER_REQUEST_SPEAKER
    throw std::invalid_argument("Per-request speaker switching requires speaker-switch runtime patch");
#endif
    req_speaker_hex = encode_speaker_vector_hex(req->speaker_vector, req->speaker_dim, e->speaker_dim);
    use_req_hex = true;
   } else if (has_path) {
#if !ORTTS_AUDIOCPP_PER_REQUEST_SPEAKER
    throw std::invalid_argument("Per-request speaker switching requires speaker-switch runtime patch");
#endif
    ortts::pack::validate_speaker(req->speaker_f32, e->speaker_dim);
    req_speaker_path = req->speaker_f32;
    use_req_path = true;
   }
  }
 } catch(const std::invalid_argument& x) {
  error=x.what(); return ORTTS_INVALID;
 } catch(const std::exception& x) {
  error=x.what(); return ORTTS_RUNTIME_ERROR;
 }
 ortts_status lock_status=ORTTS_BUSY;
 auto lock=ortts::detail::try_acquire_execution(e->execution,e->running,e->cancelled,policy,lock_status);
 if(!lock.owns_lock())return lock_status;
 const auto cancelled=[&] { return e->cancelled.load() || (token && token->cancelled.load()); };
 try {
  Running running(*e);
  CancelScope cancellation(&e->cancelled,token?&token->cancelled:nullptr);
  cancellation_checkpoint(token);
  RequestOwner q;if(!q.p)throw std::runtime_error("Request allocation failed");
  check(audiocpp_request_set_text(q.p,req->text,nullptr));
  for(auto kv:ortts::inference::request_defaults)check(audiocpp_request_set_option(q.p,kv.first,kv.second));
  check(audiocpp_request_set_option(q.p,"language",resolved_language.c_str()));
  check(audiocpp_request_set_option(q.p,"seed",std::to_string(req->seed).c_str()));
  check(audiocpp_request_set_option(q.p,"max_tokens",std::to_string(req->max_tokens).c_str()));
  if (use_req_hex) {
   check(audiocpp_request_set_option(q.p,"qwen3_tts.fixed_speaker_hex",req_speaker_hex.c_str()));
  } else if (use_req_path) {
   check(audiocpp_request_set_option(q.p,"qwen3_tts.fixed_speaker_f32",req_speaker_path.c_str()));
  } else if (e->speaker_overridden) {
   if (!e->active_speaker_hex.empty()) {
    check(audiocpp_request_set_option(q.p,"qwen3_tts.fixed_speaker_hex",e->active_speaker_hex.c_str()));
   } else {
    check(audiocpp_request_set_option(q.p,"qwen3_tts.fixed_speaker_f32",e->speaker.c_str()));
   }
  }
  Capture c{e,sink,user,api_start};c.token=token;ResultOwner result;
  if(e->streaming) {
   check(audiocpp_request_set_option(q.p,"stream_frames_per_event","3"));
   check(audiocpp_request_set_option(q.p,"stream_chunk_policy","fixed"));
   check(audiocpp_stream_set_callback(e->session,capture,&c));
   auto status=audiocpp_stream_start(e->session,q.p);
   const char* raw_error=status==AUDIOCPP_OK?nullptr:audiocpp_last_error();
   const std::string stream_error=raw_error?raw_error:"Stream generation failed";
   (void)audiocpp_stream_set_callback(e->session,nullptr,nullptr);
   if(cancelled()||c.failed) {
    (void)audiocpp_stream_reset(e->session);
    error=c.failed?"PCM callback failed":"Generation cancelled";
    return c.failed?ORTTS_RUNTIME_ERROR:ORTTS_CANCELLED;
   }
   if(status!=AUDIOCPP_OK)throw std::runtime_error(stream_error);
   check(audiocpp_stream_finish(e->session,&result.p));
  }else check(audiocpp_session_run(e->session,q.p,&result.p));
  if(cancelled())throw std::runtime_error("Generation cancelled");
  const float* pcm=nullptr;size_t n=0;int rate=0,channels=0;
  check(audiocpp_result_audio(result.p,&pcm,&n,&rate,&channels));
  if(!n||!pcm||rate!=24000||channels!=1||(e->streaming&&c.samples!=n))throw std::runtime_error("Invalid/incomplete result PCM");
  for(size_t i=0;i<n;++i)if(!std::isfinite(pcm[i]))throw std::runtime_error("Nonfinite result PCM");
  auto audio=std::make_unique<ortts_audio>();audio->samples.assign(pcm,pcm+n);
  const double wall=elapsed(api_start);
  audio->metrics=c.metrics;audio->metrics.api_ms=wall;
  audio->metrics.generation_ms=std::max(0.0,wall-c.metrics.callback_ms);
  if(cancelled())throw std::runtime_error("Generation cancelled");
  *out=audio.release();return ORTTS_OK;
 }catch(const std::invalid_argument& x){error=x.what();return cancelled()?ORTTS_CANCELLED:ORTTS_INVALID;}
 catch(const std::exception& x) {
#if ORTTS_AUDIOCPP_C0_GUARD
  const char* reason = ortts_lc_stop_reason();
  if (reason && std::strcmp(reason, "c0_repeat_loop_stop") == 0) {
   error = std::string("Talker c0 repeat loop stop (c0_repeat_loop_stop): ") + x.what();
  } else {
   error = x.what();
  }
#else
  error=x.what();
#endif
 }
 catch(...) {error="Unknown synthesis failure";}
 if(e->streaming) {
  (void)audiocpp_stream_set_callback(e->session,nullptr,nullptr);
  (void)audiocpp_stream_reset(e->session);
 }
 if(cancelled()){error="Generation cancelled; model remains loaded";return ORTTS_CANCELLED;}
 return ORTTS_RUNTIME_ERROR;
}
void ortts_engine_cancel(ortts_engine* e){if(e&&e->running.load())e->cancelled=true;}
void ortts_engine_free(ortts_engine* e){if(!e)return;{std::lock_guard<std::timed_mutex> lock(e->execution);}delete e;}
const float* ortts_audio_samples(const ortts_audio* a){return a?a->samples.data():nullptr;}
size_t ortts_audio_sample_count(const ortts_audio* a){return a?a->samples.size():0;}
int32_t ortts_audio_sample_rate(const ortts_audio* a){return a?24000:0;}
ortts_status ortts_audio_metrics(const ortts_audio* a,ortts_metrics* out){if(!a||!out){error="Invalid audio/metrics output";return ORTTS_INVALID;}*out=a->metrics;return ORTTS_OK;}
void ortts_audio_free(ortts_audio* a){delete a;}
}
