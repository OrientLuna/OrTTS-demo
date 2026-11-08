#include <jni.h>
#include <audiocpp.h>
#include "ortts_speech.h"
#include "../../../../../runtime/src/model_pack.h"
#include "../../../../../runtime/src/inference_defaults.h"
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <mutex>
#include <codecvt>
#include <locale>
#include <sys/resource.h>
namespace {
using Clock=std::chrono::steady_clock;std::mutex mu;
audiocpp_registry*reg=nullptr;audiocpp_model*model=nullptr;audiocpp_session*session=nullptr;std::string active;
double ms(Clock::time_point t){return std::chrono::duration<double,std::milli>(Clock::now()-t).count();}
void check(audiocpp_status s){if(s!=AUDIOCPP_OK)throw std::runtime_error(audiocpp_last_error());}
std::string str(JNIEnv*e,jstring s){if(!s)return{};const jchar*p=e->GetStringChars(s,nullptr);if(!p)throw std::runtime_error("text allocation failed");std::u16string u((const char16_t*)p,e->GetStringLength(s));e->ReleaseStringChars(s,p);return std::wstring_convert<std::codecvt_utf8_utf16<char16_t>,char16_t>{}.to_bytes(u);}
void release(){audiocpp_session_free(session);session=nullptr;audiocpp_model_free(model);model=nullptr;audiocpp_registry_free(reg);reg=nullptr;active.clear();}
void u32(std::ostream&f,uint32_t v){for(int i=0;i<4;i++)f.put(char(v>>(i*8)));}
void u16(std::ostream&f,uint16_t v){f.put(char(v));f.put(char(v>>8));}
void savewav(const std::string&p,const float*x,size_t n){std::ofstream f(p,std::ios::binary);f.write("RIFF",4);u32(f,uint32_t(36+n*4));f.write("WAVEfmt ",8);u32(f,16);u16(f,3);u16(f,1);u32(f,24000);u32(f,96000);u16(f,4);u16(f,32);f.write("data",4);u32(f,uint32_t(n*4));f.write((const char*)x,n*4);if(!f)throw std::runtime_error("WAV write failed");}
struct Capture{JNIEnv*env;jobject sink;jmethodID method;Clock::time_point start;std::vector<float>pcm;size_t chunks=0;double first=-1,last=0,maxgap=0,callback_ms=0;bool failed=false;};
int callback(const audiocpp_event*event,void*data){auto&c=*(Capture*)data;auto sinkStart=Clock::now();try{const float*x=nullptr;size_t n=0;int sr=0,ch=0;check(audiocpp_result_audio(audiocpp_event_as_result(event),&x,&n,&sr,&ch));if(!n)return 0;if(sr!=24000||ch!=1||!x)throw std::runtime_error("callback schema");for(size_t i=0;i<n;i++)if(!std::isfinite(x[i]))throw std::runtime_error("nonfinite callback");double arrival=ms(c.start);if(c.first<0)c.first=arrival;if(c.chunks)c.maxgap=std::max(c.maxgap,arrival-c.last);c.last=arrival;c.chunks++;c.pcm.insert(c.pcm.end(),x,x+n);auto a=c.env->NewFloatArray((jsize)n);if(!a)throw std::runtime_error("audio allocation");c.env->SetFloatArrayRegion(a,0,(jsize)n,x);c.env->CallVoidMethod(c.sink,c.method,a,sr);c.env->DeleteLocalRef(a);c.callback_ms+=ms(sinkStart);if(c.env->ExceptionCheck()){c.failed=true;return 1;}return 0;}catch(...){c.failed=true;return 1;}}
}
extern "C" JNIEXPORT jboolean JNICALL Java_com_orient_ortts_demo_NativeBridge_supportsLiquidCodecNative(JNIEnv*,jclass){return ORTTS_WITH_LIQUIDCODEC?JNI_TRUE:JNI_FALSE;}
extern "C" JNIEXPORT void JNICALL Java_com_orient_ortts_demo_NativeBridge_releaseNative(JNIEnv*,jclass){std::lock_guard<std::mutex>l(mu);release();}
extern "C" JNIEXPORT jstring JNICALL Java_com_orient_ortts_demo_NativeBridge_runNative(JNIEnv*e,jclass,jstring rootJ,jstring variantJ,jstring voiceJ,jstring textJ,jint threads,jlong seed,jboolean stream,jobject sink,jstring outJ,jstring shaJ){std::lock_guard<std::mutex>l(mu);try{
 auto root=str(e,rootJ),variant=str(e,variantJ),voice=str(e,voiceJ),text=str(e,textJ),out=str(e,outJ),sha=str(e,shaJ);if((variant!="P3"&&variant!="P5")||(voice!="female"&&voice!="female_2"&&voice!="male"&&voice!="male_2")||threads<1||threads>8||text.empty()||sha.size()!=64)throw std::runtime_error("invalid model, voice or input");std::filesystem::create_directories(out);std::string trace=out+"/trace.log";check(audiocpp_ortts_trace_file(trace.c_str()));setenv("ORTTS_EXPORT_GENERATED_CODES_DIR",out.c_str(),1);setenv("TMPDIR",out.c_str(),1);
 auto decoder=ortts::pack::resolve(root);
 ortts::pack::require_dependencies(root,decoder);ortts::pack::validate_speaker(root+"/voices/"+voice+".f32",ortts::pack::speaker_dimension(root));auto predictor_sha=ortts::pack::native_predictor_hash(root,variant);
 const auto setup=Clock::now();auto key=root+variant+voice+std::to_string(threads)+(stream?"stream":"offline")+decoder.cache_key();bool reused=key==active&&session;
 if(!reused){release();ortts::pack::environment(decoder,[](const char*k,const char*v){if(v)setenv(k,v,1);else unsetenv(k);});for(auto k:{"ORTTS_GROUPED_PREDICTOR_GGUF","ORTTS_GROUPED_PREDICTOR_PACKED","ORTTS_P3_PREDICTOR_SOURCE","ORTTS_P3_NATIVE_SHA256","ORTTS_PRIVATE_NATIVE_BODY_Q4","ORTTS_PREDICTOR_CPU_REPACK","ORTTS_B0_STREAM_PREFIX_REFERENCE","ORTTS_B0_DISABLE_REPACK"})unsetenv(k);if(variant=="P3")setenv("ORTTS_P3_PREDICTOR_SOURCE",(root+"/P3/predictor").c_str(),1);if(!predictor_sha.empty())setenv("ORTTS_P3_NATIVE_SHA256",predictor_sha.c_str(),1);setenv("ORTTS_FFN_PUREC_M1","0",1);setenv("ORTTS_NATIVE_PREDICTOR_PACKED","0",1);setenv("ORTTS_CPU_PERSISTENT_POOL","0",1);setenv("ORTTS_CPU_TCONV_GEMM","1",1);setenv("ORTTS_PRIVATE_FAST_BACKEND","cpu",1);setenv("ORTTS_PRIVATE_BASE_DETOK_GGUF",(decoder.dequant_bundle.empty()?root+"/native/tokenizer-LFM2.5-Audio-1.5B-Q4_0.gguf":std::string{}).c_str(),1);setenv("ORTTS_PRIVATE_BRIDGE_MANIFEST_SHA256",(decoder.dequant_bundle.empty()?sha:decoder.dequant_sha).c_str(),1);
 check(audiocpp_registry_create(nullptr,&reg));audiocpp_model_config mc{"qwen3_tts",nullptr,nullptr,nullptr};check(audiocpp_model_load(reg,(root+"/native/model.gguf").c_str(),&mc,nullptr,&model));auto*o=audiocpp_options_create();if(!o)throw std::runtime_error("options allocation");try{auto opt=[&](const char*k,const std::string&v){check(audiocpp_options_set(o,k,v.c_str()));};opt("qwen3_tts.fixed_speaker_f32",root+"/voices/"+voice+".f32");opt("qwen3_tts.lfm_b0_bundle",decoder.dequant_bundle.empty()?root+"/native/bridge":decoder.dequant_bundle);if(decoder.dequant_bundle.empty()){opt("qwen3_tts.lfm_b0_detokenizer_gguf",root+"/native/tokenizer-b260k-MIXED_Q4_0.gguf");opt("qwen3_tts.lfm_b0_vocoder_gguf",root+"/native/vocoder-LFM2.5-Audio-1.5B-Q4_0.gguf");}for(auto p:ortts::inference::session_defaults)opt(p.first,p.second);audiocpp_backend_config bc{"cpu",0,threads};check(audiocpp_session_create(model,"tts",stream?"streaming":"offline",&bc,o,&session));}catch(...){audiocpp_options_free(o);release();throw;}audiocpp_options_free(o);active=key;
 }
 double setup_ms=ms(setup);auto*q=audiocpp_request_create();if(!q)throw std::runtime_error("request allocation");audiocpp_result*y=nullptr;try{check(audiocpp_request_set_text(q,text.c_str(),nullptr));for(auto p:{std::pair{"x_vector_only_mode","true"},{"language","Chinese"},{"max_tokens","513"},{"do_sample","true"},{"temperature","0.9"},{"top_k","50"},{"top_p","0.9"},{"repetition_penalty","1.05"},{"subtalker_do_sample","false"}})check(audiocpp_request_set_option(q,p.first,p.second));check(audiocpp_request_set_option(q,"seed",std::to_string(seed).c_str()));Capture c{e,sink,nullptr,Clock::now()};if(stream){check(audiocpp_request_set_option(q,"stream_frames_per_event","3"));check(audiocpp_request_set_option(q,"stream_chunk_policy","fixed"));auto cl=e->GetObjectClass(sink);c.method=e->GetMethodID(cl,"onPcm","([FI)V");e->DeleteLocalRef(cl);if(!c.method)throw std::runtime_error("PCM sink unavailable");check(audiocpp_stream_set_callback(session,callback,&c));auto status=audiocpp_stream_start(session,q);check(audiocpp_stream_set_callback(session,nullptr,nullptr));check(status);check(audiocpp_stream_finish(session,&y));}else check(audiocpp_session_run(session,q,&y));double wall=ms(c.start);const float*pcm=nullptr;size_t n=0;int sr=0,ch=0;check(audiocpp_result_audio(y,&pcm,&n,&sr,&ch));if(!n||sr!=24000||ch!=1)throw std::runtime_error("result schema");for(size_t i=0;i<n;i++)if(!std::isfinite(pcm[i]))throw std::runtime_error("nonfinite PCM");if(stream){if(c.failed||c.chunks<2||c.pcm.size()!=n)throw std::runtime_error("incomplete incremental PCM");for(size_t i=0;i<n;i++)if(c.pcm[i]!=pcm[i])throw std::runtime_error("callback/final mismatch");}savewav(out+"/sample.wav",pcm,n);std::ifstream f(trace);std::string log((std::istreambuf_iterator<char>(f)),{});auto p=log.rfind("observed_stop_reason ");bool eos=p!=std::string::npos&&log.substr(p+21,3)=="eos";struct rusage usage{};getrusage(RUSAGE_SELF,&usage);std::ostringstream s;s<<"{\"variant\":\""<<variant<<"\",\"voice\":\""<<voice<<"\",\"streaming\":"<<(stream?"true":"false")<<",\"setup_ms\":"<<setup_ms<<",\"session_reused\":"<<(reused?"true":"false")<<",\"api_ms\":"<<wall<<",\"audio_s\":"<<double(n)/24000<<",\"RTF\":"<<wall/1000/(double(n)/24000)<<",\"pcm_sink_wall_ms\":"<<c.callback_ms<<",\"generation_ms\":"<<std::max(0.0,wall-c.callback_ms)<<",\"generation_RTF\":"<<std::max(0.0,wall-c.callback_ms)/1000/(double(n)/24000)<<",\"first_pcm_ms\":"<<(stream?std::to_string(c.first):"null")<<",\"chunks\":"<<c.chunks<<",\"samples\":"<<n<<",\"sample_rate\":24000,\"EOS\":\""<<(eos?"eos":"UNKNOWN_OR_NON_EOS")<<"\",\"callback_concat_exact\":"<<(stream?"true":"null")<<",\"peak_RSS_KiB\":"<<usage.ru_maxrss<<",\"threads\":"<<threads<<",\"backend\":\"CPU\"}";auto result=s.str();std::ofstream(out+"/native-report.json")<<result;audiocpp_result_free(y);audiocpp_request_free(q);return e->NewStringUTF(result.c_str());}catch(...){audiocpp_result_free(y);audiocpp_request_free(q);if(session){(void)audiocpp_stream_set_callback(session,nullptr,nullptr);(void)audiocpp_stream_reset(session);}throw;}
 }catch(const std::exception&x){if(!e->ExceptionCheck())e->ThrowNew(e->FindClass("java/lang/IllegalStateException"),x.what());return nullptr;}}

