#include "ortts_speech.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include <mach/mach.h>

void expect(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
void check(ortts_status s){if(s!=ORTTS_OK)throw std::runtime_error(ortts_last_error());}
size_t rss(){mach_task_basic_info_data_t info{};mach_msg_type_number_t n=MACH_TASK_BASIC_INFO_COUNT;
 return task_info(mach_task_self(),MACH_TASK_BASIC_INFO,(task_info_t)&info,&n)==KERN_SUCCESS?info.resident_size:0;}
struct Stream {ortts_asr_stream*p=nullptr;~Stream(){ortts_asr_stream_free(p);}};
struct Event {int endpoint;uint64_t segment,start,end,revision;std::string text;};
struct Capture {
 std::vector<Event> events;bool cancel=false,gate=false;
 std::atomic<bool>* notify=nullptr;std::atomic<bool>* cancel_complete=nullptr;
};
int receive(void*u,const ortts_asr_stream_event*e){auto&c=*static_cast<Capture*>(u);
 expect(e&&e->struct_size==sizeof(*e)&&e->text&&std::string(e->language)=="en","event format");
 expect(e->end_frame>=e->start_frame,"event range");
 if(!c.events.empty()&&c.events.back().segment==e->segment_id)
  expect(e->revision>c.events.back().revision&&e->end_frame>=c.events.back().end,"event ordering");
 c.events.push_back({e->endpoint,e->segment_id,e->start_frame,e->end_frame,e->revision,e->text});
 ortts_asr_stream_stats stats{};stats.struct_size=sizeof(stats);
 c.gate=ortts_asr_stream_get_stats(nullptr,&stats)==ORTTS_BUSY;
 if(c.notify){c.notify->store(true);while(c.cancel_complete&&!c.cancel_complete->load())std::this_thread::yield();}
 return c.cancel;
}
void feed(Stream&s,const std::vector<float>&audio,size_t chunk,Capture&c){
 for(size_t i=0;i<audio.size();i+=chunk)check(ortts_asr_stream_accept(s.p,audio.data()+i,std::min(chunk,audio.size()-i),receive,&c));
}
ortts_asr_stream_stats stats(Stream&s){ortts_asr_stream_stats v{};v.struct_size=sizeof(v);check(ortts_asr_stream_get_stats(s.p,&v));return v;}
std::string final_text(const Capture&c){std::string result;for(auto&e:c.events)if(e.endpoint)result+=e.text;return result;}
int main(int argc,char**argv){if(argc!=3&&argc!=4)return 2;try{
 std::string model=argv[1];std::ifstream file(argv[2],std::ios::binary|std::ios::ate);
 expect(bool(file),"fixture missing");size_t bytes=file.tellg();expect(bytes%4==0&&bytes>16000,"fixture invalid");file.seekg(0);
 std::vector<float>audio(bytes/4);file.read(reinterpret_cast<char*>(audio.data()),bytes);
 expect(ortts_asr_stream_abi_version()==1,"incremental ABI missing");
 ortts_speech_config base{};base.struct_size=sizeof(base);base.family="moonshine_asr";base.model_path=model.c_str();base.threads=4;base.streaming=1;
 ortts_asr_stream_config settings{sizeof(settings),400,1000,15000,0,0.003F};
 if(argc==4){
  std::string mode=argv[3];expect(mode=="memory"||mode=="memory-default","unknown mode");
  size_t before=rss();settings.max_segment_ms=mode=="memory"?4000:15000;Stream only;check(ortts_asr_stream_create(&base,&settings,&only.p));
  size_t loaded=rss();Capture c;std::vector<size_t>resident;size_t finals=0;
  auto begin=std::chrono::steady_clock::now();
  for(int i=0;i<82;++i){feed(only,audio,7777,c);for(auto&e:c.events)if(e.endpoint==ORTTS_ASR_LIMIT)++finals;c.events.clear();
   auto s=stats(only);expect(s.segment_frames<=settings.max_segment_ms*16&&s.cached_encoder_frames<=settings.max_segment_ms/20+1&&s.buffered_pcm_frames<=settings.max_segment_ms*16+320,"bounded state");
   if(i==9||i==29||i==49||i==69||i==81)resident.push_back(rss());}
  auto s=stats(only);check(ortts_asr_stream_finish(only.p,receive,&c));
  size_t lo=*std::min_element(resident.begin(),resident.end()),hi=*std::max_element(resident.begin(),resident.end());
  if(hi-lo>=32*1024*1024||finals<82*audio.size()/(settings.max_segment_ms*16)){
   std::cerr<<"segment_limit_ms="<<settings.max_segment_ms<<" rss_spread_bytes="<<(hi-lo)<<" limit_finals="<<finals<<" rss_samples=";
   for(auto value:resident)std::cerr<<value<<",";
   std::cerr<<"\n";
  }
  expect(hi-lo<32*1024*1024&&finals>=82*audio.size()/(settings.max_segment_ms*16),"memory growth or missing limit endpoint");
  double total=std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();
  std::cout<<"{\"pass\":true,\"segment_limit_ms\":"<<settings.max_segment_ms<<",\"audio_s\":"<<82*audio.size()/16000.0<<",\"wall_s\":"<<total
   <<",\"rss_before_bytes\":"<<before<<",\"rss_loaded_bytes\":"<<loaded<<",\"rss_spread_bytes\":"<<hi-lo
   <<",\"limit_finals\":"<<finals<<",\"encoder_ms\":"<<s.encoder_ms<<",\"decoder_ms\":"<<s.decoder_ms
   <<",\"peak_pcm_frames\":"<<s.peak_buffered_pcm_frames<<",\"peak_encoder_frames\":"<<s.peak_cached_encoder_frames
   <<",\"rss_samples\":[";for(size_t i=0;i<resident.size();++i){if(i)std::cout<<',';std::cout<<resident[i];}std::cout<<"]}\n";return 0;
 }
 Stream stream;check(ortts_asr_stream_create(&base,&settings,&stream.p));
 Capture first;feed(stream,audio,777,first);expect(std::any_of(first.events.begin(),first.events.end(),[](auto&e){return !e.endpoint;}),"No partial before finish");
 expect(first.events.back().end<audio.size(),"partial emitted only at finish");
 check(ortts_asr_stream_finish(stream.p,receive,&first));expect(first.gate,"shared BUSY gate");
 std::string expected=final_text(first);expect(expected.find("station")!=std::string::npos,"lost fixture content");
 size_t count=first.events.size();check(ortts_asr_stream_finish(stream.p,receive,&first));expect(first.events.size()==count,"repeated flush duplicated final");
 auto done=stats(stream);expect(done.buffered_pcm_frames==0&&done.cached_encoder_frames==0,"flush retains logical cache");
 for(size_t chunk:{size_t(1),size_t(1600),size_t(16000)}){
  check(ortts_asr_stream_reset(stream.p));Capture c;feed(stream,audio,chunk,c);check(ortts_asr_stream_finish(stream.p,receive,&c));
  expect(final_text(c)==expected,"chunk-boundary final differs");
 }
 // Invalid calls are transactional: they must neither consume nor cancel input.
 check(ortts_asr_stream_reset(stream.p));Capture invalid;
 float nan=std::numeric_limits<float>::quiet_NaN();
 expect(ortts_asr_stream_accept(stream.p,&nan,1,receive,&invalid)==ORTTS_INVALID,"NaN accepted");
 expect(ortts_asr_stream_accept(stream.p,audio.data(),0,receive,&invalid)==ORTTS_INVALID,"empty accepted");
 expect(ortts_asr_stream_accept(stream.p,audio.data(),32001,receive,&invalid)==ORTTS_INVALID,"oversized call accepted");
 expect(ortts_asr_stream_accept(stream.p,audio.data(),10,nullptr,nullptr)==ORTTS_INVALID,"missing callback accepted");
 expect(stats(stream).received_frames==0,"invalid input mutated stream");
 std::vector<float>quiet(16000*2);for(size_t i=0;i<quiet.size();++i)quiet[i]=float(1e-6*std::sin(i*.1));
 feed(stream,quiet,1234,invalid);check(ortts_asr_stream_finish(stream.p,receive,&invalid));
 expect(final_text(invalid).empty()&&stats(stream).encoded_samples==0,"quiet hallucination or inference");
 // Cancel between accepts is sticky; reset clears it.
 ortts_asr_stream_cancel(stream.p);
 expect(ortts_asr_stream_accept(stream.p,audio.data(),777,receive,&invalid)==ORTTS_CANCELLED,"cancel not sticky");
 expect(ortts_asr_stream_finish(stream.p,receive,&invalid)==ORTTS_CANCELLED,"cancelled flush accepted");
 check(ortts_asr_stream_reset(stream.p));Capture cancelled;cancelled.cancel=true;bool stopped=false;
 for(size_t i=0;i<audio.size();i+=6400){auto r=ortts_asr_stream_accept(stream.p,audio.data()+i,std::min(size_t(6400),audio.size()-i),receive,&cancelled);
  if(r==ORTTS_CANCELLED){stopped=true;break;}check(r);}
 expect(stopped&&cancelled.events.size()==1,"callback cancellation failed");
 check(ortts_asr_stream_reset(stream.p));Capture concurrent;std::atomic<bool>ready{false},complete{false};
 concurrent.notify=&ready;concurrent.cancel_complete=&complete;
 std::thread canceller([&]{while(!ready.load())std::this_thread::yield();ortts_asr_stream_cancel(stream.p);complete=true;});
 ortts_status concurrent_status=ORTTS_OK;
 for(size_t i=0;i<audio.size()&&concurrent_status==ORTTS_OK;i+=6400)
  concurrent_status=ortts_asr_stream_accept(stream.p,audio.data()+i,std::min(size_t(6400),audio.size()-i),receive,&concurrent);
 // The fixture has partials; if regression prevents one, release the waiting thread.
 if(!ready.load()){ready=true;}canceller.join();
 expect(concurrent_status==ORTTS_CANCELLED,"cross-thread cancel failed");
 check(ortts_asr_stream_reset(stream.p));Capture reused;feed(stream,audio,6400,reused);check(ortts_asr_stream_finish(stream.p,receive,&reused));expect(final_text(reused)==expected,"cancel/reset reuse differs");
 // Independent streams can interleave while retaining their own timelines/state.
 Stream other;check(ortts_asr_stream_create(&base,&settings,&other.p));check(ortts_asr_stream_reset(stream.p));Capture one,two;
 for(size_t i=0;i<audio.size();i+=1600){size_t n=std::min(size_t(1600),audio.size()-i);
  check(ortts_asr_stream_accept(stream.p,audio.data()+i,n,receive,&one));
  check(ortts_asr_stream_accept(other.p,audio.data()+i,n,receive,&two));}
 check(ortts_asr_stream_finish(stream.p,receive,&one));check(ortts_asr_stream_finish(other.p,receive,&two));
 expect(final_text(one)==expected&&final_text(two)==expected,"interleaved state contamination");
 // Energy endpoint and hard limit produce distinct, reusable final events.
 settings.silence_ms=400;settings.max_segment_ms=6000;Stream endpoint;check(ortts_asr_stream_create(&base,&settings,&endpoint.p));
 Capture ended;feed(endpoint,audio,6400,ended);std::vector<float>silence(16000);feed(endpoint,silence,1000,ended);
 expect(std::any_of(ended.events.begin(),ended.events.end(),[](auto&e){return e.endpoint==ORTTS_ASR_SILENCE;}),"energy endpoint missing");
 check(ortts_asr_stream_reset(endpoint.p));
 // Five minutes of continuous, bounded segments; single short fixture repeated.
 // This is a memory/state stress test, not a natural-language accuracy corpus.
 settings.silence_ms=0;settings.max_segment_ms=4000;Stream long_run;check(ortts_asr_stream_create(&base,&settings,&long_run.p));
 Capture long_events;std::vector<size_t>resident;size_t processed=0;
 for(int i=0;i<82;++i){feed(long_run,audio,7777,long_events);processed+=audio.size();
  auto s=stats(long_run);expect(s.segment_frames<=64000&&s.cached_encoder_frames<=201,"segment/cache limit violated");
  expect(s.buffered_pcm_frames<=64000+320,"PCM bound violated");
  if(i==9||i==29||i==49||i==69||i==81)resident.push_back(rss());
  long_events.events.clear();}
 auto last=stats(long_run);Capture last_events;check(ortts_asr_stream_finish(long_run.p,receive,&last_events));
 size_t minimum=*std::min_element(resident.begin(),resident.end());size_t maximum=*std::max_element(resident.begin(),resident.end());
 expect(maximum-minimum<32*1024*1024,"RSS grows after warmup");
 // Creation must reject unavailable model families and invalid settings.
 Stream rejected;base.family="sense_asr";expect(ortts_asr_stream_create(&base,&settings,&rejected.p)==ORTTS_INVALID&&!rejected.p,"offline model accepted");base.family="moonshine_asr";
 settings.update_ms=1;expect(ortts_asr_stream_create(&base,&settings,&rejected.p)==ORTTS_INVALID,"invalid config accepted");
 std::cout<<"{\"pass\":true,\"fixture_final\":\""<<expected<<"\",\"partial_events\":"<<first.events.size()-1
  <<",\"stress_audio_s\":"<<processed/16000.0<<",\"stress_encoder_ms\":"<<last.encoder_ms<<",\"stress_decoder_ms\":"<<last.decoder_ms
  <<",\"peak_pcm_frames\":"<<last.peak_buffered_pcm_frames<<",\"peak_encoder_frames\":"<<last.peak_cached_encoder_frames
  <<",\"rss_spread_bytes\":"<<maximum-minimum<<",\"rss_samples\":[";
 for(size_t i=0;i<resident.size();++i){if(i)std::cout<<',';std::cout<<resident[i];}std::cout<<"]}\n";
 return 0;
 }catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<'\n';return 1;}}
