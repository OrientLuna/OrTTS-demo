#include "ortts_speech.h"
#include <algorithm>
#include <chrono>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <sys/resource.h>
struct Events {int partial=0,final=0;bool cancel=false;std::string text;};
static int event(void* p,const ortts_asr_stream_event* e){
 auto& s=*static_cast<Events*>(p);if(e->endpoint==0)++s.partial;else{++s.final;s.text=e->text;}
 std::cout<<"EVENT\t"<<e->endpoint<<"\t"<<e->segment_id<<"\t"<<e->revision<<"\t"<<e->start_frame<<"\t"<<e->end_frame<<"\t"<<e->text<<"\n";
 return s.cancel?1:0;
}
static void check(ortts_status s){if(s!=ORTTS_OK)throw std::runtime_error(ortts_last_error());}
int main(int argc,char**argv){
 if(argc!=3)return 2;ortts_asr_stream* engine=nullptr;
 try{
  std::ifstream f(argv[2],std::ios::binary|std::ios::ate);if(!f)throw std::runtime_error("Missing PCM");auto bytes=f.tellg();if(bytes<=0||bytes%4)throw std::runtime_error("Invalid PCM");std::vector<float> pcm(size_t(bytes)/4);f.seekg(0);f.read(reinterpret_cast<char*>(pcm.data()),bytes);
  ortts_speech_config c{};c.struct_size=sizeof(c);c.family="streaming_paraformer";c.model_path=argv[1];c.threads=2;c.streaming=1;
  ortts_asr_stream_config v{sizeof(v),200,400,15000,0,0.003f};auto load=std::chrono::steady_clock::now();check(ortts_asr_stream_create(&c,&v,&engine));
  std::cout<<"LOAD_MS\t"<<std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-load).count()<<"\n";
  std::string reference;
  for(int pass=0;pass<2;++pass){check(ortts_asr_stream_reset(engine));Events s;auto t=std::chrono::steady_clock::now();
   for(size_t i=0;i<pcm.size();i+=1600)check(ortts_asr_stream_accept(engine,pcm.data()+i,std::min(size_t(1600),pcm.size()-i),event,&s));
   check(ortts_asr_stream_finish(engine,event,&s));check(ortts_asr_stream_finish(engine,event,&s));
   if(s.final!=1||s.text.empty())throw std::runtime_error("Expected exactly one nonempty final");
   if(pass==0)reference=s.text;else if(reference!=s.text)throw std::runtime_error("Reset changed transcript");
   auto ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-t).count();struct rusage ru{};getrusage(RUSAGE_SELF,&ru);
   std::cout<<"RESULT\t"<<pass<<"\t"<<ms<<"\t"<<pcm.size()/16000.0<<"\t"<<ms/(pcm.size()/16.0)<<"\t"<<s.partial<<"\t"<<s.final<<"\t"<<ru.ru_maxrss<<"\n";
  }
  Events s;ortts_asr_stream_cancel(engine);if(ortts_asr_stream_accept(engine,pcm.data(),std::min(size_t(1600),pcm.size()),event,&s)!=ORTTS_CANCELLED)throw std::runtime_error("Cancel not sticky");check(ortts_asr_stream_reset(engine));check(ortts_asr_stream_accept(engine,pcm.data(),std::min(size_t(1600),pcm.size()),event,&s));
  check(ortts_asr_stream_reset(engine));s={};std::vector<float> silence(1600);check(ortts_asr_stream_accept(engine,silence.data(),silence.size(),event,&s));check(ortts_asr_stream_finish(engine,event,&s));if(!s.text.empty())throw std::runtime_error("Silence produced text");
  ortts_asr_stream_free(engine);engine=nullptr;check(ortts_asr_stream_create(&c,&v,&engine));ortts_asr_stream_free(engine);engine=nullptr;std::cout<<"PASS\treset-cancel-silence-free-reload\n";return 0;
 }catch(const std::exception&e){if(engine)ortts_asr_stream_free(engine);std::cerr<<e.what()<<"\n";return 1;}
}