#if ORTTS_WITH_SPEECH
namespace {
std::mutex speechPointers;
ortts_tts *speechTts=nullptr;ortts_asr *speechAsr=nullptr;ortts_asr_stream *speechStream=nullptr;
void speechCheck(ortts_status s){if(s!=ORTTS_OK)throw std::runtime_error(ortts_last_error());}
jstring unicode(JNIEnv*e,const std::string&s){auto u=std::wstring_convert<std::codecvt_utf8_utf16<char16_t>,char16_t>{}.from_bytes(s);return e->NewString(reinterpret_cast<const jchar*>(u.data()),u.size());}
void speechError(JNIEnv*e,const std::exception&x){if(!e->ExceptionCheck())e->ThrowNew(e->FindClass("java/lang/IllegalStateException"),x.what());}
void speechClose(){
 std::lock_guard<std::mutex>guard(speechPointers);
 ortts_tts_free(speechTts);speechTts=nullptr;ortts_asr_free(speechAsr);speechAsr=nullptr;ortts_asr_stream_free(speechStream);speechStream=nullptr;
}
struct SpeechSink{JNIEnv*env;jobject object;jmethodID method;};
int speechPcm(void*user,const float*pcm,size_t n,int32_t rate,int32_t channels){
 auto&s=*static_cast<SpeechSink*>(user);if(channels!=1||n>INT32_MAX)return 1;
 jfloatArray a=s.env->NewFloatArray(n);if(!a)return 1;s.env->SetFloatArrayRegion(a,0,n,pcm);s.env->CallVoidMethod(s.object,s.method,a,rate);s.env->DeleteLocalRef(a);return s.env->ExceptionCheck()?1:0;
}
int speechText(void*user,const ortts_asr_stream_event*v){
 auto&s=*static_cast<SpeechSink*>(user);jstring t=unicode(s.env,v->text);if(!t)return 1;s.env->CallVoidMethod(s.object,s.method,t,v->endpoint,jlong(v->segment_id));s.env->DeleteLocalRef(t);return s.env->ExceptionCheck()?1:0;
}
SpeechSink textSink(JNIEnv*e,jobject sink){auto c=e->GetObjectClass(sink);auto method=e->GetMethodID(c,"onText","(Ljava/lang/String;IJ)V");e->DeleteLocalRef(c);if(!method)throw std::runtime_error("ASR sink unavailable");return {e,sink,method};}
void nativeWav(const std::string&path,const float*p,size_t n,int rate){std::ofstream f(path,std::ios::binary);f.write("RIFF",4);u32(f,36+n*4);f.write("WAVEfmt ",8);u32(f,16);u16(f,3);u16(f,1);u32(f,rate);u32(f,rate*4);u16(f,4);u16(f,32);f.write("data",4);u32(f,n*4);f.write(reinterpret_cast<const char*>(p),n*4);if(!f)throw std::runtime_error("WAV save failed");}
}
#endif
extern "C" JNIEXPORT jboolean JNICALL Java_com_orient_ortts_demo_SpeechBridge_available(JNIEnv*,jclass){
#if ORTTS_WITH_SPEECH
 return ortts_speech_abi_version()==1&&ortts_asr_stream_abi_version()==1;
#else
 return JNI_FALSE;
#endif
}
extern "C" JNIEXPORT void JNICALL Java_com_orient_ortts_demo_SpeechBridge_cancel(JNIEnv*,jclass){
#if ORTTS_WITH_SPEECH
 std::lock_guard<std::mutex>guard(speechPointers);ortts_tts_cancel(speechTts);ortts_asr_cancel(speechAsr);ortts_asr_stream_cancel(speechStream);
#endif
}
extern "C" JNIEXPORT void JNICALL Java_com_orient_ortts_demo_SpeechBridge_close(JNIEnv*e,jclass){
#if ORTTS_WITH_SPEECH
 std::lock_guard<std::mutex>guard(mu);try{speechClose();}catch(const std::exception&x){speechError(e,x);}
#endif
}
extern "C" JNIEXPORT jstring JNICALL Java_com_orient_ortts_demo_SpeechBridge_synthesize(JNIEnv*e,jclass,jstring familyJ,jstring libraryJ,jstring dataJ,jstring pathJ,jstring voiceJ,jstring textJ,jboolean streaming,jobject sink,jstring outJ){
#if ORTTS_WITH_SPEECH
 std::lock_guard<std::mutex>guard(mu);ortts_speech_audio*audio=nullptr;
 try{
  release();speechClose();auto family=str(e,familyJ),library=str(e,libraryJ),data=str(e,dataJ),path=str(e,pathJ),voice=str(e,voiceJ),text=str(e,textJ),out=str(e,outJ);
  ortts_speech_config c{};c.struct_size=sizeof(c);c.family=family.c_str();c.espeak_library=library.empty()?nullptr:library.c_str();c.espeak_data=data.empty()?nullptr:data.c_str();c.model_path=path.c_str();c.threads=4;c.streaming=streaming;
  ortts_tts*engine=nullptr;speechCheck(ortts_tts_create(&c,&engine));{std::lock_guard<std::mutex>p(speechPointers);speechTts=engine;}
  auto cl=e->GetObjectClass(sink);auto method=e->GetMethodID(cl,"onPcm","([FI)V");e->DeleteLocalRef(cl);if(!method)throw std::runtime_error("PCM sink unavailable");SpeechSink receiver{e,sink,method};
  ortts_tts_request request{};request.struct_size=sizeof(request);request.text=text.c_str();request.language=voice.size()&&voice[0]=='z'?"zh":"en";request.voice_id=family=="piper_tts"?nullptr:voice.c_str();request.seed_set=1;request.seed=42;
  speechCheck(ortts_tts_synthesize(engine,&request,streaming?speechPcm:nullptr,&receiver,&audio));
  const float*pcm=ortts_speech_audio_samples(audio);size_t n=ortts_speech_audio_frames(audio);int rate=ortts_speech_audio_sample_rate(audio);
  if(!streaming&&speechPcm(&receiver,pcm,n,rate,1))throw std::runtime_error("Playback callback failed");
  nativeWav(out,pcm,n,rate);ortts_metrics metrics{};speechCheck(ortts_speech_audio_metrics(audio,&metrics));
  std::ostringstream report;report<<"{\"audio_s\":"<<double(n)/rate<<",\"api_ms\":"<<metrics.api_ms<<",\"sample_rate\":"<<rate<<",\"RTF\":"<<metrics.api_ms/(1000.0*n/rate)<<"}";
  ortts_speech_audio_free(audio);audio=nullptr;speechClose();return unicode(e,report.str());
 }catch(const std::exception&x){ortts_speech_audio_free(audio);speechClose();speechError(e,x);return nullptr;}
#else
 e->ThrowNew(e->FindClass("java/lang/IllegalStateException"),"Speech feature disabled");return nullptr;
#endif
}
extern "C" JNIEXPORT void JNICALL Java_com_orient_ortts_demo_SpeechBridge_openAsr(JNIEnv*e,jclass,jstring familyJ,jstring pathJ){
#if ORTTS_WITH_SPEECH
 std::lock_guard<std::mutex>guard(mu);try{
  release();speechClose();auto family=str(e,familyJ),path=str(e,pathJ);bool streaming=family=="moonshine_asr";
  ortts_speech_config c{};c.struct_size=sizeof(c);c.family=family.c_str();c.model_path=path.c_str();c.threads=4;c.streaming=streaming;
  if(streaming){ortts_asr_stream*engine=nullptr;speechCheck(ortts_asr_stream_create(&c,nullptr,&engine));std::lock_guard<std::mutex>p(speechPointers);speechStream=engine;}
  else{if(family!="sense_asr")throw std::runtime_error("Unsupported Demo ASR");ortts_asr*engine=nullptr;speechCheck(ortts_asr_create(&c,&engine));std::lock_guard<std::mutex>p(speechPointers);speechAsr=engine;}
 }catch(const std::exception&x){speechClose();speechError(e,x);}
#endif
}
extern "C" JNIEXPORT void JNICALL Java_com_orient_ortts_demo_SpeechBridge_accept(JNIEnv*e,jclass,jfloatArray input,jint count,jobject sink){
#if ORTTS_WITH_SPEECH
 std::lock_guard<std::mutex>guard(mu);jfloat*p=nullptr;
 try{if(!input||count<=0||count>e->GetArrayLength(input)||count>32000)throw std::runtime_error("Invalid ASR chunk");p=e->GetFloatArrayElements(input,nullptr);if(!p)throw std::bad_alloc();auto receiver=textSink(e,sink);if(speechStream)speechCheck(ortts_asr_stream_accept(speechStream,p,count,speechText,&receiver));else if(speechAsr)speechCheck(ortts_asr_accept(speechAsr,p,count));else throw std::runtime_error("ASR is not open");e->ReleaseFloatArrayElements(input,p,JNI_ABORT);
 }catch(const std::exception&x){if(p)e->ReleaseFloatArrayElements(input,p,JNI_ABORT);speechError(e,x);}
#endif
}
extern "C" JNIEXPORT void JNICALL Java_com_orient_ortts_demo_SpeechBridge_finish(JNIEnv*e,jclass,jobject sink){
#if ORTTS_WITH_SPEECH
 std::lock_guard<std::mutex>guard(mu);ortts_transcript*result=nullptr;
 try{auto receiver=textSink(e,sink);if(speechStream)speechCheck(ortts_asr_stream_finish(speechStream,speechText,&receiver));else if(speechAsr){speechCheck(ortts_asr_finish(speechAsr,nullptr,&result));ortts_asr_stream_event event{sizeof(event),ORTTS_ASR_FLUSH,0,0,0,1,ortts_transcript_text(result),"auto"};speechText(&receiver,&event);ortts_transcript_free(result);result=nullptr;}else throw std::runtime_error("ASR is not open");
 }catch(const std::exception&x){ortts_transcript_free(result);speechError(e,x);}
#endif
}
