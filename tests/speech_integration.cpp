#include "ortts_speech.h"
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>
void expect(bool b,const char*s){if(!b)throw std::runtime_error(s);}
void ok(ortts_status s){if(s)throw std::runtime_error(ortts_last_error());}
struct Tts{ortts_tts*p=nullptr;~Tts(){ortts_tts_free(p);}};
struct Asr{ortts_asr*p=nullptr;~Asr(){ortts_asr_free(p);}};
struct Audio{ortts_speech_audio*p=nullptr;~Audio(){ortts_speech_audio_free(p);}};
struct Text{ortts_transcript*p=nullptr;~Text(){ortts_transcript_free(p);}};
std::vector<float> mono16(const ortts_speech_audio*a){const float*p=ortts_speech_audio_samples(a);size_t n=ortts_speech_audio_frames(a);int rate=ortts_speech_audio_sample_rate(a);expect(ortts_speech_audio_channels(a)==1,"test fixture must be mono");std::vector<float>r(size_t(double(n)*16000/rate));for(size_t i=0;i<r.size();++i){double at=double(i)*rate/16000;size_t j=std::min(size_t(at),n-1),k=std::min(j+1,n-1);r[i]=float(p[j]*(1-(at-j))+p[k]*(at-j));}return r;}
void wav(const std::string&path,const ortts_speech_audio*a){std::ofstream f(path,std::ios::binary);uint32_t bytes=uint32_t(ortts_speech_audio_frames(a)*ortts_speech_audio_channels(a)*4),size=bytes+36,fmt_size=16,rate=ortts_speech_audio_sample_rate(a),byte_rate=rate*ortts_speech_audio_channels(a)*4;uint16_t fmt=3,ch=ortts_speech_audio_channels(a),align=ch*4,bits=32;auto w=[&](auto v){f.write((char*)&v,sizeof(v));};f.write("RIFF",4);w(size);f.write("WAVEfmt ",8);w(fmt_size);w(fmt);w(ch);w(rate);w(byte_rate);w(align);w(bits);f.write("data",4);w(bytes);f.write((char*)ortts_speech_audio_samples(a),bytes);expect(bool(f),"WAV write failed");}
ortts_speech_config config(const char*f,const std::string&path,bool stream=false){ortts_speech_config c{};c.struct_size=sizeof(c);c.family=f;c.model_path=path.c_str();c.threads=4;c.streaming=stream;c.espeak_library=std::getenv("AUDIOCPP_ESPEAK_LIBRARY");c.espeak_data=std::getenv("AUDIOCPP_ESPEAK_DATA");return c;}
struct Capture{bool cancel=false;int expected_rate=24000;size_t frames=0,chunks=0;bool shared_gate=false;};
int receive(void*u,const float*p,size_t n,int32_t rate,int32_t ch){auto&c=*(Capture*)u;expect(p&&n&&rate==c.expected_rate&&ch==1,"native stream format");c.frames+=n;++c.chunks;ortts_config cfg{sizeof(cfg),"/missing","P3",nullptr,"0000000000000000000000000000000000000000000000000000000000000000",1,1};ortts_engine*old=nullptr;c.shared_gate=ortts_engine_create(&cfg,&old)==ORTTS_BUSY;return c.cancel;}
int main(int argc,char**argv){if(argc!=3)return 2;try{
 expect(ortts_abi_version()==1&&ortts_speech_abi_version()==1,"ABI versions");std::string root=argv[1],out=argv[2];std::filesystem::create_directories(out);std::cout<<ortts_speech_catalog_json()<<"\n";
 std::vector<float>english,chinese,reference;int ref_rate=0;
 for(const std::string f:{"piper_tts","kokoro_tts","kitten_tts","pocket_tts","zipvoice"}){
  std::string file=f=="piper_tts"?"Piper-TTS-GGUF/piper-en-us-lessac-medium-orig.gguf":f=="kokoro_tts"?"Kokoro-82M-GGUF/kokoro-82m-q8_0.gguf":f=="kitten_tts"?"KittenTTS-GGUF/kitten-tts-mini-0.8-orig.gguf":f=="pocket_tts"?"PocketTTS-GGUF/english/pocket-tts-english-q8_0.gguf":"zipvoice-distill-q8_0.gguf";std::string path=root+"/"+file;auto cfg=config(f.c_str(),path);Tts e;ortts_speech_option zo{"zipvoice.espeak_library_path",cfg.espeak_library};if(f=="zipvoice"){cfg.session_options=&zo;cfg.session_option_count=1;}ok(ortts_tts_create(&cfg,&e.p));
  ortts_tts_request r{};r.struct_size=sizeof(r);r.text=f=="kokoro_tts"?"今天上午九点半，请检查车票和随身行李。":"At nine thirty, please check the train ticket and call the station.";r.language=f=="kokoro_tts"?"zh":"en";r.voice_id=f=="kokoro_tts"?"zf_xiaobei":f=="kitten_tts"?"Bella":f=="pocket_tts"?"anna":nullptr;r.seed_set=1;r.seed=42;
  if(f=="zipvoice"){r.reference_pcm=reference.data();r.reference_frames=reference.size();r.reference_sample_rate=ref_rate;r.reference_channels=1;r.reference_text="At nine thirty, please check the train ticket and call the station.";}
  Audio audio;ok(ortts_tts_synthesize(e.p,&r,nullptr,nullptr,&audio.p));expect(ortts_speech_audio_sample_rate(audio.p)==(f=="piper_tts"?22050:24000),"native rate lost");expect(ortts_speech_audio_frames(audio.p)>1000,"empty/short output");wav(out+"/"+f+".wav",audio.p);ortts_metrics metrics{};ok(ortts_speech_audio_metrics(audio.p,&metrics));std::cout<<f<<" frames="<<ortts_speech_audio_frames(audio.p)<<" rate="<<ortts_speech_audio_sample_rate(audio.p)<<" api_ms="<<metrics.api_ms<<"\n";
  if(f=="piper_tts"){english=mono16(audio.p);ref_rate=ortts_speech_audio_sample_rate(audio.p);reference.assign(ortts_speech_audio_samples(audio.p),ortts_speech_audio_samples(audio.p)+ortts_speech_audio_frames(audio.p));}
  if(f=="kokoro_tts")chinese=mono16(audio.p);
  if(f=="pocket_tts"||f=="zipvoice"){
   cfg.streaming=1;Tts streaming;ok(ortts_tts_create(&cfg,&streaming.p));Capture c;c.expected_rate=f=="piper_tts"?22050:24000;c.cancel=true;Audio cancelled;expect(ortts_tts_synthesize(streaming.p,&r,receive,&c,&cancelled.p)==ORTTS_CANCELLED&&!cancelled.p&&c.chunks==1,"native/pull stream cancel");c.cancel=false;c.frames=0;c.chunks=0;Audio full;ok(ortts_tts_synthesize(streaming.p,&r,receive,&c,&full.p));expect(c.frames==ortts_speech_audio_frames(full.p)&&c.frames>0,"native/pull stream totals");std::cout<<f<<" stream_cancel_reuse=pass chunks="<<c.chunks<<"\n";
  }
  if(f=="piper_tts"||f=="kitten_tts"){cfg.streaming=1;Tts rejected;expect(ortts_tts_create(&cfg,&rejected.p)==ORTTS_INVALID&&!rejected.p,"offline-only model silently falls back");}
  if(f=="pocket_tts"){r.language="zh";Audio bad;expect(ortts_tts_synthesize(e.p,&r,nullptr,nullptr,&bad.p)==ORTTS_INVALID&&!bad.p,"English model silently accepts Chinese language");r.language=nullptr;const char*saved=r.text;r.text="你好";expect(ortts_tts_synthesize(e.p,&r,nullptr,nullptr,&bad.p)==ORTTS_INVALID,"English-only auto silently accepts Han text");r.text="\xff";expect(ortts_tts_synthesize(e.p,&r,nullptr,nullptr,&bad.p)==ORTTS_INVALID,"invalid UTF-8 accepted");r.text=saved;r.language="en";r.voice_id="no-such-voice";expect(ortts_tts_synthesize(e.p,&r,nullptr,nullptr,&bad.p)!=ORTTS_OK&&!bad.p,"invalid voice silently falls back");}
 }
 {
  std::string path=root+"/Kokoro-82M-GGUF/kokoro-82m-q8_0.gguf";auto cfg=config("kokoro_tts",path,true);Tts e;ok(ortts_tts_create(&cfg,&e.p));ortts_tts_request r{};r.struct_size=sizeof(r);r.text="今天上午九点半。请检查车票。欢迎使用本地语音合成。";r.language="zh";r.voice_id="zf_xiaobei";ortts_speech_option opts{"text_chunk_size","12"};r.options=&opts;r.option_count=1;Capture c;c.cancel=true;Audio bad;expect(ortts_tts_synthesize(e.p,&r,receive,&c,&bad.p)==ORTTS_CANCELLED&&!bad.p&&c.chunks==1&&c.shared_gate,"stream cancel/shared legacy gate");c={};Audio good;ok(ortts_tts_synthesize(e.p,&r,receive,&c,&good.p));expect(c.frames==ortts_speech_audio_frames(good.p)&&c.chunks>=2&&c.shared_gate,"reset after cancel/chunk totals");std::cout<<"stream_cancel_reset=pass chunks="<<c.chunks<<"\n";
 }
 for(const std::string f:{"sense_asr","moonshine_asr"}){
  std::string path=root+(f=="sense_asr"?"/sensevoice-small-q8-audiocpp-v1.gguf":"/Moonshine-Streaming-GGUF/moonshine-streaming-tiny-q8_0.gguf");auto cfg=config(f.c_str(),path);cfg.max_input_frames=16000*10;Asr e;ok(ortts_asr_create(&cfg,&e.p));Text offline;ok(ortts_asr_run(e.p,english.data(),english.size(),"en",&offline.p));expect(std::string(ortts_transcript_text(offline.p)).find("station")!=std::string::npos,"ASR lost fixture text");
  for(size_t i=0;i<english.size();i+=1000)ok(ortts_asr_accept(e.p,english.data()+i,std::min(size_t(1000),english.size()-i)));Text final;ok(ortts_asr_finish(e.p,"en",&final.p));expect(std::string(ortts_transcript_text(final.p))==ortts_transcript_text(offline.p),"buffered/offline mismatch");
  std::vector<float>zeros(16000);Text silence;ok(ortts_asr_run(e.p,zeros.data(),zeros.size(),"en",&silence.p));expect(std::string(ortts_transcript_text(silence.p)).empty(),"digital silence hallucination");
  ok(ortts_asr_accept(e.p,zeros.data(),100));Text pending;expect(ortts_asr_run(e.p,zeros.data(),zeros.size(),"en",&pending.p)==ORTTS_INVALID,"pending input not protected");ok(ortts_asr_reset(e.p));expect(ortts_asr_finish(e.p,"en",&pending.p)==ORTTS_INVALID,"finish after reset should reject");
  zeros.resize(16000*10+1);expect(ortts_asr_accept(e.p,zeros.data(),zeros.size())==ORTTS_INVALID,"buffer overflow not rejected");float nan=std::numeric_limits<float>::quiet_NaN();expect(ortts_asr_accept(e.p,&nan,1)==ORTTS_INVALID,"nonfinite ASR accepted");
  if(f=="sense_asr"){Text zh;ok(ortts_asr_run(e.p,chinese.data(),chinese.size(),"zh",&zh.p));expect(std::string(ortts_transcript_text(zh.p)).find("车票")!=std::string::npos,"Chinese ASR missing content");std::cout<<"sense_zh="<<ortts_transcript_text(zh.p)<<"\n";}
  else{Text bad;expect(ortts_asr_run(e.p,chinese.data(),chinese.size(),"zh",&bad.p)==ORTTS_INVALID,"English ASR accepts unsupported language");}
  std::cout<<f<<" offline_buffer_reset_silence_bounds=pass text="<<ortts_transcript_text(final.p)<<"\n";
 }
 {
  std::string path=root+"/sensevoice-small-q8-audiocpp-v1.gguf";auto cfg=config("sense_asr",path);std::string vad=std::filesystem::absolute(std::getenv("ORTTS_TEST_VAD_MODEL")?std::getenv("ORTTS_TEST_VAD_MODEL"):"_work/runtime-speech/assets/framework/models/silero_vad/silero_vad_16k.safetensors").string();ortts_speech_option option{"sense_asr.vad_model_path",vad.c_str()};cfg.session_options=&option;cfg.session_option_count=1;Asr e;ok(ortts_asr_create(&cfg,&e.p));
  std::vector<float>quiet(16000*2);for(size_t i=0;i<quiet.size();++i)quiet[i]=float(1e-6*std::sin(double(i)*0.1));Text text;ok(ortts_asr_run(e.p,quiet.data(),quiet.size(),"zh",&text.p));expect(std::string(ortts_transcript_text(text.p)).empty(),"VAD NoSpeech incorrectly retranscribed whole input");std::cout<<"sense_vad_nonspeech=pass\n";
 }
 std::cout<<"PASS\n";return 0;
 }catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<"\n";return 1;}}
