#include <chrono>
#include <cmath>
#include <fstream>
#include <filesystem>
#include <iostream>
#include <string>
#include <vector>
#include <sys/resource.h>
#include <mach/mach.h>
#ifdef USE_SHERPA
#include "c-api-macos.h"
#else
#include "ortts_speech.h"
#endif
using Clock=std::chrono::steady_clock;
double ms(Clock::time_point t){return std::chrono::duration<double,std::milli>(Clock::now()-t).count();}
size_t rss(){mach_task_basic_info_data_t v{};mach_msg_type_number_t n=MACH_TASK_BASIC_INFO_COUNT;return task_info(mach_task_self(),MACH_TASK_BASIC_INFO,(task_info_t)&v,&n)==KERN_SUCCESS?v.resident_size:0;}
double cpu(){rusage u{};getrusage(RUSAGE_SELF,&u);return u.ru_utime.tv_sec+u.ru_utime.tv_usec/1e6+u.ru_stime.tv_sec+u.ru_stime.tv_usec/1e6;}
void u32(std::ofstream&f,uint32_t n){f.write((char*)&n,4);}void u16(std::ofstream&f,uint16_t n){f.write((char*)&n,2);}
void wav(const std::string&p,const float*s,size_t n,int rate){std::ofstream f(p,std::ios::binary);f.write("RIFF",4);u32(f,36+n*4);f.write("WAVEfmt ",8);u32(f,16);u16(f,3);u16(f,1);u32(f,rate);u32(f,rate*4);u16(f,4);u16(f,32);f.write("data",4);u32(f,n*4);f.write((char*)s,n*4);if(!f)throw std::runtime_error("WAV write failed");}
int main(int argc,char**argv){try{if(argc!=5)throw std::runtime_error("MODEL_ROOT CASE OUTPUT.wav THREADS");std::string root=argv[1],kind=argv[2],out=argv[3];int threads=std::stoi(argv[4]);bool zh=kind=="zh";std::string text=zh?"今天上午九点半，请检查车票和随身行李。":"At nine thirty, please check the train ticket and call the station.";if(kind=="long")text=text+" "+text+" "+text;auto begin=Clock::now();size_t before=rss();
#ifdef USE_SHERPA
 std::string model=root+(std::filesystem::exists(root+"/model.int8.onnx")?"/model.int8.onnx":"/model.onnx"),voices=root+"/voices.bin",tokens=root+"/tokens.txt",data=root+"/espeak-ng-data",lex=root+(zh?"/lexicon-zh.txt":"/lexicon-us-en.txt");SherpaOnnxOfflineTtsConfig cfg{};cfg.model.kokoro.model=model.c_str();cfg.model.kokoro.voices=voices.c_str();cfg.model.kokoro.tokens=tokens.c_str();cfg.model.kokoro.data_dir=data.c_str();cfg.model.kokoro.lexicon=lex.c_str();cfg.model.kokoro.lang=zh?"zh":"en-us";cfg.model.kokoro.length_scale=1;cfg.model.provider="cpu";cfg.model.num_threads=threads;cfg.max_num_sentences=1;cfg.silence_scale=0.2;auto*engine=SherpaOnnxCreateOfflineTts(&cfg);if(!engine)throw std::runtime_error("Sherpa create failed");
#else
 std::string model=root+"/Kokoro-82M-GGUF/kokoro-82m-q8_0.gguf";ortts_speech_config cfg{};cfg.struct_size=sizeof(cfg);cfg.family="kokoro_tts";cfg.model_path=model.c_str();cfg.threads=threads;cfg.espeak_library="/opt/homebrew/lib/libespeak-ng.dylib";cfg.espeak_data="/opt/homebrew/share/espeak-ng-data";ortts_tts*engine=nullptr;if(ortts_tts_create(&cfg,&engine))throw std::runtime_error(ortts_last_error());
#endif
 double load=ms(begin);std::cout<<"{\"load_ms\":"<<load<<",\"rss_before\":"<<before<<",\"rss_loaded\":"<<rss()<<",\"threads\":"<<threads<<",\"runs\":[";
 for(int i=0;i<4;i++){auto start=Clock::now();double c=cpu();const float*pcm=nullptr;size_t n=0;int rate=0;
#ifdef USE_SHERPA
 auto*audio=SherpaOnnxOfflineTtsGenerate(engine,text.c_str(),zh?45:3,1.0);if(!audio)throw std::runtime_error("Sherpa synth failed");pcm=audio->samples;n=audio->n;rate=audio->sample_rate;
#else
 ortts_tts_request req{};req.struct_size=sizeof(req);req.text=text.c_str();req.language=zh?"zh":"en";req.voice_id=zh?"zf_xiaobei":"af_heart";req.seed_set=1;req.seed=42;ortts_speech_audio*audio=nullptr;if(ortts_tts_synthesize(engine,&req,nullptr,nullptr,&audio))throw std::runtime_error(ortts_last_error());pcm=ortts_speech_audio_samples(audio);n=ortts_speech_audio_frames(audio);rate=ortts_speech_audio_sample_rate(audio);
#endif
 double wall=ms(start),cpu_s=cpu()-c;if(rate!=24000||!n)throw std::runtime_error("invalid audio format");double energy=0;for(size_t j=0;j<n;j++){if(!std::isfinite(pcm[j]))throw std::runtime_error("nonfinite PCM");energy+=double(pcm[j])*pcm[j];}if(energy/n<1e-10)throw std::runtime_error("empty signal");if(i)std::cout<<",";std::cout<<"{\"iteration\":"<<i<<",\"wall_ms\":"<<wall<<",\"cpu_s\":"<<cpu_s<<",\"audio_s\":"<<double(n)/rate<<",\"rtf\":"<<wall/(1000.0*n/rate)<<",\"rss\":"<<rss()<<"}";if(i==3)wav(out,pcm,n,rate);
#ifdef USE_SHERPA
 SherpaOnnxDestroyOfflineTtsGeneratedAudio(audio);
#else
 ortts_speech_audio_free(audio);
#endif
 }
 rusage u{};getrusage(RUSAGE_SELF,&u);std::cout<<"],\"peak_rss_bytes\":"<<u.ru_maxrss<<"}"<<std::endl;
#ifdef USE_SHERPA
 SherpaOnnxDestroyOfflineTts(engine);
#else
 ortts_tts_free(engine);
#endif
 return 0;}catch(const std::exception&e){std::cerr<<e.what()<<std::endl;return 1;}}
