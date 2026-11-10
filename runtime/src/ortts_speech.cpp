#include "ortts_speech.h"
#include "runtime_internal.h"
#include "audiocpp.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#ifndef ORTTS_WITH_SPEECH
#define ORTTS_WITH_SPEECH 0
#endif
#if ORTTS_WITH_SPEECH
#include "engine/models/moonshine_asr/runtime.h"
#endif
namespace {
using ortts::detail::error;
using ortts::detail::execution_gate;
using Clock=std::chrono::steady_clock;
double ms(Clock::time_point t){return std::chrono::duration<double,std::milli>(Clock::now()-t).count();}
bool present(const char*s){return s&&*s;}
void require(bool ok,const char*why){if(!ok)throw std::invalid_argument(why);}
void check(audiocpp_status s){if(s!=AUDIOCPP_OK)throw std::runtime_error(audiocpp_last_error());}
ortts_status failure(){try{throw;}catch(const std::invalid_argument&x){error=x.what();return ORTTS_INVALID;}catch(const std::exception&x){error=x.what();return ORTTS_RUNTIME_ERROR;}catch(...){error="Unknown speech runtime failure";return ORTTS_RUNTIME_ERROR;}}
std::unique_lock<std::mutex> gate(){error.clear();return std::unique_lock<std::mutex>(execution_gate,std::try_to_lock);}
ortts_status busy(){error="Another OrTTS operation is active";return ORTTS_BUSY;}
struct Options {audiocpp_options*p=audiocpp_options_create();~Options(){audiocpp_options_free(p);} Options(){if(!p)throw std::bad_alloc();}};
struct Request {audiocpp_request*p=audiocpp_request_create();~Request(){audiocpp_request_free(p);} Request(){if(!p)throw std::bad_alloc();}};
struct Result {audiocpp_result*p=nullptr;~Result(){audiocpp_result_free(p);}};
void pairs(const ortts_speech_option*p,size_t n){require(n<=64&&(!n||p),"Invalid options array");for(size_t i=0;i<n;++i)require(present(p[i].key)&&p[i].value,"Invalid option key/value");}
void pcm(const float*p,size_t frames,int rate,int channels){require(p&&frames&&frames<=size_t(rate)*120&&rate>=8000&&rate<=192000&&channels>=1&&channels<=2,"Invalid/oversized PCM (maximum 120s)");for(size_t i=0;i<frames*size_t(channels);++i)require(std::isfinite(p[i]),"Nonfinite PCM");}
struct Handle {
 std::string family,task,library,data;
 audiocpp_registry*registry=nullptr;audiocpp_model*model=nullptr;audiocpp_session*session=nullptr;
 std::vector<std::string> languages;
 bool streaming=false,use_vad=false;std::atomic<bool>running{false},cancelled{false};
 ~Handle(){audiocpp_session_free(session);audiocpp_model_free(model);audiocpp_registry_free(registry);}
};
struct Env {
 struct Old{std::string key,value;bool exists;};std::vector<Old>old;
 void set(const char*k,const std::string&v){if(v.empty())return;const char*p=std::getenv(k);old.push_back({k,p?p:"",p!=nullptr});if(setenv(k,v.c_str(),1))throw std::runtime_error("Cannot set eSpeak environment");}
 explicit Env(const Handle&h){try{set("AUDIOCPP_ESPEAK_LIBRARY",h.library);set("AUDIOCPP_ESPEAK_DATA",h.data);}catch(...){restore();throw;}}
 void restore()noexcept{for(auto i=old.rbegin();i!=old.rend();++i){if(i->exists)setenv(i->key.c_str(),i->value.c_str(),1);else unsetenv(i->key.c_str());}old.clear();}
 ~Env(){restore();}
};
struct Running{Handle&h;explicit Running(Handle&v):h(v){h.cancelled=false;h.running=true;}~Running(){h.running=false;}};
bool is_asr(const std::string&f){return f=="sense_asr"||f=="moonshine_asr";}
bool is_tts(const std::string&f){return f=="kokoro_tts"||f=="piper_tts"||f=="kitten_tts"||f=="pocket_tts"||f=="zipvoice"||f=="moss_tts_nano";}
std::string language_base(std::string s){for(char&c:s)if(c>='A'&&c<='Z')c+=32;if(s=="chinese")return "zh";if(s=="english")return "en";return s.substr(0,s.find_first_of("-_"));}
bool contains_han(const char*text){
 std::string s(text);require(s.size()<=65536,"Text exceeds 64KiB; split into requests");bool han=false;
 for(size_t i=0;i<s.size();){unsigned char c=s[i++];uint32_t cp=c;int extra=0;uint32_t minimum=0;
  if(c>=0xC2&&c<=0xDF){cp=c&31;extra=1;minimum=0x80;}else if(c>=0xE0&&c<=0xEF){cp=c&15;extra=2;minimum=0x800;}else if(c>=0xF0&&c<=0xF4){cp=c&7;extra=3;minimum=0x10000;}else require(c<0x80,"Invalid UTF-8 text");
  require(i+extra<=s.size(),"Truncated UTF-8 text");for(int j=0;j<extra;++j){unsigned char d=s[i++];require((d&0xC0)==0x80,"Invalid UTF-8 continuation");cp=(cp<<6)|(d&63);}require(cp>=minimum&&cp<=0x10FFFF&&!(cp>=0xD800&&cp<=0xDFFF),"Invalid UTF-8 codepoint");
  if((cp>=0x3400&&cp<=0x9FFF)||(cp>=0xF900&&cp<=0xFAFF)||(cp>=0x20000&&cp<=0x2EBEF))han=true;
 }return han;
}
bool option_declared(Handle&h,const char*key){size_t n=audiocpp_model_option_count(h.model,AUDIOCPP_OPTION_SCOPE_REQUEST);for(size_t i=0;i<n;++i){const char*name=nullptr;check(audiocpp_model_option(h.model,AUDIOCPP_OPTION_SCOPE_REQUEST,i,&name,nullptr,nullptr,nullptr,nullptr,nullptr,nullptr));if(name&&std::string(name)==key)return true;}return false;}
void language(Handle&h,audiocpp_request*q,const char*lang){
 if(!present(lang)||std::string(lang)=="auto")return;
 const auto base=language_base(lang);bool supported=false;
 for(const auto&v:h.languages)if(language_base(v)==base)supported=true;
 require(supported,"Language is not declared by this model package");
 check(audiocpp_request_set_text_language(q,lang));
 if(option_declared(h,"language"))check(audiocpp_request_set_option(q,"language",lang));
}
void init(Handle&h,const ortts_speech_config*c,bool asr){
 require(ORTTS_WITH_SPEECH,"Speech feature disabled; rebuild with --speech");
 require(c&&c->struct_size==sizeof(*c)&&present(c->family)&&present(c->model_path)&&c->threads>=1&&c->threads<=8&&(c->streaming==0||c->streaming==1),"Invalid speech configuration");
 h.family=c->family;require(asr?is_asr(h.family):is_tts(h.family),"Family not enabled for this API; inspect speech catalog");require(!asr||!c->streaming,"ASR has buffered-final input, not native streaming");
 require(std::filesystem::exists(c->model_path),"Model package path does not exist");
  pairs(c->session_options,c->session_option_count);h.streaming=c->streaming;h.task=asr?"asr":(h.family=="zipvoice"||h.family=="moss_tts_nano")?"clon":"tts";
 h.library=c->espeak_library?c->espeak_library:"";h.data=c->espeak_data?c->espeak_data:"";
 if(!h.library.empty())require(std::filesystem::path(h.library).is_absolute()&&std::filesystem::is_regular_file(h.library),"eSpeak library must be an existing absolute file");
 if(!h.data.empty())require(std::filesystem::path(h.data).is_absolute()&&std::filesystem::is_directory(h.data),"eSpeak data must be an existing absolute directory");
 Env env(h);check(audiocpp_registry_create(nullptr,&h.registry));audiocpp_model_config mc{c->family,nullptr,nullptr,nullptr};check(audiocpp_model_load(h.registry,c->model_path,&mc,nullptr,&h.model));
 require(audiocpp_model_supports(h.model,h.task.c_str(),h.streaming?"streaming":"offline"),"Model does not support selected task/mode");
 for(size_t i=0;i<audiocpp_model_language_count(h.model);++i){const char*v=nullptr;check(audiocpp_model_language(h.model,i,&v));if(v)h.languages.emplace_back(v);}
 Options options;for(size_t i=0;i<c->session_option_count;++i){
  check(audiocpp_options_set(options.p,c->session_options[i].key,c->session_options[i].value));
  if(h.family=="sense_asr"&&std::string(c->session_options[i].key)=="sense_asr.vad_model_path")h.use_vad=true;
 }
 // Piper/Kitten construct their frontend from session options, bypassing the
 // environment fallback used by Kokoro. Typed paths must reach both routes.
 if(h.family=="piper_tts"||h.family=="kitten_tts"){
  if(!h.library.empty())check(audiocpp_options_set(options.p,(h.family+".espeak_library_path").c_str(),h.library.c_str()));
  if(!h.data.empty())check(audiocpp_options_set(options.p,(h.family+".espeak_data_path").c_str(),h.data.c_str()));
 }
 audiocpp_backend_config backend{"cpu",0,c->threads};check(audiocpp_session_create(h.model,h.task.c_str(),h.streaming?"streaming":"offline",&backend,options.p,&h.session));
}
}
struct ortts_tts{Handle h;};
struct ortts_asr{Handle h;size_t limit=16000*60;std::vector<float>pending;};
struct ortts_speech_audio{std::vector<float>samples;int rate=0,channels=0;ortts_metrics metrics{};};
struct ortts_transcript{std::string text,language;double api_ms=0;};
struct ortts_asr_stream {
 std::atomic<bool> cancelled{false};
 bool faulted=false;
#if ORTTS_WITH_SPEECH
 std::unique_ptr<engine::models::moonshine_asr::MoonshineIncremental> native;
#endif
};
namespace {
struct Capture{Handle&h;ortts_speech_pcm_callback cb;void*user;Clock::time_point start;ortts_metrics metrics{0,0,0,-1,0};size_t frames=0;int rate=0,channels=0;bool failed=false;};
int capture(const audiocpp_event*event,void*user)noexcept{
 auto&c=*static_cast<Capture*>(user);if(c.h.cancelled)return 1;
 try{const float*p=nullptr;size_t n=0;int r=0,ch=0;auto status=audiocpp_result_audio(audiocpp_event_as_result(event),&p,&n,&r,&ch);if(status==AUDIOCPP_ERR_NOT_AVAILABLE){const auto*view=audiocpp_event_as_result(event);size_t named=audiocpp_result_named_audio_count(view);if(!named)return 0;require(named==1,"Multiple named audio streams are not supported");check(audiocpp_result_named_audio(view,0,nullptr,&p,&n,&r,&ch));}else check(status);if(!n)return 0;pcm(p,n,r,ch);if(c.rate)require(c.rate==r&&c.channels==ch,"Stream format changed");c.rate=r;c.channels=ch;c.frames+=n;++c.metrics.chunks;if(c.metrics.first_pcm_ms<0)c.metrics.first_pcm_ms=ms(c.start);
 if(c.cb){auto t=Clock::now();int stop=c.cb(c.user,p,n,r,ch);c.metrics.callback_ms+=ms(t);if(stop)c.h.cancelled=true;}return c.h.cancelled?1:0;
 }catch(...){c.failed=true;return 1;}
}
ortts_status recognize(ortts_asr&e,const float*p,size_t n,const char*lang,ortts_transcript**out){
 pcm(p,n,16000,1);require(n<=e.limit,"ASR input exceeds configured limit");Env env(e.h);Running running(e.h);auto start=Clock::now();Request q;check(audiocpp_request_set_audio(q.p,p,n,16000,1));language(e.h,q.p,lang);
 // No implicit VAD file discovery. Host explicitly opts into verified Silero assets.
 // Exact digital silence is deterministic even when VAD is disabled (not a VAD).
 auto text=std::make_unique<ortts_transcript>();bool silent=std::all_of(p,p+n,[](float v){return v==0;});
 if(!silent){if(e.h.family=="sense_asr")check(audiocpp_request_set_option(q.p,"audio_chunk_mode",e.h.use_vad?"auto":"none"));Result r;check(audiocpp_session_run(e.h.session,q.p,&r.p));const char*t=nullptr,*l=nullptr;check(audiocpp_result_text(r.p,&t,&l));text->text=t?t:"";text->language=l?l:"";}
 if(e.h.cancelled){error="ASR cancelled after compute";return ORTTS_CANCELLED;}text->api_ms=ms(start);*out=text.release();return ORTTS_OK;
}
}
extern "C" {
uint32_t ortts_speech_abi_version(void){return ORTTS_WITH_SPEECH?ORTTS_SPEECH_ABI_VERSION:0;}
const char*ortts_speech_catalog_json(void){
#if ORTTS_WITH_SPEECH
  return R"({"schema":1,"executor":"audio.cpp/ggml-cpu","shared_ggml":true,"tts":["kokoro_tts","piper_tts","kitten_tts","pocket_tts","zipvoice","moss_tts_nano"],"asr":["sense_asr","moonshine_asr"],"tts_stream_kind":{"kokoro_tts":"text-chunks","pocket_tts":"codec-chunks","zipvoice":"text-chunks","moss_tts_nano":"codec-chunks-stereo","piper_tts":"offline-only","kitten_tts":"offline-only"},"reference_required":["zipvoice","moss_tts_nano"],"output_channels":{"moss_tts_nano":2},"asr_input":"16000Hz-mono-f32","asr_stream":"bounded-buffer-final","partial":false,"automatic_endpoint":false,"incremental_asr":{"abi":1,"api":"ortts_asr_stream_*","families":["moonshine_asr"],"languages":["en"],"partial":"revisable","encoder":"bounded-overlap-f16","decoder":"hypothesis-redecode","endpoint":["explicit","energy-silence","segment-limit"],"max_segment_ms":30000,"cancellation":"ticks-encode-boundaries-decoder-tokens","per_layer_kv_cache":false},"cancellation":"callback-boundary-or-discard-after-compute","scheduler":"process-serialized-busy","excluded":["f5_tts","whisper","onnx"]})";
#else
 return R"({"schema":1,"tts":[],"asr":[],"disabled":true})";
#endif
}
ortts_status ortts_tts_create(const ortts_speech_config*c,ortts_tts**out){if(out)*out=nullptr;auto lock=gate();if(!lock.owns_lock())return busy();try{require(out,"Missing TTS output pointer");auto e=std::make_unique<ortts_tts>();init(e->h,c,false);*out=e.release();return ORTTS_OK;}catch(...){return failure();}}
ortts_status ortts_tts_synthesize(ortts_tts*e,const ortts_tts_request*r,ortts_speech_pcm_callback cb,void*user,ortts_speech_audio**out){
 if(out)*out=nullptr;auto lock=gate();if(!lock.owns_lock())return busy();try{
 require(e&&r&&out&&r->struct_size==sizeof(*r)&&present(r->text)&&(r->seed_set==0||r->seed_set==1),"Invalid TTS request");require(!cb||e->h.streaming,"Callbacks require a streaming TTS handle");pairs(r->options,r->option_count);
  // MOSS Nano loader advertises only Auto; its pinned family spec explicitly
  // includes Chinese. Do not mistake Auto for an English-only package.
  if(contains_han(r->text)){bool chinese=e->h.family=="moss_tts_nano";for(const auto&v:e->h.languages)if(language_base(v)=="zh")chinese=true;require(chinese,"Han text is unsupported by this language package");}
 Env env(e->h);Running running(e->h);auto start=Clock::now();Request q;check(audiocpp_request_set_text(q.p,r->text,nullptr));language(e->h,q.p,r->language);if(present(r->voice_id)){require(e->h.family!="piper_tts"&&e->h.family!="zipvoice","This adapter has no named presets for this family");check(audiocpp_request_set_voice_id(q.p,r->voice_id));}if(r->seed_set)check(audiocpp_request_set_option(q.p,"seed",std::to_string(r->seed).c_str()));
 for(size_t i=0;i<r->option_count;++i){std::string k=r->options[i].key;require(k!="language"&&k!="voice_id"&&k!="seed","Use typed language/voice/seed fields");check(audiocpp_request_set_option(q.p,k.c_str(),r->options[i].value));}
  if(e->h.family=="zipvoice"||e->h.family=="moss_tts_nano")require(r->reference_pcm&&r->reference_frames&&present(r->reference_text),"Clone family requires reference PCM and matching transcript");
 require(!present(r->reference_text)||r->reference_pcm,"Reference transcript without PCM");
 if(r->reference_pcm||r->reference_frames){require(audiocpp_model_supports_speaker_reference(e->h.model),"Model does not support reference audio");pcm(r->reference_pcm,r->reference_frames,r->reference_sample_rate,r->reference_channels);require(present(r->reference_text),"Reference transcript required");check(audiocpp_request_set_voice_audio(q.p,r->reference_pcm,r->reference_frames,r->reference_sample_rate,r->reference_channels));check(audiocpp_request_set_option(q.p,"reference_text",r->reference_text));}
 Capture cap{e->h,cb,user,start};Result result;
 if(e->h.streaming){
  audiocpp_stream_output_kind output;check(audiocpp_stream_policy(e->h.session,nullptr,&output,nullptr,nullptr));
  bool pull=output==AUDIOCPP_STREAM_OUTPUT_PULL_EVENTS;
  check(audiocpp_stream_set_callback(e->h.session,pull?nullptr:capture,pull?nullptr:&cap));
  auto status=audiocpp_stream_start(e->h.session,q.p);
  if(status==AUDIOCPP_OK&&pull){
   while(!e->h.cancelled&&!cap.failed){audiocpp_event*event=nullptr;status=audiocpp_stream_next_event(e->h.session,&event);if(status!=AUDIOCPP_OK||!event){audiocpp_event_free(event);break;}int stop=capture(event,&cap);audiocpp_event_free(event);if(stop)break;}
  }
  if(!e->h.cancelled&&!cap.failed){check(status);status=audiocpp_stream_finish(e->h.session,&result.p);}
  (void)audiocpp_stream_set_callback(e->h.session,nullptr,nullptr);
  if(e->h.cancelled||cap.failed){(void)audiocpp_stream_reset(e->h.session);error=cap.failed?"Invalid PCM/callback failure":"TTS cancelled";return cap.failed?ORTTS_RUNTIME_ERROR:ORTTS_CANCELLED;}
  check(status);
 }else check(audiocpp_session_run(e->h.session,q.p,&result.p));
 if(e->h.cancelled){error="TTS cancelled after compute";return ORTTS_CANCELLED;}
 const float*p=nullptr;size_t n=0;int rate=0,ch=0;check(audiocpp_result_audio(result.p,&p,&n,&rate,&ch));pcm(p,n,rate,ch);if(e->h.streaming)require(cap.frames==n&&cap.rate==rate&&cap.channels==ch,"Incomplete/mismatched streaming PCM");
 auto a=std::make_unique<ortts_speech_audio>();a->samples.assign(p,p+n*size_t(ch));a->rate=rate;a->channels=ch;a->metrics=cap.metrics;a->metrics.api_ms=ms(start);a->metrics.generation_ms=std::max(0.0,a->metrics.api_ms-a->metrics.callback_ms);*out=a.release();return ORTTS_OK;
 }catch(...){auto status=failure();if(e){(void)audiocpp_stream_set_callback(e->h.session,nullptr,nullptr);(void)audiocpp_stream_reset(e->h.session);}return status;}
}
void ortts_tts_cancel(ortts_tts*e){if(e&&e->h.running)e->h.cancelled=true;}
void ortts_tts_free(ortts_tts*e){if(e){std::lock_guard<std::mutex>l(execution_gate);delete e;}}
const float*ortts_speech_audio_samples(const ortts_speech_audio*a){return a?a->samples.data():nullptr;}
size_t ortts_speech_audio_frames(const ortts_speech_audio*a){return a?a->samples.size()/a->channels:0;}
int32_t ortts_speech_audio_sample_rate(const ortts_speech_audio*a){return a?a->rate:0;}
int32_t ortts_speech_audio_channels(const ortts_speech_audio*a){return a?a->channels:0;}
ortts_status ortts_speech_audio_metrics(const ortts_speech_audio*a,ortts_metrics*out){if(!a||!out){error="Invalid speech audio/metrics";return ORTTS_INVALID;}*out=a->metrics;return ORTTS_OK;}
void ortts_speech_audio_free(ortts_speech_audio*a){delete a;}
ortts_status ortts_asr_create(const ortts_speech_config*c,ortts_asr**out){if(out)*out=nullptr;auto lock=gate();if(!lock.owns_lock())return busy();try{require(out,"Missing ASR output pointer");auto e=std::make_unique<ortts_asr>();init(e->h,c,true);if(c->max_input_frames)e->limit=c->max_input_frames;require(e->limit>0&&e->limit<=16000*120,"ASR limit must be at most 120s");*out=e.release();return ORTTS_OK;}catch(...){return failure();}}
ortts_status ortts_asr_run(ortts_asr*e,const float*p,size_t n,const char*lang,ortts_transcript**out){if(out)*out=nullptr;auto lock=gate();if(!lock.owns_lock())return busy();try{require(e&&out,"Invalid ASR handle/output");require(e->pending.empty(),"ASR buffered input pending; finish/reset first");return recognize(*e,p,n,lang,out);}catch(...){return failure();}}
ortts_status ortts_asr_accept(ortts_asr*e,const float*p,size_t n){auto lock=gate();if(!lock.owns_lock())return busy();try{require(e,"Missing ASR handle");pcm(p,n,16000,1);require(n<=e->limit-e->pending.size(),"ASR buffer limit exceeded; reset or finish");e->pending.insert(e->pending.end(),p,p+n);return ORTTS_OK;}catch(...){return failure();}}
ortts_status ortts_asr_finish(ortts_asr*e,const char*lang,ortts_transcript**out){if(out)*out=nullptr;auto lock=gate();if(!lock.owns_lock())return busy();try{require(e&&out&&!e->pending.empty(),"No buffered ASR audio");auto input=std::move(e->pending);e->pending.clear();return recognize(*e,input.data(),input.size(),lang,out);}catch(...){return failure();}}
ortts_status ortts_asr_reset(ortts_asr*e){auto lock=gate();if(!lock.owns_lock())return busy();if(!e){error="Missing ASR handle";return ORTTS_INVALID;}std::vector<float>().swap(e->pending);return ORTTS_OK;}
void ortts_asr_cancel(ortts_asr*e){if(e&&e->h.running)e->h.cancelled=true;}
void ortts_asr_free(ortts_asr*e){if(e){std::lock_guard<std::mutex>l(execution_gate);delete e;}}
const char*ortts_transcript_text(const ortts_transcript*t){return t?t->text.c_str():nullptr;}
const char*ortts_transcript_language(const ortts_transcript*t){return t?t->language.c_str():nullptr;}
double ortts_transcript_api_ms(const ortts_transcript*t){return t?t->api_ms:0;}
void ortts_transcript_free(ortts_transcript*t){delete t;}
uint32_t ortts_asr_stream_abi_version(void){return ORTTS_WITH_SPEECH?ORTTS_ASR_STREAM_ABI_VERSION:0;}
ortts_status ortts_asr_stream_create(const ortts_speech_config*c,const ortts_asr_stream_config*s,ortts_asr_stream**out){
 if(out)*out=nullptr;auto lock=gate();if(!lock.owns_lock())return busy();try{
 require(ORTTS_WITH_SPEECH,"Speech feature disabled; rebuild with --speech");
 require(out&&c&&c->struct_size==sizeof(*c)&&present(c->family)&&std::string(c->family)=="moonshine_asr"&&present(c->model_path)&&c->threads>=1&&c->threads<=8&&c->streaming==1,"Incremental ASR requires Moonshine streaming configuration");
 require(!c->session_option_count&&!present(c->espeak_library)&&!present(c->espeak_data)&&!c->max_input_frames,"Use typed incremental ASR settings, not offline/session options");
 require(std::filesystem::is_regular_file(c->model_path)||std::filesystem::is_directory(c->model_path),"Missing ASR model package");
 ortts_asr_stream_config v{sizeof(v),400,1000,15000,800,0.003F};
 if(s){require(s->struct_size==sizeof(*s),"Invalid incremental config size");v=*s;}
 require(v.update_ms>=100&&v.update_ms<=2000&&v.update_ms%20==0,"update_ms must be 100..2000 and multiple of 20");
 require(v.min_partial_ms>=400&&v.min_partial_ms<=3000&&v.min_partial_ms%20==0,"min_partial_ms must be 400..3000 and multiple of 20");
 require(v.max_segment_ms>=1000&&v.max_segment_ms<=30000&&v.max_segment_ms%20==0&&v.max_segment_ms>=v.min_partial_ms,"Invalid segment limit");
 require(v.silence_ms==0||(v.silence_ms>=200&&v.silence_ms<=3000&&v.silence_ms%20==0),"Invalid silence endpoint duration");
 require(std::isfinite(v.energy_threshold)&&v.energy_threshold>0&&v.energy_threshold<1,"Invalid RMS energy threshold");
 auto e=std::make_unique<ortts_asr_stream>();
#if ORTTS_WITH_SPEECH
 engine::models::moonshine_asr::MoonshineIncrementalConfig settings;
 settings.update_samples=size_t(v.update_ms)*16;settings.min_partial_samples=size_t(v.min_partial_ms)*16;
 settings.max_segment_samples=size_t(v.max_segment_ms)*16;settings.endpoint_silence_samples=size_t(v.silence_ms)*16;settings.energy_threshold=v.energy_threshold;
 e->native=std::make_unique<engine::models::moonshine_asr::MoonshineIncremental>(c->model_path,c->threads,settings);
#endif
 *out=e.release();return ORTTS_OK;
 }catch(...){return failure();}
}
}
namespace {
ortts_status incremental_operation(ortts_asr_stream*e,const float*p,size_t n,bool finish,ortts_asr_stream_callback cb,void*user){
 auto lock=gate();if(!lock.owns_lock())return busy();bool started=false;
 try{
 require(ORTTS_WITH_SPEECH&&e&&cb,"Invalid incremental ASR handle/callback");
 if(e->cancelled){error="ASR stream cancelled; reset before reuse";return ORTTS_CANCELLED;}
 require(!e->faulted,"ASR stream failed; reset before reuse");
 if(!finish){require(n<=32000,"Incremental input call exceeds 2s; split input");pcm(p,n,16000,1);}
#if ORTTS_WITH_SPEECH
 auto sink=[&](const engine::models::moonshine_asr::MoonshineIncrementalEvent&v){
  ortts_asr_stream_event event{sizeof(event),v.endpoint,v.segment,v.start,v.end,v.revision,v.text.c_str(),"en"};
  if(cb(user,&event))e->cancelled=true;return e->cancelled.load();
 };
 auto cancel=[&](){return e->cancelled.load();};started=true;
 bool ok=finish?e->native->finish(sink,cancel):e->native->accept(p,n,sink,cancel);
 if(!ok||e->cancelled){e->cancelled=true;error="ASR stream cancelled; reset before reuse";return ORTTS_CANCELLED;}
#endif
 return ORTTS_OK;
 }catch(...){if(started&&e)e->faulted=true;return failure();}
}
}
extern "C" {
ortts_status ortts_asr_stream_accept(ortts_asr_stream*e,const float*p,size_t n,ortts_asr_stream_callback cb,void*u){return incremental_operation(e,p,n,false,cb,u);}
ortts_status ortts_asr_stream_finish(ortts_asr_stream*e,ortts_asr_stream_callback cb,void*u){return incremental_operation(e,nullptr,0,true,cb,u);}
ortts_status ortts_asr_stream_reset(ortts_asr_stream*e){auto lock=gate();if(!lock.owns_lock())return busy();try{require(ORTTS_WITH_SPEECH&&e,"Invalid incremental ASR handle");
#if ORTTS_WITH_SPEECH
 e->native->reset();e->faulted=false;e->cancelled=false;
#endif
 return ORTTS_OK;}catch(...){return failure();}}
void ortts_asr_stream_cancel(ortts_asr_stream*e){if(e)e->cancelled=true;}
ortts_status ortts_asr_stream_get_stats(ortts_asr_stream*e,ortts_asr_stream_stats*out){auto lock=gate();if(!lock.owns_lock())return busy();try{require(ORTTS_WITH_SPEECH&&e&&out&&out->struct_size==sizeof(*out),"Invalid ASR stream stats");
#if ORTTS_WITH_SPEECH
 auto s=e->native->stats();*out={sizeof(*out),s.received,s.processed,s.encoded,s.updates,s.buffered,s.cached_frames,s.segment_samples,s.peak_buffered,s.peak_cached_frames,s.encoder_ms,s.decoder_ms};
#endif
 return ORTTS_OK;}catch(...){return failure();}}
void ortts_asr_stream_free(ortts_asr_stream*e){if(e){std::lock_guard<std::mutex>l(execution_gate);delete e;}}
}
